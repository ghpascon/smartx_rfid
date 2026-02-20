"""
RFID models for SMARTX Connector.

Defines the Tag and Event models for storing RFID reader data
with proper indexing and relationships.
"""

from sqlalchemy import Boolean, Column, Integer, String, Text, DateTime

from .mixin import Base, BaseMixin


class ProductsType(Base, BaseMixin):
    __tablename__ = "products_type"

    # Primary key
    id = Column(Integer, primary_key=True, autoincrement=True)

    name = Column(String(100), nullable=False, index=True, unique=True)
    description = Column(Text, nullable=True)


class ReadersType(Base, BaseMixin):
    __tablename__ = "readers_type"

    # Primary key
    id = Column(Integer, primary_key=True, autoincrement=True)

    name = Column(String(100), nullable=False, index=True, unique=True)
    description = Column(Text, nullable=True)


class Readers(Base, BaseMixin):
    __tablename__ = "readers"

    # Primary key
    id = Column(Integer, primary_key=True, autoincrement=True)
    reader_type_id = Column(Integer, nullable=False, index=True)
    serial_number = Column(String(100), nullable=False, index=True, unique=True)
    hostname = Column(String(255), nullable=True, index=True)
    available = Column(Boolean, nullable=False, default=True, index=True)


class ProductsOrders(Base, BaseMixin):
    __tablename__ = "products_orders"

    # Primary key
    id = Column(Integer, primary_key=True, autoincrement=True)

    product_type_id = Column(Integer, nullable=False, index=True)
    client_id = Column(Integer, nullable=False, index=True)
    reader_id = Column(Integer, nullable=True, index=True)
    version = Column(String(50), nullable=False)

    mounted_at = Column(DateTime(timezone=True), nullable=True, index=True)
    tested_at = Column(DateTime(timezone=True), nullable=True, index=True)
    shipped_at = Column(DateTime(timezone=True), nullable=True, index=True)
    activated_at = Column(DateTime(timezone=True), nullable=True, index=True)


class Customer(Base, BaseMixin):
    __tablename__ = "customer"

    # Dynamically suppress all Column instances inherited from Base (legacy table)
    for _k, _v in vars(Base).items():
        if isinstance(_v, Column):
            locals()[_k] = None
    del _k, _v

    # Primary key
    ID = Column(Integer, primary_key=True, autoincrement=True)
    NAME = Column(String(255), nullable=False, index=True, unique=True)
