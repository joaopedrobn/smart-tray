from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from PySide6.QtWidgets import QApplication
from smart_tray.ui import configure_style
from smart_tray.quick_smoke import run

app = QApplication([])
app.setQuitOnLastWindowClosed(False)
configure_style(app)
raise SystemExit(run(app, ROOT, ROOT / ('diagnostics/quick-window-smoke.json' if '--qt-input' in sys.argv else 'diagnostics/quick-native-smoke.json'), native_input='--qt-input' not in sys.argv))
