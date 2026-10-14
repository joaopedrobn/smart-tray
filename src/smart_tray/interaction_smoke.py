"""Native Win32 mouse checks with simulated devices. No credentials or LAN."""
import ctypes
from ctypes import wintypes
import json
from pathlib import Path
import tempfile
import threading
import time
from PySide6.QtCore import QObject, QEvent, QTimer, Qt, QPoint
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QPushButton, QMessageBox, QDialogButtonBox, QCheckBox, QScrollArea
from .adapters import DeviceState
from .beta import BetaAdapter, BetaSettings, VERSION, load_beta_adapters
from .beta_controller import BetaController
from .beta_ui import BetaPanel


class MouseProbe(QObject):
    def __init__(self):
        super().__init__()
        self.presses = 0

    def eventFilter(self, widget, event):
        if event.type() == QEvent.Type.MouseButtonPress:
            self.presses += 1
        return False


def run(app, root, output):
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    user32.ClientToScreen.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.POINT)]
    user32.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
    user32.GetAncestor.restype = wintypes.HWND
    user32.WindowFromPoint.argtypes = [wintypes.POINT]
    user32.WindowFromPoint.restype = wintypes.HWND
    user32.SetForegroundWindow.argtypes = [wintypes.HWND]
    user32.mouse_event.argtypes = [wintypes.DWORD, wintypes.DWORD, wintypes.DWORD, wintypes.DWORD, ctypes.c_size_t]
    original_cursor = wintypes.POINT()
    user32.GetCursorPos(ctypes.byref(original_cursor))
    report = {"version": VERSION, "frozen": bool(getattr(__import__('sys'), 'frozen', False)),
        "platform": app.platformName(), "transport": "simulated_no_credentials_no_network",
        "real_device_writes": 0, "checks": {}, "mock_commands": [], "worker_thread_ids": []}
    heartbeat = []
    timer = QTimer()
    timer.setInterval(20)
    timer.timeout.connect(lambda: heartbeat.append(time.monotonic()))
    probe = MouseProbe()
    app.installEventFilter(probe)
    temporary = tempfile.TemporaryDirectory(prefix="smart-tray-interaction-")
    settings = BetaSettings(Path(temporary.name))
    settings.enabled = False  # Exercise the real default; isolated preferences.
    adapters = load_beta_adapters(root)
    simulated = {"elgin": {"power": True, "temperature": 24, "ambient_temperature": 21,
                 "mode": "cold", "fan": "low", "sleep": False, "display": True, "eco": False},
                 "led": {20: True, "mode": "scene", "colour": "000003e803e8", "brightness": 100},
                 "novadigital": {1: True, 2: True}}
    def prohibit(*args, **kwargs):
        raise AssertionError("Native interaction test cannot access LAN or credentials")
    for role, adapter in adapters.items():
        base = getattr(adapter, "base", adapter)
        if not hasattr(base, "store"):
            raise AssertionError("Required adapter unavailable")
        base.store = type("NoCredentials", (), {"load": prohibit, "save": prohibit})()
        base.factory = prohibit
        def read(role=role):
            report["worker_thread_ids"].append(threading.get_ident())
            return DeviceState("online", simulated[role].copy(), "Estado atualizado")
        adapter.read = read
        def write(dp, before, value, role=role):
            report["worker_thread_ids"].append(threading.get_ident())
            report["mock_commands"].append({"role": role, "dp": dp, "value": value})
            simulated[role][dp] = value
            return DeviceState("online", simulated[role].copy(), "Estado atualizado")
        adapter.write = write
        if isinstance(adapter, BetaAdapter):
            def execute(name, state, value, *, experimental_approved=False, role=role, adapter=adapter):
                report["worker_thread_ids"].append(threading.get_ident())
                adapter.validate(name, value)
                if not adapter.is_validated(name, value) and not experimental_approved:
                    raise AssertionError("Missing approval")
                report["mock_commands"].append({"role": role, "function": name,
                    "command": adapter.proposed(name, value, state)})
                simulated[role][name] = value
                return DeviceState("online", simulated[role].copy(), "Estado atualizado")
            adapter.execute = execute
    controller = BetaController(adapters, settings)
    panel = BetaPanel(controller)
    panel.setWindowTitle("Smart Tray · VERIFICAÇÃO GUI · dispositivos simulados")
    panel.preferences.connect(panel.settings_dialog)

    def wait(predicate, timeout=2500):
        deadline = time.monotonic() + timeout / 1000
        while not predicate() and time.monotonic() < deadline:
            QTest.qWait(20)
        assert predicate(), "Interaction condition timed out"

    def click(widget, point=None):
        assert widget.isVisible() and widget.isEnabled(), "Target widget unavailable"
        parent = widget.parentWidget()
        while parent:
            if isinstance(parent, QScrollArea):
                parent.ensureWidgetVisible(widget)
                QTest.qWait(30)
                break
            parent = parent.parentWidget()
        window = widget.window()
        window.raise_()
        window.activateWindow()
        user32.SetForegroundWindow(int(window.winId()))
        QTest.qWait(50)
        local = widget.mapTo(window, point or widget.rect().center())
        ratio = window.devicePixelRatioF()
        position = wintypes.POINT(round(local.x() * ratio), round(local.y() * ratio))
        assert user32.ClientToScreen(int(window.winId()), ctypes.byref(position))
        user32.SetCursorPos(position.x, position.y)
        QTest.qWait(30)
        hit = user32.WindowFromPoint(position)
        hit_root = user32.GetAncestor(hit, 2)
        if hit_root != int(window.winId()):
            report["hit_guard"] = {"target": int(window.winId()), "hit": int(hit_root or 0),
                "target_qt_visible": window.isVisible(), "point": [position.x, position.y]}
        assert hit_root == int(window.winId()), "Another native window covers target; click cancelled"
        user32.mouse_event(0x0002, 0, 0, 0, 0)
        user32.mouse_event(0x0004, 0, 0, 0, 0)
        QTest.qWait(80)

    def answer(yes=True):
        wait(lambda: "confirmation" in panel.dialogs)
        dialog = panel.dialogs["confirmation"]
        assert not dialog.isModal() and panel.isEnabled()
        click(dialog.button(QMessageBox.StandardButton.Yes if yes else QMessageBox.StandardButton.No))
        wait(lambda: "confirmation" not in panel.dialogs and not controller.writing)

    def choose(combo, value):
        click(combo)
        wait(lambda: combo.view().isVisible())
        index = combo.model().index(combo.findData(value), 0)
        combo.view().scrollTo(index)
        QTest.qWait(30)
        click(combo.view().viewport(), combo.view().visualRect(index).center())

    try:
        timer.start()
        controller.start()
        wait(lambda: not controller.busy)
        panel.show_at_tray(__import__('PySide6.QtCore', fromlist=['QRect']).QRect())
        panel.animation.stop()
        panel.setWindowOpacity(1)
        QTest.qWait(150)
        assert not report["mock_commands"]
        report["checks"]["startup_no_writes"] = True
        assert not panel.colour_button.isEnabled() and not panel.elgin.mode.isVisible()
        click(panel.unlock_beta)
        answer(False)
        assert not settings.enabled and not report["mock_commands"]
        click(panel.unlock_beta)
        answer(True)
        assert settings.enabled and not report["mock_commands"]
        click(panel.fixed_colour)
        answer(True)
        assert report["mock_commands"][-1]["command"] == {"21": "colour"}
        assert panel.colour_button.isEnabled() and panel.brightness.isEnabled()
        report["checks"]["inline_unlock_is_local_and_fixed_colour_is_separate_confirmed_command"] = True
        for role, dp in (("novadigital", 1), ("novadigital", 2), ("led", 20), ("led", 20)):
            before_count = len(report["mock_commands"])
            click(panel.buttons[(role, dp)])
            wait(lambda: not controller.writing)
            assert len(report["mock_commands"]) == before_count + 1
        report["checks"]["power_buttons_receive_native_clicks"] = True
        click(panel.elgin.plus)
        wait(lambda: not controller.writing)
        assert controller.states["elgin"].values["temperature"] == 25
        choose(panel.elgin.fan, "mid")
        wait(lambda: not controller.writing)
        assert controller.states["elgin"].values["fan"] == "mid"
        report["checks"]["validated_elgin_temperature_and_mid"] = True
        advanced_button = next(b for b in panel.led.findChildren(QPushButton) if b.text() == "Controles avançados")
        click(advanced_button)
        wait(lambda: "advanced_led" in panel.dialogs)
        advanced = panel.dialogs["advanced_led"]
        assert advanced.isVisible() and panel.isEnabled() and not advanced.isModal()
        panel.hide()
        QTest.qWait(50)
        assert advanced.isVisible()  # Regression: independent window survives owner hide.
        panel.show_at_tray(__import__('PySide6.QtCore', fromlist=['QRect']).QRect())
        panel.animation.stop(); panel.setWindowOpacity(1)
        panel.advanced("led")
        assert panel.dialogs["advanced_led"] is advanced
        report["checks"]["advanced_visible_nonmodal_singleton_survives_tray_hide"] = True
        count = len(report["mock_commands"])
        choose(advanced.controls["mode"], "white")
        answer(False)
        assert len(report["mock_commands"]) == count
        choose(advanced.controls["mode"], "white")
        answer(True)
        assert controller.states["led"].values["mode"] == "white"
        assert not advanced.controls["colour"].isEnabled()
        choose(advanced.controls["mode"], "colour")
        # The same target was already explicitly approved in the inline flow.
        wait(lambda: not controller.writing)
        assert advanced.controls["colour"].isEnabled()
        report["checks"]["mode_selectors_and_experimental_confirm_cancel"] = True
        click(advanced.controls["colour"])
        wait(lambda: "colour" in panel.dialogs)
        picker = panel.dialogs["colour"]
        assert picker.isVisible() and not picker.isModal()
        box = picker.findChild(QDialogButtonBox)
        click(box.button(QDialogButtonBox.StandardButton.Cancel))
        wait(lambda: "colour" not in panel.dialogs)
        blue = next(b for b in advanced.findChildren(QPushButton) if b.text() == "Azul")
        click(blue)
        answer(True)
        assert controller.states["led"].values["colour"] == "00f003e803e8"
        report["checks"]["colour_picker_and_palette_handlers"] = True
        slider = advanced.controls["brightness"]
        click(slider, QPoint(slider.width() // 3, slider.height() // 2))
        answer(True)
        assert controller.states["led"].values["brightness"] < 100
        report["checks"]["brightness_slider_native_click_debounce"] = True
        advanced.grab().save(str(Path(output).with_name("beta3-advanced-simulated.png")))
        advanced.close()
        panel.findChild(QScrollArea).ensureWidgetVisible(panel.elgin)
        QTest.qWait(30)
        panel.grab().save(str(Path(output).with_name("beta3-panel-simulated.png")))
        settings_button = next(b for b in panel.findChildren(QPushButton) if b.text() == "···")
        click(settings_button)
        wait(lambda: "settings" in panel.dialogs)
        preferences = panel.dialogs["settings"]
        checkbox = preferences.findChild(QCheckBox)
        click(checkbox, QPoint(9, checkbox.height() // 2))
        assert settings.enabled is False and BetaSettings(Path(temporary.name)).enabled is False
        click(checkbox, QPoint(9, checkbox.height() // 2))
        assert settings.enabled is True
        preferences.close()
        report["checks"]["settings_mouse_toggle_and_isolated_persistence"] = True
        before_ticks = len(heartbeat)
        def offline():
            time.sleep(1)
            return DeviceState("offline", {}, "Sem resposta LAN")
        adapters["elgin"].read = offline
        controller.refresh()
        wait(lambda: "novadigital" not in controller.busy and "led" not in controller.busy)
        assert "elgin" in controller.busy
        click(panel.buttons[("novadigital", 1)])
        wait(lambda: not controller.writing)
        assert "elgin" in controller.busy
        wait(lambda: not controller.busy)
        assert not panel.elgin.plus.isEnabled() and len(heartbeat) - before_ticks > 15
        report["checks"]["offline_device_does_not_block_other_controls_or_heartbeat"] = True
        assert all(t != threading.get_ident() for t in report["worker_thread_ids"])
        report["checks"]["operations_run_outside_gui_thread"] = True
        report["mouse_press_events"] = probe.presses
        report["heartbeat_ticks"] = len(heartbeat)
        assert probe.presses >= 15
        report["passed"] = True
    except Exception as error:
        report["passed"] = False
        report["failure_type"] = type(error).__name__
        tb = error.__traceback__
        lines = []
        while tb:
            lines.append(tb.tb_lineno)
            tb = tb.tb_next
        report["failure_lines"] = lines
        report["last_check"] = list(report["checks"])[-1] if report["checks"] else "startup"
    finally:
        controller.stop()
        controller.pool.waitForDone(4000)
        timer.stop()
        panel.hide()
        app.removeEventFilter(probe)
        user32.SetCursorPos(original_cursor.x, original_cursor.y)
        output = Path(output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, indent=2), encoding="utf-8")
        panel.deleteLater()
        app.processEvents()
        temporary.cleanup()
    return 0 if report.get("passed") else 1
