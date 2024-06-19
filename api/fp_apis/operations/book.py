import time as t
import json
import base64
import logging
import requests
from datetime import datetime

from django.conf import settings

from api.common import status_history, trace_error
from api.file_operations.directory import create_dir
from api.operations.email_senders import send_booking_status_email
from api.operations.api_booking_confirmation_lines import index as api_bcl
from api.models import Log, Dme_manifest_log

from api.fp_apis.pre_check import pre_check_book
from api.fp_apis.payload_builder import get_book_payload
from api.fp_apis.update_by_json import update_biopak_with_booked_booking
from api.fp_apis.operations.common import _set_error
from api.convertors.pdf import pdf_merge, zpl_to_pdf
from api.fp_apis.constants import (
    DME_LEVEL_API_URL,
    FP_SPOJIT,
    S3_URL,
    HEADER_FOR_NODE,
)
from api.warehouses.constants import SPOJIT_API_URL
from api.fp_apis.operations.books.built_in import book as built_in_book
from api.fp_apis.operations.books.team_global_express import book as tge_book
from api.fp_apis.operations.books.camerons import book as camerons_book
from api.fp_apis.operations.books.dxt import book as dxt_book


logger = logging.getLogger(__name__)


def book(fp_name, booking, booker):
    _fp_name = fp_name.lower()
    error_msg = pre_check_book(booking)

    if error_msg:
        return False, error_msg

    try:
        payload = get_book_payload(booking, _fp_name)
    except Exception as e:
        trace_error.print()
        logger.info(f"#401 - Error while build payload: {e}")
        error_msg = f"Error while build payload {str(e)}"
        return False, error_msg

    # TGE (via Spojit)
    if _fp_name == "team global express":
        success, message = tge_book(booking, _fp_name, payload, booker)
        return success, message
    # Camerons (via Spojit)
    elif _fp_name == "camerons":
        success, message = camerons_book(booking, _fp_name, payload, booker)
        return success, message
    # DXT (via Spojit)
    elif _fp_name == "dxt":
        success, message = dxt_book(booking, _fp_name, payload, booker)
        return success, message

    # BSD: when doesn't need any trucks from TNT
    if _fp_name == "tnt":
        if booking.b_client_warehouse_code == "BSD_MERRYLANDS":
            built_in_book(booking, booker)
            message = f"Successfully booked({booking.v_FPBookingNumber})"
            return True, message
        elif booking.z_manifest_url:
            manifest_name = booking.z_manifest_url.split("/")[1]
            manifest_logs = Dme_manifest_log.objects.filter(manifest_url=manifest_name)

            if manifest_logs and not manifest_logs.first().need_truck:
                built_in_book(booking, booker)
                message = f"Successfully booked({booking.v_FPBookingNumber})"
                return True, message

    logger.info(f"### Payload ({fp_name} book): {payload}")
    url = DME_LEVEL_API_URL + "/booking/bookconsignment"
    response = requests.post(url, params={}, json=payload, headers=HEADER_FOR_NODE)
    res_content = (
        response.content.decode("utf8").replace("'t", " not").replace("'", '"')
    )
    json_data = json.loads(res_content)

    try:
        s0 = json.dumps(
            json_data, indent=2, sort_keys=True, default=str
        )  # Just for visual
        # logger.info(f"### Response ({fp_name} book): {s0}")
        logger.info(f"### Response ({fp_name} book): {response.status_code}")
    except Exception as e:
        s0 = str(json_data)
        logger.error(f"[FP BOOK] error while dump json response. response: {json_data}")

    if (
        response.status_code == 500
        and _fp_name in ["startrack", "auspost"]
        and "An internal system error" in json_data[0]["message"]
    ):
        for i in range(4):
            t.sleep(180)
            logger.info(f"### Payload ({fp_name} book): {payload}")
            url = DME_LEVEL_API_URL + "/booking/bookconsignment"
            response = requests.post(
                url, params={}, json=payload, headers=HEADER_FOR_NODE
            )
            res_content = response.content.decode("utf8").replace("'", '"')
            json_data = json.loads(res_content)
            s0 = json.dumps(
                json_data, indent=2, sort_keys=True, default=str
            )  # Just for visual
            logger.info(f"### Response ({fp_name} book): {s0}")

            if response.status_code == 200:
                break

    if response.status_code == 200:
        try:
            request_payload = {}
            request_payload["apiUrl"] = url
            request_payload["accountCode"] = payload["spAccountDetails"]["accountCode"]
            request_payload["authKey"] = payload["spAccountDetails"]["accountKey"]
            request_payload["trackingId"] = json_data["consignmentNumber"]

            if booking.vx_freight_provider.lower() in ["startrack", "auspost"]:
                tracking_details = json_data["items"][0]["tracking_details"]
                booking.v_FPBookingNumber = tracking_details["consignment_id"]
            elif booking.vx_freight_provider.lower() == "hunter":
                booking.v_FPBookingNumber = json_data["consignmentNumber"]
                booking.jobNumber = json_data["jobNumber"]
                # booking.jobDate = json_data["jobDate"]
            elif booking.vx_freight_provider.lower() == "tnt":
                booking.v_FPBookingNumber = (
                    f"DME{str(booking.b_bookingID_Visual).zfill(9)}"
                )
            elif booking.vx_freight_provider.lower() == "sendle":
                booking.v_FPBookingNumber = json_data["v_FPBookingNumber"]
            elif booking.vx_freight_provider.lower() == "allied":
                booking.v_FPBookingNumber = json_data["consignmentNumber"]
                booking.jobNumber = json_data["jobNumber"]
            elif booking.vx_freight_provider.lower() == "direct freight":
                booking.v_FPBookingNumber = json_data["consignmentNumber"]
                booking.jobNumber = json_data["connote"]
                booking.jobDate = json_data["connoteDate"]

            booking.fk_fp_pickup_id = json_data["consignmentNumber"]
            booking.b_dateBookedDate = datetime.now()
            status_history.create(booking, "Booked", booker)
            booking.b_error_Capture = None
            booking.save()

            Log(
                request_payload=request_payload,
                request_status="SUCCESS",
                request_type=f"{fp_name.upper()} BOOK",
                response=res_content,
                fk_booking_id=booking.id,
            ).save()

            # Save Label for Hunter
            is_get_label = True  # Flag to decide if need to get label from response

            # JasonL | Plum
            if booking.kf_client_id in [
                "461162D2-90C7-BF4E-A905-000000000004",
                "1af6bcd2-6148-11eb-ae93-0242ac130002",
            ]:
                # JasonL never get label from FP
                is_get_label = False

            create_dir(f"{S3_URL}/pdfs/{_fp_name}_au")
            if _fp_name == "hunter" and is_get_label:
                json_label_data = json.loads(response.content)
                file_name = f"hunter_{str(booking.v_FPBookingNumber)}_{str(datetime.now().strftime('%Y%m%d_%H%M%S'))}.pdf"
                full_path = f"{S3_URL}/pdfs/{_fp_name}_au/{file_name}"

                with open(full_path, "wb") as f:
                    f.write(base64.b64decode(json_data["shippingLabel"]))
                    f.close()

                booking.z_label_url = f"{_fp_name}_au/{file_name}"
                booking.save()

                pod_file_name = f"hunter_POD_{booking.pu_Address_State}_{booking.b_client_sales_inv_num}_{str(datetime.now().strftime('%Y%m%d_%H%M%S'))}.pdf"
                full_path = f"{S3_URL}/pdfs/{_fp_name}_au/{pod_file_name}"

                with open(full_path, "wb") as f:
                    f.write(base64.b64decode(json_data["podImage"]))
                    f.close()

                booking.z_pod_url = f"{fp_name.lower()}_au/{pod_file_name}"
                booking.save()

                # Send email when GET_LABEL
                if booking.b_booking_Category == "Salvage Expense":
                    email_template_name = "Return Booking"
                elif booking.b_send_POD_eMail:  # POD Email
                    email_template_name = "POD"
                else:
                    email_template_name = "General Booking"

                send_booking_status_email(booking.pk, email_template_name, booker)

            # Save Label for Capital
            elif _fp_name == "capital" and is_get_label:
                json_label_data = json.loads(response.content)
                file_name = f"capital_{str(booking.v_FPBookingNumber)}_{str(datetime.now())}.pdf"
                full_path = f"{S3_URL}/pdfs/{_fp_name}_au/{file_name}"

                with open(full_path, "wb") as f:
                    f.write(base64.b64decode(json_label_data["Label"]))
                    f.close()
                    booking.z_label_url = f"{_fp_name}_au/{file_name}"
                    booking.save()

                    # Send email when GET_LABEL
                    email_template_name = "General Booking"

                    if booking.b_booking_Category == "Salvage Expense":
                        email_template_name = "Return Booking"

                    send_booking_status_email(booking.pk, email_template_name, booker)

            # Save Label for Startrack and AusPost
            elif _fp_name in ["startrack", "auspost"] and is_get_label:
                api_bcl.create(booking, json_data["items"])
            # Increase Conote Number and Manifest Count for DHL, kf_client_id of DHLPFM is hardcoded now
            elif _fp_name == "dhl" and is_get_label:
                if booking.kf_client_id == "461162D2-90C7-BF4E-A905-000000000002":
                    booking.v_FPBookingNumber = f"DME{booking.b_bookingID_Visual}"
                    booking.save()
                else:
                    booking.v_FPBookingNumber = str(json_data["orderNumber"])
                    booking.save()

            # BioPak: update with json
            if booking.b_client_name.lower() == "biopak":
                update_biopak_with_booked_booking(booking.pk, "book")

            message = f"Successfully booked({booking.v_FPBookingNumber})"
            return True, message
        except KeyError as e:
            trace_error.print()
            Log(
                request_payload=payload,
                request_status="ERROR",
                request_type=f"{fp_name.upper()} BOOK",
                response=res_content,
                fk_booking_id=booking.id,
            ).save()

            error_msg = s0
            _set_error(booking, error_msg)
            return False, error_msg
    elif response.status_code == 400:
        Log(
            request_payload=payload,
            request_status="ERROR",
            request_type=f"{fp_name.upper()} BOOK",
            response=res_content,
            fk_booking_id=booking.id,
        ).save()

        logger.error(f"[BOOK] - {str(res_content)}")

        if "errors" in json_data:
            if "errorMessage" in json_data["errors"]:
                error_msg = json_data["errors"]["errorMessage"]
            else:
                error_msg = json_data["errors"]
        elif "errorMessage" in json_data:  # Sendle, TNT Error
            error_msg = json_data["errorMessage"]
        elif "errorMessage" in json_data[0]:
            error_msg = json_data[0]["errorMessage"]
        else:
            error_msg = res_content
        _set_error(booking, error_msg)
        return False, error_msg
    elif response.status_code == 500:
        Log(
            request_payload=payload,
            request_status="ERROR",
            request_type=f"{fp_name.upper()} BOOK",
            response=res_content,
            fk_booking_id=booking.id,
        ).save()

        error_msg = "DME bot: Tried booking 3-4 times seems to be an unknown issue. Please review and contact support if needed"
        _set_error(booking, error_msg)
        return False, error_msg
