from pydantic import computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    service_name: str = "service"
    service_port: int = 8000
    postgres_host: str
    postgres_port: int = 5432
    postgres_db: str = "microshop"
    postgres_user: str = "microshop"
    # Required — no defaults; service fails fast at startup if missing
    postgres_password: str
    redis_url: str = "redis://redis:6379/0"
    kafka_bootstrap_servers: str = "kafka:9092"
    kafka_consumer_max_retries: int = 3
    kafka_retry_backoff_seconds: float = 1.0
    kafka_event_version: int = 1
    kafka_dlq_suffix: str = ".dlq"
    jwt_secret: str  # Required

    @computed_field
    @property
    def database_url(self) -> str:
        return (
            f"postgresql+psycopg2://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )


settings = Settings()
