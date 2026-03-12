"""
RFID models for SMARTX Connector.

Defines the Tag and Event models for storing RFID reader data
with proper indexing and relationships.
"""

# Adiciona event listener para gerar serial e label_code automaticamente
from sqlalchemy.orm import Session
from sqlalchemy import event, select, Boolean, Column, Integer, String, Text, DateTime

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
    # Gera o próximo serial para o product_code
    session = Session(bind=connection)
    max_serial = session.execute(
        select(Orders.product_serial)
        .where(Orders.product_code == target.product_code)
        .order_by(Orders.product_serial.desc())
    ).first()
    if max_serial and max_serial[0] is not None:
        target.product_serial = max_serial[0] + 1
    else:
        target.product_serial = 1
    # Gera o label_code no formato product_code-serial
    target.label_code = f"{target.product_code}-{target.product_serial}"
    session.close()
