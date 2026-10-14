"""Native mouse validation of QML with simulated transport and isolated prefs."""
import ctypes
from ctypes import wintypes
import json
from pathlib import Path
import tempfile
import threading
import time
from PySide6.QtCore import QPointF, QPoint, QRect, QTimer, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QSystemTrayIcon
from PySide6.QtGui import QWindow, QWheelEvent
from types import SimpleNamespace
from unittest.mock import Mock
from .app import TrayApplication
from .adapters import DeviceState
from .beta import BetaSettings, VERSION
from .desktop_state import DesktopSettings
from .direct_controller import DirectController
from .quick_panel import QuickPanel
from .quick_test_support import simulation, find_item


def run(app, root, output, *, native_input=True):
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = tempfile.TemporaryDirectory(prefix='smart-tray-2-native-')
    settings = BetaSettings(temporary.name)
    adapters, values, commands, threads = simulation(root)
    controller = DirectController(adapters, settings)
    panel = QuickPanel(controller, root, DesktopSettings(temporary.name))
    panel.setTitle('Smart Tray 2 · verificação com aparelhos simulados')
    tray_app = TrayApplication(app, root, controller,
        SimpleNamespace(activated=Mock(), release=Mock()), panel_factory=lambda c: panel)
    other_window = QWindow()
    other_window.setTitle('Smart Tray · alvo de foco isolado para teste')
    other_window.setGeometry(100, 100, 240, 150)
    report = {'version': VERSION, 'frozen': bool(getattr(__import__('sys'), 'frozen', False)),
              'transport': 'simulated_no_credentials_no_network', 'real_writes': 0, 'input_backend': 'Win32' if native_input else 'QtTest', 'checks': {}}
    warnings = []
    panel.engine().warnings.connect(lambda items: warnings.extend({'line': e.line()} for e in items))
    user32 = ctypes.WinDLL('user32', use_last_error=True)
    user32.SetForegroundWindow.argtypes = [wintypes.HWND]
    user32.GetForegroundWindow.restype = wintypes.HWND
    user32.ClientToScreen.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.POINT)]
    user32.WindowFromPoint.argtypes = [wintypes.POINT]
    user32.WindowFromPoint.restype = wintypes.HWND
    user32.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
    user32.GetAncestor.restype = wintypes.HWND
    user32.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.UINT]
    user32.mouse_event.argtypes = [wintypes.DWORD, wintypes.DWORD, wintypes.DWORD, wintypes.DWORD, ctypes.c_size_t]
    original = wintypes.POINT()
    user32.GetCursorPos(ctypes.byref(original))
    ticks = []
    heartbeat = QTimer()
    heartbeat.setInterval(20)
    heartbeat.timeout.connect(lambda: ticks.append(time.monotonic()))
    click_count = 0

    def wait(predicate, timeout=4):
        deadline = time.monotonic() + timeout
        while not predicate() and time.monotonic() < deadline:
            QTest.qWait(20)
        assert predicate(), 'Native check timed out'

    def position(name, fraction=0.5):
        item = find_item(panel, name)
        assert item and item.isVisible() and item.isEnabled(), name
        # Scroll a target into its own Flickable, never click a clipped control.
        parent = item.parentItem()
        while parent:
            if parent.metaObject().indexOfProperty('contentY') >= 0:
                point = item.mapToItem(parent, QPointF(item.width() / 2, item.height() / 2))
                if point.y() < 20 or point.y() > parent.height() - 20:
                    maximum = max(0, parent.property('contentHeight') - parent.height())
                    parent.setProperty('contentY', max(0, min(maximum, parent.property('contentY') + point.y() - parent.height() / 2)))
                    QTest.qWait(30)
                break
            parent = parent.parentItem()
        point = item.mapToScene(QPointF(item.width() * fraction, item.height() / 2))
        ratio = panel.devicePixelRatio()
        native = wintypes.POINT(round(point.x() * ratio), round(point.y() * ratio))
        assert user32.ClientToScreen(int(panel.winId()), ctypes.byref(native))
        return native

    def focus():
        panel.raise_(); panel.requestActivate()
        # This isolated test window must be above the coding application's overlay.
        user32.SetWindowPos(int(panel.winId()), -1, 0, 0, 0, 0, 0x0003)
        user32.SetForegroundWindow(int(panel.winId()))
        QTest.qWait(100)

    def click(name, fraction=0.5):
        nonlocal click_count
        focus()
        if not native_input:
            item = find_item(panel, name)
            # Also scroll into view using the existing position routine.
            position(name, fraction)
            point = item.mapToScene(QPointF(item.width() * fraction, item.height() / 2)).toPoint()
            QTest.mouseClick(panel, Qt.MouseButton.LeftButton, pos=point)
            click_count += 1
            QTest.qWait(80)
            return
        point = position(name, fraction)
        from PySide6.QtGui import QCursor
        report['last_target'] = {'name': name, 'point': [point.x, point.y], 'ratio': panel.devicePixelRatio(),
            'geometry': [panel.x(), panel.y(), panel.width(), panel.height()], 'visible': panel.isVisible(), 'active': panel.isActive(),
            'hwnd': int(panel.winId()), 'cover': user32.GetAncestor(user32.WindowFromPoint(point), 2)}
        report['last_target']['foreground_before'] = user32.GetForegroundWindow() == int(panel.winId())
        user32.SetCursorPos(point.x, point.y)
        current = wintypes.POINT()
        user32.GetCursorPos(ctypes.byref(current))
        report['last_target']['cursor_set'] = [current.x, current.y]
        QTest.qWait(25)
        assert user32.GetAncestor(user32.WindowFromPoint(point), 2) == int(panel.winId()), 'Another window covers the target; click cancelled'
        user32.SetCursorPos(point.x, point.y)
        user32.mouse_event(0x0002, 0, 0, 0, 0)
        QTest.qWait(50)
        report['last_target']['pressed'] = find_item(panel, name).property('pressed')
        user32.SetCursorPos(point.x, point.y)
        user32.mouse_event(0x0004, 0, 0, 0, 0)
        click_count += 1
        QTest.qWait(80)
        report['last_target']['cursor'] = [QCursor.pos().x(), QCursor.pos().y()]
        report['last_target']['draft'] = panel.bridge.state['elgin'].get('temperatureDraft')
        report['last_target']['visible_after_click'] = panel.isVisible()
        report['last_target']['foreground_after'] = user32.GetForegroundWindow() == int(panel.winId())

    def capture(page):
        panel.bridge.navigate(page)
        QTest.qWait(250)
        assert panel.grabWindow().save(str(output.with_name('quick-' + page + '-simulated.png')))

    def check_layout():
        button = find_item(panel, 'refreshButton')
        corner = button.mapToScene(QPointF(button.width(), button.height()))
        assert panel.height()-corner.y() >= 20 and panel.width()-corner.x() >= 20
        assert button.width() == button.height()
        center = button.mapToScene(QPointF(button.width()/2,button.height()/2))
        icon = find_item(panel, 'refreshButtonIcon')
        icon_center = icon.mapToScene(QPointF(icon.width()/2,icon.height()/2))
        assert abs(center.x()-icon_center.x()) <= .5 and abs(center.y()-icon_center.y()) <= .5
        for page in ('climate','light','switch','settings'):
            panel.bridge.navigate(page); QTest.qWait(30)
            scroll = find_item(panel,page+'Scroll')
            left = scroll.mapToScene(QPointF(scroll.property('leftPadding'),0)).x()
            right = left+scroll.property('availableWidth')
            nav_left = find_item(panel,'nav_climate').mapToScene(QPointF(0,0)).x()
            nav = find_item(panel,'nav_switch')
            nav_right = nav.mapToScene(QPointF(nav.width(),0)).x()
            assert abs(left-nav_left) <= .5 and abs(right-nav_right) <= .5
            bar = find_item(panel,page+'ScrollBar')
            assert right+8 <= bar.mapToScene(QPointF(0,0)).x()
            assert scroll.mapToScene(QPointF(0,scroll.height())).y()+8 <= center.y()-button.height()/2
        panel.bridge.navigate('climate'); QTest.qWait(30)

    try:
        heartbeat.start()
        controller.start()
        wait(lambda: not controller.busy)
        panel.show_at_tray(QRect(1350, 1000, 20, 20))
        panel.animation.stop(); panel.setOpacity(1)
        QTest.qWait(200)
        assert not commands
        report['checks']['startup_reads_only'] = True
        check_layout()
        original_size = panel.size()
        panel.resize(480,620); QTest.qWait(50); check_layout()
        panel.resize(original_size); QTest.qWait(50)
        report['checks']['normal_and_compact_layout_grid_reload_and_scroll_rail'] = True
        # Desktop activation and focus loss must never hide the main window.
        other_window.show()
        other_window.raise_(); other_window.requestActivate()
        user32.SetWindowPos(int(other_window.winId()), -1, 0, 0, 0, 0, 0x0003)
        user32.SetForegroundWindow(int(other_window.winId()))
        target = wintypes.POINT(140, 180)
        assert user32.GetAncestor(user32.WindowFromPoint(target), 2) == int(other_window.winId())
        user32.SetCursorPos(target.x, target.y)
        QTest.qWait(40)
        user32.mouse_event(0x0002, 0, 0, 0, 0); QTest.qWait(50)
        user32.SetCursorPos(target.x, target.y)
        user32.mouse_event(0x0004, 0, 0, 0, 0); QTest.qWait(100)
        assert panel.isVisible() and not panel.isActive()
        report['checks']['deactivation_keeps_main_window_visible'] = True
        report['checks']['native_click_in_other_window_keeps_main_window_visible'] = True
        other_window.hide()
        # Separate unrelated native clicks beyond Windows' double-click interval.
        QTest.qWait(user32.GetDoubleClickTime() + 30)
        identity, chosen = panel.winId(), panel.position()
        for name in ('minimizeButton', 'hideButton') * 2:
            click(name)
            assert not panel.isVisible() and controller.timer.isActive()
            tray_app.tray.activated.emit(QSystemTrayIcon.ActivationReason.Trigger)
            panel.animation.stop(); panel.setOpacity(1)
            assert panel.isVisible() and panel.winId() == identity and panel.position() == chosen
        tray_app.tray.activated.emit(QSystemTrayIcon.ActivationReason.Trigger)
        assert panel.isVisible() and panel.winId() == identity and not commands
        report['checks']['explicit_minimize_x_and_tray_restore_reuse_same_window'] = True
        click('minimizeButton')
        reads = adapters['elgin'].read.call_count
        controller.timer.setInterval(60)
        wait(lambda: adapters['elgin'].read.call_count > reads and not controller.busy)
        controller.timer.setInterval(15000)
        assert not panel.isVisible() and not commands
        tray_app.show(); panel.animation.stop(); panel.setOpacity(1)
        report['checks']['hidden_window_keeps_lan_polling_without_writes'] = True
        click('temperaturePlus')
        wait(lambda: len(commands) == 1 and not controller.writing)
        assert commands[-1]['command'] == {'2': 250}
        click('fanTile'); click('choice_mid')
        wait(lambda: not controller.writing)
        assert commands[-1]['command'] == {'5': 'mid'}
        report['checks']['validated_temperature_and_mid_clicks'] = True
        click('settingsButton')
        click('riskAcknowledgement', 0.07)
        click('experimentalToggle')
        assert settings.enabled and len(commands) == 2
        report['checks']['persistent_enable_is_local_and_has_no_device_writes'] = True
        click('nav_light')
        click('palette_00f003e803e8')
        wait(lambda: not controller.writing and not controller.colour_sequence)
        assert [c['command'] for c in commands[-2:]] == [{'21': 'colour'}, {'24': '00f003e803e8'}]
        assert panel.bridge.state['led']['colourHex'] == '#0000ff'
        report['checks']['colour_click_sequences_known_mode_then_colour_without_dialogs'] = True
        previous = len(commands)
        click('brightnessSlider', 0.4)
        wait(lambda: len(commands) > previous and not controller.writing)
        assert len(commands) == previous + 1 and set(commands[-1]['command']) == {'24'}
        report['checks']['brightness_debounce_one_write'] = True
        if not native_input:
            from .led_research import hsv16_encode
            def drag_colour(name, start, end, expected):
                focus(); position(name)
                item = find_item(panel, name)
                a = item.mapToScene(QPointF(*start)).toPoint()
                b = item.mapToScene(QPointF(*end)).toPoint()
                count = len(commands)
                QTest.mousePress(panel, Qt.MouseButton.LeftButton, pos=a)
                for step in range(1, 9):
                    QTest.mouseMove(panel, a + (b-a)*step/8)
                    QTest.qWait(20)
                    assert len(commands) == count
                QTest.mouseRelease(panel, Qt.MouseButton.LeftButton, pos=b)
                wait(lambda: len(commands) == count+1 and not controller.writing)
                assert commands[-1]['command'] == {'24': expected}
                assert find_item(panel, 'ledIllustration').property('confirmedColour').name() == panel.bridge.state['led']['colourHex']
            v = panel.bridge.state['led']['hsv']['v']
            drag_colour('hueTouch', (112,16), (208,112), hsv16_encode(90,1000,v))
            drag_colour('squareTouch', (108,10), (59,59), hsv16_encode(90,500,500))
            report['checks']['hsv_wheel_and_square_drag_commit_once_and_update_confirmed_wall'] = True
            report['qt_colour_drags'] = 2
        capture('light')
        assert find_item(panel, 'lightTab_scenes') is None
        assert find_item(panel, 'sceneDiscovery') is None
        assert find_item(panel, 'lightTab_colour') and find_item(panel, 'lightTab_favorites')
        report['checks']['only_functional_colour_and_favorites_tabs'] = True
        capture('switch')
        click('channelPower1')
        wait(lambda: not controller.writing)
        click('channelPower2')
        wait(lambda: not controller.writing)
        assert [c['command'] for c in commands[-2:]] == [{'1': False}, {'2': True}]
        report['checks']['independent_channel_cards'] = True
        capture('climate')
        before = panel.position()
        focus()
        start = position('dragHeader', 0.65)
        if native_input:
            user32.SetCursorPos(start.x, start.y)
            user32.mouse_event(0x0002, 0, 0, 0, 0)
            for step in range(1, 7):
                user32.SetCursorPos(start.x - step * 15, start.y - step * 10)
                QTest.qWait(25)
            user32.mouse_event(0x0004, 0, 0, 0, 0)
        else:
            header = find_item(panel, 'dragHeader')
            point = header.mapToScene(QPointF(130, 20)).toPoint()
            QTest.mousePress(panel, Qt.MouseButton.LeftButton, pos=point)
            QTest.mouseMove(panel, point + QPoint(-90, -60))
            QTest.mouseRelease(panel, Qt.MouseButton.LeftButton, pos=point)
        QTest.qWait(70)
        assert panel.position() != before and panel.desktop.position is not None
        chosen = panel.position()
        click('minimizeButton')
        assert not panel.isVisible()
        tray_app.tray.activated.emit(QSystemTrayIcon.ActivationReason.Trigger)
        panel.animation.stop(); panel.setOpacity(1)
        assert panel.position() == chosen
        report['checks']['header_drag_minimize_persists_and_restores'] = True
        panel.resize(480, 620)
        QTest.qWait(50)
        slider = find_item(panel, 'temperatureSlider')
        old_value, count = slider.property('value'), len(commands)
        focus()
        point = position('temperatureSlider')
        if native_input:
            user32.SetCursorPos(point.x, point.y)
            user32.mouse_event(0x0800, 0, 0, 0xFFFFFF88, 0)
        else:
            local = slider.mapToScene(QPointF(slider.width() / 2, slider.height() / 2))
            QApplication.sendEvent(panel, QWheelEvent(local, QPointF(panel.mapToGlobal(local.toPoint())),
                QPoint(), QPoint(0, -120), Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier,
                Qt.ScrollPhase.NoScrollPhase, False))
        QTest.qWait(500)
        assert slider.property('value') == old_value and len(commands) == count
        report['checks']['wheel_does_not_modify_temperature'] = True
        panel.resize(480, 850)
        panel.bridge.reduceMotion(True)
        assert not find_item(panel, 'splitIllustration').property('animate')
        panel.bridge.reduceMotion(False)
        panel.hide()
        assert not find_item(panel, 'splitIllustration').property('animate')
        panel.show_at_tray(QRect(1350, 1000, 20, 20)); panel.animation.stop(); panel.setOpacity(1)
        report['checks']['reduced_motion_and_hidden_panel_stop_air_animation'] = True
        def offline():
            time.sleep(1.5)
            return DeviceState('offline', {})
        adapters['elgin'].read.side_effect = offline
        tick_count = len(ticks)
        controller.refresh()
        wait(lambda: 'novadigital' not in controller.busy)
        click('nav_switch'); click('channelPower1')
        wait(lambda: not controller.writing)
        wait(lambda: not controller.busy)
        assert len(ticks) - tick_count > 20 and not panel.bridge.state['elgin']['temperatureEnabled']
        report['checks']['offline_lan_keeps_gui_and_other_device_responsive'] = True
        assert all(t != threading.get_ident() for t in threads)
        assert not warnings
        report['checks']['no_qml_warnings_and_workers_outside_gui_thread'] = True
        capture('settings')
        report['passed'] = True
    except Exception as error:
        report['passed'] = False
        report['failure_type'] = type(error).__name__
        trace = error.__traceback__
        report['failure_lines'] = []
        while trace:
            report['failure_lines'].append(trace.tb_lineno)
            trace = trace.tb_next
    finally:
        report.update(native_clicks=click_count if native_input else 0, qt_clicks=0 if native_input else click_count, heartbeat_ticks=len(ticks), mock_commands=commands, qml_warnings=warnings)
        controller.stop(); controller.pool.waitForDone(4000)
        tray_app.tray.hide(); tray_app.menu.hide(); other_window.hide()
        tray_app.tray.deleteLater(); tray_app.menu.deleteLater(); other_window.deleteLater()
        heartbeat.stop(); panel.hide()
        user32.SetCursorPos(original.x, original.y)
        output.write_text(json.dumps(report, indent=2), encoding='utf-8')
        panel.deleteLater(); app.processEvents(); temporary.cleanup()
    return 0 if report.get('passed') else 1
