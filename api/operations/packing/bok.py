import uuid
import logging

from django.db.models import Q

from api.models import (
    BOK_1_headers,
    BOK_2_lines,
    BOK_3_lines_data,
    Pallet,
    API_booking_quotes,
)
from api.serializers_client import BOK_2_Serializer, BOK_3_Serializer
from api.common.pallet import get_palletized_by_ai, get_number_of_pallets
from api.clients.jason_l.constants import SERVICE_GROUP_CODES

logger = logging.getLogger(__name__)


def auto_repack(bok_1, repack_status, pallet_id, client):
    LOG_ID = "[BOK AUTO REPACK]"  # Bok Auto Repack
    new_bok_2s = []

    # Get Boks
    bok_2s = BOK_2_lines.objects.filter(fk_header_id=bok_1.pk_header_id)
    bok_3s = BOK_3_lines_data.objects.filter(fk_header_id=bok_1.pk_header_id)

    # Delete existing Bok_2s and Bok_3s
    bok_2s.filter(l_003_item="Auto repacked item").delete()
    bok_3s.delete()
    bok_2s = BOK_2_lines.objects.filter(fk_header_id=bok_1.pk_header_id).exclude(
        zbl_102_text_2__in=SERVICE_GROUP_CODES
    )

    # Get Pallet
    if pallet_id == -1:  # Use DME AI for Palletizing
        # Select suitable pallet and get required pallets count
        pallets = Pallet.objects.all()

        # Anchor Packaging special
        if bok_1.fk_client_id == "49294ca3-2adb-4a6e-9c55-9b56c0361953":
            pallets = pallets.filter(pk=10)

        palletized, non_palletized = get_palletized_by_ai(bok_2s, pallets)
        logger.info(f"@8831 {LOG_ID} {palletized}\n{non_palletized}")

        # Create one PAL bok_2
        for item in non_palletized:  # Non-Palletized
            for bok_2 in bok_2s:
                if bok_2 == item["line_obj"]:
                    bok_2.pk = None
                    bok_2.l_002_qty = item["quantity"]
                    bok_2.b_093_packed_status = BOK_2_lines.AUTO_PACK
                    bok_2.save()
                    new_bok_2s.append(bok_2)

        for palletized_item in palletized:  # Palletized
            pallet = pallets[palletized_item["pallet_index"]]

            total_weight = 0
            for _iter in palletized_item["lines"]:
                line_in_pallet = _iter["line_obj"]
                total_weight += (
                    line_in_pallet.l_009_weight_per_each * line_in_pallet.l_002_qty
                )

            new_line = {}
            new_line["fk_header_id"] = bok_1.pk_header_id
            new_line["v_client_pk_consigment_num"] = bok_1.pk_header_id
            new_line["pk_booking_lines_id"] = str(uuid.uuid1())
            new_line["success"] = bok_1.success
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

                    if line.zbl_102_text_2 in SERVICE_GROUP_CODES:
                        continue

                    bok_3 = {}
                    bok_3["fk_header_id"] = bok_1.pk_header_id
                    bok_3["v_client_pk_consigment_num"] = bok_1.pk_header_id
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

                new_bok_2 = bok_2_serializer.save()
                new_bok_2s.append(new_bok_2)
            else:
                message = f"Serialiser Error - {bok_2_serializer.errors}"
                logger.info(f"@8135 {LOG_ID} {message}")
                raise Exception(message)
    else:  # Select a Pallet
        pallet = Pallet.objects.get(pk=pallet_id)
        number_of_pallets, unpalletized_line_pks = get_number_of_pallets(bok_2s, pallet)

        if not number_of_pallets and not unpalletized_line_pks:
            message = "0 number of Pallets."
            logger.info(f"@801 {LOG_ID} {message}")
            return message

        total_weight = 0
        for bok_2 in bok_2s:
            total_weight += bok_2.l_009_weight_per_each * bok_2.l_002_qty

        # Create new *1* Pallet Bok_2
        for line_pk in unpalletized_line_pks:  # Non-Palletized
            for bok_2 in bok_2s:
                if bok_2.pk == line_pk:
                    bok_2.pk = None
                    bok_2.b_093_packed_status = BOK_2_lines.AUTO_PACK
                    bok_2.save()
                    new_bok_2s.append(bok_2)

        if number_of_pallets:
            line = {}
            line["fk_header_id"] = bok_1.pk_header_id
            line["v_client_pk_consigment_num"] = bok_1.pk_header_id
            line["pk_booking_lines_id"] = str(uuid.uuid1())
            line["success"] = bok_1.success
            line["l_001_type_of_packaging"] = "PAL"
            line["l_002_qty"] = number_of_pallets
            line["l_003_item"] = "Auto repacked item"
            line["l_004_dim_UOM"] = "mm"
            line["l_005_dim_length"] = pallet.length
            line["l_006_dim_width"] = pallet.width
            line["l_007_dim_height"] = pallet.height
            line["l_009_weight_per_each"] = total_weight / number_of_pallets
            line["l_008_weight_UOM"] = "KG"
            line["b_093_packed_status"] = BOK_2_lines.AUTO_PACK

            bok_2_serializer = BOK_2_Serializer(data=line)
            if bok_2_serializer.is_valid():
                new_bok_2 = bok_2_serializer.save()
                new_bok_2s.append(new_bok_2)
            else:
                message = f"Serialiser Error - {bok_2_serializer.errors}"
                logger.info(f"@8131 {LOG_ID} {message}")
                raise Exception(message)

        # Create Bok_3
        for bok_2 in bok_2s:
            if bok_2.l_001_type_of_packaging == "PAL":
                continue

            if (
                bok_2.zbl_102_text_2 in SERVICE_GROUP_CODES
                or bok_2.pk in unpalletized_line_pks
            ):
                continue

            bok_3 = {}
            bok_3["fk_header_id"] = bok_1.pk_header_id
            bok_3["v_client_pk_consigment_num"] = bok_1.pk_header_id
            bok_3["fk_booking_lines_id"] = line["pk_booking_lines_id"]
            bok_3["success"] = bok_1.success
            bok_3["ld_005_item_serial_number"] = bok_2.zbl_131_decimal_1  # Sequence
            bok_3["ld_001_qty"] = bok_2.l_002_qty
            bok_3["ld_003_item_description"] = bok_2.l_003_item
            bok_3["ld_002_model_number"] = bok_2.e_item_type
            bok_3["zbld_121_integer_1"] = bok_2.zbl_131_decimal_1  # Sequence
            bok_3["zbld_122_integer_2"] = bok_2.l_002_qty
            bok_3["zbld_131_decimal_1"] = bok_2.l_005_dim_length
            bok_3["zbld_132_decimal_2"] = bok_2.l_006_dim_width
            bok_3["zbld_133_decimal_3"] = bok_2.l_007_dim_height
            bok_3["zbld_134_decimal_4"] = bok_2.l_009_weight_per_each
            bok_3["zbld_101_text_1"] = bok_2.l_004_dim_UOM
            bok_3["zbld_102_text_2"] = bok_2.l_008_weight_UOM
            bok_3["zbld_103_text_3"] = bok_2.e_item_type
            bok_3["zbld_104_text_4"] = bok_2.l_001_type_of_packaging
            bok_3["zbld_105_text_5"] = bok_2.l_003_item

            bok_3_serializer = BOK_3_Serializer(data=bok_3)
            if bok_3_serializer.is_valid():
                bok_3_serializer.save()
            else:
                message = f"Serialiser Error - {bok_3_serializer.errors}"
                logger.info(f"@8132 {LOG_ID} {message}, {bok_3}")
                raise Exception(message)

    logger.info(
        f"@839 {LOG_ID} OrderNum: {bok_1.b_client_order_num} --- Finished successfully!"
    )

    # # Get next business day
    # next_biz_day = dme_time_lib.next_business_day(date.today(), 1)

    # # Get Pricings
    # booking = {
    #     "pk_booking_id": bok_1.pk_header_id,
    #     "puPickUpAvailFrom_Date": next_biz_day,
    #     "b_clientReference_RA_Numbers": "",
    #     "puCompany": bok_1.b_028_b_pu_company,
    #     "pu_Contact_F_L_Name": bok_1.b_035_b_pu_contact_full_name,
    #     "pu_Email": bok_1.b_037_b_pu_email,
    #     "pu_Phone_Main": bok_1.b_038_b_pu_phone_main,
    #     "pu_Address_Street_1": bok_1.b_029_b_pu_address_street_1,
    #     "pu_Address_street_2": bok_1.b_030_b_pu_address_street_2,
    #     "pu_Address_Country": bok_1.b_034_b_pu_address_country,
    #     "pu_Address_PostalCode": bok_1.b_033_b_pu_address_postalcode,
    #     "pu_Address_State": bok_1.b_031_b_pu_address_state,
    #     "pu_Address_Suburb": bok_1.b_032_b_pu_address_suburb,
    #     "pu_Address_Type": bok_1.b_027_b_pu_address_type,
    #     "deToCompanyName": bok_1.b_054_b_del_company,
    #     "de_to_Contact_F_LName": bok_1.b_061_b_del_contact_full_name,
    #     "de_Email": bok_1.b_063_b_del_email,
    #     "de_to_Phone_Main": bok_1.b_064_b_del_phone_main,
    #     "de_To_Address_Street_1": bok_1.b_055_b_del_address_street_1,
    #     "de_To_Address_Street_2": bok_1.b_056_b_del_address_street_2,
    #     "de_To_Address_Country": bok_1.b_060_b_del_address_country,
    #     "de_To_Address_PostalCode": bok_1.b_059_b_del_address_postalcode,
    #     "de_To_Address_State": bok_1.b_057_b_del_address_state,
    #     "de_To_Address_Suburb": bok_1.b_058_b_del_address_suburb,
    #     "de_To_AddressType": bok_1.b_053_b_del_address_type,
    #     "b_booking_tail_lift_pickup": bok_1.b_019_b_pu_tail_lift,
    #     "b_booking_tail_lift_deliver": bok_1.b_041_b_del_tail_lift,
    #     "client_warehouse_code": bok_1.b_client_warehouse_code,
    #     "kf_client_id": bok_1.fk_client_id,
    #     "b_client_name": client.company_name,
    # }

    # booking_lines = []
    # for _bok_2 in new_bok_2s:
    #     if _bok_2.is_deleted:
    #         continue

    #     bok_2_line = {
    #         # "fk_booking_id": _bok_2.fk_header_id,
    #         "pk_lines_id": _bok_2.pk,
    #         "e_type_of_packaging": _bok_2.l_001_type_of_packaging,
    #         "e_qty": int(_bok_2.l_002_qty),
    #         "e_item": _bok_2.l_003_item,
    #         "e_dimUOM": _bok_2.l_004_dim_UOM,
    #         "e_dimLength": _bok_2.l_005_dim_length,
    #         "e_dimWidth": _bok_2.l_006_dim_width,
    #         "e_dimHeight": _bok_2.l_007_dim_height,
    #         "e_weightUOM": _bok_2.l_008_weight_UOM,
    #         "e_weightPerEach": _bok_2.l_009_weight_per_each,
    #     }
    #     booking_lines.append(bok_2_line)

    # fc_log, _ = FC_Log.objects.get_or_create(
    #     client_booking_id=bok_1.client_booking_id,
    #     old_quote__isnull=True,
    #     new_quote__isnull=True,
    # )
    # fc_log.old_quote = bok_1.quote
    # quote_set = None

    # if booking_lines:
    #     body = {"booking": booking, "booking_lines": booking_lines}
    #     _, success, message, quote_set = pricing_oper(
    #         body=body,
    #         booking_id=None,
    #         is_pricing_only=True,
    #     )
    #     logger.info(
    #         f"#519 {LOG_ID} Pricing result: success: {success}, message: {message}, results cnt: {quote_set.count()}"
    #     )

    # # Select best quotes(fastest, lowest)
    # json_results = []
    # if quote_set and quote_set.exists() and quote_set.count() > 0:
    #     bok_1_obj = bok_1
    #     auto_select_pricing_4_bok(bok_1_obj, quote_set)
    #     best_quotes = select_best_options(pricings=quote_set)
    #     logger.info(f"#520 {LOG_ID} Selected Best Pricings: {best_quotes}")

    #     context = {"client_customer_mark_up": client.client_customer_mark_up}
    #     json_results = SimpleQuoteSerializer(
    #         best_quotes, many=True, context=context
    #     ).data
    #     json_results = dme_time_lib.beautify_eta(json_results, best_quotes, client)

    #     if bok_1.success == dme_constants.BOK_SUCCESS_4:
    #         best_quote = best_quotes[0]
    #         bok_1_obj.b_003_b_service_name = best_quote.service_name
    #         bok_1_obj.b_001_b_freight_provider = best_quote.freight_provider
    #         bok_1_obj.b_002_b_vehicle_type = (
    #             best_quote.vehicle.description if best_quote.vehicle else None
    #         )
    #         bok_1_obj.save()
    #         fc_log.new_quote = best_quotes[0]
    #         fc_log.save()
    # else:
    #     message = f"#521 {LOG_ID} No Pricing results to select - BOK_1 pk_header_id: {bok_1.pk_header_id}\nOrder Number: {bok_1.b_client_order_num}"
    #     logger.error(message)

    #     if bok_1.b_client_order_num:
    #         send_email_to_admins("No FC result", message)

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
    # if json_results:
    #     logger.info(f"@8838 {LOG_ID} success: True, 201_created")
    #     return json_results
    # else:
    #     message = "Pricing cannot be returned due to incorrect address information."
    #     logger.info(f"@8839 {LOG_ID} {message}")

    #     result = {"success": True, "results": json_results}
    #     logger.info(f"@8837 {LOG_ID} success: True, 201_created")
    #     return result


def manual_repack(bok_1, repack_status):
    """
    Duplicate bok_2 and bok_3 for `manual` repacked status

    @params:
        bok_1:
        repack_status: 'manual-from-original' | 'manual-from-auto'
    """
    LOG_ID = "[bok_2 & bok_3 BULK DUPLICATION]"
    logger.info(
        f"@840 {LOG_ID} OrderNum: {bok_1.b_client_order_num}, Repack Status: {repack_status}"
    )

    if repack_status == "manual-from-original":  # Original
        bok_2s = (
            bok_1.bok_2s()
            .filter(
                Q(b_093_packed_status=BOK_2_lines.ORIGINAL)
                | Q(b_093_packed_status__isnull=True)
            )
            .filter(is_deleted=False)
        )
    else:  # Auto Repacked
        bok_2s = (
            bok_1.bok_2s()
            .filter(Q(b_093_packed_status=BOK_2_lines.AUTO_PACK))
            .filter(is_deleted=False)
        )

    if bok_2s.count() == 0:
        logger.info(
            f"@841 {LOG_ID} OrderNum: {bok_1.b_client_order_num} --- No items(bok_2s) to be duplicated!"
        )
        return

    for bok_2 in bok_2s:
        bok_3s = BOK_3_lines_data.objects.filter(
            fk_booking_lines_id=bok_2.pk_booking_lines_id
        )

        bok_2.pk = None
        bok_2.pk_booking_lines_id = str(uuid.uuid4())
        bok_2.b_093_packed_status = BOK_2_lines.MANUAL_PACK
        bok_2.save()

        for bok_3 in bok_3s:
            bok_3.pk = None
            bok_3.fk_booking_lines_id = bok_2.pk_booking_lines_id
            bok_3.save()

    logger.info(
        f"@849 {LOG_ID} OrderNum: {bok_1.b_client_order_num} --- Finished successfully! {len(bok_2s)} items(bok_2s) are duplicated."
    )


def reset_repack(bok_1, repack_status):
    """
    Delete bok_2 and bok_ of specified repacked status

    @params:
        bok_1:
        repack_status: 'manual' | 'auto'
    """
    LOG_ID = "[BOK REPACK RESET]"
    logger.info(
        f"@840 {LOG_ID} OrderNum: {bok_1.b_client_order_num}, Repack Status: {repack_status}"
    )

    bok_2s = (
        bok_1.bok_2s()
        .filter(b_093_packed_status=repack_status)
        .filter(is_deleted=False)
    )

    if bok_2s.count() == 0:
        logger.info(
            f"@841 {LOG_ID} OrderNum: {bok_1.b_client_order_num} --- No items(bok_2s) to be reset!"
        )
        return

    for bok_2 in bok_2s:
        bok_3s = BOK_3_lines_data.objects.filter(
            fk_booking_lines_id=bok_2.pk_booking_lines_id
        ).delete()
        bok_2.delete()

    API_booking_quotes.objects.filter(
        fk_booking_id=bok_1.pk_header_id, packed_status=repack_status
    ).update(is_used=True)

    logger.info(
        f"@849 {LOG_ID} OrderNum: {bok_1.b_client_order_num} --- Finished successfully! {len(bok_2s)} items(bok_2s) are reset."
    )
