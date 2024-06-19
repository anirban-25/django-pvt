import logging

from api.models import Api_booking_confirmation_lines

logger = logging.getLogger(__name__)


def create(booking, items):
    LOG_ID = "[BCL CREATE]"

    if booking.vx_freight_provider and booking.vx_freight_provider.lower() in [
        "startrack",
        "auspost",
    ]:
        for item in items:
            book_con = Api_booking_confirmation_lines.objects.get_or_create(
                fk_booking_id=booking.pk_booking_id,
                api_item_id=item["item_id"],
            )
    else:
        book_con = Api_booking_confirmation_lines.objects.get_or_create(
            fk_booking_id=booking.pk_booking_id,
            label_code=items[0]["label_code"],
        )
