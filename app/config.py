from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    DATABASE_URL: str = "postgresql://postgres:postgres@localhost:5432/vanta_billing"
    APP_NAME: str = "vanta-billing"
    DEBUG: bool = False

    ENCRYPTION_KEY: str = ""
    SUNAT_SOAP_URL: str = ""
    SUNAT_CONSULT_URL: str = ""
    SUNAT_VERIFY_SSL: bool = True

    # REST API for GRE (Guías de Remisión Electrónica)
    SUNAT_REST_CLIENT_ID: str = ""
    SUNAT_REST_KEY: str = ""
    SUNAT_REST_TOKEN_URL: str = ""
    SUNAT_REST_API_URL: str = ""

    IGV_RATE: float = 0.18
    ENABLE_DOCS: bool = False
    model_config = {"env_file": ".env"}


settings = Settings()
