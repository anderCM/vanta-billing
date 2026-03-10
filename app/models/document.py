import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.orm import relationship

from app.database import Base
from app.services.sunat_catalogs import DocumentStatus

class Document(Base):
    __tablename__ = "documents"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    client_id = Column(String, ForeignKey("clients.id"), nullable=False)

    # Document identity
    document_type = Column(String(2), nullable=False)  # "01", "03", or "07"
    series = Column(String(4), nullable=False)
    correlative = Column(Integer, nullable=False)

    # Customer info
    customer_doc_type = Column(String(1), nullable=False)  # "6" RUC, "1" DNI
    customer_doc_number = Column(String(20), nullable=False)
    customer_name = Column(String(255), nullable=False)
    customer_address = Column(String(255), nullable=True)

    # Dates
    issue_date = Column(DateTime, nullable=False)

    # Currency
    currency = Column(String(3), default="PEN", nullable=False)

    # Totals
    total_gravada = Column(Numeric(12, 2), nullable=False)
    total_igv = Column(Numeric(12, 2), nullable=False)
    total_amount = Column(Numeric(12, 2), nullable=False)

    # XML and CDR
    xml_content = Column(Text, nullable=True)
    xml_signed = Column(Text, nullable=True)
    cdr_content = Column(Text, nullable=True)
    cdr_code = Column(String(10), nullable=True)
    cdr_description = Column(Text, nullable=True)

    # QR code
    qr_text = Column(Text, nullable=True)
    qr_image = Column(Text, nullable=True)

    # Payment condition
    payment_condition = Column(String(10), default="contado", nullable=False)

    # Credit note fields (only for document_type "07")
    credit_note_reason_code = Column(String(2), nullable=True)
    credit_note_description = Column(String(500), nullable=True)
    reference_document_id = Column(String, ForeignKey("documents.id"), nullable=True)
    reference_document_type = Column(String(2), nullable=True)
    reference_document_series = Column(String(4), nullable=True)
    reference_document_correlative = Column(Integer, nullable=True)

    # Status
    status = Column(String(20), default=DocumentStatus.CREATED, nullable=False)

    # Timestamps
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(
        DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False
    )

    # Relationships
    client = relationship("Client", back_populates="documents")
    items = relationship("DocumentItem", back_populates="document")
    installments = relationship("DocumentInstallment", back_populates="document")
