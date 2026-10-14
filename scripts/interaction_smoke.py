"""Native interaction check; hardware transport and DPAPI are unreachable."""
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from PySide6.QtWidgets import QApplication
from smart_tray.ui import configure_style
from smart_tray.interaction_smoke import run

if __name__ == "__main__":
    app = QApplication([])
    app.setQuitOnLastWindowClosed(False)
    configure_style(app)
    raise SystemExit(run(app, ROOT, ROOT / "diagnostics/gui-interaction-smoke.json"))
