"""Simulation transport for GUI validation, with LAN and DPAPI prohibited."""
import threading
from PySide6.QtCore import QObject
from unittest.mock import Mock
from .adapters import DeviceState
from .interactive_adapters import load_interactive_adapters
from .led_research import hsv16_decode


def find_item(window, name):
    item = window.rootObject().findChild(QObject, name)
    if item:
        return item
    def visit(parent):
        for child in parent.childItems():
            if child.objectName() == name:
                return child
            found = visit(child)
            if found:
                return found
        return None
    return visit(window.contentItem())


def simulation(root):
    values = {'elgin': {'power': True, 'temperature': 24, 'ambient_temperature': 21, 'mode': 'cold',
                       'fan': 'low', 'sleep': False, 'display': True, 'eco': False},
              'led': {20: True, 'mode': 'scene', 'colour': '000003e803e8', 'brightness': 100},
              'novadigital': {1: True, 2: False}}
    commands, threads = [], []
    adapters = load_interactive_adapters(root)
    for role, adapter in adapters.items():
        base = getattr(adapter, 'base', adapter)
        base.store = Mock()
        base.store.load.side_effect = AssertionError('GUI simulation cannot access credentials')
        base.factory = Mock(side_effect=AssertionError('GUI simulation cannot access LAN'))
        def read(role=role):
            threads.append(threading.get_ident())
            return DeviceState('online', values[role].copy())
        adapter.read = Mock(side_effect=read)
        def write(dp, before, value, role=role):
            threads.append(threading.get_ident())
            commands.append({'role': role, 'command': {str(dp): value}})
            values[role][dp] = value
            return DeviceState('online', values[role].copy())
        adapter.write = Mock(side_effect=write)
        if role != 'novadigital':
            def execute(name, before, value, *, experimental_approved, role=role, adapter=adapter):
                threads.append(threading.get_ident())
                adapter.validate(name, value)
                if not adapter.is_validated(name, value) and not experimental_approved:
                    raise AssertionError('Missing persistent permission')
                commands.append({'role': role, 'function': name, 'command': adapter.proposed(name, value, before)})
                values[role][name] = value
                if name == 'brightness':
                    values[role]['colour'] = commands[-1]['command']['24']
                if name in {'brightness', 'colour'}:
                    values[role]['brightness'] = round(hsv16_decode(values[role]['colour'])['v'] / 10)
                return DeviceState('online', values[role].copy())
            adapter.execute = Mock(side_effect=execute)
    return adapters, values, commands, threads
