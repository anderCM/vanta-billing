from datetime import datetime
from decimal import Decimal
from enum import Enum

from pydantic import BaseModel, Field

from app.schemas.document import DocumentItemCreate, DocumentItemRead, InstallmentRead


class CreditNoteReasonCode(str, Enum):
    anulacion_de_la_operacion = "anulacion_de_la_operacion"
    anulacion_por_error_en_el_ruc = "anulacion_por_error_en_el_ruc"
    correccion_por_error_en_la_descripcion = "correccion_por_error_en_la_descripcion"
    descuento_global = "descuento_global"
    descuento_por_item = "descuento_por_item"
    devolucion_total = "devolucion_total"
    devolucion_por_item = "devolucion_por_item"
    bonificacion = "bonificacion"
    disminucion_en_el_valor = "disminucion_en_el_valor"
    otros_conceptos = "otros_conceptos"
    ajustes_de_operaciones_de_exportacion = "ajustes_de_operaciones_de_exportacion"
    ajustes_afectos_al_ivap = "ajustes_afectos_al_ivap"
    correccion_del_monto_neto_pendiente_de_pago = "correccion_del_monto_neto_pendiente_de_pago"


class CreditNoteCreate(BaseModel):
    reference_document_id: str = Field(..., description="UUID of the original document to credit")
    reason_code: CreditNoteReasonCode
    description: str = Field(..., max_length=500)
    series: str | None = Field(None, max_length=4)
    items: list[DocumentItemCreate] = Field(..., min_length=1)


class CreditNoteRead(BaseModel):
    id: str
    document_type: str
    series: str
    correlative: int
    customer_doc_type: str
    customer_doc_number: str
    customer_name: str
    currency: str
    total_gravada: Decimal
    total_igv: Decimal
    total_amount: Decimal
    payment_condition: str
    status: str
    credit_note_reason_code: str | None
    credit_note_description: str | None
    reference_document_id: str | None
    reference_document_series: str | None
    reference_document_correlative: int | None
    reference_document_type: str | None
    issue_date: datetime
    created_at: datetime

    model_config = {"from_attributes": True}


class CreditNoteDetail(CreditNoteRead):
    customer_address: str | None
    xml_content: str | None
    xml_signed: str | None
    cdr_content: str | None
    cdr_code: str | None
    cdr_description: str | None
    qr_text: str | None = None
    qr_image: str | None = None
    items: list[DocumentItemRead]
    installments: list[InstallmentRead]
    next_document_series: str | None = None
    next_document_number: int | None = None
    updated_at: datetime

    model_config = {"from_attributes": True}
