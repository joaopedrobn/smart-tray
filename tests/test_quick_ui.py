from pathlib import Path
import threading
import pytest
from PySide6.QtCore import Qt, QObject, QPoint, QPointF, QRect, QEvent
from PySide6.QtGui import QWheelEvent, QWindow, QFocusEvent
from PySide6.QtQuick import QQuickWindow, QSGRendererInterface
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from smart_tray.beta import BetaSettings
from smart_tray.desktop_state import DesktopSettings
from smart_tray.direct_controller import DirectController
from smart_tray.quick_panel import QuickPanel
from smart_tray.quick_test_support import simulation, find_item
from smart_tray.adapters import DeviceState
from test_interface import wait_until

QQuickWindow.setGraphicsApi(QSGRendererInterface.GraphicsApi.Software)
ROOT = Path(__file__).parent / "fixtures/config"


def find(panel, name):
    item = find_item(panel, name)
    assert item is not None, name
    return item


def click(panel, name, fraction=0.5):
    # Popup/repeater layouts are polished on the next Qt event-loop turn.
    QTest.qWait(30)
    item = find(panel, name)
    parent = item.parentItem()
    while parent:
        if parent.metaObject().indexOfProperty('contentY') >= 0:
            point = item.mapToItem(parent, QPointF(item.width() / 2, item.height() / 2))
            if point.y() < 20 or point.y() > parent.height() - 20:
                maximum = max(0, parent.property('contentHeight') - parent.height())
                parent.setProperty('contentY', max(0, min(maximum,
                    parent.property('contentY') + point.y() - parent.height() / 2)))
                QTest.qWait(30)
            break
        parent = parent.parentItem()
    point = item.mapToScene(QPointF(item.width() * fraction, item.height() / 2)).toPoint()
    QTest.mouseClick(panel, Qt.MouseButton.LeftButton, pos=point)


@pytest.fixture
def quick(qt_app, tmp_path):
    adapters, values, commands, threads = simulation(ROOT)
    settings = BetaSettings(tmp_path)
    settings.enabled = True
    controller = DirectController(adapters, settings)
    controller.start()
    wait_until(qt_app, lambda: not controller.busy)
    panel = QuickPanel(controller, ROOT, DesktopSettings(tmp_path))
    errors = []
    panel.engine().warnings.connect(lambda items: errors.extend(e.description() for e in items))
    panel.show()
    QTest.qWait(60)
    yield panel, controller, adapters, values, commands, threads
    controller.stop()
    controller.pool.waitForDone(3000)
    qt_app.processEvents()
    panel.hide()
    panel.deleteLater()
    qt_app.processEvents()
    for adapter in adapters.values():
        base = getattr(adapter, 'base', adapter)
        base.store.load.assert_not_called()
        base.factory.assert_not_called()
    assert not errors


def test_qml_loads_and_startup_never_writes(quick):
    panel, controller, _, _, commands, _ = quick
    assert panel.rootObject() is not None and not panel.errors()
    assert not commands and panel.bridge.page == 'climate'
    assert find(panel, 'splitIllustration').property('powered')
    assert find(panel, 'swingTile').property('enabled') is False


def test_temperature_plus_debounces_to_one_validated_write(quick, qt_app):
    panel, controller, adapters, _, commands, threads = quick
    click(panel, 'temperaturePlus')
    assert not commands and panel.bridge.state['elgin']['temperatureDraft'] == 25
    wait_until(qt_app, lambda: len(commands) == 1 and not controller.writing)
    assert commands[0]['command'] == {'2': 250}
    adapters['elgin'].execute.assert_called_once()
    assert all(t != threading.get_ident() for t in threads)
    assert QApplication.activeModalWidget() is None


def test_temperature_slider_releases_one_target_not_each_frame(quick, qt_app):
    panel, controller, _, _, commands, _ = quick
    item = find(panel, 'temperatureSlider')
    start = item.mapToScene(QPointF(item.width() / 2, item.height() / 2)).toPoint()
    end = item.mapToScene(QPointF(item.width() * 0.8, item.height() / 2)).toPoint()
    QTest.mousePress(panel, Qt.MouseButton.LeftButton, pos=start)
    QTest.mouseMove(panel, end)
    assert not commands
    QTest.mouseRelease(panel, Qt.MouseButton.LeftButton, pos=end)
    wait_until(qt_app, lambda: len(commands) == 1 and not controller.writing)
    assert set(commands[0]['command']) == {'2'}


def test_qml_wheel_never_changes_slider_or_sends_commands(quick, qt_app):
    panel, _, _, _, commands, _ = quick
    panel.resize(480, 620)
    QTest.qWait(40)
    item = find(panel, 'temperatureSlider')
    point = item.mapToScene(QPointF(item.width() / 2, item.height() / 2))
    before = item.property('value')
    event = QWheelEvent(point, QPointF(panel.mapToGlobal(point.toPoint())), QPoint(), QPoint(0, -120),
        Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier, Qt.ScrollPhase.NoScrollPhase, False)
    QApplication.sendEvent(panel, event)
    QTest.qWait(450)
    assert item.property('value') == before and not commands
    scroll = find(panel, 'climateScroll')
    assert scroll.property('contentItem').property('contentY') > 0


def test_palette_click_from_scene_is_consistent_and_has_no_prompt(quick, qt_app):
    panel, controller, _, _, commands, _ = quick
    click(panel, 'nav_light')
    click(panel, 'palette_00f003e803e8')
    wait_until(qt_app, lambda: len(commands) == 2 and not controller.writing and not controller.colour_sequence)
    assert [c['command'] for c in commands] == [{'21': 'colour'}, {'24': '00f003e803e8'}]
    assert panel.bridge.state['led']['colourHex'] == '#0000ff'
    assert QApplication.activeModalWidget() is None


def test_brightness_uses_debounce_and_preserves_hs(quick, qt_app):
    panel, controller, _, values, commands, _ = quick
    values['led']['mode'] = 'colour'
    values['led']['colour'] = '007803e803e8'
    controller.states['led'] = DeviceState('online', values['led'].copy())
    controller.changed.emit()
    panel.bridge.scheduleBrightness(40)
    panel.bridge.scheduleBrightness(30)
    assert not commands
    wait_until(qt_app, lambda: len(commands) == 1 and not controller.writing)
    assert commands[0]['command'] == {'24': '007803e8012c'}


def test_validated_fan_choice_is_explicit_and_refresh_does_not_select(quick, qt_app):
    panel, controller, _, _, commands, _ = quick
    click(panel, 'fanTile')
    controller.changed.emit()
    assert not commands
    click(panel, 'choice_mid')
    wait_until(qt_app, lambda: len(commands) == 1 and not controller.writing)
    assert commands[0]['command'] == {'5': 'mid'}


def test_two_channel_cards_send_only_the_selected_channel(quick, qt_app):
    panel, controller, _, _, commands, _ = quick
    click(panel, 'nav_switch')
    click(panel, 'channelPower2')
    wait_until(qt_app, lambda: len(commands) == 1 and not controller.writing)
    assert commands[0] == {'role': 'novadigital', 'command': {'2': True}}
    assert controller.states['novadigital'].values[1] is True


def test_offline_state_disables_actions_and_airflow(quick, qt_app):
    panel, controller, _, _, commands, _ = quick
    controller.states['elgin'] = DeviceState('offline', {})
    controller.changed.emit()
    assert not find(panel, 'splitIllustration').property('powered')
    assert not find(panel, 'temperatureSlider').property('enabled')
    click(panel, 'temperaturePlus')
    QTest.qWait(450)
    assert not commands


def test_hidden_panel_and_reduced_motion_stop_air_animation(quick, qt_app):
    panel, _, _, _, _, _ = quick
    split = find(panel, 'splitIllustration')
    assert split.property('animate')
    panel.hide()
    assert not split.property('animate')
    panel.show()
    panel.bridge.reduceMotion(True)
    assert not split.property('animate') and split.property('powered')


def test_settings_opt_in_persists_without_device_commands(quick, qt_app):
    panel, controller, _, _, commands, _ = quick
    controller.settings.enabled = False
    controller.changed.emit()
    click(panel, 'settingsButton')
    assert not find(panel, 'experimentalToggle').property('enabled')
    click(panel, 'riskAcknowledgement')
    click(panel, 'experimentalToggle')
    assert controller.settings.enabled and BetaSettings(controller.settings.directory).enabled
    assert not commands


def test_drag_qml_header_saves_restores_and_does_not_control_devices(quick, qt_app):
    panel, _, _, _, commands, _ = quick
    panel.show_at_tray(QRect(1100, 1000, 20, 20))
    panel.animation.stop(); panel.setOpacity(1)
    before = panel.position()
    item = find(panel, 'dragHeader')
    start = item.mapToScene(QPointF(130, 20)).toPoint()
    QTest.mousePress(panel, Qt.MouseButton.LeftButton, pos=start)
    QTest.mouseMove(panel, start + QPoint(-80, -60))
    QTest.mouseRelease(panel, Qt.MouseButton.LeftButton, pos=start)
    assert panel.position() != before
    moved = panel.position()
    panel.hide(); panel.show_at_tray(QRect(1100, 1000, 20, 20))
    assert panel.position() == moved and not commands


def test_unmapped_effects_are_informational_not_simulated_controls(quick):
    panel, _, _, _, commands, _ = quick
    click(panel, 'nav_light')
    assert find_item(panel, 'lightTab_scenes') is None
    assert find_item(panel, 'sceneDiscovery') is None
    assert find(panel, 'lightTab_colour').property('text') == 'Cores'
    assert find(panel, 'lightTab_favorites').property('text') == 'Favoritas'
    assert find(panel, 'ledPowerStatus').property('text') in ('Ligada', 'Desligada')
    assert find(panel, 'ledPreviewStatus').property('text') == 'Efeito ativo no aparelho · prévia indisponível'
    assert not commands
    assert panel.bridge.page == 'light'


def test_slow_lan_leaves_navigation_and_other_devices_responsive(quick, qt_app):
    panel, controller, adapters, _, commands, _ = quick
    gate = threading.Event()
    def delayed():
        gate.wait(2)
        return DeviceState('offline', {})
    adapters['elgin'].read.side_effect = delayed
    controller.refresh()
    wait_until(qt_app, lambda: 'led' not in controller.busy and 'novadigital' not in controller.busy)
    click(panel, 'nav_switch')
    click(panel, 'channelPower1')
    wait_until(qt_app, lambda: not controller.writing)
    assert 'elgin' in controller.busy and panel.bridge.page == 'switch'
    assert commands[-1]['command'] == {'1': False}
    gate.set()
    wait_until(qt_app, lambda: not controller.busy)


def test_failed_temperature_clears_draft_and_never_repeats_write(quick, qt_app):
    panel, controller, adapters, _, commands, _ = quick
    adapters['elgin'].execute.side_effect = TimeoutError
    click(panel, 'temperaturePlus')
    wait_until(qt_app, lambda: adapters['elgin'].execute.call_count == 1 and not controller.writing)
    QTest.qWait(450)
    assert adapters['elgin'].execute.call_count == 1 and not commands
    assert not panel.bridge.state['elgin']['temperatureEnabled']
    assert panel.bridge.state['elgin']['temperatureDraft'] is None


def test_favorite_persists_confirmed_colour_without_device_write(quick):
    panel, controller, _, values, commands, _ = quick
    values['led']['mode'] = 'colour'
    values['led']['colour'] = '007803e80258'
    controller.states['led'] = DeviceState('online', values['led'].copy())
    controller.changed.emit()
    panel.bridge.favorite()
    assert BetaSettings(controller.settings.directory).favorites == ['007803e80258']
    assert panel.bridge.favorites[0]['value'] == '007803e80258'
    assert not commands


def test_favorite_tab_applies_saved_colour_with_mock_transport(quick, qt_app):
    panel, controller, _, values, commands, _ = quick
    controller.settings.favorites = ['007803e80258']
    values['led']['mode'] = 'colour'
    controller.states['led'] = DeviceState('online', values['led'].copy())
    controller.changed.emit()
    click(panel, 'nav_light')
    click(panel, 'lightTab_favorites')
    click(panel, 'favorite_007803e80258')
    wait_until(qt_app, lambda: not controller.writing and not controller.busy)
    assert commands[-1]['command'] == {'24': '007803e80258'}


def test_deactivation_and_focus_loss_do_not_hide_main_window(quick, qt_app):
    panel, _, _, _, commands, _ = quick
    assert panel.flags() & Qt.WindowType.WindowType_Mask == Qt.WindowType.Window
    QApplication.sendEvent(panel, QEvent(QEvent.Type.WindowDeactivate))
    QApplication.sendEvent(panel, QFocusEvent(QEvent.Type.FocusOut))
    QTest.qWait(100)
    assert panel.isVisible() and not commands


def test_another_window_can_take_focus_without_hiding_panel(quick, qt_app):
    panel, _, _, _, commands, _ = quick
    other = QWindow()
    other.resize(120, 100)
    try:
        other.show(); other.raise_(); other.requestActivate()
        QTest.qWait(100)
        assert panel.isVisible() and not commands
    finally:
        other.hide(); other.destroy()


def test_minimize_and_x_hide_to_tray_and_restore_same_window_position(quick):
    panel, _, _, _, commands, _ = quick
    rect = QRect(1100, 1000, 20, 20)
    panel.show_at_tray(rect)
    panel.animation.stop(); panel.setOpacity(1)
    panel.placement.begin_drag(100, 100)
    panel.placement.move_drag(30, 50)
    panel.placement.end_drag()
    moved, identity = panel.position(), panel.winId()
    for button in ('minimizeButton', 'hideButton') * 3:
        click(panel, button)
        assert not panel.isVisible() and not panel.bridge.panelVisible
        panel.show_at_tray(rect)
        panel.animation.stop(); panel.setOpacity(1)
        assert panel.isVisible() and panel.position() == moved and panel.winId() == identity
    panel.close()
    assert not panel.isVisible() and not commands


def test_hidden_window_keeps_polling_and_updates_lan_state(quick, qt_app):
    panel, controller, adapters, values, commands, _ = quick
    reads = adapters['elgin'].read.call_count
    panel.bridge.minimize()
    values['elgin']['temperature'] = 26
    controller.timer.setInterval(40)
    wait_until(qt_app, lambda: adapters['elgin'].read.call_count > reads and
        controller.states['elgin'].values.get('temperature') == 26)
    controller.timer.setInterval(15000)
    assert not panel.isVisible() and controller.timer.isActive() and not commands


def test_raising_visible_panel_does_not_reset_geometry_or_restart_animation(quick):
    panel, _, _, _, commands, _ = quick
    panel.show_at_tray(QRect(1100, 1000, 20, 20))
    panel.animation.stop(); panel.setOpacity(1)
    panel.setPosition(panel.position() + QPoint(-40, 0))
    geometry = panel.geometry()
    panel.show_at_tray(QRect(0, 0, 20, 20))
    assert panel.geometry() == geometry and panel.opacity() == 1 and not commands
