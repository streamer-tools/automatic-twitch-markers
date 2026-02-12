"""
Authenticated user identity helpers for tray/device auth flows.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

import requests

if TYPE_CHECKING:
    from twitch_marker_agent.core.config import AppConfig
    from twitch_marker_agent.core.state_store import StateStore


HELIX_USERS_ENDPOINT = "https://api.twitch.tv/helix/users"
HTTP_TIMEOUT = (10, 30)

BROADCASTER_ID_STATE_KEY = "twitch_broadcaster_id"
BROADCASTER_LOGIN_STATE_KEY = "twitch_broadcaster_login"
BROADCASTER_NAME_STATE_KEY = "twitch_broadcaster_name"


class BroadcasterIdentityError(Exception):
    """Raised when authenticated broadcaster identity cannot be resolved."""

    pass


@dataclass(frozen=True)
class BroadcasterIdentity:
    """Authenticated broadcaster identity from Helix /users."""

    user_id: str
    login: str
    display_name: str


def fetch_authenticated_user(
    http_client: requests.Session,
    client_id: str,
    access_token: str,
    logger: logging.Logger,
) -> BroadcasterIdentity:
    """
    Fetch authenticated user identity via Helix Get Users.

    Args:
        http_client: Requests session.
        client_id: Twitch application client ID.
        access_token: Valid OAuth access token.
        logger: Logger instance.

    Returns:
        BroadcasterIdentity with id/login/display name.

    Raises:
        BroadcasterIdentityError: On HTTP or parse failures.
    """
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Client-Id": client_id,
    }

    try:
        response = http_client.get(
            HELIX_USERS_ENDPOINT,
            headers=headers,
            timeout=HTTP_TIMEOUT,
        )
    except requests.RequestException as e:
        logger.error("Failed to fetch authenticated user: %s", type(e).__name__)
        raise BroadcasterIdentityError("Failed to fetch authenticated user") from e

    if response.status_code != 200:
        logger.error("Authenticated user lookup failed: HTTP %d", response.status_code)
        raise BroadcasterIdentityError(
            f"Authenticated user lookup failed (HTTP {response.status_code})"
        )

    try:
        payload = response.json()
    except Exception as e:
        logger.error("Failed to parse authenticated user response")
        raise BroadcasterIdentityError("Invalid response from authenticated user lookup") from e

    users = payload.get("data") or []
    if not users:
        raise BroadcasterIdentityError("Authenticated user not found")

    user = users[0]
    user_id = str(user.get("id") or "").strip()
    login = str(user.get("login") or "").strip()
    display_name = str(user.get("display_name") or "").strip()

    if not user_id:
        raise BroadcasterIdentityError("Authenticated user response missing id")

    return BroadcasterIdentity(
        user_id=user_id,
        login=login,
        display_name=display_name or login,
    )


def persist_broadcaster_identity(
    state_store: "StateStore",
    identity: BroadcasterIdentity,
) -> None:
    """
    Persist broadcaster identity in state store.

    Args:
        state_store: State store instance.
        identity: Broadcaster identity to persist.
    """
    state_store.set_state(BROADCASTER_ID_STATE_KEY, identity.user_id)
    if identity.login:
        state_store.set_state(BROADCASTER_LOGIN_STATE_KEY, identity.login)
    if identity.display_name:
        state_store.set_state(BROADCASTER_NAME_STATE_KEY, identity.display_name)


def resolve_broadcaster_id(
    config: "AppConfig",
    state_store: "StateStore",
) -> str | None:
    """
    Resolve broadcaster ID from state store first, then config fallback.

    Args:
        config: App configuration.
        state_store: State store instance.

    Returns:
        Broadcaster ID string if available, else None.
    """
    state_value = state_store.get_state(BROADCASTER_ID_STATE_KEY)
    if isinstance(state_value, str):
        normalized = state_value.strip()
        if normalized:
            return normalized

    cfg_value = str(getattr(config, "broadcaster_id", "") or "").strip()
    return cfg_value or None
