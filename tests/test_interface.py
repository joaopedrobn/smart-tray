import threading
import time
from PySide6.QtCore import QRect, QPoint, QEvent, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from smart_tray.adapters import DeviceState, ElginAdapter
from smart_tray.controller import Controller
from smart_tray.ui import Panel, panel_position


class FakeAdapter:
    def __init__(self, channels, values):
        self.channels, self.values = channels, values.copy()
        self.reads, self.writes = 0, []
        self.failure = False

    def read(self):
        self.reads += 1
        return DeviceState("offline", {}, "Sem resposta") if self.failure else DeviceState("online", self.values.copy(), "Estado atualizado")

    def write(self, dp, before, value):
        self.writes.append((dp, before, value))
        self.values[dp] = value
        return DeviceState("online", self.values.copy(), "Estado atualizado")


def fixtures():
    adapters = {"elgin": ElginAdapter(), "led": FakeAdapter({20: "switch_led"}, {20: True}),
                "novadigital": FakeAdapter({1: "switch_1", 2: "switch_2"}, {1: True, 2: True})}
    controller = Controller(adapters)
    return adapters, controller, Panel(controller)


def wait_until(app, predicate, timeout=3):
    deadline = time.monotonic() + timeout
    while not predicate() and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.005)
    app.processEvents()
    assert predicate()


def finish(controller, panel):
    controller.stop()
    controller.pool.waitForDone(3000)
    panel.hide()
    panel.deleteLater()


def test_startup_reads_only_and_elgin_does_not_simulate_state(qt_app):
    adapters, controller, panel = fixtures()
    assert panel.elgin.temperature.text() == "—"
    for control in (panel.elgin.power, panel.elgin.minus, panel.elgin.plus, panel.elgin.mode, panel.elgin.fan, panel.elgin.swing):
        assert not control.isEnabled()
    assert not any(b.isEnabled() for b in panel.buttons.values())
    controller.start()
    wait_until(qt_app, lambda: not controller.busy)
    assert adapters["led"].reads == 1 and adapters["novadigital"].reads == 1
    assert adapters["led"].writes == adapters["novadigital"].writes == []
    assert all(b.isEnabled() for b in panel.buttons.values())
    assert not controller.request_elgin("power", True)
    finish(controller, panel)


def test_click_sends_one_command_only_to_selected_channel(qt_app):
    adapters, controller, panel = fixtures()
    controller.refresh()
    wait_until(qt_app, lambda: not controller.busy)
    QTest.mouseClick(panel.buttons[("novadigital", 2)], Qt.MouseButton.LeftButton)
    wait_until(qt_app, lambda: not controller.busy)
    assert adapters["novadigital"].writes == [(2, True, False)]
    assert adapters["led"].writes == []
    assert controller.states["novadigital"].values == {1: True, 2: False}
    assert panel.buttons[("novadigital", 2)].text() == "Desligado"
    finish(controller, panel)


def test_offline_then_read_only_reconnect_and_unknown(qt_app):
    adapters, controller, panel = fixtures()
    adapters["led"].failure = True
    controller.refresh()
    wait_until(qt_app, lambda: not controller.busy)
    assert not panel.buttons[("led", 20)].isEnabled()
    assert panel.buttons[("led", 20)].text() == "—"
    assert not controller.toggle("led", 20)
    adapters["led"].failure = False
    controller.refresh()
    wait_until(qt_app, lambda: not controller.busy)
    assert panel.buttons[("led", 20)].isEnabled()
    assert adapters["led"].writes == []
    controller.states["led"] = DeviceState("unknown", {}, "Resultado incerto")
    controller.changed.emit()
    assert not panel.buttons[("led", 20)].isEnabled()
    assert panel.buttons[("led", 20)].text() == "—"
    finish(controller, panel)


def test_network_worker_does_not_block_gui_and_rejects_double_click(qt_app):
    adapters, controller, panel = fixtures()
    controller.refresh()
    wait_until(qt_app, lambda: not controller.busy)
    gate = threading.Event()
    entered = threading.Event()
    original = adapters["led"].write
    def delayed(*args):
        entered.set()
        gate.wait(2)
        return original(*args)
    adapters["led"].write = delayed
    assert controller.toggle("led", 20)
    assert not controller.toggle("led", 20)
    assert not controller.toggle("novadigital", 1)
    wait_until(qt_app, entered.is_set)
    assert controller.busy and not panel.buttons[("led", 20)].isEnabled()
    assert panel.buttons[("led", 20)].text() == "Aguarde…"
    gate.set()
    wait_until(qt_app, lambda: not controller.busy)
    assert len(adapters["led"].writes) == 1
    finish(controller, panel)


def test_close_and_outside_deactivation_hide_instead_of_quit(qt_app):
    _, controller, panel = fixtures()
    panel.show()
    panel.close()
    assert not panel.isVisible()
    panel.show()
    QApplication.sendEvent(panel, QEvent(QEvent.Type.WindowDeactivate))
    assert not panel.isVisible()
    assert not controller.stopping
    finish(controller, panel)


def test_panel_is_clamped_on_negative_coordinate_monitor_and_small_screen():
    for available, anchor in [(QRect(-1920, 0, 1920, 1040), QPoint(-30, 1050)),
                              (QRect(0, 0, 800, 500), QPoint(799, 499)),
                              (QRect(1920, -1080, 1280, 1020), QPoint(1900, -1090))]:
        result = panel_position(available, anchor, 420, 800)
        assert available.contains(result)
        assert result.width() <= 420 and result.height() <= 800


def test_future_elgin_capability_binds_without_rewriting_panel(qt_app):
    adapters, controller, panel = fixtures()
    adapters["elgin"].capabilities = {"power": {"validated": True, "kind": "boolean"},
        "temperature": {"validated": True, "kind": "number", "min": 16, "max": 30, "step": 1},
        "mode": {"validated": True, "kind": "choice", "options": {"cool": "Resfriar"}}}
    controller.states["elgin"] = DeviceState("online", {"power": True, "temperature": 24, "mode": "cool"})
    controller.changed.emit()
    assert panel.elgin.power.isEnabled() and panel.elgin.plus.isEnabled()
    assert panel.elgin.temperature.text() == "24" and panel.elgin.mode.currentText() == "Resfriar"
    assert not panel.elgin.fan.isEnabled()
    assert not controller.request_elgin("temperature", 100)
    finish(controller, panel)
