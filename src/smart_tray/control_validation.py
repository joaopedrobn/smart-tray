"""Stage 2: explicit, allowlisted one-shot LAN power tests only."""
import json
import re
import ipaddress
import time
from contextlib import contextmanager

import tinytuya
from tinytuya.core import command_types as CT

from .diagnostic import quiet

TARGETS = {
    ("led", 20): ("example-led-0000000001", "3.3", "switch_led"),
    ("novadigital", 1): ("example-switch-000002", "3.4", "switch_1"),
    ("novadigital", 2): ("example-switch-000002", "3.4", "switch_2"),
}


@contextmanager
def exclusive_write_lock(directory):
    lock = directory / "active.lock"
    handle = lock.open("x")
    try:
        yield
    finally:
        handle.close()  # Windows requires closing before deletion.
        lock.unlink(missing_ok=True)


def verify_target(record, dp):
    target = TARGETS.get((record.get("role"), dp))
    if not target or not record.get("device_id") or str(record.get("protocol_version")) != target[1]:
        raise ValueError("Target/DPS not authorized")
    if not private_lan_address(record["ip"]):
        raise ValueError("Outside authorized LAN")
    candidates = record.get("metadata", {}).get("cloud_dps_candidates", [])
    if not any(str(c.get("dp_id")) == str(dp) and c.get("code") == target[2]
               and c.get("type") == "Boolean" and c.get("source") == "cloud_functions" for c in candidates):
        raise ValueError("Exact device write specification not confirmed")


def private_lan_address(value):
    address = ipaddress.IPv4Address(value)
    return any(address in ipaddress.IPv4Network(network) for network in
        ('10.0.0.0/8', '172.16.0.0/12', '192.168.0.0/16'))


def safe_snapshot(response):
    if not isinstance(response, dict) or response.get("Err") or not isinstance(response.get("dps"), dict):
        raise RuntimeError("Read failed; stop this device")
    return {str(dp): {"type": type(v).__name__, "value": v if type(v) in (bool, int, float) else "[withheld]"}
            for dp, v in response["dps"].items() if str(dp).isdigit()}


def inspect_led(response, key):
    dps = response.get("dps", {})
    mode = dps.get("21")
    observed_mode = mode if isinstance(mode, str) and mode != key and re.fullmatch(r"[a-z_]{1,20}", mode) else None
    raw = dps.get("24")
    colour = {"encoding": "unverified", "rgb_write_authorized": False}
    if isinstance(raw, str) and raw != key:
        try:
            parsed = json.loads(raw)
        except (ValueError, TypeError):
            parsed = None
        if isinstance(parsed, dict) and set(parsed) == {"h", "s", "v"} and all(type(v) is int for v in parsed.values()):
            colour.update(encoding="json_hsv", fields={k: {"type": "int", "observed_value": v} for k, v in parsed.items()})
        elif re.fullmatch(r"[0-9a-fA-F]{12}", raw):
            colour.update(encoding="hex_12_chars", groups=[int(raw[i:i+4], 16) for i in (0, 4, 8)], semantics="unverified")
    return {"observed_mode": observed_mode, "available_modes": None,
            "available_modes_blocker": "stored_cloud_enum_spec_has_no_range; no mode writes until retrieved",
            "colour_format": colour}


def make_device(record, key):
    return tinytuya.Device(record["device_id"], record["ip"], key,
                          version=float(record["protocol_version"]), connection_timeout=3,
                          connection_retry_limit=1, connection_retry_delay=0, persist=True)


def send_boolean_once(device, dp, value):
    if type(value) is not bool:
        raise ValueError("Boolean required")
    payload = device.generate_payload(CT.CONTROL, {str(dp): value})
    # TinyTuya 1.20.0 quick path makes exactly one socket.sendall call and never
    # repeats it on send timeout/exception. Do not use set_status's retry path.
    sent = device._send_receive_quick(payload, recv_retries=0)
    if sent is not True:
        raise RuntimeError("Write transport uncertain; stop without retry/restoration")


def change_once(record, key, dp, expected_before, value, approved=False, journal=None, factory=make_device):
    verify_target(record, dp)
    if not approved:
        raise ValueError("Explicit user approval required")
    if type(value) is not bool or type(expected_before) is not bool:
        raise ValueError("Boolean states required")
    result = {"before": None, "after": None, "write_attempted": False, "state_confirmed": False}
    with quiet():
        device = factory(record, key)
        try:
            before = device.status()
            result["before"] = safe_snapshot(before)
            if before["dps"].get(str(dp)) is not expected_before:
                result["result"] = "state_changed_since_proposal_no_write"
                return result
            result["write_attempted"] = True
            if journal:
                journal(result)  # Persist attempt BEFORE sending: never silently repeat.
            send_boolean_once(device, dp, value)
            # Read using a fresh socket. A persistent socket can still contain
            # unsolicited/acknowledgment frames from the preceding operation.
            # Closing never repeats the write; status establishes a read session.
            device.close()
            # Device state updates can lag the transport send. Allow a bounded
            # settling interval before the single verification query.
            time.sleep(1)
            after = device.status()
            result["after"] = safe_snapshot(after)
            result["state_confirmed"] = after["dps"].get(str(dp)) is value
            result["result"] = "dps_confirmed_physical_observation_pending" if result["state_confirmed"] else "state_not_confirmed_stop"
        except Exception:
            result["result"] = "communication_failed_stop_no_retry" if result["write_attempted"] else "initial_read_failed_no_write"
        finally:
            device.close()
    return result
