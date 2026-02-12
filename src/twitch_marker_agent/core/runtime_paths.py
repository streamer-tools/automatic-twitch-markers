"""
Runtime path resolution for portable deployments.

This module provides a small helper for deriving runtime paths from:
- Frozen app: directory containing the running executable.
- Dev mode: current working directory.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class RuntimePaths:
    """Resolved runtime paths for config, logs, and state."""

    base_dir: Path
    config_path: Path
    logs_dir: Path
    state_db_path: Path


def resolve_runtime_base_dir(
    *,
    frozen: bool | None = None,
    executable: str | Path | None = None,
    cwd: Path | None = None,
) -> Path:
    """
    Resolve runtime base directory.

    Args:
        frozen: Optional override for frozen mode detection.
        executable: Optional executable path override (for tests).
        cwd: Optional current working directory override (for tests).

    Returns:
        Base directory path.
    """
    is_frozen = getattr(sys, "frozen", False) if frozen is None else frozen
    if is_frozen:
        exe = Path(executable) if executable is not None else Path(sys.executable)
        return exe.parent

    return cwd if cwd is not None else Path.cwd()


def build_runtime_paths(
    *,
    config_filename: str = "config.json",
    frozen: bool | None = None,
    executable: str | Path | None = None,
    cwd: Path | None = None,
) -> RuntimePaths:
    """
    Build runtime paths anchored to runtime base directory.

    Args:
        config_filename: Config filename under base_dir.
        frozen: Optional override for frozen mode detection.
        executable: Optional executable path override (for tests).
        cwd: Optional current working directory override (for tests).

    Returns:
        RuntimePaths with base/config/log/state locations.
    """
    base_dir = resolve_runtime_base_dir(
        frozen=frozen,
        executable=executable,
        cwd=cwd,
    )
    return RuntimePaths(
        base_dir=base_dir,
        config_path=base_dir / config_filename,
        logs_dir=base_dir / "logs",
        state_db_path=base_dir / "data" / "state.db",
    )

