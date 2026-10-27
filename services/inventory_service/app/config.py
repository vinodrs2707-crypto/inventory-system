from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    SECRET_KEY: str = "change-me-in-env-file"
    ALGORITHM: str = "HS256"
    DATABASE_URL: str = "sqlite:///./services/inventory_service/inventory.db"
    INTERNAL_API_KEY: str = ""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()