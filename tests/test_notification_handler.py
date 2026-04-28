"""Handler error classification (Day 5)."""

import asyncio
from collections.abc import Coroutine
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from app.domain.exceptions import FatalNotificationError, TemporaryNotificationError
from app.services import notification_handler as nh


@pytest.fixture(autouse=True)
def mock_idempotency_store(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    store = MagicMock()
    store.try_start_processing = AsyncMock(return_value=True)
    store.mark_processed = AsyncMock()
    store.release_processing = AsyncMock()
    monkeypatch.setattr(nh, "idempotency_store", store)
    return store


def _run(coro: Coroutine[Any, Any, None]) -> None:
    asyncio.run(coro)


def test_fatal_unsupported_event_type(mock_idempotency_store: MagicMock) -> None:
    ev = {
        "event_id": "e1",
        "event_type": "unknown.event",
        "payload": {},
    }
    with pytest.raises(FatalNotificationError, match="Unsupported"):
        _run(nh.handle_event(ev))
    mock_idempotency_store.release_processing.assert_awaited_once()
    mock_idempotency_store.mark_processed.assert_not_awaited()


def test_fatal_missing_event_id(mock_idempotency_store: MagicMock) -> None:
    ev = {"event_type": "user.registered", "payload": {"email": "a@b.c"}}
    with pytest.raises(FatalNotificationError, match="event_id"):
        _run(nh.handle_event(ev))
    mock_idempotency_store.try_start_processing.assert_not_awaited()


def test_fatal_order_missing_order_id(mock_idempotency_store: MagicMock) -> None:
    ev = {
        "event_id": "e2",
        "event_type": "order.created",
        "payload": {"email": "a@b.c"},
    }
    with pytest.raises(FatalNotificationError, match="order_id"):
        _run(nh.handle_event(ev))
    mock_idempotency_store.release_processing.assert_awaited_once()
    mock_idempotency_store.mark_processed.assert_not_awaited()


def test_temporary_order_simulate_random_timeout(
    mock_idempotency_store: MagicMock,
) -> None:
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
    mock_idempotency_store.release_processing.assert_awaited_once()
    mock_idempotency_store.mark_processed.assert_not_awaited()


def test_temporary_payment_simulated_failure(mock_idempotency_store: MagicMock) -> None:
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
    mock_idempotency_store.release_processing.assert_awaited_once()
    mock_idempotency_store.mark_processed.assert_not_awaited()


def test_success_order_then_idempotent_skip(
    mock_idempotency_store: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ev = {
        "event_id": "e5",
        "event_type": "order.created",
        "payload": {"email": "a@b.c", "order_id": 42},
    }
    mock_idempotency_store.try_start_processing = AsyncMock(side_effect=[True, False])
    monkeypatch.setattr(nh, "idempotency_store", mock_idempotency_store)

    _run(nh.handle_event(ev))
    _run(nh.handle_event(ev))

    assert mock_idempotency_store.try_start_processing.await_count == 2
    mock_idempotency_store.mark_processed.assert_awaited_once()
