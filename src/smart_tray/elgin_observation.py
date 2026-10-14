"""Elgin status/schema observations; no write or provisioning methods."""
import hashlib
import hmac
import json
import secrets
import re
from .control_validation import make_device
from .elgin_control import specification
from .elgin_research import ELGIN_ID
from .led_research import Capture
from .diagnostic import quiet
from .security import CredentialStore

CATEGORY_NAMES = [("Modo", "mode"), ("Velocidade do ventilador", "fan"),
                  ("Oscilação vertical", "swing_vertical"), ("Oscilação horizontal", "swing_horizontal"),
                  ("Sleep", "sleep"), ("Turbo", "turbo"), ("Eco", "eco"), ("Display", "display"),
                  ("Ionizador", "ionizer"),
                  ("Outro recurso", "other")]

# Harmless fixed telemetry literals, NOT a device specification or write enum.
OBSERVABLE_LITERALS = {"low", "mid", "high", "auto", "silent", "quiet", "mute", "turbo", "strong",
                       "cold", "hot", "wet", "wind", "on", "off", "c", "f"}


def entries(record, schema=None):
    result = list(record["metadata"].get("cloud_dps_candidates", []))
    if schema and schema.get("device_id_masked") == "exampl…0003":
        for query in schema.get("queries", []):
            for entry in query.get("entries", []):
                if entry.get("dp_id") is not None:
                    result.append(entry)
    return result


def observation(response, record, key, fingerprint_key, schema=None, sensitive=()):
    if not isinstance(response, dict) or response.get("Err") or not isinstance(response.get("dps"), dict):
        raise ValueError("Read failed")
    definitions = entries(record, schema)
    values, fingerprints = {}, {}
    for dp, value in response["dps"].items():
        if not str(dp).isdigit():
            continue
        dp = str(dp)
        encoded = json.dumps(value, sort_keys=True, ensure_ascii=True, default=lambda v: v.hex() if isinstance(v, bytes) else None)
        if any(secret and secret in encoded for secret in (key, *sensitive)):
            continue
        fingerprints[dp] = hmac.new(fingerprint_key, encoded.encode(), hashlib.sha256).digest()
        matches = [c for c in definitions if str(c["dp_id"]) == dp]
        enum_allowed = any(c.get("type") == "Enum" and value in c.get("constraints", {}).get("range", []) for c in matches) if isinstance(value, str) else False
        item = {"type": type(value).__name__, "schema_codes": sorted({c["code"] for c in matches}), "observation_validates_control": False}
        if dp == "5" and isinstance(value, str) and re.fullmatch(r"[A-Za-z0-9_-]{1,15}", value):
            # Explicitly authorized display of this device's short fan setting.
            # No standard-name assumptions; key/secret/token lengths are excluded.
            item.update(value=value, encoding="observed_fan_setting", schema_enum_confirmed=enum_allowed,
                        write_validated=False)
        elif type(value) in (bool, int) or enum_allowed:
            item["value"] = value
        elif isinstance(value, str) and value in OBSERVABLE_LITERALS:
            item.update(encoding="unmapped_literal", observed_literal=value, write_value_permitted=False)
        elif isinstance(value, (str, list, dict, bytes)):
            item.update(encoding="opaque", length=len(value))
        values[dp] = item
    return Capture(values, fingerprints)


class ElginObserver:
    def __init__(self, record, store=None, factory=make_device):
        specification(record, "power")  # Identity/schema check only, no traffic.
        self.record, self.store, self.factory = record, store or CredentialStore(), factory
        self.fingerprint_key, self.schema = secrets.token_bytes(32), None

    def set_schema(self, schema):
        if schema.get("device_id_masked") != "exampl…0003":
            raise ValueError("Schema of another device rejected")
        self.schema = schema

    def capture(self):
        with quiet():
            key = self.store.load(ELGIN_ID)
            if not key:
                raise ValueError("Credential missing")
            device = self.factory(self.record, key)
            try:
                return observation(device.status(), self.record, key, self.fingerprint_key, self.schema)
            finally:
                device.close()
