from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    DATABASE_URL: str = "postgresql://postgres:postgres@localhost:5432/vanta_billing"
    APP_NAME: str = "vanta-billing"
    DEBUG: bool = False

    model_config = {"env_file": ".env"}


settings = Settings()
