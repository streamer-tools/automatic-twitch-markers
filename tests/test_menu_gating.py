"""
Tests for menu gating logic when unauthenticated.

Tests the pure helper functions that determine which menu items
should be enabled based on authentication state.
"""

import unittest


def should_enable_twitch_action(is_authenticated: bool, is_fetching: bool) -> bool:
    """
    Determine if a Twitch-dependent action should be enabled.

    This function mirrors the gating logic in app.py's is_fetch_enabled
    and is_auto_mode_enabled helpers.

    Args:
        is_authenticated: Whether user is authenticated with Twitch.
        is_fetching: Whether a fetch operation is in progress.

    Returns:
        True if the action should be enabled.
    """
    return is_authenticated and not is_fetching


def should_enable_auto_mode(is_authenticated: bool) -> bool:
    """
    Determine if auto mode controls should be enabled.

    Args:
        is_authenticated: Whether user is authenticated with Twitch.

    Returns:
        True if auto mode should be enabled.
    """
    return is_authenticated


def should_enable_output_folder() -> bool:
    """
    Determine if output folder actions should be enabled.

    Output folder is always enabled regardless of auth.

    Returns:
        Always True.
    """
    return True


class TestMenuGating(unittest.TestCase):
    """Tests for menu gating based on auth state."""

    def test_unauthenticated_disables_fetch(self):
        """When unauthenticated, fetch should be disabled."""
        result = should_enable_twitch_action(
            is_authenticated=False,
            is_fetching=False,
        )
        self.assertFalse(result)

    def test_authenticated_enables_fetch(self):
        """When authenticated and not fetching, fetch should be enabled."""
        result = should_enable_twitch_action(
            is_authenticated=True,
            is_fetching=False,
        )
        self.assertTrue(result)

    def test_authenticated_but_fetching_disables(self):
        """When authenticated but currently fetching, fetch should be disabled."""
        result = should_enable_twitch_action(
            is_authenticated=True,
            is_fetching=True,
        )
        self.assertFalse(result)

    def test_unauthenticated_and_fetching_disables(self):
        """When unauthenticated and fetching, fetch should be disabled."""
        result = should_enable_twitch_action(
            is_authenticated=False,
            is_fetching=True,
        )
        self.assertFalse(result)

    def test_unauthenticated_disables_auto_mode(self):
        """When unauthenticated, auto mode should be disabled."""
        result = should_enable_auto_mode(is_authenticated=False)
        self.assertFalse(result)

    def test_authenticated_enables_auto_mode(self):
        """When authenticated, auto mode should be enabled."""
        result = should_enable_auto_mode(is_authenticated=True)
        self.assertTrue(result)

    def test_output_folder_always_enabled(self):
        """Output folder should always be enabled regardless of auth."""
        result = should_enable_output_folder()
        self.assertTrue(result)


class TestMenuGatingDecisions(unittest.TestCase):
    """Tests that verify agreed menu gating decisions from the plan."""

    def test_fetch_requires_auth(self):
        """Fetch actions require authentication."""
        # Unauthenticated -> disabled
        self.assertFalse(should_enable_twitch_action(False, False))
        # Authenticated -> enabled
        self.assertTrue(should_enable_twitch_action(True, False))

    def test_auto_mode_requires_auth(self):
        """Auto mode start/stop requires authentication."""
        self.assertFalse(should_enable_auto_mode(False))
        self.assertTrue(should_enable_auto_mode(True))

    def test_non_auth_items_always_enabled(self):
        """Non-auth items should always be enabled."""
        # Output folder is always enabled
        self.assertTrue(should_enable_output_folder())
        # These are represented by always-True in app.py:
        # - EDL toggle (enabled=True by default in menu)
        # - Start on Windows Login (enabled=True by default)
        # - Exit (enabled=True by default)
        # - Authenticate with Twitch (visible when not auth)


if __name__ == "__main__":
    unittest.main()
