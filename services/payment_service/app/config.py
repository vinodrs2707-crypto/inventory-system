from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    SECRET_KEY: str = "change-me-in-env-file"
    ALGORITHM: str = "HS256"
    DATABASE_URL: str = "sqlite:///./services/payment_service/payment.db"
    INTERNAL_API_KEY: str = ""
    ORDER_SERVICE_URL: str = "http://127.0.0.1:8006"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
