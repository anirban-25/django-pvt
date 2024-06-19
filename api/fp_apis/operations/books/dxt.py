import json
import logging
import requests
from datetime import datetime
from ast import literal_eval

from api.models import Bookings
from api.common import status_history, trace_error
from api.fp_apis.constants import FP_SPOJIT
from api.warehouses.constants import SPOJIT_API_URL, SPOJIT_TOKEN

logger = logging.getLogger(__name__)


def book(booking, _fp_name, payload, booker):
    LOG_ID = "[DXT BOOK]"

    try:
        from api.fp_apis.utils import gen_consignment_num

        booking.v_FPBookingNumber = gen_consignment_num(
            booking.vx_freight_provider, booking.b_bookingID_Visual
        )
        booking.save()

        headers = {"content-type": "application/json", "Authorization": SPOJIT_TOKEN}
        url = f"{SPOJIT_API_URL}/webhook/{FP_SPOJIT['dxt']}?booking_id={booking.pk}"
        logger.info(f"@9000 {LOG_ID} url: {url}\npayload: {payload}")
        response = requests.post(url, json=payload)
        res_content = response.content.decode("utf8").replace("'", '"')
        json_data = json.loads(res_content)
        logger.info(f"{LOG_ID} ### Response: {json_data}")

        message = f"Successfully booked({booking.v_FPBookingNumber})"
        return True, message
    except Exception as e:
        logger.info(f"@9009 {LOG_ID} error: {e}")
        trace_error.print()
        error_msg = f"Error while BOOK via spojit: {str(e)}"
        return False, error_msg


def book_webhook(request):
    LOG_ID = "[DXT BOOK WEBHOOK]"

    body = literal_eval(request.body.decode("utf8"))
    booking_id = body["booking_id"]
    logger.info(f"{LOG_ID}, {booking_id}")

    try:
        from api.common import status_history

        booking = Bookings.objects.get(pk=booking_id)
        booking.b_status = "Booked"
        booking.b_dateBookedDate = datetime.now()
        booking.b_error_Capture = None
        status_history.create(booking, "Booked", "DME_API")
        booking.save()
    except Exception as e:
        logger.info(f"{LOG_ID}, Booking does not exist with pk({booking_id})")
        return False, "success"

    return True, "success"
