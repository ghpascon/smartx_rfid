"""
RFID models for SMARTX Connector.

Defines the Tag and Event models for storing RFID reader data
with proper indexing and relationships.
"""

from sqlalchemy import Column, String, Integer

from .mixin import Base, BaseMixin


class Users(Base, BaseMixin):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(100), nullable=False, index=True, unique=True)
    password_hash = Column(String(255), nullable=False)
    role = Column(String(50), nullable=False, default="user", index=True)
