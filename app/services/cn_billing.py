import logging
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy.orm import Session

from app.config import settings
from app.exceptions import BillingError, MissingCredentialsError, XMLBuildError, XMLSignError
from app.models.client import Client
from app.models.document import Document
from app.models.document_item import DocumentItem
from app.schemas.credit_note import CreditNoteCreate
from app.services.correlative import attach_next_correlative, next_correlative, rollback_on_pre_sunat_error, set_error_status
from app.services.crypto import decrypt_string
from app.services.integrations.sunat import query_document_status, send_document
from app.services.sunat_catalogs import (
    CREDIT_NOTE_REASON_CODES,
    CUSTOMER_DOC_TYPE_TO_CODE,
    ITEM_TYPE_TO_UNIT_CODE,
    TAX_TYPE_TO_IGV_CODE,
    DocumentStatus,
    IGVGroup,
    peru_issue_date,
    peru_now,
)
from app.services.qr_generator import build_qr_text, extract_signature_values, generate_qr_image
from app.services.xml_builder_cn import build_credit_note_xml
from app.services.xml_signer import sign_xml

logger = logging.getLogger(__name__)

IGV_RATE = Decimal(str(settings.IGV_RATE))

DOCUMENT_TYPE_CREDIT_NOTE = "07"


def _translate_items(data: CreditNoteCreate) -> list[dict]:
    return [
        {
            "description": item.description,
            "quantity": item.quantity,
            "unit_code": ITEM_TYPE_TO_UNIT_CODE[item.item_type.value],
            "unit_price": item.unit_price,
            "unit_price_without_tax": item.unit_price_without_tax,
            "igv_type": TAX_TYPE_TO_IGV_CODE[item.tax_type.value],
        }
        for item in data.items
    ]


def _calculate_items(items_data: list[dict]) -> tuple[list[dict], Decimal, Decimal, Decimal]:
    """Calculate SUNAT line amounts.

    If unit_price_without_tax is provided, it is used directly as the base price
    (no division, no rounding amplification). Otherwise, falls back to extracting
    the base price from the IGV-inclusive unit_price via unit_price / 1.18.
    """
    calculated = []
    total_gravada = Decimal("0")
    total_exonerada = Decimal("0")
    total_inafecta = Decimal("0")
    total_igv = Decimal("0")

    for item in items_data:
        qty = Decimal(str(item["quantity"]))
        unit_price = Decimal(str(item["unit_price"]))
        unit_price_without_tax = (
            Decimal(str(item["unit_price_without_tax"]))
            if item.get("unit_price_without_tax") is not None
            else None
        )
        igv_type = item["igv_type"]

        if igv_type.startswith(IGVGroup.GRAVADO):
            price_with_igv = unit_price
            if unit_price_without_tax is not None:
                base_price = unit_price_without_tax
            else:
                base_price = (unit_price / (1 + IGV_RATE)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            line_extension = (qty * base_price).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            igv = (line_extension * IGV_RATE).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            total_gravada += line_extension
        elif igv_type.startswith(IGVGroup.EXONERADO):
            base_price = unit_price_without_tax if unit_price_without_tax is not None else unit_price
            price_with_igv = unit_price
            line_extension = (qty * base_price).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            igv = Decimal("0.00")
            total_exonerada += line_extension
        else:
            base_price = unit_price_without_tax if unit_price_without_tax is not None else unit_price
            price_with_igv = unit_price
            line_extension = (qty * base_price).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            igv = Decimal("0.00")
            total_inafecta += line_extension

        line_total = line_extension + igv
        total_igv += igv

        calculated.append({
            "description": item["description"],
            "quantity": qty,
            "unit_code": item["unit_code"],
            "unit_price": base_price,
            "unit_price_without_tax": unit_price_without_tax,
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


async def create_and_send_credit_note(
    db: Session,
    client: Client,
    *,
    data: CreditNoteCreate,
) -> Document:
    """Full flow: validate ref → calculate → persist → XML → sign → send to SUNAT."""
    _validate_client_credentials(client)

    # Resolve reference document
    ref_document = db.query(Document).filter(
        Document.id == data.reference_document_id,
        Document.client_id == client.id,
    ).first()
    if not ref_document:
        raise BillingError("Reference document not found")
    if ref_document.document_type not in ("01", "03"):
        raise BillingError("Credit notes can only reference invoices (01) or receipts (03)")

    reason_code = CREDIT_NOTE_REASON_CODES[data.reason_code.value]

    items_data = _translate_items(data)
    calculated_items, total_gravada, total_igv, total_amount = _calculate_items(items_data)

    series = data.series
    correlative = next_correlative(db, client.id, DOCUMENT_TYPE_CREDIT_NOTE, series)
    issue_date = peru_issue_date()

    document = Document(
        client_id=client.id,
        document_type=DOCUMENT_TYPE_CREDIT_NOTE,
        series=series,
        correlative=correlative,
        customer_doc_type=ref_document.customer_doc_type,
        customer_doc_number=ref_document.customer_doc_number,
        customer_name=ref_document.customer_name,
        customer_address=ref_document.customer_address,
        issue_date=peru_now(),
        currency=ref_document.currency,
        total_gravada=total_gravada,
        total_igv=total_igv,
        total_amount=total_amount,
        payment_condition="contado",
        credit_note_reason_code=reason_code,
        credit_note_description=data.description,
        reference_document_id=ref_document.id,
        reference_document_type=ref_document.document_type,
        reference_document_series=ref_document.series,
        reference_document_correlative=ref_document.correlative,
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
            unit_price_without_tax=item["unit_price_without_tax"],
            igv_type=item["igv_type"],
            igv=item["igv"],
            total=item["total"],
        ))
    db.flush()

    logger.info(
        "Credit note %s created: 07-%s-%d referencing %s-%s-%d for client %s",
        document.id, series, correlative,
        ref_document.document_type, ref_document.series, ref_document.correlative,
        client.id,
    )

    # Build XML
    try:
        xml_content = build_credit_note_xml(
            series=series,
            correlative=correlative,
            issue_date=issue_date,
            currency=ref_document.currency,
            supplier_ruc=client.ruc,
            supplier_name=client.razon_social,
            supplier_trade_name=client.nombre_comercial,
            supplier_address=client.direccion,
            supplier_ubigeo=client.ubigeo,
            customer_doc_type=ref_document.customer_doc_type,
            customer_doc_number=ref_document.customer_doc_number,
            customer_name=ref_document.customer_name,
            customer_address=ref_document.customer_address,
            reason_code=reason_code,
            description=data.description,
            ref_document_type=ref_document.document_type,
            ref_series=ref_document.series,
            ref_correlative=ref_document.correlative,
            items=calculated_items,
            total_gravada=total_gravada,
            total_igv=total_igv,
            total_amount=total_amount,
        )
        document.xml_content = xml_content
    except (ValueError, KeyError, TypeError) as e:
        logger.error("XML build failed for credit note %s: %s", document.id, e)
        rollback_on_pre_sunat_error(db)
        raise XMLBuildError(f"Failed to build XML: {e}") from e

    # Sign XML
    try:
        xml_signed = sign_xml(xml_content, client.certificate, client.certificate_password)
        document.xml_signed = xml_signed
        document.status = DocumentStatus.SIGNED
    except (ValueError, OSError) as e:
        logger.error("XML signing failed for credit note %s: %s", document.id, e)
        rollback_on_pre_sunat_error(db)
        raise XMLSignError(f"Failed to sign XML: {e}") from e

    # Generate QR code
    try:
        digest_value, signature_value = extract_signature_values(xml_signed)
        qr_text = build_qr_text(
            ruc=client.ruc,
            document_type=DOCUMENT_TYPE_CREDIT_NOTE,
            series=series,
            correlative=correlative,
            total_igv=str(total_igv),
            total_amount=str(total_amount),
            issue_date=issue_date,
            customer_doc_type=ref_document.customer_doc_type,
            customer_doc_number=ref_document.customer_doc_number,
            digest_value=digest_value,
            signature_value=signature_value,
        )
        document.qr_text = qr_text
        document.qr_image = generate_qr_image(qr_text)
    except Exception as e:
        logger.warning("QR generation failed for credit note %s: %s", document.id, e)

    # Send to SUNAT
    try:
        sol_user = decrypt_string(client.sol_user)
        sol_password = decrypt_string(client.sol_password)

        cdr = await send_document(
            xml_signed=xml_signed,
            ruc=client.ruc,
            document_type=DOCUMENT_TYPE_CREDIT_NOTE,
            series=series,
            correlative=correlative,
            sol_user=sol_user,
            sol_password=sol_password,
        )

        document.cdr_content = cdr.get("cdr_content")
        document.cdr_code = cdr.get("cdr_code")
        document.cdr_description = cdr.get("cdr_description")
        document.status = cdr.get("status", DocumentStatus.SENT)

        logger.info(
            "Credit note %s sent to SUNAT: status=%s code=%s",
            document.id, document.status, document.cdr_code,
        )
    except BillingError as e:
        logger.error("SUNAT send failed for credit note %s: %s", document.id, e)
        document.cdr_description = str(e)
        set_error_status(db, document)
    else:
        db.commit()

    db.refresh(document)
    attach_next_correlative(db, document, client.id, DOCUMENT_TYPE_CREDIT_NOTE, series)
    return document


async def retry_send_credit_note(db: Session, client: Client, document: Document) -> Document:
    """Retry sending a credit note in SIGNED, ERROR or REJECTED status."""
    _validate_client_credentials(client)

    retryable = {DocumentStatus.SIGNED, DocumentStatus.ERROR, DocumentStatus.REJECTED}
    if document.status not in retryable:
        raise BillingError(f"Cannot retry document in status '{document.status}'")
    if not document.xml_signed:
        raise BillingError("Document has no signed XML to send")

    logger.info("Retrying send for credit note %s (current status: %s)", document.id, document.status)

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

        logger.info("Retry successful for credit note %s: status=%s", document.id, document.status)
    except BillingError as e:
        logger.error("SUNAT send failed for credit note %s: %s", document.id, e)
        document.cdr_description = str(e)
        set_error_status(db, document)
        raise

    db.commit()
    db.refresh(document)
    return document
