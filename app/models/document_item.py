from sqlalchemy import Column, ForeignKey, Integer, Numeric, String
from sqlalchemy.orm import relationship

from app.database import Base


class DocumentItem(Base):
    __tablename__ = "document_items"

    id = Column(Integer, primary_key=True, autoincrement=True)
    document_id = Column(String, ForeignKey("documents.id"), nullable=False)

    description = Column(String(500), nullable=False)
    quantity = Column(Numeric(14, 4), nullable=False)
    unit_code = Column(String(5), nullable=False)  # NIU=producto, ZZ=servicio
    unit_price = Column(Numeric(14, 4), nullable=False)  # Price without IGV (base price for SUNAT XML)
    unit_price_without_tax = Column(Numeric(14, 4), nullable=True)  # Explicit base price sent by caller (sin IGV)
    igv_type = Column(String(2), nullable=False)  # Catálogo 07: 10=gravado, 20=exonerado, 30=inafecto
    igv = Column(Numeric(12, 2), nullable=False)
    total = Column(Numeric(12, 2), nullable=False)  # unit_price * quantity + igv

    document = relationship("Document", back_populates="items")
