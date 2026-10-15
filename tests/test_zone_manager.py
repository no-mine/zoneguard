import subprocess
from unittest.mock import MagicMock, patch

import pytest

from zoneguard import zone_manager


def _fake(stdout: str = "") -> MagicMock:
    return MagicMock(stdout=stdout)


def test_get_all_services_parses_output():
    with patch("subprocess.run", return_value=_fake("ssh http https\n")):
        assert zone_manager.get_all_services() == ["ssh", "http", "https"]


def test_get_available_zones_parses_output():
    with patch("subprocess.run", return_value=_fake("drop block public home\n")):
        assert zone_manager.get_available_zones() == ["drop", "block", "public", "home"]


def test_get_default_zone_strips_output():
    with patch("subprocess.run", return_value=_fake("public\n")):
        assert zone_manager.get_default_zone() == "public"


def test_available_zones_or_fallback_returns_live_zones():
    with patch("subprocess.run", return_value=_fake("drop home\n")):
        assert zone_manager.available_zones_or_fallback() == ["drop", "home"]


def test_available_zones_or_fallback_survives_missing_firewalld():
    with patch("subprocess.run", side_effect=FileNotFoundError):
        assert zone_manager.available_zones_or_fallback() == list(zone_manager.FALLBACK_ZONES)


def test_available_zones_or_fallback_survives_firewalld_error():
    error = subprocess.CalledProcessError(1, ["firewall-cmd"])
    with patch("subprocess.run", side_effect=error):
        assert zone_manager.available_zones_or_fallback() == list(zone_manager.FALLBACK_ZONES)


_LIST_ALL_ZONES_OUTPUT = """
block
  target: %%REJECT%%
  icmp-block-inversion: no
  interfaces:\x20
  sources:\x20
  services:\x20
  ports:\x20
  protocols:\x20
  forward: no
  masquerade: no
  forward-ports:\x20
  source-ports:\x20
  icmp-blocks:\x20
  rich rules:\x20

dmz
  target: default
  interfaces:\x20
  sources:\x20
  services: ssh
  ports:\x20

public (active)
  target: default
  interfaces: wlp0s20f3
  sources:\x20
  services: dhcpv6-client mdns ssh
  ports: 8080/tcp 9000-9010/udp
"""


def test_list_all_zones_single_call():
    with patch("subprocess.run", return_value=_fake(_LIST_ALL_ZONES_OUTPUT)) as run:
        zone_manager.list_all_zones()
    run.assert_called_once_with(
        ["firewall-cmd", "--list-all-zones"],
        capture_output=True,
        text=True,
        check=True,
    )


def test_list_all_zones_parses_services_and_ports_per_zone():
    with patch("subprocess.run", return_value=_fake(_LIST_ALL_ZONES_OUTPUT)):
        zones = zone_manager.list_all_zones()

    assert zones["block"] == {"services": [], "ports": []}
    assert zones["dmz"] == {"services": ["ssh"], "ports": []}
    assert zones["public"] == {
        "services": ["dhcpv6-client", "mdns", "ssh"],
        "ports": ["8080/tcp", "9000-9010/udp"],
    }


def test_apply_batch_runs_everything_unprivileged_when_authorized():
    with patch("subprocess.run", return_value=_fake()) as run:
        zone_manager.apply_batch(
            [
                ["--zone", "home", "--add-service", "ssh"],
                ["--permanent", "--zone", "home", "--add-service", "ssh"],
            ]
        )
    assert [c.args[0] for c in run.call_args_list] == [
        ["firewall-cmd", "--zone", "home", "--add-service", "ssh"],
        ["firewall-cmd", "--permanent", "--zone", "home", "--add-service", "ssh"],
    ]


def test_apply_batch_escalates_remaining_commands_as_one_pkexec_call():
    """Once a command fails unprivileged, everything from that point on --
    not just the one that failed -- should be retried as a single pkexec
    invocation, so a batch of edits needs at most one prompt."""
    calls = []

    def fake_run(args, **kwargs):
        calls.append(args)
        if args[0] == "pkexec":
            return _fake()
        raise subprocess.CalledProcessError(1, args, stderr="denied")

    with patch("subprocess.run", side_effect=fake_run):
        zone_manager.apply_batch(
            [
                ["--zone", "home", "--add-service", "ssh"],
                ["--permanent", "--zone", "home", "--add-service", "ssh"],
                ["--zone", "home", "--add-port", "8080/tcp"],
            ]
        )

    assert calls == [
        ["firewall-cmd", "--zone", "home", "--add-service", "ssh"],
        [
            "pkexec",
            "sh",
            "-c",
            "firewall-cmd --zone home --add-service ssh && "
            "firewall-cmd --permanent --zone home --add-service ssh && "
            "firewall-cmd --zone home --add-port 8080/tcp",
        ],
    ]


def test_apply_batch_shell_quotes_arguments():
    """Zone/service/port values are free text (typed into an Entry) --
    they must be safely quoted before landing in the pkexec'd shell
    script, not interpolated raw."""
    calls = []

    def fake_run(args, **kwargs):
        calls.append(args)
        raise subprocess.CalledProcessError(1, args, stderr="denied")

    with patch("subprocess.run", side_effect=fake_run), pytest.raises(
        subprocess.CalledProcessError
    ):
        zone_manager.apply_batch([["--permanent", "--new-zone", "cafe; rm -rf /"]])

    script = calls[-1][-1]
    assert script == "firewall-cmd --permanent --new-zone 'cafe; rm -rf /'"


def test_apply_batch_raises_when_pkexec_also_fails():
    err = subprocess.CalledProcessError(1, "x", stderr="denied")
    with patch("subprocess.run", side_effect=err), pytest.raises(subprocess.CalledProcessError):
        zone_manager.apply_batch([["--permanent", "--delete-zone", "roaming"]])


def test_zone_name_error_accepts_valid_names():
    for name in ("cafe", "work-vpn", "lab_2", "a", "x" * 17):
        assert zone_manager.zone_name_error(name) is None


def test_zone_name_error_rejects_empty_name():
    assert zone_manager.zone_name_error("") is not None


def test_zone_name_error_rejects_overlong_name():
    assert zone_manager.zone_name_error("x" * 18) is not None


def test_zone_name_error_rejects_shell_metacharacters():
    for name in ("cafe; rm -rf /", "my zone", "zone/sub", "zone$(id)"):
        assert zone_manager.zone_name_error(name) is not None
