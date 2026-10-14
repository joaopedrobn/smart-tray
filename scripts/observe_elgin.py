"""Read-only Elgin schema and manual Smart Life comparison window."""
import json
import logging
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTimer, QLockFile
from diagnose_led import ResearchWindow
from smart_tray.elgin_observation import ElginObserver, CATEGORY_NAMES
from smart_tray.elgin_research import ELGIN_ID
from smart_tray.led_research import Session
from smart_tray.ui import configure_style


def main():
    record = next(d for d in json.loads((ROOT / "diagnostics/provisioned.json").read_text(encoding="utf-8"))["devices"] if d["role"] == "elgin")
    found = next(d for d in json.loads((ROOT / "diagnostics/discovery-current.json").read_text(encoding="utf-8"))["devices"] if d["device_id"] == ELGIN_ID)
    reader = ElginObserver({**record, "ip": found["ip"], "protocol_version": found["protocol_version"]})
    directory = ROOT / "diagnostics/elgin-research"
    if (directory / "schema-current.json").exists():
        reader.set_schema(json.loads((directory / "schema-current.json").read_text(encoding="utf-8")))
    if "--baseline" in sys.argv:
        event = Session(directory, ELGIN_ID, {"baseline"}).record(reader.capture(), "baseline")
        (directory / "baseline-current.json").write_text(json.dumps(event, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(event, ensure_ascii=True, indent=2))
        return 0
    app = QApplication(sys.argv[:1])
    if "--schema-dialog" in sys.argv:
        lock_path = Path(os.environ["LOCALAPPDATA"]) / "SmartTray/elgin-cloud-query.lock"
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        query_lock = QLockFile(str(lock_path))
        query_lock.setStaleLockTime(0)
        if not query_lock.tryLock(0):
            return 0  # Never create a second Cloud form.
        app.setQuitOnLastWindowClosed(False)
    configure_style(app)
    window = ResearchWindow(reader, directory, device_id=ELGIN_ID, title="Elgin Eco Inverter III · valores DPS 5", category_names=CATEGORY_NAMES)
    if "--schema-dialog" in sys.argv:
        def open_schema():
            # One visible window: show the result panel only after the form closes.
            window.schema_dialog()
            window.show()
            window.raise_()
            window.activateWindow()
            app.setQuitOnLastWindowClosed(True)
        QTimer.singleShot(0, open_schema)
    else:
        window.show()
    return app.exec()


if __name__ == "__main__":
    logging.disable(100)
    try:
        raise SystemExit(main())
    except Exception:
        print("Consulta indisponivel. Nenhum erro bruto exibido; nenhum controle enviado.")
        raise SystemExit(1)
