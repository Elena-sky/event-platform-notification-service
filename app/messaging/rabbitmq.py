import asyncio
import json

import aio_pika
from aio_pika import ExchangeType, IncomingMessage

from app.core.config import settings
from app.core.logging import get_logger
from app.services.notification_handler import handle_event

logger = get_logger(__name__)


class Consumer:
    async def start(self) -> None:
        connection = await aio_pika.connect_robust(settings.rabbitmq_url)
        channel = await connection.channel()

        await channel.set_qos(prefetch_count=settings.rabbitmq_prefetch)

        exchange = await channel.declare_exchange(
            settings.rabbitmq_exchange,
            ExchangeType.TOPIC,
            durable=True,
        )

        queue = await channel.declare_queue(
            settings.rabbitmq_queue,
            durable=True,
        )

        for key in settings.binding_keys:
            await queue.bind(exchange, routing_key=key)

        logger.info(
            "Consumer started",
            extra={
                "queue": settings.rabbitmq_queue,
                "bindings": settings.binding_keys,
            },
        )

        await queue.consume(self.process_message)

        await asyncio.Future()

    async def process_message(self, message: IncomingMessage) -> None:
        async with message.process(ignore_processed=True):
            try:
                payload = json.loads(message.body.decode("utf-8"))
                await handle_event(payload)
                logger.info(
                    "Message processed",
                    extra={"event_id": payload.get("event_id")},
                )
            except Exception as e:
                logger.error(
                    "Processing failed",
                    extra={"error": str(e)},
                )
                raise
