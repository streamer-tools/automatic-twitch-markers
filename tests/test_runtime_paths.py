"""
Tests for runtime path resolution helpers.
"""

from __future__ import annotations

import unittest
from pathlib import Path

from twitch_marker_agent.core.runtime_paths import (
    build_runtime_paths,
    resolve_runtime_base_dir,
)


class TestResolveRuntimeBaseDir(unittest.TestCase):
    """Tests for resolve_runtime_base_dir()."""

    def test_frozen_uses_executable_parent(self) -> None:
        """Frozen mode should use executable parent directory."""
        base = resolve_runtime_base_dir(
            frozen=True,
            executable=Path("C:/Apps/TwitchMarkerAgent/TwitchMarkerAgent.exe"),
        )
        self.assertEqual(base, Path("C:/Apps/TwitchMarkerAgent"))

    def test_dev_uses_cwd(self) -> None:
        """Dev mode should use current working directory."""
        cwd = Path("C:/Dev/automatic-twitch-markers")
        base = resolve_runtime_base_dir(frozen=False, cwd=cwd)
        self.assertEqual(base, cwd)


class TestBuildRuntimePaths(unittest.TestCase):
    """Tests for build_runtime_paths()."""

    def test_builds_config_logs_and_state_paths(self) -> None:
        """Should derive portable paths under base directory."""
        cwd = Path("C:/Portable/TwitchMarkerAgent")
        paths = build_runtime_paths(frozen=False, cwd=cwd)

        self.assertEqual(paths.base_dir, cwd)
        self.assertEqual(paths.config_path, cwd / "config.json")
        self.assertEqual(paths.logs_dir, cwd / "logs")
        self.assertEqual(paths.state_db_path, cwd / "data" / "state.db")


if __name__ == "__main__":
    unittest.main()

