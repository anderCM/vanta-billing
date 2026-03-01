from sqlalchemy import Column, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import relationship

from app.database import Base


class DocumentSeries(Base):
    __tablename__ = "document_series"

    id = Column(Integer, primary_key=True, autoincrement=True)
    client_id = Column(String, ForeignKey("clients.id"), nullable=False)
    document_type = Column(String(2), nullable=False)  # "01" factura, "03" boleta
    series = Column(String(4), nullable=False)  # e.g. F001, B001
    current_correlative = Column(Integer, default=0, nullable=False)

    __table_args__ = (
        UniqueConstraint("client_id", "document_type", "series", name="uq_client_doc_type_series"),
    )

    client = relationship("Client", back_populates="document_series")
