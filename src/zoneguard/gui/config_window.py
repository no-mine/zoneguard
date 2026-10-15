"""Settings window: daemon controls, defaults, known networks, and profiles."""
from __future__ import annotations

import logging
import subprocess

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, GLib, Gtk

from .. import applier, systemd_control, zone_manager
from ..config import Settings
from ..store import NetworkEntry, NetworkStore
from ..zone_manager import SAFE_FALLBACK_ZONE, available_zones_or_fallback
from .pending_changes import PendingChanges
from .profiles_page import ProfilesPage

log = logging.getLogger(__name__)

STATUS_POLL_SECONDS = 5


class ConfigWindow(Adw.ApplicationWindow):
    def __init__(self, app: Adw.Application) -> None:
        super().__init__(application=app, title="ZoneGuard Settings")
        self.set_default_size(560, 680)

        self.store = NetworkStore()
        self.settings = Settings.load()
        self.pending = PendingChanges(on_change=self._update_apply_button)
        self._queued_deletions: list[str] = []
        self.zones = available_zones_or_fallback()

        self.toast_overlay = Adw.ToastOverlay()
        self.set_content(self.toast_overlay)

        toolbar_view = Adw.ToolbarView()
        self.toast_overlay.set_child(toolbar_view)

        self.view_stack = Adw.ViewStack()
        switcher_title = Adw.ViewSwitcherTitle(stack=self.view_stack, title="ZoneGuard")

        header = Adw.HeaderBar()
        header.set_title_widget(switcher_title)
        self.apply_btn = Gtk.Button(label="Apply")
        self.apply_btn.add_css_class("suggested-action")
        self.apply_btn.set_sensitive(False)
        self.apply_btn.set_tooltip_text("Commit pending firewalld changes")
        self.apply_btn.connect("clicked", self._on_apply_clicked)
        header.pack_end(self.apply_btn)
        toolbar_view.add_top_bar(header)
        toolbar_view.set_content(self.view_stack)

        general_page = Adw.PreferencesPage()
        self.view_stack.add_titled(general_page, "general", "General")
        general_page.set_icon_name("preferences-system-symbolic")

        self.daemon_group = Adw.PreferencesGroup(title="Daemon")
        general_page.add(self.daemon_group)
        self._build_daemon_rows()

        defaults_group = Adw.PreferencesGroup(title="Defaults")
        general_page.add(defaults_group)
        self.default_zone_row = self._build_default_zone_row()
        defaults_group.add(self.default_zone_row)
        defaults_group.add(self._build_notify_row())

        self.networks_group = Adw.PreferencesGroup(title="Known networks")
        general_page.add(self.networks_group)
        self._network_rows: list[Gtk.Widget] = []
        self._reload_networks()

        self.profiles_page = ProfilesPage(
            pending=self.pending,
            on_zone_queued_for_deletion=self._on_zone_queued_for_deletion,
            on_error=self._show_toast,
        )
        self.view_stack.add_titled(self.profiles_page.page, "profiles", "Profiles")
        self.profiles_page.page.set_icon_name("network-wireless-symbolic")

        self._polling = True
        GLib.timeout_add_seconds(STATUS_POLL_SECONDS, self._poll_daemon_status)
        self.connect("close-request", self._on_close_request)

    def _show_toast(self, message: str) -> None:
        self.toast_overlay.add_toast(Adw.Toast(title=message, timeout=5))

    def _apply_zone_live(self, uuid: str, zone: str) -> None:
        """Best-effort: entries from older versions have no UUID to act on,
        and the connection may have gone away since it was recorded."""
        if not uuid:
            return
        try:
            applier.apply_zone_to_active_connection(uuid, zone)
        except (OSError, subprocess.CalledProcessError):
            log.warning("Could not apply zone %r live for connection %s", zone, uuid)

    def _on_zone_deleted(self, zone: str) -> None:
        """Reset anything that still pointed at a just-deleted zone."""
        reset_default = self.settings.default_zone == zone
        if reset_default:
            self.settings.default_zone = SAFE_FALLBACK_ZONE
            self.settings.save()

        affected = [
            (fp, entry)
            for fp, entry in self.store.all().items()
            if entry.zone == zone
        ]
        for fingerprint, entry in affected:
            self.store.upsert(
                fingerprint,
                label=entry.label,
                zone=SAFE_FALLBACK_ZONE,
                confirmed=False,
            )
            self._apply_zone_live(entry.uuid, SAFE_FALLBACK_ZONE)

        self._refresh_zone_choices()

        if reset_default or affected:
            parts = []
            if reset_default:
                parts.append("the default zone")
            if affected:
                parts.append(f"{len(affected)} remembered network(s)")
            self._show_toast(
                f"'{zone}' was deleted; reset {' and '.join(parts)} "
                f"to '{SAFE_FALLBACK_ZONE}'."
            )

    def _refresh_zone_choices(self) -> None:
        self.zones = available_zones_or_fallback()

        # Replacing the model resets "selected" to 0, which fires
        # notify::selected on the still-attached handler with the wrong
        # zone -- disconnect it first so that spurious event can't
        # overwrite the real setting with whatever's at index 0.
        row = self.default_zone_row
        row.disconnect(row._zoneguard_selected_handler)
        row.set_model(Gtk.StringList.new(self.zones))
        if self.settings.default_zone in self.zones:
            row.set_selected(self.zones.index(self.settings.default_zone))
        row._zoneguard_selected_handler = row.connect(
            "notify::selected", self._on_default_zone_changed
        )

        self._reload_networks()

    def _update_apply_button(self) -> None:
        self.apply_btn.set_sensitive(len(self.pending) > 0)

    def _on_zone_queued_for_deletion(self, zone: str) -> None:
        self._queued_deletions.append(zone)

    def _on_apply_clicked(self, _btn: Gtk.Button) -> None:
        if not len(self.pending):
            return
        commands = self.pending.take()
        deletions, self._queued_deletions = self._queued_deletions, []

        try:
            zone_manager.apply_batch(commands)
        except zone_manager.FIREWALLD_ERRORS as exc:
            self._show_toast(f"Couldn't apply changes: {exc}")
        else:
            self._show_toast("Changes applied.")
            for zone in deletions:
                self._on_zone_deleted(zone)

        # Resync with reality either way -- a partial failure may have
        # applied some of the batch, and pending rows were only ever a
        # local guess at what Apply would do.
        self.profiles_page.reload()
        self._refresh_zone_choices()

    def _on_close_request(self, *_args) -> bool:
        self._polling = False
        return False

    def _poll_daemon_status(self) -> bool:
        if not self._polling:
            return False
        self._update_daemon_status_row()
        self.store.reload()  # pick up networks the daemon (a separate process) detects
        # Only rebuild when something actually changed: tearing the rows down
        # closes any dropdown the user currently has open.
        if self._networks_snapshot() != self._shown_networks:
            self._reload_networks()
        return True

    # --- daemon controls --------------------------------------------------

    def _build_daemon_rows(self) -> None:
        self.status_row = Adw.ActionRow(title="Daemon status")
        self.daemon_group.add(self.status_row)

        button_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        button_box.set_valign(Gtk.Align.CENTER)

        self.start_stop_btn = Gtk.Button()
        self.start_stop_btn.connect("clicked", self._on_start_stop_clicked)
        button_box.append(self.start_stop_btn)

        restart_btn = Gtk.Button(label="Restart")
        restart_btn.connect("clicked", self._on_restart_clicked)
        button_box.append(restart_btn)

        self.status_row.add_suffix(button_box)

        self.autostart_row = Adw.SwitchRow(
            title="Start automatically at login",
            active=systemd_control.is_enabled(),
        )
        self.autostart_row.connect("notify::active", self._on_autostart_toggled)
        self.daemon_group.add(self.autostart_row)

        self._update_daemon_status_row()

    def _update_daemon_status_row(self) -> None:
        active = systemd_control.is_active()
        self.status_row.set_subtitle("Running" if active else "Stopped")
        self.start_stop_btn.set_label("Stop" if active else "Start")

    def _report_systemctl(self, result: subprocess.CompletedProcess, action: str) -> None:
        """A failed systemctl call is otherwise invisible -- the status row
        just keeps reporting the old state with no explanation."""
        if result.returncode != 0:
            detail = result.stderr.strip() or f"systemctl exited {result.returncode}"
            self._show_toast(f"Couldn't {action} the daemon: {detail}")

    def _on_start_stop_clicked(self, _btn: Gtk.Button) -> None:
        if systemd_control.is_active():
            self._report_systemctl(systemd_control.stop(), "stop")
        else:
            self._report_systemctl(systemd_control.start(), "start")
        self._update_daemon_status_row()

    def _on_restart_clicked(self, _btn: Gtk.Button) -> None:
        self._report_systemctl(systemd_control.restart(), "restart")
        self._update_daemon_status_row()

    def _on_autostart_toggled(self, row: Adw.SwitchRow, _pspec) -> None:
        if row.get_active():
            self._report_systemctl(systemd_control.enable(now=False), "enable autostart for")
        else:
            self._report_systemctl(systemd_control.disable(now=False), "disable autostart for")

    # --- defaults ----------------------------------------------------------

    def _build_default_zone_row(self) -> Adw.ComboRow:
        model = Gtk.StringList.new(self.zones)
        row = Adw.ComboRow(title="Default zone for new networks", model=model)
        if self.settings.default_zone in self.zones:
            row.set_selected(self.zones.index(self.settings.default_zone))

        row._zoneguard_selected_handler = row.connect(
            "notify::selected", self._on_default_zone_changed
        )
        return row

    def _on_default_zone_changed(self, r: Adw.ComboRow, _pspec) -> None:
        zone = self.zones[r.get_selected()]
        self.settings.default_zone = zone
        self.settings.save()
        # Queue syncing firewalld's actual system default zone, rather
        # than applying it immediately: this is what lets a brand-new
        # network land in the restrictive zone with no per-connection
        # prompt at all (NM binds it there directly at activation), and
        # queuing it means it's committed together with any other
        # pending Profiles-tab edits on one Apply click.
        self.pending.add(["--set-default-zone", zone])

    def _build_notify_row(self) -> Adw.SwitchRow:
        row = Adw.SwitchRow(
            title="Notify when a new network is restricted",
            active=self.settings.notify,
        )

        def on_toggled(r: Adw.SwitchRow, _pspec) -> None:
            self.settings.notify = r.get_active()
            self.settings.save()

        row.connect("notify::active", on_toggled)
        return row

    # --- known networks ------------------------------------------------------

    def _networks_snapshot(self) -> list[tuple[str, str, str, bool]]:
        """Everything the rows actually render, so the poll can tell a real
        change from an unchanged re-read."""
        return [
            (fp, entry.label, entry.zone, entry.confirmed)
            for fp, entry in sorted(self.store.all().items())
        ]

    def _reload_networks(self) -> None:
        self._shown_networks = self._networks_snapshot()
        for row in self._network_rows:
            # Disconnect before removal: tearing down an Adw.ComboRow can
            # reset "selected", firing one last on_changed that would
            # resurrect the entry we're discarding.
            handler_id = getattr(row, "_zoneguard_selected_handler", None)
            if handler_id is not None:
                row.disconnect(handler_id)
            self.networks_group.remove(row)
        self._network_rows = []

        entries = sorted(self.store.all().items())
        if not entries:
            placeholder = Adw.ActionRow(title="No networks remembered yet")
            placeholder.set_sensitive(False)
            self.networks_group.add(placeholder)
            self._network_rows.append(placeholder)
            return

        for fingerprint, entry in entries:
            row = self._build_network_row(fingerprint, entry)
            self.networks_group.add(row)
            self._network_rows.append(row)

    def _build_network_row(self, fingerprint: str, entry: NetworkEntry) -> Adw.ComboRow:
        model = Gtk.StringList.new(self.zones)
        subtitle = "Confirmed" if entry.confirmed else "Unconfirmed — locked to a restrictive zone"
        row = Adw.ComboRow(title=entry.label, subtitle=subtitle, model=model)
        if entry.zone in self.zones:
            row.set_selected(self.zones.index(entry.zone))

        def on_changed(r: Adw.ComboRow, _pspec) -> None:
            zone = self.zones[r.get_selected()]
            self.store.upsert(fingerprint, label=entry.label, zone=zone, confirmed=True)
            self._apply_zone_live(entry.uuid, zone)
            row.set_subtitle("Confirmed")

        row._zoneguard_selected_handler = row.connect("notify::selected", on_changed)

        forget_btn = Gtk.Button(icon_name="user-trash-symbolic")
        forget_btn.add_css_class("flat")
        forget_btn.set_valign(Gtk.Align.CENTER)
        forget_btn.set_tooltip_text("Forget this network")

        def on_delete(_btn: Gtk.Button) -> None:
            self.store.remove(fingerprint)
            self._reload_networks()

        forget_btn.connect("clicked", on_delete)
        row.add_suffix(forget_btn)

        return row
