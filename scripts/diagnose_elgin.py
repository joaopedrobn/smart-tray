"""Secure local cloud credentials; LED schema followed by Elgin provisioning/read."""
from pathlib import Path
import json
import logging
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from PySide6.QtWidgets import (QApplication, QWidget, QFormLayout, QLabel, QComboBox,
                              QLineEdit, QPushButton, QPlainTextEdit)
from PySide6.QtCore import QThreadPool
from diagnose_led import Task
from smart_tray.diagnostic import cloud_connection
from smart_tray.elgin_research import provision_and_read, ELGIN_ID
from smart_tray.led_research import collect_schema
from smart_tray.ui import configure_style


class ProvisionWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Smart Tray · Elgin Smart Life — provisionamento e leitura")
        self.resize(700, 620)
        layout = QFormLayout(self)
        message = QLabel("Identidade confirmada: exampl…0003 / 02:00:00:00:00:03.\n"
                         "Primeiro consulta o schema da fita; depois obtém a chave do Elgin,\n"
                         "protege com DPAPI e consulta seu estado LAN 3.5. Nenhum controle.\n"
                         "As credenciais abaixo ficam somente em memória; não as envie pelo chat.")
        message.setWordWrap(True)
        layout.addRow(message)
        self.region = QComboBox()
        self.region.addItems(["us", "us-e", "eu", "eu-w", "cn", "in", "sg"])
        self.api_id, self.secret = QLineEdit(), QLineEdit()
        for field in (self.api_id, self.secret):
            field.setEchoMode(QLineEdit.EchoMode.Password)
        layout.addRow("Região do projeto existente", self.region)
        layout.addRow("Access ID", self.api_id)
        layout.addRow("Access Secret", self.secret)
        self.button = QPushButton("Consultar fita → provisionar e ler Elgin")
        self.button.clicked.connect(self.start)
        layout.addRow(self.button)
        self.status = QLabel("Aguardando preenchimento local. Chaves da fita e do interruptor serão preservadas.")
        self.status.setWordWrap(True)
        layout.addRow(self.status)
        self.output = QPlainTextEdit()
        self.output.setReadOnly(True)
        layout.addRow(self.output)
        self.pool = QThreadPool(self)
        self.pool.setMaxThreadCount(1)
        self.task = None

    def start(self):
        if self.task is not None or not self.api_id.text() or not self.secret.text():
            return
        credentials = (self.region.currentText(), self.api_id.text(), self.secret.text())
        self.api_id.clear()
        self.secret.clear()
        self.button.setEnabled(False)
        self.status.setText("Consultando em segundo plano. Nenhuma escrita de controle será enviada.")
        def work():
            with cloud_connection(*credentials) as cloud:
                schema = collect_schema(cloud, (*credentials[1:], cloud.token))
                path = ROOT / "diagnostics/led-research/schema-current.json"
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(json.dumps(schema, ensure_ascii=False, indent=2), encoding="utf-8")
                report = provision_and_read(ROOT, cloud, credentials[1], credentials[2])
                elgin_schema = collect_schema(cloud, (*credentials[1:], cloud.token), device_id=ELGIN_ID)
                (ROOT / "diagnostics/elgin-schema.json").write_text(json.dumps(elgin_schema, ensure_ascii=False, indent=2), encoding="utf-8")
                return {"led_schema": schema, "elgin": report}
        self.task = Task(work)
        self.task.signals.completed.connect(self.completed)
        self.task.signals.failed.connect(self.failed)
        self.pool.start(self.task)

    def completed(self, result):
        self.task = None
        self.button.setEnabled(True)
        self.output.setPlainText(json.dumps(result, ensure_ascii=False, indent=2))
        self.status.setText("Elgin: " + result["elgin"]["result"] + ". Controles permanecem bloqueados. Relatórios salvos sem credenciais.")

    def failed(self):
        self.task = None
        self.button.setEnabled(True)
        self.status.setText("Consulta não concluída. Verifique região, vínculo e descoberta. Nenhum erro bruto exibido; nenhum controle enviado.")

    def closeEvent(self, event):
        if self.task is not None:
            event.ignore()
        else:
            event.accept()


if __name__ == "__main__":
    logging.disable(100)
    app = QApplication(sys.argv[:1])
    configure_style(app)
    window = ProvisionWindow()
    window.show()
    raise SystemExit(app.exec())
