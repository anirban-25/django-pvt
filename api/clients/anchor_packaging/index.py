import re
import os
import json
import uuid
import logging
from datetime import datetime, date
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
)
from api.common.pallet import get_number_of_pallets, get_palletized_by_ai
from api.fp_apis.utils import (
    select_best_options,
    auto_select_pricing_4_bok,
    gen_consignment_num,
)
from api.clients.operations.index import (
    get_suburb_state,
    get_similar_suburb,
    is_postalcode_in_state,
    is_suburb_in_postalcode,
)

# from api.fp_apis.operations.book import book as book_oper
from api.fp_apis.operations.pricing import pricing as pricing_oper
from api.operations.email_senders import send_email_to_admins
from api.operations.booking_line import index as line_oper
from api.clients.operations.index import get_warehouse, check_port_code
from api.helpers.cubic import get_cubic_meter
from api.convertors.pdf import pdf_merge
from api.clients.anchor_packaging.constants import WAREHOUSE_MAPPINGS, AP_FREIGHTS
from api.warehouses.index import push as push_to_warehouse


logger = logging.getLogger(__name__)


def collect_errors(bok_1):
    errors = []

    pu_street1 = bok_1.get("b_029_b_pu_address_street_1")
    pu_street2 = bok_1.get("b_030_b_pu_address_street_2")
    pu_state = bok_1.get("b_031_b_pu_address_state")
    pu_postal = bok_1.get("b_033_b_pu_address_postalcode")
    pu_suburb = bok_1.get("b_032_b_pu_address_suburb")
    pu_phone = bok_1.get("b_038_b_pu_phone_main")
    pu_email = bok_1.get("b_037_b_pu_email")

    de_street1 = bok_1.get("b_055_b_del_address_street_1")
    de_street2 = bok_1.get("b_056_b_del_address_street_2")
    de_state = bok_1.get("b_057_b_del_address_state")
    de_postal = bok_1.get("b_059_b_del_address_postalcode")
    de_suburb = bok_1.get("b_058_b_del_address_suburb")
    de_phone = bok_1.get("b_064_b_del_phone_main")
    de_email = bok_1.get("b_063_b_del_email")

    # Entity name
    if not bok_1.get("b_028_b_pu_company"):
        errors.append("Stop Error: Pickup entity missing")
    if not bok_1.get("b_054_b_del_company"):
        errors.append("Stop Error: Delivery entity missing")

    # Street
    if not (pu_street1 or pu_street2):
        errors.append("Stop Error: Pickup street missing")
    if not (de_street1 or de_street2):
        errors.append("Stop Error: Delivery street missing")

    # State
    if not pu_state:
        errors.append("Stop Error: Pickup state missing or misspelled")
    if not de_state:
        errors.append("Stop Error: Delivery state missing or misspelled")

    # Postal Code
    if not pu_postal:
        errors.append("Stop Error: Pickup postal code missing or misspelled")
    if not de_postal:
        errors.append("Stop Error: Delivery postal code missing or misspelled")

    # Suburb
    if not pu_suburb:
        errors.append("Stop Error: Pickup suburb missing or misspelled")
    if not de_suburb:
        errors.append("Stop Error: Delivery suburb missing or misspelled")

    # State & Postal Code
    if pu_state and pu_postal:
        if not is_postalcode_in_state(pu_state, pu_postal):
            errors.append(
                "Stop Error: Pickup state and postal code mismatch (Hint perform a Google search for the correct match)"
            )
    if de_state and de_postal:
        if not is_postalcode_in_state(de_state, de_postal):
            errors.append(
                "Stop Error: Delivery state and postal code mismatch (Hint perform a Google search for the correct match)"
            )

    # Postal Code & Suburb
    if pu_postal and pu_suburb:
        if not is_suburb_in_postalcode(pu_postal, pu_suburb):
            errors.append(
                "Stop Error: Pickup postal code and suburb mismatch (Hint perform a Google search for the correct match)"
            )
    if de_postal and de_suburb:
        if not is_suburb_in_postalcode(de_postal, de_suburb):
            errors.append(
                "Stop Error: Delivery postal code and suburb mismatch (Hint perform a Google search for the correct match)"
            )

    # Phone
    if not pu_phone:
        errors.append(
            "Warning: Missing Pickup phone number, if SMS status is desired please submit mobile number"
        )
    else:
        _phone = pu_phone
        _phone = _phone.replace(" ", "")
        _phone = _phone.replace("+61", "")
        _phone = _phone.replace("+", "")

        if not re.match("\d{6,10}", _phone):
            errors.append("Warning: Wrong phone number")
        elif "+61" in pu_phone and len(_phone) != 9:
            errors.append("Warning: Wrong phone number")
        elif "+61" in pu_phone and len(_phone) == 9 and _phone[0] != "4":
            errors.append(
                "Warning: Missing mobile number for pickup address, used to text booking status"
            )
        elif not "+61" in pu_phone and len(_phone) not in [6, 10]:
            errors.append("Warning: Wrong phone number")
        elif (
            not "+61" in pu_phone
            and len(_phone) == 10
            and (_phone[0] != "0" or _phone[1] != "4")
        ):
            errors.append(
                "Warning: Missing mobile number for pickup address, used to text booking status"
            )
        elif not "+61" in pu_phone and len(_phone) == 6:
            errors.append(
                "Warning: Missing mobile number for pickup address, used to text booking status"
            )
    if not de_phone:
        errors.append(
            "Warning: Missing Delivery phone number, if SMS status is desired please submit mobile number"
        )
    else:
        _phone = de_phone
        _phone = _phone.replace(" ", "")
        _phone = _phone.replace("+61", "")
        _phone = _phone.replace("+", "")

        if not re.match("\d{6,10}", _phone):
            errors.append("Warning: Wrong phone number")
        elif "+61" in de_phone and len(_phone) != 9:
            errors.append("Warning: Wrong phone number")
        elif "+61" in de_phone and len(_phone) == 9 and _phone[0] != "4":
            errors.append(
                "Warning: Missing mobile number for delivery address, used to text booking status"
            )
        elif not "+61" in de_phone and len(_phone) not in [6, 10]:
            errors.append("Warning: Wrong phone number")
        elif (
            not "+61" in de_phone
            and len(_phone) == 10
            and (_phone[0] != "0" or _phone[1] != "4")
        ):
            errors.append(
                "Warning: Missing mobile number for delivery address, used to text booking status"
            )
        elif not "+61" in address["phone"] and len(_phone) == 6:
            errors.append(
                "Warning: Missing mobile number for delivery address, used to text booking status"
            )

    # Email
    if not pu_email:
        errors.append(
            "Warning: Missing email for pickup address, used to advise booking status"
        )
    if not de_email:
        errors.append(
            "Warning: Missing email for delivery address, used to advise booking status"
        )

    has_error = False
    for error in errors:
        if "Stop Error" in error:
            has_error = True

    return has_error, "***".join(errors)


def push_boks(payload, client, username, method):
    """
    PUSH api (bok_1, bok_2, bok_3)
    """
    LOG_ID = "[PUSH FROM AP]"  # AP - Anchor Packaging
    bok_1 = payload["booking"]
    bok_2s = payload["booking_lines"]
    client_name = None
    old_quote = None
    best_quotes = None
    json_results = []

    # Strip data
    order_num = bok_1["b_client_sales_inv_num"].strip()
    inv_num = bok_1["b_client_order_num"].strip()
    bok_1["b_client_order_num"] = order_num
    bok_1["b_client_sales_inv_num"] = inv_num
    bok_1["shipping_type"] = bok_1.get("shipping_type", "DMEM").strip()
    bok_1["b_053_b_del_address_type"] = (
        bok_1.get("b_053_b_del_delivery_type", "").strip().lower()
    )

    if not bok_1["b_053_b_del_address_type"] in ["business", "residential"]:
        bok_1["b_053_b_del_address_type"] == "business"

    if not "DME" in bok_1["shipping_type"]:
        bok_1["shipping_type"] = None

    # Warehouse
    warehouse_code = bok_1.get("b_client_warehouse_code")

    if warehouse_code in WAREHOUSE_MAPPINGS:
        bok_1["b_client_warehouse_code"] = WAREHOUSE_MAPPINGS[warehouse_code]
        warehouse = get_warehouse(client, code=bok_1["b_client_warehouse_code"])
        bok_1["fk_client_warehouse"] = warehouse.pk
        bok_1["b_clientPU_Warehouse"] = warehouse.name
    else:
        send_email_to_admins(
            f"Unknown warehouse - {warehouse_code}",
            "Customer Service team,\n\nPlease check this order.\n\nRegards,\n\nFrom DME API",
        )

    # Temporary population
    bok_1["b_068_b_del_location"] = "Pickup at Door / Warehouse Dock"
    bok_1["b_069_b_del_floor_number"] = 0
    bok_1["b_072_b_pu_no_of_assists"] = 0
    bok_1["b_070_b_del_floor_access_by"] = "Elevator"
    bok_1["b_027_b_pu_address_type"] = bok_1["b_027_b_pu_address_type"].lower()

    # Check duplicated push with `b_client_order_num`
    selected_quote = None
    if method == "POST":
        order_num = bok_1.get("b_client_sales_inv_num")
        inv_num = bok_1.get("b_client_order_num")

        bok_1_objs = BOK_1_headers.objects.filter(
            fk_client_id=client.dme_account_num,
            b_client_sales_inv_num=order_num,
        )

        if bok_1_objs.exists():
            message = f"Order(b_client_order_num={bok_1['b_client_order_num']}) does already exist."
            logger.info(f"@884 {LOG_ID} {message}")

            json_res = {
                "status": False,
                "message": f"Order(b_client_order_num={bok_1['b_client_order_num']}) does already exist.",
            }

            if int(bok_1_objs.first().success) == dme_constants.BOK_SUCCESS_3:  # Update
                # Update already pushed data
                for bok_1_obj in bok_1_objs:
                    if bok_1_obj.b_client_order_num:
                        bok_1_obj.b_client_order_num = (
                            bok_1_obj.b_client_order_num + "_old"
                        )
                    if bok_1_obj.b_client_sales_inv_num:
                        bok_1_obj.b_client_sales_inv_num = (
                            bok_1_obj.b_client_sales_inv_num + "_old"
                        )
                    bok_1_obj.save()
            else:
                # Return status page url
                url = f"{settings.WEB_SITE_URL}/status/{bok_1_objs.first().client_booking_id}/"
                json_res["pricePageUrl"] = url
                logger.info(f"@886 {LOG_ID} Response: {json_res}")
                return json_res

    bok_1["pk_header_id"] = str(uuid.uuid4())

    # Generate `client_booking_id`
    client_booking_id = f"{bok_1['b_client_order_num']}_{bok_1['pk_header_id']}_{datetime.strftime(datetime.utcnow(), '%s')}"
    bok_1["client_booking_id"] = client_booking_id

    bok_1["fk_client_id"] = client.dme_account_num
    bok_1["x_booking_Created_With"] = "DME PUSH API"
    bok_1["success"] = dme_constants.BOK_SUCCESS_2  # Default success code
    bok_1["b_092_booking_type"] = bok_1.get("shipping_type")
    bok_1["success"] = dme_constants.BOK_SUCCESS_3

    if warehouse_code in WAREHOUSE_MAPPINGS:
        if not bok_1.get("b_028_b_pu_company"):
            bok_1["b_028_b_pu_company"] = warehouse.name

        if not bok_1.get("b_035_b_pu_contact_full_name"):
            bok_1["b_035_b_pu_contact_full_name"] = warehouse.contact_name

        # if not bok_1.get("b_037_b_pu_email"):
        #     bok_1["b_037_b_pu_email"] = warehouse.contact_email

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

    if not bok_1.get("b_061_b_del_contact_full_name"):
        bok_1["b_061_b_del_contact_full_name"] = bok_1["b_054_b_del_company"]

    bok_1["b_031_b_pu_address_state"] = bok_1["b_031_b_pu_address_state"].upper()
    next_biz_day = dme_time_lib.next_business_day(date.today(), 1)
    bok_1["b_021_b_pu_avail_from_date"] = (
        bok_1.get("b_021_b_pu_avail_from_date") or next_biz_day
    )

    bok_1["b_500_b_client_cust_job_code"] = bok_1.get("b_500_b_client_cust_job_code")

    has_error, bok_1["zb_105_text_5"] = collect_errors(bok_1)

    bok_1_serializer = BOK_1_Serializer(data=bok_1)

    if not bok_1_serializer.is_valid():
        message = f"Serialiser Error - {bok_1_serializer.errors}"
        logger.info(f"@8821 {LOG_ID} {message}")
        raise Exception(message)

    # Save bok_2s (Product & Child items)
    bok_2_objs = []
    new_bok_2s = []

    with transaction.atomic():
        for index, bok_2 in enumerate(bok_2s):
            _item = bok_2["booking_line"]
            line = {}
            line["fk_header_id"] = bok_1["pk_header_id"]
            line["v_client_pk_consigment_num"] = bok_1["pk_header_id"]
            line["pk_booking_lines_id"] = str(uuid.uuid1())
            line["success"] = bok_1["success"]
            line["l_001_type_of_packaging"] = _item["l_001_type_of_packaging"]
            line["l_002_qty"] = _item["l_002_qty"]
            line["l_003_item"] = _item["l_003_item"]
            line["l_004_dim_UOM"] = _item["l_004_dim_UOM"].upper()
            line["l_005_dim_length"] = _item["l_005_dim_length"]
            line["l_006_dim_width"] = _item["l_006_dim_width"]
            line["l_007_dim_height"] = _item["l_007_dim_height"]
            line["l_009_weight_per_each"] = _item["l_009_weight_per_each"]
            line["l_008_weight_UOM"] = _item["l_008_weight_UOM"].upper()
            line["b_093_packed_status"] = BOK_2_lines.ORIGINAL

            line = line_oper.handle_zero(line, client)
            bok_2_serializer = BOK_2_Serializer(data=line)
            if bok_2_serializer.is_valid():
                bok_2_obj = bok_2_serializer.save()
                bok_2_objs.append(bok_2_obj)
                new_bok_2s.append({"booking_line": line})
            else:
                message = f"Serialiser Error - {bok_2_serializer.errors}"
                logger.info(f"@8831 {LOG_ID} {message}")
                raise Exception(message)

        bok_1_obj = bok_1_serializer.save()
        bok_2s = new_bok_2s

    # create status history
    status_history.create_4_bok(
        bok_1["pk_header_id"], "Imported / Integrated", username
    )

    if not has_error and (True or bok_1["b_092_booking_type"]):
        # `auto_repack` logic
        carton_cnt = 0
        for bok_2_obj in bok_2_objs:
            carton_cnt += bok_2_obj.l_002_qty

        if carton_cnt >= 10:
            message = "Auto repacking..."
            logger.info(f"@8130 {LOG_ID} {message}")

            # Select suitable pallet and get required pallets count
            pallets = Pallet.objects.all()

            # Anchor Packaging special
            if bok_1_obj.fk_client_id == "49294ca3-2adb-4a6e-9c55-9b56c0361953":
                pallets = pallets.filter(pk=10)

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
                line["l_001_type_of_packaging"] = "PAL"
                line["l_002_qty"] = item["quantity"]
                line["l_003_item"] = line_obj.l_003_item
                line["l_004_dim_UOM"] = line_obj.l_004_dim_UOM
                line["l_005_dim_length"] = line_obj.l_005_dim_length
                line["l_006_dim_width"] = line_obj.l_006_dim_width
                line["l_007_dim_height"] = line_obj.l_007_dim_height
                line["l_009_weight_per_each"] = line_obj.l_009_weight_per_each
                line["l_008_weight_UOM"] = line_obj.l_008_weight_UOM
                line["is_deleted"] = line_obj.is_deleted
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
                new_line["l_009_weight_per_each"] = round(total_weight, 2)
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
                        bok_3["ld_001_qty"] = line.l_002_qty
                        bok_3["ld_003_item_description"] = line.l_003_item
                        bok_3["ld_002_model_number"] = line.e_item_type
                        bok_3["zbld_121_integer_1"] = line.zbl_131_decimal_1  # Sequence
                        bok_3["zbld_122_integer_2"] = _iter["quantity"]
                        bok_3["zbld_131_decimal_1"] = line.l_005_dim_length
                        bok_3["zbld_132_decimal_2"] = line.l_006_dim_width
                        bok_3["zbld_133_decimal_3"] = line.l_007_dim_height
                        bok_3["zbld_134_decimal_4"] = round(
                            line.l_009_weight_per_each, 2
                        )
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
            bok_1_obj.save()

        # Get Pricings
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
        }

        booking_lines = []
        for bok_2 in bok_2s:
            _bok_2 = bok_2["booking_line"]
            bok_2_line = {
                "fk_booking_id": _bok_2["fk_header_id"],
                "pk_lines_id": _bok_2["fk_header_id"],
                "e_type_of_packaging": _bok_2["l_001_type_of_packaging"],
                "e_qty": _bok_2["l_002_qty"],
                "e_item": _bok_2["l_003_item"],
                "e_dimUOM": _bok_2["l_004_dim_UOM"],
                "e_dimLength": _bok_2["l_005_dim_length"],
                "e_dimWidth": _bok_2["l_006_dim_width"],
                "e_dimHeight": _bok_2["l_007_dim_height"],
                "e_weightUOM": _bok_2["l_008_weight_UOM"],
                "e_weightPerEach": _bok_2["l_009_weight_per_each"],
                "packed_status": _bok_2["b_093_packed_status"],
            }
            booking_lines.append(bok_2_line)

        fc_log, _ = FC_Log.objects.get_or_create(
            client_booking_id=bok_1["client_booking_id"],
            old_quote__isnull=True,
            new_quote__isnull=True,
        )
        # fc_log.old_quote = old_quote
        body = {"booking": booking, "booking_lines": booking_lines}
        quotes = []

        if booking_lines:
            _, success, message, quotes, client = pricing_oper(
                body=body,
                booking_id=None,
                is_pricing_only=True,
                packed_statuses=[Booking_lines.ORIGINAL, Booking_lines.AUTO_PACK],
            )
            logger.info(
                f"#519 {LOG_ID} Pricing result: success: {success}, message: {message}, results cnt: {len(quotes)}"
            )

            _quotes = []
            if selected_quote:
                if selected_quote.freight_provider == "Deliver-ME":
                    for quote in quotes:
                        if (
                            quote.freight_provider == selected_quote.freight_provider
                            and quote.packed_status == Booking_lines.ORIGINAL
                        ):
                            quotes = [quote]
                            break
                else:
                    for quote in quotes:
                        if (
                            quote.freight_provider == selected_quote.freight_provider
                            and quote.service_name == selected_quote.service_name
                        ):
                            quotes = [quote]
                            break
            # All jobs to SA state should use DME quote
            elif (
                booking["de_To_Address_State"]
                and booking["de_To_Address_State"].upper() == "SA"
            ):
                for quote in quotes:
                    if quote.freight_provider in AP_FREIGHTS:
                        continue
                    _quotes.append(quote)
                quotes = _quotes

        # Select best quotes(fastest, lowest)
        if quotes:
            auto_select_pricing_4_bok(
                bok_1=bok_1_obj,
                pricings=quotes,
                is_from_script=False,
                auto_select_type=1,
                client=client,
            )

            if len(quotes):
                best_quotes = select_best_options(pricings=quotes, client=client)
            else:
                best_quotes = quotes

            logger.info(f"#520 {LOG_ID} Selected Best Pricings: {best_quotes}")

            if len(best_quotes) > 0:
                context = {"client_customer_mark_up": client.client_customer_mark_up}
                json_results = Simple4ProntoQuoteSerializer(
                    best_quotes, many=True, context=context
                ).data
                json_results = dme_time_lib.beautify_eta(
                    json_results, best_quotes, client
                )

                # if bok_1["success"] == dme_constants.BOK_SUCCESS_4:
                best_quote = best_quotes[0]
                bok_1_obj.b_003_b_service_name = best_quote.service_name
                bok_1_obj.b_001_b_freight_provider = best_quote.freight_provider
                bok_1_obj.b_002_b_vehicle_type = (
                    best_quote.vehicle.description if best_quote.vehicle else None
                )
                bok_1_obj.save()
                fc_log.new_quote = best_quotes[0]
                fc_log.save()

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

    # Response
    if json_results or not bok_1["shipping_type"]:
        if warehouse_code != "AP_HQ" and inv_num:
            push_to_warehouse(bok_1_obj)

        logger.info(f"@8838 {LOG_ID} success: True, 201_created")
        result = {"success": True, "results": json_results}
        url = f"{settings.WEB_SITE_URL}/price/{bok_1['client_booking_id']}/"
        result["pricePageUrl"] = url
        return result
    else:
        # Inform to admins
        message = f"#521 {LOG_ID} No Pricing results to select - BOK_1 pk_header_id: {bok_1['pk_header_id']}\nOrder Number: {bok_1['b_client_order_num']}"
        logger.error(message)
        # send_email_to_admins("No FC result", message)

        message = (
            "Pricing cannot be returned due to incorrect address/lines information."
        )
        logger.info(f"@8839 {LOG_ID} {message}")
        url = f"{settings.WEB_SITE_URL}/price/{bok_1['client_booking_id']}/"

        result = {"success": True, "results": json_results}
        result["pricePageUrl"] = url
        logger.info(f"@8837 {LOG_ID} success: True, 201_created")
        return result
