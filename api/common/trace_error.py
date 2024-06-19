import logging
import traceback

from django.conf import settings

logger = logging.getLogger(__name__)


def print():
    logger.error(f"@000 traceback: {traceback.format_exc()}")
