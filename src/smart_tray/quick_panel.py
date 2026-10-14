"""Native Qt Quick window, tray compatible; no Widgets content or LAN here."""
from pathlib import Path
import sys
from PySide6.QtCore import Qt, QUrl, Signal, QEvent, QPropertyAnimation, QEasingCurve, QSize
from PySide6.QtGui import QColor, QCursor
from PySide6.QtQuick import QQuickView
from PySide6.QtQuickControls2 import QQuickStyle
from .desktop_state import DesktopSettings, window_geometry
from .quick_bridge import QuickBridge
from .window_placement import WindowPlacement
from .windows import show_interactive_window
from .beta import VERSION


class QuickPanel(QQuickView):
    preferences = Signal()

    def __init__(self, controller, root=None, desktop=None):
        if QQuickStyle.name() != 'Basic':
            QQuickStyle.setStyle('Basic')
        super().__init__()
        self.controller = controller
        self.menu_visible = False
        self._placed = False
        self.setFlags(Qt.WindowType.Window | Qt.WindowType.FramelessWindowHint)
        self.setColor(QColor('transparent'))
        self.setTitle('Smart Tray ' + VERSION)
        self.setResizeMode(QQuickView.ResizeMode.SizeRootObjectToView)
        self.resize(480, 850)
        self.desktop = desktop or DesktopSettings(controller.settings.directory)
        self.placement = WindowPlacement(self, self.desktop, QSize(480, 850))
        project = Path(root) if root else Path(__file__).resolve().parents[2]
        development_tools = not getattr(sys, 'frozen', False) or any(
            arg in sys.argv for arg in ('--interaction-smoke', '--qt-interaction-smoke'))
        self.bridge = QuickBridge(controller, self.desktop, project, self, development_tools=development_tools)
        self.bridge.dragStarted.connect(self.placement.begin_drag)
        self.bridge.dragMoved.connect(self.placement.move_drag)
        self.bridge.dragEnded.connect(self.placement.end_drag)
        self.bridge.hideRequested.connect(self.hide)
        self.bridge.minimizeRequested.connect(self.hide)
        self.bridge.resetRequested.connect(self.reset_position)
        self.placement.save_failed.connect(lambda: self.bridge.toast.emit('A posição não pôde ser salva.'))
        self.rootContext().setContextProperty('smart', self.bridge)
        qml = Path(__file__).parent / 'qml/Main.qml'
        self.setSource(QUrl.fromLocalFile(str(qml)))
        if self.status() == QQuickView.Status.Error:
            raise RuntimeError('QML could not load')
        self.animation = QPropertyAnimation(self, b'opacity', self)
        self.animation.setDuration(180)
        self.animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.visibleChanged.connect(self.bridge.set_visible)

    def show_at_tray(self, tray_rect):
        anchor = tray_rect.center() if not tray_rect.isEmpty() else QCursor.pos()
        if not self._placed:
            self.placement.place(anchor)
            self._placed = True
        else:
            # Restore the current geometry, including an unsaved move, and only
            # clamp if the screen configuration has changed while hidden.
            point = self.position()
            self.setGeometry(window_geometry(self.placement.screen_provider(), point,
                self.size(), (point.x(), point.y())))
        if self.isVisible() and self.windowState() != Qt.WindowState.WindowMinimized:
            show_interactive_window(self)
            return
        self.animation.stop()
        self.setOpacity(1 if self.desktop.reduce_motion else 0)
        show_interactive_window(self)
        if not self.desktop.reduce_motion:
            self.animation.setStartValue(0.0)
            self.animation.setEndValue(1.0)
            self.animation.start()

    def activateWindow(self):
        self.requestActivate()

    def setWindowOpacity(self, value):
        self.setOpacity(value)

    def grab(self):
        return self.grabWindow()

    def settings_dialog(self):
        self.bridge.navigate('settings')

    def reset_position(self):
        self.placement.reset()

    def event(self, event):
        if event.type() == QEvent.Type.Close:
            self.hide()
            event.ignore()
            return True
        return super().event(event)
