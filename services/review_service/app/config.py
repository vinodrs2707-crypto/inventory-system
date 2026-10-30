from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    SECRET_KEY: str = "change-me-in-env-file"
    ALGORITHM: str = "HS256"
    DATABASE_URL: str = "sqlite:///./services/review_service/review.db"
    INTERNAL_API_KEY: str = ""
    AUTH_SERVICE_URL: str = "http://127.0.0.1:8001"
    ORDER_SERVICE_URL: str = "http://127.0.0.1:8006"
    PRODUCT_SERVICE_URL: str = "http://127.0.0.1:8002"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()