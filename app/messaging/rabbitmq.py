import asyncio
import hashlib
import json
from typing import Any

import aio_pika
from aio_pika import DeliveryMode, ExchangeType, IncomingMessage, Message
from aio_pika.abc import AbstractRobustChannel, AbstractRobustExchange

from app.core.config import settings
from app.core.logging import get_logger
from app.domain.exceptions import FatalNotificationError, TemporaryNotificationError
from app.messaging.amqp_retry import connect_robust_when_ready
from app.services.notification_handler import handle_event

logger = get_logger(__name__)


def _exchange_type_from_settings(name: str) -> ExchangeType:
    key = name.lower().strip()
    mapping: dict[str, ExchangeType] = {
        "topic": ExchangeType.TOPIC,
        "direct": ExchangeType.DIRECT,
        "fanout": ExchangeType.FANOUT,
        "headers": ExchangeType.HEADERS,
    }
    if key not in mapping:
        raise ValueError(
            f"Unsupported RABBITMQ_EVENTS_EXCHANGE_TYPE={name!r}; "
            f"expected one of: {', '.join(sorted(mapping))}"
        )
    return mapping[key]


def _retry_count_from_headers(headers: dict[str, Any]) -> int:
    raw = headers.get("x-retry-count", 0)
    if raw is None:
        return 0
    try:
        return int(raw)
    except (TypeError, ValueError):
        return 0


class Consumer:
    def __init__(self) -> None:
        self._connection: aio_pika.RobustConnection | None = None
        self._channel: AbstractRobustChannel | None = None
        self._events_exchange: AbstractRobustExchange | None = None
        self._retry_exchange: AbstractRobustExchange | None = None
        self._dlq_exchange: AbstractRobustExchange | None = None

    async def start(self) -> None:
        self._connection = await connect_robust_when_ready(
            settings.rabbitmq_url,
            logger=logger,
        )
        self._channel = await self._connection.channel()

        await self._channel.set_qos(prefetch_count=settings.rabbitmq_prefetch)

        self._events_exchange = await self._channel.declare_exchange(
            settings.rabbitmq_events_exchange,
            _exchange_type_from_settings(settings.rabbitmq_events_exchange_type),
            durable=True,
        )

        self._retry_exchange = await self._channel.declare_exchange(
            settings.rabbitmq_retry_exchange,
            _exchange_type_from_settings(settings.rabbitmq_retry_exchange_type),
            durable=True,
        )

        main_queue = await self._channel.declare_queue(
            settings.rabbitmq_notification_queue,
            durable=True,
        )

        for key in settings.main_queue_binding_keys:
            await main_queue.bind(self._events_exchange, routing_key=key)

        self._dlq_exchange = await self._channel.declare_exchange(
            settings.rabbitmq_dlq_exchange,
            ExchangeType.DIRECT,
            durable=True,
        )

        dlq_queue = await self._channel.declare_queue(
            settings.rabbitmq_dlq_queue,
            durable=True,
        )
        await dlq_queue.bind(
            self._dlq_exchange,
            routing_key=settings.rabbitmq_dlq_routing_key,
        )

        logger.info(
            "Notification consumer started",
            extra={
                "main_queue": settings.rabbitmq_notification_queue,
                "bindings": settings.main_queue_binding_keys,
                "retry_exchange": settings.rabbitmq_retry_exchange,
                "retry_routing_key": settings.rabbitmq_retry_routing_key,
                "dlq_queue": settings.rabbitmq_dlq_queue,
            },
        )

        await main_queue.consume(self.process_main_message)

        await asyncio.Future()

    async def process_main_message(self, message: IncomingMessage) -> None:
        await self._process_message(
            message, source_queue=settings.rabbitmq_notification_queue
        )

    async def _process_message(
        self, message: IncomingMessage, source_queue: str
    ) -> None:
        try:
            payload = self._decode_payload(message)
        except FatalNotificationError as exc:
            logger.error(
                "Invalid message body, publishing to DLQ",
                extra={"source_queue": source_queue, "error": str(exc)},
            )
            await self._publish_invalid_body_to_dlq(message, source_queue, exc)
            await message.ack()
            return

        headers = dict(message.headers or {})
        retry_count = _retry_count_from_headers(headers)

        logger.info(
            "Message received",
            extra={
                "source_queue": source_queue,
                "event_id": payload.get("event_id"),
                "event_type": payload.get("event_type"),
                "retry_count": retry_count,
            },
        )

        try:
            await handle_event(payload)

            await message.ack()

            logger.info(
                "Message acknowledged",
                extra={
                    "source_queue": source_queue,
                    "event_id": payload.get("event_id"),
                    "retry_count": retry_count,
                },
            )

        except TemporaryNotificationError as exc:
            logger.warning(
                "Temporary notification error",
                extra={
                    "event_id": payload.get("event_id"),
                    "event_type": payload.get("event_type"),
                    "retry_count": retry_count,
                    "error": str(exc),
                },
            )

            await self._forward_to_retry_orchestrator(
                message, payload, retry_count, str(exc)
            )

        except FatalNotificationError as exc:
            logger.error(
                "Fatal notification error",
                extra={
                    "event_id": payload.get("event_id"),
                    "event_type": payload.get("event_type"),
                    "retry_count": retry_count,
                    "error": str(exc),
                },
            )

            await self._publish_to_dlq(
                payload=payload,
                retry_count=retry_count,
                error_reason=str(exc),
            )
            await message.ack()

        except Exception as exc:
            logger.exception(
                "Unexpected processing error",
                extra={
                    "event_id": payload.get("event_id"),
                    "event_type": payload.get("event_type"),
                    "retry_count": retry_count,
                    "error": str(exc),
                },
            )

            await self._forward_to_retry_orchestrator(
                message, payload, retry_count, str(exc)
            )

    async def _forward_to_retry_orchestrator(
        self,
        message: IncomingMessage,
        payload: dict[str, Any],
        retry_count: int,
        error_reason: str,
    ) -> None:
        if not self._retry_exchange:
            raise RuntimeError("Retry exchange is not initialized")

        body = json.dumps(payload, default=str).encode("utf-8")

        routing_key_prop = getattr(message, "routing_key", None)
        original_rk = routing_key_prop if isinstance(routing_key_prop, str) else ""

        retry_message = Message(
            body=body,
            content_type="application/json",
            delivery_mode=DeliveryMode.PERSISTENT,
            message_id=str(payload.get("event_id")),
            type=payload.get("event_type"),
            headers={
                "x-retry-count": retry_count,
                "x-original-routing-key": original_rk,
                "x-last-error": error_reason,
            },
        )

        await self._retry_exchange.publish(
            retry_message,
            routing_key=settings.rabbitmq_retry_routing_key,
        )

        logger.info(
            "Forwarded failure to retry orchestrator",
            extra={
                "event_id": payload.get("event_id"),
                "retry_count": retry_count,
                "original_routing_key": original_rk,
            },
        )

        await message.ack()

    async def _publish_to_dlq(
        self,
        payload: dict[str, Any],
        retry_count: int,
        error_reason: str,
    ) -> None:
        if not self._dlq_exchange:
            raise RuntimeError("DLQ exchange is not initialized")

        body = json.dumps(payload, default=str).encode("utf-8")

        dlq_message = Message(
            body=body,
            content_type="application/json",
            delivery_mode=DeliveryMode.PERSISTENT,
            message_id=str(payload.get("event_id")),
            type=payload.get("event_type"),
            headers={
                "x-retry-count": retry_count,
                "x-death-reason": error_reason,
            },
        )

        await self._dlq_exchange.publish(
            dlq_message,
            routing_key=settings.rabbitmq_dlq_routing_key,
        )

        logger.info(
            "Message published to DLQ",
            extra={
                "event_id": payload.get("event_id"),
                "retry_count": retry_count,
                "dlq_queue": settings.rabbitmq_dlq_queue,
            },
        )

    async def _publish_invalid_body_to_dlq(
        self,
        message: IncomingMessage,
        source_queue: str,
        exc: FatalNotificationError,
    ) -> None:
        digest = hashlib.sha256(message.body).hexdigest()[:24]
        dlq_payload: dict[str, Any] = {
            "event_id": f"invalid-body-{digest}",
            "event_type": "__invalid_body__",
            "raw_body": message.body.decode("utf-8", errors="replace"),
            "decode_error": str(exc),
            "source_queue": source_queue,
        }
        await self._publish_to_dlq(
            payload=dlq_payload,
            retry_count=0,
            error_reason=str(exc),
        )

    @staticmethod
    def _decode_payload(message: IncomingMessage) -> dict[str, Any]:
        try:
            data = json.loads(message.body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as e:
            raise FatalNotificationError(f"Invalid JSON body: {e}") from e
        if not isinstance(data, dict):
            raise FatalNotificationError("Message body must be a JSON object")
        return data
