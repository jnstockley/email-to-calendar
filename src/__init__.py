import os
import sys
import logging

if not os.path.isdir("../data"):
    os.makedirs("../data")

db_file = os.environ.get("DB_FILE", "../data/emails.db")

if not os.path.isdir("../logs"):
    os.makedirs("../logs")

if not os.path.exists(os.path.join(os.path.dirname(__file__), "../logs/emails.log")):
    open(os.path.join(os.path.dirname(__file__), "../logs/emails.log"), "w").close()

log_file = os.path.join(os.path.dirname(__file__), "../logs/emails.log")


class StdoutFilter(logging.Filter):
    def filter(self, record):
        return record.levelno <= logging.INFO


class StderrFilter(logging.Filter):
    def filter(self, record):
        return record.levelno >= logging.WARNING


logger = logging.getLogger("email_logger")
logger.setLevel(logging.DEBUG)

log_format = (
    "%(asctime)s [%(levelname)s] %(filename)s:%(funcName)s:%(lineno)d %(message)s"
)

# Handler for stdout (INFO and below)
stdout_handler = logging.StreamHandler(sys.stdout)
stdout_handler.setLevel(logging.DEBUG)
stdout_handler.addFilter(StdoutFilter())
stdout_handler.setFormatter(logging.Formatter(log_format))

# Handler for stderr (WARNING and above)
stderr_handler = logging.StreamHandler(sys.stderr)
stderr_handler.setLevel(logging.WARNING)
stderr_handler.addFilter(StderrFilter())
stderr_handler.setFormatter(logging.Formatter(log_format))

# Handler for file (all levels)
file_handler = logging.FileHandler(log_file)
file_handler.setLevel(logging.DEBUG)
file_handler.setFormatter(logging.Formatter(log_format))

# Add handlers to logger
logger.handlers.clear()
logger.addHandler(stdout_handler)
logger.addHandler(stderr_handler)
logger.addHandler(file_handler)

# Usage: from src import logger
# logger.info("Info message")
# logger.warning("Warning message")
# logger.error("Error message")
