import pytest
from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import QWheelEvent
from PySide6.QtWidgets import QApplication, QWidget, QVBoxLayout, QComboBox, QSpinBox, QSlider, QScrollArea


@pytest.mark.parametrize('kind', ['combo', 'spin', 'slider', 'spin_editor'])
def test_wheel_scrolls_content_without_changing_controls(qt_app, kind):
    scroll = QScrollArea()
    content = QWidget()
    layout = QVBoxLayout(content)
    if kind == 'combo':
        control = QComboBox()
        control.addItems(['Baixa', 'Média', 'Alta'])
        control.setCurrentIndex(1)
        before = control.currentIndex()
    elif kind.startswith('spin'):
        control = QSpinBox()
        control.setValue(24)
        before = control.value()
    else:
        control = QSlider(Qt.Orientation.Horizontal)
        control.setValue(50)
        before = control.value()
    layout.addWidget(control)
    layout.addStretch()
    content.setMinimumHeight(1200)
    scroll.setWidget(content)
    scroll.setWidgetResizable(True)
    scroll.resize(400, 300)
    scroll.show()
    qt_app.processEvents()
    receiver = control.lineEdit() if kind == 'spin_editor' else control
    receiver.setFocus()
    origin = receiver.rect().center()
    wheel = QWheelEvent(QPointF(origin), QPointF(receiver.mapToGlobal(origin)), QPoint(), QPoint(0, -120),
        Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier, Qt.ScrollPhase.NoScrollPhase, False)
    QApplication.sendEvent(receiver, wheel)
    assert (control.currentIndex() if kind == 'combo' else control.value()) == before
    assert scroll.verticalScrollBar().value() > 0
    scroll.close()
    scroll.deleteLater()
