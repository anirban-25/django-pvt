import logging
from api.models import (
    Bookings,
    Booking_lines,
    API_booking_quotes,
)

from api.common.booking_quote import set_booking_quote
from api.fp_apis.utils import select_best_options
from api.fp_apis.operations.pricing import pricing as pricing_oper

logger = logging.getLogger(__name__)


def get_quote_again(booking):
    LOG_ID = "[RE-QUOTE]"

    logger.info(f"#371 {LOG_ID} {booking.b_bookingID_Visual} - Getting Quotes again...")
    packed_status = (
        booking.api_booking_quote.packed_status if booking.api_booking_quote else None
    )

    packed_statuses = (
        [packed_status]
        if packed_status
        else [
            Booking_lines.ORIGINAL,
            Booking_lines.MANUAL_PACK,
            Booking_lines.AUTO_PACK,
            Booking_lines.SCANNED_PACK,
        ]
    )
    _, success, message, quotes, client = pricing_oper(
        body=None,
        booking_id=booking.pk,
        is_pricing_only=False,
        packed_statuses=packed_statuses,
    )
    logger.info(
        f"#372 {LOG_ID} - Pricing result: success: {success}, message: {message}, results cnt: {quotes}"
    )

    # Select best quotes(fastest, lowest)
    if quotes.exists() and quotes.count() > 0:
        if packed_status:
            quotes = quotes.filter(packed_status=packed_status)
        quotes = quotes.exclude(freight_provider__in=["Sendle", "Hunter"])

        best_quotes = select_best_options(pricings=quotes, client=booking.get_client())
        logger.info(f"#373 {LOG_ID} - Selected Best Pricings: {best_quotes}")

        if best_quotes:
            set_booking_quote(booking, best_quotes[0])
        else:
            set_booking_quote(booking, None)
