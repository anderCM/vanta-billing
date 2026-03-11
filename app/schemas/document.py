from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field, model_validator


class ItemType(str, Enum):
    product = "product"
    service = "service"


class TaxType(str, Enum):
    gravado = "gravado"
    exonerado = "exonerado"
    inafecto = "inafecto"


class CustomerDocType(str, Enum):
    ruc = "ruc"
    dni = "dni"


class DocumentItemCreate(BaseModel):
    description: str = Field(..., max_length=500)
    quantity: Decimal = Field(..., gt=0)
    item_type: ItemType
    unit_price: Decimal = Field(..., gt=0)
    unit_price_without_tax: Decimal | None = Field(None, gt=0)
    tax_type: TaxType


class InstallmentCreate(BaseModel):
    amount: Decimal = Field(..., gt=0)
    due_date: date


class InvoiceCreate(BaseModel):
    series: str | None = Field(None, max_length=4)
    customer_doc_type: CustomerDocType = Field(default=CustomerDocType.ruc)
    customer_doc_number: str = Field(..., max_length=20)
    customer_name: str = Field(..., max_length=255)
    customer_address: str | None = None
    currency: str = Field(default="PEN", max_length=3)
    items: list[DocumentItemCreate] = Field(..., min_length=1)
    payment_condition: Literal["contado", "credito"] = "contado"
    installments: list[InstallmentCreate] | None = None

    @model_validator(mode="after")
    def validate_payment_condition(self):
        if self.payment_condition == "credito":
            if not self.installments or len(self.installments) == 0:
                raise ValueError("installments are required when payment_condition is 'credito'")
        elif self.installments:
            raise ValueError("installments must not be provided when payment_condition is 'contado'")
        return self


class ReceiptCreate(BaseModel):
    series: str | None = Field(None, max_length=4)
    customer_doc_type: CustomerDocType = Field(default=CustomerDocType.dni)
    customer_doc_number: str = Field(..., max_length=20)
    customer_name: str = Field(..., max_length=255)
    customer_address: str | None = None
    currency: str = Field(default="PEN", max_length=3)
    items: list[DocumentItemCreate] = Field(..., min_length=1)
    payment_condition: Literal["contado", "credito"] = "contado"
    installments: list[InstallmentCreate] | None = None

    @model_validator(mode="after")
    def validate_payment_condition(self):
        if self.payment_condition == "credito":
            if not self.installments or len(self.installments) == 0:
                raise ValueError("installments are required when payment_condition is 'credito'")
        elif self.installments:
            raise ValueError("installments must not be provided when payment_condition is 'contado'")
        return self


class DocumentItemRead(BaseModel):
    id: int
    description: str
    quantity: Decimal
    unit_code: str
    unit_price: Decimal
    unit_price_without_tax: Decimal | None = None
    igv_type: str
    igv: Decimal
    total: Decimal

    model_config = {"from_attributes": True}


class InstallmentRead(BaseModel):
    id: int
    installment_number: int
    amount: Decimal
    due_date: date

    model_config = {"from_attributes": True}


class DocumentRead(BaseModel):
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
    issue_date: datetime
    created_at: datetime

    model_config = {"from_attributes": True}


class DocumentDetail(DocumentRead):
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
    updated_at: datetime
    next_document_series: str | None = None
    next_document_number: int | None = None

    model_config = {"from_attributes": True}
