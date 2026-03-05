import logging

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from sqlalchemy import select

from app.database import SessionLocal
from app.models.allowed_ip import AllowedIP
from app.models.integrator import Integrator

logger = logging.getLogger(__name__)

EXEMPT_PATHS = {"/health"}


class IPWhitelistMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.url.path in EXEMPT_PATHS:
            return await call_next(request)

        client_ip = request.client.host if request.client else None

        if not client_ip:
            logger.warning("Request with no client IP — blocked")
            return JSONResponse(
                status_code=403,
                content={"detail": "IP not allowed"},
            )

        db = SessionLocal()
        try:
            stmt = (
                select(AllowedIP.id)
                .join(Integrator, AllowedIP.integrator_id == Integrator.id)
                .where(
                    AllowedIP.ip_address == client_ip,
                    AllowedIP.is_active.is_(True),
                    Integrator.is_active.is_(True),
                )
            )
            allowed = db.execute(stmt).first()
        finally:
            db.close()

        if not allowed:
            logger.warning("Blocked request from non-whitelisted IP: %s", client_ip)
            return JSONResponse(
                status_code=403,
                content={"detail": "IP not allowed"},
            )

        return await call_next(request)
