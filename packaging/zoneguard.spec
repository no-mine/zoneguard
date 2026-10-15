Name:           zoneguard
Version:        0.6.1
Release:        1%{?dist}
Summary:        Windows-style new-network firewall zone prompting for Linux

# No license chosen yet -- all rights reserved, not redistributable.
License:        LicenseRef-UNKNOWN
Source0:        %{name}-%{version}.tar.gz

BuildArch:      noarch

BuildRequires:  python3-devel
BuildRequires:  python3-setuptools >= 68
BuildRequires:  python3-gobject
BuildRequires:  pyproject-rpm-macros
BuildRequires:  systemd-rpm-macros
BuildRequires:  python3-pytest

Requires:       python3-gobject
Requires:       NetworkManager
Requires:       NetworkManager-libnm
Requires:       firewalld
Requires:       gtk4
Requires:       libadwaita
Recommends:     libnotify

%description
ZoneGuard watches NetworkManager for newly joined networks. The first time
it sees a network it locks the interface to a restrictive firewalld zone and
prompts the user, via a small GTK dialog, to pick the real profile (home,
work, public, ...) -- mirroring the "new network detected" prompt Windows
shows, instead of silently reusing whatever zone/rules were set up for a
different network.

Includes zoneguard-daemon (the background watcher) and zoneguard-config (a
GTK settings window for reviewing and editing the zones already assigned to
known networks).

%prep
%autosetup -n %{name}-%{version}

%generate_buildrequires
%pyproject_buildrequires

%build
%pyproject_wheel

%install
%pyproject_install
%pyproject_save_files zoneguard

install -Dm0644 data/zoneguard-daemon.service %{buildroot}%{_userunitdir}/zoneguard-daemon.service
install -Dm0644 data/zoneguard-settings.desktop %{buildroot}%{_datadir}/applications/zoneguard-settings.desktop
install -Dm0644 data/icons/hicolor/scalable/apps/zoneguard.svg %{buildroot}%{_datadir}/icons/hicolor/scalable/apps/zoneguard.svg
install -Dm0644 data/icons/hicolor/symbolic/apps/zoneguard-symbolic.svg %{buildroot}%{_datadir}/icons/hicolor/symbolic/apps/zoneguard-symbolic.svg

# Neither of these is installed by default -- both are opt-in, see README:
# - data/zoneguard-daemon.desktop (XDG autostart): the settings GUI manages
#   the systemd user unit directly, and shipping both risks two daemon
#   instances running at once.
# - data/zoneguard-polkit.rules: covers read-only firewalld queries only
#   (never config changes -- those always prompt via pkexec regardless).
#   Only useful if your setup doesn't already allow reads unauthenticated.

%check
# Only the pure-Python logic (fingerprinting, storage, firewalld/nmcli
# wrappers) is exercised here; the daemon and GTK windows import gi/libnm
# and need a live NetworkManager/firewalld/display session, which this
# build environment deliberately doesn't provide (PyGObject is a runtime
# Requires, not a build dependency, to keep the build environment light).
PYTHONPATH=%{buildroot}%{python3_sitelib} %{python3} -m pytest -v tests/

%files -f %{pyproject_files}
%doc README.md CHANGELOG.md
%{_bindir}/zoneguard-daemon
%{_bindir}/zoneguard-config
%{_userunitdir}/zoneguard-daemon.service
%{_datadir}/applications/zoneguard-settings.desktop
%{_datadir}/icons/hicolor/scalable/apps/zoneguard.svg
%{_datadir}/icons/hicolor/symbolic/apps/zoneguard-symbolic.svg

%changelog
* Thu Oct 15 2026 ZoneGuard Maintainers <zoneguard@example.com> - 0.6.1-1
- See CHANGELOG.md in the source tree for the full release history.
