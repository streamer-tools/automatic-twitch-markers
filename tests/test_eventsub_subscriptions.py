"""
Tests for EventSub subscription management.

Uses stdlib unittest + mocks only; no real network connections.
"""

from __future__ import annotations

import json
import logging
import unittest
from unittest.mock import MagicMock, patch

from twitch_marker_agent.core.eventsub_subscriptions import (
    EVENTSUB_SUBSCRIPTIONS_ENDPOINT,
    HTTP_TIMEOUT,
    Subscription,
    SubscriptionAuthError,
    SubscriptionError,
    SubscriptionRateLimitError,
    build_subscription_request,
    create_eventsub_subscription,
    delete_eventsub_subscription,
    ensure_stream_offline_subscription,
    list_eventsub_subscriptions,
    parse_subscription_response,
)


# =============================================================================
# Test Fixtures
# =============================================================================


def make_subscription_response(
    sub_id: str = "sub_123",
    status: str = "enabled",
    sub_type: str = "stream.offline",
    version: str = "1",
    broadcaster_id: str = "12345",
    transport_method: str = "websocket",
    session_id: str = "session_abc",
) -> dict:
    """Create a sample subscription response object."""
    return {
        "id": sub_id,
        "status": status,
        "type": sub_type,
        "version": version,
        "condition": {"broadcaster_user_id": broadcaster_id},
        "transport": {
            "method": transport_method,
            "session_id": session_id,
        },
        "created_at": "2026-02-04T00:00:00Z",
    }


def make_mock_response(status_code: int, json_data: dict | None = None) -> MagicMock:
    """Create a mock requests.Response."""
    response = MagicMock()
    response.status_code = status_code
    if json_data is not None:
        response.json.return_value = json_data
    return response


# =============================================================================
# Tests for Pure Helper Functions
# =============================================================================


class TestBuildSubscriptionRequest(unittest.TestCase):
    """Tests for build_subscription_request function."""

    def test_build_request_structure(self) -> None:
        """Request should have type, version, condition, and transport."""
        request = build_subscription_request(
            sub_type="stream.offline",
            version="1",
            condition={"broadcaster_user_id": "12345"},
            session_id="session_abc",
        )

        self.assertEqual(request["type"], "stream.offline")
        self.assertEqual(request["version"], "1")
        self.assertEqual(request["condition"], {"broadcaster_user_id": "12345"})
        self.assertEqual(request["transport"]["method"], "websocket")
        self.assertEqual(request["transport"]["session_id"], "session_abc")

    def test_build_request_preserves_condition(self) -> None:
        """Condition dict should be passed through unchanged."""
        condition = {"foo": "bar", "baz": 123}
        request = build_subscription_request(
            sub_type="test.type",
            version="2",
            condition=condition,
            session_id="sess_xyz",
        )

        self.assertEqual(request["condition"], condition)


class TestParseSubscriptionResponse(unittest.TestCase):
    """Tests for parse_subscription_response function."""

    def test_parse_condition_as_dict(self) -> None:
        """Condition as normal dict should be parsed correctly."""
        data = make_subscription_response(broadcaster_id="99999")
        sub = parse_subscription_response(data)

        self.assertEqual(sub.condition, {"broadcaster_user_id": "99999"})
        self.assertEqual(sub.id, "sub_123")
        self.assertEqual(sub.status, "enabled")
        self.assertEqual(sub.type, "stream.offline")
        self.assertEqual(sub.transport_method, "websocket")
        self.assertEqual(sub.transport_session_id, "session_abc")

    def test_parse_condition_as_json_string(self) -> None:
        """Condition as JSON-encoded string should be parsed correctly."""
        data = make_subscription_response()
        data["condition"] = '{"broadcaster_user_id": "67890"}'
        sub = parse_subscription_response(data)

        self.assertEqual(sub.condition, {"broadcaster_user_id": "67890"})

    def test_parse_invalid_json_string_condition(self) -> None:
        """Invalid JSON string condition should result in empty dict."""
        data = make_subscription_response()
        data["condition"] = "not valid json"
        sub = parse_subscription_response(data)

        self.assertEqual(sub.condition, {})

    def test_parse_missing_transport(self) -> None:
        """Missing transport should use defaults."""
        data = {"id": "sub_1", "status": "enabled", "type": "test"}
        sub = parse_subscription_response(data)

        self.assertEqual(sub.transport_method, "unknown")
        self.assertIsNone(sub.transport_session_id)


# =============================================================================
# Tests for create_eventsub_subscription
# =============================================================================


class TestCreateEventsubSubscription(unittest.TestCase):
    """Tests for create_eventsub_subscription function."""

    def setUp(self) -> None:
        """Set up test fixtures."""
        self.logger = MagicMock(spec=logging.Logger)
        self.http_client = MagicMock()
        self.client_id = "test_client_id"
        self.access_token = "test_token"

    def test_create_subscription_success(self) -> None:
        """202 response should return Subscription."""
        response_data = {
            "data": [make_subscription_response(sub_id="new_sub_456")]
        }
        self.http_client.post.return_value = make_mock_response(202, response_data)

        sub = create_eventsub_subscription(
            http_client=self.http_client,
            client_id=self.client_id,
            access_token=self.access_token,
            sub_type="stream.offline",
            version="1",
            condition={"broadcaster_user_id": "12345"},
            session_id="session_abc",
            logger=self.logger,
        )

        self.assertEqual(sub.id, "new_sub_456")
        self.assertEqual(sub.status, "enabled")
        self.http_client.post.assert_called_once()

        # Verify correct endpoint and headers
        call_kwargs = self.http_client.post.call_args.kwargs
        self.assertEqual(call_kwargs["timeout"], HTTP_TIMEOUT)
        self.assertIn("Authorization", call_kwargs["headers"])
        self.assertIn("Client-Id", call_kwargs["headers"])

    def test_create_subscription_401_raises_auth_error(self) -> None:
        """401 should raise SubscriptionAuthError with clear message."""
        self.http_client.post.return_value = make_mock_response(401)

        with self.assertRaises(SubscriptionAuthError) as ctx:
            create_eventsub_subscription(
                http_client=self.http_client,
                client_id=self.client_id,
                access_token=self.access_token,
                sub_type="stream.offline",
                version="1",
                condition={},
                session_id="session",
                logger=self.logger,
            )

        self.assertIn("auth-login", str(ctx.exception).lower())

    def test_create_subscription_403_forbidden(self) -> None:
        """403 should raise SubscriptionError."""
        self.http_client.post.return_value = make_mock_response(403)

        with self.assertRaises(SubscriptionError) as ctx:
            create_eventsub_subscription(
                http_client=self.http_client,
                client_id=self.client_id,
                access_token=self.access_token,
                sub_type="stream.offline",
                version="1",
                condition={},
                session_id="session",
                logger=self.logger,
            )

        self.assertIn("forbidden", str(ctx.exception).lower())

    def test_create_subscription_409_duplicate(self) -> None:
        """409 should raise SubscriptionError with conflict message."""
        self.http_client.post.return_value = make_mock_response(409)

        with self.assertRaises(SubscriptionError) as ctx:
            create_eventsub_subscription(
                http_client=self.http_client,
                client_id=self.client_id,
                access_token=self.access_token,
                sub_type="stream.offline",
                version="1",
                condition={},
                session_id="session",
                logger=self.logger,
            )

        self.assertIn("conflict", str(ctx.exception).lower())

    def test_create_subscription_429_rate_limit(self) -> None:
        """429 should raise SubscriptionRateLimitError."""
        self.http_client.post.return_value = make_mock_response(429)

        with self.assertRaises(SubscriptionRateLimitError):
            create_eventsub_subscription(
                http_client=self.http_client,
                client_id=self.client_id,
                access_token=self.access_token,
                sub_type="stream.offline",
                version="1",
                condition={},
                session_id="session",
                logger=self.logger,
            )

    def test_create_subscription_network_error(self) -> None:
        """Network error should raise SubscriptionError."""
        self.http_client.post.side_effect = ConnectionError("Network down")

        with self.assertRaises(SubscriptionError) as ctx:
            create_eventsub_subscription(
                http_client=self.http_client,
                client_id=self.client_id,
                access_token=self.access_token,
                sub_type="stream.offline",
                version="1",
                condition={},
                session_id="session",
                logger=self.logger,
            )

        self.assertIn("network", str(ctx.exception).lower())


# =============================================================================
# Tests for list_eventsub_subscriptions
# =============================================================================


class TestListEventsubSubscriptions(unittest.TestCase):
    """Tests for list_eventsub_subscriptions function."""

    def setUp(self) -> None:
        """Set up test fixtures."""
        self.logger = MagicMock(spec=logging.Logger)
        self.http_client = MagicMock()
        self.client_id = "test_client_id"
        self.access_token = "test_token"

    def test_list_subscriptions_success(self) -> None:
        """200 response should return list of Subscriptions."""
        response_data = {
            "data": [
                make_subscription_response(sub_id="sub_1"),
                make_subscription_response(sub_id="sub_2"),
            ]
        }
        self.http_client.get.return_value = make_mock_response(200, response_data)

        subs = list_eventsub_subscriptions(
            http_client=self.http_client,
            client_id=self.client_id,
            access_token=self.access_token,
            sub_type="stream.offline",
            logger=self.logger,
        )

        self.assertEqual(len(subs), 2)
        self.assertEqual(subs[0].id, "sub_1")
        self.assertEqual(subs[1].id, "sub_2")

    def test_list_subscriptions_with_type_filter(self) -> None:
        """Type filter should be passed as query param."""
        self.http_client.get.return_value = make_mock_response(200, {"data": []})

        list_eventsub_subscriptions(
            http_client=self.http_client,
            client_id=self.client_id,
            access_token=self.access_token,
            sub_type="stream.offline",
            logger=self.logger,
        )

        call_kwargs = self.http_client.get.call_args.kwargs
        self.assertEqual(call_kwargs["params"], {"type": "stream.offline"})

    def test_list_subscriptions_with_user_id_filter(self) -> None:
        """User ID filter should be passed as query param."""
        self.http_client.get.return_value = make_mock_response(200, {"data": []})

        list_eventsub_subscriptions(
            http_client=self.http_client,
            client_id=self.client_id,
            access_token=self.access_token,
            user_id="12345",
            logger=self.logger,
        )

        call_kwargs = self.http_client.get.call_args.kwargs
        self.assertEqual(call_kwargs["params"], {"user_id": "12345"})

    def test_list_subscriptions_rejects_multiple_filters(self) -> None:
        """ValueError should be raised if multiple filters are passed."""
        with self.assertRaises(ValueError) as ctx:
            list_eventsub_subscriptions(
                http_client=self.http_client,
                client_id=self.client_id,
                access_token=self.access_token,
                sub_type="stream.offline",
                user_id="12345",
                logger=self.logger,
            )

        self.assertIn("mutually exclusive", str(ctx.exception).lower())

    def test_list_subscriptions_401_raises_auth_error(self) -> None:
        """401 should raise SubscriptionAuthError."""
        self.http_client.get.return_value = make_mock_response(401)

        with self.assertRaises(SubscriptionAuthError):
            list_eventsub_subscriptions(
                http_client=self.http_client,
                client_id=self.client_id,
                access_token=self.access_token,
                logger=self.logger,
            )


# =============================================================================
# Tests for delete_eventsub_subscription
# =============================================================================


class TestDeleteEventsubSubscription(unittest.TestCase):
    """Tests for delete_eventsub_subscription function."""

    def setUp(self) -> None:
        """Set up test fixtures."""
        self.logger = MagicMock(spec=logging.Logger)
        self.http_client = MagicMock()
        self.client_id = "test_client_id"
        self.access_token = "test_token"

    def test_delete_subscription_success(self) -> None:
        """204 response should complete without error."""
        self.http_client.delete.return_value = make_mock_response(204)

        # Should not raise
        delete_eventsub_subscription(
            http_client=self.http_client,
            client_id=self.client_id,
            access_token=self.access_token,
            subscription_id="sub_to_delete",
            logger=self.logger,
        )

        # Verify correct endpoint and query param
        call_kwargs = self.http_client.delete.call_args.kwargs
        self.assertEqual(call_kwargs["params"], {"id": "sub_to_delete"})

    def test_delete_subscription_404_idempotent(self) -> None:
        """404 should not raise (idempotent delete)."""
        self.http_client.delete.return_value = make_mock_response(404)

        # Should not raise
        delete_eventsub_subscription(
            http_client=self.http_client,
            client_id=self.client_id,
            access_token=self.access_token,
            subscription_id="already_deleted",
            logger=self.logger,
        )

    def test_delete_subscription_401_raises_auth_error(self) -> None:
        """401 should raise SubscriptionAuthError."""
        self.http_client.delete.return_value = make_mock_response(401)

        with self.assertRaises(SubscriptionAuthError):
            delete_eventsub_subscription(
                http_client=self.http_client,
                client_id=self.client_id,
                access_token=self.access_token,
                subscription_id="sub_id",
                logger=self.logger,
            )


# =============================================================================
# Tests for ensure_stream_offline_subscription
# =============================================================================


class TestEnsureStreamOfflineSubscription(unittest.TestCase):
    """Tests for ensure_stream_offline_subscription function."""

    def setUp(self) -> None:
        """Set up test fixtures."""
        self.logger = MagicMock(spec=logging.Logger)
        self.http_client = MagicMock()
        self.client_id = "test_client_id"
        self.access_token = "test_token"
        self.broadcaster_id = "12345"
        self.session_id = "current_session"

    def test_ensure_subscription_creates_if_none(self) -> None:
        """Should create subscription if none exists."""
        # List returns empty
        list_response = make_mock_response(200, {"data": []})
        # Create returns new subscription
        create_response = make_mock_response(202, {
            "data": [make_subscription_response(
                sub_id="new_sub",
                broadcaster_id=self.broadcaster_id,
                session_id=self.session_id,
            )]
        })
        self.http_client.get.return_value = list_response
        self.http_client.post.return_value = create_response

        sub = ensure_stream_offline_subscription(
            http_client=self.http_client,
            client_id=self.client_id,
            access_token=self.access_token,
            broadcaster_id=self.broadcaster_id,
            session_id=self.session_id,
            logger=self.logger,
        )

        self.assertEqual(sub.id, "new_sub")
        self.http_client.post.assert_called_once()
        self.http_client.delete.assert_not_called()

    def test_ensure_subscription_skips_if_exists(self) -> None:
        """Should return existing subscription if matching session_id."""
        existing_sub = make_subscription_response(
            sub_id="existing_sub",
            broadcaster_id=self.broadcaster_id,
            session_id=self.session_id,
            status="enabled",
        )
        list_response = make_mock_response(200, {"data": [existing_sub]})
        self.http_client.get.return_value = list_response

        sub = ensure_stream_offline_subscription(
            http_client=self.http_client,
            client_id=self.client_id,
            access_token=self.access_token,
            broadcaster_id=self.broadcaster_id,
            session_id=self.session_id,
            logger=self.logger,
        )

        self.assertEqual(sub.id, "existing_sub")
        self.http_client.post.assert_not_called()
        self.http_client.delete.assert_not_called()

    def test_ensure_subscription_deletes_stale(self) -> None:
        """Should delete stale subscription (different session_id) then create."""
        stale_sub = make_subscription_response(
            sub_id="stale_sub",
            broadcaster_id=self.broadcaster_id,
            session_id="old_session",  # Different session
            status="enabled",
        )
        list_response = make_mock_response(200, {"data": [stale_sub]})
        delete_response = make_mock_response(204)
        create_response = make_mock_response(202, {
            "data": [make_subscription_response(
                sub_id="new_sub",
                broadcaster_id=self.broadcaster_id,
                session_id=self.session_id,
            )]
        })

        self.http_client.get.return_value = list_response
        self.http_client.delete.return_value = delete_response
        self.http_client.post.return_value = create_response

        sub = ensure_stream_offline_subscription(
            http_client=self.http_client,
            client_id=self.client_id,
            access_token=self.access_token,
            broadcaster_id=self.broadcaster_id,
            session_id=self.session_id,
            logger=self.logger,
        )

        self.assertEqual(sub.id, "new_sub")
        self.http_client.delete.assert_called_once()
        self.http_client.post.assert_called_once()

    def test_ensure_subscription_filters_by_broadcaster(self) -> None:
        """Should filter by broadcaster_id client-side."""
        # Subscription for different broadcaster
        other_sub = make_subscription_response(
            sub_id="other_sub",
            broadcaster_id="99999",  # Different broadcaster
            session_id=self.session_id,
            status="enabled",
        )
        list_response = make_mock_response(200, {"data": [other_sub]})
        create_response = make_mock_response(202, {
            "data": [make_subscription_response(
                sub_id="our_sub",
                broadcaster_id=self.broadcaster_id,
                session_id=self.session_id,
            )]
        })

        self.http_client.get.return_value = list_response
        self.http_client.post.return_value = create_response

        sub = ensure_stream_offline_subscription(
            http_client=self.http_client,
            client_id=self.client_id,
            access_token=self.access_token,
            broadcaster_id=self.broadcaster_id,
            session_id=self.session_id,
            logger=self.logger,
        )

        # Should create new, not use other broadcaster's sub
        self.assertEqual(sub.id, "our_sub")
        self.http_client.post.assert_called_once()
        self.http_client.delete.assert_not_called()

    def test_ensure_subscription_filters_by_websocket_transport(self) -> None:
        """Should filter by websocket transport method."""
        # Webhook subscription (not websocket)
        webhook_sub = make_subscription_response(
            sub_id="webhook_sub",
            broadcaster_id=self.broadcaster_id,
            transport_method="webhook",  # Not websocket
        )
        list_response = make_mock_response(200, {"data": [webhook_sub]})
        create_response = make_mock_response(202, {
            "data": [make_subscription_response(
                sub_id="ws_sub",
                broadcaster_id=self.broadcaster_id,
                session_id=self.session_id,
            )]
        })

        self.http_client.get.return_value = list_response
        self.http_client.post.return_value = create_response

        sub = ensure_stream_offline_subscription(
            http_client=self.http_client,
            client_id=self.client_id,
            access_token=self.access_token,
            broadcaster_id=self.broadcaster_id,
            session_id=self.session_id,
            logger=self.logger,
        )

        # Should create new websocket sub, ignore webhook sub
        self.assertEqual(sub.id, "ws_sub")
        self.http_client.post.assert_called_once()
        self.http_client.delete.assert_not_called()


if __name__ == "__main__":
    unittest.main()
