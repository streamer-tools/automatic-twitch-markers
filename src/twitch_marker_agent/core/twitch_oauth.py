"""
Twitch OAuth authentication for Twitch Marker Agent.

Handles:
- Browser-based OAuth flow to obtain tokens
- Token refresh with concurrency safety (RLock)
- Token validation via Twitch API
- Expiry-aware token access
- Token storage via StateStore abstraction

Required OAuth scopes:
- channel:manage:broadcast (required for Get Stream Markers and future broadcast management)
"""

from __future__ import annotations

import logging
import secrets
import threading
import webbrowser
from datetime import datetime, timedelta, timezone
from functools import partial
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import TYPE_CHECKING, Any, Callable
from urllib.parse import parse_qs, urlencode, urlparse

import requests
import ipaddress
import socket

if TYPE_CHECKING:
    from twitch_marker_agent.core.config import AppConfig
    from twitch_marker_agent.core.state_store import StateStore

# OAuth endpoints
TWITCH_AUTH_URL = "https://id.twitch.tv/oauth2/authorize"
TWITCH_TOKEN_URL = "https://id.twitch.tv/oauth2/token"
TWITCH_VALIDATE_URL = "https://id.twitch.tv/oauth2/validate"

# Default scopes for marker access
DEFAULT_SCOPES = ["channel:manage:broadcast"]

# HTTP timeouts (connect, read) in seconds
HTTP_TIMEOUT = (10, 30)


# =============================================================================
# Custom Exceptions
# =============================================================================


class OAuthCancelledError(Exception):
    """Raised when OAuth flow is cancelled by user, state mismatch, or port in use."""

    pass


class OAuthTimeoutError(Exception):
    """Raised when OAuth callback is not received within timeout."""

    pass


class TokenExchangeError(Exception):
    """Raised when token exchange with Twitch fails."""

    pass


class TokenRefreshError(Exception):
    """Raised when token refresh fails."""

    pass


# =============================================================================
# Pure Helper Functions (Unit-testable without network/port)
# =============================================================================


def build_authorize_url(
    client_id: str,
    redirect_uri: str,
    scopes: list[str],
    state: str,
) -> str:
    """
    Build the Twitch authorization URL.

    Args:
        client_id: Twitch application client ID.
        redirect_uri: OAuth redirect URI (must match app settings).
        scopes: List of OAuth scopes to request.
        state: Random state parameter for CSRF protection.

    Returns:
        Full authorization URL with query parameters.
    """
    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": " ".join(scopes),
        "state": state,
    }
    return f"{TWITCH_AUTH_URL}?{urlencode(params)}"


def parse_redirect_uri(redirect_uri: str) -> tuple[str, int, str]:
    """
    Parse redirect URI to extract host, port, and path.

    Args:
        redirect_uri: Full redirect URI (e.g., http://localhost:3000/callback).

    Returns:
        Tuple of (host, port, path).

    Raises:
        ValueError: If URI cannot be parsed or port is missing.
    """
    parsed = urlparse(redirect_uri)
    host = parsed.hostname or "localhost"
    port = parsed.port
    path = parsed.path or "/"

    if port is None:
        # Default to 80 for http, 443 for https
        port = 443 if parsed.scheme == "https" else 80

    return (host, port, path)


def compute_expires_at(expires_in_seconds: int) -> str:
    """
    Compute expiration timestamp as UTC ISO8601 string.

    Args:
        expires_in_seconds: Seconds until token expires.

    Returns:
        Timezone-aware UTC ISO8601 timestamp string.
    """
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in_seconds)
    return expires_at.isoformat()


def validate_callback_params(
    params: dict[str, list[str]],
    expected_state: str,
) -> str:
    """
    Validate OAuth callback parameters and extract authorization code.

    Args:
        params: Parsed query parameters from callback URL.
        expected_state: The state value that was sent in authorize request.

    Returns:
        Authorization code on success.

    Raises:
        OAuthCancelledError: If error param present, state missing, or state mismatch.
    """
    # Check for error response
    if "error" in params:
        error = params["error"][0]
        error_desc = params.get("error_description", [""])[0]
        raise OAuthCancelledError(f"Authorization denied: {error} - {error_desc}")

    # Validate state
    received_state = params.get("state", [None])[0]
    if received_state is None:
        raise OAuthCancelledError("Missing state parameter in callback.")

    if received_state != expected_state:
        raise OAuthCancelledError(
            "State mismatch - possible CSRF attack. Please try again."
        )

    # Extract code
    code_list = params.get("code", [])
    if not code_list:
        raise OAuthCancelledError("Missing authorization code in callback.")

    return code_list[0]

def _resolve_loopback_bind(host: str, port: int) -> tuple[int, str]:
    """
    Resolve host to a loopback IP we can safely bind to.
    Returns (address_family, ip_string). Raises ValueError if host isn't loopback.
    """
    # If host is already an IP literal
    try:
        ip_obj = ipaddress.ip_address(host)
        if not ip_obj.is_loopback:
            raise ValueError("redirect_uri host must be loopback")
        family = socket.AF_INET6 if ip_obj.version == 6 else socket.AF_INET
        return family, str(ip_obj)
    except ValueError:
        # Not an IP literal; resolve via DNS/hosts file
        pass

    infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    # Use OS preference order (first loopback returned)
    for family, _socktype, _proto, _canon, sockaddr in infos:
        ip_str = sockaddr[0]
        try:
            ip_obj = ipaddress.ip_address(ip_str)
        except ValueError:
            continue
        if ip_obj.is_loopback:
            return family, ip_str

    raise ValueError("redirect_uri host did not resolve to a loopback address")


def _make_reusable_http_server(
    family: int,
    bind_ip: str,
    port: int,
    handler_class,
):
    # address_family MUST be set before binding; define a subclass dynamically.
    class _ReusableHTTPServer(HTTPServer):
        allow_reuse_address = True
        address_family = family

    return _ReusableHTTPServer((bind_ip, port), handler_class)



# =============================================================================
# Callback Server
# =============================================================================


class _ReusableHTTPServer(HTTPServer):
    """HTTPServer subclass with allow_reuse_address set before binding."""

    allow_reuse_address = True


def _create_callback_handler(
    expected_path: str,
    result_container: dict[str, Any],
    result_event: threading.Event,
    logger: logging.Logger,
) -> type[BaseHTTPRequestHandler]:
    """
    Create a callback handler class for the OAuth redirect.

    Args:
        expected_path: Expected URL path (e.g., /callback).
        result_container: Shared dict to store callback result.
        result_event: Event to signal when callback is received.
        logger: Logger instance.

    Returns:
        Handler class for HTTPServer.
    """

    class CallbackHandler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: Any) -> None:
            # Avoid logging the full request line (may contain code/state)
            logger.debug("Callback server request received")

        def do_GET(self) -> None:
            # Parse the request path
            parsed = urlparse(self.path)

            # Check if path matches expected
            if parsed.path != expected_path:
                self.send_response(404)
                self.end_headers()
                self.wfile.write(b"Not Found")
                return

            # Parse query parameters
            params = parse_qs(parsed.query)

            # Store result and signal
            result_container["params"] = params
            result_event.set()

            # Send success response
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            response_html = """
            <!DOCTYPE html>
            <html>
            <head><title>Authorization Complete</title></head>
            <body style="font-family: sans-serif; text-align: center; padding: 50px;">
                <h1>Authorization Received</h1>
                <p>You may close this window.</p>
            </body>
            </html>
            """
            self.wfile.write(response_html.encode("utf-8"))

    return CallbackHandler


# =============================================================================
# Main OAuth Client Class
# =============================================================================


class TwitchOAuth:
    """
    Manages Twitch OAuth authentication flow and token lifecycle.

    Tokens are stored via the StateStore abstraction, allowing future
    migration to Windows Credential Manager without code changes.
    """

    # Token storage keys (match spec exactly)
    TOKEN_KEY_ACCESS = "twitch_access_token"
    TOKEN_KEY_REFRESH = "twitch_refresh_token"
    TOKEN_KEY_EXPIRES = "twitch_token_expires_at"

    def __init__(
        self,
        config: AppConfig,
        state_store: StateStore,
        logger: logging.Logger,
        http_session: requests.Session | None = None,
        browser_opener: Callable[[str], bool] | None = None,
    ) -> None:
        """
        Initialize the OAuth manager.

        Args:
            config: Application configuration with client credentials.
            state_store: State store for token persistence.
            logger: Logger instance.
            http_session: Optional HTTP session for requests (DI for testing).
            browser_opener: Optional callable to open URLs (DI for testing).
        """
        self._config = config
        self._state_store = state_store
        self._logger = logger
        self._http_session = http_session or requests.Session()
        self._browser_opener = browser_opener or webbrowser.open
        # Phase C: RLock to prevent concurrent token refreshes
        # RLock allows re-entry (get_valid_user_access_token -> refresh_access_token)
        self._refresh_lock = threading.RLock()

    def has_refresh_token(self) -> bool:
        """
        Check if a refresh token is stored.

        Returns:
            True if a refresh token exists in the state store.
        """
        return self._state_store.get_token(self.TOKEN_KEY_REFRESH) is not None

    def get_authorization_url(self, scopes: list[str] | None = None) -> str:
        """
        Build authorization URL for browser-based OAuth flow.

        Args:
            scopes: OAuth scopes to request. Defaults to DEFAULT_SCOPES.

        Returns:
            Tuple of (authorization_url, state).
        """
        if scopes is None:
            scopes = DEFAULT_SCOPES

        self._current_state = secrets.token_urlsafe(32)
        return build_authorize_url(
            client_id=self._config.client_id,
            redirect_uri=self._config.redirect_uri,
            scopes=scopes,
            state=self._current_state,
        )

    def interactive_login(self, timeout_seconds: int = 120) -> None:
        """
        Perform interactive OAuth login via browser.

        Opens the authorization URL in the default browser, starts a local
        callback server, waits for the OAuth redirect, and exchanges the
        authorization code for tokens.

        Args:
            timeout_seconds: Maximum time to wait for callback (default: 120).

        Raises:
            OAuthCancelledError: If user cancels, state mismatch, or port in use.
            OAuthTimeoutError: If callback not received within timeout.
            TokenExchangeError: If token exchange fails.
        """
        redirect_uri = self._config.redirect_uri

        # Parse redirect URI to get server binding info
        host, port, path = parse_redirect_uri(redirect_uri)

        # Generate authorization URL with state
        auth_url = self.get_authorization_url()
        state = self._current_state

        self._logger.info("Starting OAuth login flow")
        self._logger.debug("Redirect URI: %s (port %d)", redirect_uri, port)

        # Shared state for callback handler
        result_container: dict[str, Any] = {}
        result_event = threading.Event()

        # Create handler class
        handler_class = _create_callback_handler(path, result_container, result_event, self._logger)

        # Start server
        server: _ReusableHTTPServer | None = None
        server_thread: threading.Thread | None = None

        try:
            family, bind_ip = _resolve_loopback_bind(host, port)
        except ValueError as e:
            raise OAuthCancelledError(
                f"redirect_uri host must resolve to a loopback address for local auth.\n"
                f"redirect_uri={redirect_uri!r} resolved host={host!r}\n"
                f"Please set redirect_uri to http://localhost:{port}{path} "
                f"or http://127.0.0.1:{port}{path} and try again."
            ) from e

        try:
            server = _make_reusable_http_server(family, bind_ip, port, handler_class)
        except OSError as e:
            raise OAuthCancelledError(
                f"Could not start callback server on {bind_ip}:{port} "
                f"(from redirect_uri={redirect_uri!r}).\n"
                f"Please close any application using port {port} "
                f"(e.g., another instance of this tool, Node.js server)\n"
                f"and try again. Alternatively, update redirect_uri in config.json "
                f"to use a different port."
            ) from e

        try:
            # Start server in background thread
            server_thread = threading.Thread(target=server.serve_forever)
            server_thread.daemon = True
            server_thread.start()

            self._logger.info("Started OAuth callback server on port %d", port)

            # Open browser
            self._logger.info("Opening browser for Twitch authorization...")
            try:
                browser_opened = self._browser_opener(auth_url)
                if not browser_opened:
                    raise RuntimeError("Browser open returned False")
            except Exception:
                self._logger.warning("Could not open browser automatically.")
                print(
                    f"\nPlease open this URL in your browser to authorize:\n\n{auth_url}\n"
                )

            # Wait for callback
            self._logger.info("Waiting for authorization callback (timeout: %ds)...", timeout_seconds)
            callback_received = result_event.wait(timeout=timeout_seconds)

            if not callback_received:
                raise OAuthTimeoutError(
                    f"OAuth login timed out after {timeout_seconds} seconds. Please try again."
                )

            # Validate callback and extract code
            params = result_container.get("params", {})
            code = validate_callback_params(params, state)

            self._logger.info("Authorization code received, exchanging for tokens...")

            # Exchange code for tokens
            self._exchange_code_for_tokens(code)

            self._logger.info("OAuth login successful. Tokens stored.")

        finally:
            # Always clean up server
            if server is not None:
                self._logger.debug("Shutting down callback server...")
                server.shutdown()
                if server_thread is not None:
                    server_thread.join(timeout=5)
                server.server_close()

    def _exchange_code_for_tokens(self, code: str) -> None:
        """
        Exchange authorization code for tokens.

        Args:
            code: Authorization code from callback.

        Raises:
            TokenExchangeError: If exchange fails.
        """
        data = {
            "client_id": self._config.client_id,
            "client_secret": self._config.client_secret,
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": self._config.redirect_uri,
        }

        try:
            response = self._http_session.post(
                TWITCH_TOKEN_URL,
                data=data,
                timeout=HTTP_TIMEOUT,
            )
        except requests.RequestException as e:
            self._logger.error("Token exchange request failed: %s", type(e).__name__)
            raise TokenExchangeError(f"Network error during token exchange: {e}") from e

        if response.status_code != 200:
            # Try to get error details without logging sensitive data
            try:
                error_data = response.json()
                error = error_data.get("error", "unknown")
                error_desc = error_data.get("error_description", "")
                self._logger.error("Token exchange failed: %s - %s", error, error_desc)
            except Exception:
                self._logger.error("Token exchange failed: HTTP %d", response.status_code)

            raise TokenExchangeError(
                f"Token exchange failed with HTTP {response.status_code}"
            )

        # Parse response
        try:
            token_data = response.json()
        except Exception as e:
            self._logger.error("Failed to parse token response")
            raise TokenExchangeError("Invalid JSON in token response") from e

        # Extract tokens
        access_token = token_data.get("access_token")
        refresh_token = token_data.get("refresh_token")
        expires_in = token_data.get("expires_in", 0)

        if not access_token:
            self._logger.error("Token exchange response missing access_token")
            raise TokenExchangeError("Token response missing access_token")

        # Store tokens
        self._state_store.store_token(self.TOKEN_KEY_ACCESS, access_token)

        # Only store refresh token if present (defensive)
        if refresh_token:
            self._state_store.store_token(self.TOKEN_KEY_REFRESH, refresh_token)

        # Compute and store expiry
        if expires_in > 0:
            expires_at = compute_expires_at(expires_in)
            self._state_store.store_token(self.TOKEN_KEY_EXPIRES, expires_at)

        self._logger.debug("Tokens stored successfully")

    # =========================================================================
    # Phase C: Token Maintenance Methods
    # =========================================================================

    def refresh_access_token(self) -> None:
        """
        Refresh the access token using the stored refresh token.

        Updates stored access_token and twitch_token_expires_at.
        If the response includes a new refresh_token, it is also stored.

        This method is concurrency-safe (uses RLock).

        Raises:
            TokenRefreshError: If no refresh token is stored or refresh fails.
        """
        with self._refresh_lock:
            self._refresh_access_token_unlocked()

    def _refresh_access_token_unlocked(self) -> None:
        """Internal refresh implementation (caller must hold lock)."""
        refresh_token = self._state_store.get_token(self.TOKEN_KEY_REFRESH)

        if not refresh_token:
            self._logger.error("Cannot refresh: no refresh token stored")
            raise TokenRefreshError(
                "No refresh token available. Run 'auth-login' to authenticate."
            )

        data = {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": self._config.client_id,
            "client_secret": self._config.client_secret,
        }

        try:
            response = self._http_session.post(
                TWITCH_TOKEN_URL,
                data=data,
                timeout=HTTP_TIMEOUT,
            )
        except requests.RequestException as e:
            self._logger.error("Token refresh request failed: %s", type(e).__name__)
            raise TokenRefreshError(f"Network error during token refresh: {e}") from e

        if response.status_code == 401:
            # Refresh token is invalid/expired - user must re-authenticate
            self._logger.error("Refresh token is invalid or expired")
            raise TokenRefreshError(
                "Refresh token is invalid or expired. Run 'auth-login' to re-authenticate."
            )

        if response.status_code != 200:
            # Other error - try to get safe details
            try:
                error_data = response.json()
                error = error_data.get("error", "unknown")
                error_desc = error_data.get("error_description", "")
                self._logger.error("Token refresh failed: %s - %s", error, error_desc)
            except Exception:
                self._logger.error("Token refresh failed: HTTP %d", response.status_code)

            raise TokenRefreshError(
                f"Token refresh failed with HTTP {response.status_code}"
            )

        # Parse response
        try:
            token_data = response.json()
        except Exception as e:
            self._logger.error("Failed to parse refresh response")
            raise TokenRefreshError("Invalid JSON in refresh response") from e

        # Extract tokens
        access_token = token_data.get("access_token")
        new_refresh_token = token_data.get("refresh_token")
        expires_in = token_data.get("expires_in", 0)

        if not access_token:
            self._logger.error("Refresh response missing access_token")
            raise TokenRefreshError("Refresh response missing access_token")

        # Store new access token
        self._state_store.store_token(self.TOKEN_KEY_ACCESS, access_token)

        # Only update refresh token if a new one is provided (rotation safety)
        if new_refresh_token:
            self._state_store.store_token(self.TOKEN_KEY_REFRESH, new_refresh_token)
            self._logger.debug("Refresh token rotated")

        # Update expiry
        if expires_in > 0:
            expires_at = compute_expires_at(expires_in)
            self._state_store.store_token(self.TOKEN_KEY_EXPIRES, expires_at)

        self._logger.info("Access token refreshed successfully")

    def validate_access_token(self, token: str) -> dict[str, Any] | None:
        """
        Validate an access token with Twitch.

        Args:
            token: The access token to validate.

        Returns:
            Validation response dict if valid (includes expires_in, login, user_id),
            or None if the token is invalid (HTTP 401).

        Raises:
            requests.RequestException: On network errors.
        """
        headers = {
            "Authorization": f"OAuth {token}",
        }

        try:
            response = self._http_session.get(
                TWITCH_VALIDATE_URL,
                headers=headers,
                timeout=HTTP_TIMEOUT,
            )
        except requests.RequestException as e:
            self._logger.error("Token validation request failed: %s", type(e).__name__)
            raise

        if response.status_code == 401:
            self._logger.debug("Token validation returned 401: token is invalid")
            return None

        if response.status_code != 200:
            self._logger.error("Token validation failed: HTTP %d", response.status_code)
            raise requests.RequestException(
                f"Token validation failed with HTTP {response.status_code}"
            )

        try:
            return response.json()
        except Exception as e:
            self._logger.error("Failed to parse validation response")
            raise requests.RequestException("Invalid JSON in validation response") from e

    def get_valid_user_access_token(self, min_ttl_seconds: int = 300) -> str:
        """
        Get a valid access token, refreshing if necessary.

        Uses stored expires_at to determine if refresh is needed, avoiding
        unnecessary network calls.

        Args:
            min_ttl_seconds: Minimum remaining TTL before triggering refresh.
                             Defaults to 300 (5 minutes).

        Returns:
            A valid access token string.

        Raises:
            TokenRefreshError: If not authenticated or refresh fails.
        """
        access_token = self._state_store.get_token(self.TOKEN_KEY_ACCESS)

        if not access_token:
            self._logger.error("No access token stored")
            raise TokenRefreshError(
                "Not authenticated. Run 'auth-login' to authenticate."
            )

        # Check if refresh is needed
        needs_refresh = False
        expires_at_str = self._state_store.get_token(self.TOKEN_KEY_EXPIRES)

        if not expires_at_str:
            # No expiry stored - refresh to be safe
            self._logger.debug("No expires_at stored, will refresh")
            needs_refresh = True
        else:
            # Parse expires_at with hardening for invalid/naive values
            try:
                expires_at = datetime.fromisoformat(expires_at_str)
                # Ensure timezone-aware (handle naive datetime)
                if expires_at.tzinfo is None:
                    self._logger.warning("Stored expires_at is naive, treating as expired")
                    needs_refresh = True
                else:
                    now = datetime.now(timezone.utc)
                    ttl = (expires_at - now).total_seconds()

                    if ttl <= 0:
                        self._logger.debug("Token expired, will refresh")
                        needs_refresh = True
                    elif ttl <= min_ttl_seconds:
                        self._logger.debug("Token near expiry (TTL: %.0fs), will refresh", ttl)
                        needs_refresh = True
            except (ValueError, TypeError) as e:
                # Invalid expires_at format - refresh to be safe
                self._logger.warning("Invalid expires_at format (%s), treating as expired", e)
                needs_refresh = True

        if not needs_refresh:
            return access_token

        # Refresh with lock to prevent concurrent refreshes
        with self._refresh_lock:
            # Double-check pattern: re-read after acquiring lock
            access_token = self._state_store.get_token(self.TOKEN_KEY_ACCESS)
            expires_at_str = self._state_store.get_token(self.TOKEN_KEY_EXPIRES)

            # Re-evaluate if still needs refresh (another thread may have refreshed)
            still_needs_refresh = False
            if not expires_at_str:
                still_needs_refresh = True
            else:
                try:
                    expires_at = datetime.fromisoformat(expires_at_str)
                    if expires_at.tzinfo is None:
                        still_needs_refresh = True
                    else:
                        now = datetime.now(timezone.utc)
                        ttl = (expires_at - now).total_seconds()
                        if ttl <= min_ttl_seconds:
                            still_needs_refresh = True
                except (ValueError, TypeError):
                    still_needs_refresh = True

            if still_needs_refresh:
                self.refresh_access_token()
                access_token = self._state_store.get_token(self.TOKEN_KEY_ACCESS)

        return access_token

    def revoke_token(self) -> None:
        """
        Revoke stored tokens and clear from state store.

            NotImplementedError: Token revocation not yet implemented.
        """
        raise NotImplementedError("TODO: Implement token revocation")
