"""Read only previously identified and DPAPI-provisioned devices."""
import json
import argparse
from pathlib import Path
from datetime import datetime, timezone, timedelta
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from smart_tray.security import CredentialStore
from smart_tray.diagnostic import mask, query_status


def main(role=None):
    (ROOT / 'diagnostics').mkdir(parents=True, exist_ok=True)
    registry = ROOT / "diagnostics/provisioned.json"
    records = json.loads(registry.read_text(encoding="utf-8"))["devices"] if registry.exists() else []
    discovery_path = ROOT / "diagnostics/discovery-current.json"
    if not discovery_path.exists():
        discovery_path = ROOT / "diagnostics/discovery.json"
    discovered = json.loads(discovery_path.read_text(encoding="utf-8"))["devices"] if discovery_path.exists() else []
    registered = {d["device_id"]: d for d in records}
    store = CredentialStore()
    results = []
    for latest in discovered:
        record = registered.get(latest["device_id"])
        if role and (not record or record.get("role") != role):
            continue
        result = {"device_id_masked": mask(latest["device_id"]), "name": None,
                  "ip": latest["ip"], "protocol_announced": latest["protocol_version"],
                  "protocol_authenticated": False, "credential": "pending", "dps": {},
                  "potential_functions": []}
        if not record:
            result["result"] = "identity_and_credential_pending"
            results.append(result)
            continue
        result.update(name=record["metadata"].get("name"), role=record["role"])
        profile_path = ROOT / "profiles" / (record["role"] + "_profile.json")
        profile = json.loads(profile_path.read_text(encoding="utf-8"))
        try:
            key = store.load(record["device_id"])
            if not key or not latest:
                result["result"] = "pending_oem_provisioning" if record["role"] == "elgin" and not key else "credential_or_current_discovery_missing"
            else:
                result.update(ip=latest["ip"], protocol=latest["protocol_version"], credential="available_dpapi")
                result.update(query_status(latest, key))
                candidates = record["metadata"].get("cloud_dps_candidates", [])
                seen = set()
                for c in candidates:
                    marker = (str(c["dp_id"]), c.get("code"))
                    if marker[0] in result.get("dps", {}) and marker not in seen:
                        result["potential_functions"].append(c)
                        seen.add(marker)
                if result.get("result") == "local_read_ok" and record["role"] in {"elgin", "novadigital", "led"}:
                    profile.update(status="local_read_validated_control_unverified", device_id=record["device_id"],
                                   protocol=latest["protocol_version"], observed_dps=result["dps"],
                                   potential_functions=result["potential_functions"])
                    profile.setdefault("confirmed_commands", {})
                    if profile["confirmed_commands"]:
                        profile["status"] = "local_control_validated"
            key = None
        except Exception:
            result["result"] = "read_or_credential_error"
        if result["result"] == "pending_oem_provisioning":
            profile["status"] = "pending_oem_provisioning"
        profile.update(name=result["name"], credential=result["credential"],
                       protocol_authenticated=result["protocol_authenticated"],
                       last_read_result=result["result"])
        if result["result"] == "local_read_ok":
            profile["notes"] = "Leitura LAN autenticada validada; DPS observados e candidatos Cloud registrados. Nenhum comando de controle validado."
            profile["protocol_evidence"] = "authenticated_lan_status_response"
        elif result["result"] == "pending_oem_provisioning":
            profile["notes"] = "Tuya 3.5 anunciado na LAN; Local_Key pendente de autorização da conta Elgin Smart/OEM. Não bloqueia Smart Life."
        profile_path.write_text(json.dumps(profile, ensure_ascii=False, indent=2), encoding="utf-8")
        record.update(credential=result["credential"], local_read=result["result"],
                      protocol_authenticated=result["protocol_authenticated"],
                      provisioning_status="provisioned" if result["credential"] == "available_dpapi" else result["result"])
        results.append(result)
    registry.write_text(json.dumps({"devices": records}, ensure_ascii=False, indent=2), encoding="utf-8")
    report = {"timestamp": datetime.now(timezone(timedelta(hours=-3))).isoformat(), "mode": "read_only", "devices": results,
              "blocker": "no_identified_provisioned_devices" if not records else None}
    output = "local_read.json" if role is None else f"local_read_{role}.json"
    (ROOT / "diagnostics" / output).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print("Dispositivos registrados no diagnóstico:", len(results), "Leituras LAN bem-sucedidas:", sum(r.get("result") == "local_read_ok" for r in results), "Consulte diagnostics/local_read.json.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--role", choices=("elgin", "led", "novadigital"))
    parser.add_argument('--config-root', type=Path)
    args = parser.parse_args()
    if args.config_root:
        ROOT = args.config_root.resolve()
    main(args.role)
