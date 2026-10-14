"""Drag/restore behavior shared by Widgets and the future Quick window."""
from PySide6.QtCore import QObject, QEvent, QPoint, QSize, Qt, Slot, Signal
from PySide6.QtGui import QGuiApplication
from .desktop_state import window_geometry


class WindowPlacement(QObject):
    save_failed = Signal()

    def __init__(self, window, settings, size, screen_provider=None):
        super().__init__(window)
        self.window, self.settings, self.size = window, settings, size
        self.screen_provider = screen_provider or (lambda: [s.availableGeometry() for s in QGuiApplication.screens()])
        self.anchor = QPoint()
        self.drag_origin = self.window_origin = None
        self.header = None

    def place(self, anchor):
        self.anchor = anchor
        rect = window_geometry(self.screen_provider(), anchor, self.size, self.settings.position)
        self.window.setGeometry(rect)
        return rect

    def attach_header(self, header):
        if self.header:
            self.header.removeEventFilter(self)
        self.header = header
        header.installEventFilter(self)

    @Slot(int, int)
    def begin_drag(self, global_x, global_y):
        self.drag_origin = QPoint(global_x, global_y)
        self.window_origin = self.window.geometry().topLeft()

    @Slot(int, int)
    def move_drag(self, global_x, global_y):
        if self.drag_origin is None:
            return
        point = self.window_origin + QPoint(global_x, global_y) - self.drag_origin
        rect = window_geometry(self.screen_provider(), point, self.window.size(), (point.x(), point.y()))
        self.window.setGeometry(rect)

    @Slot()
    def end_drag(self):
        if self.drag_origin is None:
            return
        self.drag_origin = self.window_origin = None
        point = self.window.geometry().topLeft()
        try:
            self.settings.remember(point)
        except OSError:
            self.save_failed.emit()

    @Slot()
    def reset(self):
        try:
            self.settings.reset_position()
        except OSError:
            self.save_failed.emit()
            return
        self.place(self.anchor)

    def eventFilter(self, receiver, event):
        if receiver is not getattr(self, 'header', None):
            return False
        if event.type() == QEvent.Type.MouseButtonPress and event.button() == Qt.MouseButton.LeftButton:
            point = event.globalPosition().toPoint()
            self.begin_drag(point.x(), point.y())
            return True
        if event.type() == QEvent.Type.MouseMove and self.drag_origin is not None:
            point = event.globalPosition().toPoint()
            self.move_drag(point.x(), point.y())
            return True
        if event.type() == QEvent.Type.MouseButtonRelease and self.drag_origin is not None:
            self.end_drag()
            return True
        return False
