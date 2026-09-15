import logging
from typing import Any, Dict, List, Literal, Optional, Type, Union
from contextlib import contextmanager
from datetime import datetime, date
from decimal import Decimal
import zipfile
from sqlalchemy import create_engine, text, MetaData, inspect, event
from sqlalchemy.orm import sessionmaker, DeclarativeBase, scoped_session
from sqlalchemy.pool import QueuePool
from sqlalchemy.engine import Engine
import threading
import io
import json
import csv


class DatabaseError(Exception):
    """Custom database exception for better error handling"""

    def __init__(self, message: str, original_error: Optional[Exception] = None):
        super().__init__(message)
        self.original_error = original_error

        # Log the error
        if original_error:
            logging.error(f"DatabaseError: {message} | Original: {str(original_error)}")
        else:
            logging.error(f"DatabaseError: {message}")


class DatabaseConnectionError(DatabaseError):
    """Raised when database connection fails"""

    def __init__(self, message: str, original_error: Optional[Exception] = None):
        super().__init__(message, original_error)

        # Specific logging for connection errors
        logging.critical(f"Database connection failed: {message}")


class DatabaseOperationError(DatabaseError):
    """Raised when database operations fail"""

    def __init__(self, message: str, original_error: Optional[Exception] = None):
        super().__init__(message, original_error)

        # Specific logging for operation errors
        logging.error(f"Database operation failed: {message}")


class DatabaseManager:
    """
    Professional database manager using SQLAlchemy with support for multiple database backends.

    Features:
    - Multiple database support (PostgreSQL, MySQL, SQLite, SQL Server, Oracle, etc.)
    - Connection pooling
    - Session management
    - Automatic table creation
    - Raw SQL query support
    - Transaction management
    - Error handling
    - Thread safety
    """

    def __init__(
        self,
        database_url: str,
        echo: bool = False,
        pool_size: int = 10,
        max_overflow: int = 20,
        pool_timeout: int = 30,
        pool_recycle: int = 3600,
        **engine_kwargs,
    ):
        """
        Initialize the database manager.

        Args:
            database_url (str): Database connection URL
            echo (bool): Enable SQL query logging
            pool_size (int): Number of connections to maintain
            max_overflow (int): Maximum overflow connections
            pool_timeout (int): Timeout for getting connection from pool
            pool_recycle (int): Recycle connections after seconds
            **engine_kwargs: Additional engine configuration
        """
        self.database_url = database_url
        self.echo = echo
        self._engine: Optional[Engine] = None
        self._session_factory: Optional[sessionmaker] = None
        self._scoped_session: Optional[scoped_session] = None
        self._metadata: Optional[MetaData] = None
        self._models_registry: List[Type[DeclarativeBase]] = []
        self._lock = threading.Lock()

        # Engine configuration
        self._engine_config = {
            "echo": echo,
            "poolclass": QueuePool,
            "pool_size": pool_size,
            "max_overflow": max_overflow,
            "pool_timeout": pool_timeout,
            "pool_recycle": pool_recycle,
            "pool_pre_ping": True,  # Validate connections before use
            **engine_kwargs,
        }

        # Setup logging
        self.logger = logging.getLogger(__name__)

    def initialize(self) -> None:
        """Initialize the database engine and session factory."""
        try:
            with self._lock:
                if self._engine is None:
                    self._engine = create_engine(self.database_url, **self._engine_config)

                    # Setup connection event listeners
                    self._setup_event_listeners()

                    # Create session factory
                    self._session_factory = sessionmaker(bind=self._engine, expire_on_commit=False)

                    # Create scoped session for thread safety
                    self._scoped_session = scoped_session(self._session_factory)

                    # Create metadata instance
                    self._metadata = MetaData()

                    self.logger.info(f"Database initialized successfully: {self._get_db_info()}")

        except Exception as e:
            self.logger.error(f"Failed to initialize database: {str(e)}")
            raise DatabaseConnectionError(f"Database initialization failed: {str(e)}", e)

    def _setup_event_listeners(self) -> None:
        """Setup SQLAlchemy event listeners for connection management."""

        @event.listens_for(self._engine, "connect")
        def set_sqlite_pragma(dbapi_connection, connection_record):
            """Configure SQLite specific settings."""
            if "sqlite" in self.database_url.lower():
                cursor = dbapi_connection.cursor()
                cursor.execute("PRAGMA foreign_keys=ON")
                cursor.close()

        @event.listens_for(self._engine, "checkout")
        def receive_checkout(dbapi_connection, connection_record, connection_proxy):
            """Log connection checkout."""
            self.logger.debug("Connection checked out from pool")

        @event.listens_for(self._engine, "checkin")
        def receive_checkin(dbapi_connection, connection_record):
            """Log connection checkin."""
            self.logger.debug("Connection returned to pool")

    def _get_db_info(self) -> str:
        """Get database information for logging."""
        if self._engine:
            return f"{self._engine.dialect.name} ({self._engine.url.database})"
        return "Unknown"

    def register_models(self, *models: Type[DeclarativeBase]) -> None:
        """
        Register SQLAlchemy models for table creation.

        Args:
            *models: SQLAlchemy model classes
        """
        for model in models:
            if model not in self._models_registry:
                self._models_registry.append(model)
                self.logger.debug(f"Registered model: {model.__name__}")

    def create_tables(self, checkfirst: bool = True) -> None:
        """
        Create all registered model tables.

        Args:
            checkfirst (bool): Check if tables exist before creating
        """
        if not self._engine:
            raise DatabaseError("Database not initialized. Call initialize() first.")

        if not self._models_registry:
            self.logger.warning("No models registered for table creation")
            return

        try:
            # Get base metadata from first model
            base_metadata = self._models_registry[0].metadata

            # Create all tables
            base_metadata.create_all(bind=self._engine, checkfirst=checkfirst)

            self.logger.info(f"Tables created successfully for {len(self._models_registry)} models")

        except Exception as e:
            self.logger.error(f"Failed to create tables: {str(e)}")
            raise DatabaseOperationError(f"Table creation failed: {str(e)}", e)

    def drop_tables(self, checkfirst: bool = True) -> None:
        """
        Drop all registered model tables.

        Args:
            checkfirst (bool): Check if tables exist before dropping
        """
        if not self._engine:
            raise DatabaseError("Database not initialized. Call initialize() first.")

        if not self._models_registry:
            self.logger.warning("No models registered for table dropping")
            return

        try:
            # Get base metadata from first model
            base_metadata = self._models_registry[0].metadata

            # Drop all tables
            base_metadata.drop_all(bind=self._engine, checkfirst=checkfirst)

            self.logger.info("Tables dropped successfully")

        except Exception as e:
            self.logger.error(f"Failed to drop tables: {str(e)}")
            raise DatabaseOperationError(f"Table dropping failed: {str(e)}", e)

    def table_exists(self, table_name: str) -> bool:
        """
        Check if a table exists in the database.

        Args:
            table_name (str): Name of the table to check

        Returns:
            bool: True if table exists, False otherwise
        """
        if not self._engine:
            raise DatabaseError("Database not initialized. Call initialize() first.")

        try:
            inspector = inspect(self._engine)
            return table_name in inspector.get_table_names()
        except Exception as e:
            self.logger.error(f"Failed to check table existence: {str(e)}")
            return False

    def get_table_names(self) -> List[str]:
        """
        Get list of all table names in the database.

        Returns:
            List[str]: List of table names
        """
        if not self._engine:
            raise DatabaseError("Database not initialized. Call initialize() first.")

        try:
            inspector = inspect(self._engine)
            return inspector.get_table_names()
        except Exception as e:
            self.logger.error(f"Failed to get table names: {str(e)}")
            raise DatabaseOperationError(f"Failed to get table names: {str(e)}", e)

    @contextmanager
    def get_session(self):
        """
        Get a database session with automatic cleanup.

        Yields:
            Session: SQLAlchemy session
        """
        if not self._session_factory:
            raise DatabaseError("Database not initialized. Call initialize() first.")

        session = self._session_factory()
        try:
            yield session
            session.commit()
        except Exception as e:
            session.rollback()
            self.logger.error(f"Session error: {str(e)}")
            raise DatabaseOperationError(f"Database operation failed: {str(e)}", e)
        finally:
            session.close()

    def get_scoped_session(self) -> scoped_session:
        """
        Get a scoped session for thread-safe operations.

        Returns:
            scoped_session: Thread-safe scoped session
        """
        if not self._scoped_session:
            raise DatabaseError("Database not initialized. Call initialize() first.")
        return self._scoped_session

    def _normalize(self, v):
        if isinstance(v, Decimal):
            return float(v)
        if isinstance(v, (datetime, date)):
            return v.isoformat()
        if isinstance(v, (bytes, bytearray, memoryview)):
            return v.hex()
        return v

    # INFO
    def get_connection_info(self) -> Dict[str, Any]:
        """
        Get database connection information.

        Returns:
            Dict[str, Any]: Connection information
        """
        if not self._engine:
            return {"status": "not_initialized"}

        try:
            pool = self._engine.pool
            return {
                "status": "connected",
                "database_type": self._engine.dialect.name,
                "database_name": self._engine.url.database,
                "pool_size": pool.size(),
                "checked_in_connections": pool.checkedin(),
                "checked_out_connections": pool.checkedout(),
                "overflow": pool.overflow(),
            }
        except Exception as e:
            self.logger.error(f"Failed to get connection info: {str(e)}")
            return {"status": "error", "error": str(e)}

    def close(self) -> None:
        """Close all database connections and cleanup resources."""
        try:
            if self._scoped_session:
                self._scoped_session.remove()

            if self._engine:
                self._engine.dispose()

            self.logger.info("Database connections closed successfully")

        except Exception as e:
            self.logger.error(f"Error closing database connections: {str(e)}")
        finally:
            self._engine = None
            self._session_factory = None
            self._scoped_session = None
            self._metadata = None

    def generate_table_report(self, model: Type[DeclarativeBase], limit: int = 10000, offset: int = 0) -> dict:
        with self.get_session() as session:
            # Get total count (more efficient than loading all records)
            total = session.query(model).count()

            # Get paginated records using yield_per for memory efficiency
            query = session.query(model).limit(limit).offset(offset)
            records = [record.to_dict() for record in query]

            return {
                "total": total,
                "limit": limit,
                "offset": offset,
                "has_more": (offset + limit) < total,
                "data": records,
            }

    # QUERY
    def execute_query(self, query: Union[str, text], params: Optional[Dict[str, Any]] = None) -> Any:
        """
        Execute a raw SQL query and return results as a list of dicts.

        Args:
            query (Union[str, text]): SQL query to execute
            params (Optional[Dict[str, Any]]): Query parameters

        Returns:
            Any: List of dicts for SELECT queries, None for queries that do not return rows
        """
        with self.get_session() as session:
            try:
                if isinstance(query, str):
                    query = text(query)

                result = session.execute(query, params or {})

                if result.returns_rows:
                    return [{k: self._normalize(v) for k, v in row.items()} for row in result.mappings()]
                return None

            except Exception as e:
                self.logger.error(f"Query execution failed: {str(e)}")
                raise DatabaseOperationError(f"Query execution failed: {str(e)}", e)

    # GET
    def get_where(self, model: Type[DeclarativeBase], filter_conditions: Dict[str, Any]) -> List[DeclarativeBase]:
        """
        Retrieve records from a table based on filter conditions.

        Args:
            model (Type[DeclarativeBase]): Model class representing the table
            filter_conditions (Dict[str, Any]): Dictionary of field-value pairs to filter by

        Returns:
            List[DeclarativeBase]: List of matching records
        """
        with self.get_session() as session:
            try:
                query = session.query(model)
                for field_name, value in filter_conditions.items():
                    field = getattr(model, field_name)
                    if field is None:
                        raise AttributeError(f"Field '{field_name}' does not exist in model '{model.__name__}'")
                    query = query.filter(field == value)
                return query.all()
            except Exception as e:
                self.logger.error(
                    f"Failed to retrieve records from table {model.__tablename__} with conditions {filter_conditions}: {str(e)}"
                )
                raise DatabaseOperationError(
                    f"Failed to retrieve records from table {model.__tablename__} with conditions {filter_conditions}: {str(e)}",
                    e,
                )

    def get_by_field(self, model: Type[DeclarativeBase], field_name: str, value: Any) -> Optional[DeclarativeBase]:
        """
        Retrieve a single record by a specific field.

        Args:
            model (Type[DeclarativeBase]): Model class representing the table
            field_name (str): Field name to filter by
            value (Any): Value to match

        Returns:
            Optional[DeclarativeBase]: The matching record, or None if not found
        """
        with self.get_session() as session:
            try:
                field = getattr(model, field_name)
                if field is None:
                    raise AttributeError(f"Field '{field_name}' does not exist in model '{model.__name__}'")
                return session.query(model).filter(field == value).first()
            except Exception as e:
                self.logger.error(
                    f"Failed to retrieve record from table {model.__tablename__} by field {field_name}: {str(e)}"
                )
                raise DatabaseOperationError(
                    f"Failed to retrieve record from table {model.__tablename__} by field {field_name}: {str(e)}", e
                )

    def get_all(self, model: Type[DeclarativeBase], limit: int = 10000, offset: int = 0) -> List[DeclarativeBase]:
        """
        Retrieve all records from a table with optional pagination.

        Args:
            model (Type[DeclarativeBase]): Model class representing the table
            limit (int): Maximum number of records to retrieve
            offset (int): Number of records to skip

        Returns:
            List[DeclarativeBase]: List of records
        """
        with self.get_session() as session:
            try:
                return session.query(model).limit(limit).offset(offset).all()
            except Exception as e:
                self.logger.error(f"Failed to retrieve records from table {model.__tablename__}: {str(e)}")
                raise DatabaseOperationError(
                    f"Failed to retrieve records from table {model.__tablename__}: {str(e)}", e
                )

    def get_table_summary(self, model: Type[DeclarativeBase]) -> dict:
        """
        Get a summary of the table including total records and column information.

        Args:
            model (Type[DeclarativeBase]): Model class representing the table

        Returns:
            dict: Summary of the table including total records and column information
        """
        with self.get_session() as session:
            try:
                total_records = session.query(model).count()
                columns = {column.name: str(column.type) for column in model.__table__.columns}
                return {"total_records": total_records, "columns": columns}
            except Exception as e:
                self.logger.error(f"Failed to get table summary for {model.__tablename__}: {str(e)}")
                raise DatabaseOperationError(f"Failed to get table summary for {model.__tablename__}: {str(e)}", e)

    # INSERT
    def insert_record(self, model: Type[DeclarativeBase], data: Dict[str, Any]) -> DeclarativeBase:
        """
        Insert a single record into the database.

        Args:
            model (Type[DeclarativeBase]): Model class representing the table
            data (Dict[str, Any]): Data to insert
        Returns:
            DeclarativeBase: The inserted record
        """
        with self.get_session() as session:
            try:
                record = model(**data)
                session.add(record)
                session.commit()
                session.refresh(record)
                return record
            except Exception as e:
                self.logger.error(f"Failed to insert record into table {model.__tablename__}: {str(e)}")
                raise DatabaseOperationError(f"Failed to insert record into table {model.__tablename__}: {str(e)}", e)

    def bulk_insert(self, model_class: Type[DeclarativeBase], data: List[Dict[str, Any]]) -> None:
        """
        Perform bulk insert operation.

        Args:
            model_class (Type[DeclarativeBase]): Model class
            data (List[Dict[str, Any]]): List of data dictionaries
        """
        with self.get_session() as session:
            try:
                session.bulk_insert_mappings(model_class, data)
                self.logger.info(f"Bulk inserted {len(data)} records into {model_class.__name__}")
            except Exception as e:
                self.logger.error(f"Bulk insert failed: {str(e)}")
                raise DatabaseOperationError(f"Bulk insert failed: {str(e)}", e)

    # UPDATE
    def update_where(
        self, model: Type[DeclarativeBase], filter_conditions: Dict[str, Any], update_data: Dict[str, Any]
    ) -> int:
        """
        Update records in a table based on filter conditions.

        Args:
            model (Type[DeclarativeBase]): Model class representing the table
            filter_conditions (Dict[str, Any]): Conditions to filter records for update
            update_data (Dict[str, Any]): Data to update
        Returns:
            int: Number of records updated
        """
        with self.get_session() as session:
            try:
                query = session.query(model)
                for attr, value in filter_conditions.items():
                    query = query.filter(getattr(model, attr) == value)
                updated_count = query.update(update_data)
                return updated_count
            except Exception as e:
                self.logger.error(f"Failed to update records in table {model.__tablename__}: {str(e)}")
                raise DatabaseOperationError(f"Failed to update records in table {model.__tablename__}: {str(e)}", e)

    def bulk_update(self, model_class: Type[DeclarativeBase], data: List[Dict[str, Any]]) -> None:
        """
        Perform bulk update operation.

        Args:
            model_class (Type[DeclarativeBase]): Model class
            data (List[Dict[str, Any]]): List of data dictionaries
        """
        with self.get_session() as session:
            try:
                session.bulk_update_mappings(model_class, data)
                self.logger.info(f"Bulk updated {len(data)} records in {model_class.__name__}")
            except Exception as e:
                self.logger.error(f"Bulk update failed: {str(e)}")
                raise DatabaseOperationError(f"Bulk update failed: {str(e)}", e)

    # DELETE
    def delete_where(self, model: Type[DeclarativeBase], filter_conditions: Dict[str, Any]) -> int:
        """
        Delete records from a table based on filter conditions.

        Args:
            model (Type[DeclarativeBase]): Model class representing the table
            filter_conditions (Dict[str, Any]): Conditions to filter records for deletion
        Returns:
            int: Number of records deleted
        """
        with self.get_session() as session:
            try:
                query = session.query(model)
                for attr, value in filter_conditions.items():
                    query = query.filter(getattr(model, attr) == value)
                deleted_count = query.delete()
                return deleted_count
            except Exception as e:
                self.logger.error(f"Failed to delete records from table {model.__tablename__}: {str(e)}")
                raise DatabaseOperationError(f"Failed to delete records from table {model.__tablename__}: {str(e)}", e)

    def delete_by_field(self, model: Type[DeclarativeBase], field_name: str, value: Any) -> int:
        """
        Delete records from a table based on a specific field.

        Args:
            model (Type[DeclarativeBase]): Model class representing the table
            field_name (str): Field name to filter by
            value (Any): Value to match
        Returns:
            int: Number of records deleted
        """
        with self.get_session() as session:
            try:
                field = getattr(model, field_name)
                if field is None:
                    raise AttributeError(f"Field '{field_name}' does not exist in model '{model.__name__}'")
                deleted_count = session.query(model).filter(field == value).delete()
                return deleted_count
            except Exception as e:
                self.logger.error(
                    f"Failed to delete records from table {model.__tablename__} by field {field_name}: {str(e)}"
                )
                raise DatabaseOperationError(
                    f"Failed to delete records from table {model.__tablename__} by field {field_name}: {str(e)}", e
                )

    def clear_table(self, model: Type[DeclarativeBase]) -> None:
        """
        Clear all data from a table.

        Args:
            model (Type[DeclarativeBase]): Model class representing the table to clear
        """
        with self.get_session() as session:
            try:
                session.query(model).delete()
                self.logger.info(f"Cleared all data from table {model.__tablename__}")
            except Exception as e:
                self.logger.error(f"Failed to clear table {model.__tablename__}: {str(e)}")
                raise DatabaseOperationError(f"Failed to clear table {model.__tablename__}: {str(e)}", e)

    def get_model_by_table_name(self, table_name: str) -> Optional[Type[DeclarativeBase]]:
        for model in self._models_registry:
            if hasattr(model, "__tablename__") and model.__tablename__ == table_name:
                return model
        return None

    def get_models(self) -> List[Type[DeclarativeBase]]:
        return self._models_registry

    def generate_database_backup(
        self,
        return_type: Literal["dict", "csv", "sql", "json"] = "dict",
        limit: int = 10000,
        database_dialect: str | None = None,
    ) -> Any:
        """
        Generate a backup of the database.

        Args:
            return_type (Literal["dict", "csv", "sql", "json"], optional): Format of the backup. Defaults to "dict".
            database_dialect (str|None, optional): Database dialect to use for SQL backup. Defaults to None.
                - "dict": Return the backup as a dictionary.
                - "csv": Return the backup as CSV files.
                - "sql": Return the backup as SQL statements. The `database_dialect` parameter specifies the SQL dialect to use.
                - "json": Return the backup as JSON files.

        Returns:
            Any: The database backup in the specified format.
        """
        if return_type not in ["dict", "csv", "sql", "json"]:
            return_type = "dict"

        try:
            page_size = int(limit)
            if page_size <= 0:
                page_size = 10000
        except (TypeError, ValueError):
            page_size = 10000

        models = self.get_models()

        backup_data: Dict[str, List[Dict[str, Any]]] = {}

        for model in models:
            table_name = getattr(model, "__tablename__", model.__name__.lower())
            offset = 0
            backup_data[table_name] = []
            while True:
                report = self.generate_table_report(model, limit=page_size, offset=offset)
                data = report.get("data", [])
                backup_data[table_name].extend(data)
                if not report.get("has_more"):
                    break
                offset += page_size

        if return_type == "dict":
            # Return the backup data as a dictionary.
            return backup_data
        elif return_type == "csv":
            # Return the backup data as zip of csv files
            zip_buffer = io.BytesIO()
            with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
                for table, rows in backup_data.items():
                    csv_buffer = io.StringIO()
                    if rows:
                        writer = csv.DictWriter(csv_buffer, fieldnames=rows[0].keys())
                        writer.writeheader()
                        writer.writerows(rows)
                    zip_file.writestr(f"{table}.csv", csv_buffer.getvalue())
            zip_buffer.seek(0)
            return zip_buffer.getvalue()
        elif return_type == "json":
            # Return the backup data as zip of JSON files
            zip_buffer = io.BytesIO()
            with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
                for table, rows in backup_data.items():
                    zip_file.writestr(f"{table}.json", json.dumps(rows, indent=2))
            zip_buffer.seek(0)
            return zip_buffer.getvalue()
        elif return_type == "sql":
            # Return the backup data zip of as SQL statements to import to tables.
            def to_sql_literal(value: Any) -> str:
                if value is None:
                    return "NULL"
                if isinstance(value, bool):
                    return "1" if value else "0"
                if isinstance(value, (int, float, Decimal)):
                    return str(value)
                escaped = str(value).replace("'", "''")
                return f"'{escaped}'"

            zip_buffer = io.BytesIO()
            with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
                # Try to detect dialect to produce more appropriate SQL (MySQL/Postgres/SQLite)
                dialect = database_dialect
                if not dialect:
                    try:
                        dialect = self._engine.dialect.name if self._engine else None
                    except Exception:
                        dialect = None

                for table, rows in backup_data.items():
                    sql_lines: List[str] = []

                    # Disable foreign-key checks / prepare truncate/delete depending on dialect
                    if dialect and "mysql" in dialect:
                        sql_lines.append("SET FOREIGN_KEY_CHECKS=0;")
                        sql_lines.append(f"TRUNCATE TABLE {table};")
                    elif dialect and ("postgresql" in dialect or "postgres" in dialect):
                        sql_lines.append(f"ALTER TABLE {table} DISABLE TRIGGER ALL;")
                        sql_lines.append(f"TRUNCATE TABLE {table} RESTART IDENTITY CASCADE;")
                    elif dialect and "sqlite" in dialect:
                        sql_lines.append("PRAGMA foreign_keys=OFF;")
                        sql_lines.append(f"DELETE FROM {table};")
                        # reset sqlite autoincrement
                        sql_lines.append(f"DELETE FROM sqlite_sequence WHERE name='{table}';")
                    else:
                        sql_lines.append(f"DELETE FROM {table};")

                    # Single INSERT with multiple VALUES groups (more efficient)
                    if rows:
                        columns = list(rows[0].keys())
                        column_list = ", ".join(columns)
                        values_groups: List[str] = []
                        for row in rows:
                            values = ", ".join(to_sql_literal(row.get(column)) for column in columns)
                            values_groups.append(f"({values})")
                        sql_lines.append(
                            f"INSERT INTO {table} ({column_list}) VALUES\n" + ",\n".join(values_groups) + ";"
                        )

                    # Re-enable constraints / triggers where applicable
                    if dialect and "mysql" in dialect:
                        sql_lines.append("SET FOREIGN_KEY_CHECKS=1;")
                    elif dialect and ("postgresql" in dialect or "postgres" in dialect):
                        sql_lines.append(f"ALTER TABLE {table} ENABLE TRIGGER ALL;")
                    elif dialect and "sqlite" in dialect:
                        sql_lines.append("PRAGMA foreign_keys=ON;")

                    zip_file.writestr(f"{table}.sql", "\n".join(sql_lines) + "\n")
            zip_buffer.seek(0)
            return zip_buffer.getvalue()

    def __enter__(self):
        """Context manager entry."""
        self.initialize()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()

    def __repr__(self) -> str:
        """String representation of the database manager."""
        status = "initialized" if self._engine else "not_initialized"
        return f"DatabaseManager(status={status}, url={self.database_url})"
