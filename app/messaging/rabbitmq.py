import asyncio
import json
from typing import Any

import aio_pika
from aio_pika import DeliveryMode, ExchangeType, IncomingMessage, Message
from aio_pika.abc import AbstractRobustExchange, AbstractRobustQueue, RobustChannel

from app.core.config import settings
from app.core.logging import get_logger
from app.domain.exceptions import FatalNotificationError, TemporaryNotificationError
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
        self._channel: RobustChannel | None = None
        self._events_exchange: AbstractRobustExchange | None = None
        self._retry_exchange: AbstractRobustExchange | None = None
        self._dlq_exchange: AbstractRobustExchange | None = None

    async def start(self) -> None:
        self._connection = await aio_pika.connect_robust(settings.rabbitmq_url)
        self._channel = await self._connection.channel()

        await self._channel.set_qos(prefetch_count=settings.rabbitmq_prefetch)

        self._events_exchange = await self._channel.declare_exchange(
            settings.rabbitmq_events_exchange,
            _exchange_type_from_settings(settings.rabbitmq_events_exchange_type),
            durable=True,
        )

        self._retry_exchange = await self._channel.declare_exchange(
            settings.rabbitmq_retry_exchange,
            ExchangeType.DIRECT,
            durable=True,
        )

        self._dlq_exchange = await self._channel.declare_exchange(
            settings.rabbitmq_dlq_exchange,
            ExchangeType.DIRECT,
            durable=True,
        )

        main_queue = await self._channel.declare_queue(
            settings.rabbitmq_notification_queue,
            durable=True,
        )

        for key in settings.notification_binding_keys:
            await main_queue.bind(self._events_exchange, routing_key=key)

        retry_queue = await self._channel.declare_queue(
            settings.rabbitmq_retry_queue,
            durable=True,
        )
        await retry_queue.bind(
            self._retry_exchange,
            routing_key=settings.rabbitmq_retry_routing_key,
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
                "bindings": settings.notification_binding_keys,
                "retry_queue": settings.rabbitmq_retry_queue,
                "dlq_queue": settings.rabbitmq_dlq_queue,
                "max_retries": settings.notification_max_retries,
            },
        )

        await main_queue.consume(self.process_main_message)
        await retry_queue.consume(self.process_retry_message)

        await asyncio.Future()

    async def process_main_message(self, message: IncomingMessage) -> None:
        await self._process_message(
            message, source_queue=settings.rabbitmq_notification_queue
        )

    async def process_retry_message(self, message: IncomingMessage) -> None:
        await self._process_message(message, source_queue=settings.rabbitmq_retry_queue)

    async def _process_message(
        self, message: IncomingMessage, source_queue: str
    ) -> None:
        try:
            payload = self._decode_payload(message)
        except FatalNotificationError as exc:
            logger.error(
                "Invalid message body",
                extra={"source_queue": source_queue, "error": str(exc)},
            )
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

            await self._handle_temporary_failure(
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

            await self._handle_temporary_failure(
                message, payload, retry_count, str(exc)
            )

    async def _handle_temporary_failure(
        self,
        message: IncomingMessage,
        payload: dict[str, Any],
        retry_count: int,
        error_reason: str,
    ) -> None:
        next_retry_count = retry_count + 1

        if next_retry_count > settings.notification_max_retries:
            await self._publish_to_dlq(
                payload=payload,
                retry_count=retry_count,
                error_reason=f"Max retries exceeded: {error_reason}",
            )
            await message.ack()
            return

        await self._publish_to_retry(
            payload=payload,
            retry_count=next_retry_count,
            error_reason=error_reason,
        )
        await message.ack()

    async def _publish_to_retry(
        self,
        payload: dict[str, Any],
        retry_count: int,
        error_reason: str,
    ) -> None:
        if not self._retry_exchange:
            raise RuntimeError("Retry exchange is not initialized")

        body = json.dumps(payload, default=str).encode("utf-8")

        retry_message = Message(
            body=body,
            content_type="application/json",
            delivery_mode=DeliveryMode.PERSISTENT,
            message_id=str(payload.get("event_id")),
            type=payload.get("event_type"),
            headers={
                "x-retry-count": retry_count,
                "x-last-error": error_reason,
            },
        )

        await self._retry_exchange.publish(
            retry_message,
            routing_key=settings.rabbitmq_retry_routing_key,
        )

        logger.info(
            "Message published to retry queue",
            extra={
                "event_id": payload.get("event_id"),
                "retry_count": retry_count,
                "retry_queue": settings.rabbitmq_retry_queue,
            },
        )

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

    @staticmethod
    def _decode_payload(message: IncomingMessage) -> dict[str, Any]:
        try:
            data = json.loads(message.body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as e:
            raise FatalNotificationError(f"Invalid JSON body: {e}") from e
        if not isinstance(data, dict):
            raise FatalNotificationError("Message body must be a JSON object")
        return data
