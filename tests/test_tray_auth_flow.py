"""
Tests for tray controller Device Code Flow auth functions.

Tests cover:
- get_auth_status with/without tokens
- start_device_auth_flow
- complete_device_auth_flow token storage
- disconnect_twitch token clearing
- Cancellation stops polling
"""

import logging
import threading
import time
import unittest
from unittest.mock import MagicMock, Mock, patch

from twitch_marker_agent.tray_controller import (
    AuthStatus,
    DeviceAuthState,
    TOKEN_KEY_AUTH_METHOD,
    complete_device_auth_flow,
    disconnect_twitch,
    get_auth_status,
    start_device_auth_flow,
)


class TestGetAuthStatus(unittest.TestCase):
    """Tests for get_auth_status function."""

    def setUp(self):
        """Set up test fixtures."""
        self.mock_state_store = MagicMock()
        self.mock_http = MagicMock()
        self.logger = logging.getLogger("test")
        self.logger.setLevel(logging.DEBUG)

    def test_get_auth_status_no_token(self):
        """Test returns not authenticated when no token stored."""
        self.mock_state_store.get_token.return_value = None

        result = get_auth_status(
            self.mock_state_store,
            self.mock_http,
            self.logger,
        )

        self.assertFalse(result.is_authenticated)
        self.assertIsNone(result.display_name)

    def test_get_auth_status_with_cached_name(self):
        """Test uses cached display name without network call."""
        self.mock_state_store.get_token.return_value = "valid_token"

        result = get_auth_status(
            self.mock_state_store,
            self.mock_http,
            self.logger,
            cached_display_name="test_user",
        )

        self.assertTrue(result.is_authenticated)
        self.assertEqual(result.display_name, "test_user")
        # Should not have made network call
        self.mock_http.get.assert_not_called()

    def test_get_auth_status_validates_token(self):
        """Test validates token and gets display name from API."""
        self.mock_state_store.get_token.return_value = "valid_token"

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "login": "streamer_name",
            "user_id": "12345",
        }
        self.mock_http.get.return_value = mock_response

        result = get_auth_status(
            self.mock_state_store,
            self.mock_http,
            self.logger,
        )

        self.assertTrue(result.is_authenticated)
        self.assertEqual(result.display_name, "streamer_name")
        self.assertEqual(result.user_id, "12345")

    def test_get_auth_status_invalid_token(self):
        """Test returns not authenticated when token validation fails."""
        self.mock_state_store.get_token.return_value = "invalid_token"

        mock_response = Mock()
        mock_response.status_code = 401
        self.mock_http.get.return_value = mock_response

        result = get_auth_status(
            self.mock_state_store,
            self.mock_http,
            self.logger,
        )

        self.assertFalse(result.is_authenticated)

    def test_get_auth_status_network_error(self):
        """Test assumes authenticated on network error if token exists."""
        self.mock_state_store.get_token.return_value = "some_token"
        self.mock_http.get.side_effect = Exception("Network error")

        result = get_auth_status(
            self.mock_state_store,
            self.mock_http,
            self.logger,
        )

        # Should still report authenticated since we have a token
        self.assertTrue(result.is_authenticated)
        self.assertEqual(result.display_name, "(unknown)")


class TestStartDeviceAuthFlow(unittest.TestCase):
    """Tests for start_device_auth_flow function."""

    def setUp(self):
        """Set up test fixtures."""
        self.mock_http = MagicMock()
        self.logger = logging.getLogger("test")
        self.logger.setLevel(logging.DEBUG)

    @patch("twitch_marker_agent.core.device_auth.request_device_code")
    def test_start_device_auth_flow_calls_request_device_code(self, mock_request):
        """Test delegates to request_device_code."""
        from twitch_marker_agent.core.device_auth import DeviceCodeResponse

        expected_response = DeviceCodeResponse(
            device_code="test_device_code",
            user_code="ABCD-EFGH",
            verification_uri="https://twitch.tv/activate",
            verification_uri_complete="https://twitch.tv/activate?user_code=ABCD-EFGH",
            expires_in=1800,
            interval=5,
        )
        mock_request.return_value = expected_response

        result = start_device_auth_flow(
            client_id="test_client",
            scopes=["channel:manage:broadcast"],
            http_client=self.mock_http,
            logger=self.logger,
        )

        self.assertEqual(result, expected_response)
        mock_request.assert_called_once_with(
            client_id="test_client",
            scopes=["channel:manage:broadcast"],
            http_client=self.mock_http,
            logger=self.logger,
        )


class TestCompleteDeviceAuthFlow(unittest.TestCase):
    """Tests for complete_device_auth_flow function."""

    def setUp(self):
        """Set up test fixtures."""
        self.mock_state_store = MagicMock()
        self.mock_http = MagicMock()
        self.logger = logging.getLogger("test")
        self.logger.setLevel(logging.DEBUG)
        self.cancel_event = threading.Event()

    @patch("twitch_marker_agent.tray_controller.get_auth_status")
    @patch("twitch_marker_agent.core.device_auth.poll_for_device_token")
    def test_complete_device_auth_flow_stores_tokens(self, mock_poll, mock_get_status):
        """Test stores tokens in state store on success."""
        from twitch_marker_agent.core.device_auth import TokenResponse

        mock_poll.return_value = TokenResponse(
            access_token="new_access_token",
            refresh_token="new_refresh_token",
            expires_in=14400,
            scope=["channel:manage:broadcast"],
        )
        mock_get_status.return_value = AuthStatus(
            is_authenticated=True,
            display_name="test_user",
        )

        result = complete_device_auth_flow(
            client_id="test_client",
            device_code="test_device_code",
            scopes=["channel:manage:broadcast"],
            interval=5,
            timeout_seconds=1800,
            state_store=self.mock_state_store,
            http_client=self.mock_http,
            logger=self.logger,
            cancel_event=self.cancel_event,
        )

        # Verify tokens stored
        calls = self.mock_state_store.store_token.call_args_list
        token_keys = [call[0][0] for call in calls]
        
        self.assertIn("twitch_access_token", token_keys)
        self.assertIn("twitch_refresh_token", token_keys)
        self.assertIn("twitch_token_expires_at", token_keys)
        self.assertIn(TOKEN_KEY_AUTH_METHOD, token_keys)

        # Verify auth method stored as "dcf"
        dcf_call = [c for c in calls if c[0][0] == TOKEN_KEY_AUTH_METHOD][0]
        self.assertEqual(dcf_call[0][1], "dcf")

        # Verify result
        self.assertTrue(result.is_authenticated)
        self.assertEqual(result.display_name, "test_user")

    @patch("twitch_marker_agent.core.device_auth.poll_for_device_token")
    def test_complete_device_auth_flow_cancellation(self, mock_poll):
        """Test cancellation raises DeviceAuthCancelledError."""
        from twitch_marker_agent.core.device_auth import DeviceAuthCancelledError

        mock_poll.side_effect = DeviceAuthCancelledError("Cancelled")

        with self.assertRaises(DeviceAuthCancelledError):
            complete_device_auth_flow(
                client_id="test_client",
                device_code="test_device_code",
                scopes=["channel:manage:broadcast"],
                interval=5,
                timeout_seconds=1800,
                state_store=self.mock_state_store,
                http_client=self.mock_http,
                logger=self.logger,
                cancel_event=self.cancel_event,
            )


class TestDisconnectTwitch(unittest.TestCase):
    """Tests for disconnect_twitch function."""

    def setUp(self):
        """Set up test fixtures."""
        self.mock_state_store = MagicMock()
        self.logger = logging.getLogger("test")
        self.logger.setLevel(logging.DEBUG)

    def test_disconnect_twitch_clears_tokens(self):
        """Test clears all token-related keys."""
        disconnect_twitch(
            state_store=self.mock_state_store,
            logger=self.logger,
        )

        # Verify delete_token called for all keys
        calls = self.mock_state_store.delete_token.call_args_list
        deleted_keys = [call[0][0] for call in calls]

        self.assertIn("twitch_access_token", deleted_keys)
        self.assertIn("twitch_refresh_token", deleted_keys)
        self.assertIn("twitch_token_expires_at", deleted_keys)
        self.assertIn(TOKEN_KEY_AUTH_METHOD, deleted_keys)


class TestDeviceAuthState(unittest.TestCase):
    """Tests for DeviceAuthState dataclass."""

    def test_default_state(self):
        """Test default state values."""
        state = DeviceAuthState()

        self.assertFalse(state.is_pending)
        self.assertIsNone(state.cancel_event)
        self.assertIsNone(state.user_code)
        self.assertIsNone(state.verification_uri)

    def test_state_mutation(self):
        """Test state can be mutated."""
        state = DeviceAuthState()
        state.is_pending = True
        state.cancel_event = threading.Event()
        state.user_code = "ABCD-EFGH"
        state.verification_uri = "https://twitch.tv/activate"

        self.assertTrue(state.is_pending)
        self.assertIsNotNone(state.cancel_event)
        self.assertEqual(state.user_code, "ABCD-EFGH")


if __name__ == "__main__":
    unittest.main()
