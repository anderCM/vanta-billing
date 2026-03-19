"""Orchestration for Guías de Remisión: persist → build XML → sign → send SUNAT."""

import logging

from sqlalchemy.orm import Session

from app.exceptions import BillingError, MissingCredentialsError, XMLBuildError, XMLSignError
from app.models.client import Client
from app.models.dispatch_guide import DispatchGuide
from app.models.dispatch_guide_item import DispatchGuideItem
from app.models.document import Document
from app.schemas.dispatch_guide import GRRCreate, GRTCreate
from app.services.correlative import attach_next_correlative, next_correlative, rollback_on_pre_sunat_error, set_error_status
from app.services.crypto import decrypt_string
from app.services.integrations.sunat import send_gre_document
from app.services.sunat_catalogs import (
    CUSTOMER_DOC_TYPE_TO_CODE,
    TRANSFER_REASON_CODES,
    TRANSPORT_MODALITY_CODES,
    DocumentStatus,
    peru_issue_date,
    peru_now,
)
from app.services.qr_generator import (
    build_dispatch_guide_qr_text,
    extract_signature_values,
    generate_qr_image,
)
from app.services.xml_builder_gr import build_despatch_advice_xml
from app.services.xml_signer import sign_xml

logger = logging.getLogger(__name__)


def _validate_client_credentials(client: Client) -> None:
    if not client.sol_user or not client.sol_password:
        raise MissingCredentialsError("SOL credentials not configured")
    if not client.certificate or not client.certificate_password:
        raise MissingCredentialsError("Digital certificate not uploaded")
    if not client.sunat_client_id or not client.sunat_client_secret:
        from app.config import settings
        if not settings.SUNAT_REST_CLIENT_ID or not settings.SUNAT_REST_KEY:
            raise MissingCredentialsError(
                "SUNAT REST API credentials (sunat_client_id/sunat_client_secret) not configured. "
                "Register your application in SUNAT's SOL portal and configure these credentials."
            )


async def create_and_send_dispatch_guide(
    db: Session,
    client: Client,
    *,
    document_type: str,
    data: GRRCreate | GRTCreate,
) -> DispatchGuide:
    """Full GR flow: persist → build XML → sign → send to SUNAT."""
    _validate_client_credentials(client)

    transfer_reason_code = TRANSFER_REASON_CODES[data.transfer_reason.value]
    transport_modality_code = TRANSPORT_MODALITY_CODES[data.transport_modality.value]
    recipient_doc_type_code = CUSTOMER_DOC_TYPE_TO_CODE[data.recipient_doc_type.value]

    # Resolve related document if provided
    related_doc_type = None
    related_doc_number = None
    if data.related_document_id:
        related_doc = db.query(Document).filter(
            Document.id == data.related_document_id,
            Document.client_id == client.id,
        ).first()
        if not related_doc:
            raise BillingError("Related document not found or does not belong to this client")
        related_doc_type = related_doc.document_type
        related_doc_number = f"{related_doc.series}-{related_doc.correlative:08d}"

    correlative = next_correlative(db, client.id, document_type, data.series)
    now = peru_now()
    issue_date = now.strftime("%Y-%m-%d")
    issue_time = now.strftime("%H:%M:%S")

    guide = DispatchGuide(
        client_id=client.id,
        document_type=document_type,
        series=data.series,
        correlative=correlative,
        transfer_reason=transfer_reason_code,
        transport_modality=transport_modality_code,
        transfer_date=data.transfer_date,
        gross_weight=data.gross_weight,
        weight_unit_code=data.weight_unit_code,
        departure_address=data.departure_address,
        departure_ubigeo=data.departure_ubigeo,
        arrival_address=data.arrival_address,
        arrival_ubigeo=data.arrival_ubigeo,
        recipient_doc_type=recipient_doc_type_code,
        recipient_doc_number=data.recipient_doc_number,
        recipient_name=data.recipient_name,
        related_document_id=data.related_document_id,
        related_document_type=related_doc_type,
        related_document_number=related_doc_number,
        issue_date=peru_now(),
        status=DocumentStatus.CREATED,
    )

    # GRR-specific fields
    if document_type == "09":
        guide.carrier_ruc = getattr(data, "carrier_ruc", None)
        guide.carrier_name = getattr(data, "carrier_name", None)
        guide.vehicle_plate = getattr(data, "vehicle_plate", None)
        if getattr(data, "driver_doc_type", None):
            guide.driver_doc_type = CUSTOMER_DOC_TYPE_TO_CODE.get(data.driver_doc_type.value)
        guide.driver_doc_number = getattr(data, "driver_doc_number", None)
        guide.driver_name = getattr(data, "driver_name", None)
        guide.driver_license = getattr(data, "driver_license", None)

    # GRT-specific fields
    if document_type == "31":
        guide.shipper_doc_type = CUSTOMER_DOC_TYPE_TO_CODE.get(data.shipper_doc_type.value)
        guide.shipper_doc_number = data.shipper_doc_number
        guide.shipper_name = data.shipper_name
        guide.vehicle_plate = data.vehicle_plate
        guide.driver_doc_type = CUSTOMER_DOC_TYPE_TO_CODE.get(data.driver_doc_type.value)
        guide.driver_doc_number = data.driver_doc_number
        guide.driver_name = data.driver_name
        guide.driver_license = data.driver_license

    db.add(guide)
    db.flush()

    for item in data.items:
        db.add(
            DispatchGuideItem(
                guide_id=guide.id,
                description=item.description,
                quantity=item.quantity,
                unit_code=item.unit_code,
            )
        )
    db.flush()

    logger.info(
        "DispatchGuide %s created: %s-%s-%d for client %s",
        guide.id,
        document_type,
        data.series,
        correlative,
        client.id,
    )

    # Build XML
    try:
        items_for_xml = [
            {
                "description": i.description,
                "quantity": i.quantity,
                "unit_code": i.unit_code,
            }
            for i in data.items
        ]
        xml_content = build_despatch_advice_xml(
            document_type=document_type,
            series=data.series,
            correlative=correlative,
            issue_date=issue_date,
            issue_time=issue_time,
            supplier_ruc=client.ruc,
            supplier_name=client.razon_social,
            supplier_address=client.direccion,
            supplier_ubigeo=client.ubigeo,
            recipient_doc_type=recipient_doc_type_code,
            recipient_doc_number=data.recipient_doc_number,
            recipient_name=data.recipient_name,
            transfer_reason=transfer_reason_code,
            transport_modality=transport_modality_code,
            transfer_date=data.transfer_date,
            gross_weight=data.gross_weight,
            weight_unit_code=data.weight_unit_code,
            departure_address=data.departure_address,
            departure_ubigeo=data.departure_ubigeo,
            arrival_address=data.arrival_address,
            arrival_ubigeo=data.arrival_ubigeo,
            carrier_ruc=guide.carrier_ruc,
            carrier_name=guide.carrier_name,
            vehicle_plate=guide.vehicle_plate,
            driver_doc_type=guide.driver_doc_type,
            driver_doc_number=guide.driver_doc_number,
            driver_name=guide.driver_name,
            driver_license=guide.driver_license,
            shipper_doc_type=guide.shipper_doc_type,
            shipper_doc_number=guide.shipper_doc_number,
            shipper_name=guide.shipper_name,
            related_document_type=related_doc_type,
            related_document_number=related_doc_number,
            items=items_for_xml,
        )
        guide.xml_content = xml_content
    except (ValueError, KeyError, TypeError) as e:
        logger.error("XML build failed for dispatch guide %s: %s", guide.id, e)
        rollback_on_pre_sunat_error(db)
        raise XMLBuildError(f"Failed to build GR XML: {e}") from e

    # Sign XML
    try:
        xml_signed = sign_xml(xml_content, client.certificate, client.certificate_password)
        guide.xml_signed = xml_signed
        guide.status = DocumentStatus.SIGNED
    except (ValueError, OSError) as e:
        logger.error("XML signing failed for dispatch guide %s: %s", guide.id, e)
        rollback_on_pre_sunat_error(db)
        raise XMLSignError(f"Failed to sign GR XML: {e}") from e

    # Generate QR code
    try:
        digest_value, signature_value = extract_signature_values(xml_signed)
        qr_text = build_dispatch_guide_qr_text(
            ruc=client.ruc,
            document_type=document_type,
            series=data.series,
            correlative=correlative,
            issue_date=issue_date,
            recipient_doc_type=recipient_doc_type_code,
            recipient_doc_number=data.recipient_doc_number,
            digest_value=digest_value,
            signature_value=signature_value,
        )
        guide.qr_text = qr_text
        guide.qr_image = generate_qr_image(qr_text)
    except Exception as e:
        logger.warning("QR generation failed for dispatch guide %s: %s", guide.id, e)

    # Send to SUNAT via REST API
    try:
        sol_user = decrypt_string(client.sol_user)
        sol_password = decrypt_string(client.sol_password)
        sunat_client_id = decrypt_string(client.sunat_client_id) if client.sunat_client_id else None
        sunat_client_secret = decrypt_string(client.sunat_client_secret) if client.sunat_client_secret else None

        cdr = await send_gre_document(
            xml_signed=xml_signed,
            ruc=client.ruc,
            document_type=document_type,
            series=data.series,
            correlative=correlative,
            sol_user=sol_user,
            sol_password=sol_password,
            sunat_client_id=sunat_client_id,
            sunat_client_secret=sunat_client_secret,
        )

        guide.cdr_content = cdr.get("cdr_content")
        guide.cdr_code = cdr.get("cdr_code")
        guide.cdr_description = cdr.get("cdr_description")
        guide.status = cdr.get("status", DocumentStatus.SENT)

        logger.info(
            "DispatchGuide %s sent to SUNAT: status=%s code=%s",
            guide.id,
            guide.status,
            guide.cdr_code,
        )
    except BillingError as e:
        logger.error("SUNAT send failed for dispatch guide %s: %s", guide.id, e)
        guide.cdr_description = str(e)
        set_error_status(db, guide)
    else:
        db.commit()

    db.refresh(guide)
    attach_next_correlative(db, guide, client.id, document_type, data.series)
    return guide


async def retry_send_dispatch_guide(
    db: Session, client: Client, guide: DispatchGuide
) -> DispatchGuide:
    """Retry sending a GR in SIGNED, ERROR or REJECTED status."""
    _validate_client_credentials(client)

    retryable = {DocumentStatus.SIGNED, DocumentStatus.ERROR, DocumentStatus.REJECTED}
    if guide.status not in retryable:
        raise BillingError(f"Cannot retry dispatch guide in status '{guide.status}'")
    if not guide.xml_signed:
        raise BillingError("Dispatch guide has no signed XML to send")

    sol_user = decrypt_string(client.sol_user)
    sol_password = decrypt_string(client.sol_password)
    sunat_client_id = decrypt_string(client.sunat_client_id) if client.sunat_client_id else None
    sunat_client_secret = decrypt_string(client.sunat_client_secret) if client.sunat_client_secret else None

    try:
        cdr = await send_gre_document(
            xml_signed=guide.xml_signed,
            ruc=client.ruc,
            document_type=guide.document_type,
            series=guide.series,
            correlative=guide.correlative,
            sol_user=sol_user,
            sol_password=sol_password,
            sunat_client_id=sunat_client_id,
            sunat_client_secret=sunat_client_secret,
        )
        guide.cdr_content = cdr.get("cdr_content")
        guide.cdr_code = cdr.get("cdr_code")
        guide.cdr_description = cdr.get("cdr_description")
        guide.status = cdr.get("status", DocumentStatus.SENT)
    except BillingError as e:
        logger.error("SUNAT send failed for dispatch guide %s: %s", guide.id, e)
        guide.cdr_description = str(e)
        set_error_status(db, guide)
        raise

    db.commit()
    db.refresh(guide)
    return guide


async def check_dispatch_guide_status(
    db: Session, client: Client, guide: DispatchGuide
) -> DispatchGuide:
    """Query SUNAT for GR status via REST ticket query.

    Only works for guides that have a pending ticket (status=SENT with ticket
    info in cdr_description). For already resolved guides, returns as-is.
    """
    from app.services.integrations.sunat.rest_client import (
        call_get_ticket_status,
        get_sunat_token,
    )
    from app.services.integrations.sunat.rest_sender import (
        _extract_cdr_from_ticket_response,
    )

    _validate_client_credentials(client)

    if guide.status != DocumentStatus.SENT:
        return guide

    # Extract ticket from cdr_description if stored there
    ticket = None
    if guide.cdr_description and guide.cdr_description.startswith("Ticket "):
        ticket = guide.cdr_description.split(" ")[1]

    if not ticket:
        return guide

    sol_user = decrypt_string(client.sol_user)
    sol_password = decrypt_string(client.sol_password)
    sunat_client_id = decrypt_string(client.sunat_client_id) if client.sunat_client_id else None
    sunat_client_secret = decrypt_string(client.sunat_client_secret) if client.sunat_client_secret else None

    token = await get_sunat_token(
        ruc=client.ruc,
        sol_user=sol_user,
        sol_password=sol_password,
        sunat_client_id=sunat_client_id,
        sunat_client_secret=sunat_client_secret,
    )

    ticket_response = await call_get_ticket_status(token=token, ticket=ticket)
    if ticket_response is None:
        return guide

    cdr = _extract_cdr_from_ticket_response(ticket_response)

    guide.cdr_content = cdr.get("cdr_content") or guide.cdr_content
    guide.cdr_code = cdr.get("cdr_code") or guide.cdr_code
    guide.cdr_description = cdr.get("cdr_description") or guide.cdr_description
    guide.status = cdr.get("status", guide.status)

    db.commit()
    db.refresh(guide)
    return guide
