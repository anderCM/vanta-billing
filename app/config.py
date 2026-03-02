from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    DATABASE_URL: str = "postgresql://postgres:postgres@localhost:5432/vanta_billing"
    APP_NAME: str = "vanta-billing"
    DEBUG: bool = False

    ENCRYPTION_KEY: str = ""
    SUNAT_SOAP_URL: str = ""
    SUNAT_CONSULT_URL: str = ""
    SUNAT_VERIFY_SSL: bool = True
    IGV_RATE: float = 0.18
    model_config = {"env_file": ".env"}


settings = Settings()
