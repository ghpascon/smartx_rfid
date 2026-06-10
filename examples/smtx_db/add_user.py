from smartx_rfid.smtx_db import SmtxDb, connection_string_example
from smartx_rfid.auth import AuthManager

auth_manager = AuthManager()
db = SmtxDb(connection_string_example)

db.add_user("Gabriel", auth_manager.hash_password("hashed"))
