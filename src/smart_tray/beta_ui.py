"""One daily panel and reusable advanced dialogs, with local confirmations."""
import json
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QComboBox, QSlider, QColorDialog, QMessageBox, QCheckBox, QPlainTextEdit, QSpinBox,
    QScrollArea, QWidget)
from .ui import Panel, label
from .beta import VERSION, BetaAdapter, valid_colour
from .led_research import hsv16_decode, hsv16_encode, hsv_to_rgb, rgb_to_hsv16
from .ui_diagnostics import record
from .windows import show_interactive_window
from .premium import ChoiceBox


class BetaPanel(Panel):
    def __init__(self, controller):
        super().__init__(controller)
        self.dialog = None
        self.dialogs = {}
        self.accepted = set()  # First use per function/target each app session.
        from .premium import STYLE
        self.setStyleSheet(STYLE)
        self.setWindowTitle("Smart Tray " + VERSION)
        # Keep all three cards visible on a typical desktop; advanced controls
        # stay in dialogs, with scrolling available for small/high-DPI screens.
        self.elgin.badge.hide()
        self.elgin.integration_hint.hide()
        self.elgin.temperature.setFixedHeight(82)
        self.elgin.temperature.setStyleSheet("font-size: 64px; font-weight: 300; color: #F2F6FF;")
        for step in (self.elgin.minus, self.elgin.plus):
            step.setFixedSize(48, 48)
        self.elgin.layout.removeWidget(self.elgin.power)
        self.elgin.power.setFixedWidth(90)
        self.elgin.layout.itemAt(0).layout().addWidget(self.elgin.power)
        for card in (self.elgin, self.switch, self.led):
            card.layout.setContentsMargins(16, 14, 16, 14)
            card.layout.setSpacing(9)
            for widget in card.findChildren(QLabel):
                if widget.text() in {"Seu clima, no centro de tudo", "Dois canais independentes", "RGBIC · controle local"}:
                    widget.hide()
        self.elgin.requested.disconnect()
        self.elgin.requested.connect(lambda name, value: self.request("elgin", name, value))
        self.elgin.integration_hint.setText("Beta · controles experimentais opcionais")
        self.elgin.swing.setToolTip("Não mapeado: eixo do DPS 33 não correlacionado ao botão Oscilar")
        more = self.elgin.findChildren(QPushButton)
        for button in more:
            if button.text() == "Mais controles":
                button.setEnabled(True)
                button.clicked.connect(lambda: self.advanced("elgin"))
        self.mode_readout = label("", "readout")
        self.mode_readout.linkActivated.connect(lambda _: self.enable_experimental())
        self.mode_readout.setToolTip("Modo observado pela LAN. Liberar Beta salva apenas a preferência; não altera o Elgin.")
        for i in range(self.elgin.layout.count()):
            grid = self.elgin.layout.itemAt(i).layout()
            if grid and grid.indexOf(self.elgin.mode) >= 0:
                grid.addWidget(self.mode_readout, 0, 0)
                break
        self.elgin_controls_status = label("", "controlStatus")
        self.elgin_controls_status.setWordWrap(True)
        self.elgin.layout.addWidget(self.elgin_controls_status)
        # Keep validated channel handlers; present both channels in one row.
        compact_channels = QHBoxLayout()
        for dp in (1, 2):
            old_channel = self.switch.layout.takeAt(1).layout()
            while old_channel.count():
                widget = old_channel.takeAt(0).widget()
                if isinstance(widget, QLabel):
                    widget.deleteLater()
            compact_channels.addWidget(label("Canal " + str(dp), "muted"))
            compact_channels.addWidget(self.buttons[("novadigital", dp)])
        self.switch.layout.insertLayout(1, compact_channels)
        # Lighting is the second primary card; switches remain readily below it.
        cards = self.led.parentWidget().layout()
        cards.removeWidget(self.led)
        cards.insertWidget(cards.indexOf(self.switch), self.led)
        power_row = self.led.layout.takeAt(1).layout()
        while power_row.count():
            widget = power_row.takeAt(0).widget()
            if isinstance(widget, QLabel):
                widget.deleteLater()
        self.led.layout.itemAt(0).layout().addWidget(self.buttons[("led", 20)])
        # Replace the old disabled LED placeholders, preserving power wiring.
        item = self.led.layout.itemAt(self.led.layout.count() - 2)
        old = item.layout()
        if old:
            while old.count():
                widget = old.takeAt(0).widget()
                if widget:
                    widget.deleteLater()
            self.led.layout.removeItem(old)
        self.colour_button = QPushButton("Cor atual: —")
        self.colour_button.clicked.connect(self.choose_colour)
        self.led.layout.insertWidget(self.led.layout.count() - 1, self.colour_button)
        mode_row = QHBoxLayout()
        mode_row.addWidget(label("Iluminação", "muted"))
        self.led_mode = ChoiceBox()
        self.led_mode.setAccessibleName("Modo de iluminação da fita")
        self.led_mode.activated.connect(lambda i: self.request("led", "mode", self.led_mode.itemData(i)))
        mode_row.addWidget(self.led_mode, 1)
        self.led.layout.insertLayout(self.led.layout.count() - 1, mode_row)
        self.led_controls_status = label("", "controlStatus")
        self.led_controls_status.setWordWrap(True)
        self.led.layout.insertWidget(self.led.layout.count() - 1, self.led_controls_status)
        self.unlock_beta = QPushButton("Liberar controles Beta")
        self.unlock_beta.setObjectName("betaUnlock")
        self.unlock_beta.clicked.connect(self.enable_experimental)
        self.led.layout.insertWidget(self.led.layout.count() - 1, self.unlock_beta)
        self.fixed_colour = QPushButton("Usar cor fixa · Beta")
        self.fixed_colour.clicked.connect(lambda: self.request("led", "mode", "colour"))
        self.led.layout.insertWidget(self.led.layout.count() - 1, self.fixed_colour)
        row = QHBoxLayout()
        self.brightness_label = label("Brilho em cor fixa · —", "muted")
        row.addWidget(self.brightness_label)
        self.brightness = QSlider(Qt.Orientation.Horizontal)
        self.brightness.setRange(1, 100)
        self.led.layout.insertLayout(self.led.layout.count() - 1, row)
        self.led.layout.insertWidget(self.led.layout.count() - 1, self.brightness)
        self.debounce = QTimer(self)
        self.debounce.setSingleShot(True)
        self.debounce.setInterval(450)
        self.brightness.valueChanged.connect(self.brightness_changed)
        self.brightness.sliderPressed.connect(self.debounce.stop)
        self.brightness.sliderReleased.connect(lambda: self.debounce.start())
        self.debounce.timeout.connect(self.send_brightness)
        advanced = QPushButton("Controles avançados")
        advanced.clicked.connect(lambda: self.advanced("led"))
        self.effects = QPushButton("Efeitos / Cenas · ver disponibilidade")
        self.effects.clicked.connect(lambda: self.advanced("led", "CENAS / EFEITOS"))
        self.effects.setText("Efeitos / Cenas")
        actions = QHBoxLayout()
        actions.addWidget(self.effects)
        actions.addWidget(advanced)
        self.led.layout.insertLayout(self.led.layout.count() - 1, actions)
        controller.action_finished.connect(self.action_finished)
        self.resize(460, 860)
        self.render_state()

    def render_state(self):
        super().render_state()
        if not hasattr(self, "brightness"):
            return
        if self.controller.stopping:
            for dialog in list(self.dialogs.values()):
                dialog.close()
        self.elgin.integration_hint.setText("Beta experimental ativada" if self.controller.settings.enabled else "Validados ativos · experimentais em Configurações")
        self.elgin.power.setToolTip("Beta: primeira alteração exige confirmação" if "power" in self.controller.elgin_capabilities() else "Liga/desliga experimental: habilite Beta em Configurações")
        temperature_reason = ("Consulta ou comando em andamento" if self.controller.writing or "elgin" in self.controller.busy
            else "Elgin offline ou estado desconhecido; use Atualizar" if self.controller.states["elgin"].connection != "online"
            else "Temperatura validada somente com aparelho ligado em Resfriar" if self.controller.states["elgin"].values.get("power") is not True or self.controller.states["elgin"].values.get("mode") != "cold"
            else "Ajustar 1 °C · DPS 2 validado · limites 16–32 °C")
        self.elgin.minus.setToolTip(temperature_reason)
        self.elgin.plus.setToolTip(temperature_reason)
        self.elgin.fan.setToolTip("Média validada; demais velocidades exigem Beta. O valor já selecionado não envia nova escrita.")
        self.elgin.mode.setToolTip("Modos experimentais: habilite Beta em Configurações. Só há escrita após ação e confirmação." if "mode" not in self.controller.elgin_capabilities()
            else "Elgin offline ou consulta em andamento" if self.controller.states["elgin"].connection != "online" or "elgin" in self.controller.busy
            else "Mudança de modo experimental; requer aparelho ligado")
        # Swing and ionizer remain unmapped, regardless of Beta activation.
        self.elgin.swing.setEnabled(False)
        self.elgin.swing.setText("Oscilação · indisponível")
        elgin_state = self.controller.states["elgin"]
        has_mode = "mode" in self.controller.elgin_capabilities()
        self.elgin.mode.setVisible(has_mode)
        self.mode_readout.setVisible(not has_mode)
        modes = {"cold": "Resfriar", "wet": "Desumidificar", "wind": "Ventilar", "auto": "Automático"}
        self.mode_readout.setText("Modo · " + modes.get(elgin_state.values.get("mode"), "—") +
            '<br>Somente leitura · <a style="color:#8AB8FF" href="beta">Liberar Beta</a>')
        self.elgin_controls_status.setText(
            "Aguardando resposta LAN…" if "elgin" in self.controller.busy or self.controller.write_role == "elgin" else
            "Erro / sem confirmação LAN · atualize para tentar novamente" if elgin_state.connection != "online" else
            "Temperatura e Média disponíveis · demais ações experimentais" if elgin_state.values.get("power") is True and elgin_state.values.get("mode") == "cold" else
            "Controles de temperatura disponíveis quando ligado em Resfriar")
        ambient = elgin_state.values.get("ambient_temperature")
        if elgin_state.connection == "online" and type(ambient) in (int, float):
            self.elgin.temperature_hint.setText(f"Ambiente · {ambient:g} °C")
        state = self.controller.states["led"]
        if state.message == "Estado sincronizado pela LAN":
            self.led.message.hide()
        capabilities = self.controller.capabilities_for("led")
        interactive = state.connection == "online" and not self.controller.writing and "led" not in self.controller.busy
        colour = state.values.get("colour")
        ready = interactive and state.values.get(20) is True and state.values.get("mode") == "colour" and valid_colour(colour)
        beta_enabled = self.controller.settings.enabled
        self.unlock_beta.setVisible(not beta_enabled)
        self.unlock_beta.setEnabled(not self.controller.stopping)
        self.fixed_colour.setVisible(beta_enabled and state.values.get("mode") != "colour")
        self.fixed_colour.setEnabled(interactive and state.values.get(20) is True and "colour" in capabilities.get("mode", {}).get("options", {}))
        self.fixed_colour.setToolTip("Altera somente o modo. A confirmação mostra DPS 21 antes de enviar; não aplica cor automaticamente.")
        self._sync_led_mode(self.led_mode, state, capabilities, interactive)
        self.led_controls_status.setText(
            "Aguardando resposta LAN…" if "led" in self.controller.busy or self.controller.write_role == "led" else
            "Erro / sem confirmação LAN · atualize para tentar novamente" if state.connection != "online" else
            "Cor e brilho · experimentais. Libere abaixo para testar." if not beta_enabled else
            "Ligue a fita para ajustar a iluminação" if state.values.get(20) is not True else
            "Cor e brilho · escolha Usar cor fixa para liberar" if state.values.get("mode") != "colour" else
            "Cor e brilho disponíveis · Beta com confirmação" if ready and "colour" in capabilities else
            "Cor e brilho indisponíveis · dados LAN não confirmados")
        self.colour_button.setEnabled(ready and "colour" in capabilities)
        self.brightness.setEnabled(ready and "brightness" in capabilities)
        self.brightness.blockSignals(True)
        if valid_colour(colour):
            rgb = hsv_to_rgb(hsv16_decode(colour))
            hex_rgb = QColor(*rgb).name()
            fixed_mode = state.values.get("mode") == "colour"
            self.colour_button.setText(("Cor " if fixed_mode else "Cor fixa salva ") + hex_rgb.upper()
                + (" · β" if ready and "colour" in capabilities else ""))
            self.colour_button.setStyleSheet(
                "QPushButton { text-align: left; min-height: 26px; padding-left: 16px; "
                f"background: qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #1B2639,stop:0.55 #233149,stop:1 {hex_rgb}); "
                f"border: 1px solid {hex_rgb}; color: #FFFFFF; }} "
                "QPushButton:disabled { color: #AAB7CA; border-color: #39475B; background: #1B2331; }")
            if not self.brightness.isSliderDown() and not self.debounce.isActive():
                self.brightness.setValue(max(1, state.values["brightness"]))
            self.brightness_label.setText(f"Brilho {'HSV' if fixed_mode else 'salvo'} · {state.values['brightness']}%")
        else:
            self.colour_button.setText("Cor atual não disponível")
            self.colour_button.setStyleSheet("")
            self.brightness_label.setText("Brilho em cor fixa · indisponível")
        self.brightness.blockSignals(False)
        self.colour_button.setToolTip("Selecione Colour nos controles avançados. Cor/brilho usam somente DPS 24; nenhuma troca de modo automática.")
        reason = ("Consultando estado LAN; aguarde." if "led" in self.controller.busy else
                  "Operação em andamento; aguarde." if self.controller.writing else
                  "Dispositivo offline ou estado desconhecido; use Atualizar." if state.connection != "online" else
                  "Habilite os experimentais em Configurações." if not self.controller.settings.enabled else
                  "Controle não habilitado pelo schema/perfil disponível." if "colour" not in capabilities else
                  "Ligue a fita antes de ajustar cor/brilho." if state.values.get(20) is not True else
                  "Selecione Colour nos controles avançados; o modo atual é " + str(state.values.get("mode")) + "." if state.values.get("mode") != "colour" else
                  "Formato de cor não disponível na leitura LAN." if not valid_colour(colour) else "")
        self.colour_button.setToolTip(reason or "Selecionar cor · DPS 24 HSV16 experimental")
        self.brightness.setToolTip(reason or "Brilho em cor fixa · V do DPS 24 · debounce 450 ms")
        if reason:
            self.brightness_label.setText("Brilho · indisponível" if not valid_colour(colour) else f"Brilho salvo · {state.values['brightness']}%")
        self.brightness_label.setWordWrap(False)
        for (role, dp), button in self.buttons.items():
            state_button = self.controller.states[role]
            button.setToolTip("Operação ou consulta LAN em andamento" if role in self.controller.busy or self.controller.writing
                else "Dispositivo offline ou estado desconhecido; use Atualizar" if state_button.connection != "online"
                else f"Alternar alimentação · DPS {dp} validado")

    @staticmethod
    def _sync_led_mode(combo, state, capabilities, interactive):
        titles = {"white": "Branco", "colour": "Cor fixa", "scene": "Cena", "music": "Música"}
        options = capabilities.get("mode", {}).get("options", {})
        observed = state.values.get("mode")
        entries = [(v, titles.get(v, v) + " · Beta") for v in options]
        if not entries:
            entries = [(observed, titles.get(observed, "Não disponível") + " · somente leitura")]
        combo.blockSignals(True)
        if not combo.view().isVisible():
            if [(combo.itemData(i), combo.itemText(i)) for i in range(combo.count())] != entries:
                combo.clear()
                for value, title in entries:
                    combo.addItem(title, value)
            combo.setCurrentIndex(combo.findData(observed))
        combo.blockSignals(False)
        combo.setEnabled(bool(options) and interactive and state.values.get(20) is True and observed in options)
        combo.setToolTip("Modo do schema oficial. Cena/Música não selecionam presets; códigos ainda não mapeados.")

    def enable_experimental(self):
        if self.controller.settings.enabled:
            return
        def answer(result):
            if result != QMessageBox.StandardButton.Yes or self.controller.stopping:
                return
            self.controller.settings.enabled = True
            try:
                self.controller.settings.save()
            except OSError:
                self.controller.settings.enabled = False
                self._notice("Preferências", "Não foi possível salvar a liberação Beta.")
            self.controller.changed.emit()
        self._question("Liberar controles Beta?",
            "Libera cor, brilho e modos documentados para testes, também disponíveis em Configurações. "
            "Esta ação só salva uma preferência local; não altera nenhum aparelho. "
            "O primeiro comando de cada função experimental pedirá confirmação separada.", answer)

    def interaction_active(self):
        return any(dialog.isVisible() for dialog in self.dialogs.values())

    def _focus_dialog(self, key):
        dialog = self.dialogs.get(key)
        if dialog:
            show_interactive_window(dialog)
        return dialog

    def _show_dialog(self, key, dialog, finished=None):
        # Independent, NON-modal windows cannot disable the tray panel if their
        # native owner hides or is activated again through the single instance.
        dialog.setWindowModality(Qt.WindowModality.NonModal)
        from .premium import STYLE
        dialog.setStyleSheet(STYLE)
        self.dialogs[key] = dialog
        def closed(result):
            self.dialogs.pop(key, None)
            try:
                if finished:
                    finished(result)
            finally:
                record("dialog_closed", dialog=key)
                dialog.deleteLater()
                if not self.controller.stopping and not self.interaction_active():
                    show_interactive_window(self)
        dialog.finished.connect(closed)
        show_interactive_window(dialog)
        QTimer.singleShot(0, lambda: self._focus_dialog(key))
        record("dialog_opened", dialog=key)
        return dialog

    def _question(self, title, text, finished, *, physical=False):
        if self._focus_dialog("confirmation"):
            return False
        dialog = QMessageBox(QMessageBox.Icon.Question, title, text,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No |
            (QMessageBox.StandardButton.Cancel if physical else QMessageBox.StandardButton.No), None)
        dialog.setDefaultButton(QMessageBox.StandardButton.Cancel if physical else QMessageBox.StandardButton.No)
        self._show_dialog("confirmation", dialog, finished)
        return False  # Nothing has been dispatched while awaiting user input.

    def _notice(self, title, text):
        if self._focus_dialog("notice"):
            return
        self._show_dialog("notice", QMessageBox(QMessageBox.Icon.Warning, title, text, QMessageBox.StandardButton.Ok, None))

    def brightness_changed(self, value):
        self.brightness_label.setText(f"Brilho proposto · {value}%")
        if not self.brightness.isSliderDown():
            self.debounce.start()

    def send_brightness(self):
        if self.brightness.isEnabled():
            self.request("led", "brightness", self.brightness.value())

    def modal(self, function):
        previous = self.menu_visible
        self.menu_visible = True
        try:
            return function()
        finally:
            self.menu_visible = previous

    def request(self, role, name, value):
        record("control_clicked", role=role, function=name)
        if self.controller.stopping or self.controller.writing or role in self.controller.busy:
            record("control_busy", role=role, function=name)
            return False
        adapter = self.controller.adapters[role]
        if not isinstance(adapter, BetaAdapter):
            return self.controller.request_elgin(name, value) if role == "elgin" else False
        if name not in self.controller.capabilities_for(role):
            return False
        try:
            command = adapter.proposed(name, value, self.controller.states[role])
        except (ValueError, TypeError):
            return False
        validated = adapter.is_validated(name, value)
        token = (role, name, value if name in {"fan", "mode"} else None)
        approved = validated or token in self.accepted
        if not approved:
            explanation = adapter.capabilities[name].get("evidence", "DPS e tipo do schema do próprio dispositivo; efeito físico ainda não validado.")
            text = (f"{role} · {name}\nComando LAN: {json.dumps(command, ensure_ascii=False)}\n\n"
                    f"{explanation}\nUma única escrita, com leitura antes e depois, sem repetição nem restauração automática.\n"
                    "A confirmação LAN não equivale à confirmação física. Autorizar este teste?")
            def answer(result):
                if result != QMessageBox.StandardButton.Yes:
                    record("experimental_cancelled", role=role, function=name)
                    self.controller.changed.emit()
                    return
                self.accepted.add(token)
                self._dispatch(role, name, value, command)
            return self._question("Primeiro uso experimental", text, answer)
        return self._dispatch(role, name, value, command)

    def _dispatch(self, role, name, value, approved_command):
        adapter = self.controller.adapters[role]
        try:
            if adapter.proposed(name, value, self.controller.states[role]) != approved_command:
                raise ValueError("Snapshot changed")
        except (ValueError, TypeError):
            self._notice("Estado atualizado", "O comando proposto mudou após a consulta. Revise o estado e tente novamente; nenhuma escrita foi enviada.")
            return False
        dispatched = self.controller.request_beta(role, name, value, approved=True)
        if not dispatched:
            record("control_not_dispatched", role=role, function=name)
            self.controller.changed.emit()
        return dispatched

    def choose_colour(self):
        if self._focus_dialog("colour"):
            return
        colour = self.controller.states["led"].values.get("colour")
        if not valid_colour(colour):
            return
        initial = QColor(*hsv_to_rgb(hsv16_decode(colour)))
        dialog = QColorDialog(initial, None)
        dialog.setOption(QColorDialog.ColorDialogOption.DontUseNativeDialog, True)
        dialog.setWindowTitle("Cor da fita · HSV16")
        def selected(result):
            if result == QDialog.DialogCode.Accepted:
                colour = dialog.selectedColor()
                if colour.isValid():
                    self.request("led", "colour", rgb_to_hsv16(colour.red(), colour.green(), colour.blue()))
        return self._show_dialog("colour", dialog, selected)

    def action_finished(self, role, item):
        if self.controller.stopping:
            return
        path, result = item
        if not result.get("lan_confirmed"):
            self._notice("Estado não confirmado", "A operação foi interrompida. Nenhuma escrita será repetida. Consulte o histórico e atualize o estado antes de novo teste.")
            return
        if role == "led" and valid_colour(result.get("after", {}).get("colour")):
            self.controller.settings.last_colour = result["after"]["colour"]
            try:
                self.controller.settings.save()
            except OSError:
                pass
        if result.get("classification") != "experimental":
            return
        def observed(answer):
            result["physical_confirmation"] = {QMessageBox.StandardButton.Yes: "confirmed_by_user",
                QMessageBox.StandardButton.No: "rejected_by_user"}.get(answer, "not_verified")
            temporary = path.with_suffix(".tmp")
            try:
                temporary.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
                temporary.replace(path)
            except OSError:
                self._notice("Histórico", "Não foi possível salvar a observação física no histórico local.")
        self._question("Confirmação física",
            f"A leitura LAN confirmou {json.dumps(result['command'])}.\nO resultado foi observado no aparelho ou no Smart Life?\n"
            "Sim = observado; Não = efeito diferente; Cancelar = não verificado.\nNenhuma restauração será enviada.", observed, physical=True)

    def advanced(self, role, section=None):
        key = "advanced_" + role
        if self._focus_dialog(key):
            if section in self.dialogs[key].sections:
                self.dialogs[key].scroll.ensureWidgetVisible(self.dialogs[key].sections[section])
            return self.dialogs[key]
        dialog = QDialog(None)
        dialog.setWindowTitle("Elgin · controles avançados" if role == "elgin" else "Outsmart RGBIC · controles avançados")
        dialog.setMinimumWidth(390)
        from .premium import STYLE
        dialog.setStyleSheet(STYLE)
        dialog.resize(540, 700)
        outer = QVBoxLayout(dialog)
        outer.setContentsMargins(20, 20, 20, 20)
        outer.addWidget(label("Seu clima" if role == "elgin" else "Sua iluminação", "title"))
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setSpacing(10)
        scroll.setWidget(content)
        outer.addWidget(scroll)
        dialog.scroll = scroll
        dialog.sections = {}
        def heading(title):
            widget = label(title, "section")
            dialog.sections[title] = widget
            layout.addWidget(widget)
        if role == "led":
            navigation = QHBoxLayout()
            for title, target in (("Cor", "COR"), ("Favoritos", "FAVORITOS"), ("Efeitos", "CENAS / EFEITOS")):
                button = QPushButton(title)
                button.clicked.connect(lambda checked=False, target=target: scroll.ensureWidgetVisible(dialog.sections[target]))
                navigation.addWidget(button)
            outer.insertLayout(1, navigation)
        hint = label("Controles Beta · uma ação por vez, com confirmação pela LAN.", "muted")
        hint.setWordWrap(True)
        layout.addWidget(hint)
        release = QPushButton("Liberar controles Beta")
        release.setObjectName("betaUnlock")
        release.clicked.connect(self.enable_experimental)
        layout.addWidget(release)
        controls = {}
        dialog.controls = controls
        names = {"mode": "Modo", "sleep": "Dormir", "display": "Visor", "eco": "Eco (schema)", "fan": "Ventilação"}
        for name in (("mode", "fan", "sleep", "display", "eco") if role == "elgin" else ("mode",)):
            spec = getattr(self.controller.adapters[role], "capabilities", {}).get(name)
            if not spec:
                continue
            row = QHBoxLayout()
            row.addWidget(label(names[name]), 1)
            if spec["kind"] == "choice":
                widget = ChoiceBox()
                for value, title in spec["options"].items():
                    experimental = not self.controller.adapters[role].is_validated(name, value)
                    widget.addItem(title + (" · Beta" if experimental else ""), value)
                widget.activated.connect(lambda i, n=name, w=widget: self.request(role, n, w.itemData(i)))
            else:
                widget = QPushButton("—")
                widget.clicked.connect(lambda checked=False, n=name: self.request(role, n, not self.controller.states[role].values.get(n)))
            controls[name] = widget
            row.addWidget(widget)
            layout.addLayout(row)
        if role == "elgin":
            for text in ("Oscilação · não mapeada (correspondência DPS 33 pendente)",
                         "Ionizador · não mapeado (health/DPS 106 sem correlação)", "Fungusproof · não exposto / LAN desconhecida"):
                button = QPushButton(text)
                button.setEnabled(False)
                layout.addWidget(button)
        else:
            heading("COR")
            colour = QPushButton("Selecionar cor RGB / HSV…")
            colour.clicked.connect(self.choose_colour)
            layout.addWidget(colour)
            controls["colour"] = colour
            brightness = QSlider(Qt.Orientation.Horizontal)
            brightness.setRange(1, 100)
            brightness.setObjectName("advancedBrightness")
            brightness_timer = QTimer(brightness)
            brightness_timer.setSingleShot(True)
            brightness_timer.setInterval(450)
            brightness_timer.timeout.connect(lambda: self.request("led", "brightness", brightness.value()))
            brightness.valueChanged.connect(lambda _: brightness_timer.start() if not brightness.isSliderDown() else None)
            brightness.sliderPressed.connect(brightness_timer.stop)
            brightness.sliderReleased.connect(brightness_timer.start)
            heading("BRILHO")
            layout.addWidget(label("Cor fixa · 1–100%", "muted"))
            layout.addWidget(brightness)
            controls["brightness"] = brightness
            palette = QHBoxLayout()
            for title, rgb in (("Vermelho", (255, 0, 0)), ("Verde", (0, 255, 0)), ("Azul", (0, 0, 255)), ("Branco RGB", (255, 255, 255))):
                button = QPushButton(title)
                button.clicked.connect(lambda checked=False, rgb=rgb: self.request("led", "colour", rgb_to_hsv16(*rgb)))
                palette.addWidget(button)
            layout.addLayout(palette)
            controls["palette"] = palette
            hsv_row = QHBoxLayout()
            spins = []
            for title, maximum in (("H", 360), ("S", 1000), ("V", 1000)):
                hsv_row.addWidget(label(title))
                spin = QSpinBox()
                spin.setRange(0, maximum)
                hsv_row.addWidget(spin)
                spins.append(spin)
            apply = QPushButton("Aplicar HSV")
            apply.clicked.connect(lambda: self.request("led", "colour", hsv16_encode(*(s.value() for s in spins))))
            hsv_row.addWidget(apply)
            layout.addLayout(hsv_row)
            controls["hsv"] = apply
            current = self.controller.states[role].values.get("colour")
            if valid_colour(current):
                for spin, value in zip(spins, hsv16_decode(current).values()):
                    spin.setValue(value)
            save = QPushButton("Favoritar cor fixa lida (não a animação)")
            heading("FAVORITOS")
            favorites = ChoiceBox()
            favorites.addItem("Cores favoritas…", None)
            for item in self.controller.settings.favorites:
                favorites.addItem(QColor(*hsv_to_rgb(hsv16_decode(item))).name().upper(), item)
            favorites.activated.connect(lambda i: self.request("led", "colour", favorites.itemData(i)) if favorites.itemData(i) else None)
            def favorite():
                value = self.controller.states[role].values.get("colour")
                if valid_colour(value) and value not in self.controller.settings.favorites:
                    self.controller.settings.favorites = (self.controller.settings.favorites + [value])[-12:]
                    self.controller.settings.save()
                    favorites.addItem(QColor(*hsv_to_rgb(hsv16_decode(value))).name().upper(), value)
            save.clicked.connect(favorite)
            layout.addWidget(save)
            layout.addWidget(favorites)
            controls["favorites"] = favorites
            last = QPushButton("Aplicar última cor confirmada pela LAN")
            last.clicked.connect(lambda: self.request("led", "colour", self.controller.settings.last_colour))
            layout.addWidget(last)
            controls["last"] = last
            for title, text in (("CENAS / EFEITOS", "Indisponíveis · presets do Smart Life ainda sem códigos LAN confirmados. Trocar o modo não escolhe um efeito."),
                         ("RECURSOS RGBIC", "Indisponíveis · segmentos, velocidade e direção ainda sem formato LAN confirmado."),
                         ("MÚSICA", "Presets locais não mapeados. O microfone do celular pode exigir transmissão contínua pelo app."),
                         ("OUTROS RECURSOS", "Comprimento, pixels e temporizador permanecem sem controle nesta Beta.")):
                heading(title)
                note = label(text, "muted")
                note.setWordWrap(True)
                layout.addWidget(note)
        def sync():
            release.setVisible(not self.controller.settings.enabled)
            release.setEnabled(not self.controller.stopping)
            if role == "led" and (not self.controller.settings.enabled or self.controller.stopping):
                brightness_timer.stop()
            state = self.controller.states[role]
            available = self.controller.capabilities_for(role)
            interactive = state.connection == "online" and not self.controller.writing and role not in self.controller.busy
            for name, widget in controls.items():
                canonical = "colour" if name in {"palette", "hsv", "favorites", "last"} else name
                spec = available.get(canonical, {})
                ready = (interactive and bool(spec) and state.values.get(canonical) is not None
                         and all(state.values.get(k) == v for k, v in spec.get("requires", {}).items()))
                if name == "last":
                    ready = ready and valid_colour(self.controller.settings.last_colour)
                if isinstance(widget, QHBoxLayout):
                    for i in range(widget.count()):
                        widget.itemAt(i).widget().setEnabled(ready)
                else:
                    widget.setEnabled(ready)
                    widget.setToolTip("Habilite Beta em Configurações" if not spec else
                        "Offline ou operação em andamento" if not interactive else
                        "Selecione Colour e ligue a fita para ajustar cor/brilho" if not ready and role == "led" else
                        "Condições de operação não atendidas" if not ready else "Ação explícita; nenhuma escrita automática")
                if isinstance(widget, QSlider) and not widget.isSliderDown():
                    if not brightness_timer.isActive():
                        widget.blockSignals(True)
                        widget.setValue(max(1, state.values.get("brightness", 1)))
                        widget.blockSignals(False)
                if isinstance(widget, QComboBox) and name != "favorites":
                    if not widget.view().isVisible():
                        widget.setCurrentIndex(widget.findData(state.values.get(name)))
                    allowed = spec.get("options", {})
                    for i in range(widget.count()):
                        widget.model().item(i).setEnabled(widget.itemData(i) in allowed)
                elif isinstance(widget, QPushButton) and name in {"sleep", "display", "eco"}:
                    value = state.values.get(name)
                    widget.setText("Ligado · desligar (Beta)" if value is True else "Desligado · ligar (Beta)" if value is False else "Estado desconhecido")
        self.controller.changed.connect(sync)
        sync()
        def closed(_):
            self.controller.changed.disconnect(sync)
            if role == "led":
                brightness_timer.stop()
        result = self._show_dialog(key, dialog, closed)
        if section in dialog.sections:
            QTimer.singleShot(0, lambda: scroll.ensureWidgetVisible(dialog.sections[section]))
        return result

    def settings_dialog(self):
        if self._focus_dialog("settings"):
            return self.dialogs["settings"]
        dialog = QDialog(None)
        dialog.setWindowTitle("Smart Tray · Configurações / Sobre")
        dialog.resize(530, 470)
        layout = QVBoxLayout(dialog)
        layout.addWidget(label("Smart Tray " + VERSION, "title"))
        layout.addWidget(label("LAN · DPAPI · instância única · nenhuma escrita na inicialização", "muted"))
        enabled = QCheckBox("Habilitar controles experimentais Beta")
        enabled.setChecked(self.controller.settings.enabled)
        def changed(value):
            previous = self.controller.settings.enabled
            self.controller.settings.enabled = value
            try:
                self.controller.settings.save()
            except OSError:
                self.controller.settings.enabled = previous
                enabled.blockSignals(True)
                enabled.setChecked(previous)
                enabled.blockSignals(False)
                self._notice("Configurações", "Não foi possível salvar a preferência local.")
            self.debounce.stop()
            self.controller.changed.emit()
        enabled.toggled.connect(changed)
        layout.addWidget(enabled)
        layout.addWidget(label("Histórico local: leitura LAN e confirmação física são registradas separadamente.", "muted"))
        history = QPlainTextEdit()
        history.setReadOnly(True)
        directory = self.controller.settings.directory / "operations"
        records = []
        if directory.exists():
            for path in sorted(directory.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)[:40]:
                try:
                    item = json.loads(path.read_text(encoding="utf-8"))
                    # Display only journals generated by the typed Beta writer.
                    if item.get("version") in {VERSION, "0.4.1-beta.2", "0.4.0-beta.1"}:
                        records.append({k: item.get(k) for k in ("timestamp", "role", "function", "command", "result", "lan_confirmed", "physical_confirmation")})
                    elif item.get("role") in {"led", "novadigital"} and type(item.get("requested")) is bool:
                        role, dp = item["role"], item.get("dp")
                        if (role == "led" and dp == 20) or (role == "novadigital" and dp in (1, 2)):
                            result = item.get("result", {})
                            records.append({"timestamp": item.get("timestamp"), "role": role,
                                "command": {str(dp): item["requested"]}, "classification": "validated",
                                "lan_confirmed": result.get("state_confirmed") is True,
                                "physical_confirmation": "not_requested_previously_validated"})
                except Exception:
                    continue
        history.setPlainText(json.dumps(records, ensure_ascii=False, indent=2) if records else "Nenhuma ação Beta registrada.")
        layout.addWidget(history)
        layout.addWidget(label("Para relatar: versão, função, valor solicitado, resultado LAN e observação física.\nNão envie credenciais. Os perfis validados são preservados.", "muted"))
        return self._show_dialog("settings", dialog)

    def show_at_tray(self, tray_rect):
        super().show_at_tray(tray_rect)
        # Keep the popup compact; advanced controls live in their own dialog.
        from .ui import panel_position
        from PySide6.QtWidgets import QApplication
        screen = QApplication.screenAt(self.geometry().center()) or QApplication.primaryScreen()
        anchor = tray_rect.center() if not tray_rect.isEmpty() else self.geometry().bottomRight()
        self.setGeometry(panel_position(screen.availableGeometry(), anchor, 460, 860))
        for key in ("confirmation", "notice", "colour"):
            if self._focus_dialog(key):
                break
