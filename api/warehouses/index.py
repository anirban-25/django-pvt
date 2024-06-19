import json
import uuid
import logging
import requests
import time as t
from datetime import datetime, date
from base64 import b64encode

from django.conf import settings
from django.db import models, transaction
from rest_framework.exceptions import ValidationError

from api.clients.anchor_packaging.constants import AP_FREIGHTS
from api.models import (
    Bookings,
    Booking_lines,
    Booking_lines_data,
    BOK_1_headers,
    BOK_2_lines,
    Log,
    FC_Log,
    FPRouting,
)
from api.fp_apis.utils import (
    select_best_options,
    auto_select_pricing_4_bok,
    gen_consignment_num,
)
from api.fp_apis.operations.pricing import pricing as pricing_oper
from api.operations.email_senders import send_email_to_admins
from api.operations.labels.index import build_label as build_label_oper
from api.operations.manifests.index import build_manifest as build_manifest_oper
from api.common.booking_quote import set_booking_quote
from api.common.thread import background
from api.common import (
    time as dme_time_lib,
    constants as dme_constants,
    status_history,
    trace_error,
)
from api.convertors import pdf
from api.warehouses.libs import build_push_payload
from api.warehouses.constants import (
    SPOJIT_API_URL,
    SPOJIT_TOKEN,
    SPOJIT_WAREHOUSE_MAPPINGS,
    CARRIER_MAPPING,
)

logger = logging.getLogger(__name__)


def push(bok_1):
    LOG_ID = "[PUSH TO WHSE]"

    try:
        headers = {"content-type": "application/json", "Authorization": SPOJIT_TOKEN}
        url = f"{SPOJIT_API_URL}/webhook/{SPOJIT_WAREHOUSE_MAPPINGS[bok_1.b_client_warehouse_code]}"
        bok_2s = BOK_2_lines.objects.filter(
            fk_header_id=bok_1.pk_header_id, b_093_packed_status=BOK_2_lines.ORIGINAL
        )
        log = Log(fk_booking_id=bok_1.pk_header_id, request_type="WHSE_PUSH")
        log.save()

        try:
            logger.info(f"@9000 {LOG_ID} url - {url}")
            payload = build_push_payload(bok_1, bok_2s)
            logger.info(f"@9000 {LOG_ID} payload - {payload}")
        except Exception as e:
            error = f"@901 {LOG_ID} error on payload builder.\n\nError: {str(e)}\nBok_1: {str(bok_1.pk)}\nOrder Number: {bok_1.b_client_order_num}"
            logger.error(error)
            raise Exception(error)

        response = requests.post(url, headers=headers, json=payload)
        res_content = response.content.decode("utf8").replace("'", '"')
        json_data = json.loads(res_content)
        s0 = json.dumps(json_data, indent=2, sort_keys=True)  # Just for visual
        logger.info(f"### Response: {s0}")
    except Exception as e:
        if bok_1.b_client_order_num:
            to_emails = [settings.ADMIN_EMAIL_02]
            subject = "Error on Whse workflow"

            if settings.ENV == "prod":
                to_emails.append(settings.SUPPORT_CENTER_EMAIL)

            send_email(
                send_to=to_emails,
                send_cc=[],
                send_bcc=["goldj@deliver-me.com.au"],
                subject=subject,
                text=str(e),
            )
            logger.error(f"@905 {LOG_ID} Sent email notification!")

        return None


def push_webhook(data):
    LOG_ID = "[WHSE PUSH WEBHOOK]"
    logger.info(f"{LOG_ID} Webhook data: {data}")

    if data["code"] == "success":
        bok_1_pk = data.get("bookingId")
        order_num = data.get("orderNumber")

        if not bok_1_pk or not order_num:
            message = f"{LOG_ID} Webhook data is invalid. Data: {data}"
            logger.error(message)
            send_email_to_admins("Invalid webhook data", message)

        try:
            bok_1 = BOK_1_headers.objects.get(pk=bok_1_pk, b_client_order_num=order_num)
            bok_2s = BOK_2_lines.objects.filter(fk_header_id=bok_1.pk_header_id)

            for bok_2 in bok_2s:
                bok_2.success = dme_constants.BOK_SUCCESS_4
                bok_2.save()

            bok_1.success = dme_constants.BOK_SUCCESS_4
            bok_1.save()
            logger.info(
                f"{LOG_ID} Bok_1 will be mapped. Detail: {bok_1_pk}(pk_auto_id), {order_num}(order number)"
            )
        except:
            message = f"{LOG_ID} BOK_1 does not exist. Data: {data}"
            logger.error(message)
            send_email_to_admins("No BOK_1", message)

    return None


@background
def send_scanned_email_in_bg(booking):
    LOG_ID = "[WHSE SCANNED]"
    msg = f"Client: {booking.b_client_name}\nFP: {booking.vx_freight_provider}\nOrderNo: {booking.b_client_order_num}"
    logger.info(f"{LOG_ID} {msg}")
    send_email_to_admins("Order is scanned", msg)


def scanned(payload):
    """
    called as get_label

    request when item(s) is picked(scanned) at warehouse
    should response LABEL if payload is correct
    """

    LOG_ID = "[SCANNED at WHSE]"
    client_name = payload.get("clientName")
    b_client_order_num = payload.get("orderNumber")
    picked_items = payload.get("items")
    time1 = t.time()

    # Check required params are included
    if not client_name:
        message = "'clientName' is required."
        raise ValidationError(message)

    if not b_client_order_num:
        message = "'orderNumber' is required."
        raise ValidationError(message)

    if not picked_items:
        message = "'items' is required."
        raise ValidationError(message)

    # Check if Order exists on Bookings table
    bookings = Bookings.objects.select_related("api_booking_quote").filter(
        b_client_name__iexact=client_name, b_client_order_num=b_client_order_num
    )

    if bookings.count() == 0:
        message = f"Order({b_client_order_num}) does not exist."
        # raise ValidationError(message)
        return {"success": True, "message": message, "freightProvider": "None"}
    else:
        booking = bookings.first()

    freight_provider = CARRIER_MAPPING[booking.vx_freight_provider.lower()]
    if "MCPHEE_" in booking.b_client_warehouse_code and freight_provider == "DMECHP":
        freight_provider = "DME-DMECHP"

    if booking.b_status not in ["Picking", "Picked"]:
        return {
            "success": True,
            "message": "Already Picked.",
            "freightProvider": freight_provider,
        }

    if CARRIER_MAPPING[booking.vx_freight_provider.lower()] == "AFSCHP":
        return {
            "success": False,
            "message": "Label should be generated by Warehouse.",
            "freightProvider": freight_provider,
        }

    # If Order exists
    pk_booking_id = booking.pk_booking_id
    lines = Booking_lines.objects.filter(fk_booking_id=pk_booking_id)
    line_datas = Booking_lines_data.objects.filter(fk_booking_id=pk_booking_id)
    original_items = lines.filter(
        sscc__isnull=True, packed_status=Booking_lines.ORIGINAL
    )
    scanned_items = lines.filter(sscc__isnull=False, e_item="Picked Item")
    sscc_list = scanned_items.values_list("sscc", flat=True)

    logger.info(f"@360 {LOG_ID} Booking: {booking}")
    logger.info(f"@361 {LOG_ID} Lines: {lines}")
    logger.info(f"@362 {LOG_ID} original_items: {original_items}")
    logger.info(f"@363 {LOG_ID} scanned_items: {scanned_items}")
    logger.info(f"@365 {LOG_ID} sscc(s): {sscc_list}")

    # Delete existing ssccs(for scanned ones)
    scanned_items.delete()

    # Save
    try:
        labels = []
        sscc_list = []
        sscc_lines = {}

        with transaction.atomic():
            for picked_item in picked_items:
                # Create new Lines
                new_line = Booking_lines()
                new_line.fk_booking_id = pk_booking_id
                new_line.pk_booking_lines_id = str(uuid.uuid4())
                new_line.e_type_of_packaging = picked_item.get("packageType") or "CTN"
                new_line.e_qty = 1
                new_line.e_item = "Picked Item"
                new_line.packed_status = Booking_lines.SCANNED_PACK
                new_line.e_dimUOM = picked_item["dimUOM"]
                new_line.e_dimLength = picked_item["length"]
                new_line.e_dimWidth = picked_item["width"]
                new_line.e_dimHeight = picked_item["height"]
                new_line.e_weightUOM = picked_item["weightUOM"]
                new_line.e_weightPerEach = picked_item["weight"]
                new_line.e_Total_KG_weight = picked_item["weight"]
                sscc = str(picked_item.get("sscc"))
                new_line.sscc = sscc
                new_line.picked_up_timestamp = (
                    picked_item.get("timestamp") or datetime.now()
                )
                new_line.save()

                if picked_item["sscc"] not in sscc_list:
                    sscc_list.append(sscc)
                    sscc_lines[sscc] = [new_line]
                else:
                    sscc_lines[sscc].append(new_line)

                # for item in picked_item["items"]:
                #     # Create new Line_Data
                #     line_data = Booking_lines_data()
                #     line_data.fk_booking_id = pk_booking_id
                #     line_data.fk_booking_lines_id = new_line.pk_booking_lines_id
                #     line_data.modelNumber = item["model_number"]
                #     line_data.itemDescription = "Picked at warehouse"
                #     line_data.quantity = item.get("qty")
                #     line_data.clientRefNumber = picked_item["sscc"]
                #     line_data.save()

        next_biz_day = dme_time_lib.next_business_day(date.today(), 1)
        booking.puPickUpAvailFrom_Date = next_biz_day

        # Re-quote
        set_booking_quote(booking, None)
        logger.info(
            f"#371 {LOG_ID} {booking.b_bookingID_Visual} - Getting Quotes again..."
        )
        _, success, message, quotes, client = pricing_oper(
            body=None,
            booking_id=booking.pk,
            is_pricing_only=False,
            packed_statuses=[Booking_lines.SCANNED_PACK],
        )
        logger.info(
            f"#372 {LOG_ID} - Pricing result: success: {success}, message: {message}, results cnt: {len(quotes)}"
        )

        # Select best quotes(fastest, lowest)
        best_quote = None
        if quotes:
            _quotes = []
            for quote in quotes:
                if quote.freight_provider in AP_FREIGHTS:
                    continue
                if quote.packed_status == Booking_lines.SCANNED_PACK:
                    _quotes.append(quote)
            quotes = _quotes

            best_quotes = select_best_options(pricings=quotes)
            logger.info(f"#373 {LOG_ID} - Selected Best Pricings: {best_quotes}")

            if best_quotes:
                best_quote = best_quotes[0]
                set_booking_quote(booking, best_quote)

        if not best_quote:
            message = f"#521 {LOG_ID} Scanned but no pricing! Order Number: {booking.b_client_order_num} BookingId: {booking.b_bookingID_Visual}"
            logger.error(message)
            send_email_to_admins("No FC result", message)
            raise Exception("Booking doens't have quote.")
        
        if CARRIER_MAPPING[booking.vx_freight_provider.lower()] == "AFSCHP":
            return {
                "success": False,
                "message": "Label should be generated by Warehouse.",
                "freightProvider": freight_provider,
            }

        # Build label with SSCC - one sscc should have one page label
        file_path = (
            f"{settings.STATIC_PUBLIC}/pdfs/{booking.vx_freight_provider.lower()}_au"
        )
        label_data = build_label_oper(
            booking=booking,
            file_path=file_path,
            total_qty=len(sscc_list),
            sscc_list=sscc_list,
            sscc_lines=sscc_lines,
            need_base64=True,
            need_zpl=False,
        )

        entire_label_url = f"{file_path}/DME{booking.b_bookingID_Visual}.pdf"
        pdf.pdf_merge(label_data["urls"], entire_label_url)
        booking.z_label_url = f"{booking.vx_freight_provider.lower()}_au/DME{booking.b_bookingID_Visual}.pdf"
        # Set consignment number
        booking.v_FPBookingNumber = gen_consignment_num(
            booking.vx_freight_provider,
            booking.b_bookingID_Visual,
            booking.kf_client_id,
            booking,
        )
        entire_label_b64 = str(pdf.pdf_to_base64(entire_label_url))[2:-1]
        booking.save()

        entire_consignment_b64 = None
        if booking.vx_freight_provider.lower() in ["northline"]:
            entire_consignment_url = (
                f"{file_path}/DME{booking.b_bookingID_Visual}_consignment.pdf"
            )
            consignment_urls = []
            for label_url in label_data["urls"]:
                consignment_url = label_url.replace(".pdf", "_consignment.pdf")
                consignment_urls.append(consignment_url)
            pdf.pdf_merge(label_data["urls"], entire_consignment_url)
            entire_consignment_b64 = pdf.pdf_to_base64(entire_consignment_url)
            entire_consignment_b64 = str(entire_consignment_b64)[2:-1]

        time2 = t.time()
        logger.info(f"{LOG_ID} Spent time: {str(int(round(time2 - time1)))}s\n")
        logger.info(
            f"#379 {LOG_ID} - Successfully scanned. Booking Id: {booking.b_bookingID_Visual}"
        )

        if not booking.b_dateBookedDate and booking.b_status != "Picked":
            status_history.create(booking, "Picked", client_name)

        # Send email in bg
        send_scanned_email_in_bg(booking)

        return {
            "success": True,
            "message": "Successfully updated picked info.",
            "invNumber": booking.b_client_order_num,
            "consignmentNumber": gen_consignment_num(
                booking.vx_freight_provider,
                booking.b_bookingID_Visual,
                booking.kf_client_id,
                booking,
            ),
            "labels": label_data["labels"],
            "label": entire_label_b64,
            "consignmentPdf": entire_consignment_b64,
            "freightProvider": freight_provider,
        }
    except Exception as e:
        trace_error.print()
        error_msg = f"@370 {LOG_ID} Exception: {str(e)}"
        logger.error(error_msg)
        send_email_to_admins(f"{LOG_ID}", f"{error_msg}")
        raise Exception(
            "Please contact DME support center. <bookings@deliver-me.com.au>"
        )


def reprint_label(params):
    """
    get label(already built)
    """
    LOG_ID = "[REPRINT from WHSE]"
    client_name = params.get("clientName")
    b_client_order_num = params.get("orderNumber")
    sscc = params.get("sscc")

    if not b_client_order_num:
        message = "'orderNumber' is required."
        raise ValidationError(message)

    booking = (
        Bookings.objects.select_related("api_booking_quote")
        .filter(
            b_client_order_num=b_client_order_num,
            b_client_name__iexact=client_name,
        )
        .first()
    )

    if not booking:
        message = "Order does not exist. 'orderNumber' is invalid."
        raise ValidationError(message)

    fp_name = booking.api_booking_quote.freight_provider.lower()

    if sscc:
        is_exist = False
        sscc_line = None
        lines = Booking_lines.objects.filter(fk_booking_id=booking.pk_booking_id)

        for line in lines:
            if line.sscc == sscc:
                is_exist = True
                sscc_line = line

        if not is_exist:
            message = "SSCC is not found."
            raise ValidationError(message)

    if not sscc and not booking.z_label_url:
        message = "Label is not ready."
        raise ValidationError(message)

    if sscc:  # Line label
        filename = f"{booking.pu_Address_State}_{str(booking.b_bookingID_Visual)}_{str(sscc_line.sscc)}.pdf"
        label_url = f"{settings.STATIC_PUBLIC}/pdfs/{booking.vx_freight_provider.lower()}_au/{filename}"
    else:  # Order Label
        if not "http" in booking.z_label_url:
            label_url = f"{settings.STATIC_PUBLIC}/pdfs/{booking.z_label_url}"
        else:
            label_url = f"{settings.STATIC_PUBLIC}/pdfs/{booking.vx_freight_provider.lower()}_au/DME{booking.b_bookingID_Visual}.pdf"

    # Plum ZPL printer requries portrait label
    if booking.vx_freight_provider.lower() == "allied":
        label_url = pdf.rotate_pdf(label_url)

    # Convert label into ZPL format
    logger.info(f"@369 - converting LABEL({label_url}) into ZPL format...")
    result = pdf.pdf_to_zpl(label_url, label_url[:-4] + ".zpl")

    if not result:
        message = "Please contact DME support center. <bookings@deliver-me.com.au>"
        raise Exception(message)

    with open(label_url[:-4] + ".zpl", "rb") as zpl:
        zpl_data = str(b64encode(zpl.read()))[2:-1]

    return {
        "success": True,
        "message": "Successfully reprint label.",
        "label": zpl_data,
    }


def ready(payload):
    """
    When it is ready(picked all items) on Warehouse
    """
    LOG_ID = "[READY at WHSE]"
    client_name = payload.get("clientName")
    b_client_order_num = payload.get("orderNumber")

    # Check required params are included
    if not client_name:
        message = "'clientName' is required."
        raise ValidationError(message)

    if not b_client_order_num:
        message = "'orderNumber' is required."
        raise ValidationError(message)

    # Check if Order exists
    booking = (
        Bookings.objects.select_related("api_booking_quote")
        .filter(
            b_client_name__iexact=client_name,
            b_client_order_num=b_client_order_num,
        )
        .first()
    )

    if not booking:
        message = "Order does not exist. orderNumber' is invalid."
        raise ValidationError(message)

    # Check if already ready
    if booking.b_status not in ["Picking", "Ready for Booking"]:
        message = "Order was already Ready."
        logger.info(f"@342 {LOG_ID} {message}")
        return {"success": True, "message": message}

    # Update DB so that Booking can be BOOKED
    if booking.api_booking_quote:
        status_history.create(booking, "Ready for Booking", "WHSE Module")
    else:
        status_history.create(booking, "Ready for Booking", "WHSE Module")
        send_email_to_admins(
            f"URGENT! Quote issue on Booking(#{booking.b_bookingID_Visual})",
            f"Original FP was {booking.vx_freight_provider}({booking.vx_serviceName})."
            + f" After labels were made {booking.vx_freight_provider}({booking.vx_serviceName}) was not an option for shipment."
            + f" Please do FC manually again on DME portal.",
        )

    return {"success": True, "message": "Order will be BOOKED soon."}


def manifest(payload):
    LOG_ID = "[MANIFEST WHSE]"
    client_name = payload.get("clientName")
    order_nums = payload.get("orderNumbers")

    # Required fields
    if not order_nums:
        message = "'orderNumbers' is required."
        raise ValidationError(message)

    bookings = Bookings.objects.filter(
        b_client_name__iexact=client_name, b_client_order_num__in=order_nums
    ).only("id", "b_client_order_num")

    booking_ids = []
    filtered_order_nums = []
    for booking in bookings:
        booking_ids.append(booking.id)
        filtered_order_nums.append(booking.b_client_order_num)

    missing_order_nums = list(set(order_nums) - set(filtered_order_nums))

    if missing_order_nums:
        _missing_order_nums = ", ".join(missing_order_nums)
        raise ValidationError(f"Missing Order numbers: {_missing_order_nums}")

    bookings, manifest_url = build_manifest_oper(booking_ids, "WHSE Module")
    manifest_full_url = f"{settings.STATIC_PUBLIC}/pdfs/startrack_au/{manifest_url}"

    with open(manifest_full_url, "rb") as manifest:
        manifest_data = str(b64encode(manifest.read()))

    Bookings.objects.filter(
        b_client_name__iexact=client_name, b_client_order_num__in=order_nums
    ).update(z_manifest_url=manifest_url)

    return {
        "success": True,
        "message": "Successfully manifested.",
        "manifest": manifest_data,
    }
