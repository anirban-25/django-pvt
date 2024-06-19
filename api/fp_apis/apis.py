import time as t
import json
import requests
import datetime
import base64
import os
import logging
from ast import literal_eval

from rest_framework.decorators import (
    api_view,
    authentication_classes,
    permission_classes,
)
from rest_framework.authentication import BasicAuthentication, SessionAuthentication
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework import status
from django.http import JsonResponse
from django.conf import settings

from api.clients.bsd.operations import send_email_booked
from api.fps.team_global_express import get_tge_ins_order_url, get_tge_ins_summary_url
from api.models import *
from api.serializers import ApiBookingQuotesSerializer, BookingSerializer
from api.common import status_history, download_external, trace_error
from api.common.time import convert_to_UTC_tz
from api.file_operations.directory import create_dir
from api.file_operations.downloads import download_from_url
from api.utils import get_eta_pu_by, get_eta_de_by
from api.operations.email_senders import (
    send_booking_status_email,
    send_email_manual_book,
)
from api.operations.labels.index import build_label

from api.fp_apis.payload_builder import *
from api.fp_apis.response_parser import *
from api.fp_apis.pre_check import *
from api.fp_apis.operations.common import _set_error
from api.fp_apis.operations.tracking import (
    update_booking_with_tracking_result,
    populate_fp_status_history,
    populate_items_status,
)
from api.fp_apis.operations.book import book as book_oper
from api.fp_apis.operations.pricing import pricing as pricing_oper
from api.fp_apis.utils import auto_select_pricing
from api.fp_apis.constants import (
    FP_CREDENTIALS,
    S3_URL,
    DME_LEVEL_API_URL,
    HEADER_FOR_NODE,
)
from api.fp_apis.utils import gen_consignment_num
from api.fp_apis.constants import SPECIAL_FPS
from api.helpers.string import *
from api.operations.email_senders import send_email_to_admins

logger = logging.getLogger(__name__)


@api_view(["POST"])
@authentication_classes((SessionAuthentication, BasicAuthentication))
@permission_classes((AllowAny,))
def bulk_tracking(request, fp_name):
    # For Startrack, Direct Freight

    body = literal_eval(request.body.decode("utf8"))
    booking_ids = body["booking_ids"].split(",")

    try:
        bookings = Bookings.objects.filter(pk__in=booking_ids)
        payload = get_tracking_payload(bookings, fp_name, True)

        logger.info(f"### Payload ({fp_name} tracking): {payload}")
        url = DME_LEVEL_API_URL + "/tracking/trackconsignment"
        response = requests.post(url, params={}, json=payload, headers=HEADER_FOR_NODE)
        res_content = response.content.decode("utf8").replace("'", '"')
        json_data = json.loads(res_content)
        # s0 = json.dumps(json_data, indent=2, sort_keys=True)  # Just for visual
        # # disabled on 2021-07-05
        # logger.info(f"### Response ({fp_name} tracking): {s0}")

        consignmentTrackDetails = json_data["consignmentTrackDetails"]
        results = []

        for trackDetail in consignmentTrackDetails:
            _booking = None
            result = {"v_FPBookingNumber": trackDetail["consignmentNumber"]}

            for booking in bookings:
                if trackDetail["consignmentNumber"] == booking.v_FPBookingNumber:
                    _booking = booking

            if not _booking:
                pass

            consignmentStatuses = trackDetail["consignmentStatuses"]
            items = trackDetail["items"]
            populate_items_status(_booking, items)
            has_new = populate_fp_status_history(_booking, consignmentStatuses)
            result["b_booking_visualID"] = _booking.b_bookingID_Visual
            result["v_FPBookingNumber"] = _booking.v_FPBookingNumber
            result["has_new_status"] = has_new

            if has_new:
                update_booking_with_tracking_result(
                    request, _booking, fp_name, consignmentStatuses
                )
                _booking.b_error_Capture = None
                _booking.save()
                result["b_status"] = _booking.b_status
                Log(
                    request_payload=payload,
                    request_status="SUCCESS",
                    request_type=f"{fp_name.upper()} BULK TRACKING",
                    response=res_content,
                    fk_booking_id=booking_ids[0],
                ).save()

            results.append(result)

        return JsonResponse(
            {
                "message": f"Successfully updated {len(booking_ids)} bookings status!",
                "result": results,
            },
            status=status.HTTP_200_OK,
        )
    except Exception as e:
        trace_error.print()
        logger.error(f"#512 ERROR: {e}")
        return JsonResponse(
            {"message": "Bulk Tracking failed"}, status=status.HTTP_400_BAD_REQUEST
        )


@api_view(["POST"])
@authentication_classes((SessionAuthentication, BasicAuthentication))
@permission_classes((AllowAny,))
def tracking(request, fp_name):
    body = literal_eval(request.body.decode("utf8"))
    booking_id = body["booking_id"]

    try:
        booking = Bookings.objects.get(id=booking_id)
        headers = HEADER_FOR_NODE
        payload = get_tracking_payload(booking, fp_name, False)
        url = DME_LEVEL_API_URL + "/tracking/trackconsignment"

        # TGE (via Spojit)
        if fp_name.lower() == "team global express":
            from api.fps.team_global_express import (
                get_base_url as get_tge_base_url,
                get_headers as get_tge_headers,
                get_service_code as get_tge_service_code,
            )

            service_code = get_tge_service_code(booking)
            base_url = get_tge_base_url(booking)
            url = f"{base_url}/{service_code}/tracking"
            headers = get_tge_headers(booking)

        logger.info(f"### Url: {url}\n, Payload ({fp_name} tracking): {payload}")
        response = requests.post(url, params={}, json=payload, headers=headers)

        if fp_name.lower() in ["tnt"]:
            res_content = response.content.decode("utf8")
        else:
            res_content = response.content.decode("utf8").replace("'", '"')

        json_data = json.loads(res_content)
        # disabled on 2021-07-05
        # s0 = json.dumps(json_data, indent=2, sort_keys=True)  # Just for visual
        # logger.info(f"### Response ({fp_name} tracking): {s0}")

        try:
            # TGE tracking handler (via Spojit)
            if fp_name.lower() == "team global express":
                _consignmentStatuses = json_data["events"]
                consignmentStatuses = []

                for _status in _consignmentStatuses:
                    if _status["itemReference"]:
                        consignmentStatuses.append(_status)
            else:
                consignmentTrackDetail = json_data["consignmentTrackDetails"][0]
                consignmentStatuses = consignmentTrackDetail["consignmentStatuses"]

            has_new = populate_fp_status_history(booking, consignmentStatuses)

            # Allied POD
            if booking.vx_freight_provider.lower() == "allied":
                if consignmentTrackDetail["pods"]:
                    podData = consignmentTrackDetail["pods"][0]["podData"]

                    _fp_name = fp_name.lower()
                    pod_file_name = f"allied_POD_{booking.pu_Address_State}_{toAlphaNumeric(booking.b_client_sales_inv_num)}_{str(datetime.now().strftime('%Y%m%d_%H%M%S'))}.png"
                    full_path = f"{S3_URL}/imgs/{_fp_name}_au/{pod_file_name}"

                    f = open(full_path, "wb")
                    f.write(base64.b64decode(podData))
                    f.close()

                    booking.z_pod_url = f"{fp_name.lower()}_au/{pod_file_name}"

                signatures = consignmentTrackDetail["signatures"]
                if signatures:
                    if "signImg" in signatures[0]:
                        posData = signatures[0]["signImg"]
                        _fp_name = fp_name.lower()
                        pos_file_name = f"allied_POS_{booking.pu_Address_State}_{toAlphaNumeric(booking.b_client_sales_inv_num)}_{str(datetime.now().strftime('%Y%m%d_%H%M%S'))}.png"
                        full_path = f"{S3_URL}/imgs/{_fp_name}_au/{pos_file_name}"

                        f = open(full_path, "wb")
                        f.write(base64.b64decode(posData))
                        f.close()

                        booking.b_del_to_signed_name = signatures[0]["signerName"]
                        booking.z_pod_signed_url = (
                            f"{fp_name.lower()}_au/{pos_file_name}"
                        )

                if "scheduledDeliveryDate" in consignmentTrackDetail:
                    scheduledDeliveryDate = consignmentTrackDetail[
                        "scheduledDeliveryDate"
                    ]
                    event_at = datetime.strptime(
                        scheduledDeliveryDate[:19], "%Y-%m-%dT%H:%M:%S"
                    )
                    event_at = str(convert_to_UTC_tz(event_at))
                    booking.s_06_Latest_Delivery_Date_TimeSet = event_at

            if has_new:
                update_booking_with_tracking_result(
                    request, booking, fp_name, consignmentStatuses
                )

                if fp_name.lower() == "team global express":
                    populate_items_status(booking, consignmentStatuses)

                booking.b_error_Capture = None
                Log(
                    request_payload=payload,
                    request_status="SUCCESS",
                    request_type=f"{fp_name.upper()} TRACKING",
                    response=res_content,
                    fk_booking_id=booking.id,
                ).save()

            booking.save()
            return JsonResponse(
                {
                    "message": f"DME status: {booking.b_status}, FP status: {booking.b_status_API}",
                    "b_status": booking.b_status,
                    "b_status_API": booking.b_status_API,
                },
                status=status.HTTP_200_OK,
            )
        except KeyError:
            if "errorMessage" in json_data:
                error_msg = json_data["errorMessage"]
                _set_error(booking, error_msg)
                logger.info(f"#510 ERROR: {error_msg}")
            else:
                error_msg = "Failed Tracking"

            trace_error.print()
            return JsonResponse(
                {"error": error_msg}, status=status.HTTP_400_BAD_REQUEST
            )
    except Bookings.DoesNotExist:
        trace_error.print()
        logger.error(f"#511 ERROR: {e}")
        return JsonResponse(
            {"message": "Booking not found"}, status=status.HTTP_400_BAD_REQUEST
        )
    except Exception as e:
        trace_error.print()
        logger.error(f"#512 ERROR: {e}")
        return JsonResponse(
            {"message": "Tracking failed"}, status=status.HTTP_400_BAD_REQUEST
        )


@api_view(["POST"])
@permission_classes((AllowAny,))
def book_webhook(request, fp_name):
    if fp_name == "camerons":
        from api.fp_apis.operations.books.camerons import (
            book_webhook as book_webhook_camerons,
        )

        success, message = book_webhook_camerons(request)
        return JsonResponse(
            {"message": message},
            status=status.HTTP_200_OK,
        )


@api_view(["POST"])
@authentication_classes((SessionAuthentication, BasicAuthentication))
@permission_classes((AllowAny,))
def book(request, fp_name):
    LOG_ID = "[FP BOOK]"

    try:
        username = request.user.username
        body = literal_eval(request.body.decode("utf8"))
        booking_id = body["booking_id"]
    except SyntaxError as e:
        trace_error.print()
        logger.error(f"#514 BOOK error: {error_msg}")
        return JsonResponse(
            {"message": f"SyntaxError: {e}"}, status=status.HTTP_400_BAD_REQUEST
        )

    try:
        booking = Bookings.objects.get(id=booking_id)

        if fp_name.lower() not in FP_CREDENTIALS:
            booking.b_status = "Booked"
            booking.b_dateBookedDate = datetime.now()
            booking.b_error_Capture = None
            booking.v_FPBookingNumber = gen_consignment_num(
                fp_name, booking.b_bookingID_Visual, booking.kf_client_id, booking
            )
            status_history.create(booking, "Booked", username)
            booking.save()

            if booking.b_client_name == "Bathroom Sales Direct":
                booking_lines = Booking_lines.objects.filter(
                    fk_booking_id=booking.pk_booking_id, is_deleted=False, packed_status="scanned"
                )
                send_email_booked(booking, booking_lines)

            if booking.vx_freight_provider not in SPECIAL_FPS:
                send_email_manual_book(booking)

            res_json = {
                "success": True,
                "message": "Booked Successfully",
                "booking": BookingSerializer(booking).data,
            }
            return JsonResponse(res_json)
        else:
            success, message = book_oper(fp_name, booking, username)

            # # TEST Usage #
            # booking.v_FPBookingNumber = "TEST"
            # booking.b_dateBookedDate = datetime.now()
            # status_history.create(booking, "Booked", username)
            # booking.save()
            # message = f"Successfully booked({booking.v_FPBookingNumber})"
            # # TEST Usage End #

            res_json = {
                "success": success,
                "message": message,
                "booking": BookingSerializer(booking).data,
            }

        if success:
            return JsonResponse(res_json)
        else:
            logger.info(
                f"{LOG_ID} Failed. BookingId: {booking.b_bookingID_Visual} Error: {message}"
            )
            return JsonResponse(res_json, status=status.HTTP_400_BAD_REQUEST)
    except Exception as e:
        trace_error.print()
        error_msg = str(e)
        logger.error(f"#513 BOOK error: {error_msg}")
        _set_error(booking, error_msg)
        return JsonResponse({"message": error_msg}, status=status.HTTP_400_BAD_REQUEST)


@api_view(["POST"])
@authentication_classes((SessionAuthentication, BasicAuthentication))
@permission_classes((AllowAny,))
def rebook(request, fp_name):
    try:
        body = literal_eval(request.body.decode("utf8"))
        booking_id = body["booking_id"]
        _fp_name = fp_name.lower()

        try:
            booking = Bookings.objects.get(id=booking_id)

            error_msg = pre_check_rebook(booking)

            if error_msg:
                return JsonResponse(
                    {"message": f"#700 Error: {error_msg}"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            try:
                payload = get_book_payload(booking, _fp_name)
            except Exception as e:
                trace_error.print()
                logger.info(f"#401 - Error while build payload: {e}")
                return JsonResponse(
                    {"message": f"Error while build payload {str(e)}"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            logger.info(f"### Payload ({fp_name} rebook): {payload}")
            url = DME_LEVEL_API_URL + "/booking/rebookconsignment"
            response = requests.post(
                url, params={}, json=payload, headers=HEADER_FOR_NODE
            )
            res_content = response.content.decode("utf8").replace("'", '"')
            json_data = json.loads(res_content)
            s0 = json.dumps(
                json_data, indent=2, sort_keys=True, default=str
            )  # Just for visual
            # logger.info(f"### Response ({fp_name} rebook): {s0}")
            logger.info(f"### Response ({fp_name} rebook): {response.status_code}")

            if response.status_code == 200:
                try:
                    request_payload = {
                        "apiUrl": "",
                        "accountCode": "",
                        "authKey": "",
                        "trackingId": "",
                    }
                    request_payload["apiUrl"] = url
                    request_payload["accountCode"] = payload["spAccountDetails"][
                        "accountCode"
                    ]
                    request_payload["authKey"] = payload["spAccountDetails"][
                        "accountKey"
                    ]
                    request_payload["trackingId"] = json_data["consignmentNumber"]

                    if booking.vx_freight_provider.lower() == "tnt":
                        booking.v_FPBookingNumber = (
                            f"DME{str(booking.b_bookingID_Visual).zfill(9)}"
                        )

                    old_fk_fp_pickup_id = booking.fk_fp_pickup_id
                    booking.fk_fp_pickup_id = json_data["consignmentNumber"]
                    booking.b_dateBookedDate = datetime.now()
                    status_history.create(
                        booking,
                        "Pickup Rebooked(Last pickup Id was "
                        + str(old_fk_fp_pickup_id)
                        + ")",
                        request.user.username,
                    )
                    status_history.create(booking, "Pickup Rebooked", "jason_l")
                    booking.s_05_Latest_Pick_Up_Date_TimeSet = get_eta_pu_by(booking)
                    booking.s_06_Latest_Delivery_Date_TimeSet = get_eta_de_by(
                        booking, booking.api_booking_quote
                    )
                    booking.b_error_Capture = None
                    booking.save()

                    Log(
                        request_payload=request_payload,
                        request_status="SUCCESS",
                        request_type=f"{fp_name.upper()} REBOOK",
                        response=res_content,
                        fk_booking_id=booking.id,
                    ).save()

                    return JsonResponse(
                        {"message": f"Successfully booked({booking.v_FPBookingNumber})"}
                    )
                except KeyError as e:
                    trace_error.print()
                    Log(
                        request_payload=payload,
                        request_status="ERROR",
                        request_type=f"{fp_name.upper()} REBOOK",
                        response=res_content,
                        fk_booking_id=booking.id,
                    ).save()

                    error_msg = s0
                    _set_error(booking, error_msg)
                    return JsonResponse(
                        {"message": error_msg}, status=status.HTTP_400_BAD_REQUEST
                    )
            elif response.status_code == 400:
                Log(
                    request_payload=payload,
                    request_status="ERROR",
                    request_type=f"{fp_name.upper()} REBOOK",
                    response=res_content,
                    fk_booking_id=booking.id,
                ).save()

                if "errors" in json_data:
                    error_msg = json_data["errors"]
                elif "errorMessage" in json_data:  # TNT Error
                    error_msg = json_data["errorMessage"]
                elif "errorMessage" in json_data[0]:  # Hunter Error
                    error_msg = json_data[0]["errorMessage"]
                else:
                    error_msg = s0
                _set_error(booking, error_msg)
                return JsonResponse(
                    {"message": error_msg}, status=status.HTTP_400_BAD_REQUEST
                )
            elif response.status_code == 500:
                Log(
                    request_payload=payload,
                    request_status="ERROR",
                    request_type=f"{fp_name.upper()} REBOOK",
                    response=res_content,
                    fk_booking_id=booking.id,
                ).save()

                error_msg = "DME bot: Tried rebooking 3-4 times seems to be an unknown issue. Please review and contact support if needed"
                _set_error(booking, error_msg)
                return JsonResponse(
                    {"message": error_msg}, status=status.HTTP_400_BAD_REQUEST
                )
        except Exception as e:
            trace_error.print()
            error_msg = str(e)
            _set_error(booking, error_msg)
            return JsonResponse(
                {"message": error_msg}, status=status.HTTP_400_BAD_REQUEST
            )
    except SyntaxError as e:
        trace_error.print()
        return JsonResponse(
            {"message": f"SyntaxError: {e}"}, status=status.HTTP_400_BAD_REQUEST
        )


@api_view(["POST"])
@authentication_classes((SessionAuthentication, BasicAuthentication))
@permission_classes((AllowAny,))
def edit_book(request, fp_name):
    try:
        body = literal_eval(request.body.decode("utf8"))
        booking_id = body["booking_id"]
        _fp_name = fp_name.lower()

        try:
            booking = Bookings.objects.get(id=booking_id)

            if booking.pu_Address_State is None or not booking.pu_Address_State:
                error_msg = "State for pickup postal address is required."
                _set_error(booking, error_msg)
                return JsonResponse({"message": error_msg})
            elif booking.pu_Address_Suburb is None or not booking.pu_Address_Suburb:
                error_msg = "Suburb name for pickup postal address is required."
                _set_error(booking, error_msg)
                return booking_id({"message": error_msg})
            # elif booking.z_manifest_url is not None or booking.z_manifest_url != "":
            #     error_msg = "This booking is manifested."
            #     _set_error(booking, error_msg)
            #     return booking_id({"message": error_msg})

            payload = get_book_payload(booking, fp_name)

            logger.info(f"### Payload ({fp_name} edit book): {payload}")
            url = DME_LEVEL_API_URL + "/booking/bookconsignment"
            response = requests.post(
                url, params={}, json=payload, headers=HEADER_FOR_NODE
            )
            res_content = response.content.decode("utf8").replace("'", '"')
            json_data = json.loads(res_content)
            s0 = json.dumps(
                json_data, indent=2, sort_keys=True, default=str
            )  # Just for visual
            logger.info(f"### Response ({fp_name} edit book): {s0}")

            try:
                request_payload = {
                    "apiUrl": "",
                    "accountCode": "",
                    "authKey": "",
                    "trackingId": "",
                }
                request_payload["apiUrl"] = url
                request_payload["accountCode"] = payload["spAccountDetails"][
                    "accountCode"
                ]
                request_payload["authKey"] = payload["spAccountDetails"]["accountKey"]
                request_payload["trackingId"] = json_data["consignmentNumber"]
                request_type = f"{fp_name.upper()} EDIT BOOK"
                request_status = "SUCCESS"

                if booking.vx_freight_provider.lower() == "startrack":
                    booking.v_FPBookingNumber = json_data["items"][0][
                        "tracking_details"
                    ]["consignment_id"]
                elif booking.vx_freight_provider.lower() == "hunter":
                    booking.v_FPBookingNumber = json_data["consignmentNumber"]
                    booking.jobNumber = json_data["jobNumber"]
                elif booking.vx_freight_provider.lower() == "tnt":
                    booking.v_FPBookingNumber = (
                        f"DME{str(booking.b_bookingID_Visual).zfill(9)}"
                    )
                elif booking.vx_freight_provider.lower() == "sendle":
                    booking.v_FPBookingNumber = json_data["v_FPBookingNumber"]

                booking.fk_fp_pickup_id = json_data["consignmentNumber"]
                booking.b_dateBookedDate = datetime.now()
                status_history.create(booking, "Booked", "DME_API")
                booking.b_error_Capture = None
                booking.save()

                Log(
                    request_payload=request_payload,
                    request_status=request_status,
                    request_type=request_type,
                    response=res_content,
                    fk_booking_id=booking.id,
                ).save()

                create_dir_if_not_exist(f"./static/pdfs/{fp_name.lower()}_au")
                if booking.vx_freight_provider.lower() == "hunter":
                    json_label_data = json.loads(response.content)
                    file_name = f"hunter_{str(booking.v_FPBookingNumber)}_{str(datetime.now().strftime('%Y%m%d_%H%M%S'))}.pdf"
                    full_path = f"{S3_URL}/pdfs/{_fp_name}_au/{file_name}"

                    with open(full_path, "wb") as f:
                        f.write(base64.b64decode(json_label_data["shippingLabel"]))
                        f.close()
                        booking.z_label_url = f"hunter_au/{file_name}"
                        booking.save()

                    pod_file_name = f"hunter_POD_{booking.pu_Address_State}_{toAlphaNumeric(booking.b_client_sales_inv_num)}_{str(datetime.now().strftime('%Y%m%d_%H%M%S'))}.pdf"
                    full_path = f"{S3_URL}/imgs/{_fp_name}_au/{pod_file_name}"

                    f = open(full_path, "wb")
                    f.write(base64.b64decode(json_label_data["podImage"]))
                    f.close()

                    booking.z_pod_url = f"{fp_name.lower()}_au/{pod_file_name}"
                    booking.save()

                    # Send email when GET_LABEL
                    email_template_name = "General Booking"

                    if booking.b_booking_Category == "Salvage Expense":
                        email_template_name = "Return Booking"

                    email_module.send_booking_email_using_template(
                        booking.pk, email_template_name, request.user.username
                    )
                    # POD Email
                    if booking.b_send_POD_eMail:
                        email_template_name = "POD"
                        email_module.send_booking_email_using_template(
                            booking.pk, email_template_name, request.user.username
                        )
                else:
                    Api_booking_confirmation_lines.objects.filter(
                        fk_booking_id=booking.pk_booking_id
                    ).delete()

                    for item in json_data["items"]:
                        book_con = Api_booking_confirmation_lines(
                            fk_booking_id=booking.pk_booking_id,
                            api_item_id=item["item_id"],
                        ).save()
                return JsonResponse(
                    {"message": f"Successfully edit book({booking.v_FPBookingNumber})"}
                )
            except KeyError as e:
                trace_error.print()
                Log(
                    request_payload=payload,
                    request_status="ERROR",
                    request_type=f"{fp_name.upper()} EDIT BOOK",
                    response=res_content,
                    fk_booking_id=booking.id,
                ).save()

                error_msg = s0
                _set_error(booking, error_msg)
                return JsonResponse(
                    {"message": error_msg}, status=status.HTTP_400_BAD_REQUEST
                )
        except IndexError as e:
            trace_error.print()
            return JsonResponse(
                {"message": f"IndexError {e}"}, status=status.HTTP_400_BAD_REQUEST
            )
    except SyntaxError as e:
        trace_error.print()
        return JsonResponse(
            {"message": f"SyntaxError {e}"}, status=status.HTTP_400_BAD_REQUEST
        )


@api_view(["POST"])
@authentication_classes((SessionAuthentication, BasicAuthentication))
@permission_classes((AllowAny,))
def cancel_book(request, fp_name):
    try:
        body = literal_eval(request.body.decode("utf8"))
        booking_id = body["booking_id"]
        booking = Bookings.objects.get(id=booking_id)

        if booking.b_status != "Closed":
            if booking.b_dateBookedDate is not None:
                payload = get_cancel_book_payload(booking, fp_name)

                logger.info(f"### Payload ({fp_name} cancel book): {payload}")
                url = DME_LEVEL_API_URL + "/booking/cancelconsignment"
                response = requests.delete(
                    url, params={}, json=payload, headers=HEADER_FOR_NODE
                )
                res_content = response.content.decode("utf8").replace("'", '"')
                json_data = json.loads(res_content)
                s0 = json.dumps(
                    json_data, indent=2, sort_keys=True, default=str
                )  # Just for visual
                logger.info(f"### Response ({fp_name} cancel book): {s0}")

                try:
                    if response.status_code == 200:
                        status_history.create(booking, "Closed", request.user.username)
                        booking.b_dateBookedDate = None
                        booking.b_booking_Notes = (
                            "This booking has been closed vis Startrack API"
                        )
                        booking.b_error_Capture = None
                        booking.save()

                        Log(
                            request_payload=payload,
                            request_status="SUCCESS",
                            request_type=f"{fp_name.upper()} CANCEL BOOK",
                            response=res_content,
                            fk_booking_id=booking.id,
                        ).save()

                        return JsonResponse(
                            {"message": "Successfully cancelled book"},
                            status=status.HTTP_200_OK,
                        )
                    else:
                        if "errorMessage" in json_data:
                            error_msg = json_data["errorMessage"]
                            _set_error(booking, error_msg)
                            return JsonResponse(
                                {"message": error_msg},
                                status=status.HTTP_400_BAD_REQUEST,
                            )

                        error_msg = json_data
                        _set_error(booking, error_msg)
                        return JsonResponse(
                            {"message": "Failed to cancel book"},
                            status=status.HTTP_400_BAD_REQUEST,
                        )
                except KeyError as e:
                    trace_error.print()
                    Log(
                        request_payload=payload,
                        request_status="ERROR",
                        request_type=f"{fp_name.upper()} CANCEL BOOK",
                        response=res_content,
                        fk_booking_id=booking.id,
                    ).save()

                    error_msg = s0
                    _set_error(booking, error_msg)
                    return JsonResponse(
                        {"message": error_msg}, status=status.HTTP_400_BAD_REQUEST
                    )
            else:
                error_msg = "Booking is not booked yet"
                _set_error(booking, error_msg)
                return JsonResponse(
                    {"message": error_msg}, status=status.HTTP_400_BAD_REQUEST
                )
        else:
            return JsonResponse(
                {"message": "Booking is already cancelled"},
                status=status.HTTP_400_BAD_REQUEST,
            )
    except IndexError as e:
        trace_error.print()
        return JsonResponse(
            {"message": f"IndexError: {e}"}, status=status.HTTP_400_BAD_REQUEST
        )
    except SyntaxError as e:
        trace_error.print()
        return JsonResponse(
            {"message": f"SyntaxError: {e}"}, status=status.HTTP_400_BAD_REQUEST
        )


@api_view(["POST"])
@authentication_classes((SessionAuthentication, BasicAuthentication))
@permission_classes((AllowAny,))
def get_label(request, fp_name):
    try:
        body = literal_eval(request.body.decode("utf8"))
        booking_id = body["booking_id"]
        booking = Bookings.objects.get(id=booking_id)
        _fp_name = fp_name.lower()

        if (
            booking.kf_client_id
            in [
                "1af6bcd2-6148-11eb-ae93-0242ac130002",
                "9e72da0f-77c3-4355-a5ce-70611ffd0bc8",
            ]
            and booking.vx_freight_provider.lower() != "tnt"
        ):  # JasonL & BSD:
            error_msg = "JasonL order label should be built by built-in module."
            return JsonResponse(
                {"message": error_msg}, status=status.HTTP_400_BAD_REQUEST
            )

        booking, error_msg = pre_check_label(booking)
        if error_msg:
            return JsonResponse(
                {"message": error_msg}, status=status.HTTP_400_BAD_REQUEST
            )

        payload = {}
        if _fp_name in ["startrack", "auspost"]:
            try:
                payload = get_create_label_payload(booking, _fp_name)

                logger.info(
                    f"### Payload ({fp_name} create_label): {json.dumps(payload, indent=2, sort_keys=True, default=str)}"
                )
                url = DME_LEVEL_API_URL + "/labelling/createlabel"
                response = requests.post(
                    url, params={}, json=payload, headers=HEADER_FOR_NODE
                )
                res_content = response.content.decode("utf8").replace("'", '"')
                json_data = json.loads(res_content)
                # # Deactivated on 2021-11-26
                # s0 = json.dumps(
                #     json_data, indent=2, sort_keys=True, default=str
                # )  # Just for visual
                # logger.info(f"### Response ({fp_name} create_label): {s0}")

                payload["consignmentNumber"] = json_data[0]["request_id"]
            except Exception as e:
                trace_error.print()
                request_type = f"{fp_name.upper()} CREATE LABEL"
                request_status = "ERROR"
                oneLog = Log(
                    request_payload=payload,
                    request_status=request_status,
                    request_type=request_type,
                    response=res_content,
                    fk_booking_id=booking.id,
                ).save()

                _set_error(booking, "Label operation got failed")
                return JsonResponse(
                    {"message": error_msg}, status=status.HTTP_400_BAD_REQUEST
                )
        elif _fp_name in ["tnt", "sendle"]:
            payload = get_getlabel_payload(booking, fp_name)

        try:
            logger.info(f"### Payload ({fp_name} get_label): {payload}")
            url = DME_LEVEL_API_URL + "/labelling/getlabel"
            json_data = None
            z_label_url = None

            while (
                json_data is None
                or (
                    json_data is not None
                    and _fp_name in ["startrack", "auspost"]
                    and json_data["labels"][0]["status"] == "PENDING"
                )
                or (
                    json_data is not None
                    and _fp_name == "tnt"
                    and json_data["anyType"]["Status"] != "SUCCESS"
                )
            ):
                t.sleep(5)  # Delay to wait label is created
                response = requests.post(
                    url, params={}, json=payload, headers=HEADER_FOR_NODE
                )
                res_content = response.content.decode("utf8").replace("'", '"')

                if _fp_name in ["sendle"]:
                    res_content = response.content.decode("utf8")

                json_data = json.loads(res_content)
                s0 = json.dumps(
                    json_data, indent=2, sort_keys=True, default=str
                )  # Just for visual
                logger.info(f"### Response ({fp_name} get_label): {s0}")

            if _fp_name in ["startrack", "auspost"]:
                z_label_url = download_external.pdf(
                    json_data["labels"][0]["url"], booking
                )
            elif _fp_name in ["tnt", "sendle"]:
                try:
                    if _fp_name == "tnt":
                        label_data = base64.b64decode(json_data["anyType"]["LabelPDF"])
                        file_name = f"{fp_name}_label_{booking.pu_Address_State}_{toAlphaNumeric(booking.b_client_sales_inv_num)}_{str(datetime.now())}.pdf"
                    elif _fp_name == "sendle":
                        file_name = f"{fp_name}_label_{booking.pu_Address_State}_{booking.v_FPBookingNumber}_{str(datetime.now())}.pdf"

                    z_label_url = f"{_fp_name}_au/{file_name}"
                    full_path = f"{S3_URL}/pdfs/{z_label_url}"

                    if _fp_name == "tnt":
                        with open(full_path, "wb") as f:
                            f.write(label_data)
                            f.close()
                    else:
                        pdf_url = json_data["pdfURL"]
                        download_from_url(pdf_url, full_path)
                except KeyError as e:
                    if "errorMessage" in json_data:
                        error_msg = json_data["errorMessage"]
                        _set_error(booking, error_msg)
                        return JsonResponse(
                            {"message": error_msg}, status=status.HTTP_400_BAD_REQUEST
                        )

                    trace_error.print()
                    error_msg = f"KeyError: {e}"
                    _set_error(booking, error_msg)
            # Deactivated on 2022-09-22
            # elif _fp_name in ["dhl"]:
            #     file_path = f"{S3_URL}/pdfs/{_fp_name}_au/"
            #     file_path, file_name = build_label(booking, file_path)
            #     z_label_url = f"{_fp_name}_au/{file_name}"

            # JasonL & BSD
            if not booking.kf_client_id in [
                "1af6bcd2-6148-11eb-ae93-0242ac130002",
                "9e72da0f-77c3-4355-a5ce-70611ffd0bc8",
            ]:
                # JasonL & BSD never get Label from FP
                booking.z_label_url = z_label_url

            booking.b_error_Capture = None
            booking.save()

            # Do not send email when booking is `Rebooked`
            if (
                not _fp_name in ["startrack", "auspost"]
                and not "Rebooked" in booking.b_status
            ):
                # Send email when GET_LABEL
                email_template_name = "General Booking"

                if booking.b_booking_Category == "Salvage Expense":
                    email_template_name = "Return Booking"

                send_booking_status_email(
                    booking.pk, email_template_name, request.user.username
                )

            # if not _fp_name in ["sendle"]:
            Log(
                request_payload=payload,
                request_status="SUCCESS",
                request_type=f"{fp_name.upper()} GET LABEL",
                response=res_content,
                fk_booking_id=booking.id,
            ).save()

            return JsonResponse(
                {"message": f"Successfully created label({booking.z_label_url})"},
                status=status.HTTP_200_OK,
            )
        except KeyError as e:
            logger.error(f"[GET LABEL] Error - {str(e)}")
            trace_error.print()
            Log(
                request_payload=payload,
                request_status="ERROR",
                request_type=f"{fp_name.upper()} GET LABEL",
                response=res_content,
                fk_booking_id=booking.id,
            ).save()

            error_msg = res_content

            if _fp_name in ["tnt"]:
                error_msg = json_data["errorMessage"]

            _set_error(booking, error_msg)
            return JsonResponse(
                {"message": error_msg}, status=status.HTTP_400_BAD_REQUEST
            )
    except IndexError as e:
        trace_error.print()
        return JsonResponse(
            {"message": "IndexError: {e}"}, status=status.HTTP_400_BAD_REQUEST
        )


@api_view(["POST"])
@authentication_classes((SessionAuthentication, BasicAuthentication))
@permission_classes((AllowAny,))
def create_order(request, fp_name):
    results = []
    body = literal_eval(request.body.decode("utf8"))
    booking_ids = body["bookingIds"]
    payload = None

    try:
        bookings = Bookings.objects.filter(
            pk__in=booking_ids,
            b_dateBookedDate__isnull=False,
            vx_freight_provider__iexact=fp_name,
        )

        if bookings.exists() and bookings.first().vx_fp_order_id:
            message = f"Successfully create order({bookings.first().vx_fp_order_id})"
            return JsonResponse({"message": message})

        payload = get_create_order_payload(bookings, fp_name)
        logger.info(f"Payload(Create Order for {fp_name}): {payload}")
        url = DME_LEVEL_API_URL + "/order/create"
        headers = HEADER_FOR_NODE

        # TGE (via Spojit)
        if fp_name.lower() == "team global express":
            from api.fps.team_global_express import (
                get_base_url as get_tge_base_url,
                get_headers as get_tge_headers,
                get_service_code as get_tge_service_code,
            )
            service_code = get_tge_service_code(bookings.first())
            base_url = get_tge_base_url(bookings.first())
            url = f"{base_url}/{service_code}/order/create"
            headers = get_tge_headers(bookings.first())

            # JasonL
            if bookings.first().kf_client_id == "1af6bcd2-6148-11eb-ae93-0242ac130002" and service_code == "ins":
                payload_bookings = payload["bookings"]
                for booking in bookings:
                    payload["bookings"] = [get_book_payload(booking, fp_name)]
                    url = get_tge_ins_order_url(booking)
                    response = requests.post(url, params={}, json=payload, headers=headers)
                    logger.info(f"Response(Create Order One by One for JasonL {fp_name} {payload}): {response}")
                url = get_tge_ins_summary_url(booking)
                payload["bookings"] = payload_bookings

        #     # Aberdeen
        #     if bookings.first().kf_client_id == "4ac9d3ee-2558-4475-bdbb-9d9405279e81":
        #         payload_bookings = payload["bookings"]
        #         for booking in bookings:
        #             payload["bookings"] = [get_book_payload(booking, fp_name)]
        #             response = requests.post(url, params={}, json=payload, headers=headers)
        #             logger.info(f"Response(Create Order for Aberdeen {fp_name} {payload}): {response}")
             
        # # Not Aberdeen
        # if bookings.first().kf_client_id != "4ac9d3ee-2558-4475-bdbb-9d9405279e81":
        
        response = requests.post(url, params={}, json=payload, headers=headers)
        had_504_res = False
        while response.status_code == 504:
            had_504_res = True
            response = requests.post(
                url, params={}, json=payload, headers=HEADER_FOR_NODE
            )

        res_content = response.content.decode("utf8").replace("'", '"')
        json_data = json.loads(res_content)
        s0 = json.dumps(
            json_data, indent=2, sort_keys=True, default=str
        )  # Just for visual
        logger.info(f"Response(Create Order for {fp_name}): {s0}")

        try:
            Log(
                request_payload=payload,
                request_status="SUCCESS",
                request_type=f"CREATE ORDER",
                response=res_content,
                fk_booking_id=bookings[0].pk_booking_id,
            ).save()

            for booking in bookings:
                # TGE I&S `TW` pickup number
                pickup_ref_no = json_data.get("pickup_ref_no")
                order_id = json_data["order_id"]
                order_id = pickup_ref_no or order_id
                booking.vx_fp_order_id = (
                    order_id if not had_504_res else json_data[0]["context"]["order_id"]
                )
                booking.fk_fp_pickup_id = pickup_ref_no
                booking.save()

            return JsonResponse(
                {"message": f"Successfully create order({booking.vx_fp_order_id})"}
            )
        except KeyError as e:
            trace_error.print()
            booking.b_error_Capture = json_data["errorMsg"]
            booking.save()
            Log(
                request_payload=payload,
                request_status="ERROR",
                request_type=f"{fp_name.upper()} CREATE ORDER",
                response=res_content,
                fk_booking_id=booking.id,
            ).save()

            error_msg = s0
            _set_error(booking, error_msg)
            send_email_to_admins(f"{fp_name.upper()} CREATE ORDER", error_msg)
            return JsonResponse({"message": error_msg})
    except IndexError as e:
        trace_error.print()
        send_email_to_admins(f"{fp_name.upper()} CREATE ORDER", f"IndexError: {e}")
        return JsonResponse({"message": f"IndexError: e"})
    except Exception as e:
        trace_error.print()
        send_email_to_admins(
            f"{fp_name.upper()} CREATE ORDER", f"Payload: {payload},\nException: {e}"
        )
        return JsonResponse({"message": f"Exception: e"})


@api_view(["POST"])
@authentication_classes((SessionAuthentication, BasicAuthentication))
@permission_classes((AllowAny,))
def get_order_summary(request, fp_name):
    try:
        body = literal_eval(request.body.decode("utf8"))
        booking_ids = body["bookingIds"]
        _fp_name = fp_name.lower()

        try:
            booking = Bookings.objects.get(id=booking_ids[0])
            bookings = Bookings.objects.filter(
                pk__in=booking_ids,
                b_dateBookedDate__isnull=False,
                vx_freight_provider__iexact=fp_name,
            )

            booking_ids = []
            for booking in bookings:
                booking_ids.append(str(booking.pk))

            payload = get_get_order_summary_payload(bookings, fp_name)
            headers = {
                "Accept": "application/pdf",
                "Content-Type": "application/json",
                **HEADER_FOR_NODE,
            }
            url = DME_LEVEL_API_URL + "/order/summary"

            # TGE (via Spojit)
            if _fp_name == "team global express":
                from api.fps.team_global_express import (
                    get_base_url as get_tge_base_url,
                    get_headers as get_tge_headers,
                    get_service_code as get_tge_service_code,
                )

                service_code = get_tge_service_code(booking)
                base_url = get_tge_base_url(booking)
                url = f"{base_url}/{service_code}/callback/order/summary"
                headers = get_tge_headers(booking)

            logger.info(f"### Payload ({fp_name} Get Order Summary): {url} {payload}")
            response = requests.post(url, json=payload, headers=headers)
            res_content = response.content
            json_data = json.loads(res_content)
            # Just for visual
            s0 = json.dumps(json_data, indent=2, sort_keys=True, default=str)
            logger.info(f"### Response ({fp_name} Get Order Summary): {json_data}")

            try:
                suffix = f"{str(booking.vx_fp_order_id)}_{str(datetime.now())}.pdf"
                file_name = f"manifest_{suffix}"
                full_path = f"{S3_URL}/pdfs/{_fp_name}_au/{file_name}"

                if _fp_name == "team global express":
                    # Webhook case
                    if not "pdfData" in json_data:
                        msg = "Manifest will be ready in 5 mins."
                        return JsonResponse({"message": msg})

                    pod_data = base64.b64decode(json_data["pdfData"]["data"])

                    # ONLY for BioPak + TGE + PE (Pallet Express service)
                    # Download Pickup PDF file
                    if "consignmentData" in json_data:
                        pickup_file_name = f"pickup_{suffix}"
                        pickup_full_path = (
                            f"{S3_URL}/pdfs/{_fp_name}_au/{pickup_file_name}"
                        )
                        pickup_data = base64.b64decode(
                            json_data["consignmentData"]["data"]
                        )
                        with open(pickup_full_path, "wb") as f:
                            f.write(pickup_data)
                            f.close()
                else:
                    pod_data = bytes(json_data["pdfData"]["data"])

                with open(full_path, "wb") as f:
                    f.write(pod_data)
                    f.close()

                manifest_timestamp = datetime.now()
                for booking in bookings:
                    booking.z_manifest_url = f"{_fp_name}_au/{file_name}"
                    booking.manifest_timestamp = manifest_timestamp
                    booking.save()

                Dme_manifest_log.objects.create(
                    fk_booking_id=booking.pk_booking_id,
                    manifest_url=booking.z_manifest_url,
                    manifest_number=str(booking.vx_fp_order_id),
                    bookings_cnt=bookings.count(),
                    is_one_booking=False,
                    z_createdByAccount=request.user.username,
                    booking_ids=",".join(booking_ids),
                    freight_provider=fp_name,
                )

                Log(
                    request_payload=payload,
                    request_status="SUCCESS",
                    request_type=f"ORDER SUMMARY",
                    response=res_content,
                    fk_booking_id=bookings[0].pk_booking_id,
                ).save()

                return JsonResponse({"message": "Manifest is created successfully."})
            except KeyError as e:
                trace_error.print()
                Log(
                    request_payload=payload,
                    request_status="FAILED",
                    request_type=f"ORDER SUMMARY",
                    response=res_content,
                    fk_booking_id=bookings[0].pk_booking_id,
                ).save()

                error_msg = s0
                _set_error(booking, error_msg)
                return JsonResponse({"message": s0})
        except IndexError as e:
            trace_error.print()
            error_msg = "Order is not created for this booking."
            _set_error(booking, error_msg)
            return JsonResponse({"message": error_msg})
    except SyntaxError:
        trace_error.print()
        return JsonResponse({"message": "Booking id is required"})


@api_view(["POST"])
@authentication_classes((SessionAuthentication, BasicAuthentication))
@permission_classes((AllowAny,))
def get_booking_info(request, fp_name):
    try:
        body = literal_eval(request.body.decode("utf8"))
        booking_ids = body["booking_ids"].split(",")
        _fp_name = fp_name.lower()

        bookings = Bookings.objects.filter(
            pk__in=booking_ids,
            # b_dateBookedDate__isnull=False,
            vx_freight_provider__iexact=fp_name,
        )

        payload_list = []
        for booking in bookings:
            try:
                payload = get_spojit_book_payload(booking, _fp_name)
                payload_list.append(payload)
            except Exception as e:
                trace_error.print()

        logger.info(f"### Payload ({fp_name} get_booking_info): {payload_list}")

        return JsonResponse({"bookings": payload_list})

    except SyntaxError as e:
        trace_error.print()
        return JsonResponse(
            {"message": f"SyntaxError: {e}"}, status=status.HTTP_400_BAD_REQUEST
        )


@api_view(["POST"])
@authentication_classes((SessionAuthentication, BasicAuthentication))
@permission_classes((AllowAny,))
def pod(request, fp_name):
    try:
        body = literal_eval(request.body.decode("utf8"))
        booking_id = body["booking_id"]
        _fp_name = fp_name.lower()
    except SyntaxError:
        trace_error.print()
        return JsonResponse(
            {"message": "Booking id is required"}, status=status.HTTP_400_BAD_REQUEST
        )

    try:
        booking = Bookings.objects.get(id=booking_id)
    except KeyError as e:
        trace_error.print()
        return JsonResponse({"message": str(e)}, status=status.HTTP_400_BAD_REQUEST)

    try:
        payload = get_pod_payload(booking, fp_name)
        logger.info(f"### Payload ({fp_name} POD): {payload}")

        url = DME_LEVEL_API_URL + "/pod/fetchpod"
        response = requests.post(url, params={}, json=payload, headers=HEADER_FOR_NODE)
        res_content = response.content.decode("utf8").replace("'", '"')
        json_data = json.loads(res_content)
        s0 = json.dumps(json_data, indent=2, sort_keys=True)  # Just for visual
        logger.info(f"### Response ({fp_name} POD): {s0}")

        if _fp_name in ["hunter"]:
            try:
                podData = json_data[0]["podImage"]
            except KeyError as e:
                error_msg = json_data["errorMessage"]
                _set_error(booking, error_msg)
                return JsonResponse({"message": error_msg})
        else:
            if "errorMessage" in json_data:
                error_msg = json_data["errorMessage"]
                _set_error(booking, error_msg)
                return JsonResponse({"message": error_msg})
            elif "podData" not in json_data["pod"]:
                error_msg = "Unknown error, please contact support center."
                _set_error(booking, error_msg)
                return JsonResponse({"message": error_msg})
            podData = json_data["pod"]["podData"]

        file_name = f"POD_{booking.pu_Address_State}_{toAlphaNumeric(booking.b_client_sales_inv_num)}_{str(datetime.now().strftime('%Y%m%d_%H%M%S'))}"

        file_name += ".jpeg" if _fp_name in ["hunter"] else ".png"
        full_path = f"{S3_URL}/imgs/{_fp_name}_au/{file_name}"

        f = open(full_path, "wb")
        f.write(base64.b64decode(podData))
        f.close()

        booking.z_pod_url = f"{_fp_name}_au/{file_name}"
        booking.b_error_Capture = None
        booking.save()

        # POD Email
        if booking.b_send_POD_eMail:
            email_template_name = "POD"
            send_booking_status_email(
                booking.pk, email_template_name, request.user.username
            )

        return JsonResponse({"message": "POD is fetched successfully."})
    except Exception as e:
        trace_error.print()
        error_msg = f"KeyError: {e}"
        _set_error(booking, error_msg)
        return JsonResponse({"message": str(e)}, status=status.HTTP_400_BAD_REQUEST)


@api_view(["POST"])
@authentication_classes((SessionAuthentication, BasicAuthentication))
@permission_classes((AllowAny,))
def reprint(request, fp_name):
    try:
        _fp_name = fp_name.lower()
        body = literal_eval(request.body.decode("utf8"))
        booking_id = body["booking_id"]

        try:
            booking = Bookings.objects.get(id=booking_id)
            payload = get_reprint_payload(booking, fp_name)

            logger.info(f"### Payload ({fp_name} REPRINT): {payload}")
            url = DME_LEVEL_API_URL + "/labelling/reprint"
            response = requests.post(
                url, params={}, json=payload, headers=HEADER_FOR_NODE
            )

            res_content = response.content.decode("utf8").replace("'", '"')
            json_data = json.loads(res_content)

            # s0 = json.dumps(json_data, indent=2, sort_keys=True)  # Just for visual
            # logger.info(f"### Response ({fp_name} POD): {s0}")

            podData = json_data["ReprintActionResult"]["LabelPDF"]

            try:
                file_name = f"{fp_name}_reprint_{booking.pu_Address_State}_{toAlphaNumeric(booking.b_client_sales_inv_num)}_{str(datetime.now())}.pdf"
                full_path = f"{S3_URL}/pdfs/{_fp_name}_au/{file_name}"

                with open(full_path, "wb") as f:
                    f.write(base64.b64decode(podData))
                    f.close()

                booking.z_label_url = f"{_fp_name}_au/{file_name}"
                booking.b_error_Capture = None
                booking.save()

                return JsonResponse({"message": "Label is reprinted successfully."})
            except KeyError as e:
                trace_error.print()
                error_msg = f"KeyError: {e}"
                _set_error(booking, error_msg)
                return JsonResponse({"message": s0}, status=status.HTTP_400_BAD_REQUEST)
        except KeyError as e:
            if "errorMessage" in json_data:
                error_msg = json_data["errorMessage"]
                _set_error(booking, error_msg)
                return JsonResponse(
                    {"message": error_msg}, status=status.HTTP_400_BAD_REQUEST
                )
            trace_error.print()
            return JsonResponse(
                {"Error": "Too many request"}, status=status.HTTP_400_BAD_REQUEST
            )
    except SyntaxError:
        trace_error.print()
        return JsonResponse(
            {"message": "Booking id is required"}, status=status.HTTP_400_BAD_REQUEST
        )


@api_view(["POST"])
@authentication_classes((SessionAuthentication, BasicAuthentication))
@permission_classes((AllowAny,))
def pricing(request):
    body = literal_eval(request.body.decode("utf8"))
    booking_id = body["booking_id"]
    auto_select_type = body.get("auto_select_type", 1)
    is_pricing_only = False

    if not booking_id and "booking" in body:
        is_pricing_only = True
        packed_statuses = [Booking_lines.ORIGINAL]
    else:
        packed_statuses = [
            Booking_lines.ORIGINAL,
            Booking_lines.AUTO_PACK,
            Booking_lines.MANUAL_PACK,
            Booking_lines.SCANNED_PACK,
        ]

    booking, success, message, results, client = pricing_oper(
        body, booking_id, is_pricing_only, packed_statuses
    )
    client_customer_mark_up = client.client_customer_mark_up or 0

    if not success:
        return JsonResponse(
            {"success": False, "message": message}, status=status.HTTP_400_BAD_REQUEST
        )

    json_results = ApiBookingQuotesSerializer(
        results,
        many=True,
        context={
            "booking": booking,
            "client_customer_mark_up": client_customer_mark_up,
        },
    ).data

    if is_pricing_only:
        API_booking_quotes.objects.filter(fk_booking_id=booking.pk_booking_id).delete()
    else:
        _results = []
        if booking.api_booking_quote and booking.is_quote_locked:
            for quote in results:
                if (
                    quote.freight_provider == booking.vx_freight_provider
                    and quote.service_name == booking.vx_serviceName
                    and quote.packed_status == booking.api_booking_quote.packed_status
                ):
                    _results.append(quote)
        elif booking.kf_client_id == "4ac9d3ee-2558-4475-bdbb-9d9405279e81":
            # Aberdeen Paper & Direct Freight
            for quote in results:
                if quote.freight_provider == "Direct Freight":
                    _results.append(quote)
        else:
            for quote in results:
                if quote.freight_provider != "Sendle":
                    _results.append(quote)

        if _results:
            results = _results

        if not booking.b_dateBookedDate and booking.b_client_name != "Ariston Wire":
            auto_select_pricing(booking, results, auto_select_type, client)

    res_json = {"success": True, "message": message, "results": json_results}
    return JsonResponse(res_json, status=status.HTTP_200_OK)


@api_view(["POST"])
@authentication_classes((SessionAuthentication, BasicAuthentication))
@permission_classes((AllowAny,))
def update_servce_code(request, fp_name):
    _fp_name = fp_name.lower()

    try:
        payload = get_get_accounts_payload(_fp_name)
        headers = {
            "Accept": "application/pdf",
            "Content-Type": "application/json",
            **HEADER_FOR_NODE,
        }
        logger.info(f"### Payload ({fp_name.upper()} Get Accounts): {payload}")
        url = DME_LEVEL_API_URL + "/servicecode/getaccounts"
        response = requests.post(url, json=payload, headers=headers)
        res_content = response.content
        json_data = json.loads(res_content)
        # Just for visual
        s0 = json.dumps(json_data, indent=2, sort_keys=True, default=str)
        fp = Fp_freight_providers.objects.filter(
            fp_company_name__iexact=_fp_name
        ).first()

        for data in json_data["returns_products"]:
            product_type = data["type"]
            product_id = data["product_id"]

            etd, is_created = FP_Service_ETDs.objects.update_or_create(
                fp_delivery_service_code=product_id,
                fp_delivery_time_description=product_type,
                freight_provider=fp,
                dme_service_code_id=1,
            )

        for data in json_data["postage_products"]:
            product_type = data["type"]
            product_id = data["product_id"]

            etd, is_created = FP_Service_ETDs.objects.update_or_create(
                fp_delivery_service_code=product_id,
                fp_delivery_time_description=product_type,
                freight_provider=fp,
                dme_service_code_id=1,
            )

        return JsonResponse({"message": "Updated service codes successfully."})
    except IndexError as e:
        trace_error.print()
        error_msg = "GetAccounts is failed."
        _set_error(booking, error_msg)
        return JsonResponse({"message": error_msg})


def get_etd(booking):
    """
    Avalilable FPs: Startrack
    """
    LOG_ID = "GET_ETD"
    fp_name = booking.vx_freight_provider
    _fp_name = booking.vx_freight_provider.lower()

    try:
        payload = get_etd_payload(booking, _fp_name)

        logger.info(f"### Payload ({fp_name} ETD): {payload}")
        url = DME_LEVEL_API_URL + "/pricing/getetd"
        response = requests.post(url, params={}, json=payload, headers=HEADER_FOR_NODE)

        res_content = response.content.decode("utf8").replace("'", '"')
        json_data = json.loads(res_content)
        logger.info(f"{LOG_ID} {json_data}")

        business_days_min = json_data["estimated_delivery_dates"][0][
            "business_days_min"
        ]
        business_days_max = json_data["estimated_delivery_dates"][0][
            "business_days_max"
        ]

        logger.info(f"{LOG_ID} min: {business_days_min}, max: {business_days_max}")

        return business_days_max
    except Exception as e:
        trace_error.print()
        error_msg = "GETETD is failed."
        logger.error(f"{LOG_ID} {error_msg}, error: {str(e)}")
        return None
