"""QR code generation for SUNAT electronic documents."""

import base64
import io
import logging

from lxml import etree
import qrcode

logger = logging.getLogger(__name__)

_DS_NS = "http://www.w3.org/2000/09/xmldsig#"


def extract_signature_values(xml_signed: str) -> tuple[str, str]:
    """Extract DigestValue and SignatureValue from signed XML.

    Returns (digest_value, signature_value).
    """
    root = etree.fromstring(xml_signed.encode("utf-8"))

    digest = root.find(f".//{{{_DS_NS}}}DigestValue")
    signature = root.find(f".//{{{_DS_NS}}}SignatureValue")

    if digest is None or signature is None:
        raise ValueError("Signed XML missing DigestValue or SignatureValue")

    return digest.text.strip(), signature.text.strip()


def build_qr_text(
    *,
    ruc: str,
    document_type: str,
    series: str,
    correlative: int,
    total_igv: str,
    total_amount: str,
    issue_date: str,
    customer_doc_type: str,
    customer_doc_number: str,
    digest_value: str,
    signature_value: str,
) -> str:
    """Build the pipe-separated QR text per SUNAT specification.

    Format: RUC|TIPO_DOC|SERIE|CORRELATIVO|IGV|TOTAL|FECHA|TIPO_DOC_RECEPTOR|NRO_DOC_RECEPTOR|DIGEST|SIGNATURE
    """
    return "|".join([
        ruc,
        document_type,
        series,
        str(correlative),
        str(total_igv),
        str(total_amount),
        issue_date,
        customer_doc_type,
        customer_doc_number,
        digest_value,
        signature_value,
    ])


def generate_qr_image(qr_text: str) -> str:
    """Generate a QR code PNG image and return it as a base64 data URI."""
    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=10,
        border=4,
    )
    qr.add_data(qr_text)
    qr.make(fit=True)

    img = qr.make_image(fill_color="black", back_color="white")

    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    b64 = base64.b64encode(buffer.getvalue()).decode("ascii")

    return f"data:image/png;base64,{b64}"
