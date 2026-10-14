"""Render an offline preview. No credential loading, sockets or device writes."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from PySide6.QtWidgets import QApplication
from smart_tray.adapters import ElginAdapter, DeviceState
from smart_tray.controller import Controller
from smart_tray.ui import Panel, configure_style


class PreviewAdapter:
    channels = {20: "switch_led"}
    def read(self):
        return DeviceState()


app = QApplication([])
configure_style(app)
controller = Controller({"elgin": ElginAdapter(), "led": PreviewAdapter(), "novadigital": PreviewAdapter()})
panel = Panel(controller)
panel.show()
app.processEvents()
path = ROOT / "diagnostics/ui-preview.png"
panel.grab().save(str(path))
panel.hide()
print("Offline preview saved: diagnostics/ui-preview.png")
