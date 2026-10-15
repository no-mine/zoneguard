from unittest.mock import MagicMock, patch

from zoneguard import systemd_control


def test_is_active_true_when_output_is_active():
    fake = MagicMock(stdout="active\n")
    with patch("subprocess.run", return_value=fake):
        assert systemd_control.is_active() is True


def test_is_active_false_when_output_is_inactive():
    fake = MagicMock(stdout="inactive\n")
    with patch("subprocess.run", return_value=fake):
        assert systemd_control.is_active() is False


def test_is_enabled_true_when_output_is_enabled():
    fake = MagicMock(stdout="enabled\n")
    with patch("subprocess.run", return_value=fake):
        assert systemd_control.is_enabled() is True


def test_start_invokes_systemctl_user_start():
    with patch("subprocess.run") as run:
        systemd_control.start()
    run.assert_called_once_with(
        ["systemctl", "--user", "start", systemd_control.UNIT],
        capture_output=True,
        text=True,
    )


def test_stop_invokes_systemctl_user_stop():
    with patch("subprocess.run") as run:
        systemd_control.stop()
    run.assert_called_once_with(
        ["systemctl", "--user", "stop", systemd_control.UNIT],
        capture_output=True,
        text=True,
    )


def test_enable_defaults_to_now():
    with patch("subprocess.run") as run:
        systemd_control.enable()
    run.assert_called_once_with(
        ["systemctl", "--user", "enable", "--now", systemd_control.UNIT],
        capture_output=True,
        text=True,
    )


def test_enable_without_now():
    with patch("subprocess.run") as run:
        systemd_control.enable(now=False)
    run.assert_called_once_with(
        ["systemctl", "--user", "enable", systemd_control.UNIT],
        capture_output=True,
        text=True,
    )


def test_disable_defaults_to_now():
    with patch("subprocess.run") as run:
        systemd_control.disable()
    run.assert_called_once_with(
        ["systemctl", "--user", "disable", "--now", systemd_control.UNIT],
        capture_output=True,
        text=True,
    )
