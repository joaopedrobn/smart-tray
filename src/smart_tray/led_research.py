"""Stage A: LED schema/observations only. No setters or command transport."""
from dataclasses import dataclass, field
from datetime import datetime, timezone
import colorsys
import hashlib
import hmac
import json
import math
from pathlib import Path
import re
import secrets
import uuid

from .control_validation import make_device, verify_target
from .diagnostic import quiet, safe_constraints
from .security import CredentialStore

LED_ID = "example-led-0000000001"
CATEGORIES = {"baseline", "colour", "brightness", "effect", "speed", "intensity", "direction", "music", "mode", "other"}
MODES = {"white", "colour", "scene", "music"}


def hsv16_decode(raw):
    """Documented Tuya HSV16 candidate, not a claim of physical validation."""
    if not isinstance(raw, str) or not re.fullmatch(r"[0-9a-fA-F]{12}", raw):
        raise ValueError("Invalid HSV16 shape")
    h, s, v = (int(raw[i:i + 4], 16) for i in (0, 4, 8))
    if not 0 <= h <= 360 or not 0 <= s <= 1000 or not 0 <= v <= 1000:
        raise ValueError("HSV out of documented range")
    return {"h": h, "s": s, "v": v}


def hsv16_encode(h, s, v):
    if any(type(n) is not int for n in (h, s, v)):
        raise ValueError("Integer HSV required")
    value = f"{h:04x}{s:04x}{v:04x}"
    hsv16_decode(value)
    return value


def rgb_to_hsv16(r, g, b):
    if any(type(n) is not int or not 0 <= n <= 255 for n in (r, g, b)):
        raise ValueError("RGB range required")
    h, s, v = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
    return hsv16_encode(round(h * 360), round(s * 1000), round(v * 1000))


def hsv_to_rgb(hsv):
    raw = hsv16_encode(hsv["h"], hsv["s"], hsv["v"])
    hsv16_decode(raw)
    values = colorsys.hsv_to_rgb((hsv["h"] % 360) / 360, hsv["s"] / 1000, hsv["v"] / 1000)
    return [round(n * 255) for n in values]


def schema_constraints(value, sensitive=()):
    result = safe_constraints(value, sensitive)
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except ValueError:
            value = {}
    if isinstance(value, dict):
        if type(value.get("maxlen")) is int and 0 <= value["maxlen"] <= 65535:
            result["maxlen"] = value["maxlen"]
        if isinstance(value.get("unit"), str) and value.get("unit") in {"cm", "m", "s", "%", "℃", "°C", "°F", "℉"}:
            result["unit"] = value["unit"]
    # Reject embedded tokens too, not just strings equal to a secret.
    def contains_sensitive(item):
        if isinstance(item, str):
            return any(s and s in item for s in sensitive)
        if isinstance(item, list):
            return any(contains_sensitive(v) for v in item)
        if isinstance(item, dict):
            return any(contains_sensitive(v) for v in item.values())
        return False
    if contains_sensitive(result):
        return {}
    return result


def clean_schema(response, source, sensitive=()):
    if not isinstance(response, dict) or response.get("success") is not True:
        return {"source": source, "result": "denied_or_unavailable", "entries": []}
    body = response.get("result", {})
    entries = []
    sections = []
    if isinstance(body, dict) and "model" in body:
        model = body["model"]
        if isinstance(model, str) and len(model) <= 250000:
            try:
                model = json.loads(model)
            except ValueError:
                model = {}
        if isinstance(model, dict):
            for service in model.get("services", []):
                # Actions/events may carry arbitrary credential fields. Inspect
                # property definitions only; never export defaults/current data.
                sections.append(("properties", service.get("properties", [])))
    elif isinstance(body, dict):
        sections = [(section, body.get(section, [])) for section in ("status", "functions")]
    for section, items in sections:
        for item in items:
            code = item.get("code")
            if not isinstance(code, str) or not re.fullmatch(r"[a-zA-Z0-9_]{1,64}", code) or any(s and s in code for s in sensitive):
                continue
            typespec = item.get("typeSpec", {})
            raw_type = item.get("type", typespec.get("type"))
            kind = {"bool": "Boolean", "boolean": "Boolean", "value": "Integer", "integer": "Integer",
                    "enum": "Enum", "json": "Json", "raw": "Raw", "string": "String"}.get(str(raw_type).lower())
            if kind is None:
                continue
            dp = item.get("dp_id")
            dp = int(dp) if str(dp).isdigit() and 0 < int(dp) <= 65535 else None
            ability = item.get("abilityId")
            entries.append({"dp_id": dp, "ability_id": ability if type(ability) is int else None,
                            "code": code, "type": kind, "section": section,
                            "access": item.get("accessMode") if item.get("accessMode") in {"ro", "rw", "wo", "wr"} else
                                      "rw" if section == "functions" else "unspecified",
                            "constraints": schema_constraints(item.get("values", typespec), sensitive),
                            "lan_mapping_confirmed": False, "write_validated": False})
    return {"source": source, "result": "schema_read_ok", "entries": entries}


def collect_schema(cloud, sensitive=(), *, device_id=LED_ID):
    if device_id not in {LED_ID, "example-elgin-00000003"}:
        raise ValueError("Only identified LED and Elgin schema queries allowed")
    # Exact device only, official read endpoints; no account/device exports.
    queries = [("device_spec_v1_1", f"devices/{device_id}/specifications", "v1.1"),
               ("device_spec_iot03", f"iot-03/devices/{device_id}/specification", "v1.0"),
               ("things_model", f"cloud/thing/{device_id}/model", "v2.0")]
    outcomes = []
    for source, uri, version in queries:
        try:
            response = cloud._tuyaplatform(uri, action="GET", ver=version)
            outcomes.append(clean_schema(response, source, sensitive))
        except Exception:
            outcomes.append({"source": source, "result": "denied_or_unavailable", "entries": []})
    return {"timestamp": datetime.now(timezone.utc).isoformat(), "device_id_masked": device_id[:6] + "…" + device_id[-4:], "queries": outcomes}


@dataclass
class Capture:
    values: dict
    fingerprints: dict = field(repr=False)
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


def capture_response(response, sensitive, fingerprint_key):
    if not isinstance(response, dict) or response.get("Err") or not isinstance(response.get("dps"), dict):
        raise ValueError("Status unavailable")
    values, fingerprints = {}, {}
    for dp, value in response["dps"].items():
        if not str(dp).isdigit():
            continue
        dp = str(dp)
        encoded = json.dumps(value, sort_keys=True, ensure_ascii=True,
                             default=lambda v: v.hex() if isinstance(v, bytes) else None)
        if any(s and s in encoded for s in sensitive):
            continue  # No key/token, not even length or fingerprint.
        fingerprints[dp] = hmac.new(fingerprint_key, encoded.encode(), hashlib.sha256).digest()
        item = {"type": type(value).__name__}
        if type(value) in (bool, int) or (type(value) is float and math.isfinite(value)):
            item["value"] = value
        elif dp == "21" and isinstance(value, str) and value in MODES:
            item["value"] = value
        elif dp == "24" and isinstance(value, str):
            try:
                hsv = hsv16_decode(value)
                item.update(encoding="candidate_hsv16", hsv=hsv, derived_rgb=hsv_to_rgb(hsv), physical_mapping_confirmed=False)
            except ValueError:
                try:
                    hsv = json.loads(value)
                    if set(hsv) != {"h", "s", "v"}:
                        raise ValueError
                    hsv16_encode(hsv["h"], hsv["s"], hsv["v"])
                    item.update(encoding="json_hsv", hsv=hsv, physical_mapping_confirmed=False)
                except (ValueError, TypeError, KeyError):
                    item.update(encoding="opaque", length=len(value))
        elif isinstance(value, (str, bytes, list, dict)):
            item.update(encoding="opaque", length=len(value))
        values[dp] = item
    return Capture(values, fingerprints)


def differences(before, after):
    result = {}
    for dp in sorted(set(before.values) | set(after.values), key=int):
        if before.fingerprints.get(dp) != after.fingerprints.get(dp):
            result[dp] = {"before": before.values.get(dp), "after": after.values.get(dp),
                          "value_changed": True,
                          "interpretation": "correlation_only_not_function_validation"}
    return result


class LedReader:
    def __init__(self, record, store=None, factory=make_device):
        if record.get("role") != "led" or record.get("device_id") != LED_ID:
            raise ValueError("LED identity required")
        verify_target(record, 20)
        self.record, self.store, self.factory = record, store or CredentialStore(), factory
        self.fingerprint_key = secrets.token_bytes(32)

    def capture(self):
        with quiet():
            key = self.store.load(LED_ID)
            if not key:
                raise RuntimeError("Credential unavailable")
            device = self.factory(self.record, key)
            try:
                return capture_response(device.status(), (key,), self.fingerprint_key)
            finally:
                device.close()


class Session:
    def __init__(self, directory, device_id=LED_ID, categories=CATEGORIES):
        self.device_id, self.categories = device_id, categories
        self.directory = Path(directory)
        self.path = self.directory / ("session-" + uuid.uuid4().hex + ".json")
        self.baseline = None
        self.events = []

    def record(self, capture, category):
        if category not in self.categories:
            raise ValueError("Predefined observation category required")
        if category != "baseline" and self.baseline is None:
            raise ValueError("Capture a baseline before manual changes")
        changes = differences(self.baseline, capture) if self.baseline else {}
        event = {"timestamp": capture.timestamp, "category": category,
                 "snapshot": capture.values, "changes": changes, "writes_sent": 0}
        self.events.append(event)
        self.directory.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps({"device_id_masked": self.device_id[:6] + "…" + self.device_id[-4:], "events": self.events}, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(self.path)
        self.baseline = capture
        return event
