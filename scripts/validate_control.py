"""Prepare or execute ONE approved power test step. No automatic restoration."""
import argparse
from datetime import datetime, timezone, timedelta
import json
from pathlib import Path
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from smart_tray.control_validation import verify_target, make_device, safe_snapshot, inspect_led, change_once, exclusive_write_lock
from smart_tray.security import CredentialStore
from smart_tray.diagnostic import quiet, mask


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["prepare", "change", "restore"])
    parser.add_argument("--role", choices=["led", "novadigital"], required=True)
    parser.add_argument("--dp", type=int, required=True)
    parser.add_argument("--plan")
    parser.add_argument("--approved", action="store_true")
    args = parser.parse_args()
    records = json.loads((ROOT / "diagnostics/provisioned.json").read_text(encoding="utf-8"))["devices"]
    record = next(r for r in records if r["role"] == args.role)
    latest = json.loads((ROOT / "diagnostics/discovery-current.json").read_text(encoding="utf-8"))
    found = next(d for d in latest["devices"] if d["device_id"] == record["device_id"])
    record = {**record, "ip": found["ip"], "protocol_version": found["protocol_version"]}
    verify_target(record, args.dp)
    with quiet():
        key = CredentialStore().load(record["device_id"])
    if not key:
        raise RuntimeError("Credential pending")
    directory = ROOT / "diagnostics/control-tests"
    directory.mkdir(exist_ok=True)
    if args.action == "prepare":
        with quiet():
            device = make_device(record, key)
            try:
                raw = device.status()
                snapshot = safe_snapshot(raw)
                initial = raw["dps"].get(str(args.dp))
                if type(initial) is not bool:
                    raise RuntimeError("No Boolean initial state")
                inspection = inspect_led(raw, key) if args.role == "led" else None
            finally:
                device.close()
        plan_id = uuid.uuid4().hex
        plan = {"plan_id": plan_id, "timestamp": datetime.now(timezone(timedelta(hours=-3))).isoformat(),
                "role": args.role, "name": record["metadata"]["name"], "device_id_masked": mask(record["device_id"]),
                "ip": record["ip"], "dp": args.dp, "initial": initial, "proposed": not initial,
                "before": snapshot, "inspection": inspection, "change": None, "restore": None,
                "status": "awaiting_explicit_approval", "physical_confirmed": False}
        (directory / (plan_id + ".json")).write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
    else:
        if not args.approved or not args.plan or len(args.plan) != 32 or any(c not in "0123456789abcdef" for c in args.plan):
            raise ValueError("Approved plan required")
        path = directory / (args.plan + ".json")
        plan = json.loads(path.read_text(encoding="utf-8"))
        if (plan["role"], plan["dp"], plan["ip"]) != (args.role, args.dp, record["ip"]):
            raise ValueError("Plan scope changed")
        if plan[args.action] is not None:
            raise ValueError("Attempt already recorded; no automatic replay")
        if args.action == "restore" and not (plan.get("change") or {}).get("state_confirmed"):
            raise ValueError("Uncertain change; restoration prohibited")
        if args.action == "change" and (datetime.now(timezone.utc) - datetime.fromisoformat(plan["timestamp"])).total_seconds() > 900:
            raise ValueError("Proposal expired; prepare and approve a fresh proposal")
        def persist(result):
            plan[args.action] = result
            path.write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
        # Atomic exclusion prevents concurrent writes, including different devices.
        with exclusive_write_lock(directory):
                expected = plan["initial"] if args.action == "change" else plan["proposed"]
                value = plan["proposed"] if args.action == "change" else plan["initial"]
                result = change_once(record, key, args.dp, expected, value, approved=True, journal=persist)
                persist(result)
                plan["status"] = result["result"]
                path.write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
    key = None
    print(json.dumps(plan, ensure_ascii=True, indent=2))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        print("Teste interrompido. Nenhum erro bruto ou credencial foi exibido. Revise escopo, aprovacao, conectividade e registro de tentativa.")
        sys.exit(1)
