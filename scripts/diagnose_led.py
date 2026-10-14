"""Interactive LED observation window. All device traffic is status queries."""
from pathlib import Path
import json
import logging
import os
import sys
from datetime import datetime, timedelta, timezone

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from PySide6.QtCore import QObject, Signal, QRunnable, QThreadPool, QTimer, Qt, QLockFile
from PySide6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
                              QComboBox, QPlainTextEdit, QDialog, QFormLayout, QLineEdit,
                              QDialogButtonBox)
from smart_tray.led_research import LedReader, Session, collect_schema, LED_ID
from smart_tray.diagnostic import cloud_connection, quiet
from smart_tray.ui import configure_style

CATEGORY_NAMES = [("Cor", "colour"), ("Brilho", "brightness"), ("Efeito", "effect"),
                  ("Velocidade", "speed"), ("Intensidade", "intensity"), ("Direção", "direction"),
                  ("Música", "music"), ("Modo", "mode"), ("Outro recurso", "other")]


class Signals(QObject):
    completed = Signal(object)
    failed = Signal()


class Task(QRunnable):
    def __init__(self, function):
        super().__init__()
        self.function = function
        self.signals = Signals()

    def run(self):
        try:
            with quiet():
                result = self.function()
            self.signals.completed.emit(result)
        except Exception:
            self.signals.failed.emit()
        finally:
            self.function = None  # Release closures containing transient API credentials.


def get_record(root):
    registry = json.loads((root / "diagnostics/provisioned.json").read_text(encoding="utf-8"))
    record = next(d for d in registry["devices"] if d["role"] == "led" and d["device_id"] == LED_ID)
    discovery = json.loads((root / "diagnostics/discovery-current.json").read_text(encoding="utf-8"))
    found = next(d for d in discovery["devices"] if d["device_id"] == LED_ID)
    return {**record, "ip": found["ip"], "protocol_version": found["protocol_version"]}


class ResearchWindow(QWidget):
    def __init__(self, reader, directory, *, device_id=LED_ID, title="Outsmart RGBIC", category_names=CATEGORY_NAMES, cloud_logs=False, cloud_window=None):
        super().__init__()
        self.cloud_logs = cloud_logs
        from smart_tray.rgbic_cloud_logs import START, END
        self.cloud_window = cloud_window or (START, END)
        self.schema_device_id = device_id
        self.reader, self.session = reader, Session(directory, device_id, {"baseline", *(code for _, code in category_names)})
        self.directory = Path(directory)
        self.setWindowTitle(f"Smart Tray · investigação {title} — somente leitura")
        self.resize(780, 640)
        self.setStyleSheet("QWidget { background: #0C0E12; } QPlainTextEdit { background: #14171F; border: 1px solid #222634; padding: 10px; }")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 22, 22, 22)
        layout.addWidget(QLabel(title + " · somente leitura"))
        instructions = QLabel("1. Capture o estado inicial.\n2. Altere uma única opção no Smart Life e aguarde 2 segundos.\n3. Selecione o tipo de alteração e capture depois.\nRepita para comparar cada mudança. Esta ferramenta nunca controla a fita.")
        instructions.setWordWrap(True)
        layout.addWidget(instructions)
        row = QHBoxLayout()
        self.baseline_button = QPushButton("1 · Capturar estado inicial")
        self.baseline_button.clicked.connect(lambda: self.capture("baseline"))
        row.addWidget(self.baseline_button)
        self.category = QComboBox()
        for name, code in category_names:
            self.category.addItem(name, code)
        row.addWidget(self.category)
        self.after_button = QPushButton("2 · Capturar após alteração manual")
        self.after_button.setEnabled(False)
        self.after_button.clicked.connect(lambda: self.capture(self.category.currentData()))
        row.addWidget(self.after_button)
        layout.addLayout(row)
        self.schema_button = QPushButton("Consultar especificação Tuya e modelo de dados…")
        self.schema_button.clicked.connect(self.schema_dialog)
        layout.addWidget(self.schema_button)
        self.status = QLabel("Sem leituras realizadas. Nenhuma escrita disponível.")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.output = QPlainTextEdit()
        self.output.setReadOnly(True)
        layout.addWidget(self.output, 1)
        layout.addWidget(QLabel("Valores identificados são sanitizados; strings desconhecidas ficam ocultas. Não há campos livres para credenciais/notas."))
        self.pool = QThreadPool(self)
        self.pool.setMaxThreadCount(1)
        self.task = None
        self.closing = False
        if cloud_logs:
            self.setWindowTitle('Smart Tray - logs Cloud RGBIC - somente leitura')
            instructions.setText('Logs existentes: 12/10/2026, 17:17:30 a 17:21:00 (Brasilia).\nSomente consultas Cloud de envios e reportes; nenhuma leitura LAN ou controle.\nRegiao us. Credenciais somente no formulario local e em memoria.')
            times = [datetime.fromtimestamp(t / 1000, timezone(timedelta(hours=-3))).strftime('%d/%m/%Y %H:%M:%S') for t in self.cloud_window]
            instructions.setText(f'Logs existentes: {times[0]} a {times[1]} (Brasilia).\nUma unica pagina, sem retries. Nenhum controle ou leitura LAN.\nRegiao us. Credenciais somente no formulario local e em memoria.')
            for widget in (self.baseline_button, self.after_button, self.category):
                widget.hide()
            self.schema_button.setText('Consultar logs existentes da fita...')

    def set_busy(self, busy):
        for widget in (self.baseline_button, self.schema_button, self.category):
            widget.setEnabled(not busy)
        self.after_button.setEnabled(not busy and self.session.baseline is not None)

    def submit(self, function, callback):
        if self.task is not None:
            return
        self.set_busy(True)
        self.status.setText("Consultando… a interface permanece disponível.")
        self.task = Task(function)
        self.task.signals.completed.connect(callback)
        self.task.signals.failed.connect(self.failed)
        self.pool.start(self.task)

    def capture(self, category):
        self.submit(lambda: self.session.record(self.reader.capture(), category), self.captured)

    def captured(self, event):
        self.task = None
        self.output.setPlainText(json.dumps(event, ensure_ascii=False, indent=2))
        changed = ", ".join(event["changes"]) or "nenhum"
        self.status.setText(f"DPS alterados: {changed}. Correlação, não validação de comandos. Registro: {self.session.path.name}")
        self.set_busy(False)

    def failed(self):
        self.task = None
        self.status.setText("Consulta não concluída. Nenhum erro bruto ou credencial exibido. Nenhum controle enviado. Verifique conexão/perfil/serviços.")
        self.set_busy(False)

    def schema_dialog(self):
        dialog = QDialog(self)
        dialog.setObjectName("cloudSchemaDialog")
        target = "Elgin · DPS 5" if self.schema_device_id != LED_ID else "Outsmart"
        dialog.setWindowTitle(f"{'Logs RGBIC' if self.cloud_logs else 'Especificação Tuya'} · {target} · credenciais somente em memória")
        dialog.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
        form = QFormLayout(dialog)
        region = QComboBox()
        region.addItems(["us", "us-e", "eu", "eu-w", "cn", "in", "sg"])
        region.setObjectName("cloudRegion")
        region.setCurrentText("us")
        if self.cloud_logs:
            region.setEnabled(False)
        api_id, secret = QLineEdit(), QLineEdit()
        for field in (api_id, secret):
            field.setEchoMode(QLineEdit.EchoMode.Password)
        api_id.setObjectName("cloudAccessId")
        secret.setObjectName("cloudAccessSecret")
        form.addRow("Região do projeto existente", region)
        form.addRow("Access ID", api_id)
        form.addRow("Access Secret", secret)
        form.addRow(QLabel("Somente GET do aparelho identificado. Não coleta/grava Local_Key nem altera provisionamento."))
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        form.addRow(buttons)
        def focus_form():
            dialog.showNormal()
            dialog.raise_()
            dialog.activateWindow()
            api_id.setFocus()
        QTimer.singleShot(0, focus_form)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            values = (region.currentText(), api_id.text(), secret.text())
            api_id.clear()
            secret.clear()
            if values[1] and values[2]:
                def fetch():
                    if self.cloud_logs:
                        from smart_tray.rgbic_cloud_logs import collect_logs, capture_intervals, START, END
                        from smart_tray.rgbic_capture import now, MASKED_ID
                        from smart_tray.cloud_evidence import failure_evidence
                        try:
                            with cloud_connection(*values, single_attempt=True) as cloud:
                                catalog = Path(os.environ['LOCALAPPDATA'])/'SmartTray/rgbic-scenes'
                                return collect_logs(cloud, (values[1], values[2], cloud.token),
                                    device_id=self.schema_device_id, start=self.cloud_window[0], end=self.cloud_window[1],
                                    intervals=capture_intervals(catalog), max_pages=1)
                        except Exception as exc:
                            evidence = getattr(exc, 'evidence', None) or failure_evidence(exception=type(exc).__name__)
                            return {'timestamp': now(), 'device_id_masked': MASKED_ID, 'region': 'us',
                                'window': {'start_ms': self.cloud_window[0], 'end_ms': self.cloud_window[1]},
                                'query_result': 'denied_or_unavailable', 'pages': 0,
                                'failure': evidence, 'logs_found': 0, 'sending_count': 0,
                                'report_count': 0, 'dreamlight_scene_mode_count': 0,
                                'logs': [], 'writes_sent': 0, 'replay_ready': False,
                                'next_step': 'resolve_query_access_or_completeness_first'}
                    with cloud_connection(*values, single_attempt=self.cloud_logs) as cloud:
                        return collect_schema(cloud, (values[1], values[2], cloud.token), device_id=self.schema_device_id)
                self.submit(fetch, self.logs_received if self.cloud_logs else self.schema_received)
        dialog.deleteLater()

    def logs_received(self, report):
        self.task = None
        self.directory.mkdir(parents=True, exist_ok=True)
        path = self.directory/'cloud-logs-current.json'
        try:
            if path.exists():
                previous = json.loads(path.read_text(encoding='utf-8'))
                window = previous.get('window', {})
                if window != report.get('window'):
                    archive = self.directory/f"cloud-logs-{window.get('start_ms')}-{window.get('end_ms')}.json"
                    if not archive.exists():
                        archive.write_text(json.dumps(previous, ensure_ascii=False, indent=2), encoding='utf-8')
                    report['comparison_previous'] = {
                        'window': window,
                        'previous_counts': {k: previous.get(k) for k in ('logs_found','sending_count','report_count','dreamlight_scene_mode_count')},
                        'previous_codes': sorted({r['code'] for r in previous.get('logs', [])}),
                        'current_codes': sorted({r['code'] for r in report.get('logs', [])}),
                        'scene_identity_from_time_only': True}
                    if report['query_result'] == 'read_ok' and not report.get('omitted_records') and not report['dreamlight_scene_mode_count']:
                        report['next_step'] = 'inspect_nonstandard_dp_log_coverage_no_repeat_4g_capture'
            archive = self.directory/f"cloud-logs-{report['window']['start_ms']}-{report['window']['end_ms']}.json"
            archive.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
            path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        except OSError:
            self.output.setPlainText(json.dumps(report, ensure_ascii=False, indent=2))
            self.status.setText('Consulta concluida; nao foi possivel salvar. Resultado seguro visivel nesta janela.')
            self.set_busy(False)
            return
        self.output.setPlainText(json.dumps(report, ensure_ascii=False, indent=2))
        self.status.setText(f"Consulta: {report['query_result']} | Logs: {report['logs_found']} | Envios: {report['sending_count']} | Reportes: {report['report_count']} | Cenas: {report['dreamlight_scene_mode_count']}\nSalvo em {path}. Nenhum comando enviado.")
        self.set_busy(False)

    def schema_received(self, schema):
        self.task = None
        self.directory.mkdir(parents=True, exist_ok=True)
        path = self.directory / "schema-current.json"
        path.write_text(json.dumps(schema, ensure_ascii=False, indent=2), encoding="utf-8")
        if hasattr(self.reader, "set_schema"):
            self.reader.set_schema(schema)
        self.output.setPlainText(json.dumps(schema, ensure_ascii=False, indent=2))
        self.status.setText("Especificação consultada. Resultados por endpoint em schema-current.json; não são comandos validados.")
        self.set_busy(False)

    def closeEvent(self, event):
        if self.task is not None:
            self.status.setText("Aguarde a consulta terminar antes de fechar.")
            event.ignore()
        else:
            event.accept()


def main():
    logging.disable(100)
    if "--baseline" in sys.argv:
        try:
            capture = LedReader(get_record(ROOT)).capture()
            event = Session(ROOT / "diagnostics/led-research").record(capture, "baseline")
            (ROOT / "diagnostics/led-research/baseline-current.json").write_text(json.dumps(event, ensure_ascii=False, indent=2), encoding="utf-8")
            print(json.dumps(event, ensure_ascii=True, indent=2))
            return 0
        except Exception:
            print("Leitura indisponivel; nenhum comando ou erro bruto exibido.")
            return 1
    app = QApplication(sys.argv[:1])
    configure_style(app)
    logs_mode = '--cloud-logs' in sys.argv
    cloud_window = None
    if logs_mode:
        import argparse
        parser = argparse.ArgumentParser()
        parser.add_argument('--cloud-logs', action='store_true')
        parser.add_argument('--cloud-start')
        parser.add_argument('--cloud-end')
        args = parser.parse_args()
        if args.cloud_start or args.cloud_end:
            start, end = (datetime.fromisoformat(value) for value in (args.cloud_start, args.cloud_end))
            if start.tzinfo is None or end.tzinfo is None:
                raise ValueError('Timezone required')
            cloud_window = (int(start.timestamp()*1000), int(end.timestamp()*1000))
            if not 0 < cloud_window[1]-cloud_window[0] <= 600_000:
                raise ValueError('Invalid bounded window')
    query_lock = None
    if logs_mode:
        folder = Path(os.environ['LOCALAPPDATA'])/'SmartTray'
        folder.mkdir(parents=True, exist_ok=True)
        query_lock = QLockFile(str(folder/'rgbic-cloud-query.lock'))
        if not query_lock.tryLock(0):
            return 0
    try:
        reader = LedReader(get_record(ROOT))
        window = ResearchWindow(reader, ROOT / ('diagnostics/rgbic-scenes' if logs_mode else 'diagnostics/led-research'), cloud_logs=logs_mode, cloud_window=cloud_window)
    except Exception:
        from PySide6.QtWidgets import QMessageBox
        QMessageBox.critical(None, "Investigação LED", "Perfil/descoberta indisponível. Nenhum comando enviado.")
        return 1
    from smart_tray.windows import show_interactive_window
    show_interactive_window(window)
    if logs_mode:
        QTimer.singleShot(150, window.schema_dialog)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
