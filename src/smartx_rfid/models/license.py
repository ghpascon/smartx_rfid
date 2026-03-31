"""
RFID models for SMARTX Connector.

Defines the Tag and Event models for storing RFID reader data
with proper indexing and relationships.
"""

from sqlalchemy import Column, String, Text, Integer
import base64
from .mixin import Base, BaseMixin


class License(Base, BaseMixin):
    __tablename__ = "licenses"
    id = Column(Integer, primary_key=True, autoincrement=True)
    public_key = Column(String(700), nullable=False, index=True, unique=True)
    private_key = Column(Text, nullable=False)

    def __setattr__(self, name, value):
        if name in ["public_key", "private_key"] and isinstance(value, str):
            value = value.strip()
        if name == "public_key" and isinstance(value, str):
            try:
                base64.b64decode(value.encode("utf-8"), validate=True)
            except Exception:
                value = base64.b64encode(value.encode("utf-8")).decode("utf-8")
        super().__setattr__(name, value)

    @property
    def public_key_decoded(self):
        try:
            return base64.b64decode(self.public_key.encode("utf-8")).decode("utf-8")
        except Exception:
            return self.public_key
