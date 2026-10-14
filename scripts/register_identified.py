"""Register only user-identified devices with matching discovery ID and ARP MAC."""
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from smart_tray.diagnostic import associate, mask


def main():
    def read(name):
        return json.loads((ROOT / "diagnostics" / name).read_text(encoding="utf-8-sig"))
    identities = read("app-identities.json")["devices"]
    discovered = read("discovery-current.json")
    records = associate(identities, discovered["devices"], read("arp-current.json"))
    path = ROOT / "diagnostics/provisioned.json"
    previous = {r["device_id"]: r for r in read("provisioned.json")["devices"]} if path.exists() else {}
    for record in records:
        old = previous.get(record["device_id"], {})
        if old:
            record["metadata"] = {**record["metadata"], **old.get("metadata", {})}
            record["credential"] = old.get("credential", "pending")
        profile_path = ROOT / "profiles" / (record["role"] + "_profile.json")
        profile = json.loads(profile_path.read_text(encoding="utf-8"))
        profile.update(name=record["name"], status="identified_awaiting_credentials",
                       device_id=record["device_id"], ip=record["ip"], mac=record["mac"],
                       protocol=record["protocol_version"], protocol_evidence="tinytuya_decoded_lan_discovery",
                       protocol_authenticated=False, identity_evidence=record["identity_evidence"],
                       app=record["app"], manufacturer_user_reported=record["metadata"]["manufacturer"],
                       model_user_reported=record["metadata"]["model"], credential=record["credential"],
                       notes="Identidade confirmada por ID e MAC do aplicativo; leitura e controle aguardam validação.")
        profile_path.write_text(json.dumps(profile, ensure_ascii=False, indent=2), encoding="utf-8")
    path.write_text(json.dumps({"discovery_timestamp": discovered["timestamp"], "devices": records}, ensure_ascii=False, indent=2), encoding="utf-8")
    for r in records:
        print(r["name"], r["ip"], mask(r["device_id"]), "Tuya", r["protocol_version"])


if __name__ == "__main__":
    main()
