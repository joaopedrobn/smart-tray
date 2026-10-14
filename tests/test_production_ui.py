from pathlib import Path
import sys
from PySide6.QtCore import QRect, QEvent
from PySide6.QtTest import QTest
from smart_tray.beta import BetaSettings
from smart_tray.desktop_state import DesktopSettings
from smart_tray.direct_controller import DirectController
from smart_tray.quick_panel import QuickPanel
from smart_tray.quick_test_support import simulation, find_item
from test_interface import wait_until


def test_frozen_normal_launch_has_no_recorder_and_keeps_window_persistent(qt_app,tmp_path,monkeypatch):
    root=Path(__file__).parent / "fixtures/config"
    adapters,values,commands,threads=simulation(root)
    controller=DirectController(adapters,BetaSettings(tmp_path))
    controller.start();wait_until(qt_app,lambda:not controller.busy)
    monkeypatch.setattr(sys,'frozen',True,raising=False)
    monkeypatch.setattr(sys,'argv',['SmartTray.exe'])
    panel=QuickPanel(controller,root,DesktopSettings(tmp_path))
    warnings=[];panel.engine().warnings.connect(lambda items:warnings.extend(e.description() for e in items))
    try:
        assert not panel.bridge.developmentToolsEnabled and panel.bridge.recorder is None
        panel.show_at_tray(QRect(100,100,20,20));QTest.qWait(50)
        panel.bridge.openSceneDiscovery();panel.bridge.startSceneCapture()
        panel.bridge.page='light';QTest.qWait(50)
        assert find_item(panel,'sceneDiscovery') is None
        qt_app.sendEvent(panel,QEvent(QEvent.Type.WindowDeactivate))
        assert panel.isVisible()
        panel.setPosition(120,panel.position().y());position=panel.position()
        panel.hide();panel.show_at_tray(QRect(500,500,20,20))
        assert panel.position()==position and panel.isVisible()
        assert not warnings and not commands
    finally:
        controller.stop();controller.pool.waitForDone(3000)
        panel.hide();panel.deleteLater();qt_app.processEvents()
