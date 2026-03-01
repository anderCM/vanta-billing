import logging

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.client import Client
from app.services.crypto import hash_api_key

logger = logging.getLogger(__name__)

security = HTTPBearer()


def get_current_client(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db),
) -> Client:
    api_key = credentials.credentials
    key_hash = hash_api_key(api_key)

    client = db.query(Client).filter(Client.api_key_hash == key_hash).first()
    if client is None or not client.is_active:
        logger.warning("Authentication failed: invalid or inactive API key")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or inactive API key",
        )
    return client
