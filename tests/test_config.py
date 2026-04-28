from app.core.config import settings


def test_notification_binding_keys_parsed() -> None:
    assert "user.*" in settings.notification_binding_keys
    assert "order.created" in settings.notification_binding_keys
    assert "payment.failed" in settings.notification_binding_keys


def test_main_queue_binding_keys_match_notification_keys() -> None:
    keys = settings.main_queue_binding_keys
    assert keys == settings.notification_binding_keys


def test_rabbitmq_url_format() -> None:
    assert settings.rabbitmq_url.startswith("amqp://")


def test_redis_url_format() -> None:
    assert settings.redis_url.startswith("redis://")
    assert ":6379/" in settings.redis_url or ":6379/0" in settings.redis_url
