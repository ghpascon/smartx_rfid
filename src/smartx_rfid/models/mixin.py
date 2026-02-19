"""
Base mixin classes for SMARTX Connector models.

Provides common functionality and utilities that can be shared
across different model classes without code duplication.
"""

import json
from datetime import datetime
from typing import Any, Dict, Optional, Type, TypeVar

try:
    from sqlalchemy import func
    from sqlalchemy.orm import DeclarativeBase
except ImportError:
    from sqlalchemy import func
    from sqlalchemy.ext.declarative import declarative_base

    DeclarativeBase = declarative_base()

from sqlalchemy import Column, DateTime, func

# Type variable for generic model operations
ModelType = TypeVar("ModelType", bound="BaseMixin")


class Base(DeclarativeBase):
    """
    Base declarative class for all models.
    """

    # timestamps
    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )

    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class BaseMixin:
    """
    Base mixin providing common functionality for all models.

    Includes timestamp management and utility methods for
    serialization, representation, and data manipulation.
    """

    def __repr__(self) -> str:
        """
        Dynamic string representation of the model instance.

        Returns:
            str: Human-readable representation
        """
        class_name = self.__class__.__name__

        # Get primary key columns dynamically
        primary_keys = []
        if hasattr(self.__class__, "__table__"):
            for column in self.__class__.__table__.primary_key.columns:
                value = getattr(self, column.name, None)
                if value is not None:
                    primary_keys.append(f"{column.name}={value!r}")

        pk_str = ", ".join(primary_keys) if primary_keys else "id=None"
        return f"<{class_name}({pk_str})>"

    def to_dict(self, exclude: Optional[list] = None, include_relationships: bool = False) -> Dict[str, Any]:
        """
        Convert model instance to dictionary.

        Args:
            exclude: List of attribute names to exclude
            include_relationships: Whether to include relationship data

        Returns:
            Dict[str, Any]: Dictionary representation of the model
        """
        exclude = exclude or []
        result = {}

        # Get table columns
        if hasattr(self.__class__, "__table__"):
            for column in self.__class__.__table__.columns:
                column_name = column.name

                if column_name in exclude:
                    continue

                value = getattr(self, column_name)

                # Handle datetime serialization
                if isinstance(value, datetime):
                    result[column_name] = value.isoformat()
                else:
                    result[column_name] = value

        # Include relationships if requested
        if include_relationships and hasattr(self.__class__, "__mapper__"):
            mapper = self.__class__.__mapper__
            for relationship in mapper.relationships:
                rel_name = relationship.key

                if rel_name in exclude:
                    continue

                rel_value = getattr(self, rel_name, None)

                if rel_value is not None:
                    if hasattr(rel_value, "to_dict"):
                        # Single relationship
                        result[rel_name] = rel_value.to_dict(exclude=exclude)
                    elif hasattr(rel_value, "__iter__"):
                        # Collection relationship
                        result[rel_name] = [
                            item.to_dict(exclude=exclude) for item in rel_value if hasattr(item, "to_dict")
                        ]

        return result

    def to_json(self, exclude: Optional[list] = None, include_relationships: bool = False, **json_kwargs) -> str:
        """
        Convert model instance to JSON string.

        Args:
            exclude: List of attribute names to exclude
            include_relationships: Whether to include relationship data
            **json_kwargs: Additional arguments for json.dumps

        Returns:
            str: JSON string representation
        """
        data = self.to_dict(exclude=exclude, include_relationships=include_relationships)
        return json.dumps(data, default=str, **json_kwargs)

    @classmethod
    def from_dict(cls: Type[ModelType], data: Dict[str, Any], ignore_unknown: bool = True) -> ModelType:
        """
        Create model instance from dictionary.

        Args:
            data: Dictionary with model data
            ignore_unknown: Whether to ignore unknown attributes

        Returns:
            ModelType: New model instance
        """
        filtered_data = {}

        if hasattr(cls, "__table__"):
            # Only include known columns
            column_names = {column.name for column in cls.__table__.columns}

            for key, value in data.items():
                if key in column_names:
                    filtered_data[key] = value
                elif not ignore_unknown:
                    raise ValueError(f"Unknown attribute '{key}' for {cls.__name__}")
        else:
            # Fallback for classes without __table__
            filtered_data = data

        return cls(**filtered_data)

    def update_from_dict(self, data: Dict[str, Any], ignore_unknown: bool = True) -> None:
        """
        Update model instance from dictionary.

        Args:
            data: Dictionary with updated data
            ignore_unknown: Whether to ignore unknown attributes
        """
        if hasattr(self.__class__, "__table__"):
            column_names = {column.name for column in self.__class__.__table__.columns}

            for key, value in data.items():
                if key in column_names:
                    setattr(self, key, value)
                elif not ignore_unknown:
                    raise ValueError(f"Unknown attribute '{key}' for {self.__class__.__name__}")
        else:
            # Fallback for classes without __table__
            for key, value in data.items():
                if hasattr(self, key) or not ignore_unknown:
                    setattr(self, key, value)

    def refresh_timestamps(self) -> None:
        """
        Manually refresh the updated_at timestamp.
        """
        if hasattr(self, "updated_at"):
            self.updated_at = func.now()
