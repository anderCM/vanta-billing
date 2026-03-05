from sqlalchemy import Column, ForeignKey, Integer, Numeric, String
from sqlalchemy.orm import relationship

from app.database import Base


class DispatchGuideItem(Base):
    __tablename__ = "dispatch_guide_items"

    id = Column(Integer, primary_key=True, autoincrement=True)
    guide_id = Column(String, ForeignKey("dispatch_guides.id"), nullable=False)

    description = Column(String(500), nullable=False)
    quantity = Column(Numeric(14, 4), nullable=False)
    unit_code = Column(String(5), nullable=False)

    guide = relationship("DispatchGuide", back_populates="items")
