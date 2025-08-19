import os
import sys
import logging

db_file = os.environ.get("DB_FILE", "../data/emails.db")

log_file = os.path.join(os.path.dirname(__file__), "../logs/emails.log")

class StdoutFilter(logging.Filter):
    def filter(self, record):
        return record.levelno <= logging.INFO

class StderrFilter(logging.Filter):
    def filter(self, record):
        return record.levelno >= logging.WARNING

logger = logging.getLogger("email_logger")
logger.setLevel(logging.DEBUG)

# Handler for stdout (INFO and below)
stdout_handler = logging.StreamHandler(sys.stdout)
stdout_handler.setLevel(logging.DEBUG)
stdout_handler.addFilter(StdoutFilter())
stdout_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))

# Handler for stderr (WARNING and above)
stderr_handler = logging.StreamHandler(sys.stderr)
stderr_handler.setLevel(logging.WARNING)
stderr_handler.addFilter(StderrFilter())
stderr_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))

# Handler for file (all levels)
file_handler = logging.FileHandler(log_file)
file_handler.setLevel(logging.DEBUG)
file_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))

# Add handlers to logger
logger.handlers.clear()
logger.addHandler(stdout_handler)
logger.addHandler(stderr_handler)
logger.addHandler(file_handler)

# Usage: from src import logger
# logger.info("Info message")
# logger.warning("Warning message")
# logger.error("Error message")
