from unittest.mock import Mock
import socket

import pytest
import tinytuya

from smart_tray.control_validation import verify_target, change_once, send_boolean_once, inspect_led, exclusive_write_lock


def test_write_lock_cleans_up_after_exception_on_windows(tmp_path):
    with pytest.raises(RuntimeError):
        with exclusive_write_lock(tmp_path):
            assert (tmp_path / "active.lock").exists()
            raise RuntimeError("synthetic")
    assert not (tmp_path / "active.lock").exists()


def test_competing_write_cannot_remove_existing_lock(tmp_path):
    with exclusive_write_lock(tmp_path):
        with pytest.raises(FileExistsError):
            with exclusive_write_lock(tmp_path):
                pytest.fail("Concurrent write admitted")
        assert (tmp_path / "active.lock").exists()


def target():
    return {"role": "led", "device_id": "example-led-0000000001", "ip": "10.77.0.39", "protocol_version": "3.3",
            "metadata": {"cloud_dps_candidates": [{"dp_id": 20, "code": "switch_led", "type": "Boolean", "source": "cloud_functions"}]}}


def test_approval_required_before_any_network_access():
    factory = Mock()
    with pytest.raises(ValueError, match="approval"):
        change_once(target(), "0" * 16, 20, True, False, factory=factory)
    factory.assert_not_called()


@pytest.mark.parametrize("dp", [21, 24, 26, 46, 47, 53, 1, 2])
def test_all_other_led_dps_writes_are_rejected(dp):
    with pytest.raises(ValueError):
        verify_target(target(), dp)


def test_elgin_writes_are_rejected():
    r = target()
    r.update(role="elgin", device_id="example-elgin-00000003", protocol_version="3.5")
    with pytest.raises(ValueError):
        verify_target(r, 20)


def test_channel_schema_is_checked_individually():
    r = target()
    r.update(role="novadigital", device_id="example-switch-000002", protocol_version="3.4")
    r["metadata"]["cloud_dps_candidates"] = [{"dp_id": 1, "code": "switch_1", "type": "Boolean", "source": "cloud_functions"}]
    verify_target(r, 1)
    with pytest.raises(ValueError):
        verify_target(r, 2)


def test_single_send_transport_never_replays_on_timeout():
    device = tinytuya.Device("synthetic", "10.77.0.39", "0" * 16, version=3.3)
    device._get_socket = Mock(return_value=True)
    device._encode_message = Mock(return_value=b"synthetic-frame")
    device.socket = Mock()
    transport = device.socket
    device.socket.sendall.side_effect = socket.timeout()
    with pytest.raises(RuntimeError, match="uncertain"):
        send_boolean_once(device, 20, False)
    device._encode_message.assert_called_once()
    # The quick path cleared device.socket on error; capture the original mock.
    assert device._get_socket.call_count == 1
    transport.sendall.assert_called_once_with(b"synthetic-frame")


def test_before_after_recorded_and_attempt_logged_before_send(monkeypatch):
    device = Mock()
    device.status.side_effect = [{"dps": {"20": True}}, {"dps": {"20": False}}]
    device._send_receive_quick.return_value = True
    events = []
    monkeypatch.setattr("smart_tray.control_validation.time.sleep", lambda seconds: events.append(("settle", seconds)))
    device._send_receive_quick.side_effect = lambda *a, **k: events.append("send") or True
    device.close.side_effect = lambda: events.append("close")
    result = change_once(target(), "0" * 16, 20, True, False, approved=True,
                         journal=lambda r: events.append("journal"), factory=Mock(return_value=device))
    assert events == ["journal", "send", "close", ("settle", 1), "close"]
    assert result["state_confirmed"] and result["after"]["20"]["value"] is False
    device._send_receive_quick.assert_called_once()
    assert device.status.call_count == 2
    assert device.close.call_count == 2


def test_uncertain_write_stops_without_postread_or_restoration():
    device = Mock()
    device.status.return_value = {"dps": {"20": True}}
    device._send_receive_quick.return_value = None
    result = change_once(target(), "0" * 16, 20, True, False, approved=True, factory=Mock(return_value=device))
    assert result["result"] == "communication_failed_stop_no_retry"
    assert device.status.call_count == 1
    device._send_receive_quick.assert_called_once()


def test_changed_initial_state_aborts_without_write():
    device = Mock()
    device.status.return_value = {"dps": {"20": False}}
    result = change_once(target(), "0" * 16, 20, True, False, approved=True, factory=Mock(return_value=device))
    assert result["result"] == "state_changed_since_proposal_no_write"
    device._send_receive_quick.assert_not_called()


def test_colour_format_analysis_does_not_export_arbitrary_data():
    result = inspect_led({"dps": {"21": "colour", "24": '{"token":"private"}'}}, "0" * 16)
    assert result["observed_mode"] == "colour"
    assert "private" not in str(result)
    result = inspect_led({"dps": {"24": '{"h":120,"s":1000,"v":500}'}}, "0" * 16)
    assert result["colour_format"]["encoding"] == "json_hsv"
    assert not result["colour_format"]["rgb_write_authorized"]
