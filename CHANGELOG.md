# Changelog

All notable changes to ZoneGuard are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.6.1] - 2026-10-15

### Fixed

- Changing "Default zone for new networks" and clicking **Apply** could
  silently revert to the wrong zone. Rebuilding the zone list after a
  successful Apply replaces the combo row's model, which resets its
  `selected` property and fired the still-attached handler with whatever
  zone sat at index 0 — overwriting the setting that had just been applied
  and queuing a stray `--set-default-zone` for the wrong zone. The handler
  is now disconnected around the refresh, matching how the Known Networks
  rows already avoided this.
- The new-network dialog crashed its handler instead of recovering when the
  chosen zone was deleted between the prompt appearing and **Apply** being
  clicked. It now uses the same fallback path as every other caller.
- The daemon no longer overwrites the configured default zone when that zone
  is temporarily missing; it falls back for that activation and logs, so the
  setting survives for when the zone exists again.
- `settings.json` and `networks.json` are written atomically. The daemon and
  the GUI are separate processes sharing both files, so a half-written file
  could previously be read back as corrupt; a malformed or hand-edited file
  now falls back to defaults instead of stopping the daemon.
- Queued zone deletions could be discarded if the pending-command queue was
  empty when **Apply** was clicked.
- The Known Networks list was torn down and rebuilt on every 5-second poll
  whether or not anything had changed, which closed any zone dropdown the
  user had open. It now rebuilds only when the stored networks actually
  differ from what is on screen.
- Daemon start, stop, restart and autostart failures were silently
  swallowed — the status row simply kept reporting the old state. The
  `systemctl` result is now checked and reported in a toast.
- Creating a profile whose name firewalld would reject (too long, or
  containing characters outside letters, digits, `-` and `_`) optimistically
  added a row and then failed the entire Apply batch with an opaque error.
  Names are now validated when entered, and duplicate or empty names give
  feedback instead of silently doing nothing.

### Changed

- Consolidated `zones.py` into `zone_manager.py`, so firewalld has a single
  interface module. Removed the unused `RESTRICTIVE_ZONES` constant and the
  `get_zone_services()`/`get_zone_ports()` helpers that `list_all_zones()`
  superseded in 0.6.0.
- The restrictive fallback zone is now one `SAFE_FALLBACK_ZONE` constant
  rather than four separate hardcoded literals.
- Narrowed blanket `except Exception` handlers to the errors that firewalld
  and NetworkManager calls actually raise.

### Added

- `pytest` now runs in a fresh checkout without an editable install first,
  and the project carries a ruff configuration.
- Test coverage for `config.py`, including the atomic-write behaviour.

## [0.6.0] - 2026-10-15

Initial public release. Versions 0.1.0 through 0.5.2 were pre-release
development iterations; their substantive changes are consolidated here.

### Added

- `zoneguard-daemon`: watches NetworkManager for connection activations,
  fingerprints each network (SSID for Wi-Fi, gateway for wired), and either
  re-applies the zone you confirmed for it or locks the interface to a
  restrictive zone and prompts.
- `zoneguard-config`: a libadwaita settings window with a **General** tab
  (daemon start/stop/restart/autostart, default zone, notifications, and the
  zones assigned to known networks) and a **Profiles** tab for managing
  firewalld zones and the services and ports each one allows.
- A batched **Apply** button. Profiles-tab edits and the default-zone change
  are queued and committed as one operation, so a burst of edits needs at
  most one authentication prompt rather than one per click.
- Syncing of firewalld's system default zone with ZoneGuard's "default zone
  for new networks". This is what removes the per-new-network auth prompt:
  NetworkManager binds a new connection straight to the restrictive zone at
  activation, so there is no already-applied zone to override.
- An opt-in polkit rule (`data/zoneguard-polkit.rules`) covering read-only
  firewalld queries. It never authorizes a configuration change.
- RPM and `.deb` packaging, built in podman containers so the build never
  touches the host.
- A desktop entry, application icons, and a systemd user unit.

### Fixed

- Only interactive actions escalate to `pkexec`. The daemon's automatic
  reconnect and self-heal paths never prompt, so rejoining a trusted network
  stays silent.
- Live zone changes check the interface's current zone first and skip the
  call entirely when it already matches, so confirming an already-correct
  zone is a no-op rather than a prompt.
- Deleting a zone that was in use no longer breaks subsequent new-network
  handling; the daemon falls back to a safe zone and the GUI resets affected
  settings and networks.
- Opening the Profiles tab fetches every zone's services and ports in two
  `firewall-cmd` calls rather than 25-30, which had made the tab slow to
  render.
- GUI zone corrections are pushed to the live NetworkManager connection and
  firewalld interface immediately, instead of waiting for a reconnect.
- The settings window picks up networks detected by the daemon while it is
  open.
- Forgetting a known network no longer leaves it in the list, re-added as
  confirmed, via a selection event fired during row teardown.
