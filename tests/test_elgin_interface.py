from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from smart_tray.adapters import DeviceState
from test_interface import fixtures, wait_until, finish


class TemperatureAdapter:
    channels = {}
    capabilities = {"temperature": {"validated": True, "kind": "number", "min": 16, "max": 32, "step": 1,
                                    "requires": {"power": True, "mode": "cold"}}}
    def __init__(self):
        self.values = {"temperature": 24, "ambient_temperature": 21, "power": True, "mode": "cold"}
        self.commands = []
    def read(self):
        return DeviceState("online", self.values.copy(), "Sincronizado")
    def command_from_state(self, name, expected, value):
        self.commands.append((name, expected, value))
        self.values[name] = value
        return self.read()


def test_setpoint_controls_click_only_no_startup_write_and_other_controls_disabled(qt_app):
    adapters, controller, panel = fixtures()
    adapters["elgin"] = TemperatureAdapter()
    controller.start()
    wait_until(qt_app, lambda: not controller.busy)
    assert not adapters["elgin"].commands
    assert panel.elgin.temperature.text() == "24"
    assert "21" in panel.elgin.temperature_hint.text()
    assert panel.elgin.layout.indexOf(panel.elgin.temperature_hint) >= 0
    assert not panel.elgin.temperature_hint.isHidden()
    assert panel.elgin.plus.isEnabled() and panel.elgin.minus.isEnabled()
    assert not any(w.isEnabled() for w in (panel.elgin.power, panel.elgin.mode, panel.elgin.fan, panel.elgin.swing))
    assert "Frio" in panel.elgin.mode.currentText()
    QTest.mouseClick(panel.elgin.plus, Qt.MouseButton.LeftButton)
    assert not controller.request_elgin("temperature", 26)
    wait_until(qt_app, lambda: not controller.busy)
    assert adapters["elgin"].commands == [("temperature", 24, 25)]
    assert panel.elgin.temperature.text() == "25"
    assert not adapters["led"].writes and not adapters["novadigital"].writes
    finish(controller, panel)


def test_offline_wrong_mode_and_step_disable_setpoint_without_simulating_state(qt_app):
    adapters, controller, panel = fixtures()
    adapters["elgin"] = TemperatureAdapter()
    controller.refresh()
    wait_until(qt_app, lambda: not controller.busy)
    assert not controller.request_elgin("temperature", 24.5)
    for values in ({"temperature": 24, "power": False, "mode": "cold"},
                   {"temperature": 24, "power": True, "mode": "wind"}):
        controller.states["elgin"] = DeviceState("online", values)
        controller.changed.emit()
        assert not panel.elgin.plus.isEnabled() and not controller.request_elgin("temperature", 25)
    controller.states["elgin"] = DeviceState("offline", {})
    controller.changed.emit()
    assert panel.elgin.temperature.text() == "—" and not panel.elgin.minus.isEnabled()
    assert "LAN" in panel.elgin.badge.text()
    assert not adapters["elgin"].commands
    finish(controller, panel)
