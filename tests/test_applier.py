import subprocess
from unittest.mock import MagicMock, patch

from zoneguard import applier


def test_set_connection_zone_invokes_nmcli():
    with patch("subprocess.run") as run:
        applier.set_connection_zone("uuid-1", "home")
    run.assert_called_once_with(
        ["nmcli", "connection", "modify", "uuid-1", "connection.zone", "home"],
        check=True,
    )


def test_apply_runtime_zone_returns_true_on_success():
    with patch("subprocess.run"):
        assert applier.apply_runtime_zone("wlan0", "home") is True


def test_apply_runtime_zone_returns_false_and_logs_on_failure():
    err = subprocess.CalledProcessError(1, "firewall-cmd", stderr="denied")
    with patch("subprocess.run", side_effect=err):
        assert applier.apply_runtime_zone("wlan0", "home") is False


def test_apply_runtime_zone_does_not_use_pkexec_by_default():
    """Automatic/background callers (the daemon) must never trigger a
    surprise auth prompt on a routine reconnect -- use_pkexec defaults to
    False, so a failure here should NOT attempt pkexec at all."""
    calls = []

    def fake_run(args, **kwargs):
        calls.append(args)
        raise subprocess.CalledProcessError(1, args, stderr="denied")

    with patch("subprocess.run", side_effect=fake_run):
        assert applier.apply_runtime_zone("wlan0", "home") is False

    assert calls == [
        ["firewall-cmd", "--get-zone-of-interface", "wlan0"],
        ["firewall-cmd", "--zone", "home", "--change-interface", "wlan0"],
    ]


def test_apply_runtime_zone_skips_the_call_entirely_when_already_correct():
    """Confirming a zone that's already applied (e.g. via the system
    default zone sync) must be a silent no-op -- never a prompt."""
    with patch("subprocess.run", return_value=MagicMock(returncode=0, stdout="home\n")) as run:
        assert applier.apply_runtime_zone("wlan0", "home", use_pkexec=True) is True

    run.assert_called_once_with(
        ["firewall-cmd", "--get-zone-of-interface", "wlan0"],
        capture_output=True,
        text=True,
    )


def test_apply_runtime_zone_falls_back_to_pkexec_when_use_pkexec_true():
    calls = []

    def fake_run(args, **kwargs):
        calls.append(args)
        if args[0] == "pkexec":
            return MagicMock(stdout="", stderr="")
        raise subprocess.CalledProcessError(1, args, stderr="denied")

    with patch("subprocess.run", side_effect=fake_run):
        assert applier.apply_runtime_zone("wlan0", "home", use_pkexec=True) is True

    assert calls == [
        ["firewall-cmd", "--get-zone-of-interface", "wlan0"],
        ["firewall-cmd", "--zone", "home", "--change-interface", "wlan0"],
        ["pkexec", "firewall-cmd", "--zone", "home", "--change-interface", "wlan0"],
    ]


def test_apply_runtime_zone_returns_false_when_pkexec_also_fails():
    err = subprocess.CalledProcessError(1, "x", stderr="denied")
    with patch("subprocess.run", side_effect=err):
        assert applier.apply_runtime_zone("wlan0", "home", use_pkexec=True) is False


def test_apply_runtime_zone_returns_false_when_pkexec_missing():
    def fake_run(args, **kwargs):
        if args[0] == "pkexec":
            raise FileNotFoundError("pkexec not found")
        raise subprocess.CalledProcessError(1, args, stderr="denied")

    with patch("subprocess.run", side_effect=fake_run):
        assert applier.apply_runtime_zone("wlan0", "home", use_pkexec=True) is False


def test_get_current_zone_returns_zone_when_known():
    with patch("subprocess.run", return_value=MagicMock(returncode=0, stdout="public\n")) as run:
        result = applier.get_current_zone("wlan0")
    run.assert_called_once_with(
        ["firewall-cmd", "--get-zone-of-interface", "wlan0"],
        capture_output=True,
        text=True,
    )
    assert result == "public"


def test_get_current_zone_returns_none_on_nonzero_exit():
    with patch("subprocess.run", return_value=MagicMock(returncode=1, stdout="")):
        assert applier.get_current_zone("wlan0") is None


def test_get_current_zone_returns_none_on_subprocess_error():
    with patch("subprocess.run", side_effect=FileNotFoundError("firewall-cmd not found")):
        assert applier.get_current_zone("wlan0") is None


def test_get_active_interface_returns_device_when_active():
    with patch("subprocess.run", return_value=MagicMock(returncode=0, stdout="wlan0\n")) as run:
        result = applier.get_active_interface("uuid-1")
    run.assert_called_once_with(
        ["nmcli", "-g", "GENERAL.DEVICES", "connection", "show", "uuid-1"],
        capture_output=True,
        text=True,
    )
    assert result == "wlan0"


def test_get_active_interface_returns_none_when_inactive():
    with patch("subprocess.run", return_value=MagicMock(returncode=0, stdout="\n")):
        assert applier.get_active_interface("uuid-1") is None


def test_get_active_interface_returns_none_on_unknown_uuid():
    with patch("subprocess.run", return_value=MagicMock(returncode=1, stdout="")):
        assert applier.get_active_interface("not-a-real-uuid") is None


def test_apply_zone_with_fallback_returns_requested_zone_on_success():
    with patch("subprocess.run", return_value=MagicMock(stdout="", stderr="")):
        result = applier.apply_zone_with_fallback("uuid-1", "wlan0", "home")
    assert result == "home"


def test_apply_zone_with_fallback_falls_back_when_zone_was_deleted():
    attempts = {"n": 0}

    def fake_run(args, **kwargs):
        attempts["n"] += 1
        if attempts["n"] == 1:
            raise subprocess.CalledProcessError(1, args, stderr="INVALID_ZONE: no such zone")
        # returncode=1 so get_current_zone's query (attempt 3) doesn't
        # short-circuit the actual change call that follows it.
        return MagicMock(stdout="", stderr="", returncode=1)

    with patch("subprocess.run", side_effect=fake_run) as run:
        result = applier.apply_zone_with_fallback(
            "uuid-1", "wlan0", "missing-zone", fallback="drop"
        )

    assert result == "drop"
    assert run.call_count == 4
    assert run.call_args_list[0].args[0] == [
        "nmcli", "connection", "modify", "uuid-1", "connection.zone", "missing-zone",
    ]
    assert run.call_args_list[1].args[0] == [
        "nmcli", "connection", "modify", "uuid-1", "connection.zone", "drop",
    ]
    assert run.call_args_list[2].args[0] == [
        "firewall-cmd", "--get-zone-of-interface", "wlan0",
    ]
    assert run.call_args_list[3].args[0] == [
        "firewall-cmd", "--zone", "drop", "--change-interface", "wlan0",
    ]
