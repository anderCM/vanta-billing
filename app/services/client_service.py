import logging

from sqlalchemy.orm import Session

from app.exceptions import BillingError
from app.models.client import Client
from app.services.crypto import (
    encrypt_bytes,
    encrypt_string,
    generate_api_key,
    generate_client_id,
    hash_api_key,
)

logger = logging.getLogger(__name__)

_UPDATABLE_FIELDS = {
    "razon_social",
    "nombre_comercial",
    "direccion",
    "ubigeo",
    "sol_user",
    "sol_password",
    "serie_factura",
    "serie_boleta",
    "send_email",
    "generate_pdf",
}

_ENCRYPTED_FIELDS = {"sol_user", "sol_password"}


def register_client(
    db: Session,
    *,
    ruc: str,
    razon_social: str,
    nombre_comercial: str | None = None,
    direccion: str | None = None,
    ubigeo: str | None = None,
    sol_user: str | None = None,
    sol_password: str | None = None,
) -> tuple[Client, str]:
    """Register a new client. Returns (client, api_key)."""
    existing = db.query(Client).filter(Client.ruc == ruc).first()
    if existing:
        raise BillingError("A client with this RUC already exists")

    client_id = generate_client_id()
    api_key = generate_api_key()

    client = Client(
        id=client_id,
        ruc=ruc,
        razon_social=razon_social,
        nombre_comercial=nombre_comercial,
        direccion=direccion,
        ubigeo=ubigeo,
        api_key_hash=hash_api_key(api_key),
    )

    if sol_user and sol_password:
        client.sol_user = encrypt_string(sol_user)
        client.sol_password = encrypt_string(sol_password)

    db.add(client)
    db.commit()
    db.refresh(client)

    logger.info("Client registered: id=%s ruc=%s", client.id, client.ruc)
    return client, api_key


def update_client(db: Session, client: Client, **fields) -> Client:
    """Update client fields, encrypting SOL credentials if provided."""
    for key, value in fields.items():
        if key not in _UPDATABLE_FIELDS:
            raise BillingError(f"Field '{key}' cannot be updated")
        if key in _ENCRYPTED_FIELDS and value is not None:
            value = encrypt_string(value)
        setattr(client, key, value)

    db.commit()
    db.refresh(client)

    logger.info("Client updated: id=%s fields=%s", client.id, list(fields.keys()))
    return client


def rotate_client_api_key(db: Session, client: Client) -> str:
    """Rotate API key. Returns the new plain-text key."""
    new_api_key = generate_api_key()
    client.api_key_hash = hash_api_key(new_api_key)
    db.commit()

    logger.info("API key rotated for client: id=%s", client.id)
    return new_api_key


def upload_client_certificate(
    db: Session, client: Client, pfx_data: bytes, password: str
) -> None:
    """Store encrypted PFX certificate for a client."""
    client.certificate = encrypt_bytes(pfx_data)
    client.certificate_password = encrypt_string(password)
    db.commit()

    logger.info("Certificate uploaded for client: id=%s", client.id)
