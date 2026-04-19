"""Consumer routing for invalid inbound bodies."""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock

from app.core.config import settings
from app.messaging.rabbitmq import Consumer, retry_queue_for_attempt


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

    await consumer._process_message(msg, source_queue="notification.retry.5s")

    consumer._dlq_exchange.publish.assert_called_once()
    msg.ack.assert_called_once()
    published = consumer._dlq_exchange.publish.call_args[0][0]
    stored = json.loads(published.body.decode("utf-8"))
    assert "must be a JSON object" in stored["decode_error"]


def test_retry_queue_for_attempt_maps_three_tiers() -> None:
    assert retry_queue_for_attempt(1) == settings.retry_queue_1
    assert retry_queue_for_attempt(2) == settings.retry_queue_2
    assert retry_queue_for_attempt(3) == settings.retry_queue_3
    assert retry_queue_for_attempt(4) is None
    assert retry_queue_for_attempt(0) is None
