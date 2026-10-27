from datetime import datetime
from time import sleep
import logging
from smartx_rfid.utils import LoggerManager

logging.basicConfig(level=logging.INFO)

# Run Once to configure the logger manager.
# The database table (default model: smartx_rfid.models.log.Logs) is created automatically
# and logs are inserted in batches in a background thread, so logging never blocks the app.
logger = LoggerManager(
    database_url="sqlite:///logs.db",  # or mysql+pymysql://..., postgresql+psycopg2://...
    db_batch_size=100,  # max rows per bulk insert
    db_flush_interval=2.0,  # max seconds a row waits before being inserted
    db_storage_days=30,  # delete database logs older than 30 days (0 keeps only today's logs)
)

# File system and database can be used together:
# logger = LoggerManager(
#     log_path="C:/Users/DELL/Documents/Logs",
#     base_filename="app",  # optional, defaults to the executed script name
#     storage_days=7,
#     database_url="sqlite:///logs.db",
# )

# An existing DatabaseManager (and a custom model) can be used instead of a URL:
# from smartx_rfid.db import DatabaseManager
# db = DatabaseManager("sqlite:///logs.db")
# logger = LoggerManager(database_manager=db, database_model=MyLogModel)


def register_logs():
    start_time = datetime.now()
    logging.info(f"{'=' * 60}")
    logging.info("Logger initialized from utils/logger_database.py")
    logging.debug("Debugging information (ignored, root level is INFO)")
    logging.warning("Warning from utils/logger_database.py")
    logging.error("Error from utils/logger_database.py")
    stop_time = datetime.now()
    # Extra fields are stored as JSON in the "extra" column
    logging.info(
        f"Logging completed in {stop_time - start_time}", extra={"execution_time": str(stop_time - start_time)}
    )

    raise Exception("Test exception to verify logging of exceptions")


try:
    register_logs()
except Exception as e:
    logging.error("Exception occurred", exc_info=e)
finally:
    logging.info("Shutting down logger")
    logger.flush()  # optional: wait until buffered rows are written
    print(logger.get_stats())
    sleep(1)
    logger.close()  # flushes what is left and closes the database connections
