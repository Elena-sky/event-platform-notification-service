from app.core.logging import get_logger

logger = get_logger(__name__)

processed_events: set[str] = set()  # mock idempotency


async def handle_event(event: dict) -> None:
    event_id = event["event_id"]
    event_type = event["event_type"]

    if event_id in processed_events:
        logger.warning("Duplicate event skipped", extra={"event_id": event_id})
        return

    processed_events.add(event_id)

    if event_type == "user.registered":
        await send_welcome_email(event)
    elif event_type == "order.created":
        await send_order_email(event)
    else:
        logger.info("Event ignored", extra={"event_type": event_type})


async def send_welcome_email(event: dict) -> None:
    logger.info("Sending welcome email", extra=event["payload"])


async def send_order_email(event: dict) -> None:
    logger.info("Sending order email", extra=event["payload"])
