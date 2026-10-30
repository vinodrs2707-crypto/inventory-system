from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    SECRET_KEY: str = "change-me-in-env-file"
    ALGORITHM: str = "HS256"
    ORDER_SERVICE_URL: str = "http://127.0.0.1:8006"
    INVENTORY_SERVICE_URL: str = "http://127.0.0.1:8003"
    PRODUCT_SERVICE_URL: str = "http://127.0.0.1:8002"
    RETURN_SERVICE_URL: str = "http://127.0.0.1:8009"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()