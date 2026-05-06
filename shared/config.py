import os


class Settings:
    service_name = os.getenv("SERVICE_NAME", "service")
    service_port = int(os.getenv("SERVICE_PORT", "8000"))
    postgres_host = os.getenv("POSTGRES_HOST", "postgres")
    postgres_port = int(os.getenv("POSTGRES_PORT", "5432"))
    postgres_db = os.getenv("POSTGRES_DB", "microshop")
    postgres_user = os.getenv("POSTGRES_USER", "microshop")
    postgres_password = os.getenv("POSTGRES_PASSWORD", "microshop")
    redis_url = os.getenv("REDIS_URL", "redis://redis:6379/0")
    kafka_bootstrap_servers = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka:9092")
    jwt_secret = os.getenv("JWT_SECRET", "supersecret")

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+psycopg2://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )


settings = Settings()
