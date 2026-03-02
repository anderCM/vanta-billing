import logging
from datetime import datetime, timezone
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import settings
from app.exceptions import BillingError, MissingCredentialsError, XMLBuildError, XMLSignError
from app.models.client import Client
from app.models.document import Document
from app.models.document_item import DocumentItem
from app.schemas.document import InvoiceCreate, ReceiptCreate
from app.services.crypto import decrypt_string
from app.services.integrations.sunat import query_document_status, send_document
from app.services.sunat_catalogs import (
    CUSTOMER_DOC_TYPE_TO_CODE,
    ITEM_TYPE_TO_UNIT_CODE,
    TAX_TYPE_TO_IGV_CODE,
    DocumentStatus,
    IGVGroup,
)
from app.services.qr_generator import build_qr_text, extract_signature_values, generate_qr_image
from app.services.xml_builder import build_invoice_xml
from app.services.xml_signer import sign_xml

logger = logging.getLogger(__name__)

IGV_RATE = Decimal(str(settings.IGV_RATE))


def _next_correlative(db: Session, client_id: str, document_type: str, series: str) -> int:
    result = db.execute(
        text(
            """
            INSERT INTO document_series (client_id, document_type, series, current_correlative)
            VALUES (:client_id, :doc_type, :series, 1)
            ON CONFLICT ON CONSTRAINT uq_client_doc_type_series
            DO UPDATE SET current_correlative = document_series.current_correlative + 1
            RETURNING current_correlative
            """
        ),
        {"client_id": client_id, "doc_type": document_type, "series": series},
    )
    return result.scalar_one()


def _translate_items(data: InvoiceCreate | ReceiptCreate) -> list[dict]:
    """Translate user-friendly schema values to SUNAT catalog codes."""
    return [
        {
            "description": item.description,
            "quantity": item.quantity,
            "unit_code": ITEM_TYPE_TO_UNIT_CODE[item.item_type.value],
            "unit_price": item.unit_price,
            "igv_type": TAX_TYPE_TO_IGV_CODE[item.tax_type.value],
        }
        for item in data.items
    ]


def _calculate_items(items_data: list[dict]) -> tuple[list[dict], Decimal, Decimal, Decimal]:
    calculated = []
    total_gravada = Decimal("0")
    total_exonerada = Decimal("0")
    total_inafecta = Decimal("0")
    total_igv = Decimal("0")

    for item in items_data:
        qty = Decimal(str(item["quantity"]))
        unit_price = Decimal(str(item["unit_price"]))
        igv_type = item["igv_type"]

        line_extension = (qty * unit_price).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        if igv_type.startswith(IGVGroup.GRAVADO):
            igv = (line_extension * IGV_RATE).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            price_with_igv = (unit_price * (1 + IGV_RATE)).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
            total_gravada += line_extension
        elif igv_type.startswith(IGVGroup.EXONERADO):
            igv = Decimal("0.00")
            price_with_igv = unit_price
            total_exonerada += line_extension
        else:  # IGVGroup.INAFECTO
            igv = Decimal("0.00")
            price_with_igv = unit_price
            total_inafecta += line_extension

        line_total = line_extension + igv
        total_igv += igv

        calculated.append({
            "description": item["description"],
            "quantity": qty,
            "unit_code": item["unit_code"],
            "unit_price": unit_price,
            "igv_type": igv_type,
            "line_extension": line_extension,
            "igv": igv,
            "total": line_total,
            "price_with_igv": price_with_igv,
        })

    total_amount = total_gravada + total_exonerada + total_inafecta + total_igv
    return calculated, total_gravada, total_igv, total_amount


def _validate_client_credentials(client: Client) -> None:
    if not client.sol_user or not client.sol_password:
        raise MissingCredentialsError("SOL credentials not configured")
    if not client.certificate or not client.certificate_password:
        raise MissingCredentialsError("Digital certificate not uploaded")


def _set_error_status(db: Session, document: Document) -> None:
    """Mark document as ERROR and commit. Used when the flow fails after persistence."""
    document.status = DocumentStatus.ERROR
    db.commit()


async def create_and_send_document(
    db: Session,
    client: Client,
    *,
    document_type: str,
    data: InvoiceCreate | ReceiptCreate,
) -> Document:
    """Full flow: translate → calculate → persist → XML → sign → send to SUNAT."""
    _validate_client_credentials(client)

    items_data = _translate_items(data)
    customer_doc_type = CUSTOMER_DOC_TYPE_TO_CODE[data.customer_doc_type.value]
    calculated_items, total_gravada, total_igv, total_amount = _calculate_items(items_data)

    correlative = _next_correlative(db, client.id, document_type, data.series)
    issue_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    document = Document(
        client_id=client.id,
        document_type=document_type,
        series=data.series,
        correlative=correlative,
        customer_doc_type=customer_doc_type,
        customer_doc_number=data.customer_doc_number,
        customer_name=data.customer_name,
        customer_address=data.customer_address,
        issue_date=datetime.now(timezone.utc),
        currency=data.currency,
        total_gravada=total_gravada,
        total_igv=total_igv,
        total_amount=total_amount,
        status=DocumentStatus.CREATED,
    )
    db.add(document)
    db.flush()

    for item in calculated_items:
        db.add(DocumentItem(
            document_id=document.id,
            description=item["description"],
            quantity=item["quantity"],
            unit_code=item["unit_code"],
            unit_price=item["unit_price"],
            igv_type=item["igv_type"],
            igv=item["igv"],
            total=item["total"],
        ))
    db.flush()

    logger.info(
        "Document %s created: %s-%s-%d for client %s",
        document.id, document_type, data.series, correlative, client.id,
    )

    # Build XML
    try:
        xml_content = build_invoice_xml(
            document_type=document_type,
            series=data.series,
            correlative=correlative,
            issue_date=issue_date,
            currency=data.currency,
            supplier_ruc=client.ruc,
            supplier_name=client.razon_social,
            supplier_trade_name=client.nombre_comercial,
            supplier_address=client.direccion,
            supplier_ubigeo=client.ubigeo,
            customer_doc_type=customer_doc_type,
            customer_doc_number=data.customer_doc_number,
            customer_name=data.customer_name,
            customer_address=data.customer_address,
            items=calculated_items,
            total_gravada=total_gravada,
            total_igv=total_igv,
            total_amount=total_amount,
        )
        document.xml_content = xml_content
    except (ValueError, KeyError, TypeError) as e:
        logger.error("XML build failed for document %s: %s", document.id, e)
        _set_error_status(db, document)
        raise XMLBuildError(f"Failed to build XML: {e}") from e

    # Sign XML
    try:
        xml_signed = sign_xml(xml_content, client.certificate, client.certificate_password)
        document.xml_signed = xml_signed
        document.status = DocumentStatus.SIGNED
    except (ValueError, OSError) as e:
        logger.error("XML signing failed for document %s: %s", document.id, e)
        _set_error_status(db, document)
        raise XMLSignError(f"Failed to sign XML: {e}") from e

    # Generate QR code
    try:
        digest_value, signature_value = extract_signature_values(xml_signed)
        qr_text = build_qr_text(
            ruc=client.ruc,
            document_type=document_type,
            series=data.series,
            correlative=correlative,
            total_igv=str(total_igv),
            total_amount=str(total_amount),
            issue_date=issue_date,
            customer_doc_type=customer_doc_type,
            customer_doc_number=data.customer_doc_number,
            digest_value=digest_value,
            signature_value=signature_value,
        )
        document.qr_text = qr_text
        document.qr_image = generate_qr_image(qr_text)
    except Exception as e:
        logger.warning("QR generation failed for document %s: %s", document.id, e)

    # Send to SUNAT
    try:
        sol_user = decrypt_string(client.sol_user)
        sol_password = decrypt_string(client.sol_password)

        cdr = await send_document(
            xml_signed=xml_signed,
            ruc=client.ruc,
            document_type=document_type,
            series=data.series,
            correlative=correlative,
            sol_user=sol_user,
            sol_password=sol_password,
        )

        document.cdr_content = cdr.get("cdr_content")
        document.cdr_code = cdr.get("cdr_code")
        document.cdr_description = cdr.get("cdr_description")
        document.status = cdr.get("status", DocumentStatus.SENT)

        logger.info(
            "Document %s sent to SUNAT: status=%s code=%s",
            document.id, document.status, document.cdr_code,
        )
    except BillingError:
        _set_error_status(db, document)
        raise

    db.commit()
    db.refresh(document)
    return document


async def retry_send_document(db: Session, client: Client, document: Document) -> Document:
    """Retry sending a document in SIGNED, ERROR or REJECTED status."""
    _validate_client_credentials(client)

    retryable = {DocumentStatus.SIGNED, DocumentStatus.ERROR, DocumentStatus.REJECTED}
    if document.status not in retryable:
        raise BillingError(f"Cannot retry document in status '{document.status}'")
    if not document.xml_signed:
        raise BillingError("Document has no signed XML to send")

    logger.info("Retrying send for document %s (current status: %s)", document.id, document.status)

    sol_user = decrypt_string(client.sol_user)
    sol_password = decrypt_string(client.sol_password)

    try:
        cdr = await send_document(
            xml_signed=document.xml_signed,
            ruc=client.ruc,
            document_type=document.document_type,
            series=document.series,
            correlative=document.correlative,
            sol_user=sol_user,
            sol_password=sol_password,
        )

        document.cdr_content = cdr.get("cdr_content")
        document.cdr_code = cdr.get("cdr_code")
        document.cdr_description = cdr.get("cdr_description")
        document.status = cdr.get("status", DocumentStatus.SENT)

        logger.info("Retry successful for document %s: status=%s", document.id, document.status)
    except BillingError:
        _set_error_status(db, document)
        raise

    db.commit()
    db.refresh(document)
    return document


async def check_document_status(db: Session, client: Client, document: Document) -> Document:
    """Query SUNAT for the current status of a document.

    If SUNAT_CONSULT_URL is not configured (beta environment), returns
    the document with its current locally stored status without querying SUNAT.
    """
    _validate_client_credentials(client)

    sol_user = decrypt_string(client.sol_user)
    sol_password = decrypt_string(client.sol_password)

    logger.info("Querying SUNAT status for document %s", document.id)

    cdr = await query_document_status(
        ruc=client.ruc,
        document_type=document.document_type,
        series=document.series,
        correlative=document.correlative,
        sol_user=sol_user,
        sol_password=sol_password,
    )

    if cdr is None:
        logger.info(
            "No SUNAT consult service configured, returning local status for document %s: status=%s",
            document.id, document.status,
        )
        return document

    document.cdr_content = cdr.get("cdr_content") or document.cdr_content
    document.cdr_code = cdr.get("cdr_code") or document.cdr_code
    document.cdr_description = cdr.get("cdr_description") or document.cdr_description
    document.status = cdr.get("status", document.status)

    logger.info("Status query result for document %s: status=%s", document.id, document.status)

    db.commit()
    db.refresh(document)
    return document
