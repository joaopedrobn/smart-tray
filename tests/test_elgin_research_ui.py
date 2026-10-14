import importlib.util
from pathlib import Path
import sys
from contextlib import contextmanager
from test_interface import wait_until


def test_secure_window_clears_fields_and_runs_only_research(qt_app, tmp_path, monkeypatch):
    scripts = Path(__file__).parents[1] / "scripts"
    monkeypatch.syspath_prepend(str(scripts))
    spec = importlib.util.spec_from_file_location("elgin_observer_ui", scripts / "diagnose_elgin.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "ROOT", tmp_path)
    calls = []
    @contextmanager
    def cloud(*credentials):
        calls.append("authenticate")
        yield type("Cloud", (), {"token": "in-memory-token"})()
    monkeypatch.setattr(module, "cloud_connection", cloud)
    def schema(*args, **kwargs):
        calls.append("elgin_schema" if kwargs else "led_schema")
        return {"queries": []}
    monkeypatch.setattr(module, "collect_schema", schema)
    def elgin(*args):
        calls.append("elgin_provision_read")
        return {"result": "local_read_ok", "writes_sent": 0}
    monkeypatch.setattr(module, "provision_and_read", elgin)
    window = module.ProvisionWindow()
    assert window.api_id.echoMode() == window.api_id.EchoMode.Password
    assert window.secret.echoMode() == window.secret.EchoMode.Password
    window.api_id.setText("private-access")
    window.secret.setText("private-secret")
    window.button.click()
    assert window.api_id.text() == window.secret.text() == ""
    wait_until(qt_app, lambda: window.task is None)
    assert calls == ["authenticate", "led_schema", "elgin_provision_read", "elgin_schema"]
    assert "private-secret" not in window.output.toPlainText()
    assert "private-access" not in window.output.toPlainText()
    assert "in-memory-token" not in (tmp_path / "diagnostics/led-research/schema-current.json").read_text()
    window.close()
    window.pool.waitForDone(3000)
    window.deleteLater()
