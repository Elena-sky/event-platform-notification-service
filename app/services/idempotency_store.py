from redis.asyncio import Redis

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


class IdempotencyStore:
    def __init__(self) -> None:
        self._redis: Redis | None = None

    async def connect(self) -> None:
        self._redis = Redis.from_url(
            settings.redis_url,
            decode_responses=True,
        )
        await self._redis.ping()
        logger.info("Redis idempotency store connected")

    async def close(self) -> None:
        if self._redis:
            await self._redis.aclose()
            self._redis = None

    async def try_start_processing(self, event_id: str, scope: str) -> bool:
        if not self._redis:
            raise RuntimeError("Redis is not initialized")

        key = f"idempotency:{scope}:{event_id}"

        was_set = await self._redis.set(
            key,
            "processing",
            nx=True,
            ex=settings.idempotency_ttl_seconds,
        )

        return bool(was_set)

    async def mark_processed(self, event_id: str, scope: str) -> None:
        if not self._redis:
            raise RuntimeError("Redis is not initialized")

        key = f"idempotency:{scope}:{event_id}"

        await self._redis.set(
            key,
            "processed",
            ex=settings.idempotency_ttl_seconds,
        )

    async def release_processing(self, event_id: str, scope: str) -> None:
        if not self._redis:
            raise RuntimeError("Redis is not initialized")

        key = f"idempotency:{scope}:{event_id}"
        await self._redis.delete(key)


idempotency_store = IdempotencyStore()
