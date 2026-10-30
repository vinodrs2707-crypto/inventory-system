from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    SECRET_KEY: str = "change-me-in-env-file"
    ALGORITHM: str = "HS256"

    AUTH_SERVICE_URL: str = "http://127.0.0.1:8001"
    PRODUCT_SERVICE_URL: str = "http://127.0.0.1:8002"
    INVENTORY_SERVICE_URL: str = "http://127.0.0.1:8003"
    COUPON_SERVICE_URL: str = "http://127.0.0.1:8004"
    CART_SERVICE_URL: str = "http://127.0.0.1:8005"
    ORDER_SERVICE_URL: str = "http://127.0.0.1:8006"
    PAYMENT_SERVICE_URL: str = "http://127.0.0.1:8007"
    REVIEW_SERVICE_URL: str = "http://127.0.0.1:8008"
    RETURN_SERVICE_URL: str = "http://127.0.0.1:8009"
    # websites that may call the gateway from a browser (comma separated)
    CORS_ORIGINS: str = "http://localhost:3000,http://localhost:5173"

    GENERAL_RATE_LIMIT_PER_MINUTE: int = 120
    AUTH_RATE_LIMIT_PER_MINUTE: int = 10
    SENSITIVE_RATE_LIMIT_PER_MINUTE: int = 30
    MAX_BODY_BYTES: int = 2_000_000

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()