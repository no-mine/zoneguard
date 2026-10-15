"""Queues firewall-cmd argument-lists for a single batched commit instead
of applying each edit immediately -- lets a burst of Profiles-tab edits
need at most one pkexec prompt instead of one per click.
"""
from __future__ import annotations

from collections.abc import Callable


class PendingChanges:
    def __init__(self, on_change: Callable[[], None]) -> None:
        self._commands: list[list[str]] = []
        self._on_change = on_change

    def add(self, *commands: list[str]) -> None:
        self._commands.extend(commands)
        self._on_change()

    def __len__(self) -> int:
        return len(self._commands)

    def take(self) -> list[list[str]]:
        """Return and clear the queue."""
        commands, self._commands = self._commands, []
        self._on_change()
        return commands
