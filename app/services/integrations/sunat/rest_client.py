"""Low-level REST HTTP transport for SUNAT GRE (Guías de Remisión Electrónica).

Handles OAuth2 token acquisition, document submission, and ticket status queries
via SUNAT's REST API (replaces SOAP for dispatch guides).
"""

import logging

import httpx

from app.config import settings
from app.exceptions import SUNATError

logger = logging.getLogger(__name__)


async def get_sunat_token(
    *,
    ruc: str,
    sol_user: str,
    sol_password: str,
    sunat_client_id: str | None = None,
    sunat_client_secret: str | None = None,
) -> str:
    """Obtain an OAuth2 access token from SUNAT's security endpoint.

    POST https://api-seguridad.sunat.gob.pe/v1/clientessol/{client_id}/oauth2/token
    Content-Type: application/x-www-form-urlencoded

    Uses per-client credentials if provided, falls back to global settings.
    Returns the access_token string.
    """
    client_id = sunat_client_id or settings.SUNAT_REST_CLIENT_ID
    client_secret = sunat_client_secret or settings.SUNAT_REST_KEY

    if not client_id or not client_secret:
        raise SUNATError(
            "SUNAT REST credentials not configured. "
            "Set sunat_client_id/sunat_client_secret on the client, "
            "or SUNAT_REST_CLIENT_ID/SUNAT_REST_KEY globally."
        )
    if not settings.SUNAT_REST_TOKEN_URL:
        raise SUNATError("SUNAT_REST_TOKEN_URL not configured")

    url = f"{settings.SUNAT_REST_TOKEN_URL}/{client_id}/oauth2/token"
    username = f"{ruc}{sol_user}"

    data = {
        "grant_type": "password",
        "scope": "https://api-cpe.sunat.gob.pe",
        "client_id": client_id,
        "client_secret": client_secret,
        "username": username,
        "password": sol_password,
    }

    async with httpx.AsyncClient(
        timeout=30, verify=settings.SUNAT_VERIFY_SSL
    ) as client:
        response = await client.post(
            url,
            data=data,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )

    if response.status_code != 200:
        logger.error(
            "SUNAT token request failed: HTTP %d - %s",
            response.status_code,
            response.text[:500],
        )
        raise SUNATError(f"SUNAT token request failed: HTTP {response.status_code}")

    body = response.json()
    token = body.get("access_token")
    if not token:
        raise SUNATError("SUNAT token response missing access_token")

    logger.info("SUNAT OAuth token obtained (expires_in=%s)", body.get("expires_in"))
    return token


async def call_send_gre(
    *, token: str, filename: str, zip_base64: str, hash_zip: str
) -> str:
    """Send a GRE document via REST API.

    POST https://api-cpe.sunat.gob.pe/v1/contribuyente/gem/comprobantes/{filename}
    Authorization: Bearer {token}
    Content-Type: application/json

    Returns the ticket number (numTicket).
    """
    if not settings.SUNAT_REST_API_URL:
        raise SUNATError("SUNAT_REST_API_URL not configured")

    # URL uses filename without extension; nomArchivo in body includes .zip
    base_name = filename.removesuffix(".zip")
    url = f"{settings.SUNAT_REST_API_URL}/contribuyente/gem/comprobantes/{base_name}"

    payload = {
        "archivo": {
            "nomArchivo": filename,
            "arcGreZip": zip_base64,
            "hashZip": hash_zip,
        }
    }

    async with httpx.AsyncClient(
        timeout=60, verify=settings.SUNAT_VERIFY_SSL
    ) as client:
        response = await client.post(
            url,
            json=payload,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
        )

    if response.status_code not in (200, 201):
        logger.error(
            "SUNAT REST sendGRE failed: HTTP %d - %s",
            response.status_code,
            response.text[:500],
        )
        raise SUNATError(f"SUNAT REST sendGRE failed: HTTP {response.status_code} - {response.text[:200]}")

    body = response.json()
    ticket = body.get("numTicket")
    if not ticket:
        raise SUNATError(f"SUNAT REST sendGRE response missing numTicket: {body}")

    logger.info("SUNAT REST GRE sent, ticket=%s", ticket)
    return ticket


async def call_get_ticket_status(*, token: str, ticket: str) -> dict | None:
    """Query the status of a GRE submission ticket.

    GET https://api-cpe.sunat.gob.pe/v1/contribuyente/gem/comprobantes/envios/{numTicket}
    Authorization: Bearer {token}

    Returns a dict with the response data, or None if not yet processed.
    """
    url = f"{settings.SUNAT_REST_API_URL}/contribuyente/gem/comprobantes/envios/{ticket}"

    async with httpx.AsyncClient(
        timeout=30, verify=settings.SUNAT_VERIFY_SSL
    ) as client:
        response = await client.get(
            url,
            headers={"Authorization": f"Bearer {token}"},
        )

    if response.status_code == 200:
        body = response.json()
        logger.debug("SUNAT ticket %s status response: %s", ticket, body)
        return body

    if response.status_code == 422:
        # Ticket still being processed
        logger.debug("SUNAT ticket %s still processing (HTTP 422)", ticket)
        return None

    logger.error(
        "SUNAT REST ticket query failed: HTTP %d - %s",
        response.status_code,
        response.text[:500],
    )
    raise SUNATError(f"SUNAT REST ticket query failed: HTTP {response.status_code}")
