from zoneguard.fingerprint import NetworkInfo, compute_fingerprint, is_promptable


def test_wifi_fingerprint_uses_ssid():
    info = NetworkInfo(conn_type="802-11-wireless", uuid="u1", ssid="HomeNet")
    assert compute_fingerprint(info) == "wifi:HomeNet"


def test_wifi_fingerprint_stable_across_different_uuid_same_ssid():
    a = NetworkInfo(conn_type="802-11-wireless", uuid="u1", ssid="CafeWifi")
    b = NetworkInfo(conn_type="802-11-wireless", uuid="u2", ssid="CafeWifi")
    assert compute_fingerprint(a) == compute_fingerprint(b)


def test_ethernet_fingerprint_uses_gateway_when_known():
    info = NetworkInfo(conn_type="802-3-ethernet", uuid="u1", gateway="192.168.1.1")
    assert compute_fingerprint(info) == "eth-gw:192.168.1.1"


def test_ethernet_fingerprint_falls_back_to_uuid():
    info = NetworkInfo(conn_type="802-3-ethernet", uuid="u1", gateway=None)
    assert compute_fingerprint(info) == "eth-uuid:u1"


def test_ethernet_same_profile_different_gateway_is_a_new_network():
    a = NetworkInfo(conn_type="802-3-ethernet", uuid="shared-profile", gateway="10.0.0.1")
    b = NetworkInfo(conn_type="802-3-ethernet", uuid="shared-profile", gateway="10.0.1.1")
    assert compute_fingerprint(a) != compute_fingerprint(b)


def test_vpn_is_not_promptable():
    info = NetworkInfo(conn_type="vpn", uuid="u1")
    assert not is_promptable(info)


def test_wifi_and_ethernet_are_promptable():
    assert is_promptable(NetworkInfo(conn_type="802-11-wireless", uuid="u1", ssid="x"))
    assert is_promptable(NetworkInfo(conn_type="802-3-ethernet", uuid="u1"))
