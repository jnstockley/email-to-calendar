import os
import sys
import logging
from pathlib import Path

from src.util.env import get_settings

settings = get_settings()

db_file = Path(settings.DB_FILE)

db_file.parent.mkdir(parents=True, exist_ok=True)

log_file_path = Path(os.path.dirname(__file__), "../logs/emails.log")
log_file_path.parent.mkdir(parents=True, exist_ok=True)
log_file_path.touch(exist_ok=True)


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
file_handler = logging.FileHandler(log_file_path)
file_handler.setLevel(logging.DEBUG)
file_handler.setFormatter(logging.Formatter(log_format))

# Add handlers to logger
logger.handlers.clear()
logger.addHandler(stdout_handler)
logger.addHandler(stderr_handler)
logger.addHandler(file_handler)
