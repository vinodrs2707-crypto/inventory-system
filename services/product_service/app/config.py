from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    SECRET_KEY: str = "change-me-in-env-file"
    ALGORITHM: str = "HS256"
    DATABASE_URL: str = "sqlite:///./services/product_service/product.db"

    model_config = SettingsConfigDict(env_file=".env")


settings = Settings()