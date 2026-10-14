import importlib.util
from pathlib import Path
from unittest.mock import Mock
from smart_tray.elgin_observation import observation, CATEGORY_NAMES
from smart_tray.elgin_research import ELGIN_ID
from test_elgin_control import record
from test_interface import wait_until


def test_manual_elgin_observer_ui_only_reads_and_exports_elgin_identity(qt_app, tmp_path):
    spec = importlib.util.spec_from_file_location("observer_ui", Path(__file__).parents[1] / "scripts/diagnose_led.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    reader = Mock()
    reader.capture.side_effect = [observation({"dps": {"1": True, "4": "cold"}}, record(), "synthetic", b"test"),
                                  observation({"dps": {"1": True, "4": "wind"}}, record(), "synthetic", b"test")]
    window = module.ResearchWindow(reader, tmp_path, device_id=ELGIN_ID, title="Elgin", category_names=CATEGORY_NAMES)
    window.baseline_button.click()
    wait_until(qt_app, lambda: window.task is None)
    window.category.setCurrentIndex(window.category.findData("mode"))
    window.after_button.click()
    wait_until(qt_app, lambda: window.task is None)
    assert window.session.events[-1]["changes"]["4"]["after"]["value"] == "wind"
    assert window.schema_device_id == ELGIN_ID
    reader.write.assert_not_called()
    reader.command.assert_not_called()
    window.close()
    window.pool.waitForDone(3000)
    window.deleteLater()


def test_cloud_form_defaults_us_masks_credentials_and_cancel_sends_nothing(qt_app, tmp_path):
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QComboBox, QLineEdit
    spec = importlib.util.spec_from_file_location("cloud_form_ui", Path(__file__).parents[1] / "scripts/diagnose_led.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    reader = Mock()
    window = module.ResearchWindow(reader, tmp_path, device_id=ELGIN_ID, title="Elgin", category_names=CATEGORY_NAMES)
    checked = []
    def inspect():
        dialog = qt_app.activeModalWidget()
        checked.append((dialog.objectName(), dialog.findChild(QComboBox, "cloudRegion").currentText(),
                        dialog.findChild(QLineEdit, "cloudAccessId").echoMode(),
                        dialog.findChild(QLineEdit, "cloudAccessSecret").echoMode()))
        dialog.reject()
    QTimer.singleShot(0, inspect)
    window.schema_dialog()
    assert checked == [("cloudSchemaDialog", "us", QLineEdit.EchoMode.Password, QLineEdit.EchoMode.Password)]
    assert window.task is None
    reader.capture.assert_not_called()
    window.close()
    window.deleteLater()
