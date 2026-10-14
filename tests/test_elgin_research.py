import json
from unittest.mock import Mock
import pytest

from smart_tray.elgin_research import ELGIN_ID, ELGIN_MAC, provision_and_read


def prepare(root):
    (root / "diagnostics").mkdir()
    (root / "profiles").mkdir()
    peer = {"role": "led", "device_id": "peer", "credential": "available_dpapi", "metadata": {}}
    elgin = {"role": "elgin", "device_id": ELGIN_ID, "mac": ELGIN_MAC,
             "app": "Smart Life", "migration_identity_confirmed": True, "metadata": {}}
    (root / "diagnostics/provisioned.json").write_text(json.dumps({"devices": [peer, elgin]}))
    (root / "diagnostics/discovery-current.json").write_text(json.dumps({"devices": [
        {"device_id": ELGIN_ID, "ip": "10.77.0.138", "protocol_version": "3.5"}]}))
    (root / "profiles/elgin_profile.json").write_text(json.dumps({"confirmed_commands": {}}))
    (root / "profiles/led_profile.json").write_bytes(b'validated-peer-untouched')
    return peer


def test_secure_elgin_provision_and_status_preserve_peers(tmp_path, monkeypatch):
    peer = prepare(tmp_path)
    monkeypatch.setattr("smart_tray.elgin_research.collect_device", lambda *a: (
        {"name": "Elgin", "cloud_dps_candidates": [{"dp_id": 1, "code": "switch"}]}, "protected-key", "metadata_available"))
    store = Mock()
    store.load.return_value = "protected-key"
    query = Mock(return_value={"result": "local_read_ok", "protocol_authenticated": True,
                               "dps": {"1": {"value": True}}})
    result = provision_and_read(tmp_path, Mock(), "access", "secret", store, query)
    store.save.assert_called_once_with(ELGIN_ID, "protected-key")
    store.load.assert_called_once_with(ELGIN_ID)
    query.assert_called_once()
    assert result["writes_sent"] == 0 and result["protocol_authenticated"]
    assert json.loads((tmp_path / "diagnostics/provisioned.json").read_text())["devices"][0] == peer
    assert (tmp_path / "profiles/led_profile.json").read_bytes() == b'validated-peer-untouched'
    assert json.loads((tmp_path / "profiles/elgin_profile.json").read_text())["confirmed_commands"] == {}
    assert all("protected-key" not in p.read_text(encoding="utf-8") for p in tmp_path.rglob("*.json"))


def test_migrated_identity_required_before_cloud_or_store(tmp_path):
    prepare(tmp_path)
    p = tmp_path / "diagnostics/provisioned.json"
    data = json.loads(p.read_text())
    data["devices"][1]["device_id"] = "different-device"
    p.write_text(json.dumps(data))
    store, cloud = Mock(), Mock()
    with pytest.raises(ValueError):
        provision_and_read(tmp_path, cloud, "access", "secret", store)
    assert not store.mock_calls and not cloud.mock_calls


def test_cloud_pending_and_lan_failure_never_enable_controls(tmp_path, monkeypatch):
    prepare(tmp_path)
    monkeypatch.setattr("smart_tray.elgin_research.collect_device", lambda *a: (None, None, "device_api_error"))
    store = Mock()
    store.load.return_value = None
    query = Mock(side_effect=OSError("sensitive-error"))
    result = provision_and_read(tmp_path, Mock(), "access", "secret", store, query)
    query.assert_not_called()
    store.save.assert_not_called()
    assert result["result"] == "pending_smart_life_provisioning"
    store.load.return_value = "protected-key"
    result = provision_and_read(tmp_path, Mock(), "access", "secret", store, query)
    assert result["result"] == "lan_read_error" and not result["protocol_authenticated"]
    assert "sensitive-error" not in json.dumps(result)
