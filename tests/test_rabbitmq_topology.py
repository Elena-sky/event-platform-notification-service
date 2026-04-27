"""Topology tests: critical queues are declared as quorum, not classic.

These tests pin two invariants:
1. ``QUORUM_QUEUE_ARGS`` matches the canonical ``{"x-queue-type": "quorum"}``
   literal — so an accidental rename / typo in this service is caught
   before it diverges from event-platform-retry-orchestrator-service
   (which co-declares ``notification.email.dlq``).
2. ``Consumer.start`` calls ``declare_queue`` with that ``arguments`` dict
   for both the main notification queue and the DLQ.
"""

from __future__ import annotations

import asyncio
from contextlib import suppress
from unittest.mock import AsyncMock, patch

from app.messaging.rabbitmq import QUORUM_QUEUE_ARGS, Consumer


def test_quorum_queue_args_is_canonical_literal() -> None:
    """Catch drift between this service and retry-orchestrator's DLQ declare.

    Both services declare ``notification.email.dlq`` and RabbitMQ rejects
    the second declare with ``inequivalent arg`` if the dicts are not
    byte-equivalent — pinning the literal here is the cheapest defence.
    """
    assert QUORUM_QUEUE_ARGS == {"x-queue-type": "quorum"}


def test_start_declares_main_queue_and_dlq_as_quorum() -> None:
    asyncio.run(_start_declares_main_queue_and_dlq_as_quorum())


async def _start_declares_main_queue_and_dlq_as_quorum() -> None:
    channel = AsyncMock()
    channel.declare_exchange = AsyncMock(return_value=AsyncMock())

    declared_queue = AsyncMock()
    declared_queue.bind = AsyncMock()
    declared_queue.consume = AsyncMock()
    channel.declare_queue = AsyncMock(return_value=declared_queue)

    connection = AsyncMock()
    connection.channel = AsyncMock(return_value=channel)

    consumer = Consumer()

    with (
        patch(
            "app.messaging.rabbitmq.connect_robust_when_ready",
            AsyncMock(return_value=connection),
        ),
        suppress(asyncio.TimeoutError),
    ):
        # ``start()`` ends with ``await asyncio.Future()`` (blocks forever);
        # break out via a short timeout once topology is set up.
        await asyncio.wait_for(consumer.start(), timeout=0.1)

    queue_calls = channel.declare_queue.call_args_list
    assert len(queue_calls) == 2, (
        "Expected two declare_queue calls (main + dlq), got "
        f"{len(queue_calls)}: {queue_calls}"
    )

    # Order in start(): main queue first, DLQ second.
    main_call, dlq_call = queue_calls
    assert main_call.kwargs["arguments"] == QUORUM_QUEUE_ARGS
    assert dlq_call.kwargs["arguments"] == QUORUM_QUEUE_ARGS
