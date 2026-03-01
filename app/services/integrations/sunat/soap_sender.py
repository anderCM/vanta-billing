"""sendBill operation: zip, encode, send, and parse SUNAT response."""

import base64
import hashlib
import io
import logging
import zipfile

from app.exceptions import CDRParseError
from app.services.sunat_catalogs import DocumentStatus

from .cdr_parser import parse_cdr_zip
from .soap_client import call_send_bill

logger = logging.getLogger(__name__)


def _zip_and_encode(xml_content: str, filename: str) -> tuple[str, str]:
    """ZIP the signed XML and return (base64_archive, sha256_hash)."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(f"{filename}.xml", xml_content.encode("utf-8"))

    zip_bytes = buffer.getvalue()
    archive = base64.b64encode(zip_bytes).decode()
    hash_zip = hashlib.sha256(zip_bytes).hexdigest()
    return archive, hash_zip


def _extract_cdr_from_response(body) -> dict:
    """Extract applicationResponse from SOAP Body and parse it.

    The sendBillResponse contains an applicationResponse element
    with the base64-encoded CDR ZIP.
    """
    app_response = body.findtext(".//{http://service.sunat.gob.pe}applicationResponse")
    if not app_response:
        app_response = body.findtext(".//applicationResponse")

    if not app_response:
        return {
            "cdr_content": "",
            "cdr_code": "",
            "cdr_description": "No applicationResponse in SUNAT reply",
            "cdr_notes": [],
            "status": DocumentStatus.ERROR,
        }

    result = {
        "cdr_content": app_response,
        "cdr_code": "",
        "cdr_description": "",
        "cdr_notes": [],
        "status": DocumentStatus.ACCEPTED,
    }

    try:
        parsed = parse_cdr_zip(app_response)
        result["cdr_code"] = parsed["cdr_code"]
        result["cdr_description"] = parsed["cdr_description"]
        result["cdr_notes"] = parsed["cdr_notes"]

        code = parsed["cdr_code"]
        if code and code != "0":
            result["status"] = DocumentStatus.REJECTED
    except CDRParseError as e:
        logger.warning("CDR parsing failed: %s", e)
        result["cdr_description"] = str(e)
        result["status"] = DocumentStatus.ERROR

    return result


async def send_document(
    *,
    xml_signed: str,
    ruc: str,
    document_type: str,
    series: str,
    correlative: int,
    sol_user: str,
    sol_password: str,
) -> dict:
    """Send a signed document to SUNAT via SOAP sendBill.

    Returns a dict with cdr_content, cdr_code, cdr_description, cdr_notes, status.
    """
    filename = f"{ruc}-{document_type}-{series}-{correlative}"
    archive, _hash = _zip_and_encode(xml_signed, filename)

    username = f"{ruc}{sol_user}"

    logger.info("Sending document %s to SUNAT via SOAP", filename)

    body = await call_send_bill(
        username=username,
        password=sol_password,
        filename=f"{filename}.zip",
        content_base64=archive,
    )

    result = _extract_cdr_from_response(body)
    logger.info(
        "Document %s SOAP result: status=%s code=%s",
        filename,
        result["status"],
        result["cdr_code"],
    )
    return result
