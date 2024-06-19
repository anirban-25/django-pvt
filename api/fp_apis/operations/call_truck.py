import json
import logging
import requests
from datetime import datetime

from api.models import (
    Bookings,
    Booking_lines,
    API_booking_quotes,
    Client_FP,
    FP_Service_ETDs,
    Surcharge,
    DME_clients,
    Fp_freight_providers,
)
from api.fp_apis.payload_builder import get_call_truck_payload
from api.fp_apis.constants import (
    FP_CREDENTIALS,
    S3_URL,
    DME_LEVEL_API_URL,
    HEADER_FOR_NODE,
)

logger = logging.getLogger(__name__)


def call_truck(bookings, fp_name, clientname):
    try:
        payload = get_call_truck_payload(bookings, fp_name, clientname)
        headers = {
            "Accept": "application/pdf",
            "Content-Type": "application/json",
            **HEADER_FOR_NODE,
        }
        logger.info(f"### Payload ({fp_name.upper()} Call Truck): {payload}")
        url = DME_LEVEL_API_URL + "/order/create"
        response = requests.post(url, json=payload, headers=headers)
        res_content = response.content
        json_data = json.loads(res_content)
        # Just for visual
        s0 = json.dumps(json_data, indent=2, sort_keys=True, default=str)
        logger.info(f"### Response ({fp_name} tracking): {s0}")

        if json_data["ResponseCode"] == "200":
            for booking in bookings:
                booking.vx_fp_order_id = json_data["BookingReferenceNumber"]
                booking.save()
            return True
        else:
            logger.info(f"Call Truck get failed: {json_data['ResponseMessage']}")
            return False
    except IndexError as e:
        trace_error.print()
        return False
