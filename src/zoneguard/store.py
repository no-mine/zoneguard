"""Persistent map of network fingerprint -> assigned firewalld zone."""
from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from .config import CONFIG_DIR, write_json_atomic

log = logging.getLogger(__name__)

NETWORKS_PATH = CONFIG_DIR / "networks.json"


@dataclass
class NetworkEntry:
    label: str
    zone: str
    confirmed: bool
    last_seen: str
    uuid: str = ""  # NM connection UUID; "" for entries from older versions


class NetworkStore:
    """__init__ only reads once -- call reload() to pick up writes made by
    another process (the daemon and the GUI each hold their own instance).
    """

    def __init__(self, path: Path = NETWORKS_PATH) -> None:
        self._path = path
        self._entries: dict[str, NetworkEntry] = {}
        self._load()

    def _load(self) -> None:
        try:
            raw = json.loads(self._path.read_text())
            entries = {fp: NetworkEntry(**data) for fp, data in raw.items()}
        except FileNotFoundError:
            return
        except (OSError, ValueError, AttributeError, TypeError):
            # Documented as hand-editable, so treat a malformed file as empty
            # rather than letting it stop the daemon.
            log.warning("Could not read %s; no networks remembered.", self._path)
            return
        self._entries = entries

    def reload(self) -> None:
        """Re-read from disk, picking up writes from another process."""
        self._entries = {}
        self._load()

    def save(self) -> None:
        write_json_atomic(self._path, {fp: asdict(e) for fp, e in self._entries.items()})

    def get(self, fingerprint: str) -> NetworkEntry | None:
        return self._entries.get(fingerprint)

    def upsert(
        self,
        fingerprint: str,
        *,
        label: str,
        zone: str,
        confirmed: bool,
        uuid: str | None = None,
    ) -> None:
        """Replace the entry for `fingerprint`. uuid=None keeps whatever was stored."""
        if uuid is None:
            existing = self._entries.get(fingerprint)
            uuid = existing.uuid if existing is not None else ""
        self._entries[fingerprint] = NetworkEntry(
            label=label,
            zone=zone,
            confirmed=confirmed,
            last_seen=datetime.now(timezone.utc).isoformat(),
            uuid=uuid,
        )
        self.save()

    def touch_last_seen(self, fingerprint: str) -> None:
        entry = self._entries.get(fingerprint)
        if entry is not None:
            entry.last_seen = datetime.now(timezone.utc).isoformat()
            self.save()

    def all(self) -> dict[str, NetworkEntry]:
        return dict(self._entries)

    def remove(self, fingerprint: str) -> None:
        if fingerprint in self._entries:
            del self._entries[fingerprint]
            self.save()
