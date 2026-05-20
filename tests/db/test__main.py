import pytest
import json
from sqlalchemy import text
from src.smartx_rfid.db._main import DatabaseManager
import tempfile


def test_execute_query_json_serializable():
    """
    Testa se o resultado de execute_query é serializável em JSON e se os dados estão normalizados corretamente.
    """
    tmp_path = tempfile.mkdtemp()
    db_url = f"sqlite:///{tmp_path}/test.db"
    db = DatabaseManager(db_url)
    db.initialize()
    db.execute_query(text("CREATE TABLE test (id INTEGER PRIMARY KEY, value DECIMAL, dt DATE, bin BLOB)"))
    db.execute_query(text("INSERT INTO test (value, dt, bin) VALUES (1.23, '2024-01-01', x'0102')"))

    result = db.execute_query("SELECT * FROM test")
    assert isinstance(result, list)
    assert len(result) == 1
    row = result[0]
    # Verifica tipos normalizados
    assert isinstance(row["value"], float)
    assert isinstance(row["dt"], str)
    assert isinstance(row["bin"], str)
    # Verifica serialização JSON
    try:
        json_str = json.dumps(result)
        assert isinstance(json_str, str)
    except Exception as e:
        pytest.fail(f"Resultado não é JSON serializável: {e}")
