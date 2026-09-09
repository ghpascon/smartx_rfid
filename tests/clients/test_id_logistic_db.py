import sys
import pathlib
import importlib.util
from smartx_rfid.db._main import DatabaseManager

# Ensure `src` is on sys.path so package imports work for DatabaseManager
src_dir = pathlib.Path(__file__).resolve().parents[2] / "src"
sys.path.insert(0, str(src_dir))


# Load id_logistic module directly to avoid importing smartx_rfid.clients.__init__
id_path = src_dir / "smartx_rfid" / "clients" / "id_logistic.py"
spec = importlib.util.spec_from_file_location("id_logistic_module", str(id_path))
id_mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(id_mod)
IdLogisticClient = id_mod.IdLogisticClient


def test_save_logconf_and_save_position(tmp_path):
    db_file = tmp_path / "test.db"
    db_url = f"sqlite:///{db_file}"
    dbm = DatabaseManager(database_url=db_url, echo=False, pool_size=1, max_overflow=0)
    dbm.initialize()

    # Create required tables
    dbm.execute_query(
        "CREATE TABLE logconf (suporte TEXT, bancada INTEGER, data TEXT, hora TEXT, usuario TEXT, embalagem TEXT, status TEXT, codpro TEXT, quantidade INTEGER, sinal TEXT)"
    )
    dbm.execute_query(
        "CREATE TABLE logconfdiv (suporte TEXT, bancada INTEGER, data TEXT, hora TEXT, usuario TEXT, embalagem TEXT, status TEXT, codpro TEXT, quantidade INTEGER, sinal TEXT, qtesperada INTEGER)"
    )
    dbm.execute_query(
        "CREATE TABLE baseinv (numinv TEXT, numdoc TEXT, seqdoc TEXT, etadoc TEXT, codpro TEXT, pecas_esp INTEGER, pecas_inv INTEGER, status TEXT, posicao TEXT, user TEXT)"
    )

    client = IdLogisticClient()
    client.db_manager = dbm
    client.user = "tester"

    # save_logconf normal
    ok, err = client.save_logconf(
        {"suporte": "A1", "status": "OK", "codpro": "123", "quantidade": 10, "sinal": "="}, tablename="logconf"
    )
    assert ok, err

    rows = dbm.execute_query("SELECT * FROM logconf")
    assert len(rows) == 1
    row = rows[0]
    assert row["suporte"] == "A1"
    assert int(row["quantidade"]) == 10

    # save_logconf div with qtesperada
    ok, err = client.save_logconf(
        {"suporte": "B2", "status": "OK", "codpro": "456", "quantidade": 5, "sinal": "=", "qtesperada": 6},
        tablename="logconfdiv",
    )
    assert ok, err
    rowsdiv = dbm.execute_query("SELECT * FROM logconfdiv")
    assert len(rowsdiv) == 1
    assert int(rowsdiv[0]["qtesperada"]) == 6

    # save_position
    comparison = [
        {"ean": "123", "sku": "SKU1", "match": "=", "expected_qty": 10, "current_qty": 10},
        {"ean": "999", "match": "!", "expected_qty": 0, "current_qty": 3},
    ]
    position_info = {"numinv": "N1", "numdoc": "D1", "seqdoc": "S1", "etadoc": "2026-09-09", "posicao": "A1"}
    ok, err = client.save_position(position_info, comparison)
    assert ok, err
    base_rows = dbm.execute_query("SELECT * FROM baseinv")
    assert len(base_rows) == 2
    cods = set(r["codpro"] for r in base_rows)
    assert "SKU1" in cods and "999" in cods


def test_get_logconf_status_count(tmp_path):
    db_file = tmp_path / "test2.db"
    db_url = f"sqlite:///{db_file}"
    dbm = DatabaseManager(database_url=db_url, echo=False, pool_size=1, max_overflow=0)
    dbm.initialize()

    # Create tables and insert values
    dbm.execute_query("CREATE TABLE logconf (sinal TEXT, data TEXT)")
    dbm.execute_query("CREATE TABLE logconfdiv (sinal TEXT, data TEXT)")
    dbm.execute_query("INSERT INTO logconf (sinal, data) VALUES ('A', '2026-09-09')")
    dbm.execute_query("INSERT INTO logconf (sinal, data) VALUES ('B', '2026-09-09')")
    dbm.execute_query("INSERT INTO logconfdiv (sinal, data) VALUES ('A', '2026-09-09')")

    client = IdLogisticClient()
    client.db_manager = dbm

    ok, counts = client.get_logconf_status_count(days=None)
    assert ok
    assert counts.get("A") == 2
    assert counts.get("B") == 1
