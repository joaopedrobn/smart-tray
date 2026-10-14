"""Native QML preview with prohibited credentials and simulated device states."""
from pathlib import Path
import sys
import tempfile
from unittest.mock import Mock
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from PySide6.QtCore import QTimer, QRect
from PySide6.QtWidgets import QApplication
from smart_tray.ui import configure_style
from smart_tray.adapters import DeviceState
from smart_tray.beta import BetaSettings
from smart_tray.desktop_state import DesktopSettings
from smart_tray.direct_controller import DirectController
from smart_tray.interactive_adapters import load_interactive_adapters
from smart_tray.quick_panel import QuickPanel

app = QApplication([])
app.setQuitOnLastWindowClosed(False)
configure_style(app)
temporary = tempfile.TemporaryDirectory(prefix='smart-tray-quick-preview-')
settings = BetaSettings(temporary.name)
settings.enabled = True
values = {'elgin': {'power': True, 'temperature': 24, 'ambient_temperature': 21, 'mode': 'cold', 'fan': 'mid', 'sleep': False, 'display': True, 'eco': False},
          'led': {20: True, 'mode': 'colour', 'colour': '00f003e803e8', 'brightness': 100},
          'novadigital': {1: True, 2: False}}
adapters = load_interactive_adapters(ROOT)
for role, adapter in adapters.items():
    base = getattr(adapter, 'base', adapter)
    base.store = Mock()
    base.store.load.side_effect = AssertionError('Preview cannot access credentials')
    base.factory = Mock(side_effect=AssertionError('Preview cannot access LAN'))
    adapter.read = lambda role=role: DeviceState('online', values[role].copy())
    adapter.write = Mock(side_effect=AssertionError('Preview writes prohibited'))
    if role != 'novadigital':
        adapter.execute = Mock(side_effect=AssertionError('Preview writes prohibited'))
controller = DirectController(adapters, settings)
panel = QuickPanel(controller, ROOT, DesktopSettings(temporary.name))
controller.start()
panel.show_at_tray(QRect(1300, 980, 20, 20))
panel.animation.stop(); panel.setOpacity(1)
if '--compact' in sys.argv:
    panel.resize(480, 620)
elif '--narrow' in sys.argv:
    panel.resize(420, 700)
suffix = '-discovery' if '--discover-effects' in sys.argv else '-compact' if '--compact' in sys.argv else '-narrow' if '--narrow' in sys.argv else ''
output = ROOT / ('diagnostics/quick-preview' + suffix)
output.mkdir(parents=True, exist_ok=True)
motion_frames = []
motion_preview = '--motion' in sys.argv

def capture_motion():
    # Optional local review artifact; Pillow is an analysis dependency only.
    import io
    from PIL import Image
    from PySide6.QtCore import QBuffer, QIODevice
    image = panel.grabWindow()
    buffer = QBuffer(); buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    image.save(buffer, 'PNG')
    motion_frames.append(Image.open(io.BytesIO(bytes(buffer.data()))).copy())

if motion_preview:
    for frame in range(45):
        QTimer.singleShot(500 + frame * 100, capture_motion)
def capture(page):
    panel.bridge.navigate(page)
    QTimer.singleShot(400, lambda: panel.grabWindow().save(str(output / (page + '-simulated.png'))))
offset = 5200 if motion_preview else 600
for index, page in enumerate(('climate', 'light', 'switch', 'settings')):
    QTimer.singleShot(offset + index * 700, lambda page=page: capture(page))
def capture_light_controls():
    from smart_tray.quick_test_support import find_item
    if '--discover-effects' in sys.argv:
        panel.bridge.openSceneDiscovery()
        QTimer.singleShot(400, lambda: panel.grabWindow().save(str(output/'discovery-ready-simulated.png')))
        return
    panel.bridge.navigate('light')
    scroll = find_item(panel, 'lightScroll').property('contentItem')
    scroll.setProperty('contentY', max(0, scroll.property('contentHeight')-scroll.height()))
    QTimer.singleShot(400, lambda: panel.grabWindow().save(str(output/'light-controls-simulated.png')))

QTimer.singleShot(offset + 2800, capture_light_controls)

def finish():
    if motion_frames:
        motion_frames[0].save(output / 'airflow-simulated.gif', save_all=True,
            append_images=motion_frames[1:], duration=100, loop=0)
    controller.stop(); controller.pool.waitForDone(3000); panel.hide(); app.quit()
QTimer.singleShot(offset + 3600, finish)
raise SystemExit(app.exec())
