"""Actual Qt mouse/selector/dialog tests; all device operations are mocked."""
import json
from pathlib import Path
import sys
import threading
from unittest.mock import Mock
from PySide6.QtCore import Qt, QEvent, QRect, QPoint
from PySide6.QtGui import QColor
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QMessageBox, QDialog, QDialogButtonBox
import pytest
from smart_tray.beta import BetaSettings, load_beta_adapters
from smart_tray.beta_controller import BetaController
from smart_tray.beta_ui import BetaPanel
from smart_tray.adapters import DeviceState
from smart_tray.ui_diagnostics import install_exception_hook, record
from test_interface import wait_until, finish

ROOT = Path(__file__).parent / "fixtures/config"


@pytest.fixture
def gui(qt_app, tmp_path):
    adapters = load_beta_adapters(ROOT)
    values = {"elgin": {"power": True, "temperature": 24, "ambient_temperature": 21, "mode": "cold", "fan": "low"},
              "led": {20: True, "mode": "colour", "colour": "000003e803e8", "brightness": 100},
              "novadigital": {1: True, 2: True}}
    for role, adapter in adapters.items():
        adapter.read = Mock(side_effect=lambda role=role: DeviceState("online", values[role].copy()))
        base = getattr(adapter, "base", adapter)
        base.store = Mock()
        base.store.load.side_effect = AssertionError("No real credentials in GUI tests")
        base.factory = Mock(side_effect=AssertionError("No real LAN in GUI tests"))
        def write(dp, before, value, role=role):
            values[role][dp] = value
            return DeviceState("online", values[role].copy())
        adapter.write = Mock(side_effect=write)
        if role in {"elgin", "led"}:
            def execute(name, state, value, *, experimental_approved, role=role):
                values[role][name] = value
                return DeviceState("online", values[role].copy())
            adapter.execute = Mock(side_effect=execute)
    settings = BetaSettings(tmp_path)
    settings.enabled = True
    controller = BetaController(adapters, settings)
    controller.start()
    wait_until(qt_app, lambda: not controller.busy)
    panel = BetaPanel(controller)
    panel.show()
    qt_app.processEvents()
    yield panel, controller, adapters
    finish(controller, panel)
    for adapter in adapters.values():
        base = getattr(adapter, "base", adapter)
        base.store.load.assert_not_called()
        base.factory.assert_not_called()


def click(widget):
    QTest.mouseClick(widget, Qt.MouseButton.LeftButton)


@pytest.mark.parametrize("role,dp", [("led", 20), ("novadigital", 1), ("novadigital", 2)])
def test_power_mouse_reaches_handler_once(gui, qt_app, role, dp):
    panel, controller, adapters = gui
    click(panel.buttons[(role, dp)])
    wait_until(qt_app, lambda: not controller.writing)
    adapters[role].write.assert_called_once_with(dp, True, False)
    assert controller.states[role].values[dp] is False


def test_advanced_is_visible_modeless_singleton_and_owner_hide_safe(gui, qt_app):
    panel, controller, adapters = gui
    button = next(b for b in panel.led.findChildren(__import__('PySide6.QtWidgets', fromlist=['QPushButton']).QPushButton) if b.text() == "Controles avançados")
    click(button)
    dialog = panel.dialogs["advanced_led"]
    assert dialog.isVisible() and not dialog.isModal() and panel.isEnabled()
    assert dialog.parentWidget() is None
    panel.hide()
    assert dialog.isVisible()
    panel.show_at_tray(QRect())
    assert panel.advanced("led") is dialog
    dialog.close()
    assert panel.isEnabled() and panel.isVisible()
    assert "advanced_led" not in panel.dialogs
    adapters["led"].execute.assert_not_called()


def test_confirmation_nonmodal_cancel_and_hidden_recovery(gui, qt_app):
    panel, controller, adapters = gui
    assert panel.request("elgin", "fan", "high") is False
    dialog = panel.dialogs["confirmation"]
    assert dialog.isVisible() and not dialog.isModal() and panel.isEnabled()
    dialog.hide()
    panel.show_at_tray(QRect())
    assert dialog.isVisible()
    click(dialog.button(QMessageBox.StandardButton.No))
    adapters["elgin"].execute.assert_not_called()
    assert panel.isEnabled() and "confirmation" not in panel.dialogs


def test_confirmed_experimental_mouse_dispatches_once(gui, qt_app):
    panel, controller, adapters = gui
    panel.request("elgin", "fan", "high")
    dialog = panel.dialogs["confirmation"]
    assert '{"5": "high"}' in dialog.text()
    click(dialog.button(QMessageBox.StandardButton.Yes))
    wait_until(qt_app, lambda: not controller.writing)
    adapters["elgin"].execute.assert_called_once()
    assert controller.states["elgin"].values["fan"] == "high"


def test_async_colour_picker_has_real_handler(gui, qt_app):
    panel, controller, adapters = gui
    click(panel.colour_button)
    picker = panel.dialogs["colour"]
    assert picker.isVisible() and not picker.isModal()
    picker.setCurrentColor(QColor(0, 0, 255))
    click(picker.findChild(QDialogButtonBox).button(QDialogButtonBox.StandardButton.Ok))
    assert '{"24": "00f003e803e8"}' in panel.dialogs["confirmation"].text()
    click(panel.dialogs["confirmation"].button(QMessageBox.StandardButton.Yes))
    wait_until(qt_app, lambda: not controller.writing)
    assert controller.states["led"].values["colour"] == "00f003e803e8"


def test_advanced_brightness_groove_click_debounces_and_cancel_is_safe(gui, qt_app):
    panel, controller, adapters = gui
    dialog = panel.advanced("led")
    slider = dialog.controls["brightness"]
    QTest.mouseClick(slider, Qt.MouseButton.LeftButton, pos=QPoint(10, slider.height() // 2))
    wait_until(qt_app, lambda: "confirmation" in panel.dialogs)
    adapters["led"].execute.assert_not_called()
    click(panel.dialogs["confirmation"].button(QMessageBox.StandardButton.No))
    QTest.qWait(500)
    assert "confirmation" not in panel.dialogs
    adapters["led"].execute.assert_not_called()


def test_selector_popup_does_not_hide_panel_or_rebuild_on_refresh(gui, qt_app):
    panel, controller, adapters = gui
    combo = panel.elgin.fan
    combo.showPopup()
    qt_app.processEvents()
    assert combo.view().isVisible()
    QApplication.sendEvent(panel, QEvent(QEvent.Type.WindowDeactivate))
    assert panel.isVisible()
    count = combo.count()
    controller.changed.emit()
    assert combo.view().isVisible() and combo.count() == count
    combo.hidePopup()


def test_settings_checkbox_mouse_and_no_automatic_writes(gui, qt_app):
    from PySide6.QtWidgets import QCheckBox
    panel, controller, adapters = gui
    dialog = panel.settings_dialog()
    checkbox = dialog.findChild(QCheckBox)
    QTest.mouseClick(checkbox, Qt.MouseButton.LeftButton, pos=QPoint(9, checkbox.height() // 2))
    assert controller.settings.enabled is False
    assert BetaSettings(controller.settings.directory).enabled is False
    assert not panel.colour_button.isEnabled()
    for role in ("elgin", "led"):
        adapters[role].execute.assert_not_called()
    dialog.close()
    assert panel.isVisible() and panel.isEnabled()


def test_slow_device_worker_cannot_block_other_device_or_gui(gui, qt_app):
    panel, controller, adapters = gui
    gate = threading.Event()
    entered = threading.Event()
    def slow_read():
        entered.set()
        gate.wait(2)
        return DeviceState("offline", {})
    adapters["elgin"].read = slow_read
    controller.refresh()
    wait_until(qt_app, lambda: entered.is_set() and "novadigital" not in controller.busy)
    assert "elgin" in controller.busy
    click(panel.buttons[("novadigital", 1)])
    wait_until(qt_app, lambda: not controller.writing)
    adapters["novadigital"].write.assert_called_once()
    assert "elgin" in controller.busy
    dialog = panel.advanced("led")
    assert dialog.isVisible() and panel.isEnabled()
    gate.set()
    wait_until(qt_app, lambda: not controller.busy)
    assert not panel.elgin.plus.isEnabled()


def test_worker_failure_leaves_gui_usable_and_clears_pending(gui, qt_app):
    panel, controller, adapters = gui
    adapters["novadigital"].write.side_effect = OSError("synthetic-secret-value")
    click(panel.buttons[("novadigital", 1)])
    wait_until(qt_app, lambda: not controller.writing)
    assert controller.states["novadigital"].connection == "unknown"
    assert "synthetic-secret" not in controller.states["novadigital"].message
    assert panel.settings_dialog().isVisible()
    assert panel.isEnabled()


def test_validated_mid_available_from_other_readable_speed_without_beta(gui, qt_app):
    panel, controller, adapters = gui
    controller.settings.enabled = False
    controller.states["elgin"] = DeviceState("online", {"power": True, "mode": "cold", "temperature": 24, "fan": "high"})
    controller.changed.emit()
    assert panel.elgin.fan.isEnabled()
    assert panel.request("elgin", "fan", "mid")
    wait_until(qt_app, lambda: not controller.writing)
    assert controller.states["elgin"].values["fan"] == "mid"
    assert "confirmation" not in panel.dialogs


def test_disabled_colour_explains_scene_and_beta_conditions(gui):
    panel, controller, _ = gui
    controller.settings.enabled = False
    controller.changed.emit()
    assert "Configurações" in panel.colour_button.toolTip()
    controller.settings.enabled = True
    controller.states["led"] = DeviceState("online", {20: True, "mode": "scene", "colour": "000003e803e8", "brightness": 100})
    controller.changed.emit()
    assert not panel.colour_button.isEnabled()
    assert "Colour" in panel.colour_button.toolTip() and "Cor fixa salva" in panel.colour_button.text()


def test_shutdown_closes_all_secondary_windows_without_writes(gui, qt_app):
    panel, controller, adapters = gui
    panel.advanced("led")
    panel.settings_dialog()
    panel.request("elgin", "fan", "high")
    controller.stop()
    assert not panel.dialogs
    adapters["elgin"].execute.assert_not_called()


def test_gui_exception_log_never_formats_sensitive_message(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    previous = sys.excepthook
    try:
        install_exception_hook()
        try:
            raise ValueError("synthetic-local-key-token-password")
        except ValueError:
            sys.excepthook(*sys.exc_info())
        record("unsafe", detail="password=abc")
    finally:
        sys.excepthook = previous
    content = (tmp_path / "SmartTray/ui-events.jsonl").read_text()
    assert "synthetic" not in content and "password" not in content
    entries = [json.loads(line) for line in content.splitlines()]
    assert entries[0]["error_type"] == "ValueError" and entries[0]["line"] > 0


def test_overlapping_quiet_workers_restore_streams_once():
    from smart_tray.diagnostic import quiet
    original = (sys.stdout, sys.stderr)
    first_entered, second_entered, release_first, release_second = (threading.Event() for _ in range(4))
    def first():
        with quiet():
            first_entered.set()
            release_first.wait(2)
    def second():
        first_entered.wait(2)
        with quiet():
            second_entered.set()
            release_second.wait(2)
    a, b = threading.Thread(target=first), threading.Thread(target=second)
    a.start(); b.start()
    assert second_entered.wait(2)
    release_first.set(); a.join(2)
    assert sys.stdout is not original[0] and not sys.stdout.closed
    release_second.set(); b.join(2)
    assert (sys.stdout, sys.stderr) == original
