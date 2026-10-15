from __future__ import annotations

import subprocess

UNIT = "zoneguard-daemon.service"


def _run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["systemctl", "--user", *args],
        capture_output=True,
        text=True,
    )


def is_active() -> bool:
    return _run("is-active", UNIT).stdout.strip() == "active"


def is_enabled() -> bool:
    return _run("is-enabled", UNIT).stdout.strip() == "enabled"


def start() -> subprocess.CompletedProcess:
    return _run("start", UNIT)


def stop() -> subprocess.CompletedProcess:
    return _run("stop", UNIT)


def restart() -> subprocess.CompletedProcess:
    return _run("restart", UNIT)


def enable(now: bool = True) -> subprocess.CompletedProcess:
    args = ["enable"]
    if now:
        args.append("--now")
    args.append(UNIT)
    return _run(*args)


def disable(now: bool = True) -> subprocess.CompletedProcess:
    args = ["disable"]
    if now:
        args.append("--now")
    args.append(UNIT)
    return _run(*args)
