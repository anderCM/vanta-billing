"""Low-level SOAP HTTP transport for SUNAT web services.

Responsible only for building SOAP envelopes and sending them via HTTP.
No business logic — just transport.
"""

import logging

import httpx
from lxml import etree

from app.config import settings
from app.exceptions import SUNATError

from .constants import (
    ENDPOINT_BILL_SERVICE,
    ENDPOINT_CONSULT_SERVICE,
    NS_SERVICE,
    NS_SOAPENV,
    NS_WSSE,
    GET_STATUS_CDR_TEMPLATE,
    SEND_BILL_TEMPLATE,
    SOAP_ACTION_GET_STATUS_CDR,
    SOAP_ACTION_SEND_BILL,
)

logger = logging.getLogger(__name__)

_SOAP_HEADERS = {"Content-Type": "text/xml; charset=utf-8"}


def _build_send_bill_envelope(
    *, username: str, password: str, filename: str, content_base64: str
) -> str:
    return SEND_BILL_TEMPLATE.format(
        ns_soap=NS_SOAPENV,
        ns_ser=NS_SERVICE,
        ns_wsse=NS_WSSE,
        username=username,
        password=password,
        filename=filename,
        content=content_base64,
    )


def _build_get_status_cdr_envelope(
    *,
    username: str,
    password: str,
    ruc: str,
    doc_type: str,
    series: str,
    correlative: int,
) -> str:
    return GET_STATUS_CDR_TEMPLATE.format(
        ns_soap=NS_SOAPENV,
        ns_ser=NS_SERVICE,
        ns_wsse=NS_WSSE,
        username=username,
        password=password,
        ruc=ruc,
        doc_type=doc_type,
        series=series,
        correlative=correlative,
    )


def _parse_soap_response(response_bytes: bytes) -> etree._Element:
    """Parse SOAP response XML and check for SOAP faults.

    SUNAT may return SOAP faults with HTTP 200 or 500 — both are valid SOAP.
    The namespace prefix varies (soap-env, soapenv, etc.) so we match by URI.
    """
    try:
        root = etree.fromstring(response_bytes)
    except etree.XMLSyntaxError as e:
        raise SUNATError(f"Invalid SOAP XML response: {e}") from e

    soap_ns = f"{{{NS_SOAPENV}}}"

    # Look for Fault inside Body
    body = root.find(f".//{soap_ns}Body")
    if body is None:
        raise SUNATError("Missing SOAP Body in response")

    fault = body.find(f"{soap_ns}Fault")
    if fault is not None:
        fault_code = fault.findtext("faultcode") or ""
        fault_string = fault.findtext("faultstring") or ""
        logger.error("SUNAT SOAP Fault [%s]: %s", fault_code, fault_string)
        raise SUNATError(f"SOAP Fault [{fault_code}]: {fault_string}")

    return body


async def call_send_bill(
    *, username: str, password: str, filename: str, content_base64: str
) -> etree._Element:
    """Send a SOAP sendBill request and return the parsed Body element."""
    envelope = _build_send_bill_envelope(
        username=username,
        password=password,
        filename=filename,
        content_base64=content_base64,
    )

    headers = {**_SOAP_HEADERS, "SOAPAction": SOAP_ACTION_SEND_BILL}

    async with httpx.AsyncClient(
        timeout=60, verify=settings.SUNAT_VERIFY_SSL
    ) as client:
        url = f"{settings.SUNAT_SOAP_URL}{ENDPOINT_BILL_SERVICE}"
        response = await client.post(
            url, content=envelope.encode("utf-8"), headers=headers
        )

    if response.status_code not in (200, 500):
        logger.error(
            "SUNAT SOAP sendBill HTTP error: %d - %s",
            response.status_code,
            response.text[:500],
        )
        raise SUNATError(
            f"SUNAT SOAP HTTP error: {response.status_code}"
        )

    return _parse_soap_response(response.content)


async def call_get_status_cdr(
    *,
    username: str,
    password: str,
    ruc: str,
    doc_type: str,
    series: str,
    correlative: int,
) -> etree._Element:
    """Send a SOAP getStatusCdr request and return the parsed Body element.

    Uses SUNAT_CONSULT_URL (billConsultService), which is only available
    in production. The caller must check that the URL is configured.
    """
    envelope = _build_get_status_cdr_envelope(
        username=username,
        password=password,
        ruc=ruc,
        doc_type=doc_type,
        series=series,
        correlative=correlative,
    )

    headers = {**_SOAP_HEADERS, "SOAPAction": SOAP_ACTION_GET_STATUS_CDR}

    async with httpx.AsyncClient(
        timeout=30, verify=settings.SUNAT_VERIFY_SSL
    ) as client:
        url = f"{settings.SUNAT_CONSULT_URL}{ENDPOINT_CONSULT_SERVICE}"
        response = await client.post(
            url, content=envelope.encode("utf-8"), headers=headers
        )

    if response.status_code not in (200, 500):
        logger.error(
            "SUNAT SOAP getStatusCdr HTTP error: %d - %s",
            response.status_code,
            response.text[:500],
        )
        raise SUNATError(
            f"SUNAT SOAP HTTP error: {response.status_code}"
        )

    return _parse_soap_response(response.content)
