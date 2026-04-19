"""Handler error classification (Day 5)."""

import asyncio
from collections.abc import Coroutine, Iterator
from typing import Any

import pytest

from app.domain.exceptions import FatalNotificationError, TemporaryNotificationError
from app.services import notification_handler as nh


@pytest.fixture(autouse=True)
def _clear_processed() -> Iterator[None]:
    nh.processed_events.clear()
    yield
    nh.processed_events.clear()


def _run(coro: Coroutine[Any, Any, None]) -> None:
    asyncio.run(coro)


def test_fatal_unsupported_event_type() -> None:
    ev = {
        "event_id": "e1",
        "event_type": "unknown.event",
        "payload": {},
    }
    with pytest.raises(FatalNotificationError, match="Unsupported"):
        _run(nh.handle_event(ev))


def test_fatal_missing_event_id() -> None:
    ev = {"event_type": "user.registered", "payload": {"email": "a@b.c"}}
    with pytest.raises(FatalNotificationError, match="event_id"):
        _run(nh.handle_event(ev))


def test_fatal_order_missing_order_id() -> None:
    ev = {
        "event_id": "e2",
        "event_type": "order.created",
        "payload": {"email": "a@b.c"},
    }
    with pytest.raises(FatalNotificationError, match="order_id"):
        _run(nh.handle_event(ev))


def test_temporary_order_simulate_random_timeout() -> None:
    ev = {
        "event_id": "e3",
        "event_type": "order.created",
        "payload": {
            "email": "a@b.c",
            "order_id": 1,
            "simulate_random_timeout": True,
        },
    }
    with pytest.raises(TemporaryNotificationError, match="Simulated timeout"):
        _run(nh.handle_event(ev))


def test_temporary_payment_simulated_failure() -> None:
    ev = {
        "event_id": "e4",
        "event_type": "payment.failed",
        "payload": {
            "email": "a@b.c",
            "simulate_temporary_failure": True,
        },
    }
    with pytest.raises(TemporaryNotificationError, match="outage"):
        _run(nh.handle_event(ev))


def test_success_order_then_idempotent_skip() -> None:
    ev = {
        "event_id": "e5",
        "event_type": "order.created",
        "payload": {"email": "a@b.c", "order_id": 42},
    }
    _run(nh.handle_event(ev))
    _run(nh.handle_event(ev))
    assert "e5" in nh.processed_events
