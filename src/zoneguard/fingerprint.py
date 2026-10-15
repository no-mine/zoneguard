from __future__ import annotations

from dataclasses import dataclass

WIRELESS = "802-11-wireless"
ETHERNET = "802-3-ethernet"


@dataclass(frozen=True)
class NetworkInfo:
    """Raw facts about an activated connection, gathered from NetworkManager."""

    conn_type: str  # e.g. "802-11-wireless", "802-3-ethernet", "vpn"
    uuid: str
    ssid: str | None = None
    gateway: str | None = None


def compute_fingerprint(info: NetworkInfo) -> str:
    """Stable network identity: SSID for Wi-Fi, gateway IP for Ethernet
    (NM connection UUID isn't reliable -- profiles get recreated/reused).
    Same-SSID networks at different sites fingerprint identically; so does Windows."""
    if info.conn_type == WIRELESS and info.ssid:
        return f"wifi:{info.ssid}"
    if info.conn_type == ETHERNET:
        if info.gateway:
            return f"eth-gw:{info.gateway}"
        return f"eth-uuid:{info.uuid}"
    return f"{info.conn_type}:{info.uuid}"


def is_promptable(info: NetworkInfo) -> bool:
    """VPNs and other virtual connection types shouldn't trigger a zone prompt."""
    return info.conn_type in (WIRELESS, ETHERNET)
