"""getStatusCdr operation: query document status from SUNAT."""

import logging

from app.exceptions import CDRParseError
from app.services.sunat_catalogs import DocumentStatus

from .cdr_parser import parse_cdr_zip
from .soap_client import call_get_status_cdr

logger = logging.getLogger(__name__)


def _extract_status_from_response(body) -> dict:
    """Extract statusCdr from SOAP Body and parse it.

    The getStatusCdrResponse contains:
    - statusCode: response status code
    - statusMessage: response description
    - content: base64-encoded CDR ZIP (optional)
    """
    ns = "{http://service.sunat.gob.pe}"

    status_code = body.findtext(f".//{ns}statusCode") or body.findtext(".//statusCode") or ""
    status_message = body.findtext(f".//{ns}statusMessage") or body.findtext(".//statusMessage") or ""
    content = body.findtext(f".//{ns}content") or body.findtext(".//content") or ""

    result = {
        "cdr_content": content,
        "cdr_code": status_code,
        "cdr_description": status_message,
        "cdr_notes": [],
        "status": DocumentStatus.ACCEPTED if status_code == "0" else DocumentStatus.REJECTED,
    }

    if content:
        try:
            parsed = parse_cdr_zip(content)
            result["cdr_code"] = parsed["cdr_code"] or status_code
            result["cdr_description"] = parsed["cdr_description"] or status_message
            result["cdr_notes"] = parsed["cdr_notes"]
        except CDRParseError as e:
            logger.warning("CDR parsing failed in status query: %s", e)

    return result


async def query_document_status(
    *,
    ruc: str,
    document_type: str,
    series: str,
    correlative: int,
    sol_user: str,
    sol_password: str,
) -> dict:
    """Query SUNAT for the status of a previously sent document.

    Returns a dict with cdr_content, cdr_code, cdr_description, cdr_notes, status.
    """
    username = f"{ruc}{sol_user}"
    doc_id = f"{ruc}-{document_type}-{series}-{correlative:08d}"

    logger.info("Querying SUNAT status for %s via SOAP", doc_id)

    body = await call_get_status_cdr(
        username=username,
        password=sol_password,
        ruc=ruc,
        doc_type=document_type,
        series=series,
        correlative=correlative,
    )

    result = _extract_status_from_response(body)
    logger.info(
        "Status query for %s: status=%s code=%s",
        doc_id,
        result["status"],
        result["cdr_code"],
    )
    return result
