"""
Unit tests for configuration loading and validation.
"""

import json
import tempfile
import unittest
from pathlib import Path

from twitch_marker_agent.core.config import (
    AppConfig,
    RetryConfig,
    ensure_config_exists,
    load_config,
    get_logging_level,
    is_placeholder_client_id,
    resolve_client_id_seed,
    write_bootstrap_template,
    write_broadcaster_id_if_empty,
)


class TestRetryConfig(unittest.TestCase):
    """Tests for RetryConfig dataclass validation."""

    def test_valid_retry_config(self) -> None:
        """Test valid retry configuration."""
        config = RetryConfig(
            max_attempts=5,
            base_delay_seconds=1.0,
            max_delay_seconds=60.0,
        )
        self.assertEqual(config.max_attempts, 5)
        self.assertEqual(config.base_delay_seconds, 1.0)
        self.assertEqual(config.max_delay_seconds, 60.0)

    def test_invalid_max_attempts(self) -> None:
        """Test that max_attempts < 1 raises ValueError."""
        with self.assertRaises(ValueError) as ctx:
            RetryConfig(
                max_attempts=0,
                base_delay_seconds=1.0,
                max_delay_seconds=60.0,
            )
        self.assertIn("max_attempts", str(ctx.exception))

    def test_invalid_base_delay(self) -> None:
        """Test that base_delay_seconds <= 0 raises ValueError."""
        with self.assertRaises(ValueError) as ctx:
            RetryConfig(
                max_attempts=5,
                base_delay_seconds=0,
                max_delay_seconds=60.0,
            )
        self.assertIn("base_delay_seconds", str(ctx.exception))

    def test_invalid_max_delay(self) -> None:
        """Test that max_delay < base_delay raises ValueError."""
        with self.assertRaises(ValueError) as ctx:
            RetryConfig(
                max_attempts=5,
                base_delay_seconds=10.0,
                max_delay_seconds=5.0,
            )
        self.assertIn("max_delay_seconds", str(ctx.exception))


class TestLoadConfig(unittest.TestCase):
    """Tests for load_config function."""

    def setUp(self) -> None:
        """Create a temporary directory for test config files."""
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self) -> None:
        """Clean up temporary files."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _write_config(self, data: dict) -> Path:
        """Helper to write config file."""
        config_path = Path(self.temp_dir) / "config.json"
        with config_path.open("w", encoding="utf-8") as f:
            json.dump(data, f)
        return config_path

    def test_load_valid_config(self) -> None:
        """Test loading a complete valid configuration."""
        config_data = {
            "client_id": "test_client_id",
            "client_secret": "test_secret",
            "redirect_uri": "http://localhost:3000/callback",
            "broadcaster_id": "123456",
            "output_dir": "./exports",
            "export_formats": ["csv", "edl"],
            "resolve_offset_enabled": True,
            "resolve_offset_timecode": "01:00:00:00",
            "timecode_fps": 24,
            "log_level": "INFO",
            "state_db_path": "./data/state.db",
            "retry": {
                "max_attempts": 5,
                "base_delay_seconds": 1.0,
                "max_delay_seconds": 60.0,
            },
        }
        config_path = self._write_config(config_data)
        config = load_config(config_path)

        self.assertEqual(config.client_id, "test_client_id")
        self.assertEqual(config.broadcaster_id, "123456")
        self.assertEqual(config.export_formats, ("csv", "edl"))
        self.assertEqual(config.timecode_fps, 24)
        self.assertTrue(config.resolve_offset_enabled)
        self.assertIsInstance(config.output_dir, Path)
        self.assertIsInstance(config.retry, RetryConfig)

    def test_missing_required_field(self) -> None:
        """Test that missing required fields raise KeyError."""
        config_data = {
            "client_secret": "test_secret",
            # missing client_id and broadcaster_id
        }
        config_path = self._write_config(config_data)

        with self.assertRaises(KeyError):
            load_config(config_path)

    def test_invalid_export_format(self) -> None:
        """Test that invalid export formats raise ValueError."""
        config_data = {
            "client_id": "test",
            "broadcaster_id": "123",
            "export_formats": ["csv", "invalid_format"],
        }
        config_path = self._write_config(config_data)

        with self.assertRaises(ValueError) as ctx:
            load_config(config_path)
        self.assertIn("invalid_format", str(ctx.exception))

    def test_invalid_log_level(self) -> None:
        """Test that invalid log level raises ValueError."""
        config_data = {
            "client_id": "test",
            "broadcaster_id": "123",
            "log_level": "INVALID",
        }
        config_path = self._write_config(config_data)

        with self.assertRaises(ValueError) as ctx:
            load_config(config_path)
        self.assertIn("log_level", str(ctx.exception))

    def test_config_file_not_found(self) -> None:
        """Test that missing config file raises FileNotFoundError."""
        with self.assertRaises(FileNotFoundError):
            load_config(Path(self.temp_dir) / "nonexistent.json")

    def test_default_values(self) -> None:
        """Test that optional fields get default values."""
        config_data = {
            "client_id": "test",
            "broadcaster_id": "123",
        }
        config_path = self._write_config(config_data)
        config = load_config(config_path)

        # Check defaults
        self.assertEqual(config.redirect_uri, "http://localhost:3000/callback")
        self.assertEqual(config.export_formats, ("csv",))
        self.assertFalse(config.resolve_offset_enabled)
        self.assertEqual(config.log_level, "INFO")

    def test_relative_paths_anchor_to_base_dir(self) -> None:
        """Relative output/state paths should anchor to provided base_dir."""
        config_data = {
            "client_id": "test",
            "broadcaster_id": "123",
            "output_dir": "./exports",
            "state_db_path": "./data/state.db",
        }
        config_path = self._write_config(config_data)
        base_dir = Path(self.temp_dir) / "portable_root"
        base_dir.mkdir(parents=True, exist_ok=True)

        config = load_config(config_path, base_dir=base_dir)

        self.assertEqual(config.output_dir, base_dir / "exports")
        self.assertEqual(config.state_db_path, base_dir / "data" / "state.db")

    def test_allow_empty_broadcaster_id(self) -> None:
        """Should allow empty broadcaster_id when explicitly requested."""
        config_data = {
            "client_id": "test",
            "broadcaster_id": "",
        }
        config_path = self._write_config(config_data)

        config = load_config(config_path, allow_empty_broadcaster_id=True)

        self.assertEqual(config.broadcaster_id, "")

    def test_empty_broadcaster_id_rejected_by_default(self) -> None:
        """Should reject empty broadcaster_id unless explicitly allowed."""
        config_data = {
            "client_id": "test",
            "broadcaster_id": "",
        }
        config_path = self._write_config(config_data)

        with self.assertRaises(ValueError):
            load_config(config_path)

    def test_write_broadcaster_id_if_empty_writes_once(self) -> None:
        """Should write broadcaster_id only when existing value is empty."""
        config_data = {
            "client_id": "test",
            "broadcaster_id": "",
        }
        config_path = self._write_config(config_data)

        wrote = write_broadcaster_id_if_empty(config_path, "12345")
        self.assertTrue(wrote)

        with config_path.open("r", encoding="utf-8") as f:
            updated = json.load(f)
        self.assertEqual(updated["broadcaster_id"], "12345")

        wrote_again = write_broadcaster_id_if_empty(config_path, "99999")
        self.assertFalse(wrote_again)

    def test_ensure_config_exists_creates_missing_file(self) -> None:
        """Should create config from bootstrap template when missing."""
        config_path = Path(self.temp_dir) / "missing_config.json"

        created = ensure_config_exists(config_path)

        self.assertTrue(created)
        self.assertTrue(config_path.exists())
        with config_path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        self.assertIn("client_id", data)
        self.assertTrue(str(data["client_id"]).strip())

    def test_ensure_config_exists_does_not_overwrite_existing(self) -> None:
        """Should not overwrite existing config files."""
        config_path = self._write_config(
            {
                "client_id": "existing_client",
                "broadcaster_id": "123",
            }
        )

        created = ensure_config_exists(config_path, client_id_seed="seeded_client")

        self.assertFalse(created)
        loaded = load_config(config_path)
        self.assertEqual(loaded.client_id, "existing_client")

    def test_ensure_config_exists_uses_seeded_client_id(self) -> None:
        """Should write provided client_id seed when creating config."""
        config_path = Path(self.temp_dir) / "seeded_config.json"

        ensure_config_exists(config_path, client_id_seed="seed_client_id")

        with config_path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        self.assertEqual(data["client_id"], "seed_client_id")

    def test_invalid_existing_json_still_errors(self) -> None:
        """Invalid existing JSON should still fail load_config."""
        config_path = Path(self.temp_dir) / "broken_config.json"
        config_path.write_text("{invalid json", encoding="utf-8")

        created = ensure_config_exists(config_path)
        self.assertFalse(created)

        with self.assertRaises(json.JSONDecodeError):
            load_config(config_path)


class TestBootstrapHelpers(unittest.TestCase):
    """Tests for bootstrap helper functions."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self) -> None:
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_is_placeholder_client_id_detects_known_values(self) -> None:
        """Should identify blank and known placeholder client_id values."""
        self.assertTrue(is_placeholder_client_id(""))
        self.assertTrue(is_placeholder_client_id("   "))
        self.assertTrue(is_placeholder_client_id("YOUR_TWITCH_CLIENT_ID"))
        self.assertTrue(is_placeholder_client_id("your_client_id_here"))
        self.assertTrue(is_placeholder_client_id("your_client_id"))
        self.assertTrue(is_placeholder_client_id("your_client_id_here..."))
        self.assertFalse(is_placeholder_client_id("real_client_id"))

    def test_write_bootstrap_template_uses_non_empty_placeholder(self) -> None:
        """Generated bootstrap template should have non-empty placeholder client_id."""
        output_path = Path(self.temp_dir) / "config.bootstrap.json"

        write_bootstrap_template(output_path)

        with output_path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        client_id = str(data.get("client_id", ""))
        self.assertTrue(client_id.strip())
        self.assertTrue(is_placeholder_client_id(client_id))

    def test_write_bootstrap_template_uses_seeded_client_id(self) -> None:
        """Generated bootstrap template should honor client_id seed."""
        output_path = Path(self.temp_dir) / "config.bootstrap.json"

        write_bootstrap_template(output_path, client_id_seed="seeded123")

        with output_path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        self.assertEqual(data["client_id"], "seeded123")

    def test_resolve_client_id_seed_prefers_explicit_non_placeholder(self) -> None:
        """Explicit non-placeholder seed should take precedence over local config."""
        local_config_path = Path(self.temp_dir) / "local.config.json"
        local_config_path.write_text(
            json.dumps({"client_id": "local_client"}),
            encoding="utf-8",
        )

        resolved = resolve_client_id_seed(
            "explicit_client",
            local_config_path=local_config_path,
        )

        self.assertEqual(resolved, "explicit_client")

    def test_resolve_client_id_seed_ignores_placeholder_explicit_and_uses_local(self) -> None:
        """Placeholder explicit seed should fall back to valid local client_id."""
        local_config_path = Path(self.temp_dir) / "local.config.json"
        local_config_path.write_text(
            json.dumps({"client_id": "local_client"}),
            encoding="utf-8",
        )

        resolved = resolve_client_id_seed(
            "YOUR_TWITCH_CLIENT_ID",
            local_config_path=local_config_path,
        )

        self.assertEqual(resolved, "local_client")

    def test_resolve_client_id_seed_missing_local_returns_none(self) -> None:
        """Missing local config should return None when explicit seed is unusable."""
        local_config_path = Path(self.temp_dir) / "missing-local.config.json"

        resolved = resolve_client_id_seed(
            "YOUR_TWITCH_CLIENT_ID",
            local_config_path=local_config_path,
        )

        self.assertIsNone(resolved)

    def test_resolve_client_id_seed_malformed_local_returns_none(self) -> None:
        """Malformed local config should return None without raising."""
        local_config_path = Path(self.temp_dir) / "local.config.json"
        local_config_path.write_text("{not json", encoding="utf-8")

        resolved = resolve_client_id_seed(
            None,
            local_config_path=local_config_path,
        )

        self.assertIsNone(resolved)

    def test_resolve_client_id_seed_missing_client_id_returns_none(self) -> None:
        """Local config without client_id should return None."""
        local_config_path = Path(self.temp_dir) / "local.config.json"
        local_config_path.write_text(
            json.dumps({"redirect_uri": "http://localhost:3000/callback"}),
            encoding="utf-8",
        )

        resolved = resolve_client_id_seed(
            None,
            local_config_path=local_config_path,
        )

        self.assertIsNone(resolved)


class TestGetLoggingLevel(unittest.TestCase):
    """Tests for get_logging_level function."""

    def test_all_log_levels(self) -> None:
        """Test all valid log levels are converted correctly."""
        import logging

        # Create minimal config for each level
        for level_name, expected_level in [
            ("DEBUG", logging.DEBUG),
            ("INFO", logging.INFO),
            ("WARNING", logging.WARNING),
            ("ERROR", logging.ERROR),
            ("CRITICAL", logging.CRITICAL),
        ]:
            config = AppConfig(
                client_id="test",
                client_secret="",
                redirect_uri="http://localhost:3000/callback",
                broadcaster_id="123",
                output_dir=Path("./exports"),
                export_formats=("csv",),
                resolve_offset_enabled=False,
                resolve_offset_timecode="01:00:00:00",
                timecode_fps=24,
                log_level=level_name,
                state_db_path=Path("./state.db"),
                retry=RetryConfig(5, 1.0, 60.0),
            )
            self.assertEqual(get_logging_level(config), expected_level)


if __name__ == "__main__":
    unittest.main()
