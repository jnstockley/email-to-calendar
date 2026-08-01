import sys

from util.logging import logger


def healthcheck() -> bool:
    logger.info("Healthcheck passed!")
    sys.exit(0)
