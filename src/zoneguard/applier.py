"""Applies a zone to a single network, via nmcli and firewall-cmd."""
from __future__ import annotations

import logging
import subprocess

from .zone_manager import SAFE_FALLBACK_ZONE

log = logging.getLogger(__name__)


def set_connection_zone(uuid: str, zone: str) -> None:
    """Persist the zone on the NM connection profile (survives reboots)."""
    subprocess.run(
        ["nmcli", "connection", "modify", uuid, "connection.zone", zone],
        check=True,
    )


def get_current_zone(iface: str) -> str | None:
    """The zone `iface` is currently bound to, or None if undetermined."""
    try:
        result = subprocess.run(
            ["firewall-cmd", "--get-zone-of-interface", iface],
            capture_output=True,
            text=True,
        )
    except (subprocess.SubprocessError, OSError):
        return None
    if result.returncode != 0:
        return None
    return result.stdout.strip() or None


def apply_runtime_zone(iface: str, zone: str, use_pkexec: bool = False) -> bool:
    """Change `iface`'s live zone, returning whether it now matches.

    Set use_pkexec only for changes made in direct response to a user
    action, where an auth prompt is expected; background callers leave it
    off so routine reconnects stay silent. See docs/DOCUMENTATION.md.
    """
    if get_current_zone(iface) == zone:
        return True

    cmd = ["firewall-cmd", "--zone", zone, "--change-interface", iface]
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True)
        return True
    except subprocess.CalledProcessError:
        pass

    if not use_pkexec:
        log.info(
            "Zone %r not applied live to %s; it takes effect on the next reconnect.",
            zone,
            iface,
        )
        return False

    try:
        subprocess.run(["pkexec", *cmd], check=True, capture_output=True, text=True)
        return True
    except FileNotFoundError:
        log.warning("pkexec is not installed; zone %r not applied to %s", zone, iface)
    except subprocess.CalledProcessError as exc:
        log.warning(
            "pkexec could not apply zone %r to %s: %s",
            zone,
            iface,
            (exc.stderr or "").strip(),
        )
    return False


def get_active_interface(uuid: str) -> str | None:
    """The interface `uuid` is active on right now, or None."""
    result = subprocess.run(
        ["nmcli", "-g", "GENERAL.DEVICES", "connection", "show", uuid],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return None
    return result.stdout.strip() or None


def apply_zone_to_active_connection(uuid: str, zone: str) -> None:
    """Persist `zone` on the connection and, if it is active right now, push
    it live so the change doesn't wait for a reconnect."""
    set_connection_zone(uuid, zone)
    iface = get_active_interface(uuid)
    if iface:
        apply_runtime_zone(iface, zone, use_pkexec=True)


def apply_zone_with_fallback(
    uuid: str,
    iface: str,
    zone: str,
    fallback: str = SAFE_FALLBACK_ZONE,
    use_pkexec: bool = False,
) -> str:
    """Apply `zone`, falling back to `fallback` (and returning it) if `zone`
    no longer exists -- e.g. it was deleted in the Profiles tab."""
    try:
        set_connection_zone(uuid, zone)
    except subprocess.CalledProcessError:
        log.warning("Zone %r no longer exists; falling back to %r for %s", zone, fallback, iface)
        zone = fallback
        set_connection_zone(uuid, zone)
    apply_runtime_zone(iface, zone, use_pkexec=use_pkexec)
    return zone
