import json
import os
from unittest.mock import Mock

import pytest

from smart_tray.security import CredentialStore
from smart_tray.diagnostic import query_status, clean_text, device_details, cloud_connection, collect_device


@pytest.mark.skipif(os.name != "nt", reason="Windows DPAPI")
def test_dpapi_roundtrip_and_no_plaintext(tmp_path):
    store = CredentialStore(tmp_path)
    key = os.urandom(8).hex()
    store.save("test-device", key)
    assert store.load("test-device") == key
    assert key.encode() not in store.path("test-device").read_bytes()
    store.path("test-device").write_bytes(b"corrupted")
    with pytest.raises(RuntimeError, match="unavailable or corrupted"):
        store.load("test-device")


def test_invalid_key_never_written(tmp_path):
    store = CredentialStore(tmp_path)
    with pytest.raises(ValueError):
        store.save("device", "invalid")
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("version", ["3.3", "3.4", "3.5"])
def test_status_only_and_unknown_strings_withheld(version):
    device = Mock()
    device.status.return_value = {"dps": {"1": True, "2": 24, "3": "secret-data", "4": {"token": "secret-data"}}}
    factory = Mock(return_value=device)
    result = query_status({"ip": "10.77.0.38", "protocol_version": version, "device_id": "device"}, "0" * 16, factory)
    assert result["protocol_authenticated"] is True
    assert "secret-data" not in json.dumps(result)
    assert result["dps"]["2"]["value"] == 24
    assert [call[0] for call in device.method_calls] == ["set_socketRetryLimit", "status", "close"]
    assert factory.call_args.kwargs["version"] == float(version)


def test_failed_status_does_not_export_raw_response():
    device = Mock()
    device.status.return_value = {"Err": "914", "Payload": "secret-data"}
    result = query_status({"ip": "10.77.0.38", "protocol_version": "3.4", "device_id": "device"}, "0" * 16, Mock(return_value=device))
    assert not result["protocol_authenticated"]
    assert "secret-data" not in json.dumps(result)


def test_wrong_network_rejected():
    factory = Mock()
    with pytest.raises(ValueError):
        query_status({"ip": "203.0.113.10", "protocol_version": "3.3", "device_id": "device"}, "0" * 16, factory)
    factory.assert_not_called()


def test_cloud_metadata_redacts_secrets_and_does_not_confirm_commands():
    cloud = Mock(token="token-secret")
    cloud._tuyaplatform.return_value = {"success": True, "result": {"id": "device", "name": "name key-secret", "local_key": "key-secret", "uid": "private", "model": "token-secret"}}
    cloud.getdps.return_value = {"success": True, "result": {"functions": [{"dp_id": 1, "code": "switch", "type": "Boolean", "values": "private"}]}}
    metadata, key, outcome = device_details(cloud, "device", "api-secret", "client-secret")
    assert key == "key-secret"
    assert "key-secret" not in json.dumps(metadata)
    assert "token-secret" not in json.dumps(metadata)
    assert "private" not in json.dumps(metadata)
    assert metadata["cloud_dps_candidates"][0]["locally_validated"] is False
    cloud._tuyaplatform.assert_called_once_with("devices/device")


def test_cloud_identity_mismatch_rejected():
    cloud = Mock()
    cloud._tuyaplatform.return_value = {"success": True, "result": {"id": "other", "local_key": "secret"}}
    assert device_details(cloud, "device", "api", "secret") == (None, None, "device_id_mismatch")


def test_exception_closes_socket_without_exporting_exception():
    device = Mock()
    device.status.side_effect = OSError("private")
    with pytest.raises(OSError):
        query_status({"ip": "10.77.0.38", "protocol_version": "3.3", "device_id": "device"}, "0" * 16, Mock(return_value=device))
    device.close.assert_called_once()


def test_cloud_transport_rejects_writes_and_unknown_hosts(monkeypatch):
    import importlib
    import requests
    module = importlib.import_module("tinytuya.Cloud")
    monkeypatch.setattr("tinytuya.Cloud", Mock(return_value=Mock(token="test-token")))
    session = Mock()
    session.__enter__ = Mock(return_value=session)
    session.__exit__ = Mock(return_value=False)
    monkeypatch.setattr(requests, "Session", Mock(return_value=session))
    with cloud_connection("us", "test-api", "test-secret"):
        with pytest.raises(ValueError):
            module.requests.get("https://example.com/")
        with pytest.raises(ValueError):
            module.requests.request("POST", "https://openapi.tuyaus.com/v1.0/devices/device/commands")
        module.requests.get("https://openapi.tuyaus.com/v1.0/devices/device")
    session.get.assert_called_once_with("https://openapi.tuyaus.com/v1.0/devices/device", timeout=(5, 15), allow_redirects=False)


def test_schema_failure_preserves_retrieved_key():
    cloud = Mock(token="token")
    cloud._tuyaplatform.return_value = {"success": True, "result": {"id": "device", "local_key": "0" * 16}}
    cloud.getdps.side_effect = OSError("raw-sensitive-response")
    metadata, key, outcome = collect_device(cloud, "device", "api", "secret")
    assert key == "0" * 16
    assert metadata["cloud_dps_candidates"] == []
    assert "raw-sensitive-response" not in json.dumps(metadata)


def test_one_cloud_device_failure_does_not_stop_other_devices():
    cloud = Mock(token="token")
    cloud._tuyaplatform.side_effect = [OSError("raw-sensitive-response"), {"success": True, "result": {"id": "second", "local_key": "0" * 16}}]
    cloud.getdps.return_value = None
    assert collect_device(cloud, "first", "api", "secret") == (None, None, "device_api_error")
    assert collect_device(cloud, "second", "api", "secret")[1] == "0" * 16
