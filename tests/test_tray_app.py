from unittest.mock import Mock
from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QSystemTrayIcon
from smart_tray.app import TrayApplication
from test_interface import fixtures, finish


def setup_tray(qt_app, tmp_path, monkeypatch):
    startup = Mock()
    startup.enabled.return_value = False
    monkeypatch.setattr("smart_tray.app.Startup", lambda: startup)
    _, controller, panel = fixtures()
    panel.deleteLater()
    class Instance:
        class Signals(QObject):
            activated = Signal()
        def __init__(self):
            self.signals = self.Signals()
            self.activated = self.signals.activated
            self.release = Mock()
    instance = Instance()
    tray_app = TrayApplication(qt_app, tmp_path, controller, instance)
    return tray_app, startup


def cleanup(tray_app):
    tray_app.tray.hide()
    finish(tray_app.controller, tray_app.panel)
    tray_app.menu.deleteLater()
    tray_app.tray.deleteLater()


def test_tray_left_click_always_shows_existing_window_and_context_does_not(qt_app, tmp_path, monkeypatch):
    tray_app, startup = setup_tray(qt_app, tmp_path, monkeypatch)
    tray_app.activate(QSystemTrayIcon.ActivationReason.Context)
    assert not tray_app.panel.isVisible()
    tray_app.activate(QSystemTrayIcon.ActivationReason.Trigger)
    assert tray_app.panel.isVisible()
    tray_app.activate(QSystemTrayIcon.ActivationReason.Trigger)
    assert tray_app.panel.isVisible()
    startup.set_enabled.assert_not_called()
    cleanup(tray_app)


def test_startup_changes_only_after_explicit_menu_action(qt_app, tmp_path, monkeypatch):
    tray_app, startup = setup_tray(qt_app, tmp_path, monkeypatch)
    assert not tray_app.startup_action.isChecked()
    startup.set_enabled.assert_not_called()
    tray_app.startup_action.trigger()
    startup.set_enabled.assert_called_once_with(True, tmp_path)
    cleanup(tray_app)


def test_second_instance_activation_shows_existing_panel(qt_app, tmp_path, monkeypatch):
    tray_app, _ = setup_tray(qt_app, tmp_path, monkeypatch)
    tray_app.instance.activated.emit()
    assert tray_app.panel.isVisible()
    cleanup(tray_app)


def test_exit_stops_polling_without_device_commands(qt_app, tmp_path, monkeypatch):
    tray_app, _ = setup_tray(qt_app, tmp_path, monkeypatch)
    tray_app.quit()
    assert tray_app.controller.stopping and not tray_app.controller.timer.isActive()
    assert not tray_app.menu.isEnabled()
    assert not tray_app.panel.isVisible()
    tray_app.exit_timer.stop()  # Do not quit the shared test QApplication.
    assert not tray_app.controller.toggle("led", 20)
    cleanup(tray_app)
