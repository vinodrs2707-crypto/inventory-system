from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    SECRET_KEY: str = "change-me-in-env-file"
    ALGORITHM: str = "HS256"
    DATABASE_URL: str = "sqlite:///./services/notification_service/notification.db"
    RABBITMQ_URL: str = ""
    MAX_RETRIES: int = 3
    RETRY_DELAY_SECONDS: int = 10
    # only for our tests: lets scripts send fake events that fail on purpose
    ENABLE_TEST_EVENTS: bool = False

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()