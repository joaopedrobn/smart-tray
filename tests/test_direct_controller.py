from pathlib import Path
from unittest.mock import Mock
import threading
import pytest
from smart_tray.adapters import DeviceState
from smart_tray.beta import BetaSettings
from smart_tray.direct_controller import DirectController
from smart_tray.interactive_adapters import load_interactive_adapters
from test_interface import wait_until

ROOT = Path(__file__).parent / "fixtures/config"


@pytest.fixture
def direct(qt_app, tmp_path):
    adapters = load_interactive_adapters(ROOT)
    values = {'elgin': {'power': True, 'mode': 'cold', 'temperature': 24, 'fan': 'low'},
              'led': {20: True, 'mode': 'scene', 'colour': '000003e803e8', 'brightness': 100},
              'novadigital': {1: True, 2: True}}
    threads = []
    for role, adapter in adapters.items():
        base = getattr(adapter, 'base', adapter)
        base.store = Mock()
        base.store.load.side_effect = AssertionError('No credentials in test')
        base.factory = Mock(side_effect=AssertionError('No network in test'))
        adapter.read = Mock(side_effect=lambda role=role: DeviceState('online', values[role].copy()))
        adapter.write = Mock()
        if role in ('elgin', 'led'):
            def execute(name, before, value, *, experimental_approved, role=role):
                threads.append(threading.get_ident())
                values[role][name] = value
                return DeviceState('online', values[role].copy())
            adapter.execute = Mock(side_effect=execute)
    settings = BetaSettings(tmp_path)
    controller = DirectController(adapters, settings)
    controller.start()
    wait_until(qt_app, lambda: not controller.busy)
    yield controller, adapters, values, threads
    controller.stop()
    controller.pool.waitForDone(3000)
    qt_app.processEvents()
    for adapter in adapters.values():
        base = getattr(adapter, 'base', adapter)
        base.store.load.assert_not_called()
        base.factory.assert_not_called()


def enable(controller):
    assert controller.set_experimental_enabled(True, risk_acknowledged=True)


def test_start_and_reload_never_control_devices(direct):
    controller, adapters, _, _ = direct
    for role in ('elgin', 'led'):
        adapters[role].execute.assert_not_called()
    assert not controller.request_colour('00f003e803e8')
    assert not controller.set_experimental_enabled(True)
    assert not controller.settings.enabled
    enable(controller)
    assert BetaSettings(controller.settings.directory).enabled
    for role in ('elgin', 'led'):
        adapters[role].execute.assert_not_called()


def test_persistent_opt_in_allows_direct_operations_without_per_click_prompts(direct, qt_app):
    controller, adapters, _, threads = direct
    enable(controller)
    assert controller.request_direct('elgin', 'fan', 'high')
    wait_until(qt_app, lambda: not controller.writing)
    assert controller.request_direct('elgin', 'fan', 'low')
    wait_until(qt_app, lambda: not controller.writing)
    assert adapters['elgin'].execute.call_count == 2
    assert all(t != threading.get_ident() for t in threads)


def test_colour_click_changes_mode_then_colour_only_after_confirmation(direct, qt_app):
    controller, adapters, values, _ = direct
    enable(controller)
    assert controller.request_colour('00f003e803e8')
    assert not controller.request_colour('007803e803e8')  # No concurrent queue.
    wait_until(qt_app, lambda: not controller.writing and controller.colour_sequence is None)
    calls = adapters['led'].execute.call_args_list
    assert [(c.args[0], c.args[2]) for c in calls] == [('mode', 'colour'), ('colour', '00f003e803e8')]
    assert calls[1].args[1].values['mode'] == 'colour'
    assert all(c.kwargs['experimental_approved'] is True for c in calls)
    assert values['led']['colour'] == '00f003e803e8'
    adapters['elgin'].execute.assert_not_called()
    adapters['novadigital'].write.assert_not_called()


@pytest.mark.parametrize('fault', ['mode_unknown', 'power_changed', 'disabled_between', 'colour_unknown'])
def test_colour_sequence_stops_on_uncertain_or_changed_conditions(direct, qt_app, fault):
    controller, adapters, values, _ = direct
    enable(controller)
    def execute(name, before, value, **kwargs):
        if name == 'mode':
            values['led']['mode'] = value
            if fault == 'mode_unknown':
                return DeviceState('unknown', {})
            if fault == 'power_changed':
                values['led'][20] = False
            if fault == 'disabled_between':
                controller.settings.enabled = False
            return DeviceState('online', values['led'].copy())
        return DeviceState('unknown', {})
    adapters['led'].execute.side_effect = execute
    assert controller.request_colour('00f003e803e8')
    wait_until(qt_app, lambda: not controller.writing and controller.colour_sequence is None)
    assert adapters['led'].execute.call_count == (2 if fault == 'colour_unknown' else 1)
    qt_app.processEvents()
    assert adapters['led'].execute.call_count == (2 if fault == 'colour_unknown' else 1)


def test_brightness_in_scene_preserves_hue_saturation_and_uses_one_target(direct, qt_app):
    controller, adapters, values, _ = direct
    enable(controller)
    values['led']['colour'] = '007803e803e8'
    controller.states['led'] = DeviceState('online', values['led'].copy())
    assert controller.request_brightness(25)
    wait_until(qt_app, lambda: not controller.writing and not controller.colour_sequence)
    calls = adapters['led'].execute.call_args_list
    assert [(c.args[0], c.args[2]) for c in calls] == [('mode', 'colour'), ('colour', '007803e800fa')]


def test_stopping_mid_sequence_never_continues(direct, qt_app):
    controller, adapters, values, _ = direct
    enable(controller)
    gate = threading.Event()
    def delayed(*args, **kwargs):
        gate.wait(2)
        values['led']['mode'] = 'colour'
        return DeviceState('online', values['led'].copy())
    adapters['led'].execute.side_effect = delayed
    assert controller.request_colour('00f003e803e8')
    controller.stop()
    gate.set()
    controller.pool.waitForDone(3000)
    qt_app.processEvents()
    assert adapters['led'].execute.call_count <= 1


@pytest.mark.parametrize('name,value', [('swing', True), ('fan', 'invented'), ('mode', 'hot')])
def test_unknown_values_remain_blocked_after_enabling(direct, name, value):
    controller, adapters, _, _ = direct
    enable(controller)
    assert not controller.request_direct('elgin', name, value)
    adapters['elgin'].execute.assert_not_called()


def test_labels_and_validated_controls_work_without_experimental_suffixes(direct, qt_app):
    controller, adapters, _, _ = direct
    assert controller.request_direct('elgin', 'fan', 'mid')
    wait_until(qt_app, lambda: not controller.writing)
    assert controller.request_direct('elgin', 'temperature', 25)
    wait_until(qt_app, lambda: not controller.writing)
    enable(controller)
    for role in ('led', 'elgin'):
        for spec in controller.capabilities_for(role).values():
            assert all('β' not in title and 'Beta' not in title for title in spec.get('options', {}).values())
