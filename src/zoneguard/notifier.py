from __future__ import annotations

import logging
import shutil
import subprocess

log = logging.getLogger(__name__)


def notify(title: str, body: str) -> None:
    if shutil.which("notify-send") is None:
        log.info("%s: %s", title, body)
        return
    subprocess.run(
        ["notify-send", "--app-name=ZoneGuard", "--icon=zoneguard", title, body],
        check=False,
    )
