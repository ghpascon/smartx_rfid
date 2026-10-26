"""
Log model for SMARTX Connector.

Default model used by ``LoggerManager`` when logging to a database.
It owns an isolated declarative base so that creating its table never
creates unrelated tables registered in other metadata.
"""

from datetime import datetime

from sqlalchemy import Column, DateTime, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase

from .mixin import BaseMixin


class LogsBase(DeclarativeBase):
    """Isolated declarative base for the logs table."""


class Logs(BaseMixin, LogsBase):
    __tablename__ = "logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now().astimezone(), index=True)
    level = Column(String(50), nullable=False, index=True)
    logger = Column(String(255), nullable=True)
    message = Column(Text, nullable=False)
    module = Column(String(255), nullable=True)
    function = Column(String(100), nullable=True)
    line = Column(Integer, nullable=True)
    thread = Column(String(100), nullable=True)
    pathname = Column(String(500), nullable=True)
    exception = Column(Text, nullable=True)
    extra = Column(Text, nullable=True)  # JSON-encoded extra fields
