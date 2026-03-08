import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from app.database import Base
from app.services.sunat_catalogs import DocumentStatus


class DispatchGuide(Base):
    __tablename__ = "dispatch_guides"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    client_id = Column(String, ForeignKey("clients.id"), nullable=False)

    # Document identity
    document_type = Column(String(2), nullable=False)  # "09" GRR, "31" GRT
    series = Column(String(4), nullable=False)
    correlative = Column(Integer, nullable=False)

    # Transfer metadata
    transfer_reason = Column(String(2), nullable=False)    # Catálogo 20
    transport_modality = Column(String(2), nullable=False)  # Catálogo 18
    transfer_date = Column(String(10), nullable=False)      # YYYY-MM-DD

    # Shipment weight
    gross_weight = Column(String(20), nullable=False)
    weight_unit_code = Column(String(5), default="KGM", nullable=False)

    # Departure address (origin)
    departure_address = Column(String(500), nullable=False)
    departure_ubigeo = Column(String(6), nullable=False)

    # Arrival address (destination)
    arrival_address = Column(String(500), nullable=False)
    arrival_ubigeo = Column(String(6), nullable=False)

    # Recipient (destinatario)
    recipient_doc_type = Column(String(1), nullable=False)  # "6" RUC, "1" DNI
    recipient_doc_number = Column(String(20), nullable=False)
    recipient_name = Column(String(255), nullable=False)

    # GRR: carrier info (public transport)
    carrier_ruc = Column(String(11), nullable=True)
    carrier_name = Column(String(255), nullable=True)

    # GRR/GRT: vehicle and driver info
    vehicle_plate = Column(String(20), nullable=True)
    driver_doc_type = Column(String(1), nullable=True)
    driver_doc_number = Column(String(20), nullable=True)
    driver_name = Column(String(255), nullable=True)
    driver_license = Column(String(50), nullable=True)

    # GRT: shipper (remitente) info
    shipper_doc_type = Column(String(1), nullable=True)
    shipper_doc_number = Column(String(20), nullable=True)
    shipper_name = Column(String(255), nullable=True)

    # Related document reference (optional link to invoice/receipt)
    related_document_id = Column(String, ForeignKey("documents.id"), nullable=True)
    related_document_type = Column(String(2), nullable=True)   # "01" factura, "03" boleta
    related_document_number = Column(String(20), nullable=True)  # e.g. "F001-00000123"

    # Issue date
    issue_date = Column(DateTime, nullable=False)

    # XML and CDR
    xml_content = Column(Text, nullable=True)
    xml_signed = Column(Text, nullable=True)
    cdr_content = Column(Text, nullable=True)
    cdr_code = Column(String(10), nullable=True)
    cdr_description = Column(Text, nullable=True)

    # QR code
    qr_text = Column(Text, nullable=True)
    qr_image = Column(Text, nullable=True)

    # Status
    status = Column(String(20), default=DocumentStatus.CREATED, nullable=False)

    # Timestamps
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # Relationships
    client = relationship("Client", back_populates="dispatch_guides")
    items = relationship("DispatchGuideItem", back_populates="guide")
