from smartx_rfid.db import DatabaseManager
from smartx_rfid.models import Base, BaseMixin
import logging
from sqlalchemy import Column, String, Integer
import os

logging.basicConfig(level=logging.INFO)


class Test01(Base, BaseMixin):
    __tablename__ = "test01"
    id = Column(Integer, primary_key=True, autoincrement=True)
    data1 = Column(String(100), nullable=False, index=True, unique=True)
    data2 = Column(String(255), nullable=False)


# sqlite in memory
db_manager = DatabaseManager("sqlite:///:memory:")
db_manager.initialize()
db_manager.register_models(Test01)
db_manager.create_tables()

# Fake data
with db_manager.get_session() as session:
    test01 = Test01(data1="data1_value", data2="data2_value")
    test03 = Test01(data1="data1_value_2", data2="data2_value_2")
    session.add(test01)
    session.add(test03)

db_manager.upsert(Test01, {"data1": "data1_value", "data2": "data4_value"}, "data1")
logging.info("Performed upsert operation.")
db_manager.bulk_upsert(
    Test01,
    [
        {"data1": "data1_value", "data2": "abc"},
        {"data1": "data1_value_2", "data2": "def"},
        {"data1": "data1_value_3", "data2": "123"},
    ],
    "data1",
)
logging.info("Database has been populated with fake data.")

logging.info(f"Backup = {db_manager.generate_database_backup()}")
sql_file_zip = db_manager.generate_database_backup("sql", database_dialect="mysql")
dir_path = "./backup"
os.makedirs(dir_path, exist_ok=True)
with open(f"{dir_path}/backup.zip", "wb") as f:
    f.write(sql_file_zip)
