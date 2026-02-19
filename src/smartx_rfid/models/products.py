"""
RFID models for SMARTX Connector.

Defines the Tag and Event models for storing RFID reader data
with proper indexing and relationships.
"""

from sqlalchemy import Column, Integer, String, Text, DateTime

from .mixin import Base, BaseMixin


class ProductsType(Base, BaseMixin):
    __tablename__ = "products_type"

    # Primary key
    id = Column(Integer, primary_key=True, autoincrement=True)

    name = Column(String(100), nullable=False, index=True)
    description = Column(Text, nullable=True)


class ReadersType(Base, BaseMixin):
    __tablename__ = "readers_type"

    # Primary key
    id = Column(Integer, primary_key=True, autoincrement=True)

    name = Column(String(100), nullable=False, index=True)
    description = Column(Text, nullable=True)


class ProductsOrders(Base, BaseMixin):
    __tablename__ = "products_orders"

    # Primary key
    id = Column(Integer, primary_key=True, autoincrement=True)

    product_type_id = Column(Integer, nullable=False, index=True)
    client_id = Column(Integer, nullable=False, index=True)
    reader_type_id = Column(Integer, nullable=False)
    reader_serial = Column(String(100), nullable=False)
    version = Column(String(50), nullable=False)

    mounted_at = Column(DateTime(timezone=True), nullable=True)
    shipped_at = Column(DateTime(timezone=True), nullable=True)
    activated_at = Column(DateTime(timezone=True), nullable=True)
