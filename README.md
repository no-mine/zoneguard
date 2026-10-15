# ZoneGuard

Windows-style "new network detected" prompting for Linux, built on
firewalld and NetworkManager.

## The problem

firewalld already has zones (`public`, `home`, `work`, `trusted`, …), and
NetworkManager already supports binding a connection profile to one
(`connection.zone`). What's missing is the prompt: when you join a network
NetworkManager hasn't seen before, nothing asks what to trust it with, and
nothing stops it reusing whatever rules you set up for a different network.

ZoneGuard is a small daemon that closes that gap.

## How it works

When a connection activates, ZoneGuard computes a fingerprint for the
network — SSID for Wi-Fi, gateway address for wired — and then:

- **Known and confirmed** — re-applies the zone you chose for it.
- **New or unconfirmed** — immediately locks the interface to a restrictive
  zone (`drop` by default) and prompts you to pick a profile. Nothing is
  exposed while you decide.

Two components ship with it:

- **`zoneguard-daemon`** — the background watcher, run as a systemd `--user`
  service.
- **`zoneguard-config`** — a libadwaita settings window. **General** covers
  daemon start/stop/restart, start-at-login, the zones assigned to known
  networks, the default restrictive zone, and notifications. **Profiles**
  manages the firewalld zones themselves: create or delete a zone, and add
  or remove the services and ports it allows.

Profiles-tab edits and the default-zone change are queued and committed only
when you click **Apply** in the header bar, so a batch of edits needs at most
one authentication prompt rather than one per click.

For architecture, a module-by-module breakdown, config file formats, the
authentication design, and troubleshooting, see
[`docs/DOCUMENTATION.md`](docs/DOCUMENTATION.md).

## Requirements

System packages (names as on Fedora/RHEL-family distros):

- `NetworkManager`, `firewalld`
- `python3-gobject` (PyGObject)
- `NetworkManager-libnm` (provides the `NM-1.0` GI typelib)
- `gtk4`, `libadwaita` (GI typelibs for the GUI)
- `libnotify` (optional, for desktop notifications via `notify-send`)

Debian/Ubuntu package names are listed in `packaging/debian/control`.

## Installing

### From a package

```bash
sudo dnf install dist/rpmbuild/RPMS/noarch/zoneguard-*.noarch.rpm   # RPM
sudo apt install ./dist/deb/zoneguard_*.deb                         # deb
```

Then enable the daemon:

```bash
systemctl --user daemon-reload
systemctl --user enable --now zoneguard-daemon.service
```

Both package types point the unit at `/usr/bin/zoneguard-daemon` and omit the
XDG autostart entry, so only one daemon instance ever runs. After the first
`enable --now`, use `zoneguard-config` for day-to-day daemon control instead
of `systemctl`.

### From source

```bash
pip install --user .
```

This installs the `zoneguard-daemon` and `zoneguard-config` entry points,
typically to `~/.local/bin`. Copy `data/zoneguard-daemon.service` to
`~/.config/systemd/user/` and change its `ExecStart` to
`%h/.local/bin/zoneguard-daemon`, then enable it as above.

Optionally, copy `data/zoneguard-settings.desktop` to
`~/.local/share/applications/` and the icons under `data/icons/hicolor/` to
the matching paths below `~/.local/share/icons/hicolor/`, so the settings
window appears in your application menu.

`data/zoneguard-daemon.desktop` is an XDG autostart entry for anyone who
would rather not use systemd. Use it *instead of* the systemd unit, not
alongside it, or the daemon will run twice.

## Authentication prompts

Changing an already-active interface's zone at runtime requires
authorization. ZoneGuard only falls back to `pkexec` for changes made in
direct response to something you clicked — **Apply** in the new-network
dialog, or a zone edit in the settings window. Background work never
prompts, so reconnecting to a network you already trust is silent.

Two things keep that from becoming a prompt on every new network:

- The default-zone setting is kept in sync with firewalld's own system
  default zone, so NetworkManager binds a brand-new connection to the
  restrictive zone itself, with nothing to override.
- Every live zone change checks the interface's current zone first and skips
  the call entirely when it already matches.

Read-only queries (listing zones, services, and ports) need no
authorization under firewalld's default policy. If your policy differs,
installing `data/zoneguard-polkit.rules` to
`/etc/polkit-1/rules.d/49-zoneguard.rules` as root covers read-only queries;
it never authorizes a configuration change.

## Building packages

RPM and `.deb` packages are built inside podman containers, so the build
never touches the host (see `packaging/`). The containers carry only generic
build tooling — actual build dependencies are resolved from
`packaging/zoneguard.spec` and `packaging/debian/control` at build time via
`dnf builddep` and `mk-build-deps`, keeping those files the single source of
truth.

```bash
make packages     # everything below
make rpm          # Fedora + Rocky Linux 9 / RHEL 9
make rpm-fedora
make rpm-rocky9
make deb          # Ubuntu 24.04 + Debian 12
make deb-ubuntu
make deb-debian
```

Output lands in `dist/rpmbuild/RPMS/noarch/` and `SRPMS/` for RPMs, and
`dist/deb/` for `.deb`s. `make shell-<target>` opens a shell in that build
container, and `make clean` removes `dist/`.

The Debian/Ubuntu dependency names in `packaging/debian/control` — the
`gir1.2-*` GObject-introspection packages in particular — have not been
verified against every release and may need adjusting for yours.

## Known limitations

- Two Wi-Fi networks sharing an SSID (for example "Guest" at two different
  sites) fingerprint identically and are treated as one network. Windows has
  the same limitation.
- VPN connections are passed through untouched; ZoneGuard manages only Wi-Fi
  and wired connections.
- The GUI and the NetworkManager/firewalld integration need a real desktop
  session to exercise. Only the fingerprinting, storage, and zone-command
  logic is covered by automated tests.

## Development

```bash
pip install -e ".[dev]"
pytest
ruff check .
```

## License

No license has been chosen yet. Until one is added, all rights are
reserved and this project is not redistributable.
