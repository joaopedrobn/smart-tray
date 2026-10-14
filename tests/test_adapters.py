import json
from unittest.mock import Mock
import pytest
from smart_tray.adapters import LedAdapter, SwitchAdapter, ElginAdapter, load_adapters, UnavailableAdapter


def setup_adapter(tmp_path, role="led"):
    cls = LedAdapter if role == "led" else SwitchAdapter
    did, version = (("example-led-0000000001", "3.3") if role == "led" else ("example-switch-000002", "3.4"))
    record = {"role": role, "device_id": did, "protocol_version": version, "ip": "10.77.0.39",
              "metadata": {"cloud_dps_candidates": [{"dp_id": dp, "code": code, "type": "Boolean", "source": "cloud_functions"}
                                                     for dp, code in cls.channels.items()]}}
    profile = {"device_id": did, "protocol": version, "protocol_authenticated": True,
               "confirmed_commands": {code: {"dp": dp, "values": [False, True], "transport": "lan"} for dp, code in cls.channels.items()}}
    store = Mock()
    store.load.return_value = "0" * 16  # Synthetic credential; no DPAPI reads in tests.
    device = Mock()
    factory = Mock(return_value=device)
    adapter = cls(record, profile, store=store, factory=factory, journal_dir=tmp_path)
    return adapter, device, store


@pytest.mark.parametrize("role", ["led", "novadigital"])
def test_read_only_exports_validated_boolean_channels(tmp_path, role):
    adapter, device, _ = setup_adapter(tmp_path, role)
    device.status.return_value = {"dps": {"20": True, "1": False, "2": True, "24": "private-payload", "14": "sensitive"}}
    state = adapter.read()
    assert state.connection == "online"
    assert set(state.values) == set(adapter.channels)
    assert "private" not in repr(state) and "sensitive" not in repr(state)
    device._send_receive_quick.assert_not_called()
    device.close.assert_called_once()


def test_failure_clears_values_and_never_exports_exception(tmp_path):
    adapter, device, _ = setup_adapter(tmp_path)
    device.status.side_effect = OSError("private-credential-in-response")
    state = adapter.read()
    assert state.connection == "offline" and state.values == {}
    assert "private" not in repr(state)


def test_missing_boolean_is_unknown_not_off(tmp_path):
    adapter, device, _ = setup_adapter(tmp_path)
    device.status.return_value = {"dps": {"20": "false"}}
    assert adapter.read().values[20] is None


@pytest.mark.parametrize("dp", [21, 24, 26, 46, 47, 53])
def test_unvalidated_led_command_rejected_before_credentials(tmp_path, dp):
    adapter, device, store = setup_adapter(tmp_path)
    with pytest.raises(ValueError):
        adapter.write(dp, True, False)
    store.load.assert_not_called()
    device.status.assert_not_called()


def test_profile_validation_is_required_not_just_generic_schema(tmp_path):
    adapter, device, store = setup_adapter(tmp_path)
    adapter.profile["confirmed_commands"] = {}
    with pytest.raises(ValueError):
        adapter.write(20, True, False)
    store.load.assert_not_called()


def test_channel_two_is_separate_and_no_other_dps_sent(tmp_path, monkeypatch):
    monkeypatch.setattr("smart_tray.control_validation.time.sleep", lambda _: None)
    adapter, device, _ = setup_adapter(tmp_path, "novadigital")
    device.status.side_effect = [{"dps": {"1": True, "2": True}}, {"dps": {"1": True, "2": False}}]
    device._send_receive_quick.return_value = True
    state = adapter.write(2, True, False)
    assert state.values == {1: True, 2: False}
    assert device.generate_payload.call_args.args[1] == {"2": False}
    assert device._send_receive_quick.call_count == 1
    journal = json.loads(next(tmp_path.glob("*.json")).read_text())
    assert journal["dp"] == 2 and journal["result"]["state_confirmed"]
    assert "0000000000000000" not in json.dumps(journal)


def test_uncertain_send_is_not_retried(tmp_path):
    adapter, device, _ = setup_adapter(tmp_path)
    device.status.return_value = {"dps": {"20": True}}
    device._send_receive_quick.return_value = None
    state = adapter.write(20, True, False)
    assert state.connection == "unknown" and state.values == {}
    assert device._send_receive_quick.call_count == 1
    assert device.status.call_count == 1


def test_changed_baseline_sends_nothing(tmp_path):
    adapter, device, _ = setup_adapter(tmp_path)
    device.status.return_value = {"dps": {"20": False}}
    assert adapter.write(20, True, False).connection == "unknown"
    device._send_receive_quick.assert_not_called()


def test_elgin_has_no_network_or_command_path():
    adapter = ElginAdapter()
    assert adapter.read().connection == "pending"
    assert adapter.read().values == {} and adapter.capabilities == {}
    with pytest.raises(ValueError):
        adapter.command("power", True)


def test_missing_registry_does_not_hide_elgin_or_enable_controls(tmp_path):
    adapters = load_adapters(tmp_path)
    assert adapters["elgin"].read().connection == "pending"
    assert adapters["led"].read().connection == "offline"
    assert isinstance(adapters["novadigital"], UnavailableAdapter)


def test_bad_peer_profile_does_not_block_good_adapter(tmp_path):
    adapter, _, _ = setup_adapter(tmp_path)
    (tmp_path / "diagnostics").mkdir()
    (tmp_path / "profiles").mkdir()
    (tmp_path / "diagnostics/provisioned.json").write_text(json.dumps({"devices": [adapter.record]}))
    (tmp_path / "profiles/led_profile.json").write_text(json.dumps(adapter.profile))
    adapters = load_adapters(tmp_path)
    assert isinstance(adapters["led"], LedAdapter)
    assert isinstance(adapters["novadigital"], UnavailableAdapter)
