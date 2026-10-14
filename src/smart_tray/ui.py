"""Compact dark Widgets panel; unvalidated features remain disabled."""
import time
import os
from pathlib import Path
from PySide6.QtCore import Qt, Signal, QRect, QPoint, QPropertyAnimation, QEasingCurve, QEvent, QTimer
from PySide6.QtGui import QIcon, QPainter, QPen, QColor, QPixmap, QCursor, QFontDatabase, QPalette
from PySide6.QtWidgets import (QApplication, QWidget, QFrame, QLabel, QPushButton, QVBoxLayout,
                              QHBoxLayout, QGridLayout, QComboBox, QSlider, QScrollArea,
                              QGraphicsDropShadowEffect)
from .premium import ChoiceBox

STYLE = """
QWidget { color: #E9ECF5; font-family: 'Segoe UI Variable', 'Segoe UI'; font-size: 12px; }
QFrame#shell { background: #0C0E12; border: 1px solid #222634; border-radius: 20px; }
QFrame#card { background: #14171F; border: 1px solid #222634; border-radius: 16px; }
QFrame#hero { background: #141B2B; border: 1px solid #273750; border-radius: 16px; }
QLabel { background: transparent; border: none; }
QLabel#title { font-size: 19px; font-weight: 650; }
QLabel#name { font-size: 14px; font-weight: 600; }
QLabel#muted { color: #8792A8; font-size: 11px; }
QLabel#section { color: #66758F; font-size: 10px; font-weight: 650; }
QLabel#temperature { font-size: 48px; font-weight: 300; color: #697992; }
QLabel#badge { color: #D6AD69; background: #30281D; border-radius: 7px; padding: 4px 7px; font-size: 10px; }
QPushButton { background: #1B2230; border: 1px solid #293449; border-radius: 10px; padding: 7px 10px; }
QPushButton:hover { background: #233451; border-color: #3B82F6; }
QPushButton:pressed { background: #263E62; }
QPushButton:disabled { background: #161C28; border-color: #242C3C; color: #556077; }
QPushButton#iconButton { border: none; background: transparent; font-size: 16px; padding: 0px; }
QPushButton#primary { background: #3B82F6; color: white; }
QPushButton#primary:disabled { background: #1C3152; color: #697992; }
QComboBox { background: #1B2230; border: 1px solid #293449; border-radius: 8px; padding: 6px; }
QComboBox:disabled { color: #66758F; background: #161C28; }
QSlider::groove:horizontal { background: #252D3E; height: 4px; border-radius: 2px; }
QSlider::handle:horizontal { background: #66758F; width: 12px; margin: -4px 0; border-radius: 6px; }
QScrollArea { background: transparent; border: none; }
QScrollBar:vertical { background: transparent; width: 5px; margin: 2px; }
QScrollBar::handle:vertical { background: #2D374C; border-radius: 2px; min-height: 25px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0px; }
QMenu { background: #14171F; color: #E9ECF5; border: 1px solid #222634; padding: 5px; }
QMenu::item { padding: 8px 16px; border-radius: 5px; }
QMenu::item:selected { background: #233451; }
"""


def configure_style(app):
    from .wheel_guard import install_wheel_guard
    install_wheel_guard(app)
    # Qt's offscreen Windows plugin has no system font database. Load the
    # existing Windows fonts for meaningful test renders; no fonts are bundled.
    if os.name == "nt" and "Segoe UI" not in QFontDatabase.families():
        for filename in ("segoeui.ttf", "segoeuib.ttf", "segoeuis.ttf", "segoeuil.ttf"):
            path = Path(os.environ["WINDIR"]) / "Fonts" / filename
            if path.exists():
                QFontDatabase.addApplicationFont(str(path))
    app.setStyle("Fusion")
    palette = QPalette()
    for role, colour in ((QPalette.ColorRole.Window, "#0C0E12"), (QPalette.ColorRole.WindowText, "#E9ECF5"),
                         (QPalette.ColorRole.Base, "#14171F"), (QPalette.ColorRole.AlternateBase, "#1B2230"),
                         (QPalette.ColorRole.Text, "#E9ECF5"), (QPalette.ColorRole.Button, "#1B2230"),
                         (QPalette.ColorRole.ButtonText, "#E9ECF5"), (QPalette.ColorRole.Highlight, "#3B82F6"),
                         (QPalette.ColorRole.HighlightedText, "#FFFFFF")):
        palette.setColor(role, QColor(colour))
    app.setPalette(palette)
    app.setStyleSheet(STYLE)


def icon(kind="tray", color="#93A4C0", size=24):
    pixmap = QPixmap(size * 2, size * 2)
    pixmap.setDevicePixelRatio(2)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(QPen(QColor(color), 1.8, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
    if kind == "power":
        painter.drawArc(5, 5, 14, 14, 135 * 16, 270 * 16)
        painter.drawLine(12, 3, 12, 11)
    elif kind == "ac":
        painter.drawRoundedRect(3, 5, 18, 10, 3, 3)
        painter.drawLine(6, 11, 18, 11)
        for x in (7, 12, 17):
            painter.drawLine(x, 17, x - 1, 20)
    elif kind == "led":
        painter.drawRoundedRect(4, 6, 16, 12, 3, 3)
        for x in (8, 12, 16):
            painter.drawPoint(x, 12)
    elif kind == "switch":
        painter.drawRoundedRect(4, 3, 16, 18, 3, 3)
        painter.drawLine(12, 6, 12, 18)
    else:
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#3B82F6"))
        painter.drawRoundedRect(1, 1, 22, 22, 6, 6)
        painter.setPen(QPen(QColor("white"), 2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        painter.drawLine(5, 11, 12, 5)
        painter.drawLine(12, 5, 19, 11)
        painter.drawLine(7, 10, 7, 19)
        painter.drawLine(17, 10, 17, 19)
        painter.drawLine(7, 19, 10, 19)
        painter.drawLine(10, 19, 10, 14)
        painter.drawLine(10, 14, 14, 14)
        painter.drawLine(14, 14, 14, 19)
        painter.drawLine(14, 19, 17, 19)
    painter.end()
    return QIcon(pixmap)


def label(text, name=None):
    widget = QLabel(text)
    if name:
        widget.setObjectName(name)
    return widget


class PowerButton(QPushButton):
    """No optimistic checked state; display only confirmed LAN values."""
    def __init__(self):
        super().__init__("—")
        self.setFixedSize(94, 34)
        self.setEnabled(False)
        self.setAccessibleName("Liga/desliga")

    def reflect(self, value, enabled, busy=False):
        self.setText("Aguarde…" if busy else "Ligado" if value is True else "Desligado" if value is False else "—")
        self.setIcon(icon("power", "#FFFFFF" if value is True else "#8792A8"))
        self.setObjectName("primary" if value is True else "")
        self.setEnabled(enabled)
        self.style().unpolish(self)
        self.style().polish(self)


class DeviceCard(QFrame):
    def __init__(self, title, subtitle, glyph):
        super().__init__()
        self.setObjectName("card")
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(16, 14, 16, 14)
        self.layout.setSpacing(6)
        row = QHBoxLayout()
        image = QLabel()
        image.setPixmap(icon(glyph).pixmap(24, 24))
        row.addWidget(image)
        titles = QVBoxLayout()
        titles.setSpacing(3)
        titles.addWidget(label(title, "name"))
        titles.addWidget(label(subtitle, "muted"))
        row.addLayout(titles, 1)
        self.status = label("●  Consultando", "muted")
        row.addWidget(self.status)
        self.layout.addLayout(row)
        self.message = label("", "muted")
        self.message.setWordWrap(True)

    def reflect(self, state, busy):
        names = {"online": "Online", "offline": "Offline", "unknown": "Desconhecido", "pending": "Pendente"}
        self.status.setText("●  " + ("Atualizando" if busy else names.get(state.connection, "Desconhecido")))
        self.status.setStyleSheet("color: " + ("#69CDA8" if state.connection == "online" else "#8792A8") + ";")
        self.message.setText("" if state.message in ("Estado atualizado", "Consultando estado…") else state.message)
        self.message.setVisible(bool(self.message.text()))


class ElginCard(DeviceCard):
    """Named controls and capability-driven binding allow a future OEM adapter."""
    requested = Signal(str, object)

    def __init__(self):
        super().__init__("Elgin Eco Inverter III", "Seu clima, no centro de tudo", "ac")
        self.setObjectName("hero")
        self.layout.setSpacing(4)
        self.status.hide()
        self.badge = label("Aguardando configuração", "badge")
        self.layout.addWidget(self.badge, 0, Qt.AlignmentFlag.AlignLeft)
        temperature_row = QHBoxLayout()
        self.minus = QPushButton("−")
        self.plus = QPushButton("+")
        self.minus.setFixedSize(36, 36)
        self.plus.setFixedSize(36, 36)
        self.temperature = label("—", "temperature")
        self.temperature.setFixedHeight(60)
        self.temperature.setAlignment(Qt.AlignmentFlag.AlignCenter)
        temperature_row.addWidget(self.minus)
        temperature_row.addStretch()
        temperature_row.addWidget(self.temperature)
        temperature_row.addWidget(label("°C", "muted"))
        temperature_row.addStretch()
        temperature_row.addWidget(self.plus)
        self.layout.addLayout(temperature_row)
        hint = label("Temperatura indisponível", "muted")
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hint.hide()
        self.temperature_hint = hint
        self.layout.addWidget(hint)
        self.minus.setAccessibleName("Diminuir temperatura do Elgin em 1 °C")
        self.plus.setAccessibleName("Aumentar temperatura do Elgin em 1 °C")
        self.power = PowerButton()
        self.power.setFixedWidth(140)
        self.power.clicked.connect(lambda: self.requested.emit("power", not self.current.get("power")))
        self.layout.addWidget(self.power, 0, Qt.AlignmentFlag.AlignHCenter)
        controls = QGridLayout()
        self.mode, self.fan = ChoiceBox(), ChoiceBox()
        self.mode.addItem("Modo indisponível", None)
        self.fan.addItem("Ventilação indisponível", None)
        controls.addWidget(self.mode, 0, 0)
        controls.addWidget(self.fan, 0, 1)
        self.swing = QPushButton("Oscilação")
        self.swing.clicked.connect(lambda: self.requested.emit("swing", not self.current.get("swing")))
        controls.addWidget(self.swing, 1, 0)
        more = QPushButton("Mais controles")
        more.setEnabled(False)
        controls.addWidget(more, 1, 1)
        self.layout.addLayout(controls)
        self.integration_hint = label("Integração local em preparação · pareamento preservado", "muted")
        self.integration_hint.setWordWrap(True)
        self.layout.addWidget(self.integration_hint)
        self.message.setWordWrap(True)
        self.layout.addWidget(self.message)
        self.current = {}
        self.minus.clicked.connect(lambda: self._temperature_step(-1))
        self.plus.clicked.connect(lambda: self._temperature_step(1))
        self.mode.activated.connect(lambda i: self.requested.emit("mode", self.mode.itemData(i)))
        self.fan.activated.connect(lambda i: self.requested.emit("fan", self.fan.itemData(i)))
        self.reflect_pending()

    def _temperature_step(self, direction):
        spec = self.capabilities.get("temperature", {})
        value = self.current.get("temperature")
        if type(value) in (int, float):
            value += direction * spec.get("step", 1)
            if spec.get("min", value) <= value <= spec.get("max", value):
                self.requested.emit("temperature", value)

    def reflect_pending(self):
        self.bind({}, {}, False)

    def bind(self, capabilities, values, online, busy=False, message=""):
        self.capabilities, self.current = capabilities, values
        interactive = online and not busy
        self.badge.setText("Consultando…" if busy else "Conectado pela LAN" if online else "Sem confirmação LAN" if capabilities else "Aguardando configuração")
        value = values.get("temperature") if online else None
        self.temperature.setText(str(value) if type(value) in (int, float) else "—")
        ambient = values.get("ambient_temperature") if online else None
        self.temperature_hint.setText(f"Ambiente {ambient} °C · temperatura ajustada acima" if type(ambient) in (int, float) else "Temperatura ajustada" if value is not None else "Temperatura indisponível")
        self.temperature_hint.setVisible(value is not None)
        self.integration_hint.setText("Temperatura e Média validadas · demais comandos pendentes" if "fan" in capabilities else "Temperatura validada · demais comandos em validação" if capabilities else "Integração local em preparação · pareamento preservado")
        self.message.setText(message if not interactive else "")
        self.message.setVisible(bool(self.message.text()))
        temperature_spec = capabilities.get("temperature", {})
        conditions_met = all(values.get(key) == expected for key, expected in temperature_spec.get("requires", {}).items())
        enabled = interactive and "temperature" in capabilities and type(value) in (int, float) and conditions_met
        self.minus.setEnabled(enabled and value > capabilities["temperature"].get("min", value))
        self.plus.setEnabled(enabled and value < capabilities["temperature"].get("max", value))
        self.power.reflect(values.get("power") if online else None, interactive and "power" in capabilities and type(values.get("power")) is bool)
        self.power.setToolTip("Liga/desliga ainda não validado" if "power" not in capabilities else "")
        self.swing.setEnabled(interactive and "swing" in capabilities and type(values.get("swing")) is bool)
        for name, combo in (("mode", self.mode), ("fan", self.fan)):
            spec = capabilities.get(name, {})
            options = spec.get("options", {})
            displayed_options = spec.get("observed_options", options)
            combo.blockSignals(True)
            if options:
                wanted = list(displayed_options.items())
                existing = [(combo.itemData(i), combo.itemText(i)) for i in range(combo.count())]
                if existing != wanted:
                    combo.clear()
                    for key, title in wanted:
                        combo.addItem(title, key)
                for i in range(combo.count()):
                    combo.model().item(i).setEnabled(combo.itemData(i) in options)
                if not combo.view().isVisible():
                    combo.setCurrentIndex(combo.findData(values.get(name)))
            else:
                combo.clear()
                observed_mode = {"cold": "Frio", "hot": "Quente", "wet": "Desumidificar", "wind": "Ventilar", "auto": "Automático"}.get(values.get("mode")) if online else None
                combo.addItem(observed_mode + " · somente leitura" if name == "mode" and observed_mode else "Modo indisponível" if name == "mode" else "Ventilação indisponível", None)
            combo.blockSignals(False)
            conditions_met = all(values.get(key) == expected for key, expected in spec.get("requires", {}).items())
            combo.setEnabled(interactive and bool(options) and values.get(name) in displayed_options and conditions_met)


def panel_position(available, anchor, width, height, margin=12):
    """All rectangles are Qt logical coordinates; never multiply by device DPI."""
    width, height = min(width, available.width() - margin * 2), min(height, available.height() - margin * 2)
    x = min(max(anchor.x() - width + 24, available.left() + margin), available.right() - width - margin + 1)
    y = min(max(anchor.y() - height - margin, available.top() + margin), available.bottom() - height - margin + 1)
    return QRect(x, y, width, height)


class Panel(QWidget):
    preferences = Signal()

    def __init__(self, controller):
        super().__init__(None, Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint)
        self.controller = controller
        self.setWindowTitle("Smart Tray")
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.resize(420, 800)
        self.menu_visible = False
        self.deactivated_at = 0
        outer = QVBoxLayout(self)
        outer.setContentsMargins(8, 8, 8, 8)
        shell = QFrame()
        shell.setObjectName("shell")
        shadow = QGraphicsDropShadowEffect(shell)
        shadow.setBlurRadius(16)
        shadow.setOffset(0, 3)
        shadow.setColor(QColor(0, 0, 0, 130))
        shell.setGraphicsEffect(shadow)
        outer.addWidget(shell)
        layout = QVBoxLayout(shell)
        layout.setContentsMargins(18, 17, 18, 14)
        layout.setSpacing(13)
        header = QHBoxLayout()
        logo = QLabel()
        logo.setPixmap(icon().pixmap(28, 28))
        header.addWidget(logo)
        title = QVBoxLayout()
        title.setSpacing(2)
        title.addWidget(label("Smart Tray", "title"))
        title.addWidget(label("Sua casa, a um clique", "muted"))
        header.addLayout(title, 1)
        settings = QPushButton("···")
        settings.setObjectName("iconButton")
        settings.setFixedSize(30, 30)
        settings.setToolTip("Opções")
        settings.clicked.connect(self.preferences.emit)
        header.addWidget(settings)
        hide = QPushButton("×")
        hide.setObjectName("iconButton")
        hide.setFixedSize(25, 30)
        hide.setToolTip("Recolher painel")
        hide.clicked.connect(self.hide)
        header.addWidget(hide)
        layout.addLayout(header)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        contents = QWidget()
        contents.setObjectName("contents")
        contents.setStyleSheet("QWidget#contents { background: transparent; }")
        cards = QVBoxLayout(contents)
        cards.setContentsMargins(0, 0, 5, 0)
        cards.setSpacing(12)
        cards.addWidget(label("CLIMA", "section"))
        self.elgin = ElginCard()
        self.elgin.requested.connect(controller.request_elgin)
        cards.addWidget(self.elgin)
        cards.addWidget(label("ILUMINAÇÃO", "section"))
        self.switch = DeviceCard("Interruptor NovaDigital", "Dois canais independentes", "switch")
        self.buttons = {}
        for dp in (1, 2):
            row = QHBoxLayout()
            row.addWidget(label("Canal " + str(dp)), 1)
            button = PowerButton()
            button.setAccessibleName("NovaDigital canal " + str(dp))
            button.clicked.connect(lambda checked=False, channel=dp: controller.toggle("novadigital", channel))
            self.buttons[("novadigital", dp)] = button
            row.addWidget(button)
            self.switch.layout.addLayout(row)
        self.switch.layout.addWidget(self.switch.message)
        cards.addWidget(self.switch)
        self.led = DeviceCard("Fita LED Outsmart", "RGBIC · controle local", "led")
        row = QHBoxLayout()
        row.addWidget(label("Alimentação"), 1)
        power = PowerButton()
        power.setAccessibleName("Fita Outsmart liga/desliga")
        power.clicked.connect(lambda: controller.toggle("led", 20))
        self.buttons[("led", 20)] = power
        row.addWidget(power)
        self.led.layout.addLayout(row)
        future = QHBoxLayout()
        for name in ("Cor", "Brilho", "Modos"):
            button = QPushButton(name)
            button.setEnabled(False)
            button.setToolTip("Disponível após validação deste controle")
            future.addWidget(button)
        self.led.layout.addLayout(future)
        self.led.layout.addWidget(self.led.message)
        cards.addWidget(self.led)
        cards.addStretch()
        scroll.setWidget(contents)
        layout.addWidget(scroll, 1)
        footer = QHBoxLayout()
        footer.addWidget(label("●  Conexão local · credenciais protegidas", "muted"), 1)
        self.refresh_button = QPushButton("↻")
        self.refresh_button.setFixedSize(30, 30)
        self.refresh_button.setObjectName("iconButton")
        self.refresh_button.setToolTip("Atualizar estados pela LAN")
        self.refresh_button.clicked.connect(controller.refresh)
        footer.addWidget(self.refresh_button)
        layout.addLayout(footer)
        self.animation = QPropertyAnimation(self, b"windowOpacity", self)
        self.animation.setDuration(150)
        self.animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        controller.changed.connect(self.render_state)
        self.render_state()

    def render_state(self):
        for role, card in (("led", self.led), ("novadigital", self.switch)):
            state = self.controller.states[role]
            card.reflect(state, role in self.controller.busy)
            for (r, dp), button in self.buttons.items():
                if r == role:
                    button.reflect(state.values.get(dp), self.controller.can_write(role, dp), role in self.controller.busy)
        state = self.controller.states["elgin"]
        self.elgin.bind(self.controller.elgin_capabilities(), state.values,
                        state.connection == "online", self.controller.writing or "elgin" in self.controller.busy, state.message)
        self.refresh_button.setEnabled(not self.controller.writing and not self.controller.stopping)

    def show_at_tray(self, tray_rect):
        anchor = tray_rect.center() if not tray_rect.isEmpty() else QCursor.pos()
        screen = QApplication.screenAt(anchor) or QApplication.primaryScreen()
        self.setGeometry(panel_position(screen.availableGeometry(), anchor, 420, 800))
        self.animation.stop()
        self.setWindowOpacity(0)
        self.show()
        self.raise_()
        self.activateWindow()
        from .windows import show_interactive_window
        show_interactive_window(self)
        self.animation.setStartValue(0.0)
        self.animation.setEndValue(1.0)
        self.animation.start()

    def event(self, event):
        if event.type() == QEvent.Type.WindowDeactivate and not self.menu_visible:
            # Popup activation is delivered before Qt exposes activePopupWidget.
            # Wait one event-loop turn before deciding this was an outside click.
            if event.spontaneous():
                QTimer.singleShot(0, self._hide_if_outside)
            else:
                self._hide_if_outside(check_active=False)
        return super().event(event)

    def _hide_if_outside(self, check_active=True):
        if check_active and self.isActiveWindow():
            return
        def owns_visible(widget):
            if not widget or not widget.isVisible():
                return False
            while widget:
                if widget is self:
                    return True
                widget = widget.parentWidget()
            return False
        if (not self.menu_visible and not owns_visible(QApplication.activePopupWidget())
                and not owns_visible(QApplication.activeModalWidget())
                and not getattr(self, "interaction_active", lambda: False)()):
            self.deactivated_at = time.monotonic()
            self.hide()

    def closeEvent(self, event):
        event.ignore()
        self.hide()
