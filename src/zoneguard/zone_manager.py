"""The firewalld interface: zone queries, plus apply_batch() to commit a
set of edits as a single authorized operation.

Design rationale for the batching and pkexec behaviour lives in
docs/DOCUMENTATION.md.
"""
from __future__ import annotations

import re
import shlex
import subprocess

ZoneInfo = dict[str, list[str]]

# firewalld rejects zone names longer than this, or holding anything outside
# this character set.
MAX_ZONE_NAME_LENGTH = 17
_VALID_ZONE_NAME = re.compile(r"\A[A-Za-z0-9_-]+\Z")

# Built-in and undeletable, so it is always a valid target when a configured
# or remembered zone has disappeared.
SAFE_FALLBACK_ZONE = "drop"

# Used when firewalld can't be reached, so the GUI still renders a usable
# zone list instead of an empty dropdown.
FALLBACK_ZONES = (
    "drop",
    "block",
    "public",
    "home",
    "work",
    "internal",
    "trusted",
    "dmz",
    "external",
)


# Raised when firewall-cmd is missing or exits nonzero -- i.e. firewalld is
# unreachable. Callers that can degrade gracefully catch this.
FIREWALLD_ERRORS = (OSError, subprocess.CalledProcessError)


def zone_name_error(name: str) -> str | None:
    """Why firewalld would reject `name`, or None if it is usable.

    Checked before queuing, because an invalid name otherwise only surfaces
    at Apply -- where it fails the whole batch rather than just itself.
    """
    if not name:
        return "Enter a name for the new profile."
    if len(name) > MAX_ZONE_NAME_LENGTH:
        return f"Profile names can be at most {MAX_ZONE_NAME_LENGTH} characters."
    if not _VALID_ZONE_NAME.match(name):
        return "Profile names can only contain letters, digits, '-' and '_'."
    return None


def _run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["firewall-cmd", *args],
        capture_output=True,
        text=True,
        check=True,
    )


def get_available_zones() -> list[str]:
    return _run("--get-zones").stdout.split()


def available_zones_or_fallback() -> list[str]:
    """Zone list for the GUI, degrading to FALLBACK_ZONES so a dropdown is
    never empty just because firewalld is down."""
    try:
        return get_available_zones()
    except FIREWALLD_ERRORS:
        return list(FALLBACK_ZONES)


def get_default_zone() -> str:
    return _run("--get-default-zone").stdout.strip()


def get_all_services() -> list[str]:
    return _run("--get-services").stdout.split()


def list_all_zones() -> dict[str, ZoneInfo]:
    """Services and ports for every zone in one firewall-cmd call instead of
    2*N -- firewall-cmd has a real per-invocation startup cost and the
    Profiles tab needs every zone at once."""
    zones: dict[str, ZoneInfo] = {}
    current: str = ""
    for line in _run("--list-all-zones").stdout.splitlines():
        if not line.strip():
            continue
        if not line[0].isspace():
            current = line.split()[0]
            zones[current] = {"services": [], "ports": []}
            continue
        if not current:
            continue
        stripped = line.strip()
        for field in ("services", "ports"):
            prefix = f"{field}:"
            if stripped.startswith(prefix):
                zones[current][field] = stripped[len(prefix):].split()
                break
    return zones


def apply_batch(commands: list[list[str]]) -> None:
    """Run a batch of firewall-cmd argument lists as a single operation.

    Each command is tried unprivileged first; on the first failure, every
    remaining command is re-run as one pkexec'd shell script, so a burst of
    edits costs at most one authorization prompt. Arguments are shell-quoted
    individually because some are free text (a zone name, a port spec).
    """
    for index, args in enumerate(commands):
        try:
            _run(*args)
        except subprocess.CalledProcessError:
            script = " && ".join(
                "firewall-cmd " + " ".join(shlex.quote(arg) for arg in command)
                for command in commands[index:]
            )
            subprocess.run(
                ["pkexec", "sh", "-c", script],
                capture_output=True,
                text=True,
                check=True,
            )
            return
