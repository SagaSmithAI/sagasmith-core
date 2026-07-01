"""Runtime paths for the new SagaSmith TTRPG base."""

from __future__ import annotations

import os
from pathlib import Path


def data_root() -> Path:
    """Return the canonical SagaSmith data root."""
    configured = os.environ.get("SAGASMITH_DATA_DIR")
    return Path(configured).expanduser() if configured else Path.home() / ".sagasmith"


def system_data_dir(system: str) -> Path:
    target = data_root() / system
    target.mkdir(parents=True, exist_ok=True)
    return target
