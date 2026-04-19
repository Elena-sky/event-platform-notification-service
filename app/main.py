import asyncio

from app.core.logging import configure_logging
from app.messaging.rabbitmq import Consumer

configure_logging()


async def main() -> None:
    consumer = Consumer()
    await consumer.start()


if __name__ == "__main__":
    asyncio.run(main())