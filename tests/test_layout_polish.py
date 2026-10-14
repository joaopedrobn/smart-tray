"""Rendered geometry regressions, using only the isolated simulated transport."""
import pytest
from PySide6.QtCore import QPointF
from PySide6.QtTest import QTest
from test_quick_ui import quick, find


def bounds(item):
    a = item.mapToScene(QPointF(0, 0))
    b = item.mapToScene(QPointF(item.width(), item.height()))
    return a.x(), a.y(), b.x(), b.y()


@pytest.mark.parametrize('size', [(480,850), (480,620), (420,700)])
def test_reload_has_safe_margins_and_never_overlaps_scrolling(size, quick):
    panel, _, _, _, commands, _ = quick
    panel.resize(*size)
    QTest.qWait(60)
    button = find(panel, 'refreshButton')
    left, top, right, bottom = bounds(button)
    assert panel.height()-bottom >= 20
    assert panel.width()-right >= 20
    assert button.width() == button.height()
    for page in ('climate', 'light', 'switch', 'settings'):
        panel.bridge.navigate(page)
        QTest.qWait(30)
        scroll = find(panel, page+'Scroll')
        assert bounds(scroll)[3] + 8 <= top
    assert not commands


@pytest.mark.parametrize('page', ['climate', 'light', 'switch', 'settings'])
def test_navigation_and_content_share_the_same_horizontal_grid(page, quick):
    panel, _, _, _, commands, _ = quick
    panel.bridge.navigate(page)
    QTest.qWait(40)
    scroll = find(panel, page+'Scroll')
    left = scroll.mapToScene(QPointF(scroll.property('leftPadding'), 0)).x()
    right = left + scroll.property('availableWidth')
    assert left == pytest.approx(bounds(find(panel, 'nav_climate'))[0], abs=.5)
    assert right == pytest.approx(bounds(find(panel, 'nav_switch'))[2], abs=.5)
    assert (left+right)/2 == pytest.approx(panel.width()/2, abs=.5)
    assert not commands


def test_reload_icon_is_centered_inside_its_button_and_footer(quick):
    panel, _, _, _, commands, _ = quick
    button, icon = find(panel, 'refreshButton'), find(panel, 'refreshButtonIcon')
    a, b = bounds(button), bounds(icon)
    assert (a[0]+a[2])/2 == pytest.approx((b[0]+b[2])/2, abs=.5)
    assert (a[1]+a[3])/2 == pytest.approx((b[1]+b[3])/2, abs=.5)
    assert a[2] == pytest.approx(bounds(find(panel, 'appFooter'))[2], abs=.5)
    assert not commands


@pytest.mark.parametrize('page', ['climate', 'light', 'switch', 'settings'])
@pytest.mark.parametrize('size', [(480,850), (480,620), (420,700)])
def test_every_page_control_fits_the_grid_and_is_reachable_by_scrolling(page, size, quick):
    panel, _, _, _, commands, _ = quick
    panel.resize(*size)
    panel.bridge.navigate(page)
    QTest.qWait(60)
    scroll = find(panel, page+'Scroll')
    viewport = scroll.property('contentItem')
    content_left = scroll.mapToScene(QPointF(scroll.property('leftPadding'),0)).x()
    content_right = content_left + scroll.property('availableWidth')
    bar = bounds(find(panel, page+'ScrollBar'))
    assert content_right + 8 <= bar[0]
    assert bar[2] <= panel.width()-8
    assert scroll.property('contentWidth') == pytest.approx(scroll.property('availableWidth'))

    def controls(parent):
        for child in parent.childItems():
            if child.isVisible():
                if child.inherits('QQuickAbstractButton') or child.inherits('QQuickSlider'):
                    yield child
                yield from controls(child)
    targets = list(controls(scroll))
    assert targets
    for item in targets:
        a = bounds(item)
        assert a[0] >= content_left-.5, item.objectName()
        assert a[2] <= content_right+.5, item.objectName()
        center = item.mapToItem(viewport, QPointF(item.width()/2,item.height()/2)).y()
        maximum = max(0,viewport.property('contentHeight')-viewport.height())
        viewport.setProperty('contentY', max(0,min(maximum,
            viewport.property('contentY')+center-viewport.height()/2)))
        QTest.qWait(5)
        a, v = bounds(item), bounds(viewport)
        assert a[1] >= v[1]-.5, item.objectName()
        assert a[3] <= v[3]+.5, item.objectName()
    assert not commands


def test_light_preview_wheel_palette_and_tabs_are_centered_on_the_same_axis(quick):
    panel, _, _, _, commands, _ = quick
    panel.bridge.navigate('light')
    QTest.qWait(50)
    for name in ('ledCard','ledIllustration','lightTabs','colourWheel','colourPalette','brightnessSlider'):
        a = bounds(find(panel,name))
        assert (a[0]+a[2])/2 == pytest.approx(panel.width()/2, abs=.5), name
    assert not commands


@pytest.mark.parametrize('card,content,page', [('climateCard','climateContent','climate'),('ledCard','ledContent','light')])
def test_main_cards_have_equal_inner_padding(card, content, page, quick):
    panel, _, _, _, commands, _ = quick
    panel.bridge.navigate(page)
    QTest.qWait(40)
    a, b = bounds(find(panel,card)), bounds(find(panel,content))
    padding = b[0]-a[0]
    assert padding >= 18
    assert a[2]-b[2] == pytest.approx(padding,abs=.5)
    assert b[1]-a[1] == pytest.approx(padding,abs=.5)
    assert a[3]-b[3] == pytest.approx(padding,abs=.5)
    assert not commands


def test_air_illustration_and_header_controls_fit_their_reserved_rows(quick):
    panel, _, _, _, commands, _ = quick
    header = bounds(find(panel,'mainHeader'))
    for name in ('settingsButton','minimizeButton','hideButton'):
        a, icon = bounds(find(panel,name)), bounds(find(panel,name+'Icon'))
        assert a[1] >= header[1] and a[3] <= header[3]
        assert a[2] <= header[2]
        assert (a[1]+a[3])/2 == pytest.approx((header[1]+header[3])/2,abs=.5)
        assert (a[0]+a[2])/2 == pytest.approx((icon[0]+icon[2])/2,abs=.5)
    model, flow = bounds(find(panel,'splitIllustration')), bounds(find(panel,'airflow'))
    assert flow[1] >= model[1] and flow[3] <= model[3]
    assert model[0] <= flow[0] < flow[2] <= model[2]
    assert not commands
