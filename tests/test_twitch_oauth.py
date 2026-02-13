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


# =============================================================================
# Phase C Tests: Token Maintenance
# =============================================================================


class TestRefreshAccessToken(unittest.TestCase):
    """Tests for refresh_access_token method."""

    def setUp(self) -> None:
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = Path(self.temp_dir) / "test_state.db"
        self.state_store = StateStore(self.db_path)

        self.mock_config = MagicMock()
        self.mock_config.client_id = "test_client_id"
        self.mock_config.client_secret = "test_client_secret"

        self.mock_logger = MagicMock()
        self.mock_session = MagicMock()

    def tearDown(self) -> None:
        """Clean up test fixtures."""
        import shutil
        self.state_store.close()
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_refresh_success_stores_access_token(self) -> None:
        """Successful refresh should store new access token."""
        # Store initial refresh token
        self.state_store.store_token(TwitchOAuth.TOKEN_KEY_REFRESH, "old_refresh")

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "access_token": "new_access_token",
            "expires_in": 3600,
        }
        self.mock_session.post.return_value = mock_response

        oauth = TwitchOAuth(
            config=self.mock_config,
            state_store=self.state_store,
            logger=self.mock_logger,
            http_session=self.mock_session,
        )

        oauth.refresh_access_token()

        self.assertEqual(
            self.state_store.get_token(TwitchOAuth.TOKEN_KEY_ACCESS),
            "new_access_token",
        )

    def test_refresh_success_stores_expires_at(self) -> None:
        """Successful refresh should store new expires_at."""
        self.state_store.store_token(TwitchOAuth.TOKEN_KEY_REFRESH, "old_refresh")

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "access_token": "new_access_token",
            "expires_in": 7200,
        }
        self.mock_session.post.return_value = mock_response

        oauth = TwitchOAuth(
            config=self.mock_config,
            state_store=self.state_store,
            logger=self.mock_logger,
            http_session=self.mock_session,
        )

        oauth.refresh_access_token()

        expires_at = self.state_store.get_token(TwitchOAuth.TOKEN_KEY_EXPIRES)
        self.assertIsNotNone(expires_at)
        # Verify it's valid ISO8601
        parsed = datetime.fromisoformat(expires_at)
        self.assertIsNotNone(parsed.tzinfo)

    def test_refresh_rotates_refresh_token(self) -> None:
        """Refresh should store new refresh token when provided."""
        self.state_store.store_token(TwitchOAuth.TOKEN_KEY_REFRESH, "old_refresh")

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "access_token": "new_access",
            "refresh_token": "rotated_refresh",
            "expires_in": 3600,
        }
        self.mock_session.post.return_value = mock_response

        oauth = TwitchOAuth(
            config=self.mock_config,
            state_store=self.state_store,
            logger=self.mock_logger,
            http_session=self.mock_session,
        )

        oauth.refresh_access_token()

        self.assertEqual(
            self.state_store.get_token(TwitchOAuth.TOKEN_KEY_REFRESH),
            "rotated_refresh",
        )

    def test_refresh_preserves_refresh_token_if_omitted(self) -> None:
        """Refresh should preserve old refresh token when response omits it."""
        self.state_store.store_token(TwitchOAuth.TOKEN_KEY_REFRESH, "original_refresh")

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "access_token": "new_access",
            "expires_in": 3600,
            # No refresh_token in response
        }
        self.mock_session.post.return_value = mock_response

        oauth = TwitchOAuth(
            config=self.mock_config,
            state_store=self.state_store,
            logger=self.mock_logger,
            http_session=self.mock_session,
        )

        oauth.refresh_access_token()

        # Original refresh token should be preserved
        self.assertEqual(
            self.state_store.get_token(TwitchOAuth.TOKEN_KEY_REFRESH),
            "original_refresh",
        )

    def test_refresh_401_raises_reauth_error(self) -> None:
        """Refresh 401 should raise error with auth-login message."""
        from twitch_marker_agent.core.twitch_oauth import TokenRefreshError

        self.state_store.store_token(TwitchOAuth.TOKEN_KEY_REFRESH, "expired_refresh")

        mock_response = MagicMock()
        mock_response.status_code = 401
        self.mock_session.post.return_value = mock_response

        oauth = TwitchOAuth(
            config=self.mock_config,
            state_store=self.state_store,
            logger=self.mock_logger,
            http_session=self.mock_session,
        )

        with self.assertRaises(TokenRefreshError) as ctx:
            oauth.refresh_access_token()

        self.assertIn("expired", str(ctx.exception).lower())

    def test_refresh_no_stored_token_raises(self) -> None:
        """Refresh without stored token should raise with auth-login message."""
        from twitch_marker_agent.core.twitch_oauth import TokenRefreshError

        # No refresh token stored

        oauth = TwitchOAuth(
            config=self.mock_config,
            state_store=self.state_store,
            logger=self.mock_logger,
            http_session=self.mock_session,
        )

        with self.assertRaises(TokenRefreshError) as ctx:
            oauth.refresh_access_token()

        self.assertIn("auth-login", str(ctx.exception))

    def test_refresh_sends_correct_payload(self) -> None:
        """Refresh should POST with required fields: grant_type, refresh_token, client_id, client_secret."""
        self.state_store.store_token(TwitchOAuth.TOKEN_KEY_REFRESH, "my_refresh_token")

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "access_token": "new_access",
            "expires_in": 3600,
        }
        self.mock_session.post.return_value = mock_response

        oauth = TwitchOAuth(
            config=self.mock_config,
            state_store=self.state_store,
            logger=self.mock_logger,
            http_session=self.mock_session,
        )

        oauth.refresh_access_token()

        # Verify POST was called with correct data= parameter
        call_args = self.mock_session.post.call_args
        sent_data = call_args.kwargs.get("data", {})

        self.assertEqual(sent_data["grant_type"], "refresh_token")
        self.assertEqual(sent_data["refresh_token"], "my_refresh_token")
        self.assertEqual(sent_data["client_id"], "test_client_id")
        self.assertEqual(sent_data["client_secret"], "test_client_secret")

    def test_refresh_uses_correct_timeout(self) -> None:
        """Refresh should use the expected timeout tuple (10, 30)."""
        from twitch_marker_agent.core.twitch_oauth import HTTP_TIMEOUT

        self.state_store.store_token(TwitchOAuth.TOKEN_KEY_REFRESH, "refresh_token")

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "access_token": "new_access",
            "expires_in": 3600,
        }
        self.mock_session.post.return_value = mock_response

        oauth = TwitchOAuth(
            config=self.mock_config,
            state_store=self.state_store,
            logger=self.mock_logger,
            http_session=self.mock_session,
        )

        oauth.refresh_access_token()

        # Verify timeout was passed correctly
        call_args = self.mock_session.post.call_args
        sent_timeout = call_args.kwargs.get("timeout")

        self.assertEqual(sent_timeout, HTTP_TIMEOUT)
        self.assertEqual(sent_timeout, (10, 30))

    def test_refresh_dcf_omits_client_secret(self) -> None:
        """DCF tokens should NOT include client_secret in refresh request."""
        from twitch_marker_agent.tray_controller import TOKEN_KEY_AUTH_METHOD

        # Store tokens with DCF auth method
        self.state_store.store_token(TwitchOAuth.TOKEN_KEY_REFRESH, "dcf_refresh")
        self.state_store.store_token(TOKEN_KEY_AUTH_METHOD, "dcf")

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "access_token": "new_access",
            "refresh_token": "rotated_refresh",
            "expires_in": 3600,
        }
        self.mock_session.post.return_value = mock_response

        oauth = TwitchOAuth(
            config=self.mock_config,
            state_store=self.state_store,
            logger=self.mock_logger,
            http_session=self.mock_session,
        )

        oauth.refresh_access_token()

        # Verify client_secret was NOT sent
        call_args = self.mock_session.post.call_args
        sent_data = call_args.kwargs.get("data", {})

        self.assertNotIn("client_secret", sent_data)
        self.assertEqual(sent_data["client_id"], "test_client_id")

    def test_refresh_non_dcf_includes_client_secret(self) -> None:
        """Non-DCF tokens should include client_secret in refresh request."""
        # Store tokens without auth method (defaults to non-DCF)
        self.state_store.store_token(TwitchOAuth.TOKEN_KEY_REFRESH, "regular_refresh")
        # No TOKEN_KEY_AUTH_METHOD set

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "access_token": "new_access",
            "expires_in": 3600,
        }
        self.mock_session.post.return_value = mock_response

        oauth = TwitchOAuth(
            config=self.mock_config,
            state_store=self.state_store,
            logger=self.mock_logger,
            http_session=self.mock_session,
        )

        oauth.refresh_access_token()

        # Verify client_secret WAS sent
        call_args = self.mock_session.post.call_args
        sent_data = call_args.kwargs.get("data", {})

        self.assertEqual(sent_data["client_secret"], "test_client_secret")

    def test_refresh_non_dcf_omits_placeholder_client_secret(self) -> None:
        """Placeholder client_secret should not be sent in refresh payload."""
        self.mock_config.client_secret = "YOUR_TWITCH_CLIENT_SECRET"
        self.state_store.store_token(TwitchOAuth.TOKEN_KEY_REFRESH, "regular_refresh")

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "access_token": "new_access",
            "expires_in": 3600,
        }
        self.mock_session.post.return_value = mock_response

        oauth = TwitchOAuth(
            config=self.mock_config,
            state_store=self.state_store,
            logger=self.mock_logger,
            http_session=self.mock_session,
        )

        oauth.refresh_access_token()

        call_args = self.mock_session.post.call_args
        sent_data = call_args.kwargs.get("data", {})
        self.assertNotIn("client_secret", sent_data)

    def test_refresh_401_clears_all_tokens(self) -> None:
        """Refresh 401 should clear all stored tokens."""
        from twitch_marker_agent.core.twitch_oauth import TokenRefreshError
        from twitch_marker_agent.tray_controller import TOKEN_KEY_AUTH_METHOD

        # Store tokens
        self.state_store.store_token(TwitchOAuth.TOKEN_KEY_ACCESS, "old_access")
        self.state_store.store_token(TwitchOAuth.TOKEN_KEY_REFRESH, "old_refresh")
        self.state_store.store_token(TwitchOAuth.TOKEN_KEY_EXPIRES, "2024-01-01T00:00:00+00:00")
        self.state_store.store_token(TOKEN_KEY_AUTH_METHOD, "dcf")

        mock_response = MagicMock()
        mock_response.status_code = 401
        self.mock_session.post.return_value = mock_response

        oauth = TwitchOAuth(
            config=self.mock_config,
            state_store=self.state_store,
            logger=self.mock_logger,
            http_session=self.mock_session,
        )

        with self.assertRaises(TokenRefreshError):
            oauth.refresh_access_token()

        # Verify all tokens are cleared
        self.assertIsNone(self.state_store.get_token(TwitchOAuth.TOKEN_KEY_ACCESS))
        self.assertIsNone(self.state_store.get_token(TwitchOAuth.TOKEN_KEY_REFRESH))
        self.assertIsNone(self.state_store.get_token(TwitchOAuth.TOKEN_KEY_EXPIRES))
        self.assertIsNone(self.state_store.get_token(TOKEN_KEY_AUTH_METHOD))


class TestValidateAccessToken(unittest.TestCase):
    """Tests for validate_access_token method."""

    def setUp(self) -> None:
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = Path(self.temp_dir) / "test_state.db"
        self.state_store = StateStore(self.db_path)

        self.mock_config = MagicMock()
        self.mock_logger = MagicMock()
        self.mock_session = MagicMock()

    def tearDown(self) -> None:
        """Clean up test fixtures."""
        import shutil
        self.state_store.close()
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_validate_200_returns_dict(self) -> None:
        """Validate 200 should return parsed JSON dict."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "client_id": "test_client",
            "login": "testuser",
            "user_id": "12345",
            "expires_in": 3600,
        }
        self.mock_session.get.return_value = mock_response

        oauth = TwitchOAuth(
            config=self.mock_config,
            state_store=self.state_store,
            logger=self.mock_logger,
            http_session=self.mock_session,
        )

        result = oauth.validate_access_token("some_token")

        self.assertIsInstance(result, dict)
        self.assertEqual(result["login"], "testuser")
        self.assertEqual(result["expires_in"], 3600)

    def test_validate_401_returns_none(self) -> None:
        """Validate 401 should return None (no exception)."""
        mock_response = MagicMock()
        mock_response.status_code = 401
        self.mock_session.get.return_value = mock_response

        oauth = TwitchOAuth(
            config=self.mock_config,
            state_store=self.state_store,
            logger=self.mock_logger,
            http_session=self.mock_session,
        )

        result = oauth.validate_access_token("invalid_token")

        self.assertIsNone(result)

    def test_validate_uses_oauth_header(self) -> None:
        """Validate should use OAuth authorization header."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {}
        self.mock_session.get.return_value = mock_response

        oauth = TwitchOAuth(
            config=self.mock_config,
            state_store=self.state_store,
            logger=self.mock_logger,
            http_session=self.mock_session,
        )

        oauth.validate_access_token("my_token")

        call_args = self.mock_session.get.call_args
        headers = call_args.kwargs.get("headers", {})
        self.assertEqual(headers.get("Authorization"), "OAuth my_token")


class TestGetValidUserAccessToken(unittest.TestCase):
    """Tests for get_valid_user_access_token method."""

    def setUp(self) -> None:
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = Path(self.temp_dir) / "test_state.db"
        self.state_store = StateStore(self.db_path)

        self.mock_config = MagicMock()
        self.mock_config.client_id = "test_client_id"
        self.mock_config.client_secret = "test_client_secret"

        self.mock_logger = MagicMock()
        self.mock_session = MagicMock()

    def tearDown(self) -> None:
        """Clean up test fixtures."""
        import shutil
        self.state_store.close()
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_returns_cached_when_fresh(self) -> None:
        """Should return cached token when TTL > min_ttl_seconds."""
        from datetime import timedelta

        # Store token with expiry far in future
        future = datetime.now(timezone.utc) + timedelta(hours=2)
        self.state_store.store_token(TwitchOAuth.TOKEN_KEY_ACCESS, "cached_token")
        self.state_store.store_token(TwitchOAuth.TOKEN_KEY_EXPIRES, future.isoformat())

        oauth = TwitchOAuth(
            config=self.mock_config,
            state_store=self.state_store,
            logger=self.mock_logger,
            http_session=self.mock_session,
        )

        result = oauth.get_valid_user_access_token(min_ttl_seconds=300)

        # Should return cached, no HTTP call
        self.assertEqual(result, "cached_token")
        self.mock_session.post.assert_not_called()

    def test_refreshes_when_near_expiry(self) -> None:
        """Should refresh when TTL <= min_ttl_seconds."""
        from datetime import timedelta

        # Store token expiring in 60 seconds (less than default 300)
        near_expiry = datetime.now(timezone.utc) + timedelta(seconds=60)
        self.state_store.store_token(TwitchOAuth.TOKEN_KEY_ACCESS, "old_token")
        self.state_store.store_token(TwitchOAuth.TOKEN_KEY_REFRESH, "refresh_token")
        self.state_store.store_token(TwitchOAuth.TOKEN_KEY_EXPIRES, near_expiry.isoformat())

        # Mock refresh response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "access_token": "refreshed_token",
            "expires_in": 3600,
        }
        self.mock_session.post.return_value = mock_response

        oauth = TwitchOAuth(
            config=self.mock_config,
            state_store=self.state_store,
            logger=self.mock_logger,
            http_session=self.mock_session,
        )

        result = oauth.get_valid_user_access_token(min_ttl_seconds=300)

        self.assertEqual(result, "refreshed_token")
        self.mock_session.post.assert_called_once()

    def test_refreshes_when_expired(self) -> None:
        """Should refresh when token is expired."""
        from datetime import timedelta

        # Store expired token
        past = datetime.now(timezone.utc) - timedelta(hours=1)
        self.state_store.store_token(TwitchOAuth.TOKEN_KEY_ACCESS, "expired_token")
        self.state_store.store_token(TwitchOAuth.TOKEN_KEY_REFRESH, "refresh_token")
        self.state_store.store_token(TwitchOAuth.TOKEN_KEY_EXPIRES, past.isoformat())

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "access_token": "new_token",
            "expires_in": 3600,
        }
        self.mock_session.post.return_value = mock_response

        oauth = TwitchOAuth(
            config=self.mock_config,
            state_store=self.state_store,
            logger=self.mock_logger,
            http_session=self.mock_session,
        )

        result = oauth.get_valid_user_access_token()

        self.assertEqual(result, "new_token")
        self.mock_session.post.assert_called_once()

    def test_refreshes_when_expires_at_missing(self) -> None:
        """Should refresh when expires_at is not stored."""
        # Store token without expiry
        self.state_store.store_token(TwitchOAuth.TOKEN_KEY_ACCESS, "old_token")
        self.state_store.store_token(TwitchOAuth.TOKEN_KEY_REFRESH, "refresh_token")
        # No expires_at stored

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "access_token": "new_token",
            "expires_in": 3600,
        }
        self.mock_session.post.return_value = mock_response

        oauth = TwitchOAuth(
            config=self.mock_config,
            state_store=self.state_store,
            logger=self.mock_logger,
            http_session=self.mock_session,
        )

        result = oauth.get_valid_user_access_token()

        self.assertEqual(result, "new_token")

    def test_refreshes_when_expires_at_invalid(self) -> None:
        """Should refresh when expires_at is invalid format."""
        # Store token with invalid expiry
        self.state_store.store_token(TwitchOAuth.TOKEN_KEY_ACCESS, "old_token")
        self.state_store.store_token(TwitchOAuth.TOKEN_KEY_REFRESH, "refresh_token")
        self.state_store.store_token(TwitchOAuth.TOKEN_KEY_EXPIRES, "not-a-date")

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "access_token": "new_token",
            "expires_in": 3600,
        }
        self.mock_session.post.return_value = mock_response

        oauth = TwitchOAuth(
            config=self.mock_config,
            state_store=self.state_store,
            logger=self.mock_logger,
            http_session=self.mock_session,
        )

        # Should not crash, should refresh
        result = oauth.get_valid_user_access_token()

        self.assertEqual(result, "new_token")

    def test_raises_when_not_authenticated(self) -> None:
        """Should raise with auth-login message when no access token."""
        from twitch_marker_agent.core.twitch_oauth import TokenRefreshError

        # No tokens stored

        oauth = TwitchOAuth(
            config=self.mock_config,
            state_store=self.state_store,
            logger=self.mock_logger,
            http_session=self.mock_session,
        )

        with self.assertRaises(TokenRefreshError) as ctx:
            oauth.get_valid_user_access_token()

        self.assertIn("auth-login", str(ctx.exception))

    def test_raises_when_no_refresh_token_and_refresh_needed(self) -> None:
        """Should raise when refresh is needed but no refresh token exists."""
        from datetime import timedelta
        from twitch_marker_agent.core.twitch_oauth import TokenRefreshError

        # Expired token but no refresh token
        past = datetime.now(timezone.utc) - timedelta(hours=1)
        self.state_store.store_token(TwitchOAuth.TOKEN_KEY_ACCESS, "expired_token")
        self.state_store.store_token(TwitchOAuth.TOKEN_KEY_EXPIRES, past.isoformat())
        # No refresh token stored

        oauth = TwitchOAuth(
            config=self.mock_config,
            state_store=self.state_store,
            logger=self.mock_logger,
            http_session=self.mock_session,
        )

        with self.assertRaises(TokenRefreshError) as ctx:
            oauth.get_valid_user_access_token()

        self.assertIn("auth-login", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
