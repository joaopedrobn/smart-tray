"""Exact-identity Elgin provisioning and status only; peers are never modified."""
import json
from datetime import datetime, timezone
from pathlib import Path

from .diagnostic import collect_device, mask, query_status, quiet
from .security import CredentialStore

ELGIN_ID = "example-elgin-00000003"
ELGIN_MAC = "02:00:00:00:00:03"


def provision_and_read(root, cloud, api_id, api_secret, store=None, query=query_status):
    root = Path(root)
    registry_path = root / "diagnostics/provisioned.json"
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    record = next(d for d in registry["devices"] if d.get("role") == "elgin")
    if (record.get("device_id") != ELGIN_ID or record.get("mac", "").lower() != ELGIN_MAC
            or record.get("app") != "Smart Life"
            or record.get("migration_identity_confirmed") is not True):
        raise ValueError("Migrated identity must be confirmed")
    discovery = json.loads((root / "diagnostics/discovery-current.json").read_text(encoding="utf-8"))
    latest = next(d for d in discovery["devices"] if d.get("device_id") == ELGIN_ID)
    if str(latest.get("protocol_version")) != "3.5":
        raise ValueError("Review changed protocol before proceeding")
    store = store or CredentialStore()
    profile_path = root / "profiles/elgin_profile.json"
    profile = json.loads(profile_path.read_text(encoding="utf-8"))
    report = {"timestamp": datetime.now(timezone.utc).isoformat(), "mode": "read_only",
              "device_id_masked": mask(ELGIN_ID), "ip": latest["ip"], "protocol": "3.5",
              "credential": "pending", "protocol_authenticated": False, "dps": {},
              "writes_sent": 0, "result": "pending_smart_life_provisioning"}
    with quiet():
        metadata, key, outcome = collect_device(cloud, ELGIN_ID, api_id, api_secret)
        if metadata:
            record["metadata"].update({k: v for k, v in metadata.items() if v is not None})
        if key:
            store.save(ELGIN_ID, key)
            key = None
        key = store.load(ELGIN_ID)
        if key:
            report["credential"] = "available_dpapi"
            try:
                report.update(query(latest, key))
            except Exception:
                report["result"] = "lan_read_error"
        key = None
    candidates = record["metadata"].get("cloud_dps_candidates", [])
    report["potential_functions"] = [c for c in candidates if str(c["dp_id"]) in report["dps"]]
    status = "local_read_validated_control_unverified" if report["protocol_authenticated"] else report["result"]
    profile.update(app="Smart Life", status=status, ip=latest["ip"], protocol="3.5",
                   credential=report["credential"], protocol_authenticated=report["protocol_authenticated"],
                   last_read_result=report["result"], observed_dps=report["dps"],
                   potential_functions=report["potential_functions"],
                   notes="Migração Smart Life confirmada. Somente provisionamento DPAPI e consulta de estado; controles permanecem bloqueados.")
    if report["protocol_authenticated"]:
        profile["protocol_evidence"] = "authenticated_lan_status_response"
    record.update(ip=latest["ip"], credential=report["credential"], local_read=report["result"],
                  protocol_authenticated=report["protocol_authenticated"],
                  provisioning_status="provisioned" if report["credential"] == "available_dpapi" else report["result"])
    for path, value in ((registry_path, registry), (profile_path, profile),
                        (root / "diagnostics/local_read_elgin.json", report)):
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(path)
    return report
