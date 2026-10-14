"""Presentation preferences and screen-safe placement, separate from secrets."""
import json
import os
from pathlib import Path
from PySide6.QtCore import QPoint, QRect


class DesktopSettings:
    def __init__(self, directory=None):
        directory = Path(directory or Path(os.environ['LOCALAPPDATA']) / 'SmartTray')
        self.path = directory / 'desktop-settings.json'
        try:
            data = json.loads(self.path.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            data = {}
        if not isinstance(data, dict):
            data = {}
        point = data.get('position')
        self.position = tuple(point) if (isinstance(point, list) and len(point) == 2
            and all(type(n) is int and abs(n) <= 1_000_000 for n in point)) else None
        self.reduce_motion = data.get('reduce_motion') is True

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix('.tmp')
        temporary.write_text(json.dumps({'position': self.position,
            'reduce_motion': self.reduce_motion}, indent=2), encoding='utf-8')
        temporary.replace(self.path)

    def remember(self, position):
        if not isinstance(position, QPoint):
            raise TypeError('Screen position required')
        previous = self.position
        self.position = (position.x(), position.y())
        try:
            self.save()
        except OSError:
            self.position = previous
            raise

    def reset_position(self):
        previous = self.position
        self.position = None
        try:
            self.save()
        except OSError:
            self.position = previous
            raise


def window_geometry(screens, anchor, size, saved=None, margin=12):
    """Qt logical coordinates, including negative origins and removed monitors."""
    if not screens:
        raise ValueError('At least one available screen required')
    point = QPoint(*saved) if saved else anchor
    def distance(rect):
        x = min(max(point.x(), rect.left()), rect.right())
        y = min(max(point.y(), rect.top()), rect.bottom())
        return (x - point.x()) ** 2 + (y - point.y()) ** 2
    screen = min(screens, key=distance)
    width = max(1, min(size.width(), screen.width() - 2 * margin))
    height = max(1, min(size.height(), screen.height() - 2 * margin))
    x = point.x() if saved else anchor.x() - width + 24
    y = point.y() if saved else anchor.y() - height - margin
    x = max(screen.left() + margin, min(x, screen.right() - width - margin + 1))
    y = max(screen.top() + margin, min(y, screen.bottom() - height - margin + 1))
    return QRect(x, y, width, height)
