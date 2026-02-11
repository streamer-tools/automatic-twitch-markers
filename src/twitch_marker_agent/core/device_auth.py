"""
Device Code Flow authentication for Twitch Marker Agent.

Provides OAuth Device Code Grant Flow for public clients (no client_secret required).
This is the preferred auth method for desktop applications.

Key characteristics of DCF:
- No client_secret needed for token exchange or refresh
- Single-use refresh tokens (rotation on each refresh)
- 30-day refresh token expiry on inactivity
- User must authorize via browser

References:
- https://dev.twitch.tv/docs/authentication/getting-tokens-oauth/#device-code-grant-flow
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import requests

if TYPE_CHECKING:
    pass

# OAuth endpoints
TWITCH_DEVICE_URL = "https://id.twitch.tv/oauth2/device"
TWITCH_TOKEN_URL = "https://id.twitch.tv/oauth2/token"
DCF_GRANT_TYPE = "urn:ietf:params:oauth:grant-type:device_code"

# HTTP timeouts (connect, read) in seconds
HTTP_TIMEOUT = (10, 30)

# Default scopes for marker access
DEFAULT_SCOPES = ["channel:manage:broadcast"]


# =============================================================================
# Exceptions
# =============================================================================


class DeviceAuthError(Exception):
    """Base exception for device auth errors."""

    pass


class DeviceCodeExpiredError(DeviceAuthError):
    """User did not complete auth in time."""

    pass


class DeviceAuthDeniedError(DeviceAuthError):
    """User explicitly denied authorization."""

    pass


class DeviceAuthCancelledError(DeviceAuthError):
    """Auth flow was cancelled by the application."""

    pass


# =============================================================================
# Data Classes
# =============================================================================


@dataclass(frozen=True)
class DeviceCodeResponse:
    """Response from device code request."""

    device_code: str  # Secret code for polling (don't log this)
    user_code: str  # User-facing code to display
    verification_uri: str  # URL for user to visit
    verification_uri_complete: str | None  # URL with pre-filled code (if provided)
    expires_in: int  # Seconds until device_code expires
    interval: int  # Polling interval in seconds


@dataclass
class TokenResponse:
    """Successful token response."""

    access_token: str
    refresh_token: str
    expires_in: int
    scope: list[str] = field(default_factory=list)


# =============================================================================
# Core Functions
# =============================================================================


def request_device_code(
    client_id: str,
    scopes: list[str],
    http_client: requests.Session,
    logger: logging.Logger,
) -> DeviceCodeResponse:
    """
    Request a device code from Twitch.

    Makes POST to https://id.twitch.tv/oauth2/device with:
    - client_id
    - scopes (space-delimited)

    Args:
        client_id: Twitch application client ID.
        scopes: List of OAuth scopes to request.
        http_client: HTTP session for requests.
        logger: Logger instance.

    Returns:
        DeviceCodeResponse with user_code, verification_uri, etc.

    Raises:
        DeviceAuthError: On network or API errors.
    """
    logger.info("Requesting device code for OAuth Device Code Flow")

    data = {
        "client_id": client_id,
        "scopes": " ".join(scopes),
    }

    try:
        response = http_client.post(
            TWITCH_DEVICE_URL,
            data=data,
            timeout=HTTP_TIMEOUT,
        )
    except requests.RequestException as e:
        logger.error("Device code request failed: %s", type(e).__name__)
        raise DeviceAuthError(f"Network error requesting device code: {e}") from e

    if response.status_code != 200:
        # Try to get error details without logging sensitive data
        try:
            error_data = response.json()
            error = error_data.get("error", "unknown")
            error_desc = error_data.get("message", error_data.get("error_description", ""))
            logger.error("Device code request failed: %s - %s", error, error_desc)
        except Exception:
            logger.error("Device code request failed: HTTP %d", response.status_code)

        raise DeviceAuthError(
            f"Device code request failed with HTTP {response.status_code}"
        )

    # Parse response
    try:
        resp_data = response.json()
    except Exception as e:
        logger.error("Failed to parse device code response")
        raise DeviceAuthError("Invalid JSON in device code response") from e

    # Extract required fields
    device_code = resp_data.get("device_code")
    user_code = resp_data.get("user_code")
    verification_uri = resp_data.get("verification_uri")
    verification_uri_complete = resp_data.get("verification_uri_complete")  # Optional
    expires_in = resp_data.get("expires_in", 1800)
    interval = resp_data.get("interval", 5)

    if not device_code or not user_code or not verification_uri:
        logger.error("Device code response missing required fields")
        raise DeviceAuthError("Device code response missing required fields")

    logger.info("Device code received, expires in %d seconds", expires_in)
    # Note: Do NOT log verification_uri_complete as it contains the device_code
    logger.debug("User code: %s, Verification URI: %s", user_code, verification_uri)

    return DeviceCodeResponse(
        device_code=device_code,
        user_code=user_code,
        verification_uri=verification_uri,
        verification_uri_complete=verification_uri_complete,
        expires_in=expires_in,
        interval=interval,
    )


def poll_for_device_token(
    client_id: str,
    device_code: str,
    scopes: list[str],
    interval: int,
    timeout_seconds: int,
    http_client: requests.Session,
    logger: logging.Logger,
    cancel_event: threading.Event | None = None,
) -> TokenResponse:
    """
    Poll for device token until user authorizes or timeout.

    Handles standard DCF statuses:
    - authorization_pending: continue polling
    - slow_down: increase interval by 5 seconds
    - expired_token: raise DeviceCodeExpiredError
    - access_denied: raise DeviceAuthDeniedError

    Args:
        client_id: Twitch application client ID.
        device_code: Device code from request_device_code.
        scopes: List of OAuth scopes (for request).
        interval: Initial polling interval in seconds.
        timeout_seconds: Maximum time to poll before giving up.
        http_client: HTTP session for requests.
        logger: Logger instance.
        cancel_event: Optional event to signal cancellation.

    Returns:
        TokenResponse with tokens on success.

    Raises:
        DeviceCodeExpiredError: Device code expired.
        DeviceAuthDeniedError: User denied auth.
        DeviceAuthCancelledError: Cancelled via cancel_event.
        DeviceAuthError: Network or parse errors.
    """
    logger.info("Starting device token polling (timeout: %ds)", timeout_seconds)

    current_interval = interval
    start_time = time.monotonic()
    elapsed = 0.0

    while elapsed < timeout_seconds:
        # Check for cancellation
        if cancel_event is not None and cancel_event.is_set():
            logger.info("Device auth polling cancelled by user")
            raise DeviceAuthCancelledError("Authentication cancelled by user")

        # Wait for interval (check cancel_event periodically)
        wait_start = time.monotonic()
        while time.monotonic() - wait_start < current_interval:
            if cancel_event is not None and cancel_event.is_set():
                logger.info("Device auth polling cancelled by user")
                raise DeviceAuthCancelledError("Authentication cancelled by user")
            time.sleep(0.5)

        # Make token request
        data = {
            "client_id": client_id,
            "scopes": " ".join(scopes),
            "device_code": device_code,
            "grant_type": DCF_GRANT_TYPE,
        }

        try:
            response = http_client.post(
                TWITCH_TOKEN_URL,
                data=data,
                timeout=HTTP_TIMEOUT,
            )
        except requests.RequestException as e:
            logger.error("Token poll request failed: %s", type(e).__name__)
            raise DeviceAuthError(f"Network error polling for token: {e}") from e

        # Handle response
        if response.status_code == 200:
            # Success!
            try:
                token_data = response.json()
            except Exception as e:
                logger.error("Failed to parse token response")
                raise DeviceAuthError("Invalid JSON in token response") from e

            access_token = token_data.get("access_token")
            refresh_token = token_data.get("refresh_token")
            expires_in = token_data.get("expires_in", 0)
            scope = token_data.get("scope", [])

            if not access_token:
                logger.error("Token response missing access_token")
                raise DeviceAuthError("Token response missing access_token")

            logger.info("Device code authorization successful")
            return TokenResponse(
                access_token=access_token,
                refresh_token=refresh_token or "",
                expires_in=expires_in,
                scope=scope if isinstance(scope, list) else [scope],
            )

        # Handle error responses
        if response.status_code == 400:
            try:
                error_data = response.json()
                message = error_data.get("message", "")
            except Exception:
                message = ""

            if message == "authorization_pending":
                logger.debug("Authorization pending, continuing to poll...")
                elapsed = time.monotonic() - start_time
                continue

            if message == "slow_down":
                current_interval += 5
                logger.debug("Slow down requested, new interval: %ds", current_interval)
                elapsed = time.monotonic() - start_time
                continue

            if message == "expired_token":
                logger.warning("Device code expired")
                raise DeviceCodeExpiredError(
                    "Device code expired. Please try authenticating again."
                )

            if message == "access_denied":
                logger.warning("User denied authorization")
                raise DeviceAuthDeniedError(
                    "Authorization was denied. Please try again and accept the permissions."
                )

            # Unknown error
            logger.error("Token poll failed: %s", message)
            raise DeviceAuthError(f"Token request failed: {message}")

        # Other HTTP errors
        logger.error("Token poll failed: HTTP %d", response.status_code)
        raise DeviceAuthError(
            f"Token request failed with HTTP {response.status_code}"
        )

    # Timeout
    logger.warning("Device code polling timed out after %ds", timeout_seconds)
    raise DeviceCodeExpiredError(
        f"Authentication timed out after {timeout_seconds} seconds. Please try again."
    )
