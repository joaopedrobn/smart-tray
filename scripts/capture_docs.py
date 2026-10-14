"""Capture real QML screens with synthetic states, isolated preferences, no LAN."""
from pathlib import Path
import os
import sys
import tempfile
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QRect
from PySide6.QtTest import QTest
from smart_tray.quick_test_support import simulation
from smart_tray.beta import BetaSettings
from smart_tray.desktop_state import DesktopSettings
from smart_tray.direct_controller import DirectController
from smart_tray.quick_panel import QuickPanel
from smart_tray.adapters import DeviceState


def main():
    app=QApplication([]);app.setQuitOnLastWindowClosed(False)
    output=ROOT/'docs/images';output.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='smart-tray-docs-') as directory:
        adapters,values,commands,threads=simulation(ROOT/'tests/fixtures/config')
        values['led']['mode']='colour';values['led']['colour']='00f003e802bc';values['led']['brightness']=70
        settings=BetaSettings(directory);settings.enabled=True
        controller=DirectController(adapters,settings)
        panel=QuickPanel(controller,ROOT,DesktopSettings(directory))
        controller.start()
        for _ in range(50):
            QTest.qWait(20)
            if not controller.busy:break
        panel.show_at_tray(QRect(100,100,20,20));panel.resize(480,1120)
        panel.animation.stop();panel.setOpacity(1)
        for page,name in (('climate','climate'),('light','lighting'),('switch','switch')):
            panel.bridge.navigate(page);QTest.qWait(600)
            assert panel.grabWindow().save(str(output/f'smart-tray-{name}.png'))
        assert not commands
        controller.stop();controller.pool.waitForDone(3000);panel.hide();panel.deleteLater();app.processEvents()
    print('Captured three real QML screenshots using synthetic device states; no network or credentials.')


if __name__=='__main__':main()
