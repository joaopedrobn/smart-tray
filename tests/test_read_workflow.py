import importlib.util
import json
from pathlib import Path


def test_pending_oem_and_failed_peer_do_not_block_healthy_read(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location("reader", Path(__file__).parents[1] / "scripts/read_local.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    (tmp_path / "diagnostics").mkdir()
    (tmp_path / "profiles").mkdir()
    roles = ["elgin", "novadigital", "led"]
    records = [{"device_id": role, "role": role, "ip": f"10.77.0.{38+i}", "protocol_version": version,
                "metadata": {"name": role, "cloud_dps_candidates": []}} for i, (role, version) in enumerate(zip(roles, ["3.5", "3.4", "3.3"]))]
    for role in roles:
        (tmp_path / "profiles" / f"{role}_profile.json").write_text(json.dumps({"confirmed_commands": {}}))
    (tmp_path / "diagnostics/provisioned.json").write_text(json.dumps({"devices": records}))
    (tmp_path / "diagnostics/discovery-current.json").write_text(json.dumps({"devices": records}))
    monkeypatch.setattr(module, "ROOT", tmp_path)
    class Store:
        def load(self, did):
            return None if did == "elgin" else "0" * 16
    monkeypatch.setattr(module, "CredentialStore", Store)
    queried = []
    def query(record, key):
        queried.append(record["role"])
        if record["role"] == "novadigital":
            raise OSError("raw-sensitive-response")
        return {"result": "local_read_ok", "dps": {"20": {"type": "bool", "value": True}}, "protocol_authenticated": True}
    monkeypatch.setattr(module, "query_status", query)
    module.main()
    report = json.loads((tmp_path / "diagnostics/local_read.json").read_text(encoding="utf-8"))
    assert queried == ["novadigital", "led"]
    assert [r["result"] for r in report["devices"]] == ["pending_oem_provisioning", "read_or_credential_error", "local_read_ok"]
    assert "raw-sensitive-response" not in json.dumps(report)
    assert json.loads((tmp_path / "profiles/elgin_profile.json").read_text())["status"] == "pending_oem_provisioning"


def test_scoped_elgin_reader_preserves_validated_peers(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location("scoped_reader", Path(__file__).parents[1] / "scripts/read_local.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    (tmp_path / "diagnostics").mkdir()
    (tmp_path / "profiles").mkdir()
    records = [{"device_id": role, "role": role, "ip": "10.77.0.138", "protocol_version": "3.5",
                "metadata": {"name": role, "cloud_dps_candidates": []}} for role in ("elgin", "led", "novadigital")]
    for role in ("elgin", "led", "novadigital"):
        (tmp_path / "profiles" / f"{role}_profile.json").write_text(json.dumps({"confirmed_commands": {"validated": True} if role != "elgin" else {}}))
    originals = {role: (tmp_path / "profiles" / f"{role}_profile.json").read_bytes() for role in ("led", "novadigital")}
    for filename in ("provisioned.json", "discovery-current.json"):
        (tmp_path / "diagnostics" / filename).write_text(json.dumps({"devices": records}))
    monkeypatch.setattr(module, "ROOT", tmp_path)
    store = type("Store", (), {"load": lambda self, did: "protected-key"})
    monkeypatch.setattr(module, "CredentialStore", store)
    queried = []
    def query(record, key):
        queried.append(record["device_id"])
        return {"result": "local_read_ok", "protocol_authenticated": True, "dps": {}}
    monkeypatch.setattr(module, "query_status", query)
    module.main(role="elgin")
    assert queried == ["elgin"]
    for role, original in originals.items():
        assert (tmp_path / "profiles" / f"{role}_profile.json").read_bytes() == original
    assert (tmp_path / "diagnostics/local_read_elgin.json").exists()
    assert not (tmp_path / "diagnostics/local_read.json").exists()
