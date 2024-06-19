import uuid
import logging
from datetime import datetime, date

from django.db import transaction

from api.models import Client_warehouses, BOK_2_lines, Pallet, DME_clients
from api.serializers import SimpleQuoteSerializer
from api.serializers_client import *
from api.common import common_times as dme_time_lib, constants as dme_constants
from api.common.build_object import Struct
from api.common.pallet import get_palletized_by_ai
from api.fp_apis.operations.pricing import pricing as pricing_oper
from api.clients.operations.index import get_suburb_state

logger = logging.getLogger(__name__)


def push_boks(payload, client, username, method):
    """
    PUSH api (bok_1, bok_2, bok_3)
    """
    LOG_ID = "[PB Standard]"  # PB - PUSH BOKS
    bok_1 = payload["booking"]
    bok_1["pk_header_id"] = str(uuid.uuid4())
    bok_2s = payload["booking_lines"]

    with transaction.atomic():
        # Save bok_1
        bok_1["fk_client_id"] = client.dme_account_num
        bok_1["x_booking_Created_With"] = "DME PUSH API"
        bok_1["success"] = dme_constants.BOK_SUCCESS_2  # Default success code

        if client.company_name == "Seaway-Tempo-Aldi":  # Seaway-Tempo-Aldi
            bok_1["b_001_b_freight_provider"] = "DHL"
        else:
            # BioPak
            warehouse = Client_warehouses.objects.get(
                client_warehouse_code=bok_1["b_client_warehouse_code"]
            )
            bok_1["client_booking_id"] = bok_1["pk_header_id"]
            bok_1["fk_client_warehouse"] = warehouse.pk_id_client_warehouses
            bok_1["b_clientPU_Warehouse"] = warehouse.name
            bok_1["b_client_warehouse_code"] = warehouse.client_warehouse_code

        if not bok_1.get("b_054_b_del_company"):
            bok_1["b_054_b_del_company"] = bok_1["b_061_b_del_contact_full_name"]

        bok_1["b_057_b_del_address_state"] = bok_1["b_057_b_del_address_state"].upper()
        bok_1["b_031_b_pu_address_state"] = bok_1["b_031_b_pu_address_state"].upper()

        bok_1_serializer = BOK_1_Serializer(data=bok_1)
        if not bok_1_serializer.is_valid():
            message = f"Serialiser Error - {bok_1_serializer.errors}"
            logger.info(f"@8811 {LOG_ID} {message}")
            raise Exception(message)

        # Save bok_2s
        for index, bok_2 in enumerate(bok_2s):
            _bok_2 = bok_2["booking_line"]
            _bok_2["fk_header_id"] = bok_1["pk_header_id"]
            _bok_2["v_client_pk_consigment_num"] = bok_1["pk_header_id"]
            _bok_2["pk_booking_lines_id"] = str(uuid.uuid1())
            _bok_2["success"] = bok_1["success"]
            _bok_2["b_093_packed_status"] = BOK_2_lines.ORIGINAL
            l_001 = _bok_2.get("l_001_type_of_packaging") or "Carton"
            _bok_2["l_001_type_of_packaging"] = l_001
            _bok_2["b_097_e_bin_number"] = _bok_2.get("b_097_e_bin_number")

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
                    message = f"Serialiser Error - {bok_2_serializer.errors}"
                    logger.info(f"@8831 {LOG_ID} {message}")
                    raise Exception(message)

        bok_1_obj = bok_1_serializer.save()

    next_biz_day = dme_time_lib.next_business_day(date.today(), 1)
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
        "b_booking_tail_lift_pickup": bok_1.get("b_019_b_pu_tail_lift") or 0,
        "b_booking_tail_lift_deliver": bok_1.get("b_041_b_del_tail_lift") or 0,
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

    if booking_lines:
        _, success, message, quotes, client = pricing_oper(
            body={"booking": booking, "booking_lines": booking_lines},
            booking_id=None,
            is_pricing_only=True,
            packed_statuses=[BOK_2_lines.ORIGINAL],
        )

        logger.info(
            f"#519 {LOG_ID} Pricing result: success: {success}, message: {message}, results cnt: {len(quotes)}"
        )

    res_json = {"success": True, "message": "Push success!"}
    return res_json
