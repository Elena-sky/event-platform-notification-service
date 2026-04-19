from app.core.config import settings


def test_notification_binding_keys_parsed() -> None:
    assert "user.*" in settings.notification_binding_keys
    assert "order.created" in settings.notification_binding_keys
    assert "payment.failed" in settings.notification_binding_keys


def test_retry_tiers_three_levels() -> None:
    assert len(settings.retry_tiers) == 3
    names = [q for q, _ in settings.retry_tiers]
    assert names == [
        settings.retry_queue_1,
        settings.retry_queue_2,
        settings.retry_queue_3,
    ]


def test_main_queue_binding_keys_merge_patterns_and_retry_queues() -> None:
    keys = settings.main_queue_binding_keys
    assert "user.*" in keys
    assert settings.retry_queue_1 in keys
    assert settings.retry_queue_2 in keys
    assert settings.retry_queue_3 in keys


def test_rabbitmq_url_format() -> None:
    assert settings.rabbitmq_url.startswith("amqp://")
