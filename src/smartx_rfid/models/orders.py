"""
RFID models for SMARTX Connector.

Defines the Tag and Event models for storing RFID reader data
with proper indexing and relationships.
"""

# Adiciona event listener para gerar serial e label_code automaticamente
from datetime import datetime

from sqlalchemy.orm import Session
from sqlalchemy import event, func, select, Boolean, Column, Integer, String, Text, DateTime

from .mixin import Base, BaseMixin


class ReadersType(Base, BaseMixin):
    __tablename__ = "readers_type"

    # Primary key
    id = Column(Integer, primary_key=True, autoincrement=True)

    name = Column(String(100), nullable=False, index=True, unique=True)
    description = Column(Text, nullable=True)


@event.listens_for(ReadersType, "before_insert")
def lowercase_name(mapper, connection, target):
    if target.name:
        target.name = target.name.lower()


class Readers(Base, BaseMixin):
    __tablename__ = "readers"

    # Primary key
    id = Column(Integer, primary_key=True, autoincrement=True)
    reader_type_id = Column(Integer, nullable=False, index=True)
    serial_number = Column(String(100), nullable=False, index=True, unique=True)
    hostname = Column(String(255), nullable=True, index=True)
    available = Column(Boolean, nullable=False, default=True, index=True)


@event.listens_for(Readers, "before_insert")
def check_reader_type_id(mapper, connection, target):
    session = Session(bind=connection)
    exists = session.execute(select(ReadersType.id).where(ReadersType.id == target.reader_type_id)).first()
    session.close()
    if not exists:
        raise ValueError(f"reader_type_id {target.reader_type_id} não existe em ReadersType.")


class Orders(Base, BaseMixin):
    __tablename__ = "orders"

    # Primary key
    id = Column(Integer, primary_key=True, autoincrement=True)

    order_number = Column(Integer, nullable=False, index=True)
    client_name = Column(String(255), nullable=False, index=True)
    client_cnpj = Column(String(25), nullable=True, index=True)
    product_code = Column(String(100), nullable=False, index=True)
    product_description = Column(String(255), nullable=True, index=False)
    product_family = Column(String(255), nullable=True, index=False)
    product_serial = Column(Integer, nullable=False, index=True)
    label_code = Column(String(100), nullable=False, index=True, unique=True)

    reader_id = Column(Integer, nullable=True, index=True)

    mounted_at = Column(DateTime(timezone=True), nullable=True, index=True)
    tested_at = Column(DateTime(timezone=True), nullable=True, index=True)
    shipped_at = Column(DateTime(timezone=True), nullable=True, index=True)
    activated_at = Column(DateTime(timezone=True), nullable=True, index=True)

    created_by = Column(Integer, nullable=True, index=False)
    mounted_by = Column(Integer, nullable=True, index=False)
    tested_by = Column(Integer, nullable=True, index=False)
    shipped_by = Column(Integer, nullable=True, index=False)
    activated_by = Column(Integer, nullable=True, index=False)

    comments = Column(Text, nullable=True)


@event.listens_for(Orders, "before_insert")
def set_serial_and_label_code(mapper, connection, target):
    year = datetime.now().year
    year_suffix = str(year)[-3:]  # ex: "026" para 2026
    year_start = datetime(year, 1, 1)
    year_end = datetime(year + 1, 1, 1)

    session = Session(bind=connection)
    max_serial = session.execute(
        select(func.max(Orders.product_serial))
        .where(Orders.created_at >= year_start)
        .where(Orders.created_at < year_end)
    ).scalar()
    session.close()

    target.product_serial = (max_serial + 1) if max_serial is not None else 1
    target.label_code = f"{year_suffix}{str(target.product_serial).zfill(7)}"
