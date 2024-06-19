import logging
from datetime import datetime

from api.helpers.list import *
from api.operations.booking.surcharge import handle_manual_surcharge_change

logger = logging.getLogger(__name__)
IMPORTANT_FIELDS = ["amount", "qty"]


def post_save_handler(instance, created, update_fields):
    LOG_ID = "[SIG - SURCHAGE POST SAVE]"

    if instance.booking and (
        intersection(IMPORTANT_FIELDS, update_fields or []) or created
    ):
        logger.info(f"{LOG_ID} Created new or updated important field - {instance}")
        handle_manual_surcharge_change(instance.booking, instance)


def post_delete_handler(instance):
    LOG_ID = "[SIG - SURCHAGE POST DELETE]"

    if instance.booking:
        logger.info(f"{LOG_ID} Deleted - {instance}")
        handle_manual_surcharge_change(instance.booking, instance)
