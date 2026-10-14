"""Independent adapters. No cloud control, provisioning or credential writes."""
from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import uuid

from .control_validation import change_once, make_device, verify_target, exclusive_write_lock
from . import elgin_control
from .diagnostic import quiet
from .security import CredentialStore


@dataclass(frozen=True)
class DeviceState:
    connection: str = "unknown"
    values: dict = field(default_factory=dict)
    message: str = "Consultando estado…"
    checked_at: str | None = None


class TuyaAdapter:
    role = ""
    channels = {}

    def __init__(self, record, profile, store=None, factory=make_device, change=change_once, journal_dir=None):
        self.record, self.profile = record, profile
        self.store = store or CredentialStore()
        self.factory, self.change = factory, change
        self.journal_dir = Path(journal_dir) if journal_dir else Path(os.environ["LOCALAPPDATA"]) / "SmartTray" / "operations"
        if record.get("role") != self.role or profile.get("device_id") != record.get("device_id"):
            raise ValueError("Profile identity mismatch")

    def authorize(self, dp):
        if dp not in self.channels:
            raise ValueError("Unvalidated channel")
        verify_target(self.record, dp)
        confirmed = self.profile.get("confirmed_commands", {}).get(self.channels[dp], {})
        if (confirmed.get("dp") != dp or confirmed.get("values") != [False, True]
                or confirmed.get("transport") != "lan" or not self.profile.get("protocol_authenticated")
                or self.profile.get("protocol") != self.record.get("protocol_version")):
            raise ValueError("Command not validated")

    def _key(self):
        key = self.store.load(self.record["device_id"])
        if not key:
            raise ValueError("Credential unavailable")
        return key

    def state_from_response(self, response):
        if not isinstance(response, dict) or response.get("Err") or not isinstance(response.get("dps"), dict):
            raise ValueError("Read unavailable")
        values = {dp: response["dps"].get(str(dp)) for dp in self.channels}
        values = {dp: value if type(value) is bool else None for dp, value in values.items()}
        return DeviceState("online", values, "Estado atualizado" if all(v is not None for v in values.values()) else "Estado incompleto", datetime.now(timezone.utc).isoformat())

    def read(self):
        with quiet():
            device = None
            try:
                for dp in self.channels:
                    self.authorize(dp)
                device = self.factory(self.record, self._key())
                return self.state_from_response(device.status())
            except Exception:
                return DeviceState("offline", {}, "Sem resposta LAN ou credencial indisponível")
            finally:
                if device:
                    device.close()

    def write(self, dp, expected, value):
        # This method is invoked exclusively by an explicit UI click, never polling.
        self.authorize(dp)
        if type(expected) is not bool or type(value) is not bool or expected is value:
            raise ValueError("Known, changed Boolean state required")
        with quiet():
            try:
                key = self._key()
                self.journal_dir.mkdir(parents=True, exist_ok=True)
                path = self.journal_dir / (uuid.uuid4().hex + ".json")
                def journal(result):
                    data = {"role": self.role, "dp": dp, "requested": value,
                            "timestamp": datetime.now(timezone.utc).isoformat(), "result": result}
                    temporary = path.with_suffix(".tmp")
                    temporary.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
                    temporary.replace(path)
                result = self.change(self.record, key, dp, expected, value, approved=True,
                                     factory=self.factory, journal=journal)
                journal(result)
                if result.get("state_confirmed"):
                    # Only allowlisted Boolean values leave the adapter.
                    response = {"dps": {d: item["value"] for d, item in result["after"].items()
                                        if item.get("type") == "bool"}}
                    return self.state_from_response(response)
                if not result.get("write_attempted") and result.get("before"):
                    return DeviceState("unknown", {}, "Estado mudou. Atualize antes de um novo comando.")
                return DeviceState("unknown", {}, "Resultado não confirmado. Escrita não será repetida.")
            except Exception:
                return DeviceState("unknown", {}, "Operação interrompida. Atualize o estado.")


class LedAdapter(TuyaAdapter):
    role = "led"
    channels = {20: "switch_led"}


class SwitchAdapter(TuyaAdapter):
    role = "novadigital"
    channels = {1: "switch_1", 2: "switch_2"}


class ElginAdapter:
    """Replace this adapter after OEM authentication/DPS validation; UI is generic."""
    role = "elgin"
    channels = {}
    capabilities = {}

    def read(self):
        return DeviceState("pending", {}, "Aguardando configuração")

    def write(self, *args, **kwargs):
        raise ValueError("Elgin commands unavailable")

    command = write


class ElginLanAdapter(ElginAdapter):
    """Authenticated readings and validated setpoint only; power stays read-only."""
    def __init__(self, record, profile, store=None, factory=make_device, journal_dir=None):
        self.record = {**record, "temperature_unit_confirmed": profile.get("temperature_unit_confirmed")}
        self.profile, self.store, self.factory = profile, store or CredentialStore(), factory
        self.journal_dir = Path(journal_dir) if journal_dir else Path(os.environ["LOCALAPPDATA"]) / "SmartTray" / "operations"
        self.authorize()
        self.capabilities = {"temperature": {"validated": True, "kind": "number", "min": 16, "max": 32,
                                            "step": 1, "requires": {"power": True, "mode": "cold"}}}
        self.record["observed_fan_values"] = [v for v in profile.get("observed_fan_settings", {}) if v in {"low", "mid"}]
        choices = {}
        for value, title in (("low", "Baixa"), ("mid", "Média")):
            try:
                self.authorize_fan(value)
                choices[value] = title
            except ValueError:
                pass
        if choices:
            self.capabilities["fan"] = {"validated": True, "kind": "choice", "options": choices,
                "observed_options": {v: title for v, title in (("low", "Baixa"), ("mid", "Média")) if v in self.record["observed_fan_values"]},
                "requires": {"power": True, "mode": "cold", "temperature": 24}}

    def authorize_fan(self, value):
        confirmed = self.profile.get("confirmed_commands", {}).get("windspeed", {})
        if (confirmed.get("dp") != 5 or confirmed.get("transport") != "lan"
                or confirmed.get("physical_confirmed") is not True or value not in confirmed.get("values", [])):
            raise ValueError("This fan target has not been validated")
        elgin_control.validate_value(self.record, "fan", value)

    def authorize(self):
        confirmed = self.profile.get("confirmed_commands", {}).get("temp_set", {})
        if (self.profile.get("device_id") != self.record.get("device_id")
                or self.profile.get("protocol") != "3.5" or self.profile.get("protocol_authenticated") is not True
                or confirmed.get("dp") != 2 or confirmed.get("transport") != "lan"
                or confirmed.get("physical_confirmed") is not True or confirmed.get("scale") != 1
                or confirmed.get("unit") != "c"):
            raise ValueError("Validated setpoint profile required")
        elgin_control.validate_value(self.record, "temperature", 240)

    @staticmethod
    def state_from_snapshot(snapshot):
        values = {}
        for dp, name in (("2", "temperature"), ("3", "ambient_temperature")):
            raw = snapshot.get(dp, {}).get("value")
            if type(raw) is int:
                scaled = raw / 10
                values[name] = int(scaled) if scaled.is_integer() else scaled
        power = snapshot.get("1", {}).get("value")
        if type(power) is bool:
            values["power"] = power
        mode = snapshot.get("4", {}).get("value")
        if mode in {"cold", "hot", "wet", "wind", "auto"}:
            values["mode"] = mode
        fan = snapshot.get("5", {}).get("value")
        if fan in {"low", "mid"}:
            values["fan"] = fan
        return DeviceState("online", values, "Temperatura sincronizada pela LAN", datetime.now(timezone.utc).isoformat())

    def read(self):
        try:
            self.authorize()
            key = self.store.load(self.record["device_id"])
            if not key:
                raise ValueError("Credential unavailable")
            return self.state_from_snapshot(elgin_control.read(self.record, key, self.factory))
        except Exception:
            return DeviceState("offline", {}, "Sem resposta LAN ou credencial indisponível")

    def command(self, name, value):
        raise ValueError("Explicit UI state required; use command_from_state")

    def command_from_state(self, name, expected, value):
        self.authorize()
        if name == "fan":
            self.authorize_fan(value)
            if type(expected) is not str or value == expected:
                raise ValueError("Known, changed fan state required")
            before, target = expected, value
        elif (name != "temperature" or type(value) not in (int, float) or type(expected) not in (int, float)
                or not float(value).is_integer() or not float(expected).is_integer() or abs(value - expected) != 1):
            raise ValueError("Only a whole-degree setpoint step is validated")
        else:
            before, target = int(expected) * 10, int(value) * 10
        elgin_control.validate_value(self.record, name, before)
        elgin_control.validate_value(self.record, name, target)
        try:
            key = self.store.load(self.record["device_id"])
            if not key:
                raise ValueError("Credential unavailable")
            self.journal_dir.mkdir(parents=True, exist_ok=True)
            path = self.journal_dir / (uuid.uuid4().hex + ".json")
            def journal(result):
                data = {"role": "elgin", "function": name, "timestamp": datetime.now(timezone.utc).isoformat(), "result": result}
                temporary = path.with_suffix(".tmp")
                temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
                temporary.replace(path)
            with exclusive_write_lock(self.journal_dir):
                result = elgin_control.change_once(self.record, key, name, before, target,
                    approved=True, journal=journal, factory=self.factory)
                journal(result)
            if result["state_confirmed"]:
                return self.state_from_snapshot(result["after"])
            return DeviceState("unknown", {}, "Alteração não confirmada. Atualize o estado; nenhuma escrita será repetida.")
        except Exception:
            return DeviceState("unknown", {}, "Operação interrompida. Atualize o estado antes de novo comando.")


class UnavailableAdapter:
    def __init__(self, role, channels):
        self.role, self.channels = role, channels

    def read(self):
        return DeviceState("offline", {}, "Perfil local indisponível. Confira a configuração.")

    def write(self, *args, **kwargs):
        raise ValueError("Device configuration unavailable")


def load_adapters(root, elgin_factory=ElginAdapter):
    try:
        registry = json.loads((root / "diagnostics/provisioned.json").read_text(encoding="utf-8"))
    except Exception:
        registry = {"devices": []}
    adapters = {"elgin": elgin_factory()}
    if elgin_factory is ElginAdapter:
        try:
            record = next(r for r in registry["devices"] if r["role"] == "elgin")
            profile = json.loads((root / "profiles/elgin_profile.json").read_text(encoding="utf-8"))
            discovery = json.loads((root / "diagnostics/discovery-current.json").read_text(encoding="utf-8"))
            found = next(d for d in discovery["devices"] if d["device_id"] == record["device_id"])
            record = elgin_control.with_observed_fan_model({**record, "ip": found["ip"], "protocol_version": found["protocol_version"]}, profile, root)
            adapters["elgin"] = ElginLanAdapter(record, profile)
        except Exception:
            pass  # Leave the independent, disabled adapter when validation is missing.
    for role, cls in (("led", LedAdapter), ("novadigital", SwitchAdapter)):
        try:
            record = next(r for r in registry["devices"] if r["role"] == role)
            profile = json.loads((root / "profiles" / (role + "_profile.json")).read_text(encoding="utf-8"))
            # Only an exact ID match in the existing discovery may update an address.
            discovery_path = root / "diagnostics/discovery-current.json"
            if discovery_path.exists():
                discovered = json.loads(discovery_path.read_text(encoding="utf-8"))["devices"]
                found = next((d for d in discovered if d["device_id"] == record["device_id"]), None)
                if found:
                    record = {**record, "ip": found["ip"], "protocol_version": found["protocol_version"]}
            adapters[role] = cls(record, profile)
        except Exception:
            adapters[role] = UnavailableAdapter(role, cls.channels)
    return adapters
