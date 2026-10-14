"""Prepare/read proposals; writes require a separately approved, unreplayed plan."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from smart_tray.elgin_control import read, change_once, validate_value, specification, verified_fan_observations, FUNCTIONS
from smart_tray.control_validation import exclusive_write_lock
from smart_tray.security import CredentialStore
from smart_tray.diagnostic import quiet


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prepare", "change", "restore", "observe", "read"))
    parser.add_argument("--function", choices=tuple(FUNCTIONS), default="power")
    parser.add_argument("--plan")
    parser.add_argument("--approved", action="store_true")
    parser.add_argument("--physical-confirmed", action="store_true")
    args = parser.parse_args()
    record = next(d for d in json.loads((ROOT / "diagnostics/provisioned.json").read_text(encoding="utf-8"))["devices"] if d["role"] == "elgin")
    latest = next(d for d in json.loads((ROOT / "diagnostics/discovery-current.json").read_text(encoding="utf-8"))["devices"] if d["device_id"] == record["device_id"])
    record = {**record, "ip": latest["ip"], "protocol_version": latest["protocol_version"]}
    profile = json.loads((ROOT / "profiles/elgin_profile.json").read_text(encoding="utf-8"))
    record["temperature_unit_confirmed"] = profile.get("temperature_unit_confirmed")
    record["observed_fan_values"] = list(profile.get("observed_fan_settings", {}))
    schema_path = ROOT / "diagnostics/elgin-research/schema-current.json"
    if args.function == "fan" and schema_path.exists():
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        if schema.get("device_id_masked") == "exampl…0003":
            candidates = list(record["metadata"]["cloud_dps_candidates"])
            for query in schema.get("queries", []):
                for c in query.get("entries", []):
                    if c.get("dp_id") == 5 and c.get("section") == "functions" and c.get("type") == "Enum":
                        candidate = {"dp_id": 5, "code": c["code"], "type": "Enum", "source": "cloud_functions", "constraints": c["constraints"]}
                        if candidate not in candidates:
                            candidates.append(candidate)
            record = {**record, "metadata": {**record["metadata"], "cloud_dps_candidates": candidates}}
            sessions = []
            for relative in profile.get("fan_manual_evidence", []):
                evidence_path = (ROOT / relative).resolve()
                if evidence_path.parent != (ROOT / "diagnostics/elgin-research").resolve():
                    raise ValueError("Evidence path outside diagnostic directory")
                sessions.append(json.loads(evidence_path.read_text(encoding="utf-8")))
            for query in schema.get("queries", []):
                for c in query.get("entries", []):
                    if query.get("source") == "things_model" and c.get("ability_id") == 5 and c.get("code") == "windspeed":
                        record["oem_fan_evidence"] = {"bidirectional_manual_verified": verified_fan_observations(sessions),
                            "model_code": c["code"], "model_access": c["access"], "model_type": c["type"],
                            "model_range": c["constraints"].get("range", [])}
    key = CredentialStore().load(record["device_id"])
    if not key:
        raise ValueError("Credential unavailable")
    directory = ROOT / "diagnostics/elgin-tests"
    directory.mkdir(exist_ok=True)
    if args.action == "read":
        output = read(record, key)
    elif args.action == "prepare":
        before = read(record, key)
        dp = str(FUNCTIONS[args.function][0])
        initial = before[dp]["value"]
        proposed = "mid" if args.function == "fan" else not initial if args.function == "power" else initial + 10
        schema_confirmed = True
        validation_basis = "official_write_specification"
        if args.function == "fan":
            if (initial != "low" or before.get("1", {}).get("value") is not True
                    or before.get("4", {}).get("value") != "cold" or before.get("2", {}).get("value") != 240):
                raise ValueError("Fan proposal requires low, power on, cold mode and setpoint 240")
            try:
                validate_value(record, args.function, initial)
                validate_value(record, args.function, proposed)
                if specification(record, "fan")["source"] != "cloud_functions":
                    schema_confirmed = False
                    validation_basis = "oem_observed_bidirectional_with_model"
            except ValueError:
                schema_confirmed = False
                validation_basis = "missing_verified_fan_evidence"
        if args.function == "temperature" and (before.get("1", {}).get("value") is not True or before.get("4", {}).get("value") != "cold"):
            raise ValueError("Temperature proposal requires power on and cold mode")
        if args.function != "fan":
            validate_value(record, args.function, initial)
            validate_value(record, args.function, proposed)
        output = {"plan_id": uuid.uuid4().hex, "timestamp": datetime.now(timezone.utc).isoformat(),
                  "device_id_masked": "exampl…0003", "ip": record["ip"], "protocol": "3.5",
                  "function": args.function, "dp": int(dp), "initial": initial, "proposed": proposed,
                  "before": before, "change": None, "restore": None, "physical_confirmations": {},
                  "restoration_policy": "separate_explicit_approval_required",
                  "schema_confirmed": schema_confirmed,
                  "validation_basis": validation_basis,
                  "status": "awaiting_explicit_approval" if schema_confirmed or validation_basis == "oem_observed_bidirectional_with_model" else "blocked_missing_official_fan_schema"}
        (directory / (output["plan_id"] + ".json")).write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    else:
        if not args.plan or len(args.plan) != 32 or any(c not in "0123456789abcdef" for c in args.plan):
            raise ValueError("Exact plan required")
        path = directory / (args.plan + ".json")
        output = json.loads(path.read_text(encoding="utf-8"))
        if output.get("status") == "cancelled_by_user":
            raise ValueError("Cancelled plan cannot be executed")
        if args.function == "fan" and args.action != "observe" and not output.get("schema_confirmed") and output.get("validation_basis") != "oem_observed_bidirectional_with_model":
            raise ValueError("Prepare a new fan proposal after official schema verification")
        if (output["function"], output["ip"], output["protocol"]) != (args.function, record["ip"], "3.5"):
            raise ValueError("Plan scope changed")
        if args.action == "observe":
            phase = "restore" if output["restore"] else "change"
            if not args.physical_confirmed or not (output[phase] or {}).get("state_confirmed"):
                raise ValueError("LAN and explicit physical confirmation required")
            output["physical_confirmations"][phase] = True
        else:
            if not args.approved or output[args.action] is not None:
                raise ValueError("Explicit approval required; attempted commands cannot be replayed")
            if args.action == "restore" and not output["physical_confirmations"].get("change"):
                raise ValueError("Physical confirmation required before restoration")
            if args.action == "change" and (datetime.now(timezone.utc) - datetime.fromisoformat(output["timestamp"])).total_seconds() > 900:
                raise ValueError("Proposal expired")
            expected, value = (output["initial"], output["proposed"]) if args.action == "change" else (output["proposed"], output["initial"])
            def persist(result):
                output[args.action] = result
                path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
            with exclusive_write_lock(directory):
                result = change_once(record, key, args.function, expected, value, approved=True, journal=persist)
            output[args.action] = result
        path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(output, ensure_ascii=True, indent=2))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        print("Operacao interrompida. Nenhum erro bruto exibido; nenhuma escrita sera repetida.")
        raise SystemExit(1)
