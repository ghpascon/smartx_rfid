import logging

from smartx_rfid.utils import LoggerManager
from time import sleep

# Run Once to configure the logger manager
LoggerManager(
    "C:/Users/DELL/Documents/Logs",
    "app",
    1,
)

logging.info(f"{'=' * 60}")
logging.info("Logger initialized from utils/logger.py")
logging.debug("Debugging information from utils/logger.py")
logging.warning("Warning from utils/logger.py")
logging.error("Error from utils/logger.py")

sleep(1)  # Just to separate log entries for clarity
