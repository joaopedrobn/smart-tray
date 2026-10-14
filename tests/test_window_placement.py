from PySide6.QtCore import Qt, QPoint, QPointF, QRect, QSize, QEvent
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QWidget, QPushButton, QApplication
from smart_tray.desktop_state import DesktopSettings
from smart_tray.window_placement import WindowPlacement


def test_header_drag_persists_and_next_open_respects_choice(qt_app, tmp_path):
    window = QWidget()
    header = QWidget(window)
    header.resize(350, 40)
    settings = DesktopSettings(tmp_path)
    screens = lambda: [QRect(0, 0, 1920, 1040)]
    placement = WindowPlacement(window, settings, QSize(500, 800), screens)
    placement.attach_header(header)
    placement.place(QPoint(1900, 1030))
    window.show()
    before = window.pos()
    start = QPoint(1500, 250)
    def mouse(kind, global_point, button, buttons):
        event = QMouseEvent(kind, QPointF(20, 20), QPointF(global_point), button, buttons, Qt.KeyboardModifier.NoModifier)
        QApplication.sendEvent(header, event)
    mouse(QEvent.Type.MouseButtonPress, start, Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton)
    mouse(QEvent.Type.MouseMove, start + QPoint(-180, -20), Qt.MouseButton.NoButton, Qt.MouseButton.LeftButton)
    mouse(QEvent.Type.MouseButtonRelease, start + QPoint(-180, -20), Qt.MouseButton.LeftButton, Qt.MouseButton.NoButton)
    after = window.pos()
    assert after == before + QPoint(-180, -20)
    saved = window.geometry().topLeft()
    assert DesktopSettings(tmp_path).position == (saved.x(), saved.y())
    placement.place(QPoint(1900, 1030))
    assert window.pos() == after
    placement.reset()
    assert window.pos() == before and DesktopSettings(tmp_path).position is None
    window.close()
    window.deleteLater()


def test_drag_area_does_not_capture_child_button(qt_app, tmp_path):
    window = QWidget()
    header = QWidget(window)
    button = QPushButton('Control', header)
    count = []
    button.clicked.connect(lambda: count.append(True))
    placement = WindowPlacement(window, DesktopSettings(tmp_path), QSize(500, 800))
    placement.attach_header(header)
    from PySide6.QtTest import QTest
    QTest.mouseClick(button, Qt.MouseButton.LeftButton)
    assert count == [True] and placement.drag_origin is None
    window.deleteLater()
