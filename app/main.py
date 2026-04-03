import asyncio

from app.core.logging import configure_logging
from app.messaging.rabbitmq import Consumer

configure_logging()


async def _run() -> None:
    consumer = Consumer()
    await consumer.start()


def main() -> None:
    asyncio.run(_run())


if __name__ == "__main__":
    main()
