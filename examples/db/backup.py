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


class Test02(Base, BaseMixin):
    __tablename__ = "test02"
    id = Column(Integer, primary_key=True, autoincrement=True)
    data3 = Column(String(100), nullable=False, index=True, unique=True)
    data4 = Column(String(255), nullable=False)


# sqlite in memory
db_manager = DatabaseManager("sqlite:///:memory:")
db_manager.initialize()
db_manager.register_models(Test01, Test02)
db_manager.create_tables()

# Fake data
with db_manager.get_session() as session:
    test01 = Test01(data1="data1_value", data2="data2_value")
    test02 = Test02(data3="data3_value", data4="data4_value")
    test03 = Test01(data1="data1_value_2", data2="data2_value_2")
    test04 = Test02(data3="data3_value_2", data4="data4_value_2")
    session.add(test01)
    session.add(test02)
    session.add(test03)
    session.add(test04)

logging.info("Database has been populated with fake data.")

logging.info(f"Backup = {db_manager.generate_database_backup()}")
sql_file_zip = db_manager.generate_database_backup("sql", database_dialect="mysql")
dir_path = "./backup"
os.makedirs(dir_path, exist_ok=True)
with open(f"{dir_path}/backup.zip", "wb") as f:
    f.write(sql_file_zip)
