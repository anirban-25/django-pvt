import json
import base64
import logging
import requests
from datetime import datetime

from django.conf import settings

from api.common import status_history, trace_error
from api.convertors.pdf import pdf_merge
from api.fp_apis.constants import S3_URL

logger = logging.getLogger(__name__)


def book(booking, _fp_name, payload, booker):
    from api.fps.team_global_express import (
        get_base_url as get_tge_base_url,
        get_headers as get_tge_headers,
        get_service_code as get_tge_service_code,
    )

    try:
        # Build request
        service_code = get_tge_service_code(booking)
        base_url = get_tge_base_url(booking)
        url = f"{base_url}/{service_code}/booking/bookconsignment"
        headers = get_tge_headers(booking)
        logger.info(f"### Payload ({_fp_name} book): {url}\n{payload}")

        # Send request and parse response
        response = requests.post(url, headers=headers, json=payload)
        res_content = response.content.decode("utf8").replace("'", '"')
        json_data = json.loads(res_content)
        s0 = json.dumps(json_data, indent=2, sort_keys=True)  # Just for visual
        logger.info(f"### Response: {s0}")

        if (
            booking.b_client_name.lower() == "biopak"
            and not booking.b_client_warehouse_code in ["BIO - HAZ", "BIO - RIC"]
        ):
            # Extract Labels
            res_items = json_data["items"]
            booking_lines = (
                booking.lines().filter(is_deleted=False).order_by("pk_lines_id")
            )
            sscc_lines = []
            for booking_line in booking_lines:
                if booking_line.sscc:
                    sscc_lines.append(booking_line)

            file_path = f"{S3_URL}/pdfs/{_fp_name}_au"
            booking_file_name = f"DME{booking.b_bookingID_Visual}.pdf"
            booking_label_urls = []
            for line in sscc_lines:
                ssccs = line.sscc.split(",")
                line_items = []
                line_file_name = f"{booking.pu_Address_State}_{str(booking.b_bookingID_Visual)}_{line.pk}.pdf"
                line_label_urls = []

                for res_item in res_items:
                    if res_item["sscc"] in ssccs:
                        line_items.append(res_item)
                for item in line_items:
                    file_name = f"{booking.pu_Address_State}_{str(booking.b_bookingID_Visual)}_{str(item['sscc'])}"
                    full_path = f"{file_path}/{file_name}.pdf"

                    with open(full_path, "wb") as f:
                        f.write(base64.b64decode(item["label"]))
                        f.close()

                    line_label_urls.append(full_path)

                pdf_merge(line_label_urls, f"{file_path}/{line_file_name}")
                booking_label_urls.append(f"{file_path}/{line_file_name}")

            pdf_merge(booking_label_urls, f"{file_path}/{booking_file_name}")
            booking.z_label_url = (
                f"{settings.WEB_SITE_URL}/label/{booking.b_client_booking_ref_num}/"
            )
            booking.save()

        # Update booking with BOOK result
        booking.v_FPBookingNumber = json_data["items"][0]["consignmentNumber"]
        booking.b_dateBookedDate = datetime.now()
        status_history.create(booking, "Booked", booker)
        booking.save()

        # BioPak: update with json
        if booking.b_client_name.lower() == "biopak":
            from api.fp_apis.update_by_json import update_biopak_with_booked_booking

            update_biopak_with_booked_booking(booking.pk, "book")

        message = f"Successfully booked({booking.v_FPBookingNumber})"
        return True, message
    except Exception as e:
        trace_error.print()
        error_msg = f"Error while BOOK via spojit: {str(e)}"
        return False, error_msg
