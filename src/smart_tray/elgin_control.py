"""Typed, individually approved Elgin LAN tests. No generic DPS writer."""
import ipaddress
import time
import json
from pathlib import Path
from tinytuya.core import command_types as CT
from .control_validation import make_device, private_lan_address
from .diagnostic import quiet
from .elgin_research import ELGIN_ID

FUNCTIONS = {"power": (1, "switch", "Boolean"), "temperature": (2, "temp_set", "Integer"),
             "fan": (5, None, "Enum")}


def verified_fan_observations(sessions, device_id=ELGIN_ID):
    """Both manual directions, isolated DP5 changes and unchanged operating state."""
    directions = set()
    for session in sessions:
        if session.get("device_id_masked") != device_id[:6] + '…' + device_id[-4:]:
            continue
        events = session.get("events", [])
        for before, after in zip(events, events[1:]):
            if before.get("writes_sent") != 0 or after.get("writes_sent") != 0 or set(after.get("changes", {})) != {"5"}:
                continue
            snapshots = (before.get("snapshot", {}), after.get("snapshot", {}))
            if any(s.get("1", {}).get("value") is not True or type(s.get("2", {}).get("value")) is not int
                   or s["2"]["value"] != 240 or s.get("4", {}).get("value") != "cold" for s in snapshots):
                continue
            if {dp: value for dp, value in snapshots[0].items() if dp != "5"} != {dp: value for dp, value in snapshots[1].items() if dp != "5"}:
                continue
            pair = tuple(s.get("5", {}).get("value") for s in snapshots)
            if pair in {("low", "mid"), ("mid", "low")}:
                directions.add(pair)
    return directions == {("low", "mid"), ("mid", "low")}


def with_observed_fan_model(record, profile, root):
    """Load non-secret evidence for the adapter; failure leaves fan writes blocked."""
    result = {**record, "observed_fan_values": [v for v in profile.get("observed_fan_settings", {}) if v in {"low", "mid"}]}
    try:
        root = Path(root)
        schema = json.loads((root / "diagnostics/elgin-research/schema-current.json").read_text(encoding="utf-8"))
        if schema.get("device_id_masked") != record['device_id'][:6] + '…' + record['device_id'][-4:]:
            return result
        sessions = []
        for relative in profile.get("fan_manual_evidence", []):
            path = (root / relative).resolve()
            if path.parent != (root / "diagnostics/elgin-research").resolve():
                return result
            sessions.append(json.loads(path.read_text(encoding="utf-8")))
        for query in schema.get("queries", []):
            for entry in query.get("entries", []):
                if query.get("source") == "things_model" and entry.get("ability_id") == 5 and entry.get("code") == "windspeed":
                    result["oem_fan_evidence"] = {"bidirectional_manual_verified": verified_fan_observations(sessions, record['device_id']),
                        "model_code": entry["code"], "model_access": entry["access"], "model_type": entry["type"],
                        "model_range": entry["constraints"].get("range", [])}
    except Exception:
        pass
    return result


def specification(record, name):
    if name not in FUNCTIONS or record.get('role') != 'elgin' or not record.get('device_id') or str(record.get('protocol_version')) != '3.5':
        raise ValueError("Exact Elgin identity/function required")
    if record.get("protocol_authenticated") is not True or not private_lan_address(record["ip"]):
        raise ValueError("Authenticated private LAN required")
    dp, code, kind = FUNCTIONS[name]
    matches = [c for c in record.get("metadata", {}).get("cloud_dps_candidates", [])
               if str(c.get("dp_id")) == str(dp) and (c.get("code") == code if code else bool(c.get("code")))
               and c.get("type") == kind and c.get("source") == "cloud_functions"]
    if name == "fan" and not matches:
        evidence = record.get("oem_fan_evidence", {})
        if (evidence.get("bidirectional_manual_verified") is True and evidence.get("model_code") == "windspeed"
                and evidence.get("model_access") == "rw" and evidence.get("model_type") == "Enum"
                and {"low", "mid"}.issubset(set(evidence.get("model_range", [])))):
            return {"dp_id": 5, "code": "windspeed", "type": "Enum", "source": "oem_observed_not_standard_dp_documented",
                    "constraints": {"range": ["low", "mid"]}}
    if len(matches) != 1:
        raise ValueError("Exact own-device function schema required")
    return matches[0]


def validate_value(record, name, value):
    spec = specification(record, name)
    if name == "power":
        if type(value) is not bool:
            raise ValueError("Boolean power required")
    elif name == "fan":
        if (type(value) is not str or value not in spec.get("constraints", {}).get("range", [])
                or value not in record.get("observed_fan_values", [])):
            raise ValueError("Own-device write enum and manually observed fan value required")
    else:
        limits = spec["constraints"]
        if (record.get("temperature_unit_confirmed") != "c" or limits.get("scale") != 1
                or limits.get("step") != 10 or type(value) is not int
                or not max(160, limits["min"]) <= value <= min(320, limits["max"])
                or (value - limits["min"]) % limits["step"]):
            raise ValueError("Confirmed Celsius, scale and bounded whole-degree setpoint required")
    return spec["dp_id"]


def snapshot(response, record, key):
    if not isinstance(response, dict) or response.get("Err") or not isinstance(response.get("dps"), dict):
        raise RuntimeError("Status unavailable")
    enums = {}
    for c in record.get("metadata", {}).get("cloud_dps_candidates", []):
        if c.get("type") == "Enum":
            enums.setdefault(str(c["dp_id"]), set()).update(c.get("constraints", {}).get("range", []))
    result = {}
    enums.setdefault("5", set()).update(record.get("observed_fan_values", []))
    for dp, value in response["dps"].items():
        if not str(dp).isdigit():
            continue
        allowed = type(value) in (bool, int) or (isinstance(value, str) and value in enums.get(str(dp), set()) and key not in value)
        result[str(dp)] = {"type": type(value).__name__, "value": value if allowed else "[withheld]"}
    return result


def read(record, key, factory=make_device):
    specification(record, "power")
    with quiet():
        device = factory(record, key)
        try:
            return snapshot(device.status(), record, key)
        finally:
            device.close()


def change_once(record, key, name, expected, value, *, approved=False, journal=None, factory=make_device):
    if approved is not True or journal is None:
        raise ValueError("Explicit approval and durable attempt journal required")
    dp = str(validate_value(record, name, value))
    validate_value(record, name, expected)
    if value == expected:
        raise ValueError("Changed value required")
    result = {"function": name, "dp": int(dp), "requested": value, "before": None, "after": None,
              "write_attempted": False, "state_confirmed": False}
    with quiet():
        device = factory(record, key)
        try:
            before = device.status()
            result["before"] = snapshot(before, record, key)
            if name == "fan" and (before["dps"].get("1") is not True or before["dps"].get("4") != "cold"
                                  or type(before["dps"].get("2")) is not int or before["dps"]["2"] != 240):
                result["result"] = "fan_operating_conditions_changed_no_write"
                return result
            if name == "temperature" and (before["dps"].get("1") is not True or before["dps"].get("4") != "cold"):
                result["result"] = "power_or_mode_changed_no_write"
                return result
            current = before["dps"].get(dp)
            if type(current) is not type(expected) or current != expected:
                result["result"] = "state_changed_no_write"
                return result
            result["write_attempted"] = True
            journal(result)
            payload = device.generate_payload(CT.CONTROL, {dp: value})
            if device._send_receive_quick(payload, recv_retries=0) is not True:
                raise RuntimeError("Uncertain send")
            device.close()
            time.sleep(1)
            after = device.status()
            result["after"] = snapshot(after, record, key)
            observed = after["dps"].get(dp)
            result["state_confirmed"] = type(observed) is type(value) and observed == value
            if name == "fan" and (after["dps"].get("1") is not True or after["dps"].get("4") != "cold"
                                  or type(after["dps"].get("2")) is not int or after["dps"]["2"] != 240):
                result["state_confirmed"] = False
                result["result"] = "fan_operating_conditions_changed_stop_no_retry"
                return result
            if name == "temperature" and (after["dps"].get("1") is not True or after["dps"].get("4") != "cold"):
                result["state_confirmed"] = False
                result["result"] = "power_or_mode_changed_stop_no_retry"
                return result
            result["result"] = "lan_confirmed_physical_pending" if result["state_confirmed"] else "uncertain_stop_no_retry"
        except Exception:
            result["result"] = "communication_failed_stop_no_retry" if result["write_attempted"] else "initial_read_failed_no_write"
        finally:
            device.close()
    return result
