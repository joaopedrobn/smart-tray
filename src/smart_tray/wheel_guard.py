"""Wheel means scroll, never a device command, for all legacy Widgets tools."""
from PySide6.QtCore import QObject, QEvent, QPointF
from PySide6.QtGui import QWheelEvent
from PySide6.QtWidgets import QApplication, QWidget, QComboBox, QAbstractSlider, QAbstractSpinBox, QScrollArea


class WheelGuard(QObject):
    def eventFilter(self, receiver, event):
        if event.type() != QEvent.Type.Wheel or not isinstance(receiver, QWidget):
            return False
        widget, control = receiver, None
        scroll = None
        while widget:
            if isinstance(widget, (QComboBox, QAbstractSlider, QAbstractSpinBox)):
                control = widget
            if isinstance(widget, QScrollArea):
                scroll = widget
                break
            widget = widget.parentWidget()
        if control is None:
            return False
        if scroll:
            viewport = scroll.viewport()
            local = viewport.mapFromGlobal(event.globalPosition().toPoint())
            forwarded = QWheelEvent(QPointF(local), event.globalPosition(), event.pixelDelta(),
                event.angleDelta(), event.buttons(), event.modifiers(), event.phase(), event.inverted())
            QApplication.sendEvent(viewport, forwarded)
        event.accept()
        return True


def install_wheel_guard(app):
    if not hasattr(app, '_smart_tray_wheel_guard'):
        app._smart_tray_wheel_guard = WheelGuard(app)
        app.installEventFilter(app._smart_tray_wheel_guard)
