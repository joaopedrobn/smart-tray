from unittest.mock import Mock
import pytest
from smart_tray.elgin_control import change_once, validate_value, snapshot
from smart_tray.elgin_research import ELGIN_ID


def record():
    return {"role": "elgin", "device_id": ELGIN_ID, "ip": "10.77.0.138", "protocol_version": "3.5",
            "protocol_authenticated": True, "temperature_unit_confirmed": "c", "metadata": {"cloud_dps_candidates": [
                {"dp_id": 1, "code": "switch", "type": "Boolean", "source": "cloud_functions"},
                {"dp_id": 2, "code": "temp_set", "type": "Integer", "source": "cloud_functions",
                 "constraints": {"min": 160, "max": 900, "step": 10, "scale": 1}},
                {"dp_id": 4, "code": "mode", "type": "Enum", "source": "cloud_status", "constraints": {"range": ["cold", "wind"]}}]}}


def test_elgin_approval_before_transport():
    factory = Mock()
    with pytest.raises(ValueError):
        change_once(record(), "protected", "power", True, False, factory=factory, journal=Mock())
    factory.assert_not_called()


@pytest.mark.parametrize("value", [True, 250.0, 251, 900, 150])
def test_elgin_temperature_rejects_wrong_type_step_and_extreme_schema_values(value):
    with pytest.raises(ValueError):
        validate_value(record(), "temperature", value)


def test_temperature_requires_confirmed_unit_and_exact_schema():
    r = record()
    r["temperature_unit_confirmed"] = None
    with pytest.raises(ValueError):
        validate_value(r, "temperature", 250)
    r = record()
    r["metadata"]["cloud_dps_candidates"][1]["constraints"]["scale"] = 0
    with pytest.raises(ValueError):
        validate_value(r, "temperature", 250)


@pytest.mark.parametrize("name,before,after", [("power", True, False), ("temperature", 240, 250)])
def test_one_elgin_write_journal_before_send_and_fresh_status(name, before, after, monkeypatch):
    monkeypatch.setattr("smart_tray.elgin_control.time.sleep", lambda _: None)
    dp = "1" if name == "power" else "2"
    device = Mock()
    guards = {"1": True, "4": "cold"} if name == "temperature" else {}
    device.status.side_effect = [{"dps": {**guards, dp: before}}, {"dps": {**guards, dp: after}}]
    events = []
    device._send_receive_quick.side_effect = lambda *a, **k: events.append("send") or True
    result = change_once(record(), "protected", name, before, after, approved=True,
                         journal=lambda r: events.append("journal"), factory=Mock(return_value=device))
    assert events == ["journal", "send"] and result["state_confirmed"]
    assert device.status.call_count == 2
    device._send_receive_quick.assert_called_once()
    assert device.generate_payload.call_args.args[1] == {dp: after}
    assert device.close.call_count == 2


def test_uncertain_send_never_retried_or_restored():
    device = Mock()
    device.status.return_value = {"dps": {"1": True}}
    device._send_receive_quick.return_value = None
    result = change_once(record(), "protected", "power", True, False, approved=True,
                         journal=Mock(), factory=Mock(return_value=device))
    assert result["result"] == "communication_failed_stop_no_retry"
    assert device.status.call_count == 1
    device._send_receive_quick.assert_called_once()


def test_changed_state_and_unknown_function_block_writes():
    device = Mock()
    device.status.return_value = {"dps": {"1": False}}
    result = change_once(record(), "protected", "power", True, False, approved=True,
                         journal=Mock(), factory=Mock(return_value=device))
    assert result["result"] == "state_changed_no_write"
    device._send_receive_quick.assert_not_called()
    with pytest.raises(ValueError):
        validate_value(record(), "fan", "high")


def test_known_enums_exported_unknown_strings_never_logged():
    state = snapshot({"dps": {"4": "cold", "5": "private-value", "122": "protected"}}, record(), "protected")
    assert state["4"]["value"] == "cold"
    assert "private-value" not in str(state) and "protected" not in str(state)


@pytest.mark.parametrize("power,mode", [(False, "cold"), (True, "wind"), (True, None)])
def test_setpoint_never_written_when_power_or_cold_mode_changed(power, mode):
    device = Mock()
    device.status.return_value = {"dps": {"1": power, "2": 240, "4": mode}}
    result = change_once(record(), "protected", "temperature", 240, 250, approved=True,
                         journal=Mock(), factory=Mock(return_value=device))
    assert result["result"] == "power_or_mode_changed_no_write"
    device._send_receive_quick.assert_not_called()


def test_setpoint_result_checks_power_and_mode_without_corrective_writes(monkeypatch):
    monkeypatch.setattr("smart_tray.elgin_control.time.sleep", lambda _: None)
    device = Mock()
    device.status.side_effect = [{"dps": {"1": True, "2": 240, "4": "cold"}},
                                 {"dps": {"1": True, "2": 250, "4": "wind"}}]
    device._send_receive_quick.return_value = True
    result = change_once(record(), "protected", "temperature", 240, 250, approved=True,
                         journal=Mock(), factory=Mock(return_value=device))
    assert result["result"] == "power_or_mode_changed_stop_no_retry" and not result["state_confirmed"]
    device._send_receive_quick.assert_called_once()
