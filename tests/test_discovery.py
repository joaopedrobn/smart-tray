import importlib.util
import ipaddress
from pathlib import Path
from unittest.mock import patch

import pytest

spec = importlib.util.spec_from_file_location("discovery", Path(__file__).parents[1] / "scripts/discover.py")
discovery = importlib.util.module_from_spec(spec)
spec.loader.exec_module(discovery)


def test_report_excludes_secrets_and_other_networks():
    result = discovery.public_records({
        "10.77.0.20": {"gwId": "example", "version": "3.3", "key": "SECRET", "local_key": "SECRET"},
        "10.0.0.20": {"gwId": "outside"},
        "invalid": {},
    }, ipaddress.IPv4Network("10.77.0.0/24"))
    assert len(result) == 1
    assert result[0]["device_id"] == "example"
    assert "SECRET" not in str(result)
    assert "key" not in result[0]


@pytest.mark.parametrize("ip,cidr,seconds", [
    ("8.8.8.8", "8.8.8.0/24", 30),
    ("192.168.4.2", "10.77.0.0/24", 30),
    ("10.77.0.2", "10.77.0.0/24", 120),
])
def test_unsafe_scope_rejected_before_network_access(ip, cidr, seconds):
    with patch.object(discovery.tinytuya, "deviceScan") as scan:
        with pytest.raises(ValueError):
            discovery.discover(ip, cidr, seconds)
        scan.assert_not_called()


def test_discovery_never_polls_or_force_scans():
    with patch.object(discovery.tinytuya, "deviceScan", return_value={}) as scan:
        assert discovery.discover("10.77.0.66", "10.77.0.0/24", 30) == []
        scan.assert_called_once_with(verbose=False, maxretry=30, color=False, poll=False, forcescan=False)
