"""
Unit tests for Windows startup integration.

All tests use unittest.mock to patch winreg operations.
NO REAL REGISTRY ACCESS IS PERFORMED.
NO SYSTEM RESTART/SHUTDOWN OPERATIONS ARE CALLED.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch


# =============================================================================
# StartupError Tests
# =============================================================================


class TestStartupError(unittest.TestCase):
    """Test StartupError exception."""

    def test_startup_error_is_exception(self) -> None:
        """StartupError should be a valid exception."""
        from twitch_marker_agent.platform.windows_startup import StartupError

        error = StartupError("test error")
        self.assertIsInstance(error, Exception)
        self.assertEqual(str(error), "test error")


# =============================================================================
# is_startup_enabled Tests
# =============================================================================


class TestIsStartupEnabled(unittest.TestCase):
    """Test is_startup_enabled function."""

    @patch.object(sys, "platform", "linux")
    def test_returns_false_on_non_windows(self) -> None:
        """Should return False on non-Windows platforms."""
        from twitch_marker_agent.platform import windows_startup

        # Reload module to pick up mock
        import importlib

        importlib.reload(windows_startup)

        result = windows_startup.is_startup_enabled()
        self.assertFalse(result)

    @patch.object(sys, "platform", "win32")
    def test_returns_true_when_key_exists(self) -> None:
        """Should return True when registry value exists."""
        mock_winreg = MagicMock()
        mock_key = MagicMock()
        mock_winreg.OpenKey.return_value.__enter__ = MagicMock(return_value=mock_key)
        mock_winreg.OpenKey.return_value.__exit__ = MagicMock(return_value=None)
        mock_winreg.QueryValueEx.return_value = ("command", 1)

        with patch.dict("sys.modules", {"winreg": mock_winreg}):
            from twitch_marker_agent.platform import windows_startup

            import importlib

            importlib.reload(windows_startup)

            result = windows_startup.is_startup_enabled()
            self.assertTrue(result)

    @patch.object(sys, "platform", "win32")
    def test_returns_false_when_key_missing(self) -> None:
        """Should return False when registry value doesn't exist."""
        mock_winreg = MagicMock()
        mock_winreg.OpenKey.return_value.__enter__ = MagicMock()
        mock_winreg.OpenKey.return_value.__exit__ = MagicMock(return_value=None)
        mock_winreg.QueryValueEx.side_effect = FileNotFoundError("Value not found")

        with patch.dict("sys.modules", {"winreg": mock_winreg}):
            from twitch_marker_agent.platform import windows_startup

            import importlib

            importlib.reload(windows_startup)

            result = windows_startup.is_startup_enabled()
            self.assertFalse(result)


# =============================================================================
# enable_startup Tests
# =============================================================================


class TestEnableStartup(unittest.TestCase):
    """Test enable_startup function."""

    @patch.object(sys, "platform", "linux")
    def test_raises_on_non_windows(self) -> None:
        """Should raise StartupError on non-Windows platforms."""
        from twitch_marker_agent.platform import windows_startup

        import importlib

        importlib.reload(windows_startup)

        with self.assertRaises(windows_startup.StartupError) as ctx:
            windows_startup.enable_startup()

        self.assertIn("not available", str(ctx.exception))

    @patch.object(sys, "platform", "win32")
    def test_creates_registry_entry(self) -> None:
        """Should create registry entry with correct value."""
        mock_winreg = MagicMock()
        mock_key = MagicMock()
        mock_winreg.CreateKeyEx.return_value.__enter__ = MagicMock(return_value=mock_key)
        mock_winreg.CreateKeyEx.return_value.__exit__ = MagicMock(return_value=None)
        mock_winreg.REG_SZ = 1
        mock_winreg.KEY_SET_VALUE = 2
        mock_winreg.HKEY_CURRENT_USER = "HKCU"

        with patch.dict("sys.modules", {"winreg": mock_winreg}):
            from twitch_marker_agent.platform import windows_startup

            import importlib

            importlib.reload(windows_startup)

            # Use custom command
            windows_startup.enable_startup(command='"C:\\test\\app.exe"')

            # Verify SetValueEx was called
            mock_winreg.SetValueEx.assert_called_once()
            call_args = mock_winreg.SetValueEx.call_args
            self.assertEqual(call_args[0][0], mock_key)  # key
            self.assertEqual(call_args[0][1], "AutomaticTwitchMarkers")  # value name
            self.assertEqual(call_args[0][3], mock_winreg.REG_SZ)  # type
            self.assertEqual(call_args[0][4], '"C:\\test\\app.exe"')  # command


# =============================================================================
# disable_startup Tests
# =============================================================================


class TestDisableStartup(unittest.TestCase):
    """Test disable_startup function."""

    @patch.object(sys, "platform", "linux")
    def test_noop_on_non_windows(self) -> None:
        """Should be no-op on non-Windows platforms."""
        from twitch_marker_agent.platform import windows_startup

        import importlib

        importlib.reload(windows_startup)

        # Should not raise
        windows_startup.disable_startup()

    @patch.object(sys, "platform", "win32")
    def test_removes_registry_entry(self) -> None:
        """Should remove registry entry."""
        mock_winreg = MagicMock()
        mock_key = MagicMock()
        mock_winreg.OpenKey.return_value.__enter__ = MagicMock(return_value=mock_key)
        mock_winreg.OpenKey.return_value.__exit__ = MagicMock(return_value=None)
        mock_winreg.KEY_SET_VALUE = 2
        mock_winreg.HKEY_CURRENT_USER = "HKCU"

        with patch.dict("sys.modules", {"winreg": mock_winreg}):
            from twitch_marker_agent.platform import windows_startup

            import importlib

            importlib.reload(windows_startup)

            windows_startup.disable_startup()

            # Verify DeleteValue was called
            mock_winreg.DeleteValue.assert_called_once()
            call_args = mock_winreg.DeleteValue.call_args
            self.assertEqual(call_args[0][0], mock_key)  # key
            self.assertEqual(call_args[0][1], "AutomaticTwitchMarkers")  # value name

    @patch.object(sys, "platform", "win32")
    def test_noop_when_value_missing(self) -> None:
        """Should not raise when registry value doesn't exist."""
        mock_winreg = MagicMock()
        mock_key = MagicMock()
        mock_winreg.OpenKey.return_value.__enter__ = MagicMock(return_value=mock_key)
        mock_winreg.OpenKey.return_value.__exit__ = MagicMock(return_value=None)
        mock_winreg.DeleteValue.side_effect = FileNotFoundError("Value not found")
        mock_winreg.KEY_SET_VALUE = 2
        mock_winreg.HKEY_CURRENT_USER = "HKCU"

        with patch.dict("sys.modules", {"winreg": mock_winreg}):
            from twitch_marker_agent.platform import windows_startup

            import importlib

            importlib.reload(windows_startup)

            # Should not raise
            windows_startup.disable_startup()


# =============================================================================
# get_startup_command Tests
# =============================================================================


class TestGetStartupCommand(unittest.TestCase):
    """Test get_startup_command function."""

    def test_frozen_exe_returns_quoted_executable(self) -> None:
        """Should return quoted sys.executable for frozen exe."""
        from twitch_marker_agent.platform import windows_startup

        with patch.object(sys, "frozen", True, create=True):
            with patch.object(sys, "executable", "C:\\Program Files\\App\\app.exe"):
                result = windows_startup.get_startup_command()

        self.assertEqual(result, '"C:\\Program Files\\App\\app.exe"')

    def test_source_prefers_pythonw(self) -> None:
        """Should prefer pythonw.exe when it exists."""
        from twitch_marker_agent.platform import windows_startup

        # Ensure frozen is False
        if hasattr(sys, "frozen"):
            delattr(sys, "frozen")

        mock_pythonw = MagicMock()
        mock_pythonw.exists.return_value = True

        with patch.object(sys, "executable", "C:\\Python39\\python.exe"):
            with patch.object(Path, "parent", new_callable=lambda: property(lambda self: Path("C:\\Python39"))):
                with patch.object(Path, "__truediv__", return_value=mock_pythonw):
                    with patch.object(mock_pythonw, "__str__", return_value="C:\\Python39\\pythonw.exe"):
                        result = windows_startup.get_startup_command()

        self.assertIn("-m twitch_marker_agent.app", result)

    def test_source_falls_back_to_python(self) -> None:
        """Should fall back to python.exe when pythonw.exe doesn't exist."""
        from twitch_marker_agent.platform import windows_startup

        # Ensure frozen is False
        if hasattr(sys, "frozen"):
            delattr(sys, "frozen")

        mock_pythonw = MagicMock()
        mock_pythonw.exists.return_value = False

        with patch.object(sys, "executable", "C:\\Python39\\python.exe"):
            with patch.object(Path, "__truediv__", return_value=mock_pythonw):
                result = windows_startup.get_startup_command()

        self.assertIn("-m twitch_marker_agent.app", result)
        self.assertIn("python.exe", result)

    def test_command_includes_module_path(self) -> None:
        """Command should include -m twitch_marker_agent.app."""
        from twitch_marker_agent.platform import windows_startup

        # Ensure frozen is False
        if hasattr(sys, "frozen"):
            delattr(sys, "frozen")

        mock_pythonw = MagicMock()
        mock_pythonw.exists.return_value = False

        with patch.object(sys, "executable", "C:\\Python39\\python.exe"):
            with patch.object(Path, "__truediv__", return_value=mock_pythonw):
                result = windows_startup.get_startup_command()

        self.assertIn("-m twitch_marker_agent.app", result)

    def test_command_is_quoted(self) -> None:
        """Command path should be quoted for spaces."""
        from twitch_marker_agent.platform import windows_startup

        with patch.object(sys, "frozen", True, create=True):
            with patch.object(sys, "executable", "C:\\Program Files\\My App\\app.exe"):
                result = windows_startup.get_startup_command()

        self.assertTrue(result.startswith('"'))
        self.assertIn('"', result)

    def test_frozen_command_uses_absolute_path(self) -> None:
        """Frozen startup command should use resolved absolute exe path."""
        from twitch_marker_agent.platform import windows_startup

        with patch.object(sys, "frozen", True, create=True):
            with patch.object(sys, "executable", "TwitchMarkerAgent.exe"):
                with patch.object(
                    Path,
                    "resolve",
                    return_value=Path("C:/Portable/TwitchMarkerAgent/TwitchMarkerAgent.exe"),
                ):
                    result = windows_startup.get_startup_command()

        self.assertTrue(result.startswith('"'))
        self.assertTrue(result.endswith('"'))
        self.assertIn("TwitchMarkerAgent.exe", result)


if __name__ == "__main__":
    unittest.main()
