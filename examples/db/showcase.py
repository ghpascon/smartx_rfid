"""
SQLite Database Example using SmartX RFID Database Manager

This example demonstrates how to use the DatabaseManager with SQLite database,
including model operations, raw SQL queries, and CRUD operations.
"""

from datetime import datetime

from sqlalchemy import Column, Integer, String, Float, DateTime, create_engine
from sqlalchemy.orm import DeclarativeBase
from smartx_rfid.db._main import DatabaseManager

# Database config
# SQLite database file path
# db_path = r"C:\Users\DELL\Desktop\instance\smtx.sqlite"
# database_url = f"sqlite:///{db_path}"

# Mysql connection string
database_url = r"mysql+pymysql://root:admin@localhost:3306/lib_smtx"

# PostgreSQL connection string
# database_url = r"postgresql+psycopg2://app_user:app_password@localhost:5432/lib_smartx"
  
class Base(DeclarativeBase):
    """Base class for all models"""
    pass


class ModelTag(Base):
    """
    RFID Tag Model for storing tag information
    """
    __tablename__ = 'rfid_tags'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    epc = Column(String(50), unique=True, nullable=False, index=True)
    tid = Column(String(50), nullable=True)
    ant = Column(Integer, nullable=False)  # Antenna number
    rssi = Column(Float, nullable=False)   # Signal strength
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)
    
    def __repr__(self):
        return f"<ModelTag(epc='{self.epc}', ant={self.ant}, rssi={self.rssi})>"
    
    def to_dict(self):
        """Convert model to dictionary"""
        return {
            'id': self.id,
            'epc': self.epc,
            'tid': self.tid,
            'ant': self.ant,
            'rssi': self.rssi,
            'created_at': self.created_at,
            'updated_at': self.updated_at
        }


def setup_database() -> DatabaseManager:
    """
    Setup and initialize SQLite database
    """
    print("🗃️ Setting up SQLite database...")
    

    # Initialize database manager
    db_manager = DatabaseManager(
        database_url=database_url,
        echo=True,  
        pool_size=5,
        pool_timeout=30
    )
    
    # Initialize database connection
    db_manager.initialize()
    
    # Register models
    db_manager.register_models(ModelTag)
    
    # Create tables
    print("📋 Creating database tables...")
    db_manager.create_tables()
    
    print("✅ Database setup completed!\n")
    return db_manager


def insert_tag_examples(db_manager: DatabaseManager):
    """
    Demonstrate inserting tags using SQLAlchemy models
    """
    print("📝 Inserting sample tags using models...")
    
    with db_manager.get_session() as session:
        # Create sample tags
        tags = [
            ModelTag(epc="E200001175000001", tid="E200001175000001ABCD", ant=1, rssi=-45.5),
            ModelTag(epc="E200001175000002", tid="E200001175000002EFGH", ant=2, rssi=-52.3),
            ModelTag(epc="E200001175000003", tid="E200001175000003IJKL", ant=1, rssi=-38.7),
            ModelTag(epc="E200001175000004", tid="E200001175000004MNOP", ant=3, rssi=-61.2),
        ]
        
        # Add tags to session
        for tag in tags:
            session.add(tag)
            
        print(f"✅ Inserted {len(tags)} tags successfully!")


def get_tag_examples(db_manager: DatabaseManager):
    """
    Demonstrate reading tags using SQLAlchemy models
    """
    print("\n📖 Reading tags using models...")
    
    with db_manager.get_session() as session:
        # Get all tags
        all_tags = session.query(ModelTag).all()
        print(f"📊 Total tags in database: {len(all_tags)}")
        
        # Display all tags
        for tag in all_tags:
            print(f"  - {tag}")
        
        print("\n🔍 Filtered queries:")
        
        # Get tags by antenna
        ant1_tags = session.query(ModelTag).filter(ModelTag.ant == 1).all()
        print(f"  📡 Tags on antenna 1: {len(ant1_tags)}")
        
        # Get tags with strong signal (RSSI > -50)
        strong_signal_tags = session.query(ModelTag).filter(ModelTag.rssi > -50).all()
        print(f"  📶 Tags with strong signal: {len(strong_signal_tags)}")
        
        # Get tag by EPC
        specific_tag = session.query(ModelTag).filter(ModelTag.epc == "E200001175000001").first()
        if specific_tag:
            print(f"  🏷️ Found specific tag: {specific_tag}")


def update_tag_examples(db_manager: DatabaseManager):
    """
    Demonstrate updating tags using SQLAlchemy models
    """
    print("\n✏️ Updating tags using models...")
    
    with db_manager.get_session() as session:
        # Find a tag to update
        tag_to_update = session.query(ModelTag).filter(ModelTag.epc == "E200001175000001").first()
        
        if tag_to_update:
            print(f"📝 Updating tag: {tag_to_update.epc}")
            
            # Update values
            old_rssi = tag_to_update.rssi
            tag_to_update.rssi = -42.1  # New RSSI value
            tag_to_update.ant = 4       # New antenna
            tag_to_update.updated_at = datetime.utcnow()
            
            print(f"  📶 RSSI updated: {old_rssi} -> {tag_to_update.rssi}")
            print(f"  📡 Antenna updated: -> {tag_to_update.ant}")
            print("✅ Tag updated successfully!")
        else:
            print("❌ Tag not found for update")


def bulk_operations_example(db_manager: DatabaseManager):
    """
    Demonstrate bulk operations
    """
    print("\n🔄 Bulk operations example...")
    
    # Bulk insert data
    bulk_data = [
        {"epc": "E200001175000010", "tid": "E200001175000010BULK", "ant": 2, "rssi": -55.1},
        {"epc": "E200001175000011", "tid": "E200001175000011BULK", "ant": 3, "rssi": -48.3},
        {"epc": "E200001175000012", "tid": "E200001175000012BULK", "ant": 1, "rssi": -59.7},
    ]
    
    try:
        db_manager.bulk_insert(ModelTag, bulk_data)
        print("✅ Bulk insert completed!")
    except Exception as e:
        print(f"❌ Bulk insert failed: {e}")


def raw_sql_examples(db_manager: DatabaseManager):
    """
    Demonstrate raw SQL queries
    """
    print("\n🔧 Raw SQL query examples...")
    
    # Raw SQL Insert
    print("📝 Raw SQL Insert:")
    insert_query = """
        INSERT INTO rfid_tags (epc, tid, ant, rssi, created_at, updated_at)
        VALUES (:epc, :tid, :ant, :rssi, :created_at, :updated_at)
    """
    
    try:
        db_manager.execute_query(
            insert_query,
            params={
                "epc": "E200001175000020",
                "tid": "E200001175000020SQL",
                "ant": 2,
                "rssi": -41.5,
                "created_at": datetime.utcnow(),
                "updated_at": datetime.utcnow()
            }
        )
        print("✅ Raw SQL insert completed!")
    except Exception as e:
        print(f"❌ Raw SQL insert failed: {e}")
    
    # Raw SQL Select
    print("\n📖 Raw SQL Select:")
    select_queries = [
        ("All tags count", "SELECT COUNT(*) as total_tags FROM rfid_tags"),
        ("Average RSSI", "SELECT AVG(rssi) as avg_rssi FROM rfid_tags"),
        ("Tags by antenna", "SELECT ant, COUNT(*) as count FROM rfid_tags GROUP BY ant ORDER BY ant"),
        ("Recent tags", "SELECT epc, rssi, ant FROM rfid_tags ORDER BY created_at DESC LIMIT 3")
    ]
    
    for description, query in select_queries:
        try:
            result = db_manager.execute_query_fetchall(query)
            print(f"  🔍 {description}:")
            for row in result:
                print(f"    {dict(row._mapping)}")
        except Exception as e:
            print(f"    ❌ Query failed: {e}")


def search_examples(db_manager: DatabaseManager):
    """
    Demonstrate search operations
    """
    print("\n🔍 Search examples...")
    
    # Search with parameters
    search_queries = [
        ("Find tags with RSSI stronger than -50", 
         "SELECT epc, rssi, ant FROM rfid_tags WHERE rssi > :rssi_threshold",
         {"rssi_threshold": -50}),
        
        ("Find tags on specific antenna",
         "SELECT epc, tid, rssi FROM rfid_tags WHERE ant = :antenna",
         {"antenna": 1}),
        
        ("Find tags with EPC pattern",
         "SELECT epc, ant, rssi FROM rfid_tags WHERE epc LIKE :pattern",
         {"pattern": "%000001%"})
    ]
    
    for description, query, params in search_queries:
        try:
            results = db_manager.execute_query_fetchall(query, params)
            print(f"  {description}: Found {len(results)} tags")
            for result in results[:3]:  # Show first 3 results
                print(f"    {dict(result._mapping)}")
        except Exception as e:
            print(f"    ❌ Search failed: {e}")


def show_database_stats(db_manager: DatabaseManager):
    """
    Show database statistics and information
    """
    print("\n📊 Database Statistics:")
    
    # Connection info
    conn_info = db_manager.get_connection_info()
    print(f"  💾 Database type: {conn_info.get('database_type', 'Unknown')}")
    print(f"  🔗 Connection status: {conn_info.get('status', 'Unknown')}")
    print(f"  🏊 Pool size: {conn_info.get('pool_size', 'N/A')}")
    
    # Table info
    tables = db_manager.get_table_names()
    print(f"  📋 Tables: {tables}")
    
    # Record count
    with db_manager.get_session() as session:
        total_tags = session.query(ModelTag).count()
        print(f"  🏷️ Total tags: {total_tags}")


def cleanup_example(db_manager: DatabaseManager):
    """
    Demonstrate cleanup operations
    """
    print("\n🧹 Cleanup operations:")
    
    # Delete old test records (optional)
    response = input("Do you want to delete all test records? (y/N): ")
    if response.lower() == 'y':
        with db_manager.get_session() as session:
            deleted_count = session.query(ModelTag).delete()
            print(f"🗑️ Deleted {deleted_count} records")
    
    # Close database connection
    db_manager.close()
    print("🔒 Database connection closed")


def main():
    """
    Main function to run all examples
    """
    print("🚀 SmartX RFID SQLite Database Example")
    print("=" * 50)
    
    try:
        # Setup database
        db_manager = setup_database()
        
        # Run examples
        insert_tag_examples(db_manager)
        get_tag_examples(db_manager)
        update_tag_examples(db_manager)
        bulk_operations_example(db_manager)
        raw_sql_examples(db_manager)
        search_examples(db_manager)
        show_database_stats(db_manager)
        
        print("\n🎉 All examples completed successfully!")
        
        # Cleanup
        cleanup_example(db_manager)
        
    except Exception as e:
        print(f"❌ Error occurred: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
