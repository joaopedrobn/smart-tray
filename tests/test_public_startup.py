from pathlib import Path
from PySide6.QtCore import QRect
from PySide6.QtTest import QTest
from smart_tray.adapters import load_adapters
from smart_tray.beta import BetaSettings
from smart_tray.desktop_state import DesktopSettings
from smart_tray.direct_controller import DirectController
from smart_tray.quick_panel import QuickPanel
from test_interface import wait_until


def test_empty_configuration_starts_without_network_or_credential_access(qt_app,tmp_path,monkeypatch):
    monkeypatch.setattr('smart_tray.security.CredentialStore.load',lambda *a: (_ for _ in ()).throw(AssertionError('No credential access')))
    adapters=load_adapters(tmp_path)
    controller=DirectController(adapters,BetaSettings(tmp_path/'preferences'))
    controller.start();wait_until(qt_app,lambda:not controller.busy)
    panel=QuickPanel(controller,tmp_path,DesktopSettings(tmp_path/'preferences'))
    try:
        panel.show_at_tray(QRect(0,0,10,10));QTest.qWait(50)
        assert panel.rootObject() is not None and panel.bridge.recorder is None
        assert not panel.bridge.state['led']['powerEnabled']
        assert not panel.bridge.state['elgin']['temperatureEnabled']
        assert all(s.connection != 'online' for s in controller.states.values())
    finally:
        controller.stop();controller.pool.waitForDone(3000);panel.hide();panel.deleteLater();qt_app.processEvents()
