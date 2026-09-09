#!/usr/bin/env python3
from smartx_rfid.db import DatabaseManager
from pprint import pprint
import logging

logging.basicConfig(level=logging.INFO)

# Update this URL if different in your environment
DB_URL = "mysql+pymysql://root:admin@localhost:3306/idl"

if __name__ == "__main__":
    mgr = DatabaseManager(database_url=DB_URL, echo=False)
    try:
        mgr.initialize()
        result = mgr.execute_query("SHOW CREATE TABLE baseinv")
        pprint(result)
    except Exception as e:
        print("ERROR fetching schema:", e)
    finally:
        try:
            mgr.close()
        except Exception:
            pass
