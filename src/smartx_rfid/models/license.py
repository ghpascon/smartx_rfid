"""
RFID models for SMARTX Connector.

Defines the Tag and Event models for storing RFID reader data
with proper indexing and relationships.
"""

from sqlalchemy import Column, String, Text, Integer

from .mixin import Base, BaseMixin


class License(Base, BaseMixin):
    __tablename__ = "licenses"
    id = Column(Integer, primary_key=True, autoincrement=True)
    public_key = Column(String(2000), nullable=False, index=True, unique=True)
    private_key = Column(Text, nullable=False)

    def __setattr__(self, name, value):
        if name in ["public_key", "private_key"] and isinstance(value, str):
            value = value.strip()
        super().__setattr__(name, value)
