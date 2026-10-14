from unittest.mock import Mock
import pytest
from smart_tray.elgin_control import change_once, validate_value, specification, verified_fan_observations
from test_elgin_control import record


def fan_record():
    r = record()
    r["observed_fan_values"] = ["low", "mid"]
    r["metadata"]["cloud_dps_candidates"].append({"dp_id": 5, "code": "vendor_fan",
        "type": "Enum", "source": "cloud_functions", "constraints": {"range": ["low", "mid", "unobserved"]}})
    return r


def test_observations_alone_never_authorize_a_fan_write():
    r = record()
    r["observed_fan_values"] = ["low", "mid"]
    factory = Mock()
    with pytest.raises(ValueError):
        change_once(r, "synthetic", "fan", "mid", "low", approved=True, journal=Mock(), factory=factory)
    factory.assert_not_called()


def test_fan_requires_individual_approval_and_observed_official_enum():
    factory = Mock()
    with pytest.raises(ValueError):
        change_once(fan_record(), "synthetic", "fan", "mid", "low", journal=Mock(), factory=factory)
    factory.assert_not_called()
    for value in ("unobserved", "high", True, 1):
        with pytest.raises(ValueError):
            validate_value(fan_record(), "fan", value)


def test_single_fan_write_is_dp5_only_and_confirmed_by_fresh_status(monkeypatch):
    monkeypatch.setattr("smart_tray.elgin_control.time.sleep", lambda _: None)
    device = Mock()
    device.status.side_effect = [{"dps": {"1": True, "2": 240, "4": "cold", "5": "mid"}},
                                 {"dps": {"1": True, "2": 240, "4": "cold", "5": "low"}}]
    device._send_receive_quick.return_value = True
    result = change_once(fan_record(), "synthetic", "fan", "mid", "low", approved=True,
                         journal=Mock(), factory=Mock(return_value=device))
    assert result["state_confirmed"] and result["after"]["5"]["value"] == "low"
    assert device.generate_payload.call_args.args[1] == {"5": "low"}
    device._send_receive_quick.assert_called_once()
    assert device.status.call_count == 2 and device.close.call_count == 2


@pytest.mark.parametrize("changed", [{"1": False}, {"2": 250}, {"4": "wind"}, {"5": "low"}])
def test_fan_test_cancels_if_any_proposal_condition_changed(changed):
    device = Mock()
    device.status.return_value = {"dps": {"1": True, "2": 240, "4": "cold", "5": "mid", **changed}}
    result = change_once(fan_record(), "synthetic", "fan", "mid", "low", approved=True,
                         journal=Mock(), factory=Mock(return_value=device))
    assert not result["write_attempted"]
    device._send_receive_quick.assert_not_called()


def test_uncertain_fan_send_stops_without_repetition_or_restoration():
    device = Mock()
    device.status.return_value = {"dps": {"1": True, "2": 240, "4": "cold", "5": "mid"}}
    device._send_receive_quick.return_value = None
    result = change_once(fan_record(), "synthetic", "fan", "mid", "low", approved=True,
                         journal=Mock(), factory=Mock(return_value=device))
    assert not result["state_confirmed"] and result["result"] == "communication_failed_stop_no_retry"
    assert device.status.call_count == 1
    device._send_receive_quick.assert_called_once()


def test_oem_test_evidence_is_distinct_from_official_dp_schema_and_limits_values():
    r = record()
    r["observed_fan_values"] = ["low", "mid", "high"]
    r["oem_fan_evidence"] = {"bidirectional_manual_verified": True, "model_code": "windspeed",
        "model_access": "rw", "model_type": "Enum", "model_range": ["low", "mid", "high"]}
    assert specification(r, "fan")["source"] == "oem_observed_not_standard_dp_documented"
    assert validate_value(r, "fan", "mid") == 5
    with pytest.raises(ValueError):
        validate_value(r, "fan", "high")
    r["oem_fan_evidence"]["bidirectional_manual_verified"] = False
    with pytest.raises(ValueError):
        validate_value(r, "fan", "mid")


def test_manual_evidence_requires_both_isolated_directions_no_writes_and_preserved_state():
    def event(fan, changes):
        return {"writes_sent": 0, "changes": changes,
                "snapshot": {"1": {"value": True}, "2": {"value": 240}, "4": {"value": "cold"}, "5": {"value": fan}}}
    session = {"device_id_masked": "exampl…0003", "events": [event("low", {}), event("mid", {"5": {}}), event("low", {"5": {}})]}
    assert verified_fan_observations([session])
    assert not verified_fan_observations([{**session, "events": session["events"][:2]}])
    session["events"][-1]["changes"]["2"] = {}
    assert not verified_fan_observations([session])


def test_oem_low_to_mid_still_requires_approval_and_sends_only_dp5(monkeypatch):
    monkeypatch.setattr("smart_tray.elgin_control.time.sleep", lambda _: None)
    r = record()
    r["observed_fan_values"] = ["low", "mid"]
    r["oem_fan_evidence"] = {"bidirectional_manual_verified": True, "model_code": "windspeed",
        "model_access": "rw", "model_type": "Enum", "model_range": ["low", "mid"]}
    device = Mock()
    factory = Mock(return_value=device)
    with pytest.raises(ValueError):
        change_once(r, "synthetic", "fan", "low", "mid", factory=factory, journal=Mock())
    factory.assert_not_called()
    device.status.side_effect = [{"dps": {"1": True, "2": 240, "4": "cold", "5": "low"}},
                                 {"dps": {"1": True, "2": 240, "4": "cold", "5": "mid"}}]
    device._send_receive_quick.return_value = True
    result = change_once(r, "synthetic", "fan", "low", "mid", approved=True, journal=Mock(), factory=factory)
    assert result["state_confirmed"]
    assert device.generate_payload.call_args.args[1] == {"5": "mid"}
    device._send_receive_quick.assert_called_once()
