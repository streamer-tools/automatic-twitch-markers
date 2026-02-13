"""
Tests for first-launch config bootstrap wiring in CLI and tray entrypoints.
"""

from __future__ import annotations

import argparse
import io
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from twitch_marker_agent.core.config import AppConfig, RetryConfig


def _build_test_config(client_id: str = "real_client_id") -> AppConfig:
    """Create a minimal valid AppConfig for bootstrap wiring tests."""
    return AppConfig(
        client_id=client_id,
        client_secret="",
        redirect_uri="http://localhost:3000/callback",
        broadcaster_id="",
        output_dir=Path("./exports"),
        export_formats=("csv",),
        resolve_offset_enabled=False,
        resolve_offset_timecode="01:00:00:00",
        timecode_fps=60,
        log_level="INFO",
        state_db_path=Path("./data/state.db"),
        retry=RetryConfig(5, 1.0, 60.0),
    )


class TestCliBootstrap(unittest.TestCase):
    """Tests for cmd_auth_login bootstrap behavior."""

    @patch("twitch_marker_agent.core.twitch_oauth.TwitchOAuth")
    @patch("twitch_marker_agent.core.state_store.StateStore")
    @patch("twitch_marker_agent.core.logging_setup.setup_logging")
    @patch("twitch_marker_agent.core.config.load_config")
    @patch("twitch_marker_agent.core.config.ensure_config_exists")
    @patch("twitch_marker_agent.core.runtime_paths.build_runtime_paths")
    def test_cmd_auth_login_calls_ensure_before_load(
        self,
        mock_build_runtime_paths: MagicMock,
        mock_ensure_config_exists: MagicMock,
        mock_load_config: MagicMock,
        mock_setup_logging: MagicMock,
        mock_state_store_cls: MagicMock,
        mock_oauth_cls: MagicMock,
    ) -> None:
        """CLI auth-login should ensure config exists before loading."""
        from twitch_marker_agent import cli

        call_order: list[str] = []
        mock_build_runtime_paths.return_value = SimpleNamespace(
            base_dir=Path("C:/runtime"),
            logs_dir=Path("C:/runtime/logs"),
            config_path=Path("C:/runtime/config.json"),
        )
        mock_ensure_config_exists.side_effect = lambda *args, **kwargs: call_order.append("ensure")
        mock_load_config.side_effect = lambda *args, **kwargs: (
            call_order.append("load") or _build_test_config()
        )
        mock_setup_logging.return_value = MagicMock()
        mock_state_store_cls.return_value = MagicMock()
        mock_oauth_instance = MagicMock()
        mock_oauth_cls.return_value = mock_oauth_instance

        args = argparse.Namespace(
            config=Path("C:/runtime/config.json"),
            verbose=False,
            timeout=5,
        )
        with redirect_stdout(io.StringIO()):
            exit_code = cli.cmd_auth_login(args)

        self.assertEqual(exit_code, 0)
        self.assertEqual(call_order[:2], ["ensure", "load"])
        mock_oauth_instance.interactive_login.assert_called_once_with(timeout_seconds=5)

    @patch("twitch_marker_agent.core.config.load_config")
    @patch("twitch_marker_agent.core.config.ensure_config_exists")
    @patch("twitch_marker_agent.core.runtime_paths.build_runtime_paths")
    @patch("twitch_marker_agent.core.state_store.StateStore")
    def test_cmd_auth_login_blocks_placeholder_client_id(
        self,
        mock_state_store_cls: MagicMock,
        mock_build_runtime_paths: MagicMock,
        mock_ensure_config_exists: MagicMock,
        mock_load_config: MagicMock,
    ) -> None:
        """CLI auth-login should fail early when client_id is still placeholder."""
        from twitch_marker_agent import cli

        mock_build_runtime_paths.return_value = SimpleNamespace(
            base_dir=Path("C:/runtime"),
            logs_dir=Path("C:/runtime/logs"),
            config_path=Path("C:/runtime/config.json"),
        )
        mock_load_config.return_value = _build_test_config("YOUR_TWITCH_CLIENT_ID")

        args = argparse.Namespace(
            config=Path("C:/runtime/config.json"),
            verbose=False,
            timeout=5,
        )

        stderr = io.StringIO()
        with redirect_stderr(stderr):
            exit_code = cli.cmd_auth_login(args)

        self.assertEqual(exit_code, 1)
        error_text = stderr.getvalue()
        self.assertIn("missing the Twitch Client ID", error_text)
        self.assertIn("official release", error_text)
        self.assertIn("C:/runtime/config.json", error_text.replace("\\", "/"))
        mock_state_store_cls.assert_not_called()
        mock_ensure_config_exists.assert_called_once()


class TestAppBootstrap(unittest.TestCase):
    """Tests for tray app bootstrap behavior."""

    @patch("twitch_marker_agent.app.run_tray_app")
    @patch("twitch_marker_agent.core.twitch_oauth.TwitchOAuth")
    @patch("requests.Session")
    @patch("twitch_marker_agent.core.state_store.StateStore")
    @patch("twitch_marker_agent.core.logging_setup.setup_logging")
    @patch("twitch_marker_agent.core.config.load_config")
    @patch("twitch_marker_agent.core.config.ensure_config_exists")
    @patch("twitch_marker_agent.core.runtime_paths.build_runtime_paths")
    def test_app_main_calls_ensure_before_load(
        self,
        mock_build_runtime_paths: MagicMock,
        mock_ensure_config_exists: MagicMock,
        mock_load_config: MagicMock,
        mock_setup_logging: MagicMock,
        mock_state_store_cls: MagicMock,
        mock_session_cls: MagicMock,
        mock_oauth_cls: MagicMock,
        mock_run_tray_app: MagicMock,
    ) -> None:
        """app.main should bootstrap config before loading it."""
        from twitch_marker_agent import app

        call_order: list[str] = []
        runtime_paths = SimpleNamespace(
            base_dir=Path("C:/runtime"),
            config_path=Path("C:/runtime/config.json"),
            logs_dir=Path("C:/runtime/logs"),
            state_db_path=Path("C:/runtime/data/state.db"),
        )
        mock_build_runtime_paths.return_value = runtime_paths
        mock_ensure_config_exists.side_effect = lambda *args, **kwargs: call_order.append("ensure")
        mock_load_config.side_effect = lambda *args, **kwargs: (
            call_order.append("load") or _build_test_config()
        )
        mock_setup_logging.return_value = MagicMock()
        mock_state_store_instance = MagicMock()
        mock_state_store_cls.return_value = mock_state_store_instance
        mock_session_instance = MagicMock()
        mock_session_cls.return_value = mock_session_instance
        mock_oauth_cls.return_value = MagicMock()

        app.main()

        self.assertEqual(call_order[:2], ["ensure", "load"])
        mock_ensure_config_exists.assert_called_once_with(
            runtime_paths.config_path,
            client_id_seed=None,
        )
        mock_run_tray_app.assert_called_once()
        mock_state_store_instance.close.assert_called_once()
        mock_session_instance.close.assert_called_once()


if __name__ == "__main__":
    unittest.main()
