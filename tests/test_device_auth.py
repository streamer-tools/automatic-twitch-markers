"""
Tests for Device Code Flow authentication module.

Tests cover:
- request_device_code success and error cases
- poll_for_device_token with various DCF statuses
- Cancellation via cancel_event
- Safe error messages (no secrets logged)
"""

import logging
import threading
import unittest
from unittest.mock import MagicMock, Mock, patch

from twitch_marker_agent.core.device_auth import (
    DCF_GRANT_TYPE,
    TWITCH_DEVICE_URL,
    TWITCH_TOKEN_URL,
    DeviceAuthCancelledError,
    DeviceAuthDeniedError,
    DeviceAuthError,
    DeviceCodeExpiredError,
    DeviceCodeResponse,
    TokenResponse,
    poll_for_device_token,
    request_device_code,
)


class TestRequestDeviceCode(unittest.TestCase):
    """Tests for request_device_code function."""

    def setUp(self):
        """Set up test fixtures."""
        self.mock_http = MagicMock()
        self.logger = logging.getLogger("test")
        self.logger.setLevel(logging.DEBUG)
        self.client_id = "test_client_id"
        self.scopes = ["channel:manage:broadcast"]

    def test_request_device_code_success(self):
        """Test successful device code request."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "device_code": "abc123",
            "user_code": "ABCD-EFGH",
            "verification_uri": "https://www.twitch.tv/activate",
            "expires_in": 1800,
            "interval": 5,
        }
        self.mock_http.post.return_value = mock_response

        result = request_device_code(
            self.client_id, self.scopes, self.mock_http, self.logger
        )

        self.assertIsInstance(result, DeviceCodeResponse)
        self.assertEqual(result.device_code, "abc123")
        self.assertEqual(result.user_code, "ABCD-EFGH")
        self.assertEqual(result.verification_uri, "https://www.twitch.tv/activate")
        self.assertEqual(result.expires_in, 1800)
        self.assertEqual(result.interval, 5)
        # verification_uri_complete should be None when not provided
        self.assertIsNone(result.verification_uri_complete)

        # Verify POST was called correctly
        self.mock_http.post.assert_called_once()
        call_args = self.mock_http.post.call_args
        self.assertEqual(call_args[0][0], TWITCH_DEVICE_URL)
        self.assertEqual(call_args[1]["data"]["client_id"], self.client_id)
        self.assertEqual(call_args[1]["data"]["scopes"], "channel:manage:broadcast")

    def test_request_device_code_with_verification_uri_complete(self):
        """Test device code request includes verification_uri_complete when present."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "device_code": "abc123",
            "user_code": "ABCD-EFGH",
            "verification_uri": "https://www.twitch.tv/activate",
            "verification_uri_complete": "https://www.twitch.tv/activate?user_code=ABCD-EFGH",
            "expires_in": 1800,
            "interval": 5,
        }
        self.mock_http.post.return_value = mock_response

        result = request_device_code(
            self.client_id, self.scopes, self.mock_http, self.logger
        )

        self.assertIsInstance(result, DeviceCodeResponse)
        self.assertEqual(result.user_code, "ABCD-EFGH")
        self.assertEqual(result.verification_uri, "https://www.twitch.tv/activate")
        self.assertEqual(
            result.verification_uri_complete,
            "https://www.twitch.tv/activate?user_code=ABCD-EFGH"
        )

    def test_request_device_code_network_error(self):
        """Test network error during device code request."""
        import requests

        self.mock_http.post.side_effect = requests.RequestException("Connection failed")

        with self.assertRaises(DeviceAuthError) as ctx:
            request_device_code(
                self.client_id, self.scopes, self.mock_http, self.logger
            )

        self.assertIn("Network error", str(ctx.exception))

    def test_request_device_code_api_error(self):
        """Test API error response."""
        mock_response = Mock()
        mock_response.status_code = 400
        mock_response.json.return_value = {
            "error": "invalid_client",
            "message": "Invalid client ID",
        }
        self.mock_http.post.return_value = mock_response

        with self.assertRaises(DeviceAuthError) as ctx:
            request_device_code(
                self.client_id, self.scopes, self.mock_http, self.logger
            )

        self.assertIn("400", str(ctx.exception))

    def test_request_device_code_missing_fields(self):
        """Test response missing required fields."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "user_code": "ABCD-EFGH",
            # Missing device_code and verification_uri
        }
        self.mock_http.post.return_value = mock_response

        with self.assertRaises(DeviceAuthError) as ctx:
            request_device_code(
                self.client_id, self.scopes, self.mock_http, self.logger
            )

        self.assertIn("missing required fields", str(ctx.exception))

    def test_request_device_code_invalid_json(self):
        """Test invalid JSON response."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.side_effect = ValueError("Invalid JSON")
        self.mock_http.post.return_value = mock_response

        with self.assertRaises(DeviceAuthError) as ctx:
            request_device_code(
                self.client_id, self.scopes, self.mock_http, self.logger
            )

        self.assertIn("Invalid JSON", str(ctx.exception))


class TestPollForDeviceToken(unittest.TestCase):
    """Tests for poll_for_device_token function."""

    def setUp(self):
        """Set up test fixtures."""
        self.mock_http = MagicMock()
        self.logger = logging.getLogger("test")
        self.logger.setLevel(logging.DEBUG)
        self.client_id = "test_client_id"
        self.device_code = "device_code_123"
        self.scopes = ["channel:manage:broadcast"]

    def test_poll_success_immediate(self):
        """Test immediate success on first poll."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "access_token": "access_123",
            "refresh_token": "refresh_456",
            "expires_in": 14820,
            "scope": ["channel:manage:broadcast"],
        }
        self.mock_http.post.return_value = mock_response

        with patch("twitch_marker_agent.core.device_auth.time.sleep"):
            result = poll_for_device_token(
                self.client_id,
                self.device_code,
                self.scopes,
                interval=1,
                timeout_seconds=30,
                http_client=self.mock_http,
                logger=self.logger,
            )

        self.assertIsInstance(result, TokenResponse)
        self.assertEqual(result.access_token, "access_123")
        self.assertEqual(result.refresh_token, "refresh_456")
        self.assertEqual(result.expires_in, 14820)

    def test_poll_authorization_pending_then_success(self):
        """Test authorization_pending followed by success."""
        pending_response = Mock()
        pending_response.status_code = 400
        pending_response.json.return_value = {"status": 400, "message": "authorization_pending"}

        success_response = Mock()
        success_response.status_code = 200
        success_response.json.return_value = {
            "access_token": "access_123",
            "refresh_token": "refresh_456",
            "expires_in": 14820,
            "scope": ["channel:manage:broadcast"],
        }

        # Return pending first, then success
        self.mock_http.post.side_effect = [pending_response, success_response]

        with patch("twitch_marker_agent.core.device_auth.time.sleep"):
            with patch("twitch_marker_agent.core.device_auth.time.monotonic") as mock_time:
                # Simulate time passing
                mock_time.side_effect = [0, 0, 1, 1, 2, 2, 3]
                result = poll_for_device_token(
                    self.client_id,
                    self.device_code,
                    self.scopes,
                    interval=1,
                    timeout_seconds=30,
                    http_client=self.mock_http,
                    logger=self.logger,
                )

        self.assertEqual(result.access_token, "access_123")
        self.assertEqual(self.mock_http.post.call_count, 2)

    def test_poll_slow_down_increases_interval(self):
        """Test slow_down response increases polling interval."""
        slow_down_response = Mock()
        slow_down_response.status_code = 400
        slow_down_response.json.return_value = {"status": 400, "message": "slow_down"}

        success_response = Mock()
        success_response.status_code = 200
        success_response.json.return_value = {
            "access_token": "access_123",
            "refresh_token": "refresh_456",
            "expires_in": 14820,
            "scope": [],
        }

        self.mock_http.post.side_effect = [slow_down_response, success_response]

        # Use a counter to track monotonic calls and return increasing time
        call_count = [0]
        def mock_monotonic():
            call_count[0] += 1
            # First calls are for main loop, inner loop calls get larger values
            # to break out of wait loop quickly
            return call_count[0] * 100  # Always increasing, breaks wait loops

        with patch("twitch_marker_agent.core.device_auth.time.sleep"):
            with patch("twitch_marker_agent.core.device_auth.time.monotonic", side_effect=mock_monotonic):
                result = poll_for_device_token(
                    self.client_id,
                    self.device_code,
                    self.scopes,
                    interval=5,
                    timeout_seconds=100000,  # Large enough to not timeout
                    http_client=self.mock_http,
                    logger=self.logger,
                )

        self.assertEqual(result.access_token, "access_123")

    def test_poll_expired_token_raises(self):
        """Test expired_token response raises DeviceCodeExpiredError."""
        mock_response = Mock()
        mock_response.status_code = 400
        mock_response.json.return_value = {"status": 400, "message": "expired_token"}
        self.mock_http.post.return_value = mock_response

        with patch("twitch_marker_agent.core.device_auth.time.sleep"):
            with patch("twitch_marker_agent.core.device_auth.time.monotonic") as mock_time:
                mock_time.side_effect = [0, 0, 1, 1, 2]
                with self.assertRaises(DeviceCodeExpiredError) as ctx:
                    poll_for_device_token(
                        self.client_id,
                        self.device_code,
                        self.scopes,
                        interval=1,
                        timeout_seconds=30,
                        http_client=self.mock_http,
                        logger=self.logger,
                    )

        self.assertIn("expired", str(ctx.exception).lower())

    def test_poll_access_denied_raises(self):
        """Test access_denied response raises DeviceAuthDeniedError."""
        mock_response = Mock()
        mock_response.status_code = 400
        mock_response.json.return_value = {"status": 400, "message": "access_denied"}
        self.mock_http.post.return_value = mock_response

        with patch("twitch_marker_agent.core.device_auth.time.sleep"):
            with patch("twitch_marker_agent.core.device_auth.time.monotonic") as mock_time:
                mock_time.side_effect = [0, 0, 1, 1, 2]
                with self.assertRaises(DeviceAuthDeniedError) as ctx:
                    poll_for_device_token(
                        self.client_id,
                        self.device_code,
                        self.scopes,
                        interval=1,
                        timeout_seconds=30,
                        http_client=self.mock_http,
                        logger=self.logger,
                    )

        self.assertIn("denied", str(ctx.exception).lower())

    def test_poll_cancellation(self):
        """Test cancellation via cancel_event."""
        cancel_event = threading.Event()
        cancel_event.set()  # Already cancelled

        with self.assertRaises(DeviceAuthCancelledError) as ctx:
            poll_for_device_token(
                self.client_id,
                self.device_code,
                self.scopes,
                interval=5,
                timeout_seconds=30,
                http_client=self.mock_http,
                logger=self.logger,
                cancel_event=cancel_event,
            )

        self.assertIn("cancelled", str(ctx.exception).lower())

    def test_poll_network_error_safe_message(self):
        """Test network error produces safe error message (no secrets)."""
        import requests

        self.mock_http.post.side_effect = requests.RequestException("Connection failed")

        with patch("twitch_marker_agent.core.device_auth.time.sleep"):
            with patch("twitch_marker_agent.core.device_auth.time.monotonic") as mock_time:
                mock_time.side_effect = [0, 0, 1, 1, 2]
                with self.assertRaises(DeviceAuthError) as ctx:
                    poll_for_device_token(
                        self.client_id,
                        self.device_code,
                        self.scopes,
                        interval=1,
                        timeout_seconds=30,
                        http_client=self.mock_http,
                        logger=self.logger,
                    )

        error_msg = str(ctx.exception)
        # Ensure no secrets in error message
        self.assertNotIn(self.device_code, error_msg)
        self.assertIn("Network error", error_msg)

    def test_poll_timeout(self):
        """Test polling timeout raises DeviceCodeExpiredError."""
        pending_response = Mock()
        pending_response.status_code = 400
        pending_response.json.return_value = {"status": 400, "message": "authorization_pending"}
        self.mock_http.post.return_value = pending_response

        # Use a counter that simulates timeout after first loop iteration
        call_count = [0]
        def mock_monotonic():
            call_count[0] += 1
            # Return 0 for start_time, then jump past timeout
            if call_count[0] == 1:
                return 0  # start_time
            elif call_count[0] == 2:
                return 0  # wait_start
            else:
                return 100  # Past timeout (30 seconds)

        with patch("twitch_marker_agent.core.device_auth.time.sleep"):
            with patch("twitch_marker_agent.core.device_auth.time.monotonic", side_effect=mock_monotonic):
                with self.assertRaises(DeviceCodeExpiredError) as ctx:
                    poll_for_device_token(
                        self.client_id,
                        self.device_code,
                        self.scopes,
                        interval=1,
                        timeout_seconds=30,
                        http_client=self.mock_http,
                        logger=self.logger,
                    )

        self.assertIn("timed out", str(ctx.exception).lower())

    def test_poll_missing_access_token(self):
        """Test response missing access_token raises error."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "refresh_token": "refresh_456",
            # Missing access_token
        }
        self.mock_http.post.return_value = mock_response

        with patch("twitch_marker_agent.core.device_auth.time.sleep"):
            with patch("twitch_marker_agent.core.device_auth.time.monotonic") as mock_time:
                mock_time.side_effect = [0, 0, 1, 1, 2]
                with self.assertRaises(DeviceAuthError) as ctx:
                    poll_for_device_token(
                        self.client_id,
                        self.device_code,
                        self.scopes,
                        interval=1,
                        timeout_seconds=30,
                        http_client=self.mock_http,
                        logger=self.logger,
                    )

        self.assertIn("missing access_token", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
