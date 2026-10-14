import importlib.util
from pathlib import Path
from unittest.mock import Mock
from smart_tray.led_research import capture_response
from test_interface import wait_until


def test_interactive_observer_records_manual_changes_without_any_write(qt_app, tmp_path):
    spec = importlib.util.spec_from_file_location("led_observer_ui", Path(__file__).parents[1] / "scripts/diagnose_led.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    reader = Mock()
    reader.capture.side_effect = [capture_response({"dps": {"24": "000003e803e8"}}, (), b"test"),
                                  capture_response({"dps": {"24": "00f003e803e8"}}, (), b"test")]
    window = module.ResearchWindow(reader, tmp_path)
    assert not window.after_button.isEnabled()
    window.baseline_button.click()
    wait_until(qt_app, lambda: window.task is None)
    assert window.after_button.isEnabled()
    window.after_button.click()
    wait_until(qt_app, lambda: window.task is None)
    assert reader.capture.call_count == 2
    reader.write.assert_not_called()
    assert '"24"' in window.output.toPlainText()
    assert len(window.session.events) == 2
    assert all(event["writes_sent"] == 0 for event in window.session.events)
    window.close()
    window.pool.waitForDone(3000)
    window.deleteLater()
