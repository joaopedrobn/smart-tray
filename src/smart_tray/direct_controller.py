"""Direct interaction policy for the next frontend, with persistent opt-in.

The existing evidence-bound adapters still perform every fresh-read guard,
single write and confirmation. This layer never creates LAN payloads.
"""
from PySide6.QtCore import Signal, Slot
from .beta import BetaAdapter, valid_colour
from .beta_controller import BetaController
from .led_research import hsv16_decode, hsv16_encode


class DirectController(BetaController):
    notice = Signal(str)

    def __init__(self, *args, **kwargs):
        self.colour_sequence = None
        self.led_observer = None
        super().__init__(*args, **kwargs)

    def reserve_led_observation(self, owner):
        if (self.stopping or self.writing or self.colour_sequence
                or self.led_observer is not None or 'led' in self.busy):
            return False
        # Reserve the existing per-device busy gate for the entire read-only
        # session. Polling and all LED writers already honor this gate.
        self.led_observer = owner
        self.busy.add('led')
        self.changed.emit()
        return True

    def release_led_observation(self, owner):
        if self.led_observer is owner:
            self.led_observer = None
            self.busy.discard('led')
            self.changed.emit()

    def capabilities_for(self, role):
        result = super().capabilities_for(role)
        # UI suffixes were deliberately appended by the previous controller;
        # this is not an encoding or font problem.
        labels = {'white': 'Branco', 'colour': 'Cor fixa', 'scene': 'Cena', 'music': 'Música',
                  'cold': 'Resfriar', 'wet': 'Desumidificar', 'wind': 'Ventilar', 'auto': 'Auto',
                  'mute': 'Silêncio', 'low': 'Baixa', 'mid': 'Média', 'high': 'Alta', 'strength': 'Turbo'}
        for name, spec in result.items():
            for key in ('options', 'observed_options'):
                if key in spec:
                    spec = dict(spec)
                    spec[key] = {value: labels.get(value, title.removesuffix(' · β'))
                                 for value, title in spec[key].items()}
            result[name] = spec
        return result

    def set_experimental_enabled(self, enabled, *, risk_acknowledged=False):
        if type(enabled) is not bool or self.stopping:
            return False
        if enabled and not self.settings.enabled and risk_acknowledged is not True:
            return False
        previous = self.settings.enabled
        self.settings.enabled = enabled
        try:
            self.settings.save()
        except OSError:
            self.settings.enabled = previous
            self.notice.emit('Não foi possível salvar a preferência.')
            return False
        self.changed.emit()
        return True

    def request_direct(self, role, name, value):
        if role not in self.adapters or self.colour_sequence:
            return False
        return self.request_beta(role, name, value, approved=self.settings.enabled)

    def request_colour(self, value):
        adapter = self.adapters.get('led')
        state = self.states['led']
        if (not isinstance(adapter, BetaAdapter) or not self.settings.enabled or not valid_colour(value)
                or self.stopping or self.writing or self.colour_sequence or 'led' in self.busy
                or state.connection != 'online' or state.values.get(20) is not True):
            return False
        available = self.capabilities_for('led')
        if 'colour' not in available or not valid_colour(state.values.get('colour')):
            return False
        if state.values.get('mode') == 'colour':
            return self.request_beta('led', 'colour', value, approved=True)
        modes = available.get('mode', {}).get('options', {})
        if 'colour' not in modes or state.values.get('mode') not in modes:
            return False
        self.colour_sequence = {'target': value, 'stage': 'mode'}
        if not self.request_beta('led', 'mode', 'colour', approved=True):
            self.colour_sequence = None
            return False
        return True

    def request_brightness(self, percent):
        if type(percent) is not int or not 1 <= percent <= 100:
            return False
        state = self.states['led']
        if state.values.get('mode') == 'colour':
            return self.request_direct('led', 'brightness', percent)
        if not valid_colour(state.values.get('colour')):
            return False
        hsv = hsv16_decode(state.values['colour'])
        return self.request_colour(hsv16_encode(hsv['h'], hsv['s'], percent * 10))

    @Slot(str, object)
    def _completed(self, role, state):
        sequence = self.colour_sequence if role == 'led' else None
        super()._completed(role, state)
        if not sequence:
            return
        if (self.stopping or not self.settings.enabled or state.connection != 'online'
                or state.values.get(20) is not True or state.values.get('mode') != 'colour'):
            self.colour_sequence = None
            self.notice.emit('Cor não confirmada. Nenhum comando será repetido.')
            self.changed.emit()
            return
        if sequence['stage'] == 'mode' and state.values.get('colour') != sequence['target']:
            sequence['stage'] = 'colour'
            if self.request_beta('led', 'colour', sequence['target'], approved=True):
                return
        self.colour_sequence = None
        if state.values.get('colour') != sequence['target']:
            self.notice.emit('Cor não confirmada. O modo pode ter mudado; atualize o estado.')
        self.changed.emit()

    def stop(self):
        self.colour_sequence = None
        super().stop()
