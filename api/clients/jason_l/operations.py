import os
import re
import json
import logging
import subprocess
from datetime import datetime, date

from django.conf import settings
from django.db import transaction

from api.models import (
    FC_Log,
    BOK_1_headers,
    BOK_2_lines,
    Booking_lines,
    Pallet,
    API_booking_quotes,
    DME_clients,
    Client_Products,
)
from api.outputs.email import send_email
from api.serializers import SimpleQuoteSerializer, SurchargeSerializer
from api.common.constants import AU_STATE_ABBRS, PALLETS
from api.common.ratio import _get_dim_amount, _get_weight_amount
from api.clients.operations.index import (
    get_suburb_state,
    get_similar_suburb,
    is_postalcode_in_state,
)
from api.clients.jason_l.constants import (
    ITEM_CODES_TO_BE_IGNORED,
    LINE_TYPE_TO_BE_IGNORED,
    CHARGE_TYPE_TO_BE_IGNORED,
    ITEM_CODES_4_CUSTOMER_PICKUP,
)
from api.common.thread import background

logger = logging.getLogger(__name__)

# IS_TESTING = True  # Used for Testing
IS_TESTING = False


def _extract_address(addrs):
    logger.info(f"[_extract_address] clue: {addrs}")
    errors = []
    state, postal_code, suburb = "", "", ""

    _addrs = []
    _state = None
    for addr in addrs:
        _addr = addr.strip()
        _addrs.append(_addr)

        if len(_addr) in [3, 4] and _addr.isdigit():
            postal_code = _addr

        if _addr.upper() in AU_STATE_ABBRS:
            _state = _addr.upper()

    state, suburb = get_suburb_state(postal_code, ", ".join(_addrs))

    if not _state and not state:
        errors.append("Stop Error: Delivery state missing or misspelled")

    return errors, _state or state, postal_code, suburb


def get_address(order_num):
    """
    Get address for JasonL

    Stop Error
    Pickup address
    Stop Error: Pickup postal code and suburb mismatch. (Hint perform a Google search for the correct match)

    Stop Error
    Pickup address
    Stop Error: Pickup postal code missing

    Stop Error
    Pickup address
    Stop Error: Pickup suburb missing or misspelled

    Stop Error
    Pickup address
    Stop Error: Pickup state missing or misspelled

    Stop Error
    Delivery address
    Stop Error: Delivery postal code and suburb mismatch. (Hint perform a Google search for the correct match)

    Stop Error
    Delivery address
    Stop Error: Delivery postal code missing

    Stop Error
    Delivery address
    Stop Error: Delivery suburb missing or misspelled

    Stop Error
    Delivery address
    Stop Error: Delivery state missing or misspelled

    Stop Error
    Delivery address
    Stop Error: Delivery address contact telephone no is a standard requirement for freight providers

    Warning
    Delivery address
    Warning: Missing email for delivery address, used to advise booking status*

    Warning
    Delivery address
    Warning: Missing mobile number for delivery address, used to text booking status**
    """
    LOG_ID = "[ADDRESS CSV READER]"

    # - Split `order_num` and `suffix` -
    _order_num, suffix = order_num, ""
    iters = _order_num.split("-")

    if len(iters) > 1:
        _order_num, suffix = iters[0], iters[1]

    message = f"@350 {LOG_ID} OrderNum: {_order_num}, Suffix: {suffix}"
    logger.info(message)
    # ---

    if settings.ENV != "local":  # Only on DEV or PROD
        logger.info(f"@351 {LOG_ID} Running .sh script...")
        subprocess.run(
            [
                "/home/ubuntu/jason_l/address/src/run.sh",
                "--context_param",
                f"param1={_order_num}",
                "--context_param",
                f"param2={suffix}",
            ]
        )
        logger.info(f"@352 {LOG_ID} Finish running .sh")

    if settings.ENV == "local":
        file_path = "/Users/juli/Documents/talend_sample_data/del.csv"
    else:
        file_path = "/home/ubuntu/jason_l/address/src/del.csv"

    csv_file = open(file_path, "rb")
    csv_file = csv_file.read().decode(errors="replace")
    csv_file = csv_file.split("\n")

    logger.info(f"@350 {LOG_ID} File({file_path}) opened!")
    filtered_lines = []

    address = {
        "error": "",
        "company_name": "",
        "street_1": "",
        "street_2": "",
        "suburb": "",
        "state": "",
        "postal_code": "",
        "phone": "",
        "email": "",
        "rep_code": "",
        "reference": "",
    }

    # Priority #1: DA (Delivery Address)
    # Priority #2: CUS (Customer Contract)
    # Priority #3: DI (Delivery Instruction)
    DA_company_name, CUS_company_name, DI_company_name = None, None, None
    DA_street_1, CUS_street_1, DI_street_1 = None, None, None
    DA_suburb, CUS_suburb, DI_suburb = None, None, None
    DA_state, CUS_state, DI_state = None, None, None
    DA_postal_code, CUS_postal_code, DI_postal_code = None, None, None
    DA_phone, DI_phone = None, None
    DA_email, DI_email = None, None
    DI_inst = ""
    customer_type = None
    rep_code = None
    reference = None
    errors = []
    has_DA = False
    clue_DA, clue_CUS, clue_DI = "", "", ""
    for i, line in enumerate(csv_file):
        if i == 0:  # Ignore first header row
            continue
        if not line:  # Ignore empty string row
            continue

        line_items = line.split("|")
        type = line_items[0]
        customer_type = line_items[19]
        rep_code = line_items[20]
        reference = line_items[21]
        na_type = line_items[4]
        address["phone"] = line_items[14] if line_items[14] else address["phone"]

        if type == "SO" and na_type == "DA":  # `Delivery Address` row
            logger.info(f"@351 {LOG_ID} DA: {line}")

            DA_company_name = line_items[5]
            DA_street_1 = line_items[6]
            DA_phone = line_items[14]

            for item in line_items:
                _item = item.strip()
                email_regex = r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b"

                if re.match(email_regex, _item):
                    DA_email = _item
            try:
                clue_DA = line_items[7:14]
                errors, DA_state, DA_postal_code, DA_suburb = _extract_address(clue_DA)
            except Exception as e:
                logger.info(f"@352 {LOG_ID} Error: {str(e)}")
                pass
        elif type == "CUS" and na_type == "C":  # `Customer Contract` row
            logger.info(f"@353 {LOG_ID} CUS: {line}")

            CUS_company_name = line_items[5]
            CUS_street_1 = line_items[6]

            try:
                clue_CUS = line_items[7:14]
                errors, CUS_state, CUS_postal_code, CUS_suburb = _extract_address(
                    clue_CUS
                )
            except Exception as e:
                logger.info(f"@354 {LOG_ID} Error: {str(e)}")
                pass
        if type == "SO" and na_type == "DI":  # `Delivery Instruction` row
            logger.info(f"@351 {LOG_ID} DI: {line}")

            DI_company_name = line_items[5] or ""
            DI_street_1 = line_items[6] or ""
            DI_phone = line_items[14]
            DI_inst = f"{DI_company_name} {DI_street_1}"

            for item in line_items:
                _item = item.strip()
                email_regex = r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b"

                if re.match(email_regex, _item):
                    DI_email = _item
            try:
                clue_DI = line_items[7:14]
                errors, DI_state, DI_postal_code, DI_suburb = _extract_address(clue_DI)
            except Exception as e:
                logger.info(f"@352 {LOG_ID} Error: {str(e)}")
                pass

        if type == "CUS" and na_type == "E":
            address["email"] = line_items[5]

    if clue_DA:
        address["company_name"] = DA_company_name or ""
        address["street_1"] = DA_street_1 or ""
        address["suburb"] = DA_suburb or ""
        address["state"] = DA_state or ""
        address["postal_code"] = DA_postal_code or ""
    elif clue_CUS:
        address["company_name"] = CUS_company_name or ""
        address["street_1"] = CUS_street_1 or ""
        address["suburb"] = CUS_suburb or ""
        address["state"] = CUS_state or ""
        address["postal_code"] = CUS_postal_code or ""
    elif clue_DI:
        address["company_name"] = DI_company_name or ""
        address["street_1"] = DI_street_1 or ""
        address["suburb"] = DI_suburb or ""
        address["state"] = DI_state or ""
        address["postal_code"] = DI_postal_code or ""

    address["phone"] = DA_phone or DI_phone or address["phone"]
    address["email"] = DA_email or DI_phone or address["email"]

    if not address["postal_code"]:
        errors.append("Stop Error: Delivery postal code missing or misspelled")

    if not address["state"]:
        errors.append("Stop Error: Delivery state missing or misspelled")

    if address["state"] and address["postal_code"]:
        if not is_postalcode_in_state(address["state"], address["postal_code"]):
            errors.append(
                "Stop Error: Delivery state and postal code mismatch (Hint perform a Google search for the correct match)"
            )

    if address["state"] and not address["suburb"]:
        errors.append(
            "Stop Error: Delivery state and suburb mistmatch (Hint perform a Google search for the correct match)"
        )

    if not address["suburb"] and address["postal_code"]:
        suburb = get_similar_suburb(clue_DA or clue_CUS or clue_DI)

        if suburb:
            address["suburb"] = suburb
            errors.append("Stop Error: Delivery suburb misspelled")
        else:
            errors.append("Stop Error: Delivery suburb missing")

    if not address["phone"]:
        errors.append(
            "Warning: Missing phone number, if SMS status is desired please submit mobile number"
        )
    else:
        _phone = address["phone"]
        _phone = _phone.replace(" ", "")
        _phone = _phone.replace("+61", "")
        _phone = _phone.replace("+", "")

        if not re.match("\d{6,10}", _phone):
            errors.append("Warning: Wrong phone number")
        elif "+61" in address["phone"] and len(_phone) != 9:
            errors.append("Warning: Wrong phone number")
        elif "+61" in address["phone"] and len(_phone) == 9 and _phone[0] != "4":
            errors.append(
                "Warning: Missing mobile number for delivery address, used to text booking status"
            )
        elif not "+61" in address["phone"] and len(_phone) not in [6, 10]:
            errors.append("Warning: Wrong phone number")
        elif (
            not "+61" in address["phone"]
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
    if not address["email"]:
        if clue_DA or clue_CUS or clue_DI:
            for clue in clue_DA or clue_CUS or clue_DI:
                if "@" in clue:
                    address["email"] = clue.strip()
                    errors.append("Warning: Email is formatted incorrectly")
                    break

        if not address["email"]:
            errors.append(
                "Warning: Missing email for delivery address, used to advise booking status"
            )

    # Street 1
    if not address["street_1"] and (clue_DA or clue_CUS or clue_DI):
        for clue in clue_DA or clue_CUS or clue_DI:
            if (
                clue
                and clue.strip().upper() != address["company_name"].upper()
                and clue.strip().upper() != address["state"].upper()
                and clue.strip().upper() != address["suburb"].upper()
                and clue.strip().upper() != address["postal_code"].upper()
                and clue.strip().upper() != address["phone"].upper()
                and clue.strip().upper() != address["email"].upper()
            ):
                address["street_1"] = clue

    # Street 2
    if clue_DA or clue_CUS or clue_DI:
        street_2 = []
        for clue in clue_DA or clue_CUS or clue_DI:
            if (
                clue
                and clue.strip().upper() != address["company_name"].upper()
                and clue.strip().upper() != address["street_1"].upper()
                and clue.strip().upper() != address["state"].upper()
                and clue.strip().upper() != address["suburb"].upper()
                and clue.strip().upper() != address["postal_code"].upper()
                and clue.strip().upper() != address["phone"].upper()
                and clue.strip().upper() != address["email"].upper()
            ):
                street_2.append(clue.strip())

        if street_2:
            address["street_2"] = ", ".join(street_2)[:25]

    # Switch street_1 and _2
    if (not address["street_1"] or address["street_1"] == "\n") and address["street_2"]:
        address["street_1"] = address["street_2"]
        address["street_2"] = ""

    # if not address["street_1"]:
    #     errors.append("Stop Error: Delivery street 1 missing or misspelled")

    # Auto replacement
    if (
        address["street_1"]
        and address["street_1"].strip().upper() == "UNIT E30, 21 MORETON BAY"
    ) or (
        address["street_2"]
        and address["street_2"].strip().upper() == "UNIT E30, 21 MORETON BAY"
    ):
        address["company_name"] = "NATIONAL STORAGE"

    address["error"] = "***".join(errors)
    address["customer_type"] = customer_type
    address["rep_code"] = rep_code
    address["reference"] = reference

    if reference and reference[:3] == "TED":
        address["b_client_sales_inv_num"] = reference
    else:
        address["b_client_sales_inv_num"] = order_num

    address["de_inst"] = DI_inst
    logger.info(f"@359 {LOG_ID} {json.dumps(address, indent=2, sort_keys=True)}")
    return address


def get_bok_by_talend(bok_1):
    LOG_ID = "[FETCH BOK BY TALEND]"
    order_num = bok_1["b_client_order_num"]

    # - Split `order_num` and `suffix` -
    _order_num, suffix = order_num, ""
    iters = _order_num.split("-")

    if len(iters) > 1:
        _order_num, suffix = iters[0], iters[1]

    message = f"@380 {LOG_ID} OrderNum: {_order_num}, Suffix: {suffix}"
    logger.info(message)
    # ---

    if settings.ENV != "local":  # Only on DEV or PROD
        logger.info(f"@381 {LOG_ID} Running .sh script...")
        subprocess.run(
            [
                "/home/ubuntu/jason_l/solines/src/run.sh",
                "--context_param",
                f"param1={_order_num}",
                "--context_param",
                f"param2={suffix}",
            ]
        )
        logger.info(f"@382 {LOG_ID} Finish running .sh")

    if settings.ENV == "local":
        file_path = "/Users/juli/Documents/talend_sample_data/solines.csv"
    else:
        file_path = "/home/ubuntu/jason_l/solines/src/solines.csv"

    csv_file = open(file_path)
    logger.info(f"@383 {LOG_ID} File({file_path}) opened!")

    # Test Usage #
    if IS_TESTING:
        address = {
            "error": "Postal Code and Suburb mismatch",
            "phone": "0490001222",
            "email": "aaa@email.com",
            "street_1": "690 Ann Street",
            "street_2": "",
            "suburb": "DEE WHY",
            "state": "NSW",
            "postal_code": "2099",
            "rep_code": "097",
            "reference": "TED181079",
            "de_inst": "DE Instructions",
        }
    else:
        # get address by using `Talend` .sh script
        address = get_address(order_num)
    ##############

    line_cnt = 0
    first_line = 0
    for line in csv_file:
        first_line = line
        line_cnt += 1

    if line_cnt < 2:
        logger.info(f"@384 {LOG_ID} No enough information!")
        return None, None

    b_021 = datetime.strptime(first_line.split("|")[4], "%d-%b-%Y").strftime("%Y-%m-%d")
    b_044 = address["de_inst"]
    b_055 = address["street_1"]
    b_056 = address["street_2"]
    b_057 = address["state"]
    b_058 = address["suburb"]
    b_059 = address["postal_code"] or " "
    b_060 = "Australia"
    b_061 = address["company_name"]
    b_063 = address["email"]
    b_064 = address["phone"]
    b_066 = "Phone"  # Not provided
    b_067 = 0  # Not provided
    b_068 = "Drop at Door / Warehouse Dock"  # Not provided
    b_069 = 1  # Not provided
    b_070 = "Escalator"  # Not provided
    b_071 = 1  # Not provided
    b_096 = address["customer_type"]
    b_501 = address["rep_code"]
    reference = address["reference"]

    try:
        if int(b_501) == 3:
            b_501 = "Teddybed Australia Pty Ltd"
        else:
            b_501 = ""
    except Exception as e:
        b_501 = ""

    try:
        if reference and reference[:3] == "TED":
            inv_num = reference
        else:
            inv_num = order_num
    except Exception as e:
        inv_num = order_num

    warehouse_code = first_line.split("|")[8]
    order = {
        "b_client_order_num": order_num,
        "b_client_sales_inv_num": inv_num,
        "b_021_b_pu_avail_from_date": b_021,
        "b_044_b_del_instructions_address": b_044,
        "b_055_b_del_address_street_1": b_055,
        "b_056_b_del_address_street_2": b_056,
        "b_057_b_del_address_state": b_057,
        "b_058_b_del_address_suburb": b_058,
        "b_059_b_del_address_postalcode": b_059,
        "b_060_b_del_address_country": b_060,
        "b_061_b_del_contact_full_name": b_061,
        "b_063_b_del_email": b_063,
        "b_064_b_del_phone_main": b_064,
        "b_066_b_del_communicate_via": b_066,
        "b_067_assembly_required": b_067,
        "b_068_b_del_location": b_068,
        "b_069_b_del_floor_number": b_069,
        "b_070_b_del_floor_access_by": b_070,
        "b_071_b_del_sufficient_space": b_071,
        "b_096_v_customer_code": b_096,
        "b_501_b_client_code": b_501,
        "warehouse_code": warehouse_code,
        "zb_105_text_5": address["error"],
    }

    lines = []
    ignored_items = []
    csv_file = open(file_path)
    for i, line in enumerate(csv_file):
        if i == 0:  # Ignore first header row
            continue

        iters = line.split("|")
        ItemCode = iters[14]  #   stock_code
        OrderedQty = iters[18]  #   sol_shipped_qty
        SequenceNo = iters[2]  #   sol_line_seq
        UOMCode = iters[16]  #   sol_unit_desc

        if ItemCode and ItemCode.upper() in ITEM_CODES_TO_BE_IGNORED:
            ignored_items.append(ItemCode)
            message = f"@6410 {LOG_ID} IGNORED (LISTED ITEM) --- itemCode: {ItemCode}"
            logger.info(message)
            continue

        line = {
            "e_item_type": ItemCode,
            "description": "",
            "qty": int(float(OrderedQty)),
            "zbl_131_decimal_1": float(SequenceNo),
            "zbl_102_text_2": "_",
            "e_type_of_packaging": UOMCode,
        }
        lines.append(line)

    if ignored_items:
        order["b_010_b_notes"] = ", ".join(ignored_items)

    for prop in bok_1:
        order[prop] = bok_1[prop]

    logger.info(f"@321 {LOG_ID} result: {lines}")
    return order, lines


def sucso_handler(order_num, lines):
    """
    sucso talend app handler
    It will retrieve all the `lines` info of an `Order`

    Sample Data:
        so_order_no|so_bo_suffix|sol_line_seq|stock_code|sol_line_type|sol_chg_type|stock_group|stk_description|suc_unit_desc|unit_conversion|suc_length|suc_width|suc_height|suc_weight
        1063462|  |1.0|QDLB6168.B.WT                 |KN|K|2204|Quadro Loop Leg Bench (6P)    |EACH|1.0000|0.0000|0.0000|0.0000|0.0000
        1063462|  |2.0|MW.VS.1680WT                  |SN|D|2170|MW Top 1600x800x25mm          |CTN |1.0000|0.0000|0.0000|0.0000|0.0000
        1063462|  |2.0|MW.VS.1680WT                  |SN|D|2170|MW Top 1600x800x25mm          |EACH|1.0000|1.6000|0.0450|0.8000|23.0000
    """

    LOG_ID = "[TALEND SUCSO]"

    # - Split `order_num` and `suffix` -
    _order_num, suffix = order_num, ""
    iters = _order_num.split("-")

    if len(iters) > 1:
        _order_num, suffix = iters[0], iters[1]

    message = f"@310 {LOG_ID} OrderNum: {_order_num}, Suffix: {suffix}"
    logger.info(message)
    # ---

    if settings.ENV != "local":  # Only on DEV or PROD
        logger.info(f"@311 {LOG_ID} Running .sh script...")
        subprocess.run(
            [
                "/home/ubuntu/jason_l/sucso/src/run.sh",
                "--context_param",
                f"param1={_order_num}",
                "--context_param",
                f"param2={suffix}",
            ]
        )
        logger.info(f"@312 {LOG_ID} Finish running .sh")

    if settings.ENV == "local":
        file_path = "/Users/juli/Documents/talend_sample_data/sucso.csv"
    else:
        file_path = "/home/ubuntu/jason_l/sucso/src/sucso.csv"

    csv_file = open(file_path)
    logger.info(f"@313 {LOG_ID} File({file_path}) opened!")

    need_customer_pickup = False
    for index, csv_line in enumerate(csv_file):
        if index == 0:  # Skip header row
            continue

        iters = csv_line.split("|")
        ItemCode = iters[3].strip()

        if ItemCode.upper() in ITEM_CODES_4_CUSTOMER_PICKUP:
            need_customer_pickup = True
            break

    csv_file = open(file_path)
    new_lines = []
    for index, csv_line in enumerate(csv_file):
        if index == 0:  # Skip header row
            continue

        iters = csv_line.split("|")
        SequenceNo = int(float(iters[2]))
        ItemCode = iters[3].strip()
        LineType = iters[4].strip()
        ChargeType = iters[5].strip()
        ProductGroupCode = iters[6].strip()
        Description = iters[7].strip()
        UnitCode = iters[8]
        length = float(iters[10])
        width = float(iters[11])
        height = float(iters[12])
        weight = float(iters[13])

        if LineType and LineType.upper() in LINE_TYPE_TO_BE_IGNORED:
            message = f"@6410 {LOG_ID} IGNORED (LINE_TYPE) --- ItemCode: {ItemCode}, LineType: {LineType}"
            logger.info(message)
            continue

        if ChargeType and ChargeType.upper() in CHARGE_TYPE_TO_BE_IGNORED:
            message = f"@6410 {LOG_ID} IGNORED (LINE_TYPE) --- ItemCode: {ItemCode}, ChargeType: {ChargeType}"
            logger.info(message)
            continue

        selected_line = None
        for line in lines:
            if (
                line.get("e_item_type") == ItemCode
                and line.get("zbl_131_decimal_1") == SequenceNo
            ):
                selected_line = line

        selected_new_line_index = -1
        for i, new_line in enumerate(new_lines):
            if (
                new_line.get("e_item_type") == ItemCode
                and new_line.get("zbl_131_decimal_1") == SequenceNo
            ):
                selected_new_line_index = i

        if selected_line:
            if selected_new_line_index != -1:
                if (
                    new_lines[selected_new_line_index]["e_dimLength"]
                    and new_lines[selected_new_line_index]["e_dimWidth"]
                    and new_lines[selected_new_line_index]["e_dimHeight"]
                    and new_lines[selected_new_line_index]["e_weightPerEach"]
                ):
                    continue
                else:
                    selected_line = new_lines[selected_new_line_index]
                    new_lines.pop(selected_new_line_index)

            selected_line["description"] = Description
            selected_line["line_type"] = LineType
            selected_line["charge_type"] = ChargeType
            selected_line["zbl_102_text_2"] = ProductGroupCode
            selected_line["e_dimLength"] = length
            selected_line["e_dimWidth"] = width
            selected_line["e_dimHeight"] = height
            selected_line["e_weightPerEach"] = weight
            selected_line["e_dimUOM"] = "M"
            selected_line["e_weightUOM"] = "KG"

            if need_customer_pickup:
                selected_line["b_097_e_bin_number"] = "S070"
            else:
                selected_line["b_097_e_bin_number"] = None

            new_lines.append(selected_line)

    logger.info(f"@319 {LOG_ID} result: {new_lines}")
    return new_lines


def get_picked_items(order_num, sscc):
    """
    used to build LABEL
    """
    LOG_ID = "[SSCC CSV READER]"

    # - Split `order_num` and `suffix` -
    _order_num, suffix = order_num, ""
    iters = _order_num.split("-")

    if len(iters) > 1:
        _order_num, suffix = iters[0], iters[1]

    message = f"@300 {LOG_ID} OrderNum: {_order_num}, Suffix: {suffix}"
    logger.info(message)
    # ---

    if settings.ENV != "local":  # Only on DEV or PROD
        logger.info(f"@301 {LOG_ID} Running .sh script...")
        subprocess.run(
            [
                "/home/ubuntu/jason_l/sscc/src/run.sh",
                "--context_param",
                f"param1={_order_num}",
                "--context_param",
                f"param2={suffix}",
            ]
        )
        logger.info(f"@302 {LOG_ID} Finish running .sh")

    if settings.ENV == "local":
        file_path = "/Users/juli/Documents/talend_sample_data/sscc.csv"
    else:
        file_path = "/home/ubuntu/jason_l/sscc/src/sscc_so.csv"

    csv_file = open(file_path)
    logger.info(f"@320 {LOG_ID} File({file_path}) opened!")
    filtered_lines = []

    for i, line in enumerate(csv_file):
        line_items = line.split("|")
        order_num_csv = line_items[2].strip()
        suffix_csv = line_items[3].strip()

        if len(suffix_csv) > 0:
            order_num_csv = f"{order_num_csv}-{suffix_csv}"

        if str(order_num) == order_num_csv:
            if sscc and sscc != line_items[1].strip():
                continue

            filtered_lines.append(
                {
                    "sscc": line_items[1].strip(),
                    "timestamp": line_items[10][:19],
                    "is_repacked": True,
                    "package_type": line_items[9][:3],
                    "items": [
                        {
                            "sequence": int(float(line_items[0])),
                            "qty": int(float(line_items[4])),
                        }
                    ],
                    "dimensions": {
                        "width": float(line_items[6]),
                        "height": float(line_items[7]),
                        "length": float(line_items[5]),
                        "unit": "m",
                    },
                    "weight": {"weight": float(line_items[8]), "unit": "kg"},
                }
            )

    logger.info(f"@328 {LOG_ID} Finish reading CSV! Count: {len(filtered_lines)}")
    logger.info(f"@329 {LOG_ID} {json.dumps(filtered_lines, indent=2, sort_keys=True)}")
    return filtered_lines


def update_when_no_quote_required(old_bok_1, old_bok_2s, bok_1, bok_2s):
    """
    check if quote is required
    else update Order

    input:
        old_bok_1: Object
        old_bok_2s: Array of Object
        bok_1: Dict
        bok_2s: Array of Dict

    output:
        quote_required: Bool
    """

    if old_bok_1.b_client_warehouse_code != bok_1.get("b_client_warehouse_code"):
        return False

    if old_bok_1.b_055_b_del_address_street_1 != bok_1.get(
        "b_055_b_del_address_street_1"
    ):
        return False

    if old_bok_1.b_056_b_del_address_street_2 != bok_1.get(
        "b_056_b_del_address_street_2"
    ):
        return False

    if bok_1.get(
        "b_057_b_del_address_state"
    ) and old_bok_1.b_057_b_del_address_state != bok_1.get("b_057_b_del_address_state"):
        return False

    if bok_1.get(
        "b_058_b_del_address_suburb"
    ) and old_bok_1.b_058_b_del_address_suburb != bok_1.get(
        "b_058_b_del_address_suburb"
    ):
        return False

    if bok_1.get(
        "b_059_b_del_address_postalcode"
    ) and old_bok_1.b_059_b_del_address_postalcode != bok_1.get(
        "b_059_b_del_address_postalcode"
    ):
        return False

    if old_bok_1.b_067_assembly_required != bok_1.get("b_067_assembly_required"):
        return False

    if old_bok_1.b_068_b_del_location != bok_1.get("b_068_b_del_location"):
        return False

    if old_bok_1.b_069_b_del_floor_number != bok_1.get("b_069_b_del_floor_number"):
        return False

    if old_bok_1.b_070_b_del_floor_access_by != bok_1.get(
        "b_070_b_del_floor_access_by"
    ):
        return False

    if old_bok_1.b_071_b_del_sufficient_space != bok_1.get(
        "b_071_b_del_sufficient_space"
    ):
        return False

    for old_bok_2 in old_bok_2s:
        is_found = False

        for bok_2 in bok_2s:
            if old_bok_2.e_item_type == bok_2["e_item_type"]:
                is_found = True

                if old_bok_2.l_002_qty != bok_2["qty"]:
                    return False

        if not is_found:
            return False

    if old_bok_1.b_060_b_del_address_country != bok_1.get(
        "b_060_b_del_address_country"
    ):
        old_bok_1.b_060_b_del_address_country = bok_1.get("b_060_b_del_address_country")

    if old_bok_1.b_061_b_del_contact_full_name != bok_1.get(
        "b_061_b_del_contact_full_name"
    ):
        old_bok_1.b_061_b_del_contact_full_name = bok_1.get(
            "b_061_b_del_contact_full_name"
        )

    if old_bok_1.b_063_b_del_email != bok_1.get("b_063_b_del_email"):
        old_bok_1.b_063_b_del_email = bok_1.get("b_063_b_del_email")

    if old_bok_1.b_064_b_del_phone_main != bok_1.get("b_064_b_del_phone_main"):
        old_bok_1.b_064_b_del_phone_main = bok_1.get("b_064_b_del_phone_main")

    if old_bok_1.b_client_sales_inv_num != bok_1.get("b_client_sales_inv_num"):
        old_bok_1.b_client_sales_inv_num = bok_1.get("b_client_sales_inv_num")

    if old_bok_1.b_021_b_pu_avail_from_date != bok_1.get("b_021_b_pu_avail_from_date"):
        old_bok_1.b_021_b_pu_avail_from_date = bok_1.get("b_021_b_pu_avail_from_date")

    old_bok_1.save()
    return True


def create_or_update_product(new_product):
    LOG_ID = "[JASON_L PRODUCT]"

    products = Client_Products.objects.filter(
        fk_id_dme_client_id=21, parent_model_number=new_product["e_item_type"]
    )

    with transaction.atomic():
        if products:
            logger.info("@190 - New Product!")
            product = products.first()
        else:
            logger.info("@190 - Existing Product!")
            product = Client_Products()

        product.fk_id_dme_client_id = 21
        product.parent_model_number = new_product["e_item_type"]
        product.child_model_number = new_product["e_item_type"]
        product.description = new_product["e_item"]
        product.qty = 1
        product.e_dimUOM = new_product["e_dimUOM"]
        product.e_dimLength = new_product["e_dimLength"]
        product.e_dimWidth = new_product["e_dimWidth"]
        product.e_dimHeight = new_product["e_dimHeight"]
        product.e_weightUOM = new_product["e_weightUOM"]
        product.e_weightPerEach = new_product["e_weightPerEach"]
        product.is_ignored = new_product["is_ignored"]
        product.save()

    return product


def parse_sku_string(sku_str):
    if not sku_str:
        return []

    # Get distinct SKU array
    if "(" in sku_str:
        sku_parts = sku_str[:-1].split("(")
    else:
        sku_parts = [sku_str]

    sku_array = []
    for part in sku_parts:
        _skus = part.split("|")[0].split(",")

        for sku in _skus:
            if sku != "NONE":
                if sku not in sku_array:
                    sku_array.append(sku)

    # Get SKU array with count
    skus_with_cnt = {}
    for sku in sku_array:
        for _iter in sku_str.split(","):
            for _iter1 in _iter.split("|"):
                for _iter2 in _iter1.split("("):
                    if sku == _iter2:
                        if sku in skus_with_cnt:
                            skus_with_cnt[sku] += 1
                        else:
                            skus_with_cnt[sku] = 1

    # Formatting
    results = []
    for sku in skus_with_cnt:
        results.append({"model_number": sku, "qty": skus_with_cnt[sku]})

    return results


def isInSydneyMetro(postal_code):
    # 1000-2249, 2760-2770
    _postal_code = int(postal_code or 0)
    if _postal_code and (
        (_postal_code > 999 and _postal_code < 2250)
        or (_postal_code > 2759 and _postal_code < 2771)
    ):
        return True
    else:
        return False


def isGood4Linehaul(postal_code, booking_lines):
    """
    For DMEA price selection,
    * If the goods are in Metro areas for MEL, BRIS and ADE,
    * Bookings that have 1 or more Packing UOM = PAL OR
    * Bookings that have 1 or more other UOM with DIMS where any 2 of L, W and H are >= .5m
    Then auto select Deliver-ME Direct
    """
    _postal_code = int(postal_code or 0)
    if _postal_code and (
        (  # Metro / CBD Melbourne
            _postal_code in [3800, 3803, 3977]
            or (_postal_code >= 3000 and _postal_code <= 3207)
            or (_postal_code >= 8000 and _postal_code <= 8499)
        )
        or (  # Metro / CBD Brisbane
            (_postal_code >= 4000 and _postal_code <= 4207)
            or (_postal_code >= 9000 and _postal_code <= 9499)
        )
        or (  # Metro Adelaide
            (_postal_code >= 5000 and _postal_code <= 5199)
            or (_postal_code >= 5900 and _postal_code <= 5999)
        )
    ):
        original_lines = []

        for line in booking_lines:
            if line["packed_status"] in [
                BOK_2_lines.ORIGINAL,
                Booking_lines.SCANNED_PACK,
            ]:
                original_lines.append(line)

        pallet_cnt = 0
        big_carton_cnt = 0
        for line in original_lines:
            if line["e_type_of_packaging"].upper() in PALLETS:
                pallet_cnt += 1
            else:
                item_length = line["e_dimLength"] * _get_dim_amount(line["e_dimUOM"])
                item_width = line["e_dimWidth"] * _get_dim_amount(line["e_dimUOM"])
                item_height = line["e_dimHeight"] * _get_dim_amount(line["e_dimUOM"])

                if (
                    (item_length > 0.5 and item_width > 0.5)
                    or (item_width > 0.5 and item_height > 0.5)
                    or (item_length > 0.5 and item_height > 0.5)
                ):
                    big_carton_cnt += 1

        if pallet_cnt > 0 or big_carton_cnt > 0:
            return True

    return False


def get_total_sales(order_num):
    LOG_ID = "[FETCH BOK BY TALEND]"

    # - Split `order_num` and `suffix` -
    _order_num, suffix = order_num, ""
    iters = _order_num.split("-")

    if len(iters) > 1:
        _order_num, suffix = iters[0], iters[1]

    message = f"@380 {LOG_ID} OrderNum: {_order_num}, Suffix: {suffix}"
    logger.info(message)
    # ---

    if settings.ENV != "local":  # Only on DEV or PROD
        logger.info(f"@381 {LOG_ID} Running .sh script...")
        subprocess.run(
            [
                "/home/ubuntu/jason_l/solines/src/run.sh",
                "--context_param",
                f"param1={_order_num}",
                "--context_param",
                f"param2={suffix}",
            ]
        )
        logger.info(f"@382 {LOG_ID} Finish running .sh")

    if settings.ENV == "local":
        file_path = "/Users/juli/Documents/talend_sample_data/solines.csv"
    else:
        file_path = "/home/ubuntu/jason_l/solines/src/solines.csv"

    csv_file = open(file_path)
    logger.info(f"@383 {LOG_ID} File({file_path}) opened!")

    line_cnt = 0
    first_line = 0
    for line in csv_file:
        first_line = line
        line_cnt += 1

    if line_cnt < 2:
        logger.info(f"@384 {LOG_ID} No enough information!")
        return None, None

    value = first_line.split("|")[24]
    value = value.replace("\n", "") if value else value
    logger.info(f"@311 {LOG_ID} first_line: {first_line}\nTotal Sales: {value}")
    return 0 if not value else float(value)


def get_value_by_formula(booking_lines):
    value = 60

    for booking_line in booking_lines:
        if not booking_line.e_type_of_packaging:
            continue

        if booking_line.e_type_of_packaging.upper() in PALLETS:
            value += booking_line.e_qty * 60
        else:
            value += booking_line.e_qty * 5

    return value

@background
def send_email_zero_quote(booking):

    LOG_ID = "[JasonL 0 or no quoted $ Email]"
    subject = f"Subject 0 quoted $ for sales invoice $ ({booking.b_client_sales_inv_num})"

    message = f"""
        <html>
        <head></head>
        <body>
            <p>Hello</p>
            <div style='height:1px;'></div>
            <p>Quoting resulted in 0 or null quoted $ for</p>
            <div style='height:1px;'></div>
            <p>DME number: {booking.b_bookingID_Visual}</p>
            <p>Sales invoice number: {booking.b_client_sales_inv_num}</p>
            

            <p style='text-align:center;'>
                <a
                    style='padding:10px 20px;background: #2e6da4;color:white;border-radius:4px;text-decoration:none;'
                    href="{os.environ["WEB_SITE_URL"]}/booking?bookingId={booking.b_bookingID_Visual}"
                >
                    Click here to check on DME portal
                </a>
            </p>

            <p>For button link to work, please be sure you are logged into dme before clicking.</p>
        </body>
        </html>
    """
    # TO_EMAILS = ["adnesg@deliver-me.com.au", "dane.rose@jasonl.com.au", "dev@deliver-me.com.au"]
    TO_EMAILS = ["adnesg@deliver-me.com.au", "dev@deliver-me.com.au"]
    CC_EMAILS = ["goldj@deliver-me.com.au", "darianw@deliver-me.com.au"]
    send_email(TO_EMAILS, CC_EMAILS, [], subject, message, mime_type="html")
    logger.info(f"{LOG_ID} Sent email")

@background
def send_email_variance_quote(booking):

    LOG_ID = "[JasonL variance quote Email]"
    subject = f"Subject Booked $ variance from Quoted $ is greater than $50.00 for ({booking.b_client_sales_inv_num})"

    message = f"""
        <html>
        <head></head>
        <body>
            <p>Hello</p>
            <div style='height:1px;'></div>
            <p>Booked $ - Quoted $ = {booking.inv_booked_quoted - booking.inv_sell_quoted}</p>
            <p>DME number: {booking.b_bookingID_Visual}</p>
            <p>Sales invoice number: {booking.b_client_sales_inv_num}</p>
            

            <p style='text-align:center;'>
                <a
                    style='padding:10px 20px;background: #2e6da4;color:white;border-radius:4px;text-decoration:none;'
                    href="{os.environ["WEB_SITE_URL"]}/booking?bookingId={booking.b_bookingID_Visual}"
                >
                    Click here to check on DME portal
                </a>
            </p>

            <p>For button link to work, please be sure you are logged into dme before clicking.</p>
        </body>
        </html>
    """
    # TO_EMAILS = ["adnesg@deliver-me.com.au", "dane.rose@jasonl.com.au", "dev@deliver-me.com.au"]
    TO_EMAILS = ["adnesg@deliver-me.com.au", "dev@deliver-me.com.au"]
    CC_EMAILS = ["goldj@deliver-me.com.au", "darianw@deliver-me.com.au"]
    send_email(TO_EMAILS, CC_EMAILS, [], subject, message, mime_type="html")
    logger.info(f"{LOG_ID} Sent email")

