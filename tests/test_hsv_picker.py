"""End-to-end QML pointer input -> HSV16 -> mocked adapter -> confirmed preview."""
from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor
from PySide6.QtTest import QTest
import pytest
import threading
from smart_tray.adapters import DeviceState
from test_quick_ui import quick, find, click
from test_interface import wait_until


def colour_mode(quick, colour='000003e803e8'):
    panel, controller, _, values, _, _ = quick
    values['led'].update(mode='colour', colour=colour)
    controller.states['led'] = DeviceState('online', values['led'].copy())
    controller.changed.emit()
    click(panel, 'nav_light')
    # StackLayout polishes the newly visible page on the next event-loop turn.
    QTest.qWait(40)
    return panel, controller


def drag(panel, item, start, end):
    QTest.qWait(40)
    a = item.mapToScene(QPointF(*start)).toPoint()
    b = item.mapToScene(QPointF(*end)).toPoint()
    QTest.mousePress(panel, Qt.MouseButton.LeftButton, pos=a)
    for step in range(1, 9):
        QTest.mouseMove(panel, a + (b-a)*step/8)
        QTest.qWait(20)
    QTest.mouseRelease(panel, Qt.MouseButton.LeftButton, pos=b)


def test_hue_drag_commits_once_on_release(quick, qt_app):
    panel, controller = colour_mode(quick)
    commands = quick[4]
    wheel = find(panel, 'hueTouch')
    canceled = []
    wheel.canceled.connect(lambda: canceled.append(True))
    drag(panel, wheel, (112,16), (208,112))
    assert not canceled, 'The scrolling page stole the hue drag'
    wait_until(qt_app, lambda: len(commands)==1 and not controller.writing)
    assert commands[0]['command'] == {'24':'005a03e803e8'}


def test_sv_drag_commits_once_on_release(quick, qt_app):
    panel, controller = colour_mode(quick)
    commands = quick[4]
    square = find(panel, 'squareTouch')
    canceled = []
    square.canceled.connect(lambda: canceled.append(True))
    drag(panel, square, (108,10), (59,59))
    assert not canceled, 'The scrolling page stole the SV drag'
    wait_until(qt_app, lambda: len(commands)==1 and not controller.writing)
    assert commands[0]['command'] == {'24':'000001f401f4'}


def test_hue_selection_from_white_produces_a_visible_colour(quick, qt_app):
    panel, controller = colour_mode(quick, '0000000003e8')
    commands = quick[4]
    wheel = find(panel, 'hueTouch')
    point = wheel.mapToScene(QPointF(208,112)).toPoint()
    QTest.mouseClick(panel, Qt.MouseButton.LeftButton, pos=point)
    wait_until(qt_app, lambda: len(commands)==1 and not controller.writing)
    assert commands[0]['command'] == {'24':'005a03e803e8'}


def test_drag_does_not_write_or_repaint_confirmed_wall_until_readback(quick, qt_app):
    panel, controller = colour_mode(quick)
    adapters, commands = quick[2], quick[4]
    wall = find(panel, 'ledIllustration')
    wheel = find(panel, 'hueTouch')
    original_execute = adapters['led'].execute.side_effect
    release = threading.Event()
    def delayed(*args, **kwargs):
        assert release.wait(3)
        return original_execute(*args, **kwargs)
    adapters['led'].execute.side_effect = delayed
    a = wheel.mapToScene(QPointF(112,16)).toPoint()
    b = wheel.mapToScene(QPointF(208,112)).toPoint()
    try:
        QTest.mousePress(panel, Qt.MouseButton.LeftButton, pos=a)
        QTest.mouseMove(panel, b)
        # A background state notification must not reset the user's draft.
        controller.changed.emit()
        QTest.qWait(50)
        assert not commands and wall.property('confirmedColour') == QColor('#ff0000')
        QTest.mouseRelease(panel, Qt.MouseButton.LeftButton, pos=b)
        wait_until(qt_app, lambda: controller.writing)
        assert not commands and wall.property('confirmedColour') == QColor('#ff0000')
    finally:
        release.set()
    wait_until(qt_app, lambda: len(commands)==1 and not controller.writing)
    assert commands[0]['command'] == {'24':'005a03e803e8'}
    assert wall.property('confirmedColour') == QColor('#80ff00')


def test_hsv_selection_from_scene_confirms_mode_before_colour(quick, qt_app):
    panel, controller, _, _, commands, _ = quick
    click(panel, 'nav_light')
    drag(panel, find(panel, 'hueTouch'), (112,16), (208,112))
    wait_until(qt_app, lambda: len(commands)==2 and not controller.writing and not controller.colour_sequence)
    assert [c['command'] for c in commands] == [{'21':'colour'}, {'24':'005a03e803e8'}]


def test_hsv_timeout_never_retries_or_claims_a_confirmed_colour(quick, qt_app):
    panel, controller = colour_mode(quick)
    adapters = quick[2]
    adapters['led'].execute.side_effect = TimeoutError('simulated transport timeout')
    drag(panel, find(panel, 'hueTouch'), (112,16), (208,112))
    wait_until(qt_app, lambda: not controller.writing)
    QTest.qWait(450)
    adapters['led'].execute.assert_called_once()
    assert not find(panel, 'ledIllustration').property('fixedColourVisible')
    assert not quick[4]


@pytest.mark.parametrize('payload', ['000003e803e8','001e03e803e8','003c03e803e8',
    '007803e803e8','00b403e803e8','00f003e803e8','012c03e803e8','0000000003e8'])
def test_all_eight_palette_buttons_keep_their_exact_payload(payload, quick, qt_app):
    panel, controller, _, values, commands, _ = quick
    # Every target differs from the initial colour; otherwise the controller
    # correctly avoids a redundant colour write after confirming the mode.
    values['led'].update(colour='0000000001f4', brightness=50)
    controller.states['led'] = DeviceState('online', values['led'].copy())
    controller.changed.emit()
    click(panel, 'nav_light')
    click(panel, 'palette_'+payload)
    wait_until(qt_app, lambda: len(commands)==2 and not controller.writing and not controller.colour_sequence)
    assert [c['command'] for c in commands] == [{'21':'colour'}, {'24':payload}]
