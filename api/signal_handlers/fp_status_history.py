import logging
from datetime import datetime

from api.operations.genesis.index import update_shared_booking

logger = logging.getLogger(__name__)


def post_save_handler(instance):
    LOG_ID = "[FP_STATUS_HISTORY POST SAVE]"

    # Genesis
    update_shared_booking(instance.booking)
