"""Settings from ``.env`` / environment only (no in-code broker topology defaults)."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str
    log_level: str

    rabbitmq_host: str
    rabbitmq_port: int
    rabbitmq_user: str
    rabbitmq_password: str

    rabbitmq_exchange: str
    rabbitmq_queue: str
    rabbitmq_binding_keys: str

    rabbitmq_prefetch: int

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
    def binding_keys(self) -> list[str]:
        return [k.strip() for k in self.rabbitmq_binding_keys.split(",") if k.strip()]


settings = Settings()
