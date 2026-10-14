"""Allowlisted provisioning metadata and LAN status queries only."""
import contextlib
import importlib
import ipaddress
import logging
import os
import json
import re
import sys
import threading
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from urllib.parse import urlparse

import requests
import tinytuya

REGIONS = {"cn", "us", "us-e", "eu", "eu-w", "in", "sg"}
HOSTS = {"openapi.tuyacn.com", "openapi.tuyaus.com", "openapi-ueaz.tuyaus.com",
         "openapi.tuyaeu.com", "openapi-weaz.tuyaeu.com", "openapi.tuyain.com", "openapi-sg.iotbing.com"}


def mask(device_id):
    return device_id[:6] + "…" + device_id[-4:]


def associate(identities, discovered, arp):
    """Require exact app ID AND app MAC matching the observed IP's ARP."""
    by_id = {d["device_id"]: d for d in discovered}
    by_ip = {d["ip"]: d for d in arp}
    records = []
    seen = set()
    for identity in identities:
        did = identity["device_id"]
        if did in seen:
            raise ValueError("Duplicate identity")
        seen.add(did)
        found = by_id.get(did)
        if not found:
            raise ValueError("App ID absent from discovery")
        neighbor = by_ip.get(found["ip"])
        normalize = lambda value: value.replace(":", "").replace("-", "").lower()
        if not neighbor or normalize(neighbor["mac"]) != normalize(identity["mac"]):
            raise ValueError("App MAC does not match ARP at discovered IP")
        records.append({**found, "mac": identity["mac"], "name": identity["name"],
                        "role": identity["role"], "app": identity["app"],
                        "identity_evidence": "official_app_id_and_mac_match_discovery_and_arp",
                        "metadata": {"name": identity["name"], "manufacturer": identity["manufacturer"],
                                     "model": identity["model"], "category": identity["role"],
                                     "source": "user_official_app", "cloud_dps_candidates": []},
                        "credential": "pending", "local_read": "pending",
                        "local_control": "not_tested", "protocol_authenticated": False})
    return records


_quiet_lock = threading.RLock()
_quiet_count = 0
_quiet_saved = None
_quiet_sink = None


@contextlib.contextmanager
def quiet():
    # Multiple bounded device workers may overlap. Share one sink and restore
    # process-wide streams only after the last worker leaves; no network lock.
    global _quiet_count, _quiet_saved, _quiet_sink
    with _quiet_lock:
        if _quiet_count == 0:
            _quiet_saved = (sys.stdout, sys.stderr, logging.root.manager.disable)
            _quiet_sink = open(os.devnull, "w")
            sys.stdout = sys.stderr = _quiet_sink
            logging.disable(100)
        _quiet_count += 1
    try:
        yield
    finally:
        with _quiet_lock:
            _quiet_count -= 1
            if _quiet_count == 0:
                sys.stdout, sys.stderr, previous = _quiet_saved
                logging.disable(previous)
                _quiet_sink.close()
                _quiet_sink = _quiet_saved = None


def clean_text(value, secrets=()):
    text = str(value)[:160] if value is not None else None
    if text is not None:
        for secret in secrets:
            if secret:
                text = text.replace(str(secret), "[redacted]")
        text = "".join(c for c in text if c.isprintable())
    return text


class CloudQueryError(RuntimeError):
    def __init__(self, evidence):
        super().__init__('Cloud query stopped; sanitized evidence available')
        self.evidence = evidence


@contextlib.contextmanager
def cloud_connection(region, api_id, secret, *, single_attempt=False):
    if region not in REGIONS or not api_id or not secret:
        raise ValueError("Invalid cloud configuration")
    module = importlib.import_module("tinytuya.Cloud")
    with requests.Session() as session:
        session.trust_env = False  # No environment proxies or netrc credentials.
        http_evidence = {'http_status': None}
        attempted = set()
        def get(url, **kwargs):
            parsed = urlparse(url)
            if parsed.scheme != "https" or parsed.hostname not in HOSTS:
                raise ValueError("Unexpected cloud destination")
            if single_attempt and parsed.path in attempted:
                raise CloudQueryError({'http_status': None, 'tuya_error_code': None,
                    'category': 'automatic_retry_blocked', 'message_sanitized': 'Automatic retry blocked.'})
            attempted.add(parsed.path)
            http_evidence['http_status'] = None
            response = session.get(url, timeout=(5, 15), allow_redirects=False, **kwargs)
            if type(response.status_code) is int:
                http_evidence['http_status'] = response.status_code
            if single_attempt:
                from .cloud_evidence import failure_evidence
                try:
                    body = response.json()
                except ValueError:
                    body = None
                if not isinstance(body, dict) or body.get('success') is not True:
                    raise CloudQueryError(failure_evidence(body, http_evidence['http_status'],
                        sensitive=(api_id, secret, getattr(body, 'token', None))))
            return response
        def request(method, url, **kwargs):
            if method != "GET":
                raise ValueError("Cloud writes prohibited")
            return get(url, **kwargs)
        with quiet(), patch.object(module, "requests", SimpleNamespace(get=get, request=request, Request=requests.Request)):
            cloud = tinytuya.Cloud(apiRegion=region, apiKey=api_id, apiSecret=secret)
            if not cloud.token:
                raise RuntimeError("Cloud authentication failed; check project and region")
            cloud._smart_tray_http_evidence = http_evidence
            yield cloud


def device_details(cloud, device_id, api_id, api_secret):
    # Exact IDs from discovery only. No all-account exports or writes.
    response = cloud._tuyaplatform("devices/" + device_id)
    if not isinstance(response, dict) or not response.get("success"):
        return None, None, "metadata_api_denied_or_unavailable"
    result = response.get("result", {})
    if result.get("id") != device_id:
        return None, None, "device_id_mismatch"
    key = result.get("local_key")
    secrets = (api_id, api_secret, key, cloud.token)
    metadata = {field: clean_text(result.get(field), secrets) for field in
                ("name", "product_name", "product_id", "category", "model")}
    metadata["manufacturer"] = None  # Product name is not manufacturer proof.
    # A schema failure must not discard a successfully retrieved Local_Key.
    try:
        specs = cloud.getdps(device_id)
    except Exception:
        specs = None
    candidates = []
    if isinstance(specs, dict) and specs.get("success"):
        for section in ("status", "functions"):
            for dp in specs.get("result", {}).get(section, []):
                dp_id = dp.get("dp_id")
                if not str(dp_id).isdigit():
                    continue
                candidates.append({"dp_id": int(dp_id),
                                   "code": clean_text(dp.get("code"), secrets),
                                   "type": clean_text(dp.get("type"), secrets),
                                   "source": "cloud_" + section,
                                   "constraints": safe_constraints(dp.get("values"), secrets),
                                   "locally_validated": False})
    metadata["cloud_dps_candidates"] = candidates
    return metadata, key, "metadata_available"


def safe_constraints(values, secrets=()):
    """Only known specification constraints; never arbitrary JSON strings."""
    if isinstance(values, str):
        try:
            values = json.loads(values)
        except ValueError:
            return {}
    if not isinstance(values, dict):
        return {}
    result = {}
    for name, value in values.items():
        if name in {"min", "max", "scale", "step"} and type(value) in (int, float):
            result[name] = value
        elif name == "range" and isinstance(value, list) and len(value) <= 32:
            safe = [v for v in value if isinstance(v, str) and re.fullmatch(r"[a-zA-Z0-9_]{1,24}", v) and v not in secrets]
            if len(safe) == len(value):
                result[name] = safe
        elif name in {"h", "s", "v"} and isinstance(value, dict):
            result[name] = safe_constraints(value, secrets)
    return result


def collect_device(cloud, device_id, api_id, api_secret):
    """Isolate API/transport failures without exposing raw errors or blocking peers."""
    try:
        return device_details(cloud, device_id, api_id, api_secret)
    except Exception:
        return None, None, "device_api_error"


def query_status(record, key, factory=tinytuya.Device):
    ip = ipaddress.IPv4Address(record["ip"])
    if not any(ip in ipaddress.IPv4Network(network) for network in ('10.0.0.0/8','172.16.0.0/12','192.168.0.0/16')):
        raise ValueError("IP outside authorized LAN")
    version = str(record["protocol_version"])
    if version not in {"3.3", "3.4", "3.5"}:
        raise ValueError("Unverified protocol")
    with quiet():
        device = factory(record["device_id"], str(ip), key, version=float(version), connection_timeout=3)
        try:
            device.set_socketRetryLimit(1)
            response = device.status()  # DP_QUERY only; no set/update/detect DPS.
        finally:
            device.close()
    if not isinstance(response, dict) or response.get("Err") or not isinstance(response.get("dps"), dict):
        return {"result": "read_failed_or_no_dps", "dps": {}, "protocol_authenticated": False}
    dps = {}
    for dp, value in response["dps"].items():
        if not str(dp).isdigit():
            continue
        # Unknown string/raw DPS can contain credentials: retain only type.
        visible = value if type(value) in (bool, int, float) else "[withheld_pending_schema_review]"
        dps[str(dp)] = {"type": type(value).__name__, "value": visible, "function": "unverified"}
    return {"result": "local_read_ok", "dps": dps, "protocol_authenticated": True}
