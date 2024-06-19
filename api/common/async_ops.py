import logging
import time as t

from api.common.thread import background


logger = logging.getLogger(__name__)


@background
def quote_in_bg(booking):
    LOG_ID = "[QUOTE IN BG]"
    from api.fp_apis.operations.pricing import pricing as pricing_oper

    t.sleep(5)
    _, success, message, quotes, client = pricing_oper(
        body=None,
        booking_id=booking.pk,
        is_pricing_only=False,
    )

    logger.info(
        f"#090 {LOG_ID} Pricing result: success: {success}, message: {message}, results cnt: {len(quotes)}"
    )
