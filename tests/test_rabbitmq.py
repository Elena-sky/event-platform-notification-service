"""Consumer routing for invalid inbound bodies and retry forwarding."""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

from app.core.config import settings
from app.domain.exceptions import TemporaryNotificationError
from app.messaging.rabbitmq import Consumer


def test_invalid_json_body_published_to_dlq_then_acked() -> None:
    asyncio.run(_invalid_json_body_published_to_dlq_then_acked())


async def _invalid_json_body_published_to_dlq_then_acked() -> None:
    consumer = Consumer()
    consumer._dlq_exchange = AsyncMock()

    msg = MagicMock()
    msg.body = b"{not-valid-json"
    msg.headers = {}
    ack = AsyncMock()
    msg.ack = ack

    await consumer._process_message(msg, source_queue="notification.email")

    consumer._dlq_exchange.publish.assert_called_once()
    ack.assert_called_once()

    published = consumer._dlq_exchange.publish.call_args[0][0]
    stored = json.loads(published.body.decode("utf-8"))
    assert stored["event_type"] == "__invalid_body__"
    assert stored["raw_body"] == "{not-valid-json"
    assert "decode_error" in stored and "Invalid JSON" in stored["decode_error"]
    assert stored["source_queue"] == "notification.email"
    assert str(stored["event_id"]).startswith("invalid-body-")


def test_json_array_body_published_to_dlq_then_acked() -> None:
    asyncio.run(_json_array_body_published_to_dlq_then_acked())


async def _json_array_body_published_to_dlq_then_acked() -> None:
    consumer = Consumer()
    consumer._dlq_exchange = AsyncMock()

    msg = MagicMock()
    msg.body = b"[1, 2]"
    msg.headers = {}
    msg.ack = AsyncMock()

    await consumer._process_message(msg, source_queue="notification.email")

    consumer._dlq_exchange.publish.assert_called_once()
    msg.ack.assert_called_once()
    published = consumer._dlq_exchange.publish.call_args[0][0]
    stored = json.loads(published.body.decode("utf-8"))
    assert "must be a JSON object" in stored["decode_error"]


def test_temporary_failure_forwarded_to_retry_exchange_then_acked() -> None:
    asyncio.run(_temporary_failure_forwarded_to_retry_exchange_then_acked())


async def _temporary_failure_forwarded_to_retry_exchange_then_acked() -> None:
    consumer = Consumer()
    consumer._retry_exchange = AsyncMock()

    msg = MagicMock()
    msg.body = json.dumps(
        {"event_id": "e1", "event_type": "payment.failed", "payload": {}},
    ).encode()
    msg.headers = {}
    msg.routing_key = "payment.failed"
    msg.ack = AsyncMock()

    with patch(
        "app.messaging.rabbitmq.handle_event",
        side_effect=TemporaryNotificationError("smtp down"),
    ):
        await consumer._process_message(msg, source_queue="notification.email")

    consumer._retry_exchange.publish.assert_called_once()
    msg.ack.assert_called_once()

    published = consumer._retry_exchange.publish.call_args[0][0]
    kwargs = consumer._retry_exchange.publish.call_args[1]
    assert kwargs["routing_key"] == settings.rabbitmq_retry_routing_key

    hdrs = dict(published.headers or {})
    assert hdrs["x-retry-count"] == 0
    assert hdrs["x-original-routing-key"] == "payment.failed"
    assert hdrs["x-last-error"] == "smtp down"
