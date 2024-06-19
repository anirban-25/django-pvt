import logging
from datetime import timedelta

from api.models import DME_clients, Booking_lines, BOK_2_lines
from api.operations.pronto_xi.apis import (
    get_order,
    send_info_back_to_pronto,
    update_pronto_note,
)
from api.fp_apis.utils import get_etd_in_hour
from api.fp_apis.operations.surcharge.index import get_surcharges_total

logger = logging.getLogger(__name__)


def populate_bok(bok_1):
    LOG_ID = "[PPB]"  # PRONTO POPULATE BOK
    logger.info(f"@620 {LOG_ID} inital bok_1: {bok_1}")
    order, lines = get_order(bok_1["b_client_order_num"])

    # if order["b_client_order_num"] != bok_1["b_client_order_num"]:
    #     raise Exception({"success": False, "message": "Wrong Order is feched."})

    for prop in bok_1:
        order[prop] = bok_1[prop]

    logger.info(f"@629 {LOG_ID} Finished!\n result: {order}")
    return order, lines


def send_info_back(bok_1, quote):
    LOG_ID = "[PSIB]"  # PRONTO SEND INFO BACK
    logger.info(f"@630 {LOG_ID} bok_1 ID: {bok_1.pk}, quote ID: {quote.pk}")

    result = send_info_back_to_pronto(bok_1, quote)

    logger.info(f"@639 {LOG_ID} Finished!")
    return result


def update_note(quote, booking, lines=[], type="bok"):
    """
    quote: API_booking_quotes object
    booking: Bookings/BOK_1_headers object
    lines: Array of BookingLines/BOK_2_lines object
    type: `bok` or `booking`
    """
    return None

    LOG_ID = "[PUN]"  # PRONTO UPDATE NOTE
    logger.info(
        f"@630 {LOG_ID} orderNum: {booking.b_client_order_num}, quote ID: {quote.pk}"
    )

    if not booking.b_client_order_num:
        logger.info(f"@631 {LOG_ID} Wrong orderNum: {booking.b_client_order_num}")
        return True

    consignment_num = "---                    "
    total_cost = 0
    booking_status = "Picking"
    est_date = "---                    "

    # Client
    if type == "bok":
        client = DME_clients.objects.get(dme_account_num=booking.fk_client_id)
    else:
        client = DME_clients.objects.get(dme_account_num=booking.kf_client_id)

        # Status
        booking_status = booking.b_status.replace(" ", "_")

        # Consignment Number
        consignment_num = booking.v_FPBookingNumber or "---                    "

        # Estimated Date
        est_date = booking.puPickUpAvailFrom_Date + timedelta(
            hours=get_etd_in_hour(quote)
        )

    # Total Cost
    if lines:
        _lines = lines
    else:
        if type == "bok":
            _lines = BOK_2_lines.objects.filter(
                fk_header_id=booking.pk_header_id, is_deleted=False
            )
        else:
            _lines = Booking_lines.objects.filter(
                fk_booking_id=booking.pk_booking_id, is_deleted=False
            )

    surcharge_total = get_surcharges_total(quote)
    total_cost = "{0:.2f}".format(
        (quote.client_mu_1_minimum_values + surcharge_total)
        * (client.client_customer_mark_up + 1)
    )

    note = f"Consignment:{consignment_num}      TotalCost:{total_cost}                Status:{booking_status}                EstDate:{est_date}"
    result = update_pronto_note(booking.b_client_order_num, note)

    logger.info(f"@639 {LOG_ID} Finished!")
    return result
