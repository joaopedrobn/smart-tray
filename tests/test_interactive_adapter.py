from smart_tray.interactive_adapters import InteractiveAdapter
from test_beta import make_adapter, elgin_raw


def test_intentional_temperature_target_is_one_scaled_write(tmp_path, monkeypatch):
    monkeypatch.setattr('smart_tray.beta.time.sleep', lambda _: None)
    base_adapter, device = make_adapter('elgin', tmp_path)
    adapter = InteractiveAdapter(base_adapter.base, base_adapter.root)
    device.status.side_effect = [elgin_raw(), elgin_raw(**{'2': 270})]
    state = adapter._state(elgin_raw(), 'synthetic-secret-123456789')
    result = adapter.execute('temperature', state, 27)
    assert result.connection == 'online' and result.values['temperature'] == 27
    assert device.generate_payload.call_args.args[1] == {'2': 270}
    device._send_receive_quick.assert_called_once()
    assert device.status.call_count == 2
    adapter.base.store.save.assert_not_called()
