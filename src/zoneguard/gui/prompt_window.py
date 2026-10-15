"""Dialog shown when ZoneGuard meets a network it doesn't recognize."""
from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gtk

from ..applier import apply_zone_with_fallback
from ..store import NetworkStore
from ..zone_manager import available_zones_or_fallback


def show_prompt(
    *,
    fingerprint: str,
    label: str,
    iface: str,
    uuid: str,
    current_zone: str,
    store: NetworkStore,
) -> None:
    zones = available_zones_or_fallback()

    window = Adw.Window(title="New Network", default_width=420, resizable=False)

    toolbar_view = Adw.ToolbarView()
    window.set_content(toolbar_view)
    toolbar_view.add_top_bar(Adw.HeaderBar(show_title=False))

    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=18)
    box.set_margin_top(6)
    box.set_margin_bottom(24)
    box.set_margin_start(24)
    box.set_margin_end(24)
    toolbar_view.set_content(box)

    icon = Gtk.Image.new_from_icon_name("zoneguard-symbolic")
    icon.set_pixel_size(48)
    icon.set_halign(Gtk.Align.CENTER)
    box.append(icon)

    heading = Gtk.Label(
        label=f"New network: “{label}”",
        wrap=True,
        justify=Gtk.Justification.CENTER,
    )
    heading.add_css_class("title-2")
    box.append(heading)

    body = Gtk.Label(
        label=(
            f"It's been restricted to the ‘{current_zone}’ zone for now. "
            f"Choose a firewall profile for it:"
        ),
        wrap=True,
        justify=Gtk.Justification.CENTER,
    )
    body.add_css_class("dim-label")
    box.append(body)

    group = Adw.PreferencesGroup()
    box.append(group)

    model = Gtk.StringList.new(zones)
    combo_row = Adw.ComboRow(title="Firewall zone", model=model)
    if current_zone in zones:
        combo_row.set_selected(zones.index(current_zone))
    group.add(combo_row)

    remember_row = Adw.SwitchRow(title="Remember this choice", active=True)
    group.add(remember_row)

    button_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8, homogeneous=True)
    box.append(button_box)

    later_btn = Gtk.Button(label="Decide Later")
    later_btn.connect("clicked", lambda _b: window.close())
    button_box.append(later_btn)

    apply_btn = Gtk.Button(label="Apply")
    apply_btn.add_css_class("suggested-action")

    def on_apply(_btn: Gtk.Button) -> None:
        # Routed through the fallback helper because the chosen zone can be
        # deleted between this dialog opening and the click.
        applied = apply_zone_with_fallback(
            uuid, iface, zones[combo_row.get_selected()], use_pkexec=True
        )
        store.upsert(
            fingerprint, label=label, zone=applied, confirmed=remember_row.get_active()
        )
        window.close()

    apply_btn.connect("clicked", on_apply)
    button_box.append(apply_btn)

    window.present()
