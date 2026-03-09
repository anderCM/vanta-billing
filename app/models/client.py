from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, LargeBinary, String, Text
from sqlalchemy.orm import relationship

from app.database import Base


class Client(Base):
    __tablename__ = "clients"

    id = Column(String, primary_key=True)  # UUID as client_id
    integrator_id = Column(Integer, ForeignKey("integrators.id"), nullable=True)
    ruc = Column(String(11), nullable=False, unique=True)
    razon_social = Column(String(255), nullable=False)
    nombre_comercial = Column(String(255), nullable=True)

    # Address
    direccion = Column(String(255), nullable=True)
    ubigeo = Column(String(6), nullable=True)

    # SUNAT credentials (encrypted)
    sol_user = Column(Text, nullable=True)
    sol_password = Column(Text, nullable=True)
    sunat_client_id = Column(Text, nullable=True)
    sunat_client_secret = Column(Text, nullable=True)
    certificate = Column(LargeBinary, nullable=True)
    certificate_password = Column(Text, nullable=True)

    # API Key
    api_key_hash = Column(String(64), nullable=False, unique=True, index=True)

    # Document series defaults
    serie_factura = Column(String(4), nullable=True)  # e.g. F001
    serie_boleta = Column(String(4), nullable=True)   # e.g. B001
    serie_grr = Column(String(4), nullable=True)      # e.g. T001
    serie_grt = Column(String(4), nullable=True)      # e.g. V001

    # Service flags
    send_email = Column(Boolean, default=False, nullable=False)
    generate_pdf = Column(Boolean, default=False, nullable=False)

    # Config
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(
        DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False
    )

    # Relationships
    document_series = relationship("DocumentSeries", back_populates="client")
    documents = relationship("Document", back_populates="client")
    dispatch_guides = relationship("DispatchGuide", back_populates="client")
    integrator = relationship("Integrator", back_populates="clients")
