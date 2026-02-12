"""
Tests for authenticated broadcaster identity helpers.
"""

from __future__ import annotations

import logging
import unittest
from unittest.mock import MagicMock

from twitch_marker_agent.core.auth_identity import (
    BROADCASTER_ID_STATE_KEY,
    BROADCASTER_LOGIN_STATE_KEY,
    BROADCASTER_NAME_STATE_KEY,
    BroadcasterIdentity,
    BroadcasterIdentityError,
    fetch_authenticated_user,
    persist_broadcaster_identity,
    resolve_broadcaster_id,
)


class TestFetchAuthenticatedUser(unittest.TestCase):
    """Tests for fetch_authenticated_user()."""

    def setUp(self) -> None:
        self.http_client = MagicMock()
        self.logger = MagicMock(spec=logging.Logger)

    def test_success_returns_identity(self) -> None:
        """Should parse id/login/display_name from Helix users response."""
        response = MagicMock()
        response.status_code = 200
        response.json.return_value = {
            "data": [
                {
                    "id": "12345",
                    "login": "streamer_login",
                    "display_name": "StreamerName",
                }
            ]
        }
        self.http_client.get.return_value = response

        identity = fetch_authenticated_user(
            http_client=self.http_client,
            client_id="client_id",
            access_token="token",
            logger=self.logger,
        )

        self.assertEqual(identity.user_id, "12345")
        self.assertEqual(identity.login, "streamer_login")
        self.assertEqual(identity.display_name, "StreamerName")

    def test_non_200_raises(self) -> None:
        """Should raise BroadcasterIdentityError on HTTP failure."""
        response = MagicMock()
        response.status_code = 401
        response.json.return_value = {"error": "Unauthorized"}
        self.http_client.get.return_value = response

        with self.assertRaises(BroadcasterIdentityError):
            fetch_authenticated_user(
                http_client=self.http_client,
                client_id="client_id",
                access_token="token",
                logger=self.logger,
            )


class TestPersistBroadcasterIdentity(unittest.TestCase):
    """Tests for persist_broadcaster_identity()."""

    def test_persists_all_identity_fields(self) -> None:
        """Should store id/login/display name using state keys."""
        state_store = MagicMock()
        identity = BroadcasterIdentity(
            user_id="12345",
            login="streamer_login",
            display_name="StreamerName",
        )

        persist_broadcaster_identity(state_store, identity)

        calls = state_store.set_state.call_args_list
        keys = [call.args[0] for call in calls]
        self.assertIn(BROADCASTER_ID_STATE_KEY, keys)
        self.assertIn(BROADCASTER_LOGIN_STATE_KEY, keys)
        self.assertIn(BROADCASTER_NAME_STATE_KEY, keys)


class TestResolveBroadcasterId(unittest.TestCase):
    """Tests for resolve_broadcaster_id()."""

    def test_uses_state_store_first(self) -> None:
        """Should prefer broadcaster ID persisted in state store."""
        config = MagicMock()
        config.broadcaster_id = "99999"
        state_store = MagicMock()
        state_store.get_state.return_value = "12345"

        result = resolve_broadcaster_id(config, state_store)

        self.assertEqual(result, "12345")

    def test_falls_back_to_config(self) -> None:
        """Should use config broadcaster_id when state value missing."""
        config = MagicMock()
        config.broadcaster_id = "88888"
        state_store = MagicMock()
        state_store.get_state.return_value = None

        result = resolve_broadcaster_id(config, state_store)

        self.assertEqual(result, "88888")

    def test_returns_none_when_unset(self) -> None:
        """Should return None when no broadcaster id is available."""
        config = MagicMock()
        config.broadcaster_id = ""
        state_store = MagicMock()
        state_store.get_state.return_value = ""

        result = resolve_broadcaster_id(config, state_store)

        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()

