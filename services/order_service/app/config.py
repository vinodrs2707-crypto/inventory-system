from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    SECRET_KEY: str = "change-me-in-env-file"
    ALGORITHM: str = "HS256"
    DATABASE_URL: str = "sqlite:///./services/order_service/order.db"
    INTERNAL_API_KEY: str = ""
    CART_SERVICE_URL: str = "http://127.0.0.1:8005"
    INVENTORY_SERVICE_URL: str = "http://127.0.0.1:8003"
    COUPON_SERVICE_URL: str = "http://127.0.0.1:8004"
    TAX_RATE: float = 0.18
    SHIPPING_FEE: float = 50.0
    FREE_SHIPPING_THRESHOLD: float = 1000.0
    PENDING_ORDER_MINUTES: int = 30

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()