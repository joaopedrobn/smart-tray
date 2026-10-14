import json
from unittest.mock import Mock
import pytest
from smart_tray.adapters import ElginLanAdapter, load_adapters
from test_elgin_control import record


def setup(tmp_path):
    r = record()
    profile = {"device_id": r["device_id"], "protocol": "3.5", "protocol_authenticated": True,
               "temperature_unit_confirmed": "c", "confirmed_commands": {"temp_set": {
                   "dp": 2, "transport": "lan", "physical_confirmed": True, "scale": 1, "unit": "c"}}}
    store, device = Mock(), Mock()
    store.load.return_value = "synthetic-key"
    adapter = ElginLanAdapter(r, profile, store, Mock(return_value=device), tmp_path)
    return adapter, device, store


def test_elgin_adapter_reads_real_temperature_and_read_only_status(tmp_path):
    adapter, device, store = setup(tmp_path)
    device.status.return_value = {"dps": {"1": True, "2": 240, "3": 215, "4": "cold", "5": "private-data"}}
    state = adapter.read()
    assert state.values == {"power": True, "temperature": 24, "ambient_temperature": 21.5, "mode": "cold"}
    assert set(adapter.capabilities) == {"temperature"}
    assert state.connection == "online" and "private-data" not in repr(state)
    device._send_receive_quick.assert_not_called()
    store.save.assert_not_called()


@pytest.mark.parametrize("name,value", [("power", False), ("mode", "wind"), ("fan", "high"), ("temperature", 24.5), ("temperature", 26), ("temperature", True)])
def test_only_validated_one_degree_temperature_is_accepted(tmp_path, name, value):
    adapter, device, store = setup(tmp_path)
    with pytest.raises(ValueError):
        adapter.command_from_state(name, 24, value)
    store.load.assert_not_called()
    device._send_receive_quick.assert_not_called()


def test_temperature_click_sends_only_dp2_and_preserves_other_devices(tmp_path, monkeypatch):
    monkeypatch.setattr("smart_tray.elgin_control.time.sleep", lambda _: None)
    adapter, device, store = setup(tmp_path)
    device.status.side_effect = [{"dps": {"1": True, "2": 240, "4": "cold"}},
                                 {"dps": {"1": True, "2": 250, "4": "cold"}}]
    device._send_receive_quick.return_value = True
    state = adapter.command_from_state("temperature", 24, 25)
    assert state.values["temperature"] == 25 and state.values["power"] is True and state.values["mode"] == "cold"
    assert device.generate_payload.call_args.args[1] == {"2": 250}
    device._send_receive_quick.assert_called_once()
    assert "synthetic-key" not in next(tmp_path.glob("*.json")).read_text()
    store.save.assert_not_called()


def test_uncertain_elgin_send_clears_state_and_is_not_repeated(tmp_path):
    adapter, device, _ = setup(tmp_path)
    device.status.return_value = {"dps": {"1": True, "2": 240, "4": "cold"}}
    device._send_receive_quick.return_value = None
    state = adapter.command_from_state("temperature", 24, 25)
    assert state.connection == "unknown" and state.values == {}
    device._send_receive_quick.assert_called_once()
    assert device.status.call_count == 1


def test_profile_physical_validation_required(tmp_path):
    adapter, device, store = setup(tmp_path)
    adapter.profile["confirmed_commands"]["temp_set"]["physical_confirmed"] = False
    with pytest.raises(ValueError):
        adapter.command_from_state("temperature", 24, 25)
    store.load.assert_not_called()


def test_missing_credential_and_error_are_sanitized(tmp_path):
    adapter, device, store = setup(tmp_path)
    store.load.return_value = None
    assert adapter.read().connection == "offline"
    store.load.return_value = "synthetic-key"
    device.status.side_effect = OSError("synthetic-key")
    state = adapter.read()
    assert state.connection == "offline" and "synthetic-key" not in repr(state)


def test_loader_enables_only_physically_validated_elgin_profile(tmp_path):
    adapter, _, _ = setup(tmp_path)
    (tmp_path / "diagnostics").mkdir()
    (tmp_path / "profiles").mkdir()
    (tmp_path / "diagnostics/provisioned.json").write_text(json.dumps({"devices": [adapter.record]}))
    (tmp_path / "diagnostics/discovery-current.json").write_text(json.dumps({"devices": [adapter.record]}))
    (tmp_path / "profiles/elgin_profile.json").write_text(json.dumps(adapter.profile))
    adapters = load_adapters(tmp_path)
    assert isinstance(adapters["elgin"], ElginLanAdapter)
    assert set(adapters["elgin"].capabilities) == {"temperature"}
