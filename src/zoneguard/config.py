"""User settings, persisted under ~/.config/zoneguard/."""
from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict, dataclass, fields
from pathlib import Path

from .zone_manager import SAFE_FALLBACK_ZONE

log = logging.getLogger(__name__)

CONFIG_DIR = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "zoneguard"
SETTINGS_PATH = CONFIG_DIR / "settings.json"


def write_json_atomic(path: Path, data: object) -> None:
    """Write through a temp file and rename.

    The daemon and the GUI are separate processes sharing these files, so a
    reader must never observe a half-written one.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, indent=2))
    os.replace(tmp, path)


@dataclass
class Settings:
    default_zone: str = SAFE_FALLBACK_ZONE
    notify: bool = True

    @classmethod
    def load(cls, path: Path = SETTINGS_PATH) -> Settings:
        """Fall back to defaults if the file is missing or unreadable -- it is
        documented as hand-editable, so it can be malformed."""
        try:
            data = json.loads(path.read_text())
            known = {field.name for field in fields(cls)}
            return cls(**{k: v for k, v in data.items() if k in known})
        except FileNotFoundError:
            return cls()
        except (OSError, ValueError, AttributeError, TypeError):
            log.warning("Could not read %s; using default settings.", path)
            return cls()

    def save(self, path: Path = SETTINGS_PATH) -> None:
        write_json_atomic(path, asdict(self))
