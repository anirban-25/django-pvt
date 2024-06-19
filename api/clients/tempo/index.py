import uuid
import json
import logging
import requests
from datetime import datetime, date

from django.db import transaction
from django.conf import settings

from api.models import Client_warehouses, FPRouting, DME_Options, DME_Tokens, Bookings
from api.serializers import SimpleQuoteSerializer
from api.serializers_client import *
from api.common import time as dme_time_lib, constants as dme_constants, trace_error
from api.common.thread import background
from api.operations.email_senders import send_email_to_admins
from api.fp_apis.operations.pricing import pricing as pricing_oper
from api.convertors.packaging_type import get_package_type
from api.helpers.line import is_carton, is_pallet
from api.fp_apis.utils import (
    select_best_options,
    auto_select_pricing_4_bok,
    gen_consignment_num,
)
from api.common import (
    time as dme_time_lib,
    constants as dme_constants,
    status_history,
)
from api.clients.operations.index import get_suburb_state
from api.clients.tempo.operations import (
    find_warehouse,
    send_email_4_approval,
    send_email_approved,
    send_email_disposal,
    get_product,
    get_price,
)

logger = logging.getLogger(__name__)


@background
def quoting_in_bg(client, username, bok_1_obj, bok_1, bok_2s):
    LOG_ID = "[TEMPO QUOTING IN BG]"

    logger.info(f"#519 {LOG_ID} Pricing started")

    # create status history
    status_history.create_4_bok(
        bok_1["pk_header_id"], "Imported / Integrated", username
    )

    # PU avail
    pu_avil = datetime.strptime(bok_1["b_021_b_pu_avail_from_date"], "%Y-%m-%d")
    booking = {
        "pk_booking_id": bok_1["pk_header_id"],
        "puPickUpAvailFrom_Date": pu_avil.date(),
        "b_clientReference_RA_Numbers": "",
        "puCompany": bok_1["b_028_b_pu_company"],
        "pu_Contact_F_L_Name": bok_1["b_035_b_pu_contact_full_name"],
        "pu_Email": bok_1["b_037_b_pu_email"],
        "pu_Phone_Main": bok_1["b_038_b_pu_phone_main"],
        "pu_Address_Street_1": bok_1["b_029_b_pu_address_street_1"],
        "pu_Address_street_2": bok_1.get("b_030_b_pu_address_street_2"),
        "pu_Address_Country": bok_1["b_034_b_pu_address_country"],
        "pu_Address_PostalCode": str(bok_1["b_033_b_pu_address_postalcode"]),
        "pu_Address_State": bok_1["b_031_b_pu_address_state"],
        "pu_Address_Suburb": bok_1["b_032_b_pu_address_suburb"],
        "deToCompanyName": bok_1["b_054_b_del_company"],
        "de_to_Contact_F_LName": bok_1["b_061_b_del_contact_full_name"],
        "de_Email": bok_1["b_063_b_del_email"],
        "de_to_Phone_Main": bok_1["b_064_b_del_phone_main"],
        "de_To_Address_Street_1": bok_1["b_055_b_del_address_street_1"],
        "de_To_Address_Street_2": bok_1["b_056_b_del_address_street_2"],
        "de_To_Address_Country": bok_1["b_060_b_del_address_country"],
        "de_To_Address_PostalCode": str(bok_1["b_059_b_del_address_postalcode"]),
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
        auto_book_amount = bok_1.get("auto_book_amount_max_threshold") or 0
        if best_quote.client_mu_1_minimum_values > auto_book_amount * 1.1:
            send_email_4_approval(bok_1_obj, best_quote, auto_book_amount)
    elif bok_1.get("b_client_order_num"):
        message = f"#521 {LOG_ID} No Pricing results to select - BOK_1 pk_header_id: {bok_1['pk_header_id']}\nOrder Number: {bok_1['b_client_order_num']}"
        logger.error(message)
        send_email_to_admins("No FC result", message)

    # Update success to map booking
    bok_1_obj.bok_3s().update(success=dme_constants.BOK_SUCCESS_4)
    bok_1_obj.bok_2s().update(success=dme_constants.BOK_SUCCESS_4)
    bok_1_obj.success = dme_constants.BOK_SUCCESS_4
    bok_1_obj.save()


def push_boks(payload, client, username, method):
    """
    PUSH api (bok_1, bok_2, bok_3)
    """
    LOG_ID = "[PUSH FROM TEMPO]"
    bok_1 = payload["booking"]
    bok_2s = payload["booking_lines"]

    if not bok_2s:
        raise Exception("No Lines")

    if not bok_1.get("b_031_b_pu_address_state"):
        de_postal_code = bok_1["b_033_b_pu_address_postalcode"]
        de_suburb = bok_1["b_032_b_pu_address_suburb"]
        state, suburb = get_suburb_state(de_postal_code, de_suburb)
        bok_1["b_031_b_pu_address_state"] = state

    # Check `port_code`
    logger.info(f"{LOG_ID} Checking port_code...")
    pu_state = bok_1.get("b_031_b_pu_address_state")
    pu_suburb = bok_1.get("b_032_b_pu_address_suburb")
    pu_postcode = bok_1.get("b_033_b_pu_address_postalcode")

    # head_port and port_code
    fp_routings = FPRouting.objects.filter(
        freight_provider=13,
        dest_suburb__iexact=pu_suburb,
        dest_postcode=pu_postcode,
        dest_state__iexact=pu_state,
    )
    head_port = fp_routings[0].gateway if fp_routings and fp_routings[0].gateway else ""
    port_code = fp_routings[0].onfwd if fp_routings and fp_routings[0].onfwd else ""

    if not head_port or not port_code:
        message = f"No port_code.\n\n"
        message += f"Order Num: {bok_1['b_client_order_num']}\n"
        message += f"State: {pu_state}\nPostal Code: {pu_postcode}\nSuburb: {pu_suburb}"
        logger.error(f"{LOG_ID} {message}")
        raise Exception(message)

    bok_1["b_008_b_category"] = bok_1.get("b_008_b_category") or "salvage expense"
    b_008_b_category = bok_1.get("b_008_b_category")

    if not bok_1.get("pk_header_id"):
        bok_1["pk_header_id"] = str(uuid.uuid4())

    if b_008_b_category and b_008_b_category.lower() == "salvage expense":
        # Find warehouse
        warehouse = find_warehouse(bok_1, bok_2s)
        bok_1["client_booking_id"] = bok_1["pk_header_id"]
        bok_1["fk_client_warehouse"] = warehouse.pk_id_client_warehouses
        bok_1["b_clientPU_Warehouse"] = warehouse.name
        bok_1["b_client_warehouse_code"] = warehouse.client_warehouse_code
        bok_1["b_053_b_del_address_type"] = "Business"
        # bok_1["b_054_b_del_company"] = warehouse.name
        # bok_1["b_055_b_del_address_street_1"] = warehouse.address1
        # bok_1["b_056_b_del_address_street_2"] = warehouse.address2
        # bok_1["b_057_b_del_address_state"] = warehouse.state
        # bok_1["b_059_b_del_address_postalcode"] = warehouse.postal_code
        # bok_1["b_058_b_del_address_suburb"] = warehouse.suburb
        # bok_1["b_060_b_del_address_country"] = "Australia"
        # bok_1["b_061_b_del_contact_full_name"] = warehouse.contact_name
        # bok_1["b_063_b_del_email"] = warehouse.contact_email
        # bok_1["b_064_b_del_phone_main"] = warehouse.phone_main

    # For bookings uploading in folder 3, make the warehouse code
    if "zb_101_text_1" in bok_1 and bok_1["zb_101_text_1"] == "03_ALDI_TV_Collections":
        bok_1["fk_client_warehouse"] = 100  # No - Warehouse
        bok_1["b_clientPU_Warehouse"] = "No - Warehouse"
        bok_1["b_client_warehouse_code"] = "No - Warehouse"
        bok_1["b_005_b_created_for"] = "ALDI TV Collections"
        bok_1["b_006_b_created_for_email"] = "alditvcollections@tempo.org"

    bok_1["b_028_b_pu_company"] = bok_1.get("b_028_b_pu_company") or bok_1.get(
        "b_035_b_pu_contact_full_name"
    )
    bok_1["x_booking_Created_With"] = "DME PUSH API"
    bok_1["success"] = dme_constants.BOK_SUCCESS_3
    bok_1["b_031_b_pu_address_state"] = bok_1.get("b_031_b_pu_address_state").upper()
    bok_1["fk_client_id"] = client.dme_account_num
    client_booking_id = (
        f"{bok_1['pk_header_id']}_{datetime.strftime(datetime.utcnow(), '%s')}"
    )
    bok_1["client_booking_id"] = client_booking_id
    bok_1["b_clientPU_Warehouse"] = (
        bok_1.get("b_clientPU_Warehouse") or "No - Warehouse"
    )
    bok_1["b_client_order_num"] = bok_1.get("b_client_order_num") or ""

    # Find price for Microwave product
    if bok_1["zb_101_text_1"] == "02_Microwave_Portal_Collections":
        bok_1["auto_book_amount_max_threshold"] = get_price(bok_1)

    bok_1_serializer = BOK_1_Serializer(data=bok_1)
    if not bok_1_serializer.is_valid():
        message = f"Serialiser Error - {bok_1_serializer.errors}"
        logger.info(f"@8811 {LOG_ID} {message}")
        raise Exception(message)

    with transaction.atomic():
        # Save bok_2s
        for index, bok_2 in enumerate(bok_2s):
            _bok_2 = bok_2["booking_line"]
            _bok_2["fk_header_id"] = bok_1["pk_header_id"]
            _bok_2["v_client_pk_consigment_num"] = bok_1["pk_header_id"]

            if not _bok_2.get("pk_booking_lines_id"):
                _bok_2["pk_booking_lines_id"] = str(uuid.uuid1())

            _bok_2["success"] = bok_1["success"]
            l_001 = _bok_2.get("l_001_type_of_packaging") or "Carton"
            _bok_2["l_001_type_of_packaging"] = l_001

            if not "l_005_dim_length" in _bok_2:
                product = get_product(_bok_2["l_003_item"])
                _bok_2["l_005_dim_length"] = product.e_dimLength
                _bok_2["l_006_dim_width"] = product.e_dimWidth
                _bok_2["l_007_dim_height"] = product.e_dimHeight
                _bok_2["l_004_dim_UOM"] = product.e_dimUOM
                _bok_2["l_009_weight_per_each"] = product.e_weightPerEach
                _bok_2["l_008_weight_UOM"] = product.e_weightUOM

            bok_2_serializer = BOK_2_Serializer(data=_bok_2)
            if bok_2_serializer.is_valid():
                bok_2_serializer.save()
            else:
                message = f"Serialiser Error - {bok_2_serializer.errors}"
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

    # Fast response for sapb1
    quoting_in_bg(client, username, bok_1_obj, bok_1, bok_2s)

    res_json = {"success": True, "message": "Push success!"}
    return res_json


def update_via_api(booking, event_timestamp):
    LOG_ID = "[UPDATE TEMPO via API]"
    logger.info(f"{LOG_ID} Booking: {booking.b_bookingID_Visual}")

    TEMPO_CREDENTIALS = {
        "api_url": "https://globalconnect.tempo.org/api/RAPickup/Bookings",
        "username": "Deliver.Me",
        "password": "dk45b_AM",
    }

    # Run only on PROD
    if settings.ENV != "prod":
        return False

    # Run only for "Tempo" Client
    if booking.kf_client_id != "37C19636-C5F9-424D-AD17-05A056A8FBDB":
        return False

    # Run only when `tempo_push` flag is `on`
    dme_option = DME_Options.objects.get(option_name="tempo_push")
    if int(dme_option.option_value) != 1:
        logger.info(f"{LOG_ID} tempo_push flag is OFF")
        return False

    json_booking = {}
    json_booking["dmeBookingID"] = booking.b_bookingID_Visual
    # json_booking["clientSalesInvoice"] = booking.b_client_sales_inv_num
    # json_booking["clientOrderNo"] = booking.b_client_order_num
    json_booking["freightProvider"] = booking.vx_freight_provider
    json_booking["consignmentNo"] = booking.v_FPBookingNumber
    json_booking["status"] = booking.b_status
    json_booking["statusTimestamp"] = event_timestamp

    if event_timestamp and not isinstance(event_timestamp, str):
        json_booking["statusTimestamp"] = event_timestamp.strftime("%Y-%m-%d %H:%M:%S")

    json_booking["bookedDate"] = booking.b_dateBookedDate

    if booking.b_dateBookedDate and not isinstance(booking.b_dateBookedDate, str):
        json_booking["bookedDate"] = booking.b_dateBookedDate.strftime(
            "%Y-%m-%d %H:%M:%S"
        )

    # Client Ref Number - i.e: 'CS00493466' | Gap/Ra - i.e: 'TRA57811'
    line_datas = booking.line_datas()
    clientRefNumber = "" if not line_datas else line_datas[0].clientRefNumber
    gapRa = "" if not line_datas else line_datas[0].gap_ra
    json_booking["clientRefNum"] = clientRefNumber
    json_booking["gapRa"] = gapRa

    # Cost
    json_booking["cost"] = (
        "Not available"
        if not booking.api_booking_quote
        else booking.api_booking_quote.client_mu_1_minimum_values
    )

    # DE info
    json_booking["deToEntity"] = booking.deToCompanyName
    json_booking["deToStreet1"] = booking.de_To_Address_Street_1
    json_booking["deToState"] = booking.de_To_Address_State
    json_booking["deToPostalCode"] = booking.de_To_Address_PostalCode
    json_booking["deToSuburb"] = booking.de_To_Address_Suburb
    json_booking["deToContactName"] = booking.de_to_Contact_F_LName
    json_booking["deToPhoneMain"] = booking.de_to_Phone_Main
    json_booking["deToEmail"] = booking.de_Email

    # PU info
    json_booking["puEntity"] = booking.puCompany
    json_booking["puStreet1"] = booking.pu_Address_Street_1
    json_booking["puState"] = booking.pu_Address_State
    json_booking["puPostalCode"] = booking.pu_Address_PostalCode
    json_booking["puSuburb"] = booking.pu_Address_Suburb
    json_booking["puContactName"] = booking.pu_Contact_F_L_Name
    json_booking["puPhoneMain"] = booking.pu_Phone_Main
    json_booking["puEmail"] = booking.pu_Email

    json_payload = [json_booking]
    logger.info(f"{LOG_ID} Payload: {json_payload}")
    headers = {"content-type": "application/json", "GCDB-Request-Type": "APIRequest"}

    res = requests.post(
        TEMPO_CREDENTIALS["api_url"],
        auth=(TEMPO_CREDENTIALS["username"], TEMPO_CREDENTIALS["password"]),
        json=json_payload,
        headers=headers,
    )
    logger.info(f"{LOG_ID} Response: {res.status_code}, {res.content}")

    # TODO
    # When response status_code is not 200 then email to Gold
    return True


def approve(request):
    LOG_ID = "[APPROVE]"
    token = request.data["token"]
    decision = request.data["decision"]
    logger.info(f"{LOG_ID} Token: {token}, decision: {decision}")

    try:
        dme_token = DME_Tokens.objects.get(token=token)

        if not dme_token.z_expiredTimeStamp:
            dme_token.z_expiredTimeStamp = datetime.now()
            dme_token.save()
        else:
            return "Token is expired!"

        booking = Bookings.objects.get(pk=dme_token.booking_id)
        lines = booking.lines()
        line_datas = booking.line_datas()

        if decision == "approve":
            # TODO auto book
            pass
        elif decision == "disapprove-hold":
            send_email_approved(booking, lines, line_datas, dme_token)
        elif decision == "disapprove-disposal":
            send_email_approved(booking, lines, line_datas, dme_token)
            send_email_disposal(booking, lines, line_datas, dme_token)
        else:
            return "Wrong decision!"

        return "Thank you! DME received your decision."
    except Exception as e:
        trace_error.print()
        return "Invalid token"
