"""Bounded TinyTuya discovery: no polling, keys, forced scan or device control."""
import argparse
import ipaddress
import json
import logging
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import tinytuya
from tinytuya import scanner


def public_records(found, network):
    records = []
    for address, item in found.items():
        try:
            ip = ipaddress.IPv4Address(address)
        except ipaddress.AddressValueError:
            continue
        if ip not in network:
            continue
        # Allowlist: never serialize TinyTuya's key or raw broadcast payload.
        records.append({
            "ip": str(ip),
            "device_id": item.get("gwId") or item.get("id"),
            "protocol_version": item.get("version"),
            "product_id": item.get("productKey") or item.get("product_id"),
            "name": item.get("name") or None,
            "mac": item.get("mac") or None,
            "origin": item.get("origin"),
            "local_read": "not_attempted",
            "local_control": "not_tested",
            "local_key_requirement": "required_for_authenticated_access; legacy_3.1_read_may_not_require_key",
        })
    return records


def discover(local_ip, cidr, seconds):
    network = ipaddress.IPv4Network(cidr, strict=True)
    ip = ipaddress.IPv4Address(local_ip)
    if not any(network.subnet_of(ipaddress.IPv4Network(n)) for n in
               ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16")):
        raise ValueError("Only RFC1918 private LANs are allowed")
    if ip not in network or ip in (network.network_address, network.broadcast_address):
        raise ValueError("Interface IP must belong to the selected LAN")
    if not 1 <= seconds <= 60:
        raise ValueError("Discovery duration must be between 1 and 60 seconds")
    # Restrict official discovery broadcasts to one explicitly selected interface.
    # Prevent implicit loading of plaintext wizard files. No TCP connections.
    with patch.object(scanner, "get_ip_to_broadcast", return_value={str(network.broadcast_address): str(ip)}), \
         patch.object(tinytuya, "load_devicefile", return_value=[]):
        found = tinytuya.deviceScan(verbose=False, maxretry=seconds, color=False,
                                   poll=False, forcescan=False)
    return public_records(found, network)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--local-ip", required=True)
    parser.add_argument("--network", required=True)
    parser.add_argument("--seconds", type=int, default=30)
    parser.add_argument("--output", type=Path, default=Path("diagnostics/discovery.json"))
    args = parser.parse_args()
    logging.getLogger("tinytuya").setLevel(logging.CRITICAL)
    records = discover(args.local_ip, args.network, args.seconds)
    # Local timezone without requiring a separate IANA database on Windows.
    from datetime import timezone, timedelta
    report = {"timestamp": datetime.now(timezone(timedelta(hours=-3))).isoformat(),
              "interface_ip": args.local_ip, "network": args.network,
              "duration_seconds": args.seconds, "poll": False, "force_scan": False,
              "discovery_udp_ports": [6666, 6667, 7000],
              "devices": records}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    visible = {**report, "devices": [{**d, "device_id": d["device_id"][:6] + "…" + d["device_id"][-4:]} for d in records]}
    print(json.dumps(visible, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
