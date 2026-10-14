import json
from unittest.mock import Mock
import pytest
from smart_tray.elgin_observation import observation, ElginObserver, CATEGORY_NAMES
from smart_tray.elgin_research import ELGIN_ID
from smart_tray.led_research import Session, differences, collect_schema, clean_schema
from test_elgin_control import record


def test_elgin_manual_mode_and_unknown_fan_changes_detected_without_raw_strings(tmp_path):
    r = record()
    before = observation({"dps": {"1": True, "4": "cold", "5": "unknown-payload-low"}}, r, "synthetic-key", b"ephemeral")
    after = observation({"dps": {"1": True, "4": "wind", "5": "unknown-payload-mid"}}, r, "synthetic-key", b"ephemeral")
    changes = differences(before, after)
    assert set(changes) == {"4", "5"} and changes["4"]["after"]["value"] == "wind"
    assert "unknown" not in json.dumps(changes)
    session = Session(tmp_path, ELGIN_ID, {"baseline", *(code for _, code in CATEGORY_NAMES)})
    session.record(before, "baseline")
    session.record(after, "fan")
    exported = session.path.read_text(encoding="utf-8")
    assert "exampl" in exported and "unknown-low" not in exported and "synthetic-key" not in exported
    assert all(e["writes_sent"] == 0 for e in session.events)


def test_credentials_and_wrong_device_schema_never_exported():
    r = record()
    capture = observation({"dps": {"122": "prefixsynthetic-keysuffix", "4": "synthetic-key"}}, r, "synthetic-key", b"ephemeral")
    assert not capture.values and not capture.fingerprints
    reader = ElginObserver(r, Mock(), Mock())
    with pytest.raises(ValueError):
        reader.set_schema({"device_id_masked": "exampl…0001"})


def test_observer_status_only_never_saves_credential_or_generates_payload():
    store, device = Mock(), Mock()
    store.load.return_value = "synthetic-key"
    device.status.return_value = {"dps": {"1": True, "4": "cold"}}
    reader = ElginObserver(record(), store, Mock(return_value=device))
    assert reader.capture().values["4"]["value"] == "cold"
    device.generate_payload.assert_not_called()
    device._send_receive_quick.assert_not_called()
    device.close.assert_called_once()
    store.save.assert_not_called()


def test_elgin_schema_queries_are_get_only_no_peer_ids():
    cloud = Mock()
    cloud._tuyaplatform.return_value = {"success": True, "result": {}}
    schema = collect_schema(cloud, device_id=ELGIN_ID)
    assert schema["device_id_masked"] == "exampl…0003"
    for call in cloud._tuyaplatform.call_args_list:
        assert ELGIN_ID in call.args[0] and call.kwargs["action"] == "GET"
    assert len(cloud._tuyaplatform.call_args_list) == 3


def test_write_only_model_access_not_promoted_to_observed_dp():
    result = clean_schema({"success": True, "result": {"model": {"services": [{"properties": [
        {"abilityId": 5, "code": "fan_speed_enum", "accessMode": "wr", "typeSpec": {"type": "enum", "range": ["low", "high"]}}
    ]}]}}}, "model")
    assert result["entries"][0]["access"] == "wr"
    assert result["entries"][0]["dp_id"] is None
    reader = ElginObserver(record(), Mock(), Mock())
    schema = {"device_id_masked": "exampl…0003", "queries": [result]}
    reader.set_schema(schema)
    state = observation({"dps": {"5": "high"}}, record(), "synthetic-key", b"ephemeral", schema)
    assert state.values["5"]["schema_codes"] == [] and state.values["5"]["schema_enum_confirmed"] is False


def test_observed_fan_literal_does_not_become_write_enum_or_confirmed_function():
    state = observation({"dps": {"5": "low", "19": "c"}}, record(), "synthetic-key", b"test")
    assert state.values["5"]["value"] == "low"
    assert state.values["5"]["schema_codes"] == []
    assert state.values["5"]["write_validated"] is False and not state.values["5"]["schema_enum_confirmed"]
    assert observation({"dps": {"5": "low"}}, record(), "low", b"test").values == {}


@pytest.mark.parametrize("value", ["x7", "medium_2", "vendor-A"])
def test_fan_setting_exact_values_not_limited_to_standard_names(value):
    state = observation({"dps": {"5": value, "122": value}}, record(), "synthetic-key", b"test")
    assert state.values["5"]["value"] == value
    assert not state.values["5"]["write_validated"]
    assert "value" not in state.values["122"]


def test_fan_secret_token_and_arbitrary_payload_never_exported():
    for secret in ("1234567890abcdef", "a" * 32, "shortTOKEN"):
        state = observation({"dps": {"5": secret}}, record(), "synthetic-key", b"test", sensitive=(secret,))
        assert state.values == {}
    for payload in ("a" * 32, "1234567890abcdef", '{"token":"secret"}', "line\ntext"):
        state = observation({"dps": {"5": payload}}, record(), "synthetic-key", b"test")
        assert "value" not in state.values["5"]
