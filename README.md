# event-platform-notification-service

Async **RabbitMQ consumer** for the event platform: subscribes to a **topic** exchange with configurable binding keys and handles `user.registered` / `order.created` (mock notifications).

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

Edit `.env` as needed. **All configuration is required** in `.env` (or the environment): the application has **no in-code defaults** for these settings. See `.env.example` for the full list. `RABBITMQ_BINDING_KEYS` is a comma-separated list of topic patterns (e.g. `user.*,order.created`).

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
