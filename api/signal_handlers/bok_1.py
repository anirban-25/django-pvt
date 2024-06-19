import logging

from api.models import BOK_1_headers, BOK_2_lines, BOK_3_lines_data

# from api.fp_apis.apis import get_pricing

logger = logging.getLogger(__name__)


def on_create_bok_1_handler(bok_1):
    logger.info("#501 - bok_1 post_save(create) handler")
    # logger.info(
    #     f"#502 - bok_1 pk_header_id: {bok_1.pk_header_id}, succss code: {bok_1.success}"
    # )

    # if bok_1.success == "3":
    #     bok_2_lines = BOK_2_lines.objects.filter(fk_header_id=bok_1.pk_header_id)

    #     if not bok_2_lines.exists():
    #         logger.info(f"#503 - No lines")
    #     else:
    #         bok_2s = []
    #         bok_1 = {
    #             "pk_booking_id": bok_1.pk_header_id,
    #             "puPickUpAvailFrom_Date": str(bok_1.b_021_b_pu_avail_from_date),
    #             "b_clientReference_RA_Numbers": bok_1.b_000_1_b_clientReference_RA_Numbers,
    #             "puCompany": bok_1.b_028_b_pu_company,
    #             "pu_Contact_F_L_Name": bok_1.b_035_b_pu_contact_full_name,
    #             "pu_Email": bok_1.b_037_b_pu_email,
    #             "pu_Phone_Main": bok_1.b_038_b_pu_phone_main
    #             if bok_1.b_038_b_pu_phone_main
    #             else "419294339",
    #             "pu_Address_Street_1": bok_1.b_029_b_pu_address_street_1,
    #             "pu_Address_street_2": bok_1.b_030_b_pu_address_street_2,
    #             "pu_Address_Country": bok_1.b_034_b_pu_address_country,
    #             "pu_Address_PostalCode": bok_1.b_033_b_pu_address_postalcode,
    #             "pu_Address_State": bok_1.b_031_b_pu_address_state,
    #             "pu_Address_Suburb": bok_1.b_032_b_pu_address_suburb,
    #             "deToCompanyName": bok_1.b_054_b_del_company,
    #             "de_to_Contact_F_LName": bok_1.b_061_b_del_contact_full_name,
    #             "de_Email": bok_1.b_063_b_del_email,
    #             "de_to_Phone_Main": bok_1.b_064_b_del_phone_main
    #             if bok_1.b_064_b_del_phone_main
    #             else "419294339",
    #             "de_To_Address_Street_1": bok_1.b_055_b_del_address_street_1,
    #             "de_To_Address_Street_2": bok_1.b_056_b_del_address_street_2,
    #             "de_To_Address_Country": bok_1.b_060_b_del_address_country,
    #             "de_To_Address_PostalCode": bok_1.b_059_b_del_address_postalcode,
    #             "de_To_Address_State": bok_1.b_057_b_del_address_state,
    #             "de_To_Address_Suburb": bok_1.b_058_b_del_address_suburb,
    #             "client_warehouse_code": bok_1.b_client_warehouse_code,
    #             "vx_serviceName": bok_1.b_003_b_service_name,
    #             "kf_client_id": bok_1.fk_client_id,
    #         }

    #         for bok_2_line in bok_2_lines:
    #             bok_2 = {
    #                 "fk_booking_id": bok_2_line.fk_header_id,
    #                 "e_type_of_packaging": bok_2_line.l_001_type_of_packaging,
    #                 "e_qty": bok_2_line.l_002_qty,
    #                 "e_item": bok_2_line.l_003_item,
    #                 "e_dimUOM": bok_2_line.l_004_dim_UOM,
    #                 "e_dimLength": bok_2_line.l_005_dim_length,
    #                 "e_dimWidth": bok_2_line.l_006_dim_width,
    #                 "e_dimHeight": bok_2_line.l_007_dim_height,
    #                 "e_weightUOM": bok_2_line.l_008_weight_UOM,
    #                 "e_weightPerEach": bok_2_line.l_009_weight_per_each,
    #             }
    #             bok_2s.append(bok_2)

    #         body = {"booking": bok_1, "booking_lines": bok_2s}
    #         success, message, results = get_pricing(
    #             body=body,
    #             booking_id=None,
    #             is_pricing_only=True,
    #             is_best_options_only=True,
    #         )
    #         logger.info(
    #             f"#509 - Pricing result: success: {success}, message: {message}, results cnt: {results}"
    #         )
