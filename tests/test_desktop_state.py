import json
import pytest
from PySide6.QtCore import QPoint, QRect, QSize
from smart_tray.desktop_state import DesktopSettings, window_geometry


def test_saved_position_and_motion_reload_without_other_settings(tmp_path):
    settings = DesktopSettings(tmp_path)
    assert settings.position is None and settings.reduce_motion is False
    settings.reduce_motion = True
    settings.remember(QPoint(-1100, 80))
    loaded = DesktopSettings(tmp_path)
    assert loaded.position == (-1100, 80) and loaded.reduce_motion
    assert set(json.loads(settings.path.read_text())) == {'position', 'reduce_motion'}
    loaded.reset_position()
    assert DesktopSettings(tmp_path).position is None


@pytest.mark.parametrize('data', ['broken', '[]', '{"position":[true,1]}', '{"position":[99999999,0]}'])
def test_bad_presentation_settings_fall_back(tmp_path, data):
    (tmp_path / 'desktop-settings.json').write_text(data)
    assert DesktopSettings(tmp_path).position is None


def test_initial_placement_near_tray_then_saved_position_wins():
    screens = [QRect(0, 0, 1920, 1040), QRect(-1280, 0, 1280, 984)]
    initial = window_geometry(screens, QPoint(1900, 1030), QSize(500, 800))
    assert screens[0].contains(initial) and initial.x() > 1300
    moved = window_geometry(screens, QPoint(1900, 1030), QSize(500, 800), (-1100, 70))
    assert moved.topLeft() == QPoint(-1100, 70) and screens[1].contains(moved)


def test_removed_monitor_and_tiny_available_screen_are_clamped():
    available = QRect(0, 0, 800, 600)
    rect = window_geometry([available], QPoint(790, 590), QSize(500, 900), (-2000, 200))
    assert available.contains(rect) and rect.height() == 576


def test_position_write_failure_preserves_prior_setting(tmp_path, monkeypatch):
    settings = DesktopSettings(tmp_path)
    settings.remember(QPoint(20, 20))
    def failed():
        raise OSError('synthetic write error')
    monkeypatch.setattr(settings, 'save', failed)
    with pytest.raises(OSError):
        settings.remember(QPoint(40, 40))
    assert settings.position == (20, 20)
    with pytest.raises(OSError):
        settings.reset_position()
    assert settings.position == (20, 20)
