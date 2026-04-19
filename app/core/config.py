"""Application settings from environment / ``.env`` (no in-code defaults)."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str
    log_level: str

    rabbitmq_host: str
    rabbitmq_port: int
    rabbitmq_user: str
    rabbitmq_password: str

    rabbitmq_events_exchange: str
    rabbitmq_events_exchange_type: str

    rabbitmq_notification_queue: str
    rabbitmq_notification_binding_keys: str

    rabbitmq_retry_exchange: str
    rabbitmq_retry_queue: str
    rabbitmq_retry_routing_key: str

    rabbitmq_dlq_exchange: str
    rabbitmq_dlq_queue: str
    rabbitmq_dlq_routing_key: str

    rabbitmq_prefetch: int
    notification_max_retries: int

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    @property
    def rabbitmq_url(self) -> str:
        return (
            f"amqp://{self.rabbitmq_user}:{self.rabbitmq_password}"
            f"@{self.rabbitmq_host}:{self.rabbitmq_port}/"
        )

    @property
    def notification_binding_keys(self) -> list[str]:
        return [
            key.strip()
            for key in self.rabbitmq_notification_binding_keys.split(",")
            if key.strip()
        ]


settings = Settings()
