"""Local visual system for the tray beta; no device or credential access."""
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QComboBox


class ChoiceBox(QComboBox):
    """Visible affordance even when the Fusion/QSS native arrow is low contrast."""
    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(QColor('#B8D3F8' if self.isEnabled() else '#66758F'), 1.5))
        x, y = self.width() - 17, self.height() // 2
        painter.drawLine(x - 4, y - 2, x, y + 2)
        painter.drawLine(x, y + 2, x + 4, y - 2)
        painter.end()


STYLE = """
QFrame#shell { background: #0C0E12; border: 1px solid #283147; border-radius: 24px; }
QFrame#card { background: #14171F; border: 1px solid #252C3B; border-radius: 20px; }
QFrame#hero { background: qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 #172B46,stop:1 #141923); border: 1px solid #314865; border-radius: 22px; }
QLabel#title { font-size: 21px; font-weight: 650; }
QLabel#name { font-size: 15px; font-weight: 600; }
QLabel#section { color: #99ABC5; font-size: 11px; font-weight: 600; padding-top: 3px; }
QLabel#muted { color: #9AA8BF; font-size: 11px; }
QLabel#controlStatus { color: #9BB9DF; background: #18263A; border-radius: 8px; padding: 6px 9px; font-size: 11px; }
QLabel#readout { background: #182132; color: #B5C3D9; border: 1px solid #2C3A50; border-radius: 12px; padding: 10px; }
QPushButton { padding: 10px 12px; border-radius: 12px; background: #202B3D; border: 1px solid #344159; }
QPushButton:hover { background: #2B4060; border-color: #619EFF; }
QPushButton:pressed { background: #335584; }
QPushButton:disabled { background: #161C28; border: 1px solid #232D3D; color: #67758D; }
QPushButton#betaUnlock { background: #213350; border: 1px solid #426BA3; color: #BCD6FF; font-weight: 600; }
QPushButton#primary { background: #3B82F6; border: 1px solid #6CA5FF; }
QComboBox { min-height: 24px; padding: 6px 10px; border: 1px solid #344159; border-radius: 12px; background: #1C283B; }
QComboBox::drop-down { border: none; width: 24px; }
QComboBox::down-arrow { image: none; }
QComboBox QAbstractItemView { background: #182335; border: 1px solid #426BA3; selection-background-color: #304F7D; padding: 5px; }
QSlider { min-height: 28px; }
QSlider::groove:horizontal { background: #2A364D; height: 7px; border-radius: 3px; }
QSlider::sub-page:horizontal { background: #3B82F6; border-radius: 3px; }
QSlider::handle:horizontal { background: #EAF2FF; border: 2px solid #6AA2FA; width: 16px; margin: -6px 0; border-radius: 9px; }
QSlider::sub-page:horizontal:disabled { background: #39475D; }
QSlider::handle:horizontal:disabled { background: #67758D; border-color: #47546B; }
QDialog { background: #0F141E; }
QCheckBox { spacing: 10px; padding: 8px 0; }
QSpinBox { background: #1C283B; border: 1px solid #344159; border-radius: 8px; padding: 6px; }
"""
