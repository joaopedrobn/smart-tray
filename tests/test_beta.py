import json
from pathlib import Path
from unittest.mock import Mock
import pytest
from PySide6.QtWidgets import QMessageBox
from smart_tray.adapters import DeviceState, load_adapters
from smart_tray.beta import BetaAdapter, BetaSettings, VERSION, load_beta_adapters
from smart_tray.beta_controller import BetaController
from smart_tray.beta_ui import BetaPanel
from smart_tray.led_research import hsv16_decode, hsv16_encode, hsv_to_rgb, rgb_to_hsv16
from test_interface import wait_until, finish

ROOT = Path(__file__).parent / "fixtures/config"


def make_adapter(role, tmp_path):
    adapter = load_beta_adapters(ROOT)[role]
    assert isinstance(adapter, BetaAdapter)
    device = Mock()
    device._send_receive_quick.return_value = True
    adapter.base.factory = Mock(return_value=device)
    adapter.base.store = Mock()
    adapter.base.store.load.return_value = "synthetic-secret-123456789"
    adapter.base.journal_dir = tmp_path / "operations"
    return adapter, device


def elgin_raw(**changes):
    return {"dps": {"1": True, "2": 240, "3": 210, "4": "cold", "5": "mid", "8": False,
                    "13": True, "102": False, **changes}}


def led_raw(**changes):
    return {"dps": {"20": True, "21": "colour", "24": "000003e803e8", "46": 1000, **changes}}


@pytest.mark.parametrize("role,expected", [("elgin", {"power", "mode", "fan", "sleep", "display", "eco", "temperature"}),
                                           ("led", {"mode", "colour", "brightness"})])
def test_own_device_capabilities_are_bounded(role, expected, tmp_path):
    adapter, _ = make_adapter(role, tmp_path)
    assert set(adapter.capabilities) == expected
    assert "swing" not in adapter.capabilities and "ionizer" not in adapter.capabilities
    assert not adapter.is_validated("mode", "auto")


@pytest.mark.parametrize("name,value", [("fan", "silent"), ("fan", "turbo"), ("fan", "mid_low"),
    ("mode", "hot"), ("power", 1), ("swing", True), ("ionizer", True), ("temperature", 32.5)])
def test_no_invented_values_or_unknown_dps(name, value, tmp_path):
    adapter, device = make_adapter("elgin", tmp_path)
    with pytest.raises(ValueError):
        adapter.execute(name, DeviceState("online", {}), value, experimental_approved=True)
    device._send_receive_quick.assert_not_called()
    adapter.base.store.load.assert_not_called()


@pytest.mark.parametrize("name,value", [("power", False), ("mode", "wind"), ("fan", "low"), ("sleep", True)])
def test_experimental_approval_required_before_network(name, value, tmp_path):
    adapter, device = make_adapter("elgin", tmp_path)
    with pytest.raises(ValueError):
        adapter.execute(name, DeviceState("online", {}), value)
    device.status.assert_not_called()


@pytest.mark.parametrize("name,value,dp", [("power", False, "1"), ("mode", "wind", "4"), ("fan", "low", "5"),
                                         ("sleep", True, "102"), ("display", False, "13"), ("eco", True, "8")])
def test_each_click_writes_exactly_one_dp_then_reads(name, value, dp, tmp_path, monkeypatch):
    monkeypatch.setattr("smart_tray.beta.time.sleep", lambda _: None)
    adapter, device = make_adapter("elgin", tmp_path)
    before, after = elgin_raw(), elgin_raw(**{dp: value})
    device.status.side_effect = [before, after]
    state = adapter._state(before, "synthetic-secret-123456789")
    result = adapter.execute(name, state, value, experimental_approved=True)
    assert result.connection == "online" and result.values[name] == value
    assert device.generate_payload.call_args.args[1] == {dp: value}
    device._send_receive_quick.assert_called_once()
    assert device.status.call_count == 2
    assert adapter.base.factory.call_count == 2  # Fresh connection after write.
    adapter.base.store.save.assert_not_called()
    data = next((tmp_path / "operations").glob("*.json")).read_text(encoding="utf-8")
    assert "synthetic-secret" not in data
    journal = json.loads(data)
    assert journal["lan_confirmed"] is True and journal["physical_confirmation"] == "pending"
    assert journal["classification"] == "experimental"


def test_read_only_exposes_only_approved_types_and_codes(tmp_path):
    adapter, device = make_adapter("elgin", tmp_path)
    device.status.return_value = elgin_raw(**{"130": "synthetic-secret-123456789", "5": "not-an-enum"})
    state = adapter.read()
    assert state.values["ambient_temperature"] == 21
    assert "fan" not in state.values and "130" not in state.values
    assert "synthetic-secret" not in repr(state)
    device._send_receive_quick.assert_not_called()


@pytest.mark.parametrize("fault", ["before", "send", "after", "mismatch"])
def test_failure_does_not_retry_or_restore(fault, tmp_path, monkeypatch):
    monkeypatch.setattr("smart_tray.beta.time.sleep", lambda _: None)
    adapter, device = make_adapter("elgin", tmp_path)
    state = adapter._state(elgin_raw(), "synthetic-secret-123456789")
    device.status.side_effect = [OSError("synthetic-secret") if fault == "before" else elgin_raw(),
        OSError("synthetic-secret") if fault == "after" else elgin_raw(**{"5": "mid" if fault == "mismatch" else "low"})]
    if fault == "send":
        device._send_receive_quick.return_value = None
    result = adapter.execute("fan", state, "low", experimental_approved=True)
    assert result.connection == "unknown" and not result.values
    assert device._send_receive_quick.call_count == (0 if fault == "before" else 1)
    assert "synthetic-secret" not in repr(result)


def test_stale_ui_state_blocks_write(tmp_path):
    adapter, device = make_adapter("elgin", tmp_path)
    state = adapter._state(elgin_raw(), "synthetic-secret-123456789")
    device.status.return_value = elgin_raw(**{"5": "high"})
    assert adapter.execute("fan", state, "low", experimental_approved=True).connection == "unknown"
    device._send_receive_quick.assert_not_called()


def test_colour_and_brightness_use_only_dp24_and_preserve_hue(tmp_path, monkeypatch):
    monkeypatch.setattr("smart_tray.beta.time.sleep", lambda _: None)
    adapter, device = make_adapter("led", tmp_path)
    raw = hsv16_encode(120, 800, 1000)
    target = hsv16_encode(120, 800, 500)
    before, after = led_raw(**{"24": raw}), led_raw(**{"24": target})
    device.status.side_effect = [before, after]
    state = adapter._state(before, "synthetic-secret-123456789")
    result = adapter.execute("brightness", state, 50, experimental_approved=True)
    assert device.generate_payload.call_args.args[1] == {"24": target}
    assert result.values["brightness"] == 50
    assert set(device.generate_payload.call_args.args[1]) == {"24"}


def test_colour_never_implicitly_changes_mode(tmp_path):
    adapter, device = make_adapter("led", tmp_path)
    device.status.return_value = led_raw(**{"21": "scene"})
    state = adapter.read()
    result = adapter.execute("colour", state, rgb_to_hsv16(0, 0, 255), experimental_approved=True)
    assert result.connection == "unknown"
    device._send_receive_quick.assert_not_called()


@pytest.mark.parametrize("rgb", [(255, 0, 0), (0, 255, 0), (0, 0, 255), (0, 0, 0), (255, 255, 255), (33, 78, 194)])
def test_rgb_hsv_roundtrip(rgb):
    recovered = hsv_to_rgb(hsv16_decode(rgb_to_hsv16(*rgb)))
    assert all(abs(a - b) <= 1 for a, b in zip(rgb, recovered))


def test_settings_roundtrip_without_credentials(tmp_path):
    settings = BetaSettings(tmp_path)
    assert not settings.enabled
    settings.enabled = True
    settings.favorites = ["000003e803e8"]
    settings.save()
    loaded = BetaSettings(tmp_path)
    assert loaded.enabled and loaded.favorites == settings.favorites
    assert set(json.loads(settings.path.read_text())) == {"experimental_enabled", "favorites", "last_colour"}


def test_corrupt_settings_fail_closed(tmp_path):
    (tmp_path / "beta-settings.json").write_text("bad json")
    assert BetaSettings(tmp_path).enabled is False


def test_beta_ui_startup_has_no_writes_and_first_use_requires_confirmation(qt_app, tmp_path, monkeypatch):
    adapters = load_beta_adapters(ROOT)
    for role, raw in (("elgin", elgin_raw()), ("led", led_raw())):
        adapter = adapters[role]
        adapter.read = Mock(return_value=adapter._state(raw, "synthetic-secret-123456789"))
        adapter.execute = Mock(return_value=adapter.read.return_value)
    adapters["novadigital"].read = Mock(return_value=DeviceState("online", {1: True, 2: True}))
    settings = BetaSettings(tmp_path)
    controller = BetaController(adapters, settings)
    panel = BetaPanel(controller)
    controller.start()
    wait_until(qt_app, lambda: not controller.busy)
    assert panel.elgin.temperature.text() == "24"
    assert not panel.elgin.power.isEnabled() and panel.elgin.plus.isEnabled()
    assert panel.colour_button.isEnabled() is False
    for role in ("elgin", "led"):
        adapters[role].execute.assert_not_called()
    assert controller.request_beta("elgin", "fan", "low", approved=True) is False
    settings.enabled = True
    controller.changed.emit()
    assert panel.elgin.power.isEnabled() and panel.colour_button.isEnabled()
    assert panel.request("elgin", "fan", "low") is False
    adapters["elgin"].execute.assert_not_called()
    question = panel.dialogs["confirmation"]
    assert question.isVisible() and '{"5": "low"}' in question.text()
    question.button(QMessageBox.StandardButton.No).click()
    adapters["elgin"].execute.assert_not_called()
    assert panel.request("elgin", "fan", "low") is False
    panel.dialogs["confirmation"].button(QMessageBox.StandardButton.Yes).click()
    wait_until(qt_app, lambda: not controller.busy)
    adapters["elgin"].execute.assert_called_once()
    assert adapters["elgin"].execute.call_args.kwargs["experimental_approved"] is True
    finish(controller, panel)


def test_beta_controller_rejects_unapproved_explicit_call(qt_app, tmp_path):
    adapters = load_beta_adapters(ROOT)
    settings = BetaSettings(tmp_path)
    settings.enabled = True
    controller = BetaController(adapters, settings)
    controller.states["elgin"] = DeviceState("online", {"power": True, "fan": "mid", "mode": "cold", "temperature": 24})
    assert controller.request_beta("elgin", "fan", "low") is False
    assert not controller.busy
    controller.stop()


def test_missing_schema_preserves_validated_adapters(tmp_path):
    # Missing research files must not fabricate experimental capabilities.
    adapters = load_beta_adapters(tmp_path)
    assert not getattr(adapters["elgin"], "capabilities", {})


def test_physical_confirmation_does_not_promote_profile(qt_app, tmp_path, monkeypatch):
    adapters = load_beta_adapters(ROOT)
    controller = BetaController(adapters, BetaSettings(tmp_path))
    panel = BetaPanel(controller)
    path = tmp_path / "result.json"
    item = {"lan_confirmed": True, "classification": "experimental", "command": {"5": "low"}, "physical_confirmation": "pending"}
    before = json.dumps(adapters["elgin"].profile, sort_keys=True)
    panel.action_finished("elgin", (path, item))
    panel.dialogs["confirmation"].button(QMessageBox.StandardButton.Yes).click()
    assert json.loads(path.read_text())["physical_confirmation"] == "confirmed_by_user"
    assert json.dumps(adapters["elgin"].profile, sort_keys=True) == before
    finish(controller, panel)


@pytest.mark.parametrize("data", [None, [], {"favorites": None}, {"favorites": ["invalid", "000003e803e8"]}])
def test_malformed_preference_values_do_not_crash(data, tmp_path):
    (tmp_path / "beta-settings.json").write_text(json.dumps(data))
    settings = BetaSettings(tmp_path)
    assert settings.enabled is False
    assert all(len(v) == 12 for v in settings.favorites)


def test_fan_temperature_changed_since_ui_blocks_write(tmp_path):
    adapter, device = make_adapter("elgin", tmp_path)
    state = adapter._state(elgin_raw(), "synthetic-secret-123456789")
    device.status.return_value = elgin_raw(**{"2": 250})
    adapter.execute("fan", state, "low", experimental_approved=True)
    device._send_receive_quick.assert_not_called()


def test_frozen_startup_points_to_executable(tmp_path, monkeypatch):
    from smart_tray.windows import startup_command
    import sys
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(tmp_path / "Folder With Spaces/SmartTrayBeta.exe"))
    command = startup_command(tmp_path)
    assert command.endswith('SmartTrayBeta.exe" --background')
    assert "python" not in command


def test_last_colour_is_persisted_and_invalid_payload_discarded(tmp_path):
    settings = BetaSettings(tmp_path)
    settings.last_colour = "000003e803e8"
    settings.save()
    assert BetaSettings(tmp_path).last_colour == settings.last_colour
    (tmp_path / "beta-settings.json").write_text(json.dumps({"last_colour": "secret-token"}))
    assert BetaSettings(tmp_path).last_colour is None


def test_advanced_controls_sync_without_any_write(qt_app, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QDialog, QPushButton
    adapters = load_beta_adapters(ROOT)
    controller = BetaController(adapters, BetaSettings(tmp_path))
    controller.settings.enabled = True
    controller.states["elgin"] = adapters["elgin"]._state(elgin_raw(), "synthetic-secret-123456789")
    adapters["elgin"].execute = Mock()
    panel = BetaPanel(controller)
    dialog = panel.advanced("elgin")
    buttons = dialog.findChildren(QPushButton)
    unmapped = [b for b in buttons if "não mapead" in b.text() or "Fungusproof" in b.text()]
    assert len(unmapped) == 3 and all(not b.isEnabled() for b in unmapped)
    assert any("desligar (Beta)" in b.text() and b.isEnabled() for b in buttons)
    assert dialog.isVisible() and not dialog.isModal()
    adapters["elgin"].execute.assert_not_called()
    finish(controller, panel)
