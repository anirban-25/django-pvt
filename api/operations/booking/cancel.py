import logging

from api.models import BOK_1_headers
from api.common import status_history

logger = logging.getLogger(__name__)


def cancel_book(booking, user):
    # Plum
    if booking.kf_client_id == "461162D2-90C7-BF4E-A905-000000000004":
        booking.b_client_order_num = f"{booking.b_client_order_num}_old"
        booking.b_client_sales_inv_num = f"{booking.b_client_sales_inv_num}_old"
        booking.save()

        boks = BOK_1_headers.objects.filter(pk_header_id=booking.pk_booking_id)
        if boks:
            bok = boks.first()
            bok.b_client_order_num = f"{booking.b_client_order_num}_old"
            bok.b_client_sales_inv_num = f"{booking.b_client_sales_inv_num}_old"
            bok.save()
    # Biopak
    elif booking.kf_client_id == "7EAA4B16-484B-3944-902E-BC936BFEF535":
        booking.b_clientReference_RA_Numbers  = f"{booking.b_clientReference_RA_Numbers }_old"
        booking.save()

        boks = BOK_1_headers.objects.filter(pk_header_id=booking.pk_booking_id)
        if boks:
            bok = boks.first()
            bok.b_000_1_b_clientreference_ra_numbers = f"{booking.b_clientReference_RA_Numbers}_old"
            bok.save()

    status_history.create(booking, "Closed", user.username)
