"""Parse SUNAT CDR (Constancia de Recepción) from base64-encoded ZIP."""

import base64
import io
import zipfile

from lxml import etree

from app.exceptions import CDRParseError

_CDR_NAMESPACES = {
    "ar": "urn:oasis:names:specification:ubl:schema:xsd:ApplicationResponse-2",
    "cac": "urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2",
    "cbc": "urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2",
}


def parse_cdr_zip(arc_cdr_base64: str) -> dict:
    """Decode CDR ZIP from base64, extract XML, and parse the ApplicationResponse.

    Returns a dict with cdr_code, cdr_description, and cdr_notes.
    """
    try:
        cdr_zip_bytes = base64.b64decode(arc_cdr_base64)
    except (ValueError, base64.binascii.Error) as e:
        raise CDRParseError(f"Invalid base64 in CDR: {e}") from e

    try:
        with zipfile.ZipFile(io.BytesIO(cdr_zip_bytes)) as zf:
            xml_files = [n for n in zf.namelist() if n.lower().endswith(".xml")]
            if not xml_files:
                raise CDRParseError("No XML file found in CDR ZIP")
            cdr_xml = zf.read(xml_files[0])
    except (zipfile.BadZipFile, IndexError) as e:
        raise CDRParseError(f"Invalid CDR ZIP: {e}") from e

    try:
        root = etree.fromstring(cdr_xml)
    except etree.XMLSyntaxError as e:
        raise CDRParseError(f"Invalid CDR XML: {e}") from e

    response_code = (
        root.findtext(
            ".//cac:DocumentResponse/cac:Response/cbc:ResponseCode",
            namespaces=_CDR_NAMESPACES,
        )
        or ""
    )
    description = (
        root.findtext(
            ".//cac:DocumentResponse/cac:Response/cbc:Description",
            namespaces=_CDR_NAMESPACES,
        )
        or ""
    )

    notes = [
        note.text
        for note in root.findall(".//cbc:Note", namespaces=_CDR_NAMESPACES)
        if note.text
    ]

    return {
        "cdr_code": response_code,
        "cdr_description": description,
        "cdr_notes": notes,
    }
