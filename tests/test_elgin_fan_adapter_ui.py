from unittest.mock import Mock
import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from smart_tray.adapters import ElginLanAdapter
from test_elgin_adapter import setup
from test_interface import fixtures, wait_until, finish
from test_elgin_interface import TemperatureAdapter


def fan_adapter(tmp_path):
    original, device, store = setup(tmp_path)
    r, p = original.record, original.profile
    r["oem_fan_evidence"] = {"bidirectional_manual_verified": True, "model_code": "windspeed", "model_type": "Enum",
                             "model_access": "rw", "model_range": ["low", "mid", "high"]}
    p["observed_fan_settings"] = {"low": {}, "mid": {}}
    p["confirmed_commands"]["windspeed"] = {"dp": 5, "transport": "lan", "physical_confirmed": True, "values": ["mid"]}
    return ElginLanAdapter(r, p, store, Mock(return_value=device), tmp_path), device, store


def test_adapter_exposes_only_mid_as_validated_fan_target(tmp_path):
    adapter, device, store = fan_adapter(tmp_path)
    assert adapter.capabilities["fan"]["options"] == {"mid": "Média"}
    assert adapter.capabilities["fan"]["observed_options"] == {"low": "Baixa", "mid": "Média"}
    device.status.return_value = {"dps": {"1": True, "2": 240, "4": "cold", "5": "mid"}}
    assert adapter.read().values["fan"] == "mid"
    device._send_receive_quick.assert_not_called()
    store.save.assert_not_called()


@pytest.mark.parametrize("value", ["low", "high", "auto", "mute", "strength"])
def test_other_fan_targets_rejected_before_credentials_or_traffic(tmp_path, value):
    adapter, device, store = fan_adapter(tmp_path)
    with pytest.raises(ValueError):
        adapter.command_from_state("fan", "mid", value)
    store.load.assert_not_called()
    device._send_receive_quick.assert_not_called()


def test_validated_fan_click_sends_single_dp5_with_no_restoration(tmp_path, monkeypatch):
    monkeypatch.setattr("smart_tray.elgin_control.time.sleep", lambda _: None)
    adapter, device, _ = fan_adapter(tmp_path)
    device.status.side_effect = [{"dps": {"1": True, "2": 240, "4": "cold", "5": "low"}},
                                 {"dps": {"1": True, "2": 240, "4": "cold", "5": "mid"}}]
    device._send_receive_quick.return_value = True
    state = adapter.command_from_state("fan", "low", "mid")
    assert state.values["fan"] == "mid" and state.values["temperature"] == 24
    assert device.generate_payload.call_args.args[1] == {"5": "mid"}
    device._send_receive_quick.assert_called_once()


def test_selector_displays_low_but_disables_its_write_and_sends_only_mid(qt_app):
    adapters, controller, panel = fixtures()
    adapter = TemperatureAdapter()
    adapter.capabilities = {**adapter.capabilities, "fan": {"validated": True, "kind": "choice",
        "options": {"mid": "Média"}, "observed_options": {"low": "Baixa", "mid": "Média"},
        "requires": {"power": True, "mode": "cold", "temperature": 24}}}
    adapter.values["fan"] = "low"
    adapters["elgin"] = adapter
    controller.start()
    wait_until(qt_app, lambda: not controller.busy)
    combo = panel.elgin.fan
    assert combo.currentText() == "Baixa" and combo.isEnabled()
    assert not combo.model().item(combo.findData("low")).isEnabled()
    assert combo.model().item(combo.findData("mid")).isEnabled()
    assert not adapter.commands
    assert not controller.request_elgin("fan", "low") and not controller.request_elgin("fan", "high")
    combo.activated.emit(combo.findData("mid"))
    wait_until(qt_app, lambda: not controller.busy)
    assert adapter.commands == [("fan", "low", "mid")]
    assert panel.elgin.fan.currentText() == "Média"
    assert not adapters["led"].writes and not adapters["novadigital"].writes
    finish(controller, panel)
