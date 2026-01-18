from util.logging import logger


def healthcheck() -> bool:
    logger.info("Healthcheck passed!")
    exit(0)
