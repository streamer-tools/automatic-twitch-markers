"""
Twitch OAuth authentication for Twitch Marker Agent.

Handles:
- One-time browser-based OAuth flow to obtain refresh token
- Token refresh to maintain valid access tokens
- Token storage via StateStore abstraction

Required OAuth scopes:
- user:read:broadcast (required for Get Stream Markers)
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from twitch_marker_agent.core.config import AppConfig
    from twitch_marker_agent.core.state_store import StateStore

# OAuth endpoints
TWITCH_AUTH_URL = "https://id.twitch.tv/oauth2/authorize"
TWITCH_TOKEN_URL = "https://id.twitch.tv/oauth2/token"
TWITCH_VALIDATE_URL = "https://id.twitch.tv/oauth2/validate"

# Required scopes for marker access
REQUIRED_SCOPES = ["user:read:broadcast"]


class TwitchOAuth:
    """
    Manages Twitch OAuth authentication flow and token lifecycle.

    Tokens are stored via the StateStore abstraction, allowing future
    migration to Windows Credential Manager without code changes.
    """

    # Token storage keys
    TOKEN_KEY_ACCESS = "twitch_access_token"
    TOKEN_KEY_REFRESH = "twitch_refresh_token"
    TOKEN_KEY_EXPIRES = "twitch_token_expires"

    def __init__(
        self,
        config: AppConfig,
        state_store: StateStore,
        logger: logging.Logger,
    ) -> None:
        """
        Initialize the OAuth manager.

        Args:
            config: Application configuration with client credentials.
            state_store: State store for token persistence.
            logger: Logger instance.
        """
        self._config = config
        self._state_store = state_store
        self._logger = logger

    def has_refresh_token(self) -> bool:
        """
        Check if a refresh token is stored.

        Returns:
            True if refresh token exists, False otherwise.
        """
        token = self._state_store.get_token(self.TOKEN_KEY_REFRESH)
        return token is not None

    def get_access_token(self) -> str:
        """
        Get a valid access token, refreshing if necessary.

        Returns:
            Valid access token string.

        Raises:
            NotImplementedError: Token retrieval not yet implemented.
        """
        # TODO: Implement token retrieval
        # 1. Check if cached access token is still valid
        # 2. If expired, use refresh token to get new access token
        # 3. Update stored tokens
        # 4. Return access token
        raise NotImplementedError("TODO: Implement get_access_token")

    def login_browser(self) -> str:
        """
        Initiate browser-based OAuth flow for user authorization.

        Opens the system browser to Twitch authorization page.
        Starts a local HTTP server to receive the callback.
        Exchanges authorization code for tokens.

        Returns:
            The obtained access token.

        Raises:
            NotImplementedError: Browser login not yet implemented.
        """
        # TODO: Implement browser OAuth flow
        # 1. Generate state parameter for CSRF protection
        # 2. Build authorization URL with scopes
        # 3. Open browser to authorization URL
        # 4. Start local HTTP server for redirect_uri
        # 5. Wait for callback with authorization code
        # 6. Exchange code for tokens
        # 7. Store tokens in state store
        # 8. Return access token
        raise NotImplementedError("TODO: Implement browser OAuth login flow")

    def refresh_token(self) -> str:
        """
        Refresh the access token using stored refresh token.

        Returns:
            New access token.

        Raises:
            NotImplementedError: Token refresh not yet implemented.
        """
        # TODO: Implement token refresh
        # 1. Get refresh token from state store
        # 2. POST to token endpoint with grant_type=refresh_token
        # 3. Update stored access token and refresh token
        # 4. Return new access token
        raise NotImplementedError("TODO: Implement token refresh")

    def validate_token(self, access_token: str) -> bool:
        """
        Validate an access token with Twitch.

        Args:
            access_token: Token to validate.

        Returns:
            True if token is valid, False otherwise.

        Raises:
            NotImplementedError: Token validation not yet implemented.
        """
        # TODO: Implement token validation
        # GET https://id.twitch.tv/oauth2/validate
        # Authorization: OAuth <access_token>
        raise NotImplementedError("TODO: Implement token validation")

    def revoke_token(self) -> None:
        """
        Revoke stored tokens and clear from state store.

        Raises:
            NotImplementedError: Token revocation not yet implemented.
        """
        # TODO: Implement token revocation
        # 1. POST to revoke endpoint
        # 2. Delete tokens from state store
        raise NotImplementedError("TODO: Implement token revocation")

    def get_authorization_url(self) -> str:
        """
        Build the Twitch authorization URL.

        Returns:
            Full authorization URL with query parameters.
        """
        import urllib.parse

        params = {
            "client_id": self._config.client_id,
            "redirect_uri": self._config.redirect_uri,
            "response_type": "code",
            "scope": " ".join(REQUIRED_SCOPES),
            # TODO: Add state parameter for CSRF protection
        }
        return f"{TWITCH_AUTH_URL}?{urllib.parse.urlencode(params)}"
