"""Visual projections use confirmed mocked state, never credentials or LAN."""
from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import QColor, QWheelEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
import pytest
from smart_tray.adapters import DeviceState
from test_quick_ui import quick, find, click


def publish(controller, values, role):
    controller.states[role] = DeviceState('online', values[role].copy())
    controller.changed.emit()


def test_plate_projects_touch_and_brazilian_socket_independently(quick, qt_app):
    panel, controller, _, values, commands, _ = quick
    click(panel, 'nav_switch')
    model = find(panel, 'switchIllustration')
    assert model.property('touchKnown') and model.property('socketKnown')
    assert model.property('touchOn') and not model.property('socketOn')
    values['novadigital'].update({1: False, 2: True})
    publish(controller, values, 'novadigital')
    assert not model.property('touchOn') and model.property('socketOn')
    assert not commands


def test_offline_plate_never_displays_stale_channel_states(quick):
    panel, controller, _, _, commands, _ = quick
    controller.states['novadigital'] = DeviceState('offline', {1: True, 2: True})
    controller.changed.emit()
    model = find(panel, 'switchIllustration')
    assert not model.property('touchKnown') and not model.property('socketKnown')
    assert not model.property('touchOn') and not model.property('socketOn')
    assert not commands


def test_confirmed_colour_and_brightness_drive_led_model(quick):
    panel, controller, _, values, commands, _ = quick
    values['led'].update(mode='colour', colour='007803e80190', brightness=40)
    publish(controller, values, 'led')
    model = find(panel, 'ledIllustration')
    assert model.property('fixedColourVisible')
    assert model.property('confirmedColour') == QColor('#006600')
    assert model.property('lightLevel') == pytest.approx(.4)
    # Showing or switching tabs never turns a confirmed read into a command.
    click(panel, 'nav_light'); click(panel, 'lightTab_favorites')
    assert not commands


@pytest.mark.parametrize('kind', ['off', 'offline', 'scene', 'music', 'unknown_colour', 'unknown_power'])
def test_led_model_never_invents_a_colour_or_effect(kind, quick):
    panel, controller, _, values, commands, _ = quick
    values['led'].update(mode='colour', colour='00f003e803e8')
    if kind == 'off': values['led'][20] = False
    elif kind in ('scene', 'music'): values['led']['mode'] = kind
    elif kind == 'unknown_colour': values['led']['colour'] = None
    elif kind == 'unknown_power': values['led'][20] = None
    publish(controller, values, 'led')
    if kind == 'offline':
        controller.states['led'] = DeviceState('offline', values['led'].copy())
        controller.changed.emit()
    model = find(panel, 'ledIllustration')
    assert not model.property('fixedColourVisible')
    assert model.property('lightLevel') == 0
    assert not commands


def test_airflow_finishes_power_off_fade_and_stops_when_hidden(quick):
    panel, controller, _, values, commands, _ = quick
    split, air = find(panel, 'splitIllustration'), find(panel, 'airflow')
    assert split.property('flowRunning')
    values['elgin']['power'] = False
    publish(controller, values, 'elgin')
    assert not split.property('powered') and split.property('flowRunning')
    QTest.qWait(720)
    assert air.opacity() == 0 and not split.property('flowRunning')
    values['elgin']['power'] = True
    publish(controller, values, 'elgin')
    panel.hide()
    assert not split.property('flowRunning') and not commands


def test_reduced_motion_has_static_airflow_without_animation_clock(quick):
    panel, _, _, _, commands, _ = quick
    panel.bridge.reduceMotion(True)
    split = find(panel, 'splitIllustration')
    assert split.property('powered') and not split.property('flowRunning')
    assert not commands


@pytest.mark.parametrize('page,scroll_name', [('climate','climateScroll'),('light','lightScroll'),('switch','switchScroll'),('settings','settingsScroll')])
def test_every_scrollbar_has_its_own_gutter(page, scroll_name, quick):
    panel, _, _, _, commands, _ = quick
    panel.bridge.navigate(page)
    QTest.qWait(50)
    scroll, bar = find(panel, scroll_name), find(panel, scroll_name+'Bar')
    assert scroll.property('rightPadding') >= 12
    # Both positions are measured in the same scene, not unrelated local coords.
    content_right = scroll.mapToScene(QPointF(scroll.property('leftPadding') + scroll.property('availableWidth'), 0)).x()
    bar_left = bar.mapToScene(QPointF(0,0)).x()
    assert bar_left - content_right >= 5
    assert not commands


def test_temperature_readout_follows_drag_before_any_mocked_write(quick, qt_app):
    panel, controller, _, _, commands, _ = quick
    slider = find(panel, 'temperatureSlider')
    point = slider.mapToScene(QPointF(slider.width()*.8, slider.height()/2)).toPoint()
    QTest.mousePress(panel, Qt.MouseButton.LeftButton, pos=point)
    assert find(panel, 'temperatureReadout').property('text') == str(round(slider.property('value')))
    assert not commands
    QTest.mouseRelease(panel, Qt.MouseButton.LeftButton, pos=point)


def test_model_channel_controls_keep_original_dps_mapping(quick, qt_app):
    from test_interface import wait_until
    panel, controller, _, _, commands, _ = quick
    click(panel, 'nav_switch')
    click(panel, 'channelPower1')
    wait_until(qt_app, lambda: len(commands) == 1 and not controller.writing)
    click(panel, 'channelPower2')
    wait_until(qt_app, lambda: len(commands) == 2 and not controller.writing)
    assert commands == [{'role':'novadigital','command':{'1':False}}, {'role':'novadigital','command':{'2':True}}]


def test_wall_preview_repaints_colour_from_confirmed_state_without_writes(quick):
    panel, controller, _, values, commands, _ = quick
    panel.bridge.reduceMotion(True)
    values['led'].update(mode='colour', colour='00f003e803e8', brightness=100)
    publish(controller, values, 'led')
    click(panel, 'nav_light')
    QTest.qWait(100)
    before = panel.grabWindow()
    # Power, brightness, status and text stay identical; only confirmed hue changes.
    values['led']['colour'] = '000003e803e8'
    publish(controller, values, 'led')
    QTest.qWait(100)
    after = panel.grabWindow()
    model = find(panel, 'ledIllustration')
    origin = model.mapToScene(QPointF(0, 0)).toPoint()
    region = (origin.x(), origin.y(), round(model.width()), round(model.height())-24)
    assert before.copy(*region) != after.copy(*region)
    assert not commands


def test_scroll_over_brightness_only_moves_the_light_page(quick):
    panel, controller, _, values, commands, _ = quick
    values['led'].update(mode='colour', colour='007803e803e8', brightness=100)
    publish(controller, values, 'led')
    click(panel, 'nav_light')
    scroll = find(panel, 'lightScroll').property('contentItem')
    maximum = scroll.property('contentHeight') - scroll.height()
    assert maximum > 0  # The larger wall model must remain reachable by scrolling.
    scroll.setProperty('contentY', maximum * .75)
    QTest.qWait(40)
    slider = find(panel, 'brightnessSlider')
    local = slider.mapToScene(QPointF(slider.width()/2, slider.height()/2))
    assert 134 < local.y() < panel.height()-54
    before = slider.property('value')
    content_y = scroll.property('contentY')
    QApplication.sendEvent(panel, QWheelEvent(local, QPointF(panel.mapToGlobal(local.toPoint())),
        QPoint(), QPoint(0,-120), Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier,
        Qt.ScrollPhase.NoScrollPhase, False))
    QTest.qWait(450)
    assert slider.property('value') == before and not commands
    assert scroll.property('contentY') > content_y
