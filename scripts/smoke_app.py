"""Native Windows/tray smoke check with authenticated reads ONLY; no clicks/writes."""
import json
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QSystemTrayIcon
from smart_tray.adapters import load_adapters
from smart_tray.controller import Controller
from smart_tray.app import TrayApplication
from smart_tray.ui import configure_style
from smart_tray.windows import SingleInstance


def main():
    app = QApplication([])
    app.setQuitOnLastWindowClosed(False)
    configure_style(app)
    instance = SingleInstance()
    if not instance.acquire():
        print("Another instance is already running; smoke check skipped.")
        return
    adapters = load_adapters(ROOT)
    # Defense in depth: if any GUI wiring attempts a write, fail instead of send.
    def prohibit_write(*args, **kwargs):
        raise AssertionError("No device writes during smoke check")
    for adapter in adapters.values():
        adapter.write = prohibit_write
        if hasattr(adapter, "command"):
            adapter.command = prohibit_write
        if hasattr(adapter, "command_from_state"):
            adapter.command_from_state = prohibit_write
    controller = Controller(adapters)
    tray_app = TrayApplication(app, ROOT, controller, instance)
    controller.refresh()
    timer = QTimer()
    timer.setInterval(100)
    def capture():
        tray_app.panel.animation.stop()
        tray_app.panel.setWindowOpacity(1)
        tray_app.panel.grab().save(str(ROOT / "diagnostics/ui-native-read.png"))
        result = {"platform": app.platformName(), "tray_available": QSystemTrayIcon.isSystemTrayAvailable(),
                  "device_writes": 0, "states": {role: {"connection": state.connection, "values": state.values}
                                                   for role, state in controller.states.items()}}
        (ROOT / "diagnostics/app-smoke.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
        print(json.dumps(result))
        tray_app.quit()
    def ready():
        if not controller.busy:
            timer.stop()
            tray_app.show()
            QTimer.singleShot(250, capture)
    timer.timeout.connect(ready)
    timer.start()
    # Bound the check even if a driver gets stuck. Do not force-kill a worker.
    QTimer.singleShot(30000, tray_app.quit)
    app.exec()


if __name__ == "__main__":
    main()
