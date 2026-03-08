from datetime import datetime
from decimal import Decimal
from enum import Enum

from pydantic import BaseModel, Field, model_validator


class TransportModalityEnum(str, Enum):
    public = "public"
    private = "private"


class TransferReasonEnum(str, Enum):
    venta = "venta"
    compra = "compra"
    traslado_entre_establecimientos = "traslado_entre_establecimientos"
    importacion = "importacion"
    exportacion = "exportacion"
    otros = "otros"


class GRDocType(str, Enum):
    ruc = "ruc"
    dni = "dni"


class GRItemCreate(BaseModel):
    description: str = Field(..., max_length=500)
    quantity: Decimal = Field(..., gt=0)
    unit_code: str = Field(default="NIU", max_length=5)


class ShipmentData(BaseModel):
    transfer_reason: TransferReasonEnum
    transport_modality: TransportModalityEnum
    transfer_date: str = Field(..., description="YYYY-MM-DD")
    gross_weight: str = Field(..., description="Total weight in kg")
    weight_unit_code: str = Field(default="KGM", max_length=5)
    departure_address: str = Field(..., max_length=500)
    departure_ubigeo: str = Field(..., min_length=6, max_length=6)
    arrival_address: str = Field(..., max_length=500)
    arrival_ubigeo: str = Field(..., min_length=6, max_length=6)


class GRRCreate(ShipmentData):
    """Guía de Remisión Remitente (sender) — doc type 09, series T."""

    series: str | None = Field(None, max_length=4)
    recipient_doc_type: GRDocType = GRDocType.ruc
    recipient_doc_number: str = Field(..., max_length=20)
    recipient_name: str = Field(..., max_length=255)
    related_document_id: str | None = Field(None, description="UUID of a related invoice/receipt in this system")
    items: list[GRItemCreate] = Field(..., min_length=1)

    # Public transport fields
    carrier_ruc: str | None = Field(None, max_length=11)
    carrier_name: str | None = Field(None, max_length=255)

    # Private transport fields
    vehicle_plate: str | None = Field(None, max_length=20)
    driver_doc_type: GRDocType | None = None
    driver_doc_number: str | None = Field(None, max_length=20)
    driver_name: str | None = Field(None, max_length=255)
    driver_license: str | None = Field(None, max_length=50)

    @model_validator(mode="after")
    def validate_transport_data(self):
        if self.transport_modality == TransportModalityEnum.public:
            if not self.carrier_ruc or not self.carrier_name:
                raise ValueError(
                    "carrier_ruc and carrier_name required for public transport"
                )
        else:  # private
            if not self.vehicle_plate:
                raise ValueError("vehicle_plate required for private transport")
            if not all(
                [self.driver_doc_number, self.driver_name, self.driver_license]
            ):
                raise ValueError("driver info required for private transport")
        return self


class GRTCreate(ShipmentData):
    """Guía de Remisión Transportista (carrier) — doc type 31, series V."""

    series: str | None = Field(None, max_length=4)
    recipient_doc_type: GRDocType = GRDocType.ruc
    recipient_doc_number: str = Field(..., max_length=20)
    recipient_name: str = Field(..., max_length=255)
    related_document_id: str | None = Field(None, description="UUID of a related invoice/receipt in this system")
    items: list[GRItemCreate] = Field(..., min_length=1)

    # Shipper info (remitente — who sent the goods)
    shipper_doc_type: GRDocType = GRDocType.ruc
    shipper_doc_number: str = Field(..., max_length=20)
    shipper_name: str = Field(..., max_length=255)

    # Vehicle details (mandatory for GRT)
    vehicle_plate: str = Field(..., max_length=20)
    driver_doc_type: GRDocType = GRDocType.dni
    driver_doc_number: str = Field(..., max_length=20)
    driver_name: str = Field(..., max_length=255)
    driver_license: str = Field(..., max_length=50)


class GRItemRead(BaseModel):
    id: int
    description: str
    quantity: Decimal
    unit_code: str

    model_config = {"from_attributes": True}


class DispatchGuideRead(BaseModel):
    id: str
    document_type: str
    series: str
    correlative: int
    transfer_reason: str
    transport_modality: str
    transfer_date: str
    status: str
    issue_date: datetime
    created_at: datetime

    model_config = {"from_attributes": True}


class DispatchGuideDetail(DispatchGuideRead):
    gross_weight: str
    departure_address: str
    departure_ubigeo: str
    arrival_address: str
    arrival_ubigeo: str
    recipient_doc_type: str
    recipient_doc_number: str
    recipient_name: str
    carrier_ruc: str | None
    carrier_name: str | None
    vehicle_plate: str | None
    driver_doc_number: str | None
    driver_name: str | None
    shipper_doc_number: str | None
    shipper_name: str | None
    related_document_id: str | None
    related_document_type: str | None
    related_document_number: str | None
    xml_content: str | None
    xml_signed: str | None
    cdr_content: str | None
    cdr_code: str | None
    cdr_description: str | None
    qr_text: str | None
    qr_image: str | None
    items: list[GRItemRead]
    updated_at: datetime

    model_config = {"from_attributes": True}
