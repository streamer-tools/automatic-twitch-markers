"""
Unit tests for Twitch OAuth module.

Tests pure helper functions and mocked HTTP interactions.
No real network calls or port binding.
"""

import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

from twitch_marker_agent.core.state_store import StateStore
from twitch_marker_agent.core.twitch_oauth import (
    DEFAULT_SCOPES,
    OAuthCancelledError,
    TokenExchangeError,
    TwitchOAuth,
    build_authorize_url,
    compute_expires_at,
    parse_redirect_uri,
    validate_callback_params,
)


class TestBuildAuthorizeUrl(unittest.TestCase):
    """Tests for build_authorize_url helper."""

    def test_contains_all_required_params(self) -> None:
        """URL should contain client_id, redirect_uri, response_type, scope, state."""
        url = build_authorize_url(
            client_id="test_client_id",
            redirect_uri="http://localhost:3000/callback",
            scopes=["user:read:broadcast"],
            state="test_state_123",
        )

        self.assertIn("client_id=test_client_id", url)
        self.assertIn("redirect_uri=http", url)
        self.assertIn("response_type=code", url)
        self.assertIn("scope=user%3Aread%3Abroadcast", url)
        self.assertIn("state=test_state_123", url)

    def test_starts_with_twitch_auth_endpoint(self) -> None:
        """URL should start with Twitch authorization endpoint."""
        url = build_authorize_url(
            client_id="test",
            redirect_uri="http://localhost:3000/callback",
            scopes=["user:read:broadcast"],
            state="test",
        )

        self.assertTrue(url.startswith("https://id.twitch.tv/oauth2/authorize?"))

    def test_multiple_scopes_space_separated(self) -> None:
        """Multiple scopes should be space-separated (URL encoded as +)."""
        url = build_authorize_url(
            client_id="test",
            redirect_uri="http://localhost:3000/callback",
            scopes=["user:read:broadcast", "channel:read:subscriptions"],
            state="test",
        )

        # Space is encoded as + or %20 in URLs
        self.assertTrue(
            "scope=user%3Aread%3Abroadcast+channel" in url
            or "scope=user%3Aread%3Abroadcast%20channel" in url
        )


class TestParseRedirectUri(unittest.TestCase):
    """Tests for parse_redirect_uri helper."""

    def test_parses_localhost_with_port(self) -> None:
        """Should correctly parse localhost URI with port."""
        host, port, path = parse_redirect_uri("http://localhost:3000/callback")

        self.assertEqual(host, "localhost")
        self.assertEqual(port, 3000)
        self.assertEqual(path, "/callback")

    def test_parses_127_0_0_1_with_port(self) -> None:
        """Should correctly parse 127.0.0.1 URI."""
        host, port, path = parse_redirect_uri("http://127.0.0.1:8080/auth/callback")

        self.assertEqual(host, "127.0.0.1")
        self.assertEqual(port, 8080)
        self.assertEqual(path, "/auth/callback")

    def test_default_http_port(self) -> None:
        """Should default to port 80 for http without explicit port."""
        host, port, path = parse_redirect_uri("http://localhost/callback")

        self.assertEqual(port, 80)

    def test_default_https_port(self) -> None:
        """Should default to port 443 for https without explicit port."""
        host, port, path = parse_redirect_uri("https://localhost/callback")

        self.assertEqual(port, 443)

    def test_default_path(self) -> None:
        """Should default to / for missing path."""
        host, port, path = parse_redirect_uri("http://localhost:3000")

        self.assertEqual(path, "/")


class TestComputeExpiresAt(unittest.TestCase):
    """Tests for compute_expires_at helper."""

    def test_returns_iso8601_format(self) -> None:
        """Should return ISO8601 formatted string."""
        result = compute_expires_at(3600)

        # Should be parseable as ISO8601
        parsed = datetime.fromisoformat(result)
        self.assertIsInstance(parsed, datetime)

    def test_is_timezone_aware(self) -> None:
        """Should return timezone-aware UTC datetime."""
        result = compute_expires_at(3600)

        parsed = datetime.fromisoformat(result)
        self.assertIsNotNone(parsed.tzinfo)
        self.assertEqual(parsed.tzinfo, timezone.utc)

    def test_is_in_future(self) -> None:
        """Computed time should be in the future."""
        result = compute_expires_at(3600)

        parsed = datetime.fromisoformat(result)
        now = datetime.now(timezone.utc)
        self.assertGreater(parsed, now)


class TestValidateCallbackParams(unittest.TestCase):
    """Tests for validate_callback_params helper."""

    def test_success_returns_code(self) -> None:
        """Should return authorization code when state matches."""
        params = {
            "code": ["auth_code_123"],
            "state": ["expected_state"],
        }

        result = validate_callback_params(params, "expected_state")

        self.assertEqual(result, "auth_code_123")

    def test_state_mismatch_raises(self) -> None:
        """Should raise OAuthCancelledError on state mismatch."""
        params = {
            "code": ["auth_code_123"],
            "state": ["wrong_state"],
        }

        with self.assertRaises(OAuthCancelledError) as ctx:
            validate_callback_params(params, "expected_state")

        self.assertIn("State mismatch", str(ctx.exception))

    def test_missing_state_raises(self) -> None:
        """Should raise OAuthCancelledError when state is missing."""
        params = {
            "code": ["auth_code_123"],
        }

        with self.assertRaises(OAuthCancelledError) as ctx:
            validate_callback_params(params, "expected_state")

        self.assertIn("Missing state", str(ctx.exception))

    def test_error_param_raises(self) -> None:
        """Should raise OAuthCancelledError when error param is present."""
        params = {
            "error": ["access_denied"],
            "error_description": ["The user denied the request"],
            "state": ["expected_state"],
        }

        with self.assertRaises(OAuthCancelledError) as ctx:
            validate_callback_params(params, "expected_state")

        self.assertIn("access_denied", str(ctx.exception))

    def test_missing_code_raises(self) -> None:
        """Should raise OAuthCancelledError when code is missing."""
        params = {
            "state": ["expected_state"],
        }

        with self.assertRaises(OAuthCancelledError) as ctx:
            validate_callback_params(params, "expected_state")

        self.assertIn("Missing authorization code", str(ctx.exception))


class TestTwitchOAuthTokenExchange(unittest.TestCase):
    """Tests for TwitchOAuth token exchange with mocked HTTP."""

    def setUp(self) -> None:
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = Path(self.temp_dir) / "test_state.db"
        self.state_store = StateStore(self.db_path)

        # Mock config
        self.mock_config = MagicMock()
        self.mock_config.client_id = "test_client_id"
        self.mock_config.client_secret = "test_client_secret"
        self.mock_config.redirect_uri = "http://localhost:3000/callback"

        # Mock logger
        self.mock_logger = MagicMock()

        # Mock HTTP session
        self.mock_session = MagicMock()

    def tearDown(self) -> None:
        """Clean up test fixtures."""
        import shutil
        self.state_store.close()
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_exchange_stores_all_tokens(self) -> None:
        """Token exchange should store access, refresh, and expires_at."""
        # Mock successful token response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "access_token": "test_access_token",
            "refresh_token": "test_refresh_token",
            "expires_in": 3600,
            "token_type": "bearer",
        }
        self.mock_session.post.return_value = mock_response

        oauth = TwitchOAuth(
            config=self.mock_config,
            state_store=self.state_store,
            logger=self.mock_logger,
            http_session=self.mock_session,
        )

        # Call the internal exchange method directly
        oauth._exchange_code_for_tokens("test_auth_code")

        # Verify tokens are stored
        self.assertEqual(
            self.state_store.get_token(TwitchOAuth.TOKEN_KEY_ACCESS),
            "test_access_token",
        )
        self.assertEqual(
            self.state_store.get_token(TwitchOAuth.TOKEN_KEY_REFRESH),
            "test_refresh_token",
        )
        self.assertIsNotNone(
            self.state_store.get_token(TwitchOAuth.TOKEN_KEY_EXPIRES)
        )

    def test_exchange_sends_correct_post_body(self) -> None:
        """Token exchange should send correct form data."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "access_token": "test",
            "expires_in": 3600,
        }
        self.mock_session.post.return_value = mock_response

        oauth = TwitchOAuth(
            config=self.mock_config,
            state_store=self.state_store,
            logger=self.mock_logger,
            http_session=self.mock_session,
        )

        oauth._exchange_code_for_tokens("my_auth_code")

        # Verify POST was called with correct data
        call_args = self.mock_session.post.call_args
        self.assertEqual(call_args.kwargs["data"]["grant_type"], "authorization_code")
        self.assertEqual(call_args.kwargs["data"]["code"], "my_auth_code")
        self.assertEqual(call_args.kwargs["data"]["client_id"], "test_client_id")
        self.assertEqual(call_args.kwargs["data"]["redirect_uri"], "http://localhost:3000/callback")

    def test_exchange_raises_on_http_error(self) -> None:
        """Token exchange should raise TokenExchangeError on HTTP error."""
        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.json.return_value = {
            "error": "invalid_grant",
            "error_description": "Invalid authorization code",
        }
        self.mock_session.post.return_value = mock_response

        oauth = TwitchOAuth(
            config=self.mock_config,
            state_store=self.state_store,
            logger=self.mock_logger,
            http_session=self.mock_session,
        )

        with self.assertRaises(TokenExchangeError):
            oauth._exchange_code_for_tokens("bad_code")

    def test_exchange_handles_missing_refresh_token(self) -> None:
        """Token exchange should not fail if refresh_token is missing."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "access_token": "test_access_token",
            "expires_in": 3600,
            # No refresh_token
        }
        self.mock_session.post.return_value = mock_response

        oauth = TwitchOAuth(
            config=self.mock_config,
            state_store=self.state_store,
            logger=self.mock_logger,
            http_session=self.mock_session,
        )

        # Should not raise
        oauth._exchange_code_for_tokens("test_code")

        # Access token should be stored
        self.assertEqual(
            self.state_store.get_token(TwitchOAuth.TOKEN_KEY_ACCESS),
            "test_access_token",
        )

        # Refresh token should not be stored
        self.assertIsNone(
            self.state_store.get_token(TwitchOAuth.TOKEN_KEY_REFRESH)
        )


class TestTwitchOAuthDI(unittest.TestCase):
    """Tests for TwitchOAuth dependency injection."""

    def setUp(self) -> None:
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = Path(self.temp_dir) / "test_state.db"
        self.state_store = StateStore(self.db_path)

        self.mock_config = MagicMock()
        self.mock_config.client_id = "test_client"
        self.mock_config.redirect_uri = "http://localhost:3000/callback"

        self.mock_logger = MagicMock()

    def tearDown(self) -> None:
        """Clean up test fixtures."""
        import shutil
        self.state_store.close()
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_accepts_custom_http_session(self) -> None:
        """Should accept injected HTTP session."""
        custom_session = MagicMock()

        oauth = TwitchOAuth(
            config=self.mock_config,
            state_store=self.state_store,
            logger=self.mock_logger,
            http_session=custom_session,
        )

        self.assertIs(oauth._http_session, custom_session)

    def test_accepts_custom_browser_opener(self) -> None:
        """Should accept injected browser opener."""
        custom_opener = MagicMock(return_value=True)

        oauth = TwitchOAuth(
            config=self.mock_config,
            state_store=self.state_store,
            logger=self.mock_logger,
            browser_opener=custom_opener,
        )

        self.assertIs(oauth._browser_opener, custom_opener)

    @patch("twitch_marker_agent.core.twitch_oauth.secrets.token_urlsafe")
    def test_get_authorization_url_deterministic(self, mock_token: MagicMock) -> None:
        """get_authorization_url should use secrets.token_urlsafe for state."""
        mock_token.return_value = "deterministic_state"

        oauth = TwitchOAuth(
            config=self.mock_config,
            state_store=self.state_store,
            logger=self.mock_logger,
        )

        url = oauth.get_authorization_url()

        mock_token.assert_called_once_with(32)
        self.assertIn("state=deterministic_state", url)


class TestTwitchOAuthHasRefreshToken(unittest.TestCase):
    """Tests for has_refresh_token method."""

    def setUp(self) -> None:
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = Path(self.temp_dir) / "test_state.db"
        self.state_store = StateStore(self.db_path)

        self.mock_config = MagicMock()
        self.mock_logger = MagicMock()

    def tearDown(self) -> None:
        """Clean up test fixtures."""
        import shutil
        self.state_store.close()
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_returns_false_when_no_token(self) -> None:
        """Should return False when no refresh token stored."""
        oauth = TwitchOAuth(
            config=self.mock_config,
            state_store=self.state_store,
            logger=self.mock_logger,
        )

        self.assertFalse(oauth.has_refresh_token())

    def test_returns_true_when_token_exists(self) -> None:
        """Should return True when refresh token is stored."""
        self.state_store.store_token(TwitchOAuth.TOKEN_KEY_REFRESH, "stored_token")

        oauth = TwitchOAuth(
            config=self.mock_config,
            state_store=self.state_store,
            logger=self.mock_logger,
        )

        self.assertTrue(oauth.has_refresh_token())


if __name__ == "__main__":
    unittest.main()
