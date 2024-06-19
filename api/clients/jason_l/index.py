import os
import json
import uuid
import logging
import requests
from datetime import datetime, date
from hashlib import sha256
from base64 import b64encode

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
    Pallet,
    API_booking_quotes,
    FP_zones,
    Api_booking_confirmation_lines,
)
from api.serializers import SimpleQuoteSerializer, Simple4ProntoQuoteSerializer
from api.serializers_client import *
from api.convertors import pdf
from api.common import (
    time as dme_time_lib,
    constants as dme_constants,
    status_history,
    trace_error,
)
from api.common.thread import background
from api.common.pallet import get_number_of_pallets, get_palletized_by_ai
from api.common.booking_quote import set_booking_quote
from api.fp_apis.utils import (
    select_best_options,
    auto_select_pricing_4_bok,
    gen_consignment_num,
)
from api.fp_apis.operations.book import book as book_oper
from api.fp_apis.operations.pricing import pricing as pricing_oper
from api.operations import product_operations as product_oper
from api.operations.email_senders import send_email_to_admins, send_email_missing_dims
from api.operations.labels.index import build_label as build_label_oper
from api.operations.booking_line import index as line_oper

# from api.operations.pronto_xi.index import populate_bok as get_bok_from_pronto_xi
# from api.operations.pronto_xi.index import send_info_back
from api.clients.operations.index import get_warehouse, get_suburb_state
from api.clients.jason_l.operations import (
    get_picked_items,
    send_email_variance_quote,
    send_email_zero_quote,
    update_when_no_quote_required,
    get_bok_by_talend,
    sucso_handler,
    get_address,
    parse_sku_string,
    isGood4Linehaul,
    isInSydneyMetro,
    get_total_sales,
)
from api.clients.jason_l.constants import (
    NEED_PALLET_GROUP_CODES,
    SERVICE_GROUP_CODES,
    ITEM_CODES_4_CUSTOMER_PICKUP,
)
from api.helpers.cubic import get_cubic_meter
from api.helpers.line import is_pallet
from api.convertors.pdf import pdf_merge
from api.common.ratio import _get_dim_amount


logger = logging.getLogger(__name__)


def partial_pricing(payload, client, warehouse):
    LOG_ID = "[PP Jason L]"
    pk_header_id = str(uuid.uuid4())
    bok_2s = parse_sku_string(payload.get("sku"))
    json_results = []

    de_postal_code = payload.get("b_059_b_del_address_postalcode")
    de_state, de_suburb = get_suburb_state(de_postal_code)

    # Check if has lines
    if bok_2s and len(bok_2s) == 0:
        message = "Line items are required."
        logger.info(f"@815 {LOG_ID} {message}")
        raise Exception(message)

    # Get next business day
    next_biz_day = dme_time_lib.next_business_day(date.today(), 1)

    booking = {
        "pk_booking_id": pk_header_id,
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
        "pu_Address_Type": "business",
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
        "de_To_AddressType": "residential",
        "b_booking_tail_lift_pickup": 0,
        "b_booking_tail_lift_deliver": 0,
        "client_warehouse_code": warehouse.client_warehouse_code,
        "vx_serviceName": "exp",
        "kf_client_id": warehouse.fk_id_dme_client.dme_account_num,
        "b_client_name": client.company_name,
        "pu_no_of_assists": 0,
        "de_no_of_assists": 0,
        "b_booking_project": None,
        "b_client_order_num": "",  # bok_1["b_client_order_num"]
        "v_customer_code": None,
    }

    # Product & Child items
    missing_model_numbers = product_oper.find_missing_model_numbers(bok_2s, client)

    if missing_model_numbers:
        missing_model_numbers_str = {", ".join(missing_model_numbers)}
        message = f"System is missing model numbers - {missing_model_numbers_str}"
        logger.info(f"@816 {LOG_ID} {message}")
        raise Exception(message)

    items = product_oper.get_product_items(bok_2s, client, True, False)

    booking_lines = []
    for index, item in enumerate(items):
        booking_line = {
            "pk_lines_id": index,
            "e_type_of_packaging": item["e_type_of_packaging"] or "Carton",
            "fk_booking_id": pk_header_id,
            "e_qty": item["qty"],
            "e_item": item["description"],
            "e_dimUOM": item["e_dimUOM"],
            "e_dimLength": item["e_dimLength"],
            "e_dimWidth": item["e_dimWidth"],
            "e_dimHeight": item["e_dimHeight"],
            "e_weightUOM": item["e_weightUOM"],
            "e_weightPerEach": item["e_weightPerEach"],
            "packed_status": BOK_2_lines.ORIGINAL,
        }
        booking_lines.append(booking_line)

    _, success, message, quotes, client = pricing_oper(
        body={"booking": booking, "booking_lines": booking_lines},
        booking_id=None,
        is_pricing_only=True,
    )
    logger.info(
        f"#519 {LOG_ID} Pricing result: success: {success}, message: {message}, results cnt: {len(quotes)}"
    )

    # Select best quotes(fastest, lowest)
    if quotes:
        best_quotes = select_best_options(pricings=quotes, client=client)
        logger.info(f"#520 {LOG_ID} Selected Best Pricings: {best_quotes}")

        context = {"client_customer_mark_up": client.client_customer_mark_up}
        json_results = SimpleQuoteSerializer(
            best_quotes, many=True, context=context
        ).data
        json_results = dme_time_lib.beautify_eta(json_results, best_quotes, client)

        # delete quotes
        for quote in quotes:
            quote.is_used = True
            quote.save()

    # Set Express or Standard
    if len(json_results) == 1:
        json_results[0]["service_name"] = "Standard"
    elif len(json_results) > 1:
        if float(json_results[0]["cost"]) > float(json_results[1]["cost"]):
            json_results[0]["service_name"] = "Express"
            json_results[1]["service_name"] = "Standard"

            if json_results[0]["eta"] == json_results[1]["eta"]:
                eta = f"{int(json_results[1]['eta'].split(' ')[0]) + 1} days"
                json_results[1]["eta"] = eta

            json_results = [json_results[1], json_results[0]]
        else:
            json_results[1]["service_name"] = "Express"
            json_results[0]["service_name"] = "Standard"

            if json_results[0]["eta"] == json_results[1]["eta"]:
                eta = f"{int(json_results[0]['eta'].split(' ')[0]) + 1} days"
                json_results[0]["eta"] = eta

    if json_results:
        logger.info(f"@818 {LOG_ID} Success!")
        return json_results
    else:
        logger.info(f"@819 {LOG_ID} Failure!")
        return json_results


@background
def quoting_in_bg(
    client,
    bok_1,
    bok_1_obj,
    booking,
    booking_lines,
    selected_quote,
    original_lines_count,
):
    LOG_ID = "[QUOTING IN BG]"
    logger.info(f"#510 {LOG_ID}")

    try:
        # fc_log.old_quote = old_quote
        body = {"booking": booking, "booking_lines": booking_lines}
        postal_code = booking["de_To_Address_PostalCode"]
        quotes = None

        if not booking_lines:
            logger.info(f"#511 {LOG_ID} No lines")
        else:
            # Check Customer Pickup
            is_4_customer_pickup = False
            for line in booking_lines:
                bin_no = line.get("e_bin_number")
                if bin_no and bin_no.upper() in ITEM_CODES_4_CUSTOMER_PICKUP:
                    is_4_customer_pickup = True
                    logger.info(
                        f'{LOG_ID} {bok_1.get("b_client_order_num")}, CUSTOMER PICKUP'
                    )
                    break

            _, success, message, quotes, client = pricing_oper(
                body=body,
                booking_id=None,
                is_pricing_only=True,
                packed_statuses=[Booking_lines.ORIGINAL, Booking_lines.AUTO_PACK],
            )
            logger.info(
                f"#519 {LOG_ID} Pricing result: success: {success}, message: {message}, results cnt: {len(quotes)}"
            )
            bok_1_obj.zb_104_text_4 = None
            bok_1_obj.save()

            # Filter qutoes
            _quotes = []
            if is_4_customer_pickup:
                for quote in quotes:
                    if quote.freight_provider == "Customer Collect":
                        _quotes.append(quote)
                        bok_1_obj.b_092_is_quote_locked = True
                        break
            elif (
                not isInSydneyMetro(postal_code)
                and len(booking_lines) == 1
                and booking_lines[0]["e_qty"] == 1
                and not is_pallet(booking_lines[0]["e_type_of_packaging"])
            ):  # Allied for any single items AND out of the Sydney Metro area.
                for quote in quotes:
                    if quote.freight_provider == "Allied":
                        _quotes.append(quote)
            elif selected_quote:  # When selected quote
                logger.info(
                    f"#530 {LOG_ID} Locked Quote: {selected_quote}, {selected_quote.freight_provider}, {selected_quote.service_name}"
                )
                for quote in quotes:
                    if quote.freight_provider == selected_quote.freight_provider:
                        _quotes.append(quote)
                    if quote.service_name == selected_quote.service_name:
                        _quotes.append(quote)
                logger.info(f"#532 {LOG_ID} {quotes}")
            elif isGood4Linehaul(postal_code, booking_lines):
                for quote in quotes:
                    if quote.freight_provider == "Deliver-ME":
                        _quotes.append(quote)
            # All JasonL bookings to State SA should book with non-Allied
            elif bok_1.get("b_057_b_del_address_state", "").upper() == "SA":
                for quote in quotes:
                    if quote.freight_provider != "Allied":
                        _quotes.append(quote)
            else:
                for quote in quotes:
                    if quote.freight_provider != "Deliver-ME":
                        _quotes.append(quote)
            quotes = _quotes or quotes

        # Select best quotes(fastest, lowest)
        if quotes:
            if len(quotes) > 1:
                best_quotes = select_best_options(
                    pricings=quotes,
                    client=client,
                    original_lines_count=original_lines_count,
                )
            else:
                best_quotes = quotes

            logger.info(f"#520 {LOG_ID} Selected Best Pricings: {best_quotes}")
            best_quote = best_quotes[0]
            bok_1_obj.quote = best_quote
            bok_1_obj.b_003_b_service_name = best_quote.service_name
            bok_1_obj.b_001_b_freight_provider = best_quote.freight_provider
            bok_1_obj.b_002_b_vehicle_type = (
                best_quote.vehicle.description if best_quote.vehicle else None
            )
            bok_1_obj.zb_104_text_4 = None

            if selected_quote:
                bok_1_obj.b_092_is_quote_locked = True

            bok_1_obj.save()

            # Send quote info back to Pronto
            # result = send_info_back(bok_1_obj, best_quote)
        else:
            b_client_order_num = bok_1.get("b_client_order_num")

            if b_client_order_num:
                message = f"#521 {LOG_ID} No Pricing results to select - BOK_1 pk_header_id: {bok_1['pk_header_id']}\nOrder Number: {bok_1['b_client_order_num']}"
                logger.error(message)
                send_email_to_admins("No FC result", message)

        logger.info(f'{LOG_ID} BG JOB finished --- {bok_1.get("b_client_order_num")}')
    except Exception as e:
        trace_error.print()
        logger.info(f"{LOG_ID} BG JOB Error: {e}")


@background
def auto_repacking(
    client,
    bok_1,
    bok_1_obj,
    booking,
    booking_lines,
    bok_2_objs,
    selected_quote,
    original_lines_count,
):
    LOG_ID = "[PUSH FROM JasonL]"  # PB - PUSH BOKS

    # `auto_repack` logic
    carton_cnt = 0
    need_palletize = False
    bok_2s = []
    for bok_2_obj in bok_2_objs:
        carton_cnt += bok_2_obj.l_002_qty

        if bok_2_obj.zbl_102_text_2 in NEED_PALLET_GROUP_CODES:
            need_palletize = True
            logger.info(
                f"@8126 {LOG_ID} Need to be Palletized! - {bok_2_obj.zbl_102_text_2}"
            )
            break

    need_big_pallet = False  # 1.2m+ items
    for bok_2_obj in bok_2_objs:
        length = _get_dim_amount(bok_2_obj.l_004_dim_UOM) * bok_2_obj.l_005_dim_length
        width = _get_dim_amount(bok_2_obj.l_004_dim_UOM) * bok_2_obj.l_006_dim_width
        if not need_big_pallet and (length > 1.2 or width > 1.2):
            need_big_pallet = True

    if carton_cnt < 3000 and (carton_cnt > 2 or need_palletize):
        message = "Auto repacking..."
        logger.info(f"@8130 {LOG_ID} {message}")

        # Select suitable pallet and get required pallets count
        pallets = Pallet.objects.all()

        if not need_big_pallet:
            logger.info(f"@8126 {LOG_ID} Use only small pallets")
            pallets = pallets.exclude(pk__in=[2, 3, 4, 7])

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
            line["l_001_type_of_packaging"] = line_obj.l_001_type_of_packaging
            line["l_002_qty"] = item["quantity"]
            line["l_003_item"] = line_obj.l_003_item
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
            line["b_097_e_bin_number"] = line_obj.b_097_e_bin_number
            line["is_deleted"] = False
            line["b_093_packed_status"] = BOK_2_lines.AUTO_PACK
            bok_2_serializer = BOK_2_Serializer(data=line)
            if bok_2_serializer.is_valid():
                bok_2_serializer.save()
            else:
                message = f"Serialiser Error - {bok_2_serializer.errors}"
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
            new_line["l_001_type_of_packaging"] = "PAL"
            new_line["l_002_qty"] = palletized_item["quantity"]
            new_line["l_003_item"] = "Auto repacked item"
            new_line["l_004_dim_UOM"] = "mm"
            new_line["l_005_dim_length"] = pallet.length
            new_line["l_006_dim_width"] = pallet.width
            new_line["l_007_dim_height"] = palletized_item["packed_height"] * 1000
            new_line["l_009_weight_per_each"] = total_weight
            new_line["l_008_weight_UOM"] = "KG"
            new_line["b_097_e_bin_number"] = palletized_item.get("b_097_e_bin_number")
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
                    bok_3["ld_001_qty"] = line.l_002_qty
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
                logger.info(f"@8135 {LOG_ID} {message}")
                raise Exception(message)

        # Set `auto_repack` flag
        bok_1_obj.b_081_b_pu_auto_pack = True
        bok_1_obj.zb_104_text_4 = "In Progress"
        bok_1_obj.save()

    # Do not get pricing when there is issue
    if bok_1.get("zb_105_text_5") and "Error" in bok_1.get("zb_105_text_5"):
        logger.info(
            f"#515 {LOG_ID} Skip Pricing due to address issue: {bok_1.get('zb_105_text_5')}"
        )

        url = f"{settings.WEB_SITE_URL}/price/{bok_1['client_booking_id']}/"
        result = {"success": True, "pricePageUrl": url}
        logger.info(f"@8837 {LOG_ID} success: True, 201_created --- SKIP QUOTE!")
        return result

    # Get Pricings

    for bok_2 in bok_2s:
        _bok_2 = bok_2["booking_line"]

        if _bok_2["is_deleted"]:
            continue

        bok_2_line = {
            "fk_booking_id": _bok_2["fk_header_id"],
            "pk_lines_id": _bok_2["fk_header_id"],
            "e_type_of_packaging": _bok_2["l_001_type_of_packaging"],
            "e_qty": _bok_2["l_002_qty"],
            "e_item": _bok_2["l_003_item"],
            "e_item_type": _bok_2["l_003_item"],
            "e_dimUOM": _bok_2["l_004_dim_UOM"],
            "e_dimLength": _bok_2["l_005_dim_length"],
            "e_dimWidth": _bok_2["l_006_dim_width"],
            "e_dimHeight": _bok_2["l_007_dim_height"],
            "e_weightUOM": _bok_2["l_008_weight_UOM"],
            "e_weightPerEach": _bok_2["l_009_weight_per_each"],
            "e_bin_number": _bok_2.get("b_097_e_bin_number"),
            "packed_status": _bok_2["b_093_packed_status"],
        }
        booking_lines.append(bok_2_line)

    # Get quote in background
    quoting_in_bg(
        client,
        bok_1,
        bok_1_obj,
        booking,
        booking_lines,
        selected_quote,
        original_lines_count,
    )


def push_boks(payload, client, username, method):
    """
    PUSH api (bok_1, bok_2, bok_3)

    Sample payload:
        {
            "booking": {
                "b_client_order_num": "    20176",
                "shipping_type": "DMEM",
                "b_client_sales_inv_num": "    TEST ORDER 20176"
            },
            "is_from_script": True
        }
    """
    LOG_ID = "[PUSH FROM JasonL]"  # PB - PUSH BOKS
    bok_1 = payload["booking"]
    bok_2s = []
    is_from_script = payload.get("is_from_script")
    client_name = None
    old_quote = None
    best_quotes = None
    json_results = []

    # Assign vars
    is_biz = "_bizsys" in username
    is_web = "_websys" in username

    # Strip data
    if is_biz:
        bok_1["b_client_order_num"] = bok_1["b_client_order_num"].strip()
        bok_1["b_client_sales_inv_num"] = bok_1["b_client_sales_inv_num"].strip()
        bok_1["shipping_type"] = bok_1.get("shipping_type", "DMEM").strip()

    bok_1["b_053_b_del_address_type"] = (
        bok_1.get("b_053_b_del_delivery_type", "").strip().lower()
    )

    if not bok_1["b_053_b_del_address_type"] in ["business", "residential"]:
        bok_1["b_053_b_del_address_type"] == "business"
        bok_1["shipping_type"] = "DMEM"

    del bok_1["b_053_b_del_delivery_type"]

    # Check required fields
    if is_biz:
        if not bok_1.get("shipping_type") or len(bok_1.get("shipping_type")) != 4:
            # message = "'shipping_type' is required."
            # logger.info(f"{LOG_ID} {message}")
            # raise ValidationError(message)
            bok_1["shipping_type"] = "DMEA"

        if not bok_1.get("b_client_order_num"):
            message = "'b_client_order_num' is required."
            logger.info(f"{LOG_ID} {message}")
            raise ValidationError(message)
    else:
        _bok_2s = parse_sku_string(payload.get("sku"))

        if not bok_1.get("client_booking_id"):
            message = "'client_booking_id' is required."
            logger.info(f"{LOG_ID} {message}")
            raise ValidationError(message)

        if not payload.get("sku"):
            message = "'sku' is required."
            logger.info(f"{LOG_ID} {message}")
            raise ValidationError(message)

        # Temporary population
        bok_1["b_068_b_del_location"] = "Pickup at Door / Warehouse Dock"
        bok_1["b_069_b_del_floor_number"] = 0
        bok_1["b_072_b_pu_no_of_assists"] = 0
        bok_1["b_070_b_del_floor_access_by"] = "Elevator"
        bok_1["b_027_b_pu_address_type"] = bok_1["b_027_b_pu_address_type"].lower()

    # Check duplicated push with `b_client_order_num`
    selected_quote = None
    if method == "POST":
        if is_biz:
            bok_1_objs = BOK_1_headers.objects.filter(
                fk_client_id=client.dme_account_num,
                b_client_order_num=bok_1["b_client_order_num"],
            )

            if bok_1_objs.exists():
                message = f"Order(b_client_order_num={bok_1['b_client_order_num']}) does already exist."
                logger.info(f"@884 {LOG_ID} {message}")

                json_res = {
                    "status": False,
                    "message": f"Order(b_client_order_num={bok_1['b_client_order_num']}) does already exist.",
                }

                if (
                    int(bok_1_objs.first().success) == dme_constants.BOK_SUCCESS_3
                ):  # Update
                    # Delete existing data
                    pk_header_id = bok_1_objs.first().pk_header_id
                    old_bok_1 = bok_1_objs.first()
                    old_bok_2s = BOK_2_lines.objects.filter(fk_header_id=pk_header_id)
                    old_bok_3s = BOK_3_lines_data.objects.filter(
                        fk_header_id=pk_header_id
                    )
                    quotes = API_booking_quotes.objects.filter(
                        fk_booking_id=pk_header_id
                    )

                    # Check new Order info
                    # try:
                    #     bok_1, bok_2s = get_bok_from_pronto_xi(bok_1)
                    # except Exception as e:
                    #     bok_1, bok_2s = get_bok_by_talend(bok_1["b_client_order_num"])
                    #     logger.error(
                    #         f"@887 {LOG_ID} Failed to get Order by using Pronto API. OrderNo: {bok_1['b_client_order_num']}, Error: {str(e)}"
                    #     )
                    #     logger.info(
                    #         f"@888 Now trying to get Order by Talend App (for Archived Order)"
                    #     )
                    bok_1, bok_2s = get_bok_by_talend(bok_1)
                    bok_2s = sucso_handler(bok_1["b_client_order_num"], bok_2s)

                    warehouse = get_warehouse(
                        client, code=f"JASON_L_{bok_1['warehouse_code']}"
                    )
                    del bok_1["warehouse_code"]
                    bok_1["fk_client_warehouse"] = warehouse.pk_id_client_warehouses
                    bok_1["b_clientPU_Warehouse"] = warehouse.name
                    bok_1["b_client_warehouse_code"] = warehouse.client_warehouse_code
                    is_updated = update_when_no_quote_required(
                        old_bok_1, old_bok_2s, bok_1, bok_2s
                    )

                    if old_bok_1.quote:
                        old_quote = old_bok_1.quote

                    # if not is_updated:
                    if True:
                        logger.info(
                            f"@8850 {LOG_ID} Order {bok_1['b_client_order_num']} requires new quotes."
                        )
                        if old_bok_1.b_092_is_quote_locked and old_bok_1.quote:
                            selected_quote = old_bok_1.quote

                        quotes.delete()
                        old_bok_3s.delete()
                        old_bok_2s.delete()
                        old_bok_1.delete()
                    else:
                        # Return price page url
                        url = f"{settings.WEB_SITE_URL}/price/{bok_1_objs.first().client_booking_id}/"
                        json_res["pricePageUrl"] = url
                        logger.info(f"@885 {LOG_ID} Response: {json_res}")
                        return json_res
                else:
                    # Return status page url
                    url = f"{settings.WEB_SITE_URL}/status/{bok_1_objs.first().client_booking_id}/"
                    json_res["pricePageUrl"] = url
                    logger.info(f"@886 {LOG_ID} Response: {json_res}")
                    return json_res

    # Prepare population
    if is_biz and not bok_2s:
        bok_1, bok_2s = get_bok_by_talend(bok_1)
        bok_2s = sucso_handler(bok_1["b_client_order_num"], bok_2s)

        warehouse = get_warehouse(client, code=f"JASON_L_{bok_1['warehouse_code']}")
        del bok_1["warehouse_code"]
        bok_1["fk_client_warehouse"] = warehouse.pk_id_client_warehouses
        bok_1["b_clientPU_Warehouse"] = warehouse.name
        bok_1["b_client_warehouse_code"] = warehouse.client_warehouse_code

    if is_web:
        for index, line in enumerate(_bok_2s):
            bok_2s.append(
                {
                    "model_number": line["model_number"],
                    "qty": line["qty"],
                    "sequence": index + 1,
                    "UOMCode": "EACH",
                    "ProductGroupCode": "----",
                }
            )

        bok_2s = product_oper.get_product_items(bok_2s, client, is_web, False)

        warehouse = get_warehouse(client)
        bok_1["fk_client_warehouse"] = warehouse.pk_id_client_warehouses
        bok_1["b_clientPU_Warehouse"] = warehouse.name
        bok_1["b_client_warehouse_code"] = warehouse.client_warehouse_code

        next_biz_day = dme_time_lib.next_business_day(date.today(), 1)
        bok_1["b_021_b_pu_avail_from_date"] = str(next_biz_day)[:10]

    bok_1["pk_header_id"] = str(uuid.uuid4())

    # Generate `client_booking_id` for Pronto
    if is_biz:
        client_booking_id = f"{bok_1['b_client_order_num']}_{bok_1['pk_header_id']}_{datetime.strftime(datetime.utcnow(), '%s')}"
        bok_1["client_booking_id"] = client_booking_id

    bok_1["fk_client_id"] = client.dme_account_num
    bok_1["x_booking_Created_With"] = "DME API"
    bok_1["success"] = dme_constants.BOK_SUCCESS_2  # Default success code
    bok_1["b_092_booking_type"] = bok_1.get("shipping_type")
    bok_1["success"] = dme_constants.BOK_SUCCESS_3

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

    if not bok_1.get("b_027_b_pu_address_type"):
        bok_1["b_027_b_pu_address_type"] = "business"
    if not bok_1.get("b_053_b_del_address_type"):
        bok_1["b_053_b_del_address_type"] = "business"

    if not bok_1.get("b_019_b_pu_tail_lift"):
        bok_1["b_019_b_pu_tail_lift"] = False
    if not bok_1.get("b_041_b_del_tail_lift"):
        bok_1["b_041_b_del_tail_lift"] = 0

    if not bok_1.get("b_072_b_pu_no_of_assists"):
        bok_1["b_072_b_pu_no_of_assists"] = 0
    if not bok_1.get("b_073_b_del_no_of_assists"):
        bok_1["b_073_b_del_no_of_assists"] = 0

    if not bok_1.get("b_078_b_pu_location"):
        bok_1["b_078_b_pu_location"] = BOK_1_headers.PDWD
    if not bok_1.get("b_068_b_del_location"):
        bok_1["b_068_b_del_location"] = BOK_1_headers.DDWD

    if not bok_1.get("b_074_b_pu_access"):
        bok_1["b_074_b_pu_access"] = "Level Driveway"
    if not bok_1.get("b_075_b_del_access"):
        bok_1["b_075_b_del_access"] = "Level Driveway"

    if not bok_1.get("b_079_b_pu_floor_number"):
        bok_1["b_079_b_pu_floor_number"] = 0  # Ground
    if not bok_1.get("b_069_b_del_floor_number"):
        bok_1["b_069_b_del_floor_number"] = 0  # Ground

    if not bok_1.get("b_080_b_pu_floor_access_by"):
        bok_1["b_080_b_pu_floor_access_by"] = BOK_1_headers.NONE
    if not bok_1.get("b_070_b_del_floor_access_by"):
        bok_1["b_070_b_del_floor_access_by"] = BOK_1_headers.NONE

    if not bok_1.get("b_076_b_pu_service"):
        bok_1["b_076_b_pu_service"] = BOK_1_headers.NONE
    if not bok_1.get("b_077_b_pu_service"):
        bok_1["b_077_b_pu_service"] = BOK_1_headers.NONE

    if not bok_1.get("b_054_b_del_company"):
        bok_1["b_054_b_del_company"] = bok_1["b_061_b_del_contact_full_name"]

    bok_1["b_031_b_pu_address_state"] = bok_1["b_031_b_pu_address_state"].upper()
    bok_1["b_094_client_sales_total"] = get_total_sales(bok_1["b_client_order_num"])

    bok_1_serializer = BOK_1_Serializer(data=bok_1)

    if not bok_1_serializer.is_valid():
        message = f"Serialiser Error - {bok_1_serializer.errors}"
        logger.info(f"@8821 {LOG_ID} {message}")
        raise Exception(message)

    # Save bok_2s (Product & Child items)
    items = bok_2s
    original_lines_count = 0
    new_bok_2s = []
    bok_2_objs = []
    lines_missing_dims = []

    with transaction.atomic():
        for index, item in enumerate(items):
            line = {}
            line["fk_header_id"] = bok_1["pk_header_id"]
            line["v_client_pk_consigment_num"] = bok_1["pk_header_id"]
            line["pk_booking_lines_id"] = str(uuid.uuid1())
            line["success"] = bok_1["success"]
            line["l_001_type_of_packaging"] = item["e_type_of_packaging"]
            line["l_002_qty"] = item["qty"]
            line["l_003_item"] = item["description"]
            line["l_004_dim_UOM"] = item["e_dimUOM"].upper()
            line["l_005_dim_length"] = item["e_dimLength"]
            line["l_006_dim_width"] = item["e_dimWidth"]
            line["l_007_dim_height"] = item["e_dimHeight"]
            line["l_009_weight_per_each"] = item["e_weightPerEach"]
            line["l_008_weight_UOM"] = item["e_weightUOM"].upper()
            line["e_item_type"] = item["e_item_type"]
            line["zbl_131_decimal_1"] = item["zbl_131_decimal_1"]
            line["zbl_102_text_2"] = (
                item["zbl_102_text_2"] if item["zbl_102_text_2"] else "_"
            )
            line["is_deleted"] = item["zbl_102_text_2"] in SERVICE_GROUP_CODES
            line["b_093_packed_status"] = BOK_2_lines.ORIGINAL
            line["b_097_e_bin_number"] = item.get("b_097_e_bin_number")

            if line["is_deleted"] and line["l_005_dim_length"] == 0:
                line["l_005_dim_length"] = 0.01
                line["l_006_dim_width"] = 0.01
                line["l_007_dim_height"] = 0.01
                line["l_009_weight_per_each"] = 0.01
            elif not line["is_deleted"] and (
                line["l_005_dim_length"] == 0
                or line["l_006_dim_width"] == 0
                or line["l_007_dim_height"] == 0
                or line["l_009_weight_per_each"] == 0
            ):
                lines_missing_dims.append(line["e_item_type"])

            line = line_oper.handle_zero(line, client)
            bok_2_serializer = BOK_2_Serializer(data=line)
            if bok_2_serializer.is_valid():
                bok_2_obj = bok_2_serializer.save()
                original_lines_count += item["qty"]

                if not line["is_deleted"]:
                    bok_2_objs.append(bok_2_obj)
                    line["pk_lines_id"] = bok_2_obj.pk
                    new_bok_2s.append({"booking_line": line})
            else:
                message = f"Serialiser Error - {bok_2_serializer.errors}"
                logger.info(f"@8831 {LOG_ID} {message}")
                raise Exception(message)

        bok_2s = new_bok_2s
        bok_1_obj = bok_1_serializer.save()

    # Send missing dims email
    if len(lines_missing_dims) > 0:
        send_email_missing_dims(
            client.company_name,
            bok_1["b_client_order_num"],
            ", ".join(lines_missing_dims),
        )

    # create status history
    status_history.create_4_bok(
        bok_1["pk_header_id"], "Imported / Integrated", username
    )

    # Get next business day
    next_biz_day = dme_time_lib.next_business_day(date.today(), 1)

    booking = {
        "pk_booking_id": bok_1["pk_header_id"],
        "puPickUpAvailFrom_Date": next_biz_day,
        "b_clientReference_RA_Numbers": "",
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
        "pu_Address_Type": bok_1["b_027_b_pu_address_type"],
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
        "de_To_AddressType": bok_1["b_053_b_del_address_type"],
        "b_booking_tail_lift_pickup": bok_1["b_019_b_pu_tail_lift"],
        "b_booking_tail_lift_deliver": bok_1["b_041_b_del_tail_lift"],
        "client_warehouse_code": bok_1["b_client_warehouse_code"],
        "kf_client_id": bok_1["fk_client_id"],
        "b_client_name": client.company_name,
        "pu_no_of_assists": bok_1.get("b_072_b_pu_no_of_assists") or 0,
        "de_no_of_assists": bok_1.get("b_073_b_del_no_of_assists") or 0,
        "b_booking_project": None,
        "b_client_order_num": bok_1["b_client_order_num"],
        "b_094_client_sales_total": bok_1["b_094_client_sales_total"],
        "v_customer_code": bok_1["b_096_v_customer_code"],
    }

    booking_lines = []
    for bok_2 in bok_2s:
        _bok_2 = bok_2["booking_line"]

        if _bok_2["is_deleted"]:
            continue

        bok_2_line = {
            "fk_booking_id": _bok_2["fk_header_id"],
            "pk_lines_id": _bok_2["fk_header_id"],
            "e_type_of_packaging": _bok_2["l_001_type_of_packaging"],
            "e_qty": _bok_2["l_002_qty"],
            "e_item": _bok_2["l_003_item"],
            "e_item_type": _bok_2["l_003_item"],
            "e_dimUOM": _bok_2["l_004_dim_UOM"],
            "e_dimLength": _bok_2["l_005_dim_length"],
            "e_dimWidth": _bok_2["l_006_dim_width"],
            "e_dimHeight": _bok_2["l_007_dim_height"],
            "e_weightUOM": _bok_2["l_008_weight_UOM"],
            "e_weightPerEach": _bok_2["l_009_weight_per_each"],
            "e_bin_number": _bok_2.get("b_097_e_bin_number"),
            "packed_status": _bok_2["b_093_packed_status"],
        }
        booking_lines.append(bok_2_line)

    # Auto repack and Get quote in background for packed lines
    auto_repacking(
        client,
        bok_1,
        bok_1_obj,
        booking,
        booking_lines,
        bok_2_objs,
        selected_quote,
        original_lines_count,
    )

    # Response
    url = f"{settings.WEB_SITE_URL}/price/{bok_1['client_booking_id']}/"
    result = {"success": True}
    result["pricePageUrl"] = url
    logger.info(f"@8837 {LOG_ID} success: True, 201_created")
    return result


def scanned(payload, client):
    """
    called as get_label

    request when item(s) is picked(scanned) at warehouse
    should response LABEL if payload is correct
    """
    LOG_ID = "[SCANNED Jason L]"
    b_client_order_num = payload.get("HostOrderNumber")
    sscc = payload.get("sscc")  # Optional for single SSCC get-label

    # Check required params are included
    if not b_client_order_num:
        message = "'HostOrderNumber' is required."
        raise ValidationError(message)

    # Trim data
    b_client_order_num = b_client_order_num.strip()
    sscc = None if not sscc else sscc.strip()

    # Check if Order exists on Bookings table
    booking = (
        Bookings.objects.select_related("api_booking_quote")
        .filter(
            b_client_name=client.company_name, b_client_order_num=b_client_order_num
        )
        .first()
    )

    if not booking:
        message = "Order does not exist. 'HostOrderNumber' is invalid."
        logger.info(f"@350 {LOG_ID} Booking: {booking}")
        # raise ValidationError(message)

        # Return `does not exist` url
        res_json = {"labelUrl": f"{settings.WEB_SITE_URL}/label/does-not-exist/"}
        return res_json

    # Update DE address if not booked
    if not booking.b_dateBookedDate:
        try:
            address = get_address(b_client_order_num)
        except:
            label_url = f"{settings.WEB_SITE_URL}/label/scan-failed/?reason=address"
            res_json = {"labelUrl": label_url}
            return res_json

        b_501 = address["rep_code"]
        try:
            if int(b_501) == 3:
                b_501 = "Teddybed Australia Pty Ltd"
            else:
                b_501 = ""
        except Exception as e:
            b_501 = ""

        booking.de_To_Address_Street_1 = address["street_1"]
        booking.de_To_Address_Street_2 = address["street_2"]
        booking.de_To_Address_State = address["state"]
        booking.de_To_Address_Suburb = address["suburb"]
        booking.de_To_Address_PostalCode = address["postal_code"]
        booking.deToCompanyName = address["company_name"]
        booking.de_to_Contact_F_LName = address["company_name"]
        booking.de_Email = address["email"]
        booking.de_to_Phone_Main = address["phone"]
        booking.v_customer_code = address["customer_type"]
        booking.b_client_name_sub = b_501
        booking.b_client_sales_inv_num = address["b_client_sales_inv_num"]
        booking.save()

    # Commented on 2021-07-29
    # if not booking.api_booking_quote:
    #     logger.info(f"@351 {LOG_ID} No quote! Booking: {booking}")
    #     raise Exception("Booking doens't have quote.")

    # Fetch SSCC data by using `Talend` app
    try:
        picked_items = get_picked_items(b_client_order_num, sscc)
    except:
        label_url = f"{settings.WEB_SITE_URL}/label/scan-failed/?reason=sscc"
        res_json = {"labelUrl": label_url}
        return res_json

    if sscc and not picked_items:
        message = f"Wrong SSCC - {sscc}"
        logger.info(f"@351 {LOG_ID} {message}")
        raise ValidationError(message)
    elif not sscc and not picked_items:
        message = f"No SSCC found for the Order - {b_client_order_num}"
        logger.info(f"@352 {LOG_ID} {message}")
        raise ValidationError(message)

    # Fetch original data
    pk_booking_id = booking.pk_booking_id
    lines = Booking_lines.objects.filter(fk_booking_id=pk_booking_id)
    line_datas = Booking_lines_data.objects.filter(fk_booking_id=pk_booking_id)
    original_lines = lines.exclude(e_item="Auto repacked item").filter(
        sscc__isnull=True
    )
    postal_code = booking.de_To_Address_PostalCode

    logger.info(f"@360 {LOG_ID} Booking: {booking}")
    logger.info(f"@361 {LOG_ID} Lines: {lines}")
    logger.info(f"@362 {LOG_ID} Original Lines: {original_lines}")

    # prepare save
    sscc_list = []
    for item in picked_items:
        if item["sscc"] not in sscc_list:
            sscc_list.append(item["sscc"])

    with transaction.atomic():
        # Rollback `auto repack` | `already packed` operation
        for line in lines:
            if line.sscc:
                if "NOSSCC" in line.sscc:
                    line.sscc = None
                    line.save()
                else:  # Delete prev real-sscc lines
                    line.delete()
                    # continue

        # Delete all LineData
        for line_data in line_datas:
            line_data.delete()

        # Save
        sscc_lines = {}
        new_lines = []
        for sscc in sscc_list:
            first_item = None
            for picked_item in picked_items:
                if picked_item["sscc"] == sscc:
                    first_item = picked_item
                    break

            # Create new Line
            new_line = Booking_lines()
            new_line.fk_booking_id = pk_booking_id
            new_line.pk_booking_lines_id = str(uuid.uuid4())
            new_line.e_type_of_packaging = first_item.get("package_type")
            new_line.e_qty = 1
            new_line.zbl_131_decimal_1 = 0
            new_line.e_item = "Picked Item"
            new_line.e_item_type = None
            new_line.e_dimUOM = first_item["dimensions"]["unit"]
            new_line.e_dimLength = first_item["dimensions"]["length"]
            new_line.e_dimWidth = first_item["dimensions"]["width"]
            new_line.e_dimHeight = first_item["dimensions"]["height"]
            new_line.e_weightUOM = first_item["weight"]["unit"]
            new_line.e_weightPerEach = first_item["weight"]["weight"]
            new_line.e_Total_KG_weight = round(
                new_line.e_weightPerEach * new_line.e_qty, 5
            )
            # new_line.e_1_Total_dimCubicMeter = round(
            #     get_cubic_meter(
            #         new_line.e_dimLength,
            #         new_line.e_dimWidth,
            #         new_line.e_dimHeight,
            #         new_line.e_dimUOM,
            #         new_line.e_qty,
            #     ),
            #     5,
            # )
            new_line.is_deleted = False
            new_line.zbl_102_text_2 = None
            new_line.sscc = first_item["sscc"]
            new_line.picked_up_timestamp = first_item.get("timestamp") or datetime.now()
            new_line.packed_status = Booking_lines.SCANNED_PACK
            new_line.save()
            new_lines.append(
                {
                    "e_type_of_packaging": new_line.e_type_of_packaging,
                    "e_dimUOM": new_line.e_dimUOM,
                    "e_dimLength": new_line.e_dimLength,
                    "e_dimWidth": new_line.e_dimWidth,
                    "e_dimHeight": new_line.e_dimHeight,
                    "packed_status": Booking_lines.SCANNED_PACK,
                }
            )

            if not sscc in sscc_lines:
                sscc_lines[sscc] = [new_line]
            else:
                sscc_lines[sscc].append(new_line)

            # Create new line_data(s)
            for picked_item in picked_items:
                if picked_item["sscc"] != sscc:
                    continue

                original_line = None
                for line in original_lines:
                    if line.zbl_131_decimal_1 == picked_item["items"][0]["sequence"]:
                        original_line = line

                if (
                    not original_line
                    or original_line.zbl_102_text_2 in SERVICE_GROUP_CODES
                ):
                    continue

                line_data = Booking_lines_data()
                line_data.fk_booking_id = pk_booking_id
                line_data.fk_booking_lines_id = new_line.pk_booking_lines_id
                line_data.quantity = picked_item["items"][0]["qty"]
                line_data.itemDescription = original_line.e_item
                line_data.modelNumber = original_line.e_item_type
                line_data.clientRefNumber = sscc
                line_data.itemSerialNumbers = original_line.zbl_131_decimal_1
                line_data.save()

    if booking.booking_type == "DMEP":
        set_booking_quote(booking, None)
    else:
        # Should get pricing again
        # next_biz_day = dme_time_lib.next_business_day(date.today(), 1)
        booking.puPickUpAvailFrom_Date = date.today()
        booking.client_sales_total = get_total_sales(booking.b_client_order_num)
        booking.save()

        new_fc_log = FC_Log.objects.create(
            client_booking_id=booking.b_client_booking_ref_num,
            old_quote=booking.api_booking_quote,
        )
        new_fc_log.save()
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
        _quotes = []
        best_quote = None
        if quotes:
            for quote in quotes:
                if quote.packed_status == Booking_lines.SCANNED_PACK:
                    _quotes.append(quote)
            quotes = _quotes
            _quotes = []

            if booking.is_quote_locked:
                for quote in quotes:
                    if (
                        quote.freight_provider.lower()
                        == booking.vx_freight_provider.lower()
                    ):
                        if quote.service_name:
                            if (
                                quote.service_name.lower()
                                == booking.vx_serviceName.lower()
                            ):
                                _quotes.append(quote)
                        else:
                            _quotes.append(quote)
            if (
                not isInSydneyMetro(postal_code)
                and len(new_lines) == 1
                and not is_pallet(new_lines[0]["e_type_of_packaging"])
            ):  # Allied for any single items AND out of the Sydney Metro area.
                for quote in quotes:
                    if quote.freight_provider == "Allied":
                        _quotes.append(quote)
            elif isGood4Linehaul(booking.de_To_Address_PostalCode, new_lines):
                for quote in quotes:
                    if quote.freight_provider == "Deliver-ME":
                        _quotes.append(quote)
            # All JasonL bookings to State SA should book with non-Allied
            elif booking.de_To_Address_State.upper() == "SA":
                for quote in quotes:
                    if quote.freight_provider != "Allied":
                        _quotes.append(quote)
            else:
                for quote in quotes:
                    if quote.freight_provider != "Deliver-ME":
                        _quotes.append(quote)
            quotes = _quotes or quotes

            best_quotes = select_best_options(pricings=quotes, client=client)
            logger.info(f"#373 {LOG_ID} - Selected Best Pricings: {best_quotes}")

            if best_quotes:
                best_quote = best_quotes[0]
                set_booking_quote(booking, best_quote)
                new_fc_log.new_quote = booking.api_booking_quote
                new_fc_log.save()
            else:
                set_booking_quote(booking, None)
        else:
            message = f"#521 {LOG_ID} SCAN with No Pricing! Order Number: {booking.b_client_order_num}"
            logger.error(message)

            if booking.b_client_order_num:
                send_email_to_admins("No FC result", message)

        if not booking.inv_booked_quoted:
            send_email_zero_quote(booking)

        if booking.inv_sell_quoted and booking.inv_booked_quoted and abs(booking.inv_booked_quoted - booking.inv_sell_quoted) > 50:
            send_email_variance_quote(booking)

    # Reset all Api_booking_confirmation_lines
    Api_booking_confirmation_lines.objects.filter(
        fk_booking_id=booking.pk_booking_id
    ).delete()

    # Build built-in label with SSCC - one sscc should have one page label
    try:
        file_path = (
            f"{settings.STATIC_PUBLIC}/pdfs/{booking.vx_freight_provider.lower()}_au"
        )
    except:
        label_url = f"{settings.WEB_SITE_URL}/label/scan-failed?reason=no-fp-selected"
        res_json = {"labelUrl": label_url}
        return res_json

    try:
        label_data = build_label_oper(
            booking=booking,
            file_path=file_path,
            total_qty=len(sscc_list),
            sscc_list=sscc_list,
            sscc_lines=sscc_lines,
            need_zpl=True,
        )
    except:
        label_url = (
            f"{settings.WEB_SITE_URL}/label/scan-failed?reason=failed-label-build"
        )
        res_json = {"labelUrl": label_url}
        return res_json

    if label_data["urls"]:
        entire_label_url = f"{file_path}/DME{booking.b_bookingID_Visual}.pdf"
        pdf_merge(label_data["urls"], entire_label_url)

    message = f"#379 {LOG_ID} - Successfully scanned. Booking Id: {booking.b_bookingID_Visual}"
    logger.info(message)

    booking.z_label_url = (
        f"{settings.WEB_SITE_URL}/label/{booking.b_client_booking_ref_num}/"
    )

    if not booking.b_dateBookedDate and booking.b_status != "Picked":
        status_history.create(booking, "Picked", "jason_l")

    # Set consignment number
    booking.v_FPBookingNumber = gen_consignment_num(
        booking.vx_freight_provider,
        booking.b_bookingID_Visual,
        booking.kf_client_id,
        booking,
    )
    booking.save()

    res_json = {"labelUrl": booking.z_label_url}
    return res_json


def update_via_api(booking, timestamp):
    LOG_ID = "[JASON_L STATUS UPDATE]"

    if settings.ENV != "prod":  # Test url

        url = "https://poptopdesk.com/campaign/deliverme/getDelivermeData"
    else:  # Live url
        if booking.b_client_name_sub == "Teddybed Australia Pty Ltd":
            url = "https://prnt.jasonl.com.au/teddyaustralia/Delivermewebhook/getDeliverMeData"
        else:
            url = "https://prnt.jasonl.com.au/campaign/deliverme/getDelivermeData"

    data = {
        "bookingId": booking.b_bookingID_Visual,
        "orderNumber": booking.b_client_order_num,
        "freightProvider": booking.vx_freight_provider,
        "consignmentNumber": booking.v_FPBookingNumber,
        "status": booking.b_status,
        "timestamp": timestamp,
        "b_client_booking_ref_num": booking.b_client_booking_ref_num,
    }
    code = f"DME-{booking.b_bookingID_Visual}-{booking.b_client_order_num}"
    headers = {"Authentication": sha256(code.encode("utf-8")).hexdigest()}
    logger.info(f"{LOG_ID} endpoint URL: {url}\nheaders: {headers}\npayload: {data}")
    response = requests.post(url, data=json.dumps(data), headers=headers)
    # res_data = response.json()
    logger.info(f"{LOG_ID} response: {response.text} <{response.status_code}>")
