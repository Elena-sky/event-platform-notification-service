from app.core.logging import get_logger
from app.domain.exceptions import FatalNotificationError, TemporaryNotificationError

logger = get_logger(__name__)

processed_events: set[str] = set()  # mock idempotency


async def handle_event(event: dict) -> None:
    try:
        event_id = event["event_id"]
        event_type = event["event_type"]
    except KeyError as e:
        raise FatalNotificationError(f"Missing required field: {e.args[0]}") from e

    event_key = str(event_id)
    if event_key in processed_events:
        logger.warning("Duplicate event skipped", extra={"event_id": event_key})
        return

    if event_type == "user.registered":
        await send_welcome_email(event)
    elif event_type == "order.created":
        await send_order_email(event)
    elif event_type == "payment.failed":
        await send_payment_failed_email(event)
    else:
        raise FatalNotificationError(f"Unsupported event type: {event_type}")

    processed_events.add(event_key)


async def send_welcome_email(event: dict) -> None:
    payload = event["payload"]

    email = payload.get("email")
    if not email:
        raise FatalNotificationError("Missing required field: email")

    logger.info("Sending welcome email", extra={"email": email})


async def send_order_email(event: dict) -> None:
    payload = event["payload"]

    if payload.get("simulate_random_timeout") is True:
        raise TemporaryNotificationError("Simulated timeout")

    email = payload.get("email")
    if not email:
        raise FatalNotificationError("Missing required field: email")

    if "order_id" not in payload or payload["order_id"] in (None, ""):
        raise FatalNotificationError("Missing required field: order_id")

    logger.info(
        "Sending order email",
        extra={
            "email": email,
            "order_id": payload.get("order_id"),
        },
    )


async def send_payment_failed_email(event: dict) -> None:
    payload = event["payload"]

    if payload.get("simulate_temporary_failure") is True:
        raise TemporaryNotificationError("Simulated temporary downstream outage")

    email = payload.get("email")
    if not email:
        raise FatalNotificationError("Missing required field: email")

    logger.info(
        "Sending payment failed email",
        extra={
            "email": email,
            "payment_id": payload.get("payment_id"),
        },
    )
