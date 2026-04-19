# event-platform-notification-service

Async **RabbitMQ consumer** for the event platform: subscribes to the events **topic** exchange, handles `user.registered`, `order.created`, and `payment.failed`, and routes failures to a **retry** exchange/queue or **DLQ** (`TemporaryNotificationError` vs `FatalNotificationError`, `x-retry-count` in headers, `NOTIFICATION_MAX_RETRIES`).

## Repositories

[GitHub: Elena-sky](https://github.com/Elena-sky)

- [event-platform-gateway-api](https://github.com/Elena-sky/event-platform-gateway-api)
- [event-platform-notification-service](https://github.com/Elena-sky/event-platform-notification-service)
- [event-platform-analytics-audit-service](https://github.com/Elena-sky/event-platform-analytics-audit-service)
- [event-platform-retry-orchestrator-service](https://github.com/Elena-sky/event-platform-retry-orchestrator-service)
- [event-platform-infra](https://github.com/Elena-sky/event-platform-infra)

## Requirements

- **Python 3.12 or 3.13** (3.13 recommended). On **Python 3.14**, installing `pydantic-core` from `requirements.txt` often fails during build — use 3.12/3.13 or wait for wheels for your Python version.
- A running **RabbitMQ** instance (local or from [event-platform-infra](https://github.com/Elena-sky/event-platform-infra)).
- Exchange and queues must match the **gateway** topology (`events.topic` by default).

## Development

```bash
pip install -r requirements-dev.txt
ruff check app tests
ruff format app tests
pytest
```

**CI:** push/PR to `main` or `master` runs Ruff and pytest (see `.github/workflows/ci.yml`).

## Quick start

### 1. Infrastructure (RabbitMQ)

From the `event-platform-infra` directory:

```bash
docker compose up -d
```

Defaults: AMQP `localhost:5672`, user/password `admin` / `admin`, management UI: http://localhost:15672

### 2. Notification service (Docker)

From this repository:

```bash
cd event-platform-notification-service
cp .env.example .env
docker compose up --build
```

Compose sets `RABBITMQ_HOST=rabbitmq` on the container. Align `EVENT_PLATFORM_NETWORK_NAME` in `.env` with [event-platform-infra](https://github.com/Elena-sky/event-platform-infra) (same as [event-platform-gateway-api](https://github.com/Elena-sky/event-platform-gateway-api)).

### 3. Configuration (local `.env`)

```bash
cp .env.example .env
```

Edit `.env` as needed. **All variables** from `.env.example` must be set in `.env` or the environment — there are no fallbacks in code (`app/core/config.py`). `RABBITMQ_NOTIFICATION_BINDING_KEYS` is comma-separated (e.g. `user.*,order.created,payment.failed`).

### 4. Virtual environment and dependencies

```bash
python3.13 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 5. Run locally (no Docker)

From the repository root:

```bash
python -m app.main
```

If RabbitMQ is unreachable, the process exits with an error.

## Failure handling (retry / DLQ)

- **Success** → `ack` on the main or retry queue message.
- **`TemporaryNotificationError`** or unexpected errors → republish to the retry exchange with incremented `x-retry-count` in headers, then `ack`. If retries exceed `NOTIFICATION_MAX_RETRIES` → publish to DLQ, then `ack`.
- **`FatalNotificationError`** (e.g. bad payload, unsupported `event_type`, missing `order_id` for `order.created`) → publish to DLQ, then `ack`.

**Manual checks** (with gateway on `http://localhost:8000`): send `user.registered` with `payload.email`; send `payment.failed` with `payload.simulate_temporary_failure: true` to exercise retry → DLQ after max retries; send `payment.failed` without `email` for immediate DLQ. For `order.created`, include `order_id` in `payload` (required).
