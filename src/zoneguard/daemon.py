"""Watches NetworkManager and enforces/prompts firewalld zones per network."""
from __future__ import annotations

import logging

import gi

gi.require_version("NM", "1.0")
from gi.repository import NM, GLib

from .applier import apply_zone_with_fallback
from .config import Settings
from .fingerprint import NetworkInfo, compute_fingerprint, is_promptable
from .notifier import notify
from .store import NetworkStore

log = logging.getLogger(__name__)


def _network_info_for(device: NM.Device, conn: NM.RemoteConnection) -> NetworkInfo:
    settings = conn.get_setting_connection()
    conn_type = settings.get_connection_type()
    uuid = settings.get_uuid()
    ssid = None
    gateway = None

    if conn_type == "802-11-wireless" and isinstance(device, NM.DeviceWifi):
        ap = device.get_active_access_point()
        if ap is not None:
            ssid_bytes = ap.get_ssid()
            if ssid_bytes is not None:
                ssid = NM.utils_ssid_to_utf8(ssid_bytes.get_data())

    active_conn = device.get_active_connection()
    if active_conn is not None:
        ip4 = active_conn.get_ip4_config()
        if ip4 is not None:
            gateway = ip4.get_gateway()

    return NetworkInfo(conn_type=conn_type, uuid=uuid, ssid=ssid, gateway=gateway)


class ZoneGuardDaemon:
    def __init__(self) -> None:
        self.client = NM.Client.new(None)
        self.settings = Settings.load()
        self.store = NetworkStore()
        self._watched: set[str] = set()

    def start(self) -> None:
        for device in self.client.get_devices():
            self._watch(device)
        self.client.connect("device-added", lambda c, d: self._watch(d))
        log.info("ZoneGuard daemon watching %d device(s)", len(self.client.get_devices()))

    def _watch(self, device: NM.Device) -> None:
        path = device.get_path()
        if path in self._watched:
            return
        self._watched.add(path)
        device.connect("state-changed", self._on_state_changed)

    def _on_state_changed(self, device, new_state, old_state, reason) -> None:
        if new_state == NM.DeviceState.ACTIVATED:
            try:
                self._handle_activation(device)
            except Exception:
                log.exception("Failed handling activation of %s", device.get_iface())

    def _handle_activation(self, device: NM.Device) -> None:
        active_conn = device.get_active_connection()
        if active_conn is None:
            return
        conn = active_conn.get_connection()
        if conn is None:
            return

        info = _network_info_for(device, conn)
        if not is_promptable(info):
            return

        fp = compute_fingerprint(info)
        label = info.ssid or device.get_iface()
        iface = device.get_iface()
        uuid = info.uuid

        entry = self.store.get(fp)
        if entry is not None and entry.confirmed:
            applied = apply_zone_with_fallback(uuid, iface, entry.zone)
            if applied != entry.zone:
                # Remembered zone is gone -- ask again instead of sitting on the fallback.
                self.store.upsert(fp, label=label, zone=applied, confirmed=False, uuid=uuid)
            else:
                self.store.touch_last_seen(fp)
            return

        # Unknown or unconfirmed network: lock it down first, ask second.
        zone = apply_zone_with_fallback(uuid, iface, self.settings.default_zone)
        if zone != self.settings.default_zone:
            # Don't persist the fallback over the user's choice -- the
            # configured zone may well exist again by the next activation.
            log.warning(
                "Default zone %r is unavailable; used %r for %s instead.",
                self.settings.default_zone,
                zone,
                label,
            )

        self.store.upsert(fp, label=label, zone=zone, confirmed=False, uuid=uuid)

        if self.settings.notify:
            notify(
                "New network detected",
                f"'{label}' was restricted to the '{zone}' firewall zone. "
                f"Open ZoneGuard settings to choose a profile for it.",
            )
        self._launch_prompt(fp, label, iface, uuid, zone)

    def _launch_prompt(self, fp: str, label: str, iface: str, uuid: str, zone: str) -> None:
        from .gui.prompt_window import show_prompt

        show_prompt(
            fingerprint=fp,
            label=label,
            iface=iface,
            uuid=uuid,
            current_zone=zone,
            store=self.store,
        )


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    gi.require_version("Gtk", "4.0")
    gi.require_version("Adw", "1")
    from gi.repository import Adw, Gtk

    Gtk.init()
    Adw.init()

    daemon = ZoneGuardDaemon()
    daemon.start()
    GLib.MainLoop().run()


if __name__ == "__main__":
    main()
