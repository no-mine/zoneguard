"""The 'Profiles' page: create/delete firewalld zones and edit the services
and ports each one allows. Edits are optimistic: clicking +/trash updates
the row list immediately and queues the matching firewall-cmd argument
lists in a PendingChanges, but nothing reaches firewalld until the
window's Apply button commits the queue -- see ConfigWindow.
"""
from __future__ import annotations

from collections.abc import Callable

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gtk

from .. import zone_manager
from .pending_changes import PendingChanges


class ZoneExpanderRow(Adw.ExpanderRow):
    """One firewalld zone, expandable to show/edit its services and ports."""

    def __init__(
        self,
        *,
        zone: str,
        default_zone: str,
        all_services: list[str],
        initial_services: list[str],
        initial_ports: list[str],
        pending: PendingChanges,
        on_deleted: Callable[[ZoneExpanderRow, str], None],
    ) -> None:
        super().__init__(title=zone, subtitle="Default zone" if zone == default_zone else "")
        self.zone = zone
        self._pending = pending
        self._on_deleted = on_deleted
        self._all_services = all_services
        self._service_rows: list[Gtk.Widget] = []
        self._port_rows: list[Gtk.Widget] = []

        self._build_add_service_row()
        for service in initial_services:
            self._add_service_row(service)
        self._build_add_port_row()
        for port in initial_ports:
            self._add_port_row(port)
        self._build_delete_row()

    # -- shared row plumbing -------------------------------------------------

    def _queue(self, flag: str, value: str) -> None:
        """Queue the runtime and permanent halves of one edit together, so a
        change survives a firewalld reload as well as taking effect now."""
        self._pending.add(
            ["--zone", self.zone, flag, value],
            ["--permanent", "--zone", self.zone, flag, value],
        )

    def _add_item_row(self, kind: str, value: str, rows: list[Gtk.Widget]) -> None:
        row = Adw.ActionRow(title=value)
        remove_btn = Gtk.Button(icon_name="user-trash-symbolic")
        remove_btn.add_css_class("flat")
        remove_btn.set_valign(Gtk.Align.CENTER)
        remove_btn.set_tooltip_text(f"Remove {kind}")

        def on_remove(_btn: Gtk.Button) -> None:
            self._queue(f"--remove-{kind}", value)
            self.remove(row)
            rows.remove(row)

        remove_btn.connect("clicked", on_remove)
        row.add_suffix(remove_btn)
        self.add_row(row)
        rows.append(row)

    # -- services -----------------------------------------------------------

    def _build_add_service_row(self) -> None:
        row = Adw.ActionRow(title="Add a service")

        self._service_dropdown = Gtk.DropDown.new_from_strings(self._all_services or ["ssh"])
        self._service_dropdown.set_valign(Gtk.Align.CENTER)
        row.add_suffix(self._service_dropdown)

        add_btn = Gtk.Button(icon_name="list-add-symbolic")
        add_btn.add_css_class("flat")
        add_btn.set_valign(Gtk.Align.CENTER)
        add_btn.set_tooltip_text("Add service")
        add_btn.connect("clicked", self._on_add_service_clicked)
        row.add_suffix(add_btn)

        self.add_row(row)

    def _on_add_service_clicked(self, _btn: Gtk.Button) -> None:
        if not self._all_services:
            return
        service = self._all_services[self._service_dropdown.get_selected()]
        if any(r.get_title() == service for r in self._service_rows):
            return
        self._queue("--add-service", service)
        self._add_service_row(service)

    def _add_service_row(self, service: str) -> None:
        self._add_item_row("service", service, self._service_rows)

    # -- ports ----------------------------------------------------------------

    def _build_add_port_row(self) -> None:
        row = Adw.ActionRow(title="Add a port")

        self._port_entry = Gtk.Entry(placeholder_text="8080/tcp")
        self._port_entry.set_valign(Gtk.Align.CENTER)
        row.add_suffix(self._port_entry)

        add_btn = Gtk.Button(icon_name="list-add-symbolic")
        add_btn.add_css_class("flat")
        add_btn.set_valign(Gtk.Align.CENTER)
        add_btn.set_tooltip_text("Add port")
        add_btn.connect("clicked", self._on_add_port_clicked)
        row.add_suffix(add_btn)

        self.add_row(row)

    def _on_add_port_clicked(self, _btn: Gtk.Button) -> None:
        port = self._port_entry.get_text().strip()
        if not port:
            return
        self._port_entry.set_text("")
        if any(r.get_title() == port for r in self._port_rows):
            return
        self._queue("--add-port", port)
        self._add_port_row(port)

    def _add_port_row(self, port: str) -> None:
        self._add_item_row("port", port, self._port_rows)

    # -- delete zone -----------------------------------------------------------

    def _build_delete_row(self) -> None:
        row = Adw.ActionRow(title="Delete this profile")
        delete_btn = Gtk.Button(label="Delete")
        delete_btn.add_css_class("destructive-action")
        delete_btn.set_valign(Gtk.Align.CENTER)
        delete_btn.connect("clicked", self._on_delete_clicked)
        row.add_suffix(delete_btn)
        self.add_row(row)

    def _on_delete_clicked(self, _btn: Gtk.Button) -> None:
        self._pending.add(
            ["--permanent", "--delete-zone", self.zone],
            ["--reload"],
        )
        self._on_deleted(self, self.zone)


class ProfilesPage:
    """Owns the 'Profiles' Adw.PreferencesPage and keeps it in sync."""

    def __init__(
        self,
        pending: PendingChanges,
        on_zone_queued_for_deletion: Callable[[str], None],
        on_error: Callable[[str], None],
    ) -> None:
        self._pending = pending
        self._on_zone_queued_for_deletion = on_zone_queued_for_deletion
        self._on_error = on_error
        self._all_services: list[str] = []
        self.page = Adw.PreferencesPage()

        self.group = Adw.PreferencesGroup(
            title="Firewall Profiles",
            description=(
                "Each profile is a firewalld zone. Add or remove the services "
                "and ports it allows, or create a new one to assign to a "
                "network. Click Apply to commit your changes."
            ),
        )
        self.page.add(self.group)

        self._build_add_zone_row()

        self._zone_rows: list[ZoneExpanderRow] = []
        self.reload()

    def _build_add_zone_row(self) -> None:
        row = Adw.ActionRow(title="Add a new profile")

        self._new_zone_entry = Gtk.Entry(placeholder_text="e.g. cafe")
        self._new_zone_entry.set_valign(Gtk.Align.CENTER)
        row.add_suffix(self._new_zone_entry)

        add_btn = Gtk.Button(icon_name="list-add-symbolic")
        add_btn.add_css_class("flat")
        add_btn.set_valign(Gtk.Align.CENTER)
        add_btn.set_tooltip_text("Create profile")
        add_btn.connect("clicked", self._on_add_zone_clicked)
        row.add_suffix(add_btn)

        self.group.add(row)

    def _on_add_zone_clicked(self, _btn: Gtk.Button) -> None:
        name = self._new_zone_entry.get_text().strip()
        error = zone_manager.zone_name_error(name)
        if error is None and any(r.zone == name for r in self._zone_rows):
            error = f"A profile called '{name}' already exists."
        if error is not None:
            self._on_error(error)
            return
        self._pending.add(
            ["--permanent", "--new-zone", name],
            ["--reload"],
        )
        self._new_zone_entry.set_text("")
        row = ZoneExpanderRow(
            zone=name,
            default_zone="",
            all_services=self._all_services,
            initial_services=[],
            initial_ports=[],
            pending=self._pending,
            on_deleted=self._on_row_deleted,
        )
        self.group.add(row)
        self._zone_rows.append(row)

    def _on_row_deleted(self, row: ZoneExpanderRow, zone: str) -> None:
        self.group.remove(row)
        self._zone_rows.remove(row)
        self._on_zone_queued_for_deletion(zone)

    def reload(self) -> None:
        """Re-fetch from firewalld and rebuild. Call on first open and
        after a successful Apply -- discards any rows still pending."""
        for row in self._zone_rows:
            self.group.remove(row)
        self._zone_rows = []

        zones = zone_manager.available_zones_or_fallback()
        try:
            default_zone = zone_manager.get_default_zone()
            self._all_services = zone_manager.get_all_services()
            zones_info = zone_manager.list_all_zones()
        except zone_manager.FIREWALLD_ERRORS:
            default_zone = ""
            self._all_services = []
            zones_info = {}

        for zone in zones:
            info = zones_info.get(zone, {"services": [], "ports": []})
            row = ZoneExpanderRow(
                zone=zone,
                default_zone=default_zone,
                all_services=self._all_services,
                initial_services=info["services"],
                initial_ports=info["ports"],
                pending=self._pending,
                on_deleted=self._on_row_deleted,
            )
            self.group.add(row)
            self._zone_rows.append(row)
