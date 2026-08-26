import pytest
from datetime import date
from decimal import Decimal
from sqlalchemy import text, Column, Integer, String, Date, Numeric, LargeBinary
from sqlalchemy.orm import DeclarativeBase
from src.smartx_rfid.db._main import DatabaseManager, DatabaseOperationError


class Base(DeclarativeBase):
    pass


class DbModel(Base):
    __tablename__ = "db_model"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(50), nullable=False)
    value = Column(Numeric(10, 2), nullable=True)
    dt = Column(Date, nullable=True)
    bin = Column(LargeBinary, nullable=True)

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "value": float(self.value) if self.value is not None else None,
            "dt": self.dt.isoformat() if self.dt else None,
            "bin": self.bin.hex() if self.bin else None,
        }


@pytest.fixture
def db_manager(tmp_path):
    db_path = tmp_path / "test.db"
    db_url = f"sqlite:///{db_path}"
    manager = DatabaseManager(db_url)
    manager.initialize()
    yield manager
    manager.close()


def test_initialize_and_connection_info(db_manager):
    assert db_manager.get_connection_info()["status"] in ("connected",)


def test_create_and_drop_tables(db_manager):
    db_manager.register_models(DbModel)
    db_manager.create_tables()
    assert db_manager.table_exists("db_model")
    names = db_manager.get_table_names()
    assert "db_model" in names
    db_manager.drop_tables()
    assert not db_manager.table_exists("db_model")


def test_insert_get_and_get_all(db_manager):
    db_manager.register_models(DbModel)
    db_manager.create_tables()
    data = {"name": "Alice", "value": Decimal("12.34"), "dt": date(2024, 1, 1), "bin": b"\x01\x02"}
    rec = db_manager.insert_record(DbModel, data)
    assert rec.id is not None
    all_records = db_manager.get_all(DbModel)
    assert len(all_records) == 1
    assert all_records[0].name == "Alice"
    by_field = db_manager.get_by_field(DbModel, "name", "Alice")
    assert by_field is not None
    where = db_manager.get_where(DbModel, {"name": "Alice"})
    assert len(where) == 1


def test_bulk_insert_and_bulk_update(db_manager):
    db_manager.register_models(DbModel)
    db_manager.create_tables()
    items = [{"name": "Bob", "value": Decimal("1.00")}, {"name": "Carol", "value": Decimal("2.00")}]
    db_manager.bulk_insert(DbModel, items)
    all_records = db_manager.get_all(DbModel)
    assert len(all_records) == 2
    ids = [r.id for r in all_records]
    update_mappings = [{"id": ids[0], "value": Decimal("9.99")}, {"id": ids[1], "value": Decimal("8.88")}]
    db_manager.bulk_update(DbModel, update_mappings)
    updated = db_manager.get_all(DbModel)
    values = [float(r.value) for r in updated]
    assert 9.99 in values
    assert 8.88 in values


def test_update_where(db_manager):
    db_manager.register_models(DbModel)
    db_manager.create_tables()
    db_manager.insert_record(DbModel, {"name": "Dave", "value": Decimal("1.23")})
    updated_count = db_manager.update_where(DbModel, {"name": "Dave"}, {"value": Decimal("4.56")})
    assert updated_count >= 1
    rec = db_manager.get_by_field(DbModel, "name", "Dave")
    assert float(rec.value) == float(Decimal("4.56"))


def test_delete_where_and_delete_by_field(db_manager):
    db_manager.register_models(DbModel)
    db_manager.create_tables()
    db_manager.insert_record(DbModel, {"name": "Eve"})
    db_manager.insert_record(DbModel, {"name": "Frank"})
    deleted = db_manager.delete_where(DbModel, {"name": "Eve"})
    assert deleted == 1
    deleted_by = db_manager.delete_by_field(DbModel, "name", "Frank")
    assert deleted_by == 1
    assert db_manager.get_all(DbModel) == []


def test_clear_table(db_manager):
    db_manager.register_models(DbModel)
    db_manager.create_tables()
    db_manager.insert_record(DbModel, {"name": "G1"})
    db_manager.insert_record(DbModel, {"name": "G2"})
    db_manager.clear_table(DbModel)
    assert db_manager.get_all(DbModel) == []


def test_generate_table_report(db_manager):
    db_manager.register_models(DbModel)
    db_manager.create_tables()
    for i in range(3):
        db_manager.insert_record(DbModel, {"name": f"user{i}", "value": Decimal("1.00")})
    report = db_manager.generate_table_report(DbModel, limit=2, offset=0)
    assert report["total"] == 3
    assert report["limit"] == 2
    assert report["offset"] == 0
    assert report["has_more"] is True
    assert len(report["data"]) == 2


def test_execute_query_and_non_select(db_manager):
    db_manager.register_models(DbModel)
    db_manager.create_tables()
    # insert via SQL
    db_manager.execute_query(
        text("INSERT INTO db_model (name, value, dt, bin) VALUES ('H1', 1.23, '2024-01-01', x'0102')")
    )
    result = db_manager.execute_query("SELECT * FROM db_model WHERE name='H1'")
    assert isinstance(result, list)
    assert len(result) == 1
    row = result[0]
    assert isinstance(row["value"], float)
    assert isinstance(row["dt"], str)
    assert isinstance(row["bin"], str)
    # non-select returns None
    res = db_manager.execute_query(text("UPDATE db_model SET name='HN' WHERE name='nope'"))
    assert res is None


def test_session_rollback_on_exception(db_manager):
    db_manager.register_models(DbModel)
    db_manager.create_tables()
    with pytest.raises(DatabaseOperationError):
        with db_manager.get_session() as session:
            session.add(DbModel(name="ShouldRollback"))
            raise Exception("force rollback")
    assert db_manager.get_all(DbModel) == []


def test_scoped_session_and_context_manager(tmp_path):
    db_path = tmp_path / "test2.db"
    db_url = f"sqlite:///{db_path}"
    with DatabaseManager(db_url) as mgr:
        assert "initialized" in repr(mgr)
        s = mgr.get_scoped_session()
        assert hasattr(s, "remove")
    assert "not_initialized" in repr(mgr)
