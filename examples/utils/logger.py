import logging

from smartx_rfid.utils import LoggerManager
from time import sleep
from datetime import datetime

# Run Once to configure the logger manager
logger = LoggerManager(
    "C:/Users/DELL/Documents/Logs",
    "app",
    1,
)


def register_logs():
    start_time = datetime.now()
    logging.info(f"{'=' * 60}")
    logging.info("Logger initialized from utils/logger.py")
    logging.debug("Debugging information from utils/logger.py")
    logging.warning("Warning from utils/logger.py")
    logging.error("Error from utils/logger.py")
    stop_time = datetime.now()
    logging.info(
        f"Logging completed in {(stop_time - start_time)} seconds", extra={"execution_time": (stop_time - start_time)}
    )

    raise Exception("Test exception to verify logging of exceptions")


try:
    register_logs()
except Exception as e:
    logging.error("Exception occurred", exc_info=e)
finally:
    logging.info("Shutting down logger")
    sleep(1)
    logger.close()
