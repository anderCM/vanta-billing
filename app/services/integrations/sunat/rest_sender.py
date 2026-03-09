"""GRE REST sender: zip, encode, send, poll for CDR via SUNAT REST API."""

import asyncio
import logging

from app.exceptions import CDRParseError
from app.services.sunat_catalogs import DocumentStatus

from .cdr_parser import parse_cdr_zip
from .rest_client import call_get_ticket_status, call_send_gre, get_sunat_token
from .soap_sender import _zip_and_encode

logger = logging.getLogger(__name__)

# Polling config
_POLL_MAX_ATTEMPTS = 5
_POLL_DELAY_SECONDS = 2


def _extract_cdr_from_ticket_response(body: dict) -> dict:
    """Extract CDR data from a ticket status response.

    The ticket response contains:
    - codRespuesta: response code
    - arcCdr: base64-encoded CDR ZIP (when available)
    - indCdrGenerado: whether CDR was generated
    """
    cdr_code = body.get("codRespuesta", "")
    cdr_description = body.get("desMensaje", "")
    arc_cdr = body.get("arcCdr", "")

    result = {
        "cdr_content": arc_cdr,
        "cdr_code": str(cdr_code),
        "cdr_description": cdr_description,
        "cdr_notes": [],
        "status": DocumentStatus.ACCEPTED,
    }

    # Parse CDR ZIP if available
    if arc_cdr:
        try:
            parsed = parse_cdr_zip(arc_cdr)
            result["cdr_code"] = parsed["cdr_code"] or str(cdr_code)
            result["cdr_description"] = parsed["cdr_description"] or cdr_description
            result["cdr_notes"] = parsed["cdr_notes"]

            code = parsed["cdr_code"]
            if code and code != "0":
                result["status"] = DocumentStatus.REJECTED
        except CDRParseError as e:
            logger.warning("CDR parsing failed for GRE ticket: %s", e)
            result["cdr_description"] = str(e)
            result["status"] = DocumentStatus.ERROR
    else:
        # No CDR but we have a response code
        if cdr_code and str(cdr_code) != "0":
            result["status"] = DocumentStatus.REJECTED

    return result


async def send_gre_document(
    *,
    xml_signed: str,
    ruc: str,
    document_type: str,
    series: str,
    correlative: int,
    sol_user: str,
    sol_password: str,
    sunat_client_id: str | None = None,
    sunat_client_secret: str | None = None,
) -> dict:
    """Send a signed GRE document to SUNAT via REST API.

    Flow:
    1. ZIP and base64-encode the signed XML
    2. Get OAuth2 token from SUNAT
    3. POST the document, receive a ticket number
    4. Poll for ticket status until CDR is available

    Returns a dict with cdr_content, cdr_code, cdr_description, cdr_notes, status.
    """
    filename = f"{ruc}-{document_type}-{series}-{correlative:08d}"
    zip_base64, hash_zip = _zip_and_encode(xml_signed, filename)

    logger.info("Sending GRE %s to SUNAT via REST API", filename)

    # Step 1: Get token
    token = await get_sunat_token(
        ruc=ruc,
        sol_user=sol_user,
        sol_password=sol_password,
        sunat_client_id=sunat_client_id,
        sunat_client_secret=sunat_client_secret,
    )

    # Step 2: Send document
    ticket = await call_send_gre(
        token=token,
        filename=f"{filename}.zip",
        zip_base64=zip_base64,
        hash_zip=hash_zip,
    )

    # Step 3: Poll for ticket status
    for attempt in range(1, _POLL_MAX_ATTEMPTS + 1):
        await asyncio.sleep(_POLL_DELAY_SECONDS)

        logger.info(
            "Polling GRE ticket %s (attempt %d/%d)",
            ticket, attempt, _POLL_MAX_ATTEMPTS,
        )

        ticket_response = await call_get_ticket_status(
            token=token, ticket=ticket
        )

        if ticket_response is not None:
            result = _extract_cdr_from_ticket_response(ticket_response)
            logger.info(
                "GRE %s REST result: status=%s code=%s",
                filename, result["status"], result["cdr_code"],
            )
            return result

    # Exhausted retries — mark as SENT with ticket info
    logger.warning(
        "GRE %s ticket %s not resolved after %d attempts",
        filename, ticket, _POLL_MAX_ATTEMPTS,
    )
    return {
        "cdr_content": "",
        "cdr_code": "",
        "cdr_description": f"Ticket {ticket} pendiente de procesamiento en SUNAT",
        "cdr_notes": [],
        "status": DocumentStatus.SENT,
        "ticket": ticket,
    }
