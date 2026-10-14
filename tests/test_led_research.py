import json
from unittest.mock import Mock
import pytest
from smart_tray.led_research import (hsv16_decode, hsv16_encode, hsv_to_rgb, rgb_to_hsv16,
                                    capture_response, differences, Session, LedReader, collect_schema, clean_schema)
from test_adapters import setup_adapter


@pytest.mark.parametrize("rgb,hsv", [((255, 0, 0), (0, 1000, 1000)), ((0, 255, 0), (120, 1000, 1000)),
                                    ((0, 0, 255), (240, 1000, 1000)), ((255, 255, 255), (0, 0, 1000)),
                                    ((0, 0, 0), (0, 0, 0))])
def test_pure_colour_conversions(rgb, hsv):
    encoded = rgb_to_hsv16(*rgb)
    assert hsv16_decode(encoded) == dict(zip(("h", "s", "v"), hsv))
    assert hsv_to_rgb(hsv16_decode(encoded)) == list(rgb)


@pytest.mark.parametrize("raw", ["invalid", "0fff03e803e8", "0000040003e8", "000003e80400", "a" * 16])
def test_hsv_rejects_invalid_lengths_and_ranges(raw):
    with pytest.raises(ValueError):
        hsv16_decode(raw)


def test_boolean_is_not_a_colour_integer():
    with pytest.raises(ValueError):
        hsv16_encode(True, 1000, 1000)


def test_unknown_effect_payload_compared_but_never_exported(tmp_path):
    key = b"synthetic-session-fingerprint"
    before = capture_response({"dps": {"20": True, "51": "opaque-effect-A"}}, (), key)
    after = capture_response({"dps": {"20": True, "51": "opaque-effect-B"}}, (), key)
    session = Session(tmp_path)
    session.record(before, "baseline")
    event = session.record(after, "effect")
    assert set(event["changes"]) == {"51"}
    text = session.path.read_text(encoding="utf-8")
    assert "opaque-effect-A" not in text and "opaque-effect-B" not in text
    assert "fingerprint" not in text and event["writes_sent"] == 0


def test_sensitive_values_not_even_recorded_as_shapes():
    value = "secret-credential"
    capture = capture_response({"dps": {"90": "prefix-" + value, "20": True}}, (value,), b"test")
    assert "90" not in capture.values and "90" not in capture.fingerprints
    assert value not in repr(capture)


def test_colour_and_brightness_diff_are_decoded_without_unknown_dp_assumptions():
    before = capture_response({"dps": {"24": "000003e803e8", "46": 1000}}, (), b"test")
    after = capture_response({"dps": {"24": "000003e801f4", "46": 1000}}, (), b"test")
    diff = differences(before, after)
    assert set(diff) == {"24"}
    assert diff["24"]["after"]["hsv"]["v"] == 500
    assert not diff["24"]["after"]["physical_mapping_confirmed"]
    assert "22" not in after.values and "23" not in after.values


def test_manual_categories_and_baseline_are_required(tmp_path):
    session = Session(tmp_path)
    capture = capture_response({"dps": {"20": True}}, (), b"test")
    with pytest.raises(ValueError):
        session.record(capture, "effect")
    with pytest.raises(ValueError):
        session.record(capture, "password=do-not-export")


def test_reader_uses_status_only_and_only_for_led(tmp_path):
    adapter, device, store = setup_adapter(tmp_path)
    device.status.return_value = {"dps": {"20": True, "24": "000003e803e8"}}
    reader = LedReader(adapter.record, store=store, factory=adapter.factory)
    assert reader.capture().values["20"]["value"] is True
    device._send_receive_quick.assert_not_called()
    device.generate_payload.assert_not_called()
    device.close.assert_called_once()
    adapter.record["role"] = "novadigital"
    with pytest.raises(ValueError):
        LedReader(adapter.record, store=store, factory=adapter.factory)


def test_schema_collector_is_get_only_exact_device_and_isolates_denial():
    cloud = Mock()
    cloud._tuyaplatform.side_effect = [{"success": False, "msg": "private-token"},
                                    {"success": True, "result": {}}, {"success": True, "result": {}}]
    schema = collect_schema(cloud)
    assert len(schema["queries"]) == 3 and "private-token" not in str(schema)
    for call in cloud._tuyaplatform.call_args_list:
        assert call.kwargs["action"] == "GET"
        assert "example-led-0000000001" in call.args[0]
    assert "cloud/thing/" in cloud._tuyaplatform.call_args_list[-1].args[0]


def test_model_ability_id_not_silently_promoted_to_lan_dp():
    response = {"success": True, "result": {"model": json.dumps({"services": [{"properties": [
        {"abilityId": 53, "code": "lightpixel_number_set", "accessMode": "rw", "typeSpec": {"type": "value", "min": 1, "max": 1000}},
        {"abilityId": 52, "code": "secret-token", "typeSpec": {"type": "string", "typeDefaultValue": "sensitive"}}
    ]}]})}}
    result = clean_schema(response, "model", ("secret-token",))
    assert result["entries"][0]["dp_id"] is None and result["entries"][0]["ability_id"] == 53
    assert not result["entries"][0]["lan_mapping_confirmed"]
    assert "sensitive" not in str(result)


def test_enum_embedded_token_is_redacted():
    response = {"success": True, "result": {"functions": [{"dp_id": 21, "code": "work_mode", "type": "Enum",
        "values": '{"range":["colour","prefixTOKEN"]}'}]}}
    result = clean_schema(response, "spec", ("TOKEN",))
    assert "TOKEN" not in str(result)
