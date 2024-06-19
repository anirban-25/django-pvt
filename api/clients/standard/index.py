import uuid
import logging
from datetime import datetime, date

from django.db import transaction

from api.models import Client_warehouses, BOK_2_lines, Pallet, DME_clients
from api.serializers import SimpleQuoteSerializer
from api.serializers_client import *
from api.common import time as dme_time_lib, constants as dme_constants
from api.common.build_object import Struct
from api.common.pallet import get_palletized_by_ai
from api.fp_apis.operations.pricing import pricing as pricing_oper
from api.clients.operations.index import get_suburb_state

logger = logging.getLogger(__name__)


def quick_pricing(payload):
    # mocking data
    # import time

    # time.sleep(3)
    # return [
    #     {
    #         "cost_id": 29325,
    #         "client_mu_1_minimum_values": 411.27261252344,
    #         "cost": 411.27,
    #         "surcharge_total": 0,
    #         "surcharge_total_cl": 0,
    #         "client_customer_mark_up": 0,
    #         "eta": "2 days",
    #         "service_name": "Standard",
    #         "fp_name": "NORTHLINE",
    #         "cost_dollar": 352.63,
    #         "fuel_levy_base_cl": 58.64240372344,
    #         "mu_percentage_fuel_levy": 0.1663,
    #         "vehicle_name": "",
    #         "packed_status": "original",
    #         "eta_in_hour": 48.0,
    #     },
    #     {
    #         "cost_id": 29325,
    #         "client_mu_1_minimum_values": 411.27261252344,
    #         "cost": 411.27,
    #         "surcharge_total": 0,
    #         "surcharge_total_cl": 0,
    #         "client_customer_mark_up": 0,
    #         "eta": "2 days",
    #         "service_name": "Standard",
    #         "fp_name": "NORTHLINE",
    #         "cost_dollar": 352.63,
    #         "fuel_levy_base_cl": 58.64240372344,
    #         "mu_percentage_fuel_levy": 0.1663,
    #         "vehicle_name": "",
    #         "packed_status": "auto",
    #         "eta_in_hour": 48.0,
    #     },
    # ]

    LOG_ID = "[PP Jason L]"
    booking = payload["booking"]
    lines = payload["booking_lines"]
    client_pk = payload["clientId"]
    pk_header_id = str(uuid.uuid4())
    json_results = []

    # Get Client
    client = DME_clients.objects.get(pk=client_pk)

    # Check if has lines
    if lines and len(lines) == 0:
        message = "Line items are required."
        logger.info(f"@815 {LOG_ID} {message}")
        raise Exception(message)

    # `auto_repack` logic
    carton_cnt = 0
    need_palletize = False
    for line in lines:
        carton_cnt += int(line["e_qty"])

    if carton_cnt > 2:
        message = "Auto repacking..."
        logger.info(f"@8130 {LOG_ID} {message}")

        # Select suitable pallet and get required pallets count
        pallets = Pallet.objects.all()
        booking_lines = []
        for line in lines:
            booking_lines.append(Struct(**line))
        palletized, non_palletized = get_palletized_by_ai(booking_lines, pallets)
        logger.info(
            f"@8831 {LOG_ID} Palletized: {palletized}\nNon-Palletized: {non_palletized}"
        )

        # Create one PAL bok_2
        for item in non_palletized:  # Non Palletized
            line_obj = item["line_obj"]
            line = {}
            line["e_type_of_packaging"] = "PAL"
            line["e_qty"] = item["quantity"]
            line["e_dimUOM"] = line_obj.e_dimUOM
            line["e_dimLength"] = line_obj.e_dimLength
            line["e_dimWidth"] = line_obj.e_dimWidth
            line["e_dimHeight"] = line_obj.e_dimHeight
            line["e_weightPerEach"] = line_obj.e_weightPerEach
            line["e_weightUOM"] = line_obj.e_weightUOM
            line["is_deleted"] = False
            line["packed_status"] = BOK_2_lines.AUTO_PACK
            lines.append(line)

        for palletized_item in palletized:  # Palletized
            pallet = pallets[palletized_item["pallet_index"]]

            total_weight = 0
            for _iter in palletized_item["lines"]:
                line_in_pallet = _iter["line_obj"]
                total_weight += (
                    line_in_pallet.e_weightPerEach
                    * _iter["quantity"]
                    / palletized_item["quantity"]
                )

            new_line = {}
            new_line["e_type_of_packaging"] = "PAL"
            new_line["e_qty"] = palletized_item["quantity"]
            new_line["e_item"] = "Auto repacked item"
            new_line["e_dimUOM"] = "mm"
            new_line["e_dimLength"] = pallet.length
            new_line["e_dimWidth"] = pallet.width
            new_line["e_dimHeight"] = palletized_item["packed_height"] * 1000
            new_line["e_weightPerEach"] = round(total_weight, 2)
            new_line["e_weightUOM"] = "KG"
            new_line["is_deleted"] = False
            new_line["packed_status"] = BOK_2_lines.AUTO_PACK
            lines.append(new_line)

    # Get next business day
    next_biz_day = dme_time_lib.next_business_day(date.today(), 1)
    booking = {
        "kf_client_id": client.dme_account_num,
        "client_warehouse_code": "No - Warehouse",
        "b_client_name": client.company_name,
        "pk_booking_id": pk_header_id,
        "puPickUpAvailFrom_Date": next_biz_day,
        "b_clientReference_RA_Numbers": "initial_RA_num",
        "puCompany": "PU Company",
        "pu_Contact_F_L_Name": "initial_PU_contact",
        "pu_Email": "pu@email.com",
        "pu_Phone_Main": "419294339",
        "pu_Address_Street_1": "PU Street 1",
        "pu_Address_street_2": "PU Street 2",
        "pu_Address_Country": "Australia",
        "pu_Address_Suburb": booking["pu_Address_Suburb"],
        "pu_Address_PostalCode": booking["pu_Address_PostalCode"],
        "pu_Address_State": booking["pu_Address_State"],
        "pu_Address_Type": "business",
        "deToCompanyName": "initial_DE_company",
        "de_to_Contact_F_LName": "initial_DE_contact",
        "de_Email": "de@email.com",
        "de_to_Phone_Main": "419294339",
        "de_To_Address_Street_1": "DE Street 1",
        "de_To_Address_Street_2": "DE Street 2",
        "de_To_Address_Country": "Australia",
        "de_To_Address_Suburb": booking["de_To_Address_Suburb"],
        "de_To_Address_PostalCode": booking["de_To_Address_PostalCode"],
        "de_To_Address_State": booking["de_To_Address_State"],
        "de_To_AddressType": "business",
        "b_booking_tail_lift_pickup": 0,
        "b_booking_tail_lift_deliver": 0,
        "vx_serviceName": "exp",
        "pu_no_of_assists": booking.get("b_072_b_pu_no_of_assists") or 0,
        "de_no_of_assists": booking.get("b_073_b_del_no_of_assists") or 0,
        "b_booking_project": None,
    }

    booking_lines = []
    for index, line in enumerate(lines):
        booking_line = {
            "pk_lines_id": index,
            "e_type_of_packaging": line["e_type_of_packaging"] or "Carton",
            "fk_booking_id": pk_header_id,
            "e_qty": int(line["e_qty"]),
            "e_item": f"item-{index}",
            "e_dimUOM": line["e_dimUOM"],
            "e_dimLength": float(line["e_dimLength"]),
            "e_dimWidth": float(line["e_dimWidth"]),
            "e_dimHeight": float(line["e_dimHeight"]),
            "e_weightUOM": line["e_weightUOM"],
            "e_weightPerEach": float(line["e_weightPerEach"]),
            "packed_status": line.get("packed_status") or BOK_2_lines.ORIGINAL,
        }
        booking_lines.append(booking_line)

    _, success, message, quotes, client = pricing_oper(
        body={"booking": booking, "booking_lines": booking_lines},
        booking_id=None,
        is_pricing_only=True,
        packed_statuses=[BOK_2_lines.ORIGINAL, BOK_2_lines.AUTO_PACK],
    )

    logger.info(
        f"#519 {LOG_ID} Pricing result: success: {success}, message: {message}, results cnt: {len(quotes)}"
    )

    # Select best quotes(fastest, lowest)
    if quotes:
        quotes.sort(key=lambda x: x.client_mu_1_minimum_values)
        context = {"client_customer_mark_up": client.client_mark_up_percent}
        json_results = SimpleQuoteSerializer(quotes, many=True, context=context).data
        json_results = dme_time_lib.beautify_eta(json_results, quotes, None)

        for quote in quotes:
            quote.delete()

    if json_results:
        logger.info(f"@818 {LOG_ID} Success!")
        return json_results
    else:
        logger.info(f"@819 {LOG_ID} Failure!")
        return json_results


def push_boks(payload, client):
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

    res_json = {"success": True, "message": "Push success!"}
    return res_json
