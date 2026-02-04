"""
Helix EventSub subscription management.

Provides functions to create, list, delete, and ensure EventSub subscriptions
via the Twitch Helix API.

API Reference:
https://dev.twitch.tv/docs/api/reference/#create-eventsub-subscription
https://dev.twitch.tv/docs/api/reference/#get-eventsub-subscriptions
https://dev.twitch.tv/docs/api/reference/#delete-eventsub-subscription
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import requests

# Helix API endpoints
HELIX_BASE_URL = "https://api.twitch.tv/helix"
EVENTSUB_SUBSCRIPTIONS_ENDPOINT = f"{HELIX_BASE_URL}/eventsub/subscriptions"

# HTTP timeouts (connect, read) in seconds
HTTP_TIMEOUT = (10, 30)


# =============================================================================
# Custom Exceptions
# =============================================================================


class SubscriptionError(Exception):
    """Base exception for subscription operations."""

    pass


class SubscriptionAuthError(SubscriptionError):
    """Raised when authentication fails (401)."""

    pass


class SubscriptionRateLimitError(SubscriptionError):
    """Raised when rate limited (429)."""

    pass


# =============================================================================
# Data Classes
# =============================================================================


@dataclass
class Subscription:
    """
    Represents an EventSub subscription.

    Attributes:
        id: Unique subscription identifier.
        status: Subscription status (enabled, webhook_callback_verification_pending, etc.).
        type: Subscription type (e.g., stream.offline).
        version: Subscription version.
        condition: Condition dict (e.g., {broadcaster_user_id: "123"}).
        transport_method: Transport method (websocket or webhook).
        transport_session_id: WebSocket session ID (None for webhook).
        created_at: ISO 8601 timestamp when subscription was created.
    """

    id: str
    status: str
    type: str
    version: str
    condition: dict[str, Any]
    transport_method: str
    transport_session_id: str | None
    created_at: str

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "id": self.id,
            "status": self.status,
            "type": self.type,
            "version": self.version,
            "condition": self.condition,
            "transport_method": self.transport_method,
            "transport_session_id": self.transport_session_id,
            "created_at": self.created_at,
        }


# =============================================================================
# Pure Helper Functions
# =============================================================================


def build_subscription_request(
    sub_type: str,
    version: str,
    condition: dict[str, Any],
    session_id: str,
) -> dict[str, Any]:
    """
    Build request body for EventSub subscription creation.

    Args:
        sub_type: Subscription type (e.g., "stream.offline").
        version: Subscription version (e.g., "1").
        condition: Condition dict (e.g., {"broadcaster_user_id": "123"}).
        session_id: WebSocket session ID from session_welcome.

    Returns:
        Request body dict for POST /eventsub/subscriptions.
    """
    return {
        "type": sub_type,
        "version": version,
        "condition": condition,
        "transport": {
            "method": "websocket",
            "session_id": session_id,
        },
    }


def parse_subscription_response(data: dict[str, Any]) -> Subscription:
    """
    Parse subscription data from Helix response.

    Handles condition as either dict or JSON-encoded string (robustness).

    Args:
        data: Single subscription object from Helix response.

    Returns:
        Subscription instance.
    """
    # Handle condition as dict or JSON string
    condition = data.get("condition", {})
    if isinstance(condition, str):
        try:
            condition = json.loads(condition)
        except json.JSONDecodeError:
            condition = {}

    # Extract transport fields
    transport = data.get("transport", {})
    transport_method = transport.get("method", "unknown")
    transport_session_id = transport.get("session_id")

    return Subscription(
        id=data.get("id", ""),
        status=data.get("status", "unknown"),
        type=data.get("type", ""),
        version=data.get("version", ""),
        condition=condition,
        transport_method=transport_method,
        transport_session_id=transport_session_id,
        created_at=data.get("created_at", ""),
    )


def _build_auth_headers(client_id: str, access_token: str) -> dict[str, str]:
    """Build authorization headers for Helix API calls."""
    return {
        "Authorization": f"Bearer {access_token}",
        "Client-Id": client_id,
        "Content-Type": "application/json",
    }


# =============================================================================
# Helix API Functions
# =============================================================================


def create_eventsub_subscription(
    http_client: "requests.Session",
    client_id: str,
    access_token: str,
    sub_type: str,
    version: str,
    condition: dict[str, Any],
    session_id: str,
    logger: logging.Logger,
) -> Subscription:
    """
    Create an EventSub subscription via Helix API.

    Args:
        http_client: Configured requests Session.
        client_id: Twitch application client ID.
        access_token: Valid user access token.
        sub_type: Subscription type (e.g., "stream.offline").
        version: Subscription version (e.g., "1").
        condition: Condition dict (e.g., {"broadcaster_user_id": "123"}).
        session_id: WebSocket session ID from session_welcome.
        logger: Logger instance.

    Returns:
        Created Subscription instance.

    Raises:
        SubscriptionAuthError: If token is invalid (401).
        SubscriptionRateLimitError: If rate limited (429).
        SubscriptionError: For other failures.
    """
    headers = _build_auth_headers(client_id, access_token)
    body = build_subscription_request(sub_type, version, condition, session_id)

    # Log without sensitive data
    logger.info(
        "Creating %s subscription for condition=%s",
        sub_type,
        condition,
    )

    try:
        response = http_client.post(
            EVENTSUB_SUBSCRIPTIONS_ENDPOINT,
            headers=headers,
            json=body,
            timeout=HTTP_TIMEOUT,
        )
    except Exception as e:
        logger.error("Network error creating subscription: %s", type(e).__name__)
        raise SubscriptionError(f"Network error: {type(e).__name__}") from e

    logger.debug("Create subscription response status: %d", response.status_code)

    # Handle error responses
    if response.status_code == 401:
        logger.error("Authentication failed (401)")
        raise SubscriptionAuthError(
            "Token invalid or expired. Run 'auth-login' to re-authenticate."
        )

    if response.status_code == 403:
        logger.error("Forbidden (403) - check token scopes")
        raise SubscriptionError("Forbidden - check token scopes for subscription type.")

    if response.status_code == 409:
        logger.warning("Subscription conflict (409) - duplicate exists")
        raise SubscriptionError(
            "Subscription conflict - duplicate subscription exists."
        )

    if response.status_code == 429:
        logger.warning("Rate limited (429)")
        raise SubscriptionRateLimitError("Rate limited. Try again later.")

    if response.status_code != 202:
        logger.error("Unexpected status code: %d", response.status_code)
        raise SubscriptionError(
            f"Failed to create subscription (HTTP {response.status_code})"
        )

    # Parse success response
    try:
        response_data = response.json()
        subscriptions = response_data.get("data", [])
        if not subscriptions:
            raise SubscriptionError("No subscription data in response")

        subscription = parse_subscription_response(subscriptions[0])
        logger.info(
            "Subscription created: id=%s... status=%s",
            subscription.id[:8] if len(subscription.id) >= 8 else subscription.id,
            subscription.status,
        )
        return subscription

    except (json.JSONDecodeError, KeyError, IndexError) as e:
        logger.error("Failed to parse subscription response: %s", type(e).__name__)
        raise SubscriptionError("Failed to parse subscription response") from e


def list_eventsub_subscriptions(
    http_client: "requests.Session",
    client_id: str,
    access_token: str,
    sub_type: str | None = None,
    user_id: str | None = None,
    status: str | None = None,
    logger: logging.Logger | None = None,
) -> list[Subscription]:
    """
    List EventSub subscriptions with optional filters.

    Note: Filters are mutually exclusive. Only ONE of sub_type, user_id, or status
    may be specified per request. Passing multiple will raise ValueError.

    Args:
        http_client: Configured requests Session.
        client_id: Twitch application client ID.
        access_token: Valid user access token.
        sub_type: Filter by subscription type (e.g., "stream.offline").
        user_id: Filter by user ID in condition.
        status: Filter by subscription status.
        logger: Optional logger instance.

    Returns:
        List of Subscription instances.

    Raises:
        ValueError: If multiple filters are specified.
        SubscriptionAuthError: If token is invalid (401).
        SubscriptionError: For other failures.
    """
    log = logger or logging.getLogger(__name__)

    # Enforce mutually exclusive filters
    filters_provided = sum(
        1 for f in [sub_type, user_id, status] if f is not None
    )
    if filters_provided > 1:
        raise ValueError(
            "Filters are mutually exclusive: only ONE of sub_type, user_id, "
            "or status may be specified per request."
        )

    headers = _build_auth_headers(client_id, access_token)

    # Build query params
    params: dict[str, str] = {}
    if sub_type:
        params["type"] = sub_type
    if user_id:
        params["user_id"] = user_id
    if status:
        params["status"] = status

    log.debug("Listing subscriptions with params: %s", list(params.keys()))

    try:
        response = http_client.get(
            EVENTSUB_SUBSCRIPTIONS_ENDPOINT,
            headers=headers,
            params=params,
            timeout=HTTP_TIMEOUT,
        )
    except Exception as e:
        log.error("Network error listing subscriptions: %s", type(e).__name__)
        raise SubscriptionError(f"Network error: {type(e).__name__}") from e

    log.debug("List subscriptions response status: %d", response.status_code)

    if response.status_code == 401:
        log.error("Authentication failed (401)")
        raise SubscriptionAuthError(
            "Token invalid or expired. Run 'auth-login' to re-authenticate."
        )

    if response.status_code != 200:
        log.error("Unexpected status code: %d", response.status_code)
        raise SubscriptionError(
            f"Failed to list subscriptions (HTTP {response.status_code})"
        )

    try:
        response_data = response.json()
        subscriptions_data = response_data.get("data", [])
        subscriptions = [
            parse_subscription_response(sub) for sub in subscriptions_data
        ]
        log.debug("Listed %d subscriptions", len(subscriptions))
        return subscriptions

    except (json.JSONDecodeError, KeyError) as e:
        log.error("Failed to parse subscription list: %s", type(e).__name__)
        raise SubscriptionError("Failed to parse subscription list") from e


def delete_eventsub_subscription(
    http_client: "requests.Session",
    client_id: str,
    access_token: str,
    subscription_id: str,
    logger: logging.Logger | None = None,
) -> None:
    """
    Delete an EventSub subscription by ID.

    Uses: DELETE /eventsub/subscriptions?id=<subscription_id>

    Args:
        http_client: Configured requests Session.
        client_id: Twitch application client ID.
        access_token: Valid user access token.
        subscription_id: Subscription ID to delete.
        logger: Optional logger instance.

    Raises:
        SubscriptionAuthError: If token is invalid (401).
        SubscriptionError: For other failures.
    """
    log = logger or logging.getLogger(__name__)

    headers = _build_auth_headers(client_id, access_token)

    log.info(
        "Deleting subscription: id=%s...",
        subscription_id[:8] if len(subscription_id) >= 8 else subscription_id,
    )

    try:
        response = http_client.delete(
            EVENTSUB_SUBSCRIPTIONS_ENDPOINT,
            headers=headers,
            params={"id": subscription_id},
            timeout=HTTP_TIMEOUT,
        )
    except Exception as e:
        log.error("Network error deleting subscription: %s", type(e).__name__)
        raise SubscriptionError(f"Network error: {type(e).__name__}") from e

    log.debug("Delete subscription response status: %d", response.status_code)

    if response.status_code == 401:
        log.error("Authentication failed (401)")
        raise SubscriptionAuthError(
            "Token invalid or expired. Run 'auth-login' to re-authenticate."
        )

    if response.status_code == 404:
        log.warning("Subscription not found (404), already deleted")
        return  # Idempotent - not an error

    if response.status_code != 204:
        log.error("Unexpected status code: %d", response.status_code)
        raise SubscriptionError(
            f"Failed to delete subscription (HTTP {response.status_code})"
        )

    log.debug("Subscription deleted successfully")


def ensure_stream_offline_subscription(
    http_client: "requests.Session",
    client_id: str,
    access_token: str,
    broadcaster_id: str,
    session_id: str,
    logger: logging.Logger,
) -> Subscription:
    """
    Ensure a stream.offline subscription exists for the broadcaster.

    This is the main entry point for subscription management. It:
    1. Lists existing stream.offline subscriptions
    2. Filters by broadcaster_id in condition (client-side)
    3. If a matching websocket subscription exists with same session_id, returns it
    4. Deletes any stale websocket subscriptions (different session_id)
    5. Creates a new subscription if none exists

    Important: This should be called immediately after EventSub connect() to
    ensure subscription is created within Twitch's timeout window.

    Args:
        http_client: Configured requests Session.
        client_id: Twitch application client ID.
        access_token: Valid user access token.
        broadcaster_id: Broadcaster user ID to subscribe to.
        session_id: Current WebSocket session ID from session_welcome.
        logger: Logger instance.

    Returns:
        The active Subscription instance.

    Raises:
        SubscriptionAuthError: If token is invalid.
        SubscriptionError: For other failures.
    """
    logger.info("Ensuring stream.offline subscription for broadcaster_id=%s", broadcaster_id)

    # Step 1: List existing stream.offline subscriptions
    # Use type filter only (filters are mutually exclusive)
    existing_subs = list_eventsub_subscriptions(
        http_client=http_client,
        client_id=client_id,
        access_token=access_token,
        sub_type="stream.offline",
        logger=logger,
    )

    # Step 2: Filter by broadcaster_id and websocket transport (client-side)
    broadcaster_subs = [
        sub
        for sub in existing_subs
        if sub.condition.get("broadcaster_user_id") == broadcaster_id
        and sub.transport_method == "websocket"
    ]

    logger.debug(
        "Found %d websocket subscriptions for broadcaster_id=%s",
        len(broadcaster_subs),
        broadcaster_id,
    )

    # Step 3: Check for matching active subscription
    for sub in broadcaster_subs:
        if sub.transport_session_id == session_id and sub.status == "enabled":
            logger.info(
                "Found existing active subscription: id=%s...",
                sub.id[:8] if len(sub.id) >= 8 else sub.id,
            )
            return sub

    # Step 4: Delete stale subscriptions (different session_id or not enabled)
    for sub in broadcaster_subs:
        logger.info(
            "Deleting stale subscription: id=%s... session=%s",
            sub.id[:8] if len(sub.id) >= 8 else sub.id,
            (sub.transport_session_id or "none")[:8],
        )
        delete_eventsub_subscription(
            http_client=http_client,
            client_id=client_id,
            access_token=access_token,
            subscription_id=sub.id,
            logger=logger,
        )

    # Step 5: Create new subscription
    logger.info("Creating new stream.offline subscription")
    return create_eventsub_subscription(
        http_client=http_client,
        client_id=client_id,
        access_token=access_token,
        sub_type="stream.offline",
        version="1",
        condition={"broadcaster_user_id": broadcaster_id},
        session_id=session_id,
        logger=logger,
    )
