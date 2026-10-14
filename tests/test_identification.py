import copy
import pytest

from smart_tray.diagnostic import associate


def evidence():
    return ([{"role": "elgin", "name": "Elgin", "device_id": "exact-id", "mac": "02:00:00:00:00:03", "app": "Elgin Smart", "manufacturer": "Elgin", "model": "HJFC12C2WGCG"}],
            [{"device_id": "exact-id", "ip": "10.77.0.138", "protocol_version": "3.5"}],
            [{"ip": "10.77.0.138", "mac": "02-00-00-00-00-03", "state": "Stale"}])


def test_exact_id_and_normalized_mac_confirm_identity_only():
    record = associate(*evidence())[0]
    assert record["role"] == "elgin"
    assert record["protocol_version"] == "3.5"
    assert not record["protocol_authenticated"]
    assert record["credential"] == "pending"
    assert record["local_control"] == "not_tested"


def test_same_mac_with_different_id_is_rejected():
    identities, found, arp = evidence()
    identities[0]["device_id"] = "different-id"
    with pytest.raises(ValueError, match="absent"):
        associate(identities, found, arp)


def test_same_id_with_different_mac_is_rejected():
    identities, found, arp = evidence()
    arp[0]["mac"] = "00-11-22-33-44-55"
    with pytest.raises(ValueError, match="does not match"):
        associate(identities, found, arp)


def test_duplicate_id_is_rejected():
    identities, found, arp = evidence()
    identities.append(copy.deepcopy(identities[0]))
    with pytest.raises(ValueError, match="Duplicate"):
        associate(identities, found, arp)
