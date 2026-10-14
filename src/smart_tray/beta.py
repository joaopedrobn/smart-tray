"""Evidence-bound beta controls. This module never provisions credentials."""
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import time
import uuid

from tinytuya.core import command_types as CT
from .adapters import DeviceState, load_adapters
from .control_validation import exclusive_write_lock
from .diagnostic import quiet
from .led_research import hsv16_decode, hsv16_encode

VERSION = "2.3.1"


class BetaSettings:
    def __init__(self, directory=None):
        self.directory = Path(directory or Path(os.environ["LOCALAPPDATA"]) / "SmartTray")
        self.path = self.directory / "beta-settings.json"
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            data = {}
        if not isinstance(data, dict):
            data = {}
        self.enabled = data.get("experimental_enabled") is True
        favorites = data.get("favorites", [])
        self.favorites = [v for v in favorites if valid_colour(v)][:12] if isinstance(favorites, list) else []
        last = data.get("last_colour")
        self.last_colour = last if valid_colour(last) else None

    def save(self):
        self.directory.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps({"experimental_enabled": self.enabled,
            "favorites": self.favorites, "last_colour": self.last_colour}, indent=2), encoding="utf-8")
        temporary.replace(self.path)


def valid_colour(value):
    try:
        hsv16_decode(value)
        return True
    except (ValueError, TypeError):
        return False


def own_functions(root, role, device_id=None):
    masked = device_id[:6] + '…' + device_id[-4:] if device_id else {"elgin": "exampl…0003", "led": "exampl…0001"}[role]
    data = json.loads((root / f"diagnostics/{role}-research/schema-current.json").read_text(encoding="utf-8"))
    if data.get("device_id_masked") != masked:
        raise ValueError("Wrong schema identity")
    # Explicit function dp_id required. A model abilityId is not a LAN map.
    return {e["dp_id"]: e for q in data.get("queries", []) for e in q.get("entries", [])
            if type(e.get("dp_id")) is int and e.get("section") == "functions" and e.get("access") in {"rw", "wr", "wo"}}


def capability(dp, kind, *, validated=False, **kwargs):
    return {"dp": dp, "kind": kind, "validated": validated,
            "classification": "validated" if validated else "experimental", **kwargs}


class BetaAdapter:
    """Wrap existing validated adapters; experimental writes have a separate gate."""
    def __init__(self, base, root):
        self.base, self.root = base, Path(root)
        self.role, self.channels = base.role, base.channels
        self.record, self.profile = base.record, base.profile
        self.capabilities = {}
        self.last_result = None
        functions = own_functions(self.root, self.role, self.record['device_id'])
        if self.role == "elgin":
            self.capabilities = {k: {**v, "dp": {"temperature": 2, "fan": 5}[k],
                "classification": "validated"} for k, v in base.capabilities.items()}
            expected = {"power": (1, "switch", "Boolean"), "mode": (4, "mode", "Enum"),
                        "sleep": (102, "sleep", "Boolean"), "display": (13, "light", "Boolean"),
                        "eco": (8, "mode_eco", "Boolean")}
            for name, (dp, code, kind) in expected.items():
                entry = functions.get(dp, {})
                if (entry.get("code"), entry.get("type")) != (code, kind):
                    continue
                if kind == "Enum":
                    labels = {"cold": "Resfriar", "wet": "Desumidificar", "wind": "Ventilar", "auto": "Automático"}
                    options = {v: title for v, title in labels.items() if v in entry.get("constraints", {}).get("range", [])}
                    if options:
                        self.capabilities[name] = capability(dp, "choice", options=options, requires={"power": True})
                else:
                    self.capabilities[name] = capability(dp, "boolean", requires={} if name == "power" else {"power": True})
            # Mapping DP5 is supported by bidirectional manual evidence. Use only
            # actual own-device model enums, never invented spellings.
            evidence = base.record.get("oem_fan_evidence", {})
            if evidence.get("bidirectional_manual_verified") is True and evidence.get("model_access") == "rw":
                labels = {"mute": "Silêncio", "low": "Baixa", "mid": "Média", "high": "Alta",
                          "auto": "Auto", "strength": "Turbo · strength (Beta)"}
                options = {v: title for v, title in labels.items() if v in evidence.get("model_range", [])}
                validated = list(base.capabilities.get("fan", {}).get("options", {}))
                self.capabilities["fan"] = capability(5, "choice", options=options, observed_options=options,
                    validated_values=validated, requires={"power": True, "mode": "cold"},
                    evidence="OEM: DP5 observado; enum do modelo. Rótulos adicionais ainda experimentais.")
        elif self.role == "led":
            mode = functions.get(21, {})
            if mode.get("code") == "work_mode" and mode.get("type") == "Enum":
                labels = {"white": "White", "colour": "Colour", "scene": "Scene", "music": "Music"}
                options = {v: title for v, title in labels.items() if v in mode.get("constraints", {}).get("range", [])}
                self.capabilities["mode"] = capability(21, "choice", options=options, requires={20: True})
            colour = functions.get(24, {})
            limits = colour.get("constraints", {})
            inspection = base.profile.get("colour_inspection", {})
            if (colour.get("code") == "colour_data" and colour.get("type") == "Json"
                    and all(limits.get(k, {}).get("min") == 0 and limits.get(k, {}).get("max") == maximum
                            for k, maximum in (("h", 360), ("s", 1000), ("v", 1000)))
                    and inspection.get("observed_encoding") == "hex_12_chars"):
                self.capabilities["colour"] = capability(24, "colour", requires={20: True, "mode": "colour"},
                    evidence="HSV16 documentado + string LAN de 12 caracteres; confirmação física pendente")
                self.capabilities["brightness"] = capability(24, "brightness", min=1, max=100,
                    requires={20: True, "mode": "colour"}, evidence="Componente V de HSV16; brilho em cor fixa")

    def is_validated(self, name, value):
        spec = self.capabilities.get(name, {})
        return spec.get("validated") is True or value in spec.get("validated_values", [])

    def validate(self, name, value):
        spec = self.capabilities.get(name)
        if not spec:
            raise ValueError("Unmapped function")
        kind = spec["kind"]
        valid = ((kind == "boolean" and type(value) is bool)
                 or (kind == "choice" and type(value) is str and value in spec["options"])
                 or (kind == "number" and type(value) in (int, float) and float(value).is_integer()
                     and spec["min"] <= value <= spec["max"])
                 or (kind == "brightness" and type(value) is int and 1 <= value <= 100)
                 or (kind == "colour" and valid_colour(value)))
        if not valid:
            raise ValueError("Invalid value")
        return spec

    def proposed(self, name, value, state):
        spec = self.validate(name, value)
        if name == "brightness":
            hsv = hsv16_decode(state.values.get("colour"))
            value = hsv16_encode(hsv["h"], hsv["s"], value * 10)
        elif name == "temperature":
            value = int(value * 10)
        return {str(spec["dp"]): value}

    def _safe_values(self, response, key):
        if not isinstance(response, dict) or response.get("Err") or not isinstance(response.get("dps"), dict):
            raise ValueError("LAN read failed")
        raw, values = response["dps"], {}
        for dp in self.channels:
            if type(raw.get(str(dp))) is bool:
                values[dp] = raw[str(dp)]
        if self.role == "elgin":
            for dp, name in ((2, "temperature"), (3, "ambient_temperature")):
                if type(raw.get(str(dp))) is int and -500 <= raw[str(dp)] <= 1000:
                    scaled = raw[str(dp)] / 10
                    values[name] = int(scaled) if scaled.is_integer() else scaled
        for name, spec in self.capabilities.items():
            item = raw.get(str(spec["dp"]))
            if spec["kind"] == "boolean" and type(item) is bool:
                values[name] = item
            elif spec["kind"] == "choice" and isinstance(item, str) and item in spec["options"]:
                if key not in item:
                    values[name] = item
            elif name == "colour" and valid_colour(item) and key not in item:
                values[name] = item.lower()
                values["brightness"] = round(hsv16_decode(item)["v"] / 10)
        return values

    def _state(self, response, key, message="Estado sincronizado pela LAN"):
        return DeviceState("online", self._safe_values(response, key), message, datetime.now(timezone.utc).isoformat())

    def read(self):
        with quiet():
            device = None
            try:
                key = self.base.store.load(self.record["device_id"])
                if not key:
                    raise ValueError("Credential unavailable")
                device = self.base.factory(self.record, key)
                return self._state(device.status(), key)
            except Exception:
                return DeviceState("offline", {}, "Sem resposta LAN ou credencial indisponível")
            finally:
                if device:
                    device.close()

    def write(self, *args):
        result = self.base.write(*args)  # Existing LED power only, unchanged.
        return self.read() if result.connection == "online" else result

    def command_from_state(self, *args):
        raise ValueError("Beta commands require explicit state and approval")

    def temperature_change_allowed(self, before, target):
        return abs(target - before) == 1

    def execute(self, name, expected_state, value, *, experimental_approved=False):
        self.last_result = None
        spec = self.validate(name, value)
        validated = self.is_validated(name, value)
        if not validated and experimental_approved is not True:
            raise ValueError("Explicit experimental confirmation required")
        if expected_state.connection != "online":
            raise ValueError("Known LAN state required")
        payload = self.proposed(name, value, expected_state)
        result = {"version": VERSION, "role": self.role, "function": name, "command": payload,
                  "classification": "validated" if validated else "experimental", "write_attempted": False,
                  "lan_confirmed": False, "physical_confirmation": "pending", "before": {}, "after": {}}
        directory = self.base.journal_dir
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / (uuid.uuid4().hex + ".json")
        def journal():
            result["timestamp"] = datetime.now(timezone.utc).isoformat()
            temporary = path.with_suffix(".tmp")
            temporary.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
            temporary.replace(path)
        device = None
        with quiet():
            try:
                with exclusive_write_lock(directory):
                    key = self.base.store.load(self.record["device_id"])
                    if not key:
                        raise ValueError("Credential unavailable")
                    device = self.base.factory(self.record, key)
                    before = self._state(device.status(), key)
                    result["before"] = before.values
                    # Compare target and dependencies with the UI snapshot. Any
                    # stale value cancels the write, including H/S for brightness.
                    guards = set(spec.get("requires", {})) | {name}
                    if self.role == "elgin" and name == "fan":
                        guards.add("temperature")
                    if name == "brightness":
                        guards.add("colour")
                    if any(before.values.get(g) is None or before.values.get(g) != expected_state.values.get(g) for g in guards):
                        raise ValueError("Stale state")
                    if any(before.values.get(g) != wanted for g, wanted in spec.get("requires", {}).items()):
                        raise ValueError("Operating conditions changed")
                    if before.values.get(name) == value:
                        raise ValueError("No change")
                    # Temperature retains the already validated one-degree step.
                    if name == "temperature" and not self.temperature_change_allowed(before.values[name], value):
                        raise ValueError("One-degree step required")
                    result["write_attempted"] = True
                    journal()  # Durable before a single, unretried LAN send.
                    encoded = device.generate_payload(CT.CONTROL, payload)
                    if device._send_receive_quick(encoded, recv_retries=0) is not True:
                        raise ValueError("Uncertain send")
                    device.close()
                    device = None
                    time.sleep(1)
                    device = self.base.factory(self.record, key)
                    after = self._state(device.status(), key)
                    result["after"] = after.values
                    result["other_changes"] = {str(k): {"before": before.values.get(k), "after": v}
                        for k, v in after.values.items() if k not in {name, "colour" if name == "brightness" else name}
                        and before.values.get(k) != v}
                    actual = after.values.get("colour" if name == "brightness" else name)
                    wanted = payload[str(spec["dp"])] if name == "brightness" else int(value) if name == "temperature" else value
                    result["lan_confirmed"] = type(actual) is type(wanted) and actual == wanted
                    # Detect changed dependencies, but never restore anything.
                    result["lan_confirmed"] &= all(after.values.get(g) == v for g, v in spec.get("requires", {}).items())
                    if self.role == "elgin" and name == "fan":
                        result["lan_confirmed"] &= after.values.get("temperature") == before.values.get("temperature")
                    result["result"] = "lan_confirmed_physical_pending" if result["lan_confirmed"] else "uncertain_no_retry"
                    journal()
                    self.last_result = (path, result)
                    if result["lan_confirmed"]:
                        return DeviceState("online", after.values, "LAN confirmou · confirmação física pendente", after.checked_at)
            except Exception:
                result["result"] = "uncertain_no_retry" if result["write_attempted"] else "initial_read_or_conditions_failed_no_write"
            finally:
                if device:
                    device.close()
            journal()
            self.last_result = (path, result)
            return DeviceState("unknown", {}, "Resultado não confirmado. Nenhuma escrita será repetida; atualize o estado.")


def load_beta_adapters(root):
    adapters = load_adapters(root)
    for role in ("elgin", "led"):
        try:
            adapters[role] = BetaAdapter(adapters[role], root)
        except Exception:
            pass  # Preserve validated adapters if a research schema is missing.
    return adapters
