"""Reactive GUI facade. Every device operation is delegated to async workers."""
import json
from PySide6.QtCore import QObject, Property, Signal, Slot, QTimer
from .beta import VERSION, valid_colour
from .led_research import hsv16_decode, hsv16_encode, hsv_to_rgb
from .windows import Startup
from .rgbic_capture import SceneReader, SCENES
from .rgbic_recorder import SceneRecorder


class QuickBridge(QObject):
    changed = Signal()
    pageChanged = Signal()
    toast = Signal(str)
    dragStarted = Signal(int, int)
    dragMoved = Signal(int, int)
    dragEnded = Signal()
    hideRequested = Signal()
    minimizeRequested = Signal()
    resetRequested = Signal()
    discoveryChanged = Signal()
    discoveryRequested = Signal()

    def __init__(self, controller, desktop, root, parent=None, *, development_tools=True):
        super().__init__(parent)
        self.controller, self.desktop, self.root = controller, desktop, root
        self._page = 'climate'
        self._visible = False
        self.drafts = {}
        self._history = []
        self.startup = Startup()
        self.development_tools = development_tools
        led_base = getattr(controller.adapters['led'], 'base', controller.adapters['led'])
        self.recorder = SceneRecorder(controller, SceneReader(controller.adapters['led']),
            controller.settings.directory / 'rgbic-scenes',
            root / 'diagnostics/led-research/schema-current.json', self) if development_tools and hasattr(led_base, 'record') else None
        if self.recorder:
            self.recorder.changed.connect(self.discoveryChanged)
        self.temperature_timer = QTimer(self)
        self.brightness_timer = QTimer(self)
        for timer in (self.temperature_timer, self.brightness_timer):
            timer.setSingleShot(True)
            timer.setInterval(400)
        self.temperature_timer.timeout.connect(self._send_temperature)
        self.brightness_timer.timeout.connect(self._send_brightness)
        controller.changed.connect(self._state_changed)
        controller.notice.connect(self.toast)
        controller.action_finished.connect(self._operation_finished)

    def _state_changed(self):
        if self.controller.stopping:
            self.temperature_timer.stop()
            self.brightness_timer.stop()
            self.drafts.clear()
        for name, role, timer in (('temperature', 'elgin', self.temperature_timer), ('brightness', 'led', self.brightness_timer)):
            if role not in self.controller.busy and not timer.isActive() and not (role == 'led' and self.controller.colour_sequence):
                self.drafts.pop(name, None)
        self.changed.emit()
        self.discoveryChanged.emit()

    @Property('QVariantMap', notify=discoveryChanged)
    def sceneDiscovery(self):
        return self.recorder.view() if self.recorder else {}

    @Property(bool, constant=True)
    def developmentToolsEnabled(self):
        return self.development_tools

    @Property('QStringList', constant=True)
    def discoverySceneNames(self):
        return list(SCENES)

    @Slot()
    def openSceneDiscovery(self):
        if not self.recorder:
            return
        self.page = 'light'
        self.discoveryRequested.emit()

    @Slot(int)
    def selectDiscoveryScene(self, index):
        if not self.recorder:
            return
        self.recorder.select(index)

    @Slot()
    def startSceneCapture(self):
        if not self.recorder:
            return
        if not self.recorder.start():
            self.toast.emit('Aguarde a consulta em andamento antes de iniciar a captura.')

    @Slot()
    def concludeSceneCapture(self):
        if not self.recorder:
            return
        self.recorder.conclude()

    @Slot()
    def nextDiscoveryScene(self):
        if not self.recorder:
            return
        self.recorder.next()

    @Slot()
    def cancelSceneCapture(self):
        if not self.recorder:
            return
        self.recorder.cancel()

    @Slot()
    def openScenesFolder(self):
        if not self.recorder:
            return
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices
        try:
            self.recorder.directory.mkdir(parents=True, exist_ok=True)
        except OSError:
            self.toast.emit('Não foi possível abrir o catálogo local.')
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.recorder.directory)))

    @Property('QVariantMap', notify=changed)
    def state(self):
        result = {}
        for role, state in self.controller.states.items():
            values = state.values
            online = state.connection == 'online'
            busy = role in self.controller.busy
            interactive = online and not busy and not self.controller.writing and not self.controller.stopping
            capabilities = self.controller.capabilities_for(role)
            item = {'online': online, 'busy': busy, 'connection': state.connection,
                    'message': 'Atualizando…' if busy else '' if online else 'Sem confirmação · Atualizar',
                    'power': values.get(20) if role == 'led' else values.get('power'),
                    'temperature': values.get('temperature'), 'ambient': values.get('ambient_temperature'),
                    'mode': values.get('mode'), 'fan': values.get('fan'), 'sleep': values.get('sleep'),
                    'display': values.get('display'), 'eco': values.get('eco')}
            for name in ('power', 'temperature', 'mode', 'fan', 'sleep', 'display', 'eco'):
                spec = capabilities.get(name, {})
                item[name + 'Enabled'] = bool(interactive and spec and values.get(name) is not None
                    and all(values.get(k) == expected for k, expected in spec.get('requires', {}).items()))
                options = spec.get('observed_options', spec.get('options', {}))
                item[name + 'Options'] = [{'text': title, 'value': value,
                    'enabled': value in spec.get('options', {})} for value, title in options.items()]
            item['modeTitle'] = {'cold': 'Resfriar', 'wet': 'Desumidificar', 'wind': 'Ventilar', 'auto': 'Automático',
                'colour': 'Cor fixa', 'scene': 'Efeito não editável', 'music': 'Efeito não editável', 'white': 'Branco'}.get(values.get('mode'), 'Não disponível')
            item['fanTitle'] = {'mute': 'Silêncio', 'low': 'Baixa', 'mid': 'Média', 'high': 'Alta', 'auto': 'Auto', 'strength': 'Turbo'}.get(values.get('fan'), 'Não disponível')
            item['temperatureDraft'] = self.drafts.get('temperature', values.get('temperature'))
            if role == 'led':
                colour = values.get('colour')
                known = valid_colour(colour)
                hsv = hsv16_decode(colour) if known else {'h': 0, 's': 0, 'v': 0}
                item.update(colourKnown=known, colour=colour if known else '', hsv=hsv,
                    colourHex=('#%02x%02x%02x' % tuple(hsv_to_rgb(hsv))) if known else '#485064',
                    brightness=values.get('brightness'), brightnessDraft=self.drafts.get('brightness', values.get('brightness')),
                    colourEnabled=bool(interactive and known and values.get(20) is True and 'colour' in capabilities
                        and values.get('mode') in capabilities.get('mode', {}).get('options', {})),
                    brightnessEnabled=bool(interactive and known and values.get(20) is True and 'brightness' in capabilities
                        and values.get('mode') in capabilities.get('mode', {}).get('options', {})),
                    powerEnabled=self.controller.can_write(role, 20),
                    transitioning=bool(self.controller.colour_sequence))
            if role == 'novadigital':
                item['channels'] = [{'number': dp, 'known': type(values.get(dp)) is bool,
                    'power': values.get(dp), 'enabled': self.controller.can_write(role, dp)} for dp in (1, 2)]
            result[role] = item
        return result

    @Property(str, notify=pageChanged)
    def page(self):
        return self._page

    @page.setter
    def page(self, value):
        if value in {'climate', 'light', 'switch', 'settings'} and value != self._page:
            self._page = value
            if value == 'settings':
                self._load_history()
            self.pageChanged.emit()

    @Property(bool, notify=changed)
    def panelVisible(self):
        return self._visible

    def set_visible(self, value):
        self._visible = value
        self.changed.emit()

    @Property(bool, notify=changed)
    def experimentalEnabled(self):
        return self.controller.settings.enabled

    @Property(bool, notify=changed)
    def reducedMotion(self):
        return self.desktop.reduce_motion

    @Property(str, constant=True)
    def version(self):
        return VERSION

    @Property('QVariantList', notify=changed)
    def favorites(self):
        return [{'value': value, 'colour': '#%02x%02x%02x' % tuple(hsv_to_rgb(hsv16_decode(value)))}
                for value in self.controller.settings.favorites]

    @Property(bool, notify=changed)
    def startupEnabled(self):
        return self.startup.enabled()

    @Property('QVariantList', notify=changed)
    def history(self):
        return self._history

    def _load_history(self):
        directory = self.controller.settings.directory / 'operations'
        entries = []
        names = {'power': 'Energia', 'temperature': 'Temperatura', 'fan': 'Ventilação', 'mode': 'Modo',
                 'colour': 'Cor', 'brightness': 'Brilho', 'sleep': 'Dormir', 'display': 'Visor', 'eco': 'Eco'}
        roles = {'elgin': 'Clima', 'led': 'Luz', 'novadigital': 'Interruptor'}
        try:
            paths = sorted(directory.glob('*.json'), key=lambda p: p.stat().st_mtime, reverse=True)[:20]
        except OSError:
            paths = []
        for path in paths:
            try:
                data = json.loads(path.read_text(encoding='utf-8'))
                if not isinstance(data, dict) or data.get('role') not in roles:
                    continue
                role, function = data['role'], data.get('function', 'power')
                if function not in names:
                    continue
                confirmed = data.get('lan_confirmed') is True
                if isinstance(data.get('result'), dict):
                    confirmed = data['result'].get('state_confirmed') is True
                physical = data.get('physical_confirmation') == 'confirmed_by_user'
                entries.append({'title': roles[role] + ' · ' + names[function],
                    'detail': ('Confirmado' if confirmed else 'Sem confirmação') +
                    (' · observado no aparelho' if physical else ' · observação física não registrada')})
            except (OSError, ValueError):
                continue
        self._history = entries
        self.changed.emit()

    @Slot(str)
    def navigate(self, page):
        self.page = page

    def _feedback(self, accepted):
        if not accepted:
            self.toast.emit('Ação indisponível ou valor já selecionado. Confira a conexão e as configurações.')
        return accepted

    @Slot(str, str, 'QVariant', result=bool)
    def command(self, role, name, value):
        if role not in {'elgin', 'led'}:
            return False
        return self._feedback(self.controller.request_direct(role, name, value))

    @Slot(str, int, result=bool)
    def toggle(self, role, channel):
        if (role, channel) not in {('led', 20), ('novadigital', 1), ('novadigital', 2)}:
            return False
        return self._feedback(self.controller.toggle(role, channel))

    @Slot(int, int, int, result=bool)
    def selectHsv(self, hue, saturation, value):
        try:
            colour = hsv16_encode(hue, saturation, value)
        except (ValueError, TypeError):
            return False
        return self._feedback(self.controller.request_colour(colour))

    @Slot(str, result=bool)
    def selectColour(self, colour):
        return self._feedback(self.controller.request_colour(colour))

    @Slot(float)
    def scheduleTemperature(self, value):
        if not self.state['elgin']['temperatureEnabled'] or not float(value).is_integer() or not 16 <= value <= 32:
            return
        self.drafts['temperature'] = int(value)
        self.temperature_timer.start()
        self.changed.emit()

    def _send_temperature(self):
        value = self.drafts.get('temperature')
        if value is not None:
            if not self.controller.request_direct('elgin', 'temperature', value):
                self.drafts.pop('temperature', None)
                self.changed.emit()

    @Slot(float)
    def scheduleBrightness(self, value):
        if not self.state['led']['brightnessEnabled'] or not float(value).is_integer() or not 1 <= value <= 100:
            return
        self.drafts['brightness'] = int(value)
        self.brightness_timer.start()
        self.changed.emit()

    def _send_brightness(self):
        value = self.drafts.get('brightness')
        if value is not None:
            if not self.controller.request_brightness(value):
                self.drafts.pop('brightness', None)
                self.changed.emit()

    @Slot(bool, bool, result=bool)
    def enableExperimental(self, value, acknowledged):
        self.temperature_timer.stop()
        self.brightness_timer.stop()
        self.drafts.clear()
        return self.controller.set_experimental_enabled(value, risk_acknowledged=acknowledged)

    @Slot(bool)
    def reduceMotion(self, value):
        previous = self.desktop.reduce_motion
        self.desktop.reduce_motion = value
        try:
            self.desktop.save()
        except OSError:
            self.desktop.reduce_motion = previous
            self.toast.emit('Não foi possível salvar a preferência.')
        self.changed.emit()

    @Slot(bool)
    def setStartup(self, value):
        try:
            self.startup.set_enabled(value, self.root)
        except Exception:
            self.toast.emit('Não foi possível alterar a inicialização.')
        self.changed.emit()

    @Slot()
    def favorite(self):
        colour = self.controller.states['led'].values.get('colour')
        if not valid_colour(colour):
            return
        previous = self.controller.settings.favorites[:]
        if colour not in previous:
            self.controller.settings.favorites = (previous + [colour])[-12:]
            try:
                self.controller.settings.save()
            except OSError:
                self.controller.settings.favorites = previous
                self.toast.emit('Não foi possível salvar a cor.')
        self.changed.emit()

    @Slot()
    def refresh(self):
        self.controller.refresh()

    @Slot(int, int)
    def beginDrag(self, x, y):
        self.dragStarted.emit(x, y)

    @Slot(int, int)
    def moveDrag(self, x, y):
        self.dragMoved.emit(x, y)

    @Slot()
    def endDrag(self):
        self.dragEnded.emit()

    @Slot()
    def hide(self):
        self.hideRequested.emit()

    @Slot()
    def minimize(self):
        self.minimizeRequested.emit()

    @Slot()
    def resetPosition(self):
        self.resetRequested.emit()

    def _operation_finished(self, role, item):
        path, result = item
        if not result.get('lan_confirmed'):
            self.toast.emit('Estado não confirmado. Atualize para consultar; o comando não será repetido.')
        elif role == 'led' and valid_colour(result.get('after', {}).get('colour')):
            self.controller.settings.last_colour = result['after']['colour']
            try:
                self.controller.settings.save()
            except OSError:
                pass
        if self._page == 'settings':
            self._load_history()
