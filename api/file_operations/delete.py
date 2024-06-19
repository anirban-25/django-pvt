import logging
import os

logger = logging.getLogger(__name__)


def delete(file_path):
    if os.path.isfile(file_path):
        os.remove(file_path)
    else:
        logger.error(f"File does not exist: {file_path}")
