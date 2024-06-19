import math
import json
import uuid
import logging
from datetime import datetime, date
from base64 import b64decode, b64encode

from django.conf import settings
from django.db import transaction
from django.db.models import Q
from rest_framework.exceptions import ValidationError

from api.models import (
    Bookings,
    Booking_lines,
    Booking_lines_data,
    FC_Log,
    BOK_1_headers,
    BOK_2_lines,
    BOK_3_lines_data,
    FPRouting,
    Api_booking_confirmation_lines,
    Pallet,
)
from api.serializers import SimpleQuoteSerializer
from api.serializers_client import *
from api.fp_apis.utils import (
    select_best_options,
    auto_select_pricing_4_bok,
    gen_consignment_num,
)
from api.convertors import pdf
from api.common import (
    time as dme_time_lib,
    constants as dme_constants,
    status_history,
)
from api.common.constants import ROLLS, PACKETS
from api.common.thread import background
from api.common.booking_quote import set_booking_quote
from api.common.pallet import get_number_of_pallets, get_palletized_by_ai
from api.helpers.cubic import get_cubic_meter
from api.fp_apis.operations.book import book as book_oper
from api.fp_apis.operations.pricing import pricing as pricing_oper
from api.operations.labels.index import build_label as build_label_oper, get_barcode
from api.operations.manifests.index import build_manifest
from api.operations.email_senders import send_email_to_admins
from api.operations import product_operations as product_oper
from api.operations.booking_line import index as line_oper
from api.clients.operations.index import get_warehouse, get_suburb_state
from api.convertors.packaging_type import get_package_type
from api.helpers.line import is_carton, is_pallet

logger = logging.getLogger(__name__)


def partial_pricing(payload, client, warehouse):
    LOG_ID = "[PP ABP]"
    bok_1 = payload["booking"]
    bok_1["pk_header_id"] = str(uuid.uuid4())
    bok_2s = payload["booking_lines"]
    json_results = []

    de_postal_code = bok_1.get("b_059_b_del_address_postalcode")
    de_state, de_suburb = get_suburb_state(de_postal_code)

    # Check if has lines
    if len(bok_2s) == 0:
        message = "Line items are required."
        logger.info(f"@815 {LOG_ID} {message}")
        raise Exception(message)

    # Get next business day
    next_biz_day = dme_time_lib.next_business_day(date.today(), 1)

    booking = {
        "pk_booking_id": bok_1["pk_header_id"],
        "puPickUpAvailFrom_Date": next_biz_day,
        "b_clientReference_RA_Numbers": "initial_RA_num",
        "puCompany": warehouse.name,
        "pu_Contact_F_L_Name": "initial_PU_contact",
        "pu_Email": "pu@email.com",
        "pu_Phone_Main": "419294339",
        "pu_Address_Street_1": warehouse.address1,
        "pu_Address_street_2": warehouse.address2,
        "pu_Address_Country": "Australia",
        "pu_Address_PostalCode": warehouse.postal_code,
        "pu_Address_State": warehouse.state,
        "pu_Address_Suburb": warehouse.suburb,
        "deToCompanyName": "initial_DE_company",
        "de_to_Contact_F_LName": "initial_DE_contact",
        "de_Email": "de@email.com",
        "de_to_Phone_Main": "419294339",
        "de_To_Address_Street_1": "initial_DE_street_1",
        "de_To_Address_Street_2": "",
        "de_To_Address_Country": "Australia",
        "de_To_Address_PostalCode": de_postal_code,
        "de_To_Address_State": de_state.upper(),
        "de_To_Address_Suburb": de_suburb,
        "pu_Address_Type": "business",
        "de_To_AddressType": "residential",
        "b_booking_tail_lift_pickup": False,
        "b_booking_tail_lift_deliver": False,
        "client_warehouse_code": warehouse.client_warehouse_code,
        "vx_serviceName": "exp",
        "kf_client_id": warehouse.fk_id_dme_client.dme_account_num,
        "b_client_name": client.company_name,
        "pu_no_of_assists": bok_1.get("b_072_b_pu_no_of_assists") or 0,
        "de_no_of_assists": bok_1.get("b_073_b_del_no_of_assists") or 0,
        "b_booking_project": None,
    }

    booking_lines = []
    for bok_2 in bok_2s:
        _bok_2 = bok_2["booking_line"]
        e_type_of_packaging = "Carton"
        booking_line = {
            "pk_lines_id": "1",
            "e_type_of_packaging": e_type_of_packaging,
            "fk_booking_id": bok_1["pk_header_id"],
            "e_qty": _bok_2["l_002_qty"],
            "e_item": "initial_item",
            "e_dimUOM": _bok_2["l_004_dim_UOM"],
            "e_dimLength": _bok_2["l_005_dim_length"],
            "e_dimWidth": _bok_2["l_006_dim_width"],
            "e_dimHeight": _bok_2["l_007_dim_height"],
            "e_weightUOM": _bok_2["l_008_weight_UOM"],
            "e_weightPerEach": _bok_2["l_009_weight_per_each"],
            "packed_status": BOK_2_lines.ORIGINAL,
        }
        booking_lines.append(booking_line)

    _, success, message, quote_set = pricing_oper(
        body={"booking": booking, "booking_lines": booking_lines},
        booking_id=None,
        is_pricing_only=True,
    )
    logger.info(
        f"#519 {LOG_ID} Pricing result: success: {success}, message: {message}, results cnt: {quote_set}"
    )

    # Select best quotes(fastest, lowest)
    if quote_set.count() > 0:
        best_quotes = select_best_options(pricings=quote_set)
        logger.info(f"#520 {LOG_ID} Selected Best Pricings: {best_quotes}")

        context = {"client_customer_mark_up": client.client_customer_mark_up}
        json_results = SimpleQuoteSerializer(
            best_quotes, many=True, context=context
        ).data
        json_results = dme_time_lib.beautify_eta(json_results, best_quotes, client)

        # delete quotes
        quote_set.delete()

    # Set Express or Standard
    if len(json_results) == 1:
        json_results[0]["service_name"] = "Standard"
        eta = f"{int(json_results[0]['eta'].split(' ')[0]) + 3} days"
        json_results[0]["eta"] = eta
    elif len(json_results) > 1:
        if float(json_results[0]["cost"]) > float(json_results[1]["cost"]):
            json_results[0]["service_name"] = "Express"
            json_results[1]["service_name"] = "Standard"

            if json_results[0]["eta"] == json_results[1]["eta"]:
                eta = f"{int(json_results[1]['eta'].split(' ')[0]) + 3} days"
                json_results[1]["eta"] = eta

            # json_results = [json_results[0], json_results[1]]
        else:
            json_results[1]["service_name"] = "Express"
            json_results[0]["service_name"] = "Standard"

            if json_results[0]["eta"] == json_results[1]["eta"]:
                eta = f"{int(json_results[0]['eta'].split(' ')[0]) + 3} days"
                json_results[0]["eta"] = eta

            json_results = [json_results[1], json_results[0]]

    if json_results:
        logger.info(f"@818 {LOG_ID} Success!")
        return json_results
    else:
        logger.info(f"@819 {LOG_ID} Failure!")
        return json_results


@background
def quoting_in_bg(client, username, bok_1_obj, bok_1, bok_2s, old_quote):
    LOG_ID = "[ABERDEEN QUOTING IN BG]"

    # create status history
    status_history.create_4_bok(
        bok_1["pk_header_id"], "Imported / Integrated", username
    )

    # PU avail
    pu_avil = datetime.strptime(bok_1["b_021_b_pu_avail_from_date"], "%Y-%m-%d")

    booking = {
        "pk_booking_id": bok_1["pk_header_id"],
        "puPickUpAvailFrom_Date": pu_avil.date(),
        "b_clientReference_RA_Numbers": bok_1["b_000_1_b_clientreference_ra_numbers"],
        "puCompany": bok_1["b_028_b_pu_company"],
        "pu_Contact_F_L_Name": bok_1["b_035_b_pu_contact_full_name"],
        "pu_Email": bok_1["b_037_b_pu_email"],
        "pu_Phone_Main": bok_1["b_038_b_pu_phone_main"],
        "pu_Address_Street_1": bok_1["b_029_b_pu_address_street_1"],
        "pu_Address_street_2": bok_1["b_030_b_pu_address_street_2"],
        "pu_Address_Country": bok_1["b_034_b_pu_address_country"],
        "pu_Address_PostalCode": bok_1["b_033_b_pu_address_postalcode"],
        "pu_Address_State": bok_1["b_031_b_pu_address_state"],
        "pu_Address_Suburb": bok_1["b_032_b_pu_address_suburb"],
        "deToCompanyName": bok_1["b_054_b_del_company"],
        "de_to_Contact_F_LName": bok_1["b_061_b_del_contact_full_name"],
        "de_Email": bok_1["b_063_b_del_email"],
        "de_to_Phone_Main": bok_1["b_064_b_del_phone_main"],
        "de_To_Address_Street_1": bok_1["b_055_b_del_address_street_1"],
        "de_To_Address_Street_2": bok_1["b_056_b_del_address_street_2"],
        "de_To_Address_Country": bok_1["b_060_b_del_address_country"],
        "de_To_Address_PostalCode": bok_1["b_059_b_del_address_postalcode"],
        "de_To_Address_State": bok_1["b_057_b_del_address_state"],
        "de_To_Address_Suburb": bok_1["b_058_b_del_address_suburb"],
        "pu_Address_Type": "business",
        "de_To_AddressType": "residential",
        "b_booking_tail_lift_pickup": False,
        "b_booking_tail_lift_deliver": False,
        "client_warehouse_code": bok_1["b_client_warehouse_code"],
        "kf_client_id": bok_1["fk_client_id"],
        "b_client_name": client.company_name,
        "pu_no_of_assists": bok_1.get("b_072_b_pu_no_of_assists") or 0,
        "de_no_of_assists": bok_1.get("b_073_b_del_no_of_assists") or 0,
        "b_booking_project": None,
    }

    booking_lines = []
    for bok_2 in bok_2s:
        _bok_2 = bok_2["booking_line"]

        if not _bok_2.get("fk_header_id"):
            continue

        package_type = _bok_2["l_001_type_of_packaging"]
        bok_2_line = {
            "pk_lines_id": _bok_2["fk_header_id"],
            "fk_booking_id": _bok_2["fk_header_id"],
            "e_type_of_packaging": get_package_type(package_type),
            "e_qty": int(_bok_2["l_002_qty"]),
            "e_item": _bok_2["l_003_item"],
            "e_dimUOM": _bok_2["l_004_dim_UOM"],
            "e_dimLength": float(_bok_2["l_005_dim_length"]),
            "e_dimWidth": float(_bok_2["l_006_dim_width"]),
            "e_dimHeight": float(_bok_2["l_007_dim_height"]),
            "e_weightUOM": _bok_2["l_008_weight_UOM"],
            "e_weightPerEach": float(_bok_2["l_009_weight_per_each"]),
            "packed_status": _bok_2["b_093_packed_status"],
        }
        booking_lines.append(bok_2_line)

    # fc_log, _ = FC_Log.objects.get_or_create(
    #     client_booking_id=bok_1["client_booking_id"],
    #     old_quote__isnull=True,
    #     new_quote__isnull=True,
    # )
    # fc_log.old_quote = old_quote
    body = {"booking": booking, "booking_lines": booking_lines}
    _, success, message, quotes, client = pricing_oper(
        body=body,
        booking_id=None,
        is_pricing_only=True,
    )
    logger.info(
        f"#519 {LOG_ID} Pricing result: success: {success}, message: {message}, results cnt: {len(quotes)}"
    )

    # Filter qutoes
    _quotes = []
    for quote in quotes:
        if quote.freight_provider == "Direct Freight":
            _quotes.append(quote)
            break
    quotes = _quotes or quotes

    # Select best quotes(fastest, lowest)
    if quotes:
        auto_select_pricing_4_bok(bok_1_obj, quotes)
        best_quotes = select_best_options(pricings=quotes)
        logger.info(f"#520 {LOG_ID} Selected Best Pricings: {best_quotes}")
        best_quote = best_quotes[0]
        bok_1_obj.b_003_b_service_name = best_quote.service_name
        bok_1_obj.b_001_b_freight_provider = best_quote.freight_provider
        # fc_log.new_quote = best_quotes[0]
        # fc_log.save()
    elif bok_1.get("b_client_order_num"):
        message = f"#521 {LOG_ID} No Pricing results to select - BOK_1 pk_header_id: {bok_1['pk_header_id']}\nOrder Number: {bok_1['b_client_order_num']}"
        logger.error(message)
        send_email_to_admins("No FC result", message)

    # Update success to map booking
    bok_1_obj.bok_2s().update(success=dme_constants.BOK_SUCCESS_4)
    bok_1_obj.success = dme_constants.BOK_SUCCESS_4
    bok_1_obj.save()


@background
def send_error_to_aberdeen_paper(errors, payload):
    try:
        from api.outputs.email import send_email

        # Send email to Aberdeen Paper
        try:
            b_client_order_num = payload["booking"].get("b_client_order_num", "")
        except:
            b_client_order_num = ""

        subject = f"Aberdeen Paper | {b_client_order_num}"
        message = f"Hi Kamilian, \nOrder({b_client_order_num}) got following issues while pushing. \n\nErrors:"

        for error in errors:
            message += f"\n{error}"

        to_emails = ["care@deliver-me.com.au", "info@aberdenpaper.com.au"]
        # to_emails = ["goldj@deliverme.com.au"]
        cc_emails = ["dme_errorlogs@deliver-me.com.au", "dev.deliverme@gmail.com"]
        send_email(to_emails, cc_emails, [], subject, message)
    except Exception as e:
        logger.error(f"Got error while sending email: {e}")


def push_boks(payload, client, username, method):
    """
        PUSH api (bok_1, bok_2, bok_3)

        Sample payload:
        {
            "booking": {
                "client_booking_id": "RT989duW87daDf34644fAs1cXf1Af1sdf31saf3aF1asf3aF1dsiU15965973010",
                "b_055_b_del_address_street_1": "MELBOURNE PARK",
                "b_056_b_del_address_street_2": "RLA/MCA LOADING DOCK",
                "b_057_b_del_address_state": "MELBOURNE",
                "b_058_b_del_address_suburb": "VIC",
                "b_059_b_del_address_postalcode": "3000",
                "b_060_b_del_address_country": "australia",
                "b_061_b_del_contact_full_name": "John Doe",
                "b_063_b_del_email": "pdavenport@delawarenorth.com",
                "b_064_b_del_phone_main": "024111222",
                "b_066_b_del_communicate_via": "Email"
            },
            "booking_lines": [
            {
                "booking_line": {
                    "l_009_weight_per_each": 6,
                    "l_003_item": "Star Mini Pull Out Kitchen Mixer Brushed Bronze Gold",
                    "l_004_dim_UOM": "cm",
                    "l_002_qty": 1,
                    "l_001_type_of_packaging": "Carton",
                    "l_005_dim_length": 35,
                    "l_006_dim_width": 68,
                    "l_007_dim_height": 10,
                    "l_008_weight_UOM": "kg",
                    "b_097_e_bin_number": "A1 (10 | 11)",
                }
            },
            {
                "booking_line": {
                    "l_009_weight_per_each": 5,
                    "l_003_item": "Ovia Milan Wall Basin Bath Mixer with 180mm Spout Brushed Gold",
                    "l_004_dim_UOM": "cm",
                    "l_002_qty": 3,
                    "l_001_type_of_packaging": "Carton",
                    "l_005_dim_length": 50,
                    "l_006_dim_width": 50,
                    "l_007_dim_height": 10,
                    "l_008_weight_UOM": "kg",
                    "b_097_e_bin_number": "A1 (10 | 12)",
                }
            }
        ]
    }
    """
    LOG_ID = "[PUSH FROM ABP]"
    errors = []

    if "booking" not in payload:
        message = f"'booking' property is required."
        logger.info(f"{LOG_ID} {message}")
        errors.append(message)
        send_error_to_aberdeen_paper(errors, payload)
        raise Exception(errors[0])

    bok_1 = payload["booking"]
    bok_1["pk_header_id"] = str(uuid.uuid4())
    bok_2s = payload["booking_lines"]
    client_name = None
    message = None
    old_quote = None
    best_quotes = None
    json_results = []

    warehouse = get_warehouse(client, "ABP_SUNSHINE")
    b_client_order_num = bok_1.get("b_client_order_num")

    # Check required fields
    if not bok_1.get("shipping_type"):
        message = "Shipping Type ('shipping_type') is required."
        errors.append(message)
    if bok_1.get("shipping_type") and len(bok_1.get("shipping_type")) != 4:
        message = "Shipping Type ('shipping_type') is not valid. "
        errors.append(message)
    if not b_client_order_num:
        message = "Client Order Number ('b_client_order_num') is required."
        errors.append(message)
    if not bok_1.get("b_055_b_del_address_street_1"):
        message = "Delivery Address Street 1 is required."
        errors.append(message)
    if not bok_1.get("b_057_b_del_address_state"):
        # message = "Delivery Address State is required."
        # errors.append(message)
        bok_1["b_057_b_del_address_state"] = "NO_STATE"
    if not bok_1.get("b_058_b_del_address_suburb"):
        # message = "Delivery Address Suburb is required."
        # errors.append(message)
        bok_1["b_058_b_del_address_suburb"] = "NO_SUBURB"
    if not bok_1.get("b_059_b_del_address_postalcode"):
        # message = "Delivery Address PostalCode is required."
        # errors.append(message)
        bok_1["b_059_b_del_address_postalcode"] = "NO_POSTAL"

    if message:
        logger.info(f"{LOG_ID} {message}")
        # raise ValidationError(message)

    # Check duplicated push with `b_client_order_num`
    bok_1_objs = BOK_1_headers.objects.filter(
        b_client_order_num__icontains=b_client_order_num,
    )

    push_type = (bok_1.get("push_type") or "").upper()

    if push_type == "FULFILLMENT" and not bok_1_objs.exists():
        message = f"Ignore this FULFILLMENT request. Order does not exist. {b_client_order_num}"
        logger.info(f"{LOG_ID} {message}")
        return {"success": True, "message": message}

    if bok_1_objs.exists():
        old_bok_1 = bok_1_objs.first()

        # If "sales quote" request, then clear all existing information
        # If `success` code is 1 or 4, then ignore push
        if int(old_bok_1.success) != 1:
            pk_header_id = bok_1_objs.first().pk_header_id
            old_bok_2s = BOK_2_lines.objects.filter(fk_header_id=pk_header_id)
            old_bok_3s = BOK_3_lines_data.objects.filter(fk_header_id=pk_header_id)
            old_bok_1.delete()
            old_bok_2s.delete()
            old_bok_3s.delete()
            old_quote = old_bok_1.quote
        elif int(old_bok_1.success) == 1 and push_type != "FULFILLMENT":
            from api.clients.operations.index import get_next_version_order_num

            bookings = Bookings.objects.filter(
                b_client_order_num__icontains=b_client_order_num
            )
            for booking in bookings:
                booking.b_client_order_num = get_next_version_order_num(
                    booking.b_client_order_num
                )
                booking.b_clientReference_RA_Numbers = booking.b_client_order_num
                booking.save()
            for bok_1_obj in bok_1_objs:
                bok_1_obj.b_client_order_num = get_next_version_order_num(
                    bok_1_obj.b_client_order_num
                )
                bok_1_obj.b_000_1_b_clientReference_RA_Numbers = (
                    bok_1_obj.b_client_order_num
                )
                bok_1_obj.save()
        elif push_type == "FULFILLMENT":
            # Fulfilment process
            bookings = Bookings.objects.filter(
                b_client_name=client.company_name,
                b_client_order_num=b_client_order_num,
            )

            if not bookings:
                message = f"Could not find the booking with provided orderNo({b_client_order_num})"
                logger.info(f"{LOG_ID} {message}")
                raise Exception(message)

            booking = bookings.last()
            # Soft delete original lines
            deleted_scanned_lines = (
                Booking_lines.objects.filter(
                    fk_booking_id=booking.pk_booking_id,
                    packed_status="scanned",
                    is_deleted=True,
                )
                .exclude(e_bin_number="REPACK-BIN")
                .values("e_item")
            )
            deleted_scanned_lines_e_items = []
            for line in deleted_scanned_lines:
                deleted_scanned_lines_e_items.append(line["e_item"])
            Booking_lines.objects.filter(fk_booking_id=booking.pk_booking_id).exclude(
                e_bin_number="REPACK-BIN"
            ).delete()

            for bok_2 in bok_2s:
                _bok_2 = bok_2["booking_line"]
                package_type = _bok_2["l_001_type_of_packaging"]

                # Create new Lines
                new_line = Booking_lines()
                new_line.fk_booking_id = booking.pk_booking_id
                new_line.pk_booking_lines_id = str(uuid.uuid4())
                new_line.e_type_of_packaging = get_package_type(package_type)
                new_line.e_qty = math.ceil(_bok_2.get("l_002_qty"))
                new_line.e_item_type = _bok_2.get("e_item_type")
                new_line.e_item = _bok_2.get("l_003_item")[:50]
                new_line.e_bin_number = _bok_2.get("b_097_e_bin_number")
                new_line.packed_status = Booking_lines.ORIGINAL
                new_line.e_dimUOM = _bok_2.get("l_004_dim_UOM")
                new_line.e_dimLength = float(_bok_2.get("l_005_dim_length") or 0.11)
                new_line.e_dimWidth = float(_bok_2.get("l_006_dim_width") or 0.11)
                new_line.e_dimHeight = float(_bok_2.get("l_007_dim_height") or 0.11)
                new_line.e_weightUOM = _bok_2.get("l_008_weight_UOM")
                new_line.e_weightPerEach = float(
                    _bok_2.get("l_009_weight_per_each") or 5
                )
                new_line.e_Total_KG_weight = new_line.e_qty * new_line.e_weightPerEach
                new_line.save()

                if is_carton(new_line.e_type_of_packaging) or is_pallet(
                    new_line.e_type_of_packaging
                ):
                    if not new_line.e_item in deleted_scanned_lines_e_items:
                        new_line.pk = None
                        new_line.packed_status = Booking_lines.SCANNED_PACK
                        new_line.save()

            message = f"Successfully fulfilled. OrderNum: {b_client_order_num}"
            logger.info(f"{LOG_ID} {message}")
            return {"success": True, "message": "Successfully fulfilled"}

    # Generate `client_booking_id`
    client_booking_id = f"{bok_1['b_client_order_num']}_{bok_1['pk_header_id']}_{datetime.strftime(datetime.utcnow(), '%s')}"
    bok_1["client_booking_id"] = client_booking_id

    # Save bok_1
    bok_1["fk_client_id"] = client.dme_account_num
    bok_1["x_booking_Created_With"] = "DME PUSH API"
    bok_1["fk_client_warehouse"] = warehouse.pk_id_client_warehouses
    bok_1["b_clientPU_Warehouse"] = warehouse.name
    bok_1["b_client_warehouse_code"] = warehouse.client_warehouse_code
    bok_1["success"] = dme_constants.BOK_SUCCESS_3

    if not bok_1.get("b_000_1_b_clientreference_ra_numbers"):
        bok_1["b_000_1_b_clientreference_ra_numbers"] = ""

    if not bok_1.get("b_028_b_pu_company"):
        bok_1["b_028_b_pu_company"] = warehouse.name

    if not bok_1.get("b_035_b_pu_contact_full_name"):
        bok_1["b_035_b_pu_contact_full_name"] = warehouse.contact_name

    if not bok_1.get("b_037_b_pu_email"):
        bok_1["b_037_b_pu_email"] = warehouse.contact_email

    if not bok_1.get("b_038_b_pu_phone_main"):
        bok_1["b_038_b_pu_phone_main"] = warehouse.phone_main

    if not bok_1.get("b_029_b_pu_address_street_1"):
        bok_1["b_029_b_pu_address_street_1"] = warehouse.address1

    if not bok_1.get("b_030_b_pu_address_street_2"):
        bok_1["b_030_b_pu_address_street_2"] = warehouse.address2

    if not bok_1.get("b_034_b_pu_address_country"):
        bok_1["b_034_b_pu_address_country"] = "AU"

    if not bok_1.get("b_033_b_pu_address_postalcode"):
        bok_1["b_033_b_pu_address_postalcode"] = warehouse.postal_code

    if not bok_1.get("b_031_b_pu_address_state"):
        bok_1["b_031_b_pu_address_state"] = warehouse.state.upper()

    if not bok_1.get("b_032_b_pu_address_suburb"):
        bok_1["b_032_b_pu_address_suburb"] = warehouse.suburb

    if not bok_1.get("b_021_b_pu_avail_from_date"):
        next_biz_day = dme_time_lib.next_business_day(date.today(), 1)
        bok_1["b_021_b_pu_avail_from_date"] = str(next_biz_day)[:10]

    if not bok_1.get("b_064_b_del_phone_main"):
        bok_1["b_064_b_del_phone_main"] = "0289682200"

    if not bok_1.get("b_063_b_del_email"):
        bok_1["b_063_b_del_email"] = "noreply@aberdeenpaper.com"

    if not bok_1.get("b_054_b_del_company"):
        message = "Delivery Company Name is required"
        errors.append(message)

    if not bok_1.get("b_061_b_del_contact_full_name") and bok_1.get(
        "b_054_b_del_company"
    ):
        bok_1["b_061_b_del_contact_full_name"] = bok_1.get("b_054_b_del_company")

    # State and Suburb
    bok_1["b_031_b_pu_address_state"] = bok_1["b_031_b_pu_address_state"].upper()
    de_state = bok_1.get("b_057_b_del_address_state") or ""
    de_state = (de_state or "")[:20]
    de_suburb = bok_1.get("b_058_b_del_address_suburb") or ""
    de_suburb = (de_suburb or "")[:20]
    de_postal_code = bok_1.get("b_059_b_del_address_postalcode")
    de_postal_code = (de_postal_code or "")[:20]
    de_state = de_state.upper().replace(".", "").replace(",", "").strip()
    de_suburb = de_suburb.upper().replace(".", "").replace(",", "").strip()
    bok_1["b_057_b_del_address_state"] = de_state
    bok_1["b_058_b_del_address_suburb"] = de_suburb

    # Check prefix of email and phone - 'eml: ', 'tel: '
    de_email = bok_1["b_063_b_del_email"]
    if ":" in de_email:
        bok_1["b_063_b_del_email"] = de_email.split(":")[1].strip()

    de_phone = bok_1["b_064_b_del_phone_main"]
    if ":" in de_phone:
        bok_1["b_064_b_del_phone_main"] = de_phone.split(":")[1].strip()

    # Limit field length
    street_1 = bok_1.get("b_055_b_del_address_street_1") or ""
    bok_1["b_055_b_del_address_street_1"] = street_1[:40]
    street_2 = bok_1.get("b_056_b_del_address_street_2") or ""
    bok_1["b_056_b_del_address_street_2"] = street_2[:40]
    bok_1["b_061_b_del_contact_full_name"] = bok_1["b_061_b_del_contact_full_name"][:32]

    # Check address (by using Direct Freight)
    crecords = FPRouting.objects.filter(
        freight_provider=88,
        dest_suburb=de_suburb.upper(),
        dest_state=de_state.upper(),
        dest_postcode=de_postal_code,
    ).only("gateway", "onfwd", "sort_bin", "orig_depot")
    if not crecords.exists():
        from api.clients.aberdeen_paper.operations import send_email_wrong_address

        bok_1["zb_105_text_5"] = "State, PostalCode, Suburb mismatch"
        send_email_wrong_address(bok_1)

    # Check bok_2s:
    for index, bok_2 in enumerate(bok_2s):
        _bok_2 = bok_2["booking_line"]
        item = bok_2.get("l_003_item", "")

        if not _bok_2.get("l_001_type_of_packaging"):
            errors.append(f"{item} is missing type of package")
        # if not _bok_2.get("l_002_qty"):
        #     errors.append(f"{item} is missing quantity")
        if not _bok_2.get("l_004_dim_UOM"):
            errors.append(f"{item} is missing unit of dimentions")
        if not _bok_2.get("l_005_dim_length"):
            errors.append(f"{item} is missing length")
        if not _bok_2.get("l_006_dim_width"):
            errors.append(f"{item} is missing width")
        if not _bok_2.get("l_007_dim_height"):
            errors.append(f"{item} is missing height")
        if not _bok_2.get("l_008_weight_UOM"):
            errors.append(f"{item} is missing unit of weight")
        if not _bok_2.get("l_009_weight_per_each"):
            errors.append(f"{item} is missing weight")

    if errors:
        send_error_to_aberdeen_paper(errors, payload)
        raise Exception(errors[0])

    bok_1_serializer = BOK_1_Serializer(data=bok_1)
    if not bok_1_serializer.is_valid():
        message = f"Serialiser Error - {bok_1_serializer.errors}"
        errors.append(
            f"Unknown error: {bok_1_serializer.errors}\n Please contact DME Support email: dme_errorlogs@deliver-me.com.au"
        )
        send_error_to_aberdeen_paper(errors, payload)
        logger.info(f"@8821 {LOG_ID} {message}")
        raise Exception(message)

    bok_2_objs = []
    with transaction.atomic():
        # Save bok_2s
        for index, bok_2 in enumerate(bok_2s):
            _bok_2 = bok_2["booking_line"]

            if not _bok_2.get("l_002_qty") or _bok_2.get("l_002_qty") == "0":
                continue

            _bok_2["fk_header_id"] = bok_1["pk_header_id"]
            _bok_2["v_client_pk_consigment_num"] = bok_1["pk_header_id"]
            _bok_2["pk_booking_lines_id"] = str(uuid.uuid1())
            _bok_2["success"] = bok_1["success"]
            _bok_2["l_002_qty"] = math.ceil(_bok_2.get("l_002_qty"))
            l_001 = _bok_2.get("l_001_type_of_packaging")
            _bok_2["l_001_type_of_packaging"] = get_package_type(l_001)
            _bok_2["b_093_packed_status"] = BOK_2_lines.ORIGINAL
            _bok_2["b_097_e_bin_number"] = _bok_2.get("b_097_e_bin_number")

            _bok_2 = line_oper.handle_zero(_bok_2, client)
            bok_2_serializer = BOK_2_Serializer(data=_bok_2)
            if bok_2_serializer.is_valid():
                bok_2_obj = bok_2_serializer.save()
                bok_2_objs.append(bok_2_obj)
                bok_2["booking_line"]["pk_lines_id"] = bok_2_obj.pk
            else:
                message = f"Serialiser Error - {bok_2_serializer.errors}"
                errors.append(
                    f"Unknown error: {bok_2_serializer.errors}\n Please contact DME Support email: dme_errorlogs@deliver-me.com.au"
                )
                send_error_to_aberdeen_paper(errors, payload)
                logger.info(f"@8821 {LOG_ID} {message}")
                raise Exception(message)

            # Save bok_3s
            if not "booking_lines_data" in bok_2:
                continue

            bok_3s = bok_2["booking_lines_data"]
            for bok_3 in bok_3s:
                bok_3["fk_header_id"] = bok_1["pk_header_id"]
                bok_3["fk_booking_lines_id"] = _bok_2["pk_booking_lines_id"]
                bok_3["v_client_pk_consigment_num"] = bok_1["pk_header_id"]
                bok_3["success"] = bok_1["success"]

                bok_3_serializer = BOK_3_Serializer(data=bok_3)
                if bok_3_serializer.is_valid():
                    bok_3_serializer.save()
                else:
                    message = f"Serialiser Error - {bok_3_serializer.errors}"
                    logger.info(f"@8831 {LOG_ID} {message}")
                    raise Exception(message)

        bok_1_obj = bok_1_serializer.save()

    # create status history
    status_history.create_4_bok(
        bok_1["pk_header_id"], "Imported / Integrated", username
    )

    # `auto_repack` logic
    need_palletize = False
    for bok_2_obj in bok_2_objs:
        package_type = bok_2_obj.l_001_type_of_packaging.upper()
        package_type = get_package_type(package_type)

        if package_type in (ROLLS + PACKETS):
            need_palletize = True
            logger.info(
                f"@8126 {LOG_ID} Need to be Palletized! - {bok_2_obj.zbl_102_text_2}"
            )
            break

    if need_palletize:
        message = "Auto repacking..."
        logger.info(f"@8130 {LOG_ID} {message}")

        # Select suitable pallet and get required pallets count
        pallets = Pallet.objects.filter(pk=10)
        palletized, non_palletized = get_palletized_by_ai(bok_2_objs, pallets)
        logger.info(
            f"@8831 {LOG_ID} Palletized: {palletized}\nNon-Palletized: {non_palletized}"
        )

        # Create one PAL bok_2
        for item in non_palletized:  # Non Palletized
            line_obj = item["line_obj"]
            line = {}
            line["fk_header_id"] = line_obj.fk_header_id
            line["v_client_pk_consigment_num"] = line_obj.v_client_pk_consigment_num
            line["pk_booking_lines_id"] = line_obj.pk_booking_lines_id
            line["success"] = line_obj.success
            package_type = line_obj.l_001_type_of_packaging
            line["l_001_type_of_packaging"] = get_package_type(package_type)
            line["l_002_qty"] = math.ceil(item["quantity"])
            line["l_003_item"] = line_obj.l_003_item
            line["e_item_type"] = line_obj.e_item_type
            line["l_004_dim_UOM"] = line_obj.l_004_dim_UOM
            dim_list = [
                line_obj.l_005_dim_length,
                line_obj.l_006_dim_width,
                line_obj.l_007_dim_height,
            ]
            dim_list.sort()
            line["l_005_dim_length"] = dim_list[2]
            line["l_006_dim_width"] = dim_list[1]
            line["l_007_dim_height"] = dim_list[0]
            line["l_009_weight_per_each"] = line_obj.l_009_weight_per_each
            line["l_008_weight_UOM"] = line_obj.l_008_weight_UOM
            line["is_deleted"] = False
            line["b_093_packed_status"] = BOK_2_lines.AUTO_PACK
            bok_2_serializer = BOK_2_Serializer(data=line)
            if bok_2_serializer.is_valid():
                bok_2_serializer.save()
            else:
                message = f"Serialiser Error - {bok_2_serializer.errors}"
                errors.append(
                    f"Unknown error: {bok_2_serializer.errors}\n Please contact DME Support email: dme_errorlogs@deliver-me.com.au"
                )
                send_error_to_aberdeen_paper(errors, payload)
                logger.info(f"@8135 {LOG_ID} {message}")
                raise Exception(message)
            bok_2s.append({"booking_line": line})

        for palletized_item in palletized:  # Palletized
            pallet = pallets[palletized_item["pallet_index"]]

            total_weight = 0
            for _iter in palletized_item["lines"]:
                line_in_pallet = _iter["line_obj"]
                total_weight += (
                    line_in_pallet.l_009_weight_per_each
                    * _iter["quantity"]
                    / palletized_item["quantity"]
                )

            new_line = {}
            new_line["fk_header_id"] = bok_1["pk_header_id"]
            new_line["v_client_pk_consigment_num"] = bok_1["pk_header_id"]
            new_line["pk_booking_lines_id"] = str(uuid.uuid1())
            new_line["success"] = bok_1["success"]
            new_line["l_001_type_of_packaging"] = "Pallet"
            new_line["l_002_qty"] = math.ceil(palletized_item["quantity"])
            new_line["l_003_item"] = "Auto repacked item"
            new_line["l_004_dim_UOM"] = "mm"
            new_line["l_005_dim_length"] = pallet.length
            new_line["l_006_dim_width"] = pallet.width
            new_line["l_007_dim_height"] = palletized_item["packed_height"] * 1000
            new_line["l_009_weight_per_each"] = total_weight
            new_line["l_008_weight_UOM"] = "KG"
            new_line["is_deleted"] = False
            new_line["b_093_packed_status"] = BOK_2_lines.AUTO_PACK

            bok_2_serializer = BOK_2_Serializer(data=new_line)
            if bok_2_serializer.is_valid():
                # Create Bok_3s
                for _iter in palletized_item["lines"]:
                    line = _iter["line_obj"]  # line_in_pallet
                    bok_3 = {}
                    bok_3["fk_header_id"] = bok_1["pk_header_id"]
                    bok_3["v_client_pk_consigment_num"] = bok_1["pk_header_id"]
                    bok_3["fk_booking_lines_id"] = new_line["pk_booking_lines_id"]
                    bok_3["success"] = line.success
                    bok_3[
                        "ld_005_item_serial_number"
                    ] = line.zbl_131_decimal_1  # Sequence
                    bok_3["ld_001_qty"] = math.ceil(line.l_002_qty)
                    bok_3["ld_003_item_description"] = line.l_003_item
                    bok_3["ld_002_model_number"] = line.e_item_type
                    bok_3["zbld_121_integer_1"] = line.zbl_131_decimal_1  # Sequence
                    bok_3["zbld_122_integer_2"] = _iter["quantity"]
                    bok_3["zbld_131_decimal_1"] = line.l_005_dim_length
                    bok_3["zbld_132_decimal_2"] = line.l_006_dim_width
                    bok_3["zbld_133_decimal_3"] = line.l_007_dim_height
                    bok_3["zbld_134_decimal_4"] = round(line.l_009_weight_per_each, 2)
                    bok_3["zbld_101_text_1"] = line.l_004_dim_UOM
                    bok_3["zbld_102_text_2"] = line.l_008_weight_UOM
                    bok_3["zbld_103_text_3"] = line.e_item_type
                    bok_3["zbld_104_text_4"] = line.l_001_type_of_packaging
                    bok_3["zbld_105_text_5"] = line.l_003_item

                    bok_3_serializer = BOK_3_Serializer(data=bok_3)
                    if bok_3_serializer.is_valid():
                        bok_3_serializer.save()
                    else:
                        message = f"Serialiser Error - {bok_3_serializer.errors}"
                        logger.info(f"@8134 {LOG_ID} {message}")
                        raise Exception(message)

                bok_2_serializer.save()
                bok_2s.append({"booking_line": new_line})
            else:
                message = f"Serialiser Error - {bok_2_serializer.errors}"
                errors.append(
                    f"Unknown error: {bok_2_serializer.errors}\n Please contact DME Support email: dme_errorlogs@deliver-me.com.au"
                )
                send_error_to_aberdeen_paper(errors, payload)
                logger.info(f"@8135 {LOG_ID} {message}")
                raise Exception(message)

        # Set `auto_repack` flag
        bok_1_obj.b_081_b_pu_auto_pack = True
        bok_1_obj.zb_104_text_4 = "In Progress"
        bok_1_obj.save()

    # Fast response for sapb1
    quoting_in_bg(client, username, bok_1_obj, bok_1, bok_2s, old_quote)

    url = f"{settings.WEB_SITE_URL}/price/{bok_1['client_booking_id']}/"
    result = {"success": True, "results": [], "pricePageUrl": url}
    logger.info(f"@8838 {LOG_ID} success: True, 201_created")
    return result

    # # PU avail
    # pu_avil = datetime.strptime(bok_1["b_021_b_pu_avail_from_date"], "%Y-%m-%d")

    # booking = {
    #     "pk_booking_id": bok_1["pk_header_id"],
    #     "puPickUpAvailFrom_Date": pu_avil.date(),
    #     "b_clientReference_RA_Numbers": bok_1["b_000_1_b_clientreference_ra_numbers"],
    #     "puCompany": bok_1["b_028_b_pu_company"],
    #     "pu_Contact_F_L_Name": bok_1["b_035_b_pu_contact_full_name"],
    #     "pu_Email": bok_1["b_037_b_pu_email"],
    #     "pu_Phone_Main": bok_1["b_038_b_pu_phone_main"],
    #     "pu_Address_Street_1": bok_1["b_029_b_pu_address_street_1"],
    #     "pu_Address_street_2": bok_1["b_030_b_pu_address_street_2"],
    #     "pu_Address_Country": bok_1["b_034_b_pu_address_country"],
    #     "pu_Address_PostalCode": bok_1["b_033_b_pu_address_postalcode"],
    #     "pu_Address_State": bok_1["b_031_b_pu_address_state"],
    #     "pu_Address_Suburb": bok_1["b_032_b_pu_address_suburb"],
    #     "deToCompanyName": bok_1["b_054_b_del_company"],
    #     "de_to_Contact_F_LName": bok_1["b_061_b_del_contact_full_name"],
    #     "de_Email": bok_1["b_063_b_del_email"],
    #     "de_to_Phone_Main": bok_1["b_064_b_del_phone_main"],
    #     "de_To_Address_Street_1": bok_1["b_055_b_del_address_street_1"],
    #     "de_To_Address_Street_2": bok_1["b_056_b_del_address_street_2"],
    #     "de_To_Address_Country": bok_1["b_060_b_del_address_country"],
    #     "de_To_Address_PostalCode": bok_1["b_059_b_del_address_postalcode"],
    #     "de_To_Address_State": bok_1["b_057_b_del_address_state"],
    #     "de_To_Address_Suburb": bok_1["b_058_b_del_address_suburb"],
    #     "pu_Address_Type": "business",
    #     "de_To_AddressType": "residential",
    #     "b_booking_tail_lift_pickup": False,
    #     "b_booking_tail_lift_deliver": False,
    #     "client_warehouse_code": bok_1["b_client_warehouse_code"],
    #     "kf_client_id": bok_1["fk_client_id"],
    #     "b_client_name": client.company_name,
    #     "pu_no_of_assists": bok_1.get("b_072_b_pu_no_of_assists") or 0,
    #     "de_no_of_assists": bok_1.get("b_073_b_del_no_of_assists") or 0,
    #     "b_booking_project": None,
    # }

    # booking_lines = []
    # for bok_2 in bok_2s:
    #     _bok_2 = bok_2["booking_line"]
    #     bok_2_line = {
    #         "pk_lines_id": _bok_2["pk_lines_id"],
    #         "fk_booking_id": _bok_2["fk_header_id"],
    #         "e_type_of_packaging": _bok_2["l_001_type_of_packaging"],
    #         "e_qty": _bok_2["l_002_qty"],
    #         "e_item": _bok_2["l_003_item"],
    #         "e_dimUOM": _bok_2["l_004_dim_UOM"],
    #         "e_dimLength": _bok_2["l_005_dim_length"],
    #         "e_dimWidth": _bok_2["l_006_dim_width"],
    #         "e_dimHeight": _bok_2["l_007_dim_height"],
    #         "e_weightUOM": _bok_2["l_008_weight_UOM"],
    #         "e_weightPerEach": _bok_2["l_009_weight_per_each"],
    #         "packed_status": _bok_2["b_093_packed_status"],
    #     }
    #     booking_lines.append(bok_2_line)

    # fc_log, _ = FC_Log.objects.get_or_create(
    #     client_booking_id=bok_1["client_booking_id"],
    #     old_quote__isnull=True,
    #     new_quote__isnull=True,
    # )
    # fc_log.old_quote = old_quote
    # body = {"booking": booking, "booking_lines": booking_lines}
    # _, success, message, quotes, client = pricing_oper(
    #     body=body,
    #     booking_id=None,
    #     is_pricing_only=True,
    #     packed_statuses=[Booking_lines.ORIGINAL, Booking_lines.AUTO_PACK],
    # )
    # logger.info(
    #     f"#519 {LOG_ID} - Pricing result: success: {success}, message: {message}, results cnt: {len(quotes)}"
    # )

    # # Select best quotes(fastest, lowest)
    # if quotes:
    #     auto_select_pricing_4_bok(
    #         bok_1=bok_1_obj,
    #         pricings=quotes,
    #         is_from_script=False,
    #         auto_select_type=1,
    #         client=client,
    #     )

    #     if len(quotes):
    #         best_quotes = select_best_options(pricings=quotes, client=client)
    #     else:
    #         best_quotes = quotes

    #     logger.info(f"#520 {LOG_ID} Selected Best Pricings: {best_quotes}")

    #     if len(best_quotes) > 0:
    #         context = {"client_customer_mark_up": client.client_customer_mark_up}
    #         json_results = Simple4ProntoQuoteSerializer(
    #             best_quotes, many=True, context=context
    #         ).data
    #         json_results = dme_time_lib.beautify_eta(json_results, best_quotes, client)

    #         # if bok_1["success"] == dme_constants.BOK_SUCCESS_4:
    #         best_quote = best_quotes[0]
    #         bok_1_obj.b_003_b_service_name = best_quote.service_name
    #         bok_1_obj.b_001_b_freight_provider = best_quote.freight_provider
    #         bok_1_obj.b_002_b_vehicle_type = (
    #             best_quote.vehicle.description if best_quote.vehicle else None
    #         )
    #         bok_1_obj.save()
    #         fc_log.new_quote = best_quotes[0]
    #         fc_log.save()

    # # Set Express or Standard
    # if len(json_results) == 1:
    #     json_results[0]["service_name"] = "Standard"
    # elif len(json_results) > 1:
    #     if float(json_results[0]["cost"]) > float(json_results[1]["cost"]):
    #         json_results[0]["service_name"] = "Express"
    #         json_results[1]["service_name"] = "Standard"

    #         if json_results[0]["eta"] == json_results[1]["eta"]:
    #             eta = f"{int(json_results[1]['eta'].split(' ')[0]) + 1} days"
    #             json_results[1]["eta"] = eta

    #         json_results = [json_results[1], json_results[0]]
    #     else:
    #         json_results[1]["service_name"] = "Express"
    #         json_results[0]["service_name"] = "Standard"

    #         if json_results[0]["eta"] == json_results[1]["eta"]:
    #             eta = f"{int(json_results[0]['eta'].split(' ')[0]) + 1} days"
    #             json_results[0]["eta"] = eta

    # # Response
    # if json_results or not bok_1["shipping_type"]:
    #     logger.info(f"@8838 {LOG_ID} success: True, 201_created")
    #     result = {"success": True, "results": json_results}
    #     url = f"{settings.WEB_SITE_URL}/price/{bok_1['client_booking_id']}/"
    #     result["pricePageUrl"] = url
    #     return result
    # else:
    #     # Inform to admins
    #     message = f"#521 {LOG_ID} No Pricing results to select - BOK_1 pk_header_id: {bok_1['pk_header_id']}\nOrder Number: {bok_1['b_client_order_num']}"
    #     logger.error(message)
    #     # send_email_to_admins("No FC result", message)

    #     message = (
    #         "Pricing cannot be returned due to incorrect address/lines information."
    #     )
    #     logger.info(f"@8839 {LOG_ID} {message}")
    #     url = f"{settings.WEB_SITE_URL}/price/{bok_1['client_booking_id']}/"

    #     result = {"success": True, "results": json_results}
    #     result["pricePageUrl"] = url
    #     logger.info(f"@8837 {LOG_ID} success: True, 201_created")
    #     return result


# @background
def scan_process_in_bg(booking):
    LOG_ID = "[SCAN IN BG]"
    # Should get pricing again when if fully picked
    next_biz_day = dme_time_lib.next_business_day(date.today(), 1)
    booking.puPickUpAvailFrom_Date = str(next_biz_day)[:10]
    booking.save()

    # new_fc_log = FC_Log.objects.create(
    #     client_booking_id=booking.b_client_booking_ref_num,
    #     old_quote=booking.api_booking_quote,
    # )
    # new_fc_log.save()
    logger.info(
        f"#371 {LOG_ID} - Picked all items: {booking.b_bookingID_Visual}, now getting Quotes again..."
    )
    _, success, message, quotes = pricing_oper(
        body=None,
        booking_id=booking.pk,
        is_pricing_only=False,
        packed_statuses=[Booking_lines.SCANNED_PACK],
    )
    logger.info(
        f"#372 {LOG_ID} - Pricing result: success: {success}, message: {message}, results cnt: {quotes.count()}"
    )

    # Select best quotes(fastest, lowest)
    if quotes.exists() and quotes.count() > 0:
        quotes = quotes.filter(
            freight_provider__iexact=booking.vx_freight_provider,
            service_name=booking.vx_serviceName,
            packed_status=Booking_lines.SCANNED_PACK,
        )
        best_quotes = select_best_options(pricings=quotes)
        logger.info(f"#373 {LOG_ID} - Selected Best Pricings: {best_quotes}")

        if best_quotes:
            set_booking_quote(booking, best_quotes[0])
            # new_fc_log.new_quote = booking.api_booking_quote
            # new_fc_log.save()
        else:
            set_booking_quote(booking, None)

    status_history.create(booking, "Ready for Booking", "Aberdeen Paper")
    booking.save()

    success, message = book_oper(booking.vx_freight_provider, booking, "DME_API")

    if not success:
        error_msg = f"#374 {LOG_ID} - HUNTER order BOOK falied. Booking Id: {booking.b_bookingID_Visual}, message: {message}"
        logger.error(error_msg)
        send_email_to_admins(f"ABP {LOG_ID}", f"{error_msg}")
        message = "Please contact DME support center. <bookings@deliver-me.com.au>"
        raise Exception(message)


def scanned(payload, client):
    """
    called as get_label

    request when item(s) is picked(scanned) at warehouse
    should response LABEL if payload is correct
    """
    LOG_ID = "[SCANNED ABP]"
    b_client_order_num = payload.get("HostOrderNumber")
    picked_items = payload.get("picked_items")

    # Deactivated 2021-10-07
    # return {"success": False, "message": "Temporary unavailable"}

    # Check required params are included
    if not b_client_order_num:
        message = "'HostOrderNumber' is required."
        raise ValidationError(message)

    if not picked_items:
        message = "'picked_items' is required."
        raise ValidationError(message)

    # Check if Order exists on Bookings table
    booking = (
        Bookings.objects.select_related("api_booking_quote")
        .filter(
            b_client_name=client.company_name, b_client_order_num=b_client_order_num[5:]
        )
        .first()
    )

    if not booking:
        message = "Order does not exist. 'HostOrderNumber' is invalid."
        raise ValidationError(message)

    # If Order exists
    pk_booking_id = booking.pk_booking_id
    lines = Booking_lines.objects.filter(fk_booking_id=pk_booking_id)
    line_datas = Booking_lines_data.objects.filter(fk_booking_id=pk_booking_id)

    original_items, scanned_items, sscc_list, model_number_qtys = [], [], [], []
    for line in lines:
        if line.packed_status == Booking_lines.ORIGINAL:
            original_items.append(line)
            model_number_qtys.append((line.e_item_type, line.e_qty))

        if line.sscc and line.e_item == "Picked Item":
            scanned_items.append(line)
            sscc_list.append(line.sscc)

    logger.info(f"@360 {LOG_ID} Booking: {booking}")
    logger.info(f"@361 {LOG_ID} Lines: {lines}")
    logger.info(f"@362 {LOG_ID} original_items: {original_items}")
    logger.info(f"@363 {LOG_ID} scanned_items: {scanned_items}")
    logger.info(f"@364 {LOG_ID} model_number and qty(s): {model_number_qtys}")
    logger.info(f"@365 {LOG_ID} sscc(s): {sscc_list}")

    """
        Deactivated on 2022-11-22
            * No double scan from ACR
            * ACR reprint label when required
    """
    # # Delete existing ssccs(for scanned ones)
    # picked_ssccs = []
    # for picked_item in picked_items:
    #     picked_ssccs.append(picked_item["sscc"])
    # if picked_ssccs:
    #     Booking_lines.objects.filter(sscc__in=picked_ssccs).delete()

    # # Get scanned items again for sequence of label
    # lines = Booking_lines.objects.filter(fk_booking_id=pk_booking_id)
    # scanned_items = lines.filter(sscc__isnull=False, e_item="Picked Item")

    # Validation
    invalid_model_numbers = []
    invalid_sscc_list = []
    for picked_item in picked_items:
        # Check `sscc` is provided
        if not "sscc" in picked_item:
            message = f"There is an item which doesn`t have 'sscc' information. Invalid item: {json.dumps(picked_item)}"
            raise ValidationError(message)

        # Validate repacked items
        if (
            "is_repacked" in picked_item
            and "items" in picked_item
            and picked_item["items"]
        ):
            repack_type = None

            for item in picked_item["items"]:
                # Get and check repack_type
                if "model_number" in item and not repack_type:
                    repack_type = "model_number"

                if "sscc" in item and not repack_type:
                    repack_type = "sscc"

                # Invalid sscc check
                if repack_type == "sscc" and not item["sscc"] in sscc_list:
                    invalid_sscc_list.append(item["sscc"])

                # Check qty
                if repack_type == "model_number":
                    if not "qty" in item:
                        message = f"Qty is required. Invalid item: {json.dumps(item)}"
                        raise ValidationError(message)
                    elif "qty" in item and not item["qty"]:
                        message = f"Qty should bigger than 0. Invalid item: {json.dumps(item)}"
                        raise ValidationError(message)

                # Accumulate invalid_model_numbers
                if "model_number" in item:
                    is_valid = False

                    for model_number_qty in model_number_qtys:
                        if model_number_qty[0] == item["model_number"]:
                            is_valid = True

                    if not is_valid:
                        invalid_model_numbers.append(item["model_number"])

                # Invalid repack_type (which has both 'sscc' and 'model_number')
                if ("model_number" in item and repack_type == "sscc") or (
                    "sscc" in item and repack_type == "model_number"
                ):
                    message = f"Can not repack 'model_number' and 'sscc'."
                    raise ValidationError(message)

                # Invalid repack_type (which doesn't have both 'sscc' and 'model_number')
                if not "model_number" in item and not "sscc" in item:
                    message = f"There is an item which does not have 'model_number' information. Invalid item: {json.dumps(item)}"
                    raise ValidationError(message)
        else:
            message = f"There is an invalid item: {json.dumps(picked_item)}"
            raise ValidationError(message)

    if invalid_sscc_list:
        message = (
            f"This order doesn't have given sscc(s): {', '.join(invalid_sscc_list)}"
        )
        raise ValidationError(message)

    if invalid_model_numbers:
        message = f"'{', '.join(invalid_model_numbers)}' are invalid model_numbers for this order."
        raise ValidationError(message)

    # Check over picked items
    over_picked_items = []
    estimated_picked = {}
    is_picked_all = True

    for model_number_qty in model_number_qtys:
        estimated_picked[model_number_qty[0]] = 0

    for scanned_item in scanned_items:
        for line_data in line_datas:
            if (
                line_data.fk_booking_lines_id == scanned_item.pk_booking_lines_id
                and line_data.itemDescription != "Repacked at warehouse"
            ):
                estimated_picked[line_data.modelNumber] += line_data.quantity

    if repack_type == "model_number":
        for picked_item in picked_items:
            for item in picked_item["items"]:
                estimated_picked[item["model_number"]] += item["qty"]

    logger.info(
        f"@366 {LOG_ID} checking over picked - limit: {model_number_qtys}, estimated: {estimated_picked}"
    )

    for item in estimated_picked:
        for model_number_qty in model_number_qtys:
            if (
                item == model_number_qty[0]
                and estimated_picked[item] > model_number_qty[1]
            ):
                over_picked_items.append(model_number_qty[0])

            if (
                item == model_number_qty[0]
                and estimated_picked[item] != model_number_qty[1]
            ):
                is_picked_all = False

    # # If found over picked items
    # if over_picked_items:
    #     logger.error(
    #         f"@367 {LOG_ID} over picked! - limit: {model_number_qtys}, estimated: {estimated_picked}"
    #     )
    #     message = f"There are over picked items: {', '.join(over_picked_items)}"
    #     raise ValidationError(message)

    # Save
    try:
        labels = []
        new_sscc_list = []
        new_sscc_lines = {}

        with transaction.atomic():
            for picked_item in picked_items:
                # Find source line
                old_line = None
                first_item = picked_item["items"][0]

                for original_item in original_items:
                    if (
                        repack_type == "model_number"
                        and original_item.e_item_type == first_item["model_number"]
                    ):
                        old_line = original_item
                    elif (
                        repack_type == "sscc"
                        and original_item.sscc == first_item["sscc"]
                    ):
                        old_line = original_item

                # Create new Lines
                new_line = Booking_lines()
                new_line.fk_booking_id = pk_booking_id
                new_line.pk_booking_lines_id = str(uuid.uuid4())
                package_type = picked_item.get("package_type")
                new_line.e_type_of_packaging = get_package_type(package_type)
                new_line.e_qty = 1
                new_line.e_item = (
                    "Picked Item" if repack_type == "model_number" else "Repacked Item"
                )
                new_line.packed_status = Booking_lines.SCANNED_PACK

                if picked_item.get("dimensions"):
                    new_line.e_dimUOM = picked_item["dimensions"]["unit"]
                    new_line.e_dimLength = picked_item["dimensions"]["length"]
                    new_line.e_dimWidth = picked_item["dimensions"]["width"]
                    new_line.e_dimHeight = picked_item["dimensions"]["height"]
                else:
                    new_line.e_dimUOM = old_line.e_dimUOM
                    new_line.e_dimLength = old_line.e_dimLength
                    new_line.e_dimWidth = old_line.e_dimWidth
                    new_line.e_dimHeight = old_line.e_dimHeight
                    new_line.e_qty = old_line.e_qty

                if picked_item.get("weight"):
                    new_line.e_weightUOM = picked_item["weight"]["unit"]
                    new_line.e_weightPerEach = picked_item["weight"]["weight"]
                    new_line.e_Total_KG_weight = (
                        picked_item["weight"]["weight"] * new_line.e_qty
                    )
                else:
                    new_line.e_weightUOM = old_line.e_weightUOM
                    new_line.e_weightPerEach = old_line.e_weightPerEach
                    new_line.e_Total_KG_weight = (
                        old_line.e_weightPerEach * new_line.e_qty
                    )

                new_line.sscc = picked_item["sscc"]
                new_line.picked_up_timestamp = (
                    picked_item.get("timestamp") or datetime.now()
                )
                new_line.save()

                if picked_item["sscc"] not in new_sscc_list:
                    new_sscc_list.append(picked_item["sscc"])
                    new_sscc_lines[picked_item["sscc"]] = [new_line]
                else:
                    new_sscc_lines[picked_item["sscc"]].append(new_line)

                for item in picked_item["items"]:
                    # Create new Line_Data
                    line_data = Booking_lines_data()
                    line_data.fk_booking_id = pk_booking_id
                    line_data.fk_booking_lines_id = new_line.pk_booking_lines_id

                    if repack_type == "model_number":
                        line_data.modelNumber = item["model_number"]
                        line_data.itemDescription = "Picked at warehouse"
                        line_data.quantity = item.get("qty") or old_line.e_qty
                        line_data.clientRefNumber = picked_item["sscc"]
                    else:
                        line_data.modelNumber = item["sscc"]
                        line_data.itemDescription = "Repacked at warehouse"
                        line_data.clientRefNumber = picked_item["sscc"]

                    line_data.save()

                # Build label with Line
                if not booking.api_booking_quote:
                    raise Exception("Booking doens't have quote.")

                if not booking.vx_freight_provider and booking.api_booking_quote:
                    _booking = set_booking_quote(booking, booking.api_booking_quote)

        # Build built-in label with SSCC - one sscc should have one page label
        total_qty = 0
        for item in original_items:
            total_qty += item.e_qty

        file_path = (
            f"{settings.STATIC_PUBLIC}/pdfs/{booking.vx_freight_provider.lower()}_au"
        )
        label_data = build_label_oper(
            booking=booking,
            file_path=file_path,
            total_qty=total_qty,
            sscc_list=new_sscc_list,
            sscc_lines=new_sscc_lines,
            need_zpl=True,
            scanned_items=scanned_items,
        )

        if label_data["urls"]:
            entire_label_url = f"{file_path}/DME{booking.b_bookingID_Visual}.pdf"
            label_paths = [label_data["urls"][0]]
            pu_state = booking.pu_Address_State

            for sscc in sscc_list:
                pdf_name = f"{pu_state}_{str(booking.b_bookingID_Visual)}_{sscc}.pdf"
                label_paths.append(f"{file_path}/{pdf_name}")

            pdf.pdf_merge(label_paths, entire_label_url)
            booking.z_label_url = f"{booking.vx_freight_provider.lower()}_au/DME{booking.b_bookingID_Visual}.pdf"
            booking.v_FPBookingNumber = gen_consignment_num(
                booking.vx_freight_provider,
                booking.b_bookingID_Visual,
                booking.kf_client_id,
                booking,
            )
            booking.save()

        # If Hunter Order?
        if is_picked_all and booking.b_status != "Picking":
            logger.info(
                f"#373 {LOG_ID} - HUNTER order is already booked. Booking Id: {booking.b_bookingID_Visual}, status: {booking.b_status}"
            )

            return {
                "success": False,
                "message": "This Order is already BOOKED.",
                "consignment_number": gen_consignment_num(
                    booking.vx_freight_provider,
                    booking.b_bookingID_Visual,
                    booking.kf_client_id,
                ),
                "labels": [],
            }

        if is_picked_all:
            scan_process_in_bg(booking)

        logger.info(
            f"#379 {LOG_ID} - Successfully scanned. Booking Id: {booking.b_bookingID_Visual}"
        )
        return {
            "success": True,
            "message": "Successfully updated picked info.",
            "consignment_number": gen_consignment_num(
                booking.vx_freight_provider,
                booking.b_bookingID_Visual,
                booking.kf_client_id,
            ),
            "labels": label_data["labels"],
        }
    except Exception as e:
        error_msg = f"@370 {LOG_ID} Exception: {str(e)}"
        logger.error(error_msg)
        send_email_to_admins(f"ABP {LOG_ID}", f"{error_msg}")
        raise Exception(
            "Please contact DME support center. <bookings@deliver-me.com.au>"
        )


def ready_boks(payload, client):
    """
    When it is ready(picked all items) on Warehouse
    """
    LOG_ID = "[READY ABP]"
    b_client_order_num = payload.get("HostOrderNumber")

    # Check required params are included
    if not b_client_order_num:
        message = "'HostOrderNumber' is required."
        raise ValidationError(message)

    # Get Order Number
    order_num = b_client_order_num[5:]

    # Check if Order exists
    booking = (
        Bookings.objects.select_related("api_booking_quote")
        .filter(b_client_name=client.company_name, b_client_order_num=order_num)
        .first()
    )

    if not booking:
        message = "Order does not exist. HostOrderNumber' is invalid."
        raise ValidationError(message)

    # If Hunter Order
    fp_name = booking.api_booking_quote.freight_provider.lower()

    if fp_name == "hunter" and booking.b_status == "Booked":
        message = "Order is already BOOKED."
        logger.info(f"@340 {LOG_ID} {message}")
        return message
    elif fp_name == "hunter" and booking.b_status != "Booked":
        # DME don't get the ready api for Hunter Order
        message = "Please contact DME support center. <bookings@deliver-me.com.au>"
        logger.info(f"@341 {LOG_ID} {message}")
        raise Exception(message)

    # Check if already ready
    if booking.b_status not in ["Picking", "Ready for Booking"]:
        message = "Order is already Ready."
        logger.info(f"@342 {LOG_ID} {message}")
        return message

    # If NOT
    pk_booking_id = booking.pk_booking_id
    lines = Booking_lines.objects.filter(fk_booking_id=pk_booking_id)
    line_datas = Booking_lines_data.objects.filter(fk_booking_id=pk_booking_id)

    # Check if Order items are all picked
    original_items = lines.filter(sscc__isnull=True)
    scanned_items = lines.filter(sscc__isnull=False, e_item="Picked Item")
    model_number_qtys = original_items.values_list("e_item_type", "e_qty")
    estimated_picked = {}
    is_picked_all = True
    not_picked_items = []

    for model_number_qty in model_number_qtys:
        estimated_picked[model_number_qty[0]] = 0

    for scanned_item in scanned_items:
        if scanned_item.e_item_type:
            estimated_picked[scanned_item.e_item_type] += scanned_item.e_qty

        for line_data in line_datas:
            if (
                line_data.fk_booking_lines_id == scanned_item.pk_booking_lines_id
                and line_data.itemDescription != "Repacked at warehouse"
            ):
                estimated_picked[line_data.modelNumber] += line_data.quantity

    logger.info(f"@843 {LOG_ID} limit: {model_number_qtys}, picked: {estimated_picked}")

    for item in estimated_picked:
        for model_number_qty in model_number_qtys:
            if (
                item == model_number_qty[0]
                and estimated_picked[item] != model_number_qty[1]
            ):
                not_picked_items.append(
                    {
                        "all_items_count": model_number_qty[1],
                        "picked_items_count": estimated_picked[item],
                    }
                )
                is_picked_all = False

    if not is_picked_all:
        message = (
            f"There are some items are not picked yet - {json.dumps(not_picked_items)}"
        )
        logger.info(f"@343 {LOG_ID} {message}")
        raise Exception(message)

    # Update DB so that Booking can be BOOKED
    if booking.api_booking_quote:
        status_history.create(booking, "Ready for Booking", "jason_l")
    else:
        status_history.create(booking, "On Hold", "jason_l")
        send_email_to_admins(
            f"URGENT! Quote issue on Booking(#{booking.b_bookingID_Visual})",
            f"Original FP was {booking.vx_freight_provider}({booking.vx_serviceName})."
            + f" After labels were made {booking.vx_freight_provider}({booking.vx_serviceName}) was not an option for shipment."
            + f" Please do FC manually again on DME portal.",
        )

    booking.save()

    message = "Order will be BOOKED soon."
    return message


def reprint_label(params, client):
    """
    get label(already built)
    """
    LOG_ID = "[REPRINT ABP]"
    b_client_order_num = params.get("HostOrderNumber")
    sscc = params.get("sscc")

    if not b_client_order_num:
        message = "'HostOrderNumber' is required."
        raise ValidationError(message)

    booking = (
        Bookings.objects.select_related("api_booking_quote")
        .filter(
            b_client_order_num=b_client_order_num, b_client_name=client.company_name
        )
        .first()
    )

    if not booking:
        message = "Order does not exist. 'HostOrderNumber' is invalid."
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

    # ABP ZPL printer requries portrait label
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

    return {"success": True, "zpl": zpl_data}


def manifest(payload, client, username):
    LOG_ID = "[MANIFEST ABP]"
    order_nums = payload.get("OrderNumbers")

    # Required fields
    if not order_nums:
        message = "'OrderNumbers' is required."
        raise ValidationError(message)

    bookings = Bookings.objects.filter(
        b_client_name=client.company_name, b_client_order_num__in=order_nums
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

    bookings, manifest_url = build_manifest(booking_ids, username)

    with open(manifest_url, "rb") as manifest:
        manifest_data = str(b64encode(manifest.read()))

    Bookings.objects.filter(
        b_client_name=client.company_name, b_client_order_num__in=order_nums
    ).update(z_manifest_url=manifest_url)

    return {"success": True, "manifest": manifest_data}
