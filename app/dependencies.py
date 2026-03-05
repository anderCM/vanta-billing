import logging

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.allowed_ip import AllowedIP
from app.models.client import Client
from app.models.integrator import Integrator
from app.services.crypto import hash_api_key

logger = logging.getLogger(__name__)

security = HTTPBearer()


def get_current_client(
    request: Request,
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

    # If client is linked to an integrator, verify the request IP belongs to that integrator
    if client.integrator_id is not None:
        client_ip = request.client.host if request.client else None
        ip_belongs_to_integrator = (
            db.query(AllowedIP.id)
            .join(Integrator, AllowedIP.integrator_id == Integrator.id)
            .filter(
                AllowedIP.ip_address == client_ip,
                AllowedIP.is_active.is_(True),
                Integrator.id == client.integrator_id,
                Integrator.is_active.is_(True),
            )
            .first()
        )

        if not ip_belongs_to_integrator:
            logger.warning(
                "Client %s (integrator %s) attempted access from unauthorized IP: %s",
                client.id,
                client.integrator_id,
                client_ip,
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="IP not authorized for this client's integrator",
            )

    return client
