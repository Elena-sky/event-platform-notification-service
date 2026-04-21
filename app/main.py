"""Entrypoint: runs the AMQP consumer and the health HTTP server concurrently."""

import asyncio

import uvicorn

from app.api import app
from app.core.config import settings
from app.core.logging import configure_logging, get_logger
from app.messaging.rabbitmq import Consumer

configure_logging()
logger = get_logger(__name__)

_HTTP_PORT = 8080


async def _run_consumer() -> None:
    consumer = Consumer()
    await consumer.start()


async def _run_api() -> None:
    config = uvicorn.Config(
        app,
        host="0.0.0.0",  # noqa: S104
        port=_HTTP_PORT,
        log_level=settings.log_level.lower(),
    )
    server = uvicorn.Server(config)
    await server.serve()


async def main() -> None:
    logger.info(
        "Starting notification-service",
        extra={"service": settings.app_name, "health_port": _HTTP_PORT},
    )
    await asyncio.gather(_run_consumer(), _run_api())


if __name__ == "__main__":
    asyncio.run(main())
