import logging
import os

log_level = os.getenv("LOG_LEVEL", "INFO").upper()

log_dir = os.path.join(os.getenv("LOG_DIR", "../logs"))
os.makedirs(log_dir, exist_ok=True)


logger = logging.getLogger(__name__)
logger.setLevel(log_level)

# Create file handler
file_handler = logging.FileHandler(os.path.join(log_dir, "app.log"))

file_handler.setLevel(log_level)


# Create console handler
console_handler = logging.StreamHandler()
console_handler.setLevel(log_level)

# Create formatter and add it to the handlers
formatter = logging.Formatter(
    "%(asctime)s - %(filename)s:%(funcName)s:%(lineno)d - %(levelname)s - %(message)s"
)
file_handler.setFormatter(formatter)
console_handler.setFormatter(formatter)

logger.addHandler(file_handler)
logger.addHandler(console_handler)
