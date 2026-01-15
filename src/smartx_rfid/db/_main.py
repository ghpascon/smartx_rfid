import logging
from typing import Any, Dict, List, Optional, Type, Union
from contextlib import contextmanager
from sqlalchemy import (
    create_engine, 
    text, 
    MetaData, 
    inspect,
    event
)
from sqlalchemy.orm import (
    sessionmaker, 
    Session, 
    DeclarativeBase,
    scoped_session
)
from sqlalchemy.pool import QueuePool
from sqlalchemy.exc import (
    DatabaseError
)
from sqlalchemy.engine import Engine
import threading


class DatabaseError(Exception):
    """Custom database exception for better error handling"""
    pass


class DatabaseConnectionError(DatabaseError):
    """Raised when database connection fails"""
    pass


class DatabaseOperationError(DatabaseError):
    """Raised when database operations fail"""
    pass


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
        **engine_kwargs
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
            'echo': echo,
            'poolclass': QueuePool,
            'pool_size': pool_size,
            'max_overflow': max_overflow,
            'pool_timeout': pool_timeout,
            'pool_recycle': pool_recycle,
            'pool_pre_ping': True,  # Validate connections before use
            **engine_kwargs
        }
        
        # Setup logging
        self.logger = logging.getLogger(__name__)
        
    def initialize(self) -> None:
        """Initialize the database engine and session factory."""
        try:
            with self._lock:
                if self._engine is None:
                    self._engine = create_engine(
                        self.database_url,
                        **self._engine_config
                    )
                    
                    # Setup connection event listeners
                    self._setup_event_listeners()
                    
                    # Create session factory
                    self._session_factory = sessionmaker(
                        bind=self._engine,
                        expire_on_commit=False
                    )
                    
                    # Create scoped session for thread safety
                    self._scoped_session = scoped_session(self._session_factory)
                    
                    # Create metadata instance
                    self._metadata = MetaData()
                    
                    self.logger.info(f"Database initialized successfully: {self._get_db_info()}")
                    
        except Exception as e:
            self.logger.error(f"Failed to initialize database: {str(e)}")
            raise DatabaseConnectionError(f"Database initialization failed: {str(e)}")
    
    def _setup_event_listeners(self) -> None:
        """Setup SQLAlchemy event listeners for connection management."""
        @event.listens_for(self._engine, "connect")
        def set_sqlite_pragma(dbapi_connection, connection_record):
            """Configure SQLite specific settings."""
            if 'sqlite' in self.database_url.lower():
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
            base_metadata.create_all(
                bind=self._engine,
                checkfirst=checkfirst
            )
            
            self.logger.info(f"Tables created successfully for {len(self._models_registry)} models")
            
        except Exception as e:
            self.logger.error(f"Failed to create tables: {str(e)}")
            raise DatabaseOperationError(f"Table creation failed: {str(e)}")
    
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
            base_metadata.drop_all(
                bind=self._engine,
                checkfirst=checkfirst
            )
            
            self.logger.info("Tables dropped successfully")
            
        except Exception as e:
            self.logger.error(f"Failed to drop tables: {str(e)}")
            raise DatabaseOperationError(f"Table dropping failed: {str(e)}")
    
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
            raise DatabaseOperationError(f"Failed to get table names: {str(e)}")
    
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
            raise DatabaseOperationError(f"Database operation failed: {str(e)}")
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
    
    def execute_query(
        self, 
        query: Union[str, text], 
        params: Optional[Dict[str, Any]] = None
    ) -> Any:
        """
        Execute a raw SQL query.
        
        Args:
            query (Union[str, text]): SQL query to execute
            params (Optional[Dict[str, Any]]): Query parameters
            
        Returns:
            Any: Query result
        """
        with self.get_session() as session:
            try:
                if isinstance(query, str):
                    query = text(query)
                    
                result = session.execute(query, params or {})
                return result
            except Exception as e:
                self.logger.error(f"Query execution failed: {str(e)}")
                raise DatabaseOperationError(f"Query execution failed: {str(e)}")
    
    def execute_query_fetchall(
        self, 
        query: Union[str, text], 
        params: Optional[Dict[str, Any]] = None
    ) -> List[Any]:
        """
        Execute a raw SQL query and fetch all results.
        
        Args:
            query (Union[str, text]): SQL query to execute
            params (Optional[Dict[str, Any]]): Query parameters
            
        Returns:
            List[Any]: Query results
        """
        result = self.execute_query(query, params)
        return result.fetchall()
    
    def execute_query_fetchone(
        self, 
        query: Union[str, text], 
        params: Optional[Dict[str, Any]] = None
    ) -> Any:
        """
        Execute a raw SQL query and fetch one result.
        
        Args:
            query (Union[str, text]): SQL query to execute
            params (Optional[Dict[str, Any]]): Query parameters
            
        Returns:
            Any: Query result
        """
        result = self.execute_query(query, params)
        return result.fetchone()
    
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
                raise DatabaseOperationError(f"Bulk insert failed: {str(e)}")
    
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
                raise DatabaseOperationError(f"Bulk update failed: {str(e)}")
    
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