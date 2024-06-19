import math
import logging

from api.models import Client_Products
from api.operations import product_operations as product_oper

logger = logging.getLogger(__name__)


def _get_bok_1_modifications(client, old_bok_1, bok_1):
    result = {}

    if (
        "b_021_b_pu_avail_from_date" in bok_1
        and bok_1["b_021_b_pu_avail_from_date"] != old_bok_1.b_021_b_pu_avail_from_date
    ):
        result["b_021_b_pu_avail_from_date"] = {
            "old": old_bok_1.b_021_b_pu_avail_from_date,
            "new": bok_1["b_021_b_pu_avail_from_date"],
        }

    if (
        "b_clientReference_RA_Numbers" in bok_1
        and bok_1["b_clientReference_RA_Numbers"]
        != old_bok_1.b_clientReference_RA_Numbers
    ):
        result["b_clientReference_RA_Numbers"] = {
            "old": old_bok_1.b_clientReference_RA_Numbers,
            "new": bok_1["b_clientReference_RA_Numbers"],
        }

    if (
        "b_028_b_pu_company" in bok_1
        and bok_1["b_028_b_pu_company"] != old_bok_1.b_028_b_pu_company
    ):
        result["b_028_b_pu_company"] = {
            "old": old_bok_1.b_028_b_pu_company,
            "new": bok_1["b_028_b_pu_company"],
        }

    if (
        "b_035_b_pu_contact_full_name" in bok_1
        and bok_1["b_035_b_pu_contact_full_name"]
        != old_bok_1.b_035_b_pu_contact_full_name
    ):
        result["b_035_b_pu_contact_full_name"] = {
            "old": old_bok_1.b_035_b_pu_contact_full_name,
            "new": bok_1["b_035_b_pu_contact_full_name"],
        }

    if (
        "b_037_b_pu_email" in bok_1
        and bok_1["b_037_b_pu_email"] != old_bok_1.b_037_b_pu_email
    ):
        result["b_037_b_pu_email"] = {
            "old": old_bok_1.b_037_b_pu_email,
            "new": bok_1["b_037_b_pu_email"],
        }

    if (
        "b_038_b_pu_phone_main" in bok_1
        and bok_1["b_038_b_pu_phone_main"] != old_bok_1.b_038_b_pu_phone_main
    ):
        result["b_038_b_pu_phone_main"] = {
            "old": old_bok_1.b_038_b_pu_phone_main,
            "new": bok_1["b_038_b_pu_phone_main"],
        }

    if (
        "b_029_b_pu_address_street_1" in bok_1
        and bok_1["b_029_b_pu_address_street_1"]
        != old_bok_1.b_029_b_pu_address_street_1
    ):
        result["b_029_b_pu_address_street_1"] = {
            "old": old_bok_1.b_029_b_pu_address_street_1,
            "new": bok_1["b_029_b_pu_address_street_1"],
        }

    if (
        "b_030_b_pu_address_street_2" in bok_1
        and bok_1["b_030_b_pu_address_street_2"]
        != old_bok_1.b_030_b_pu_address_street_2
    ):
        result["b_030_b_pu_address_street_2"] = {
            "old": old_bok_1.b_030_b_pu_address_street_2,
            "new": bok_1["b_030_b_pu_address_street_2"],
        }

    if (
        "b_034_b_pu_address_country" in bok_1
        and bok_1["b_034_b_pu_address_country"] != old_bok_1.b_034_b_pu_address_country
    ):
        result["b_034_b_pu_address_country"] = {
            "old": old_bok_1.b_034_b_pu_address_country,
            "new": bok_1["b_034_b_pu_address_country"],
        }

    if (
        "b_033_b_pu_address_postalcode" in bok_1
        and bok_1["b_033_b_pu_address_postalcode"]
        != old_bok_1.b_033_b_pu_address_postalcode
    ):
        result["b_033_b_pu_address_postalcode"] = {
            "old": old_bok_1.b_033_b_pu_address_postalcode,
            "new": bok_1["b_033_b_pu_address_postalcode"],
        }

    if (
        "b_031_b_pu_address_state" in bok_1
        and bok_1["b_031_b_pu_address_state"] != old_bok_1.b_031_b_pu_address_state
    ):
        result["b_031_b_pu_address_state"] = {
            "old": old_bok_1.b_031_b_pu_address_state,
            "new": bok_1["b_031_b_pu_address_state"],
        }

    if (
        "b_032_b_pu_address_suburb" in bok_1
        and bok_1["b_032_b_pu_address_suburb"] != old_bok_1.b_032_b_pu_address_suburb
    ):
        result["b_032_b_pu_address_suburb"] = {
            "old": old_bok_1.b_032_b_pu_address_suburb,
            "new": bok_1["b_032_b_pu_address_suburb"],
        }

    if (
        "b_054_b_del_company" in bok_1
        and bok_1["b_054_b_del_company"] != old_bok_1.b_054_b_del_company
    ):
        result["b_054_b_del_company"] = {
            "old": old_bok_1.b_054_b_del_company,
            "new": bok_1["b_054_b_del_company"],
        }

    if (
        "b_061_b_del_contact_full_name" in bok_1
        and bok_1["b_061_b_del_contact_full_name"]
        != old_bok_1.b_061_b_del_contact_full_name
    ):
        result["b_061_b_del_contact_full_name"] = {
            "old": old_bok_1.b_061_b_del_contact_full_name,
            "new": bok_1["b_061_b_del_contact_full_name"],
        }

    if (
        "b_063_b_del_email" in bok_1
        and bok_1["b_063_b_del_email"] != old_bok_1.b_063_b_del_email
    ):
        result["b_063_b_del_email"] = {
            "old": old_bok_1.b_063_b_del_email,
            "new": bok_1["b_063_b_del_email"],
        }

    if (
        "b_064_b_del_phone_main" in bok_1
        and bok_1["b_064_b_del_phone_main"] != old_bok_1.b_064_b_del_phone_main
    ):
        result["b_064_b_del_phone_main"] = {
            "old": old_bok_1.b_064_b_del_phone_main,
            "new": bok_1["b_064_b_del_phone_main"],
        }

    if (
        "b_055_b_del_address_street_1" in bok_1
        and bok_1["b_055_b_del_address_street_1"]
        != old_bok_1.b_055_b_del_address_street_1
    ):
        result["b_055_b_del_address_street_1"] = {
            "old": old_bok_1.b_055_b_del_address_street_1,
            "new": bok_1["b_055_b_del_address_street_1"],
        }

    if (
        "b_056_b_del_address_street_2" in bok_1
        and bok_1["b_056_b_del_address_street_2"]
        != old_bok_1.b_056_b_del_address_street_2
    ):
        result["b_056_b_del_address_street_2"] = {
            "old": old_bok_1.b_056_b_del_address_street_2,
            "new": bok_1["b_056_b_del_address_street_2"],
        }

    if (
        "b_060_b_del_address_country" in bok_1
        and bok_1["b_060_b_del_address_country"]
        != old_bok_1.b_060_b_del_address_country
    ):
        result["b_060_b_del_address_country"] = {
            "old": old_bok_1.b_060_b_del_address_country,
            "new": bok_1["b_060_b_del_address_country"],
        }

    if (
        "b_059_b_del_address_postalcode" in bok_1
        and bok_1["b_059_b_del_address_postalcode"]
        != old_bok_1.b_059_b_del_address_postalcode
    ):
        result["b_059_b_del_address_postalcode"] = {
            "old": old_bok_1.b_059_b_del_address_postalcode,
            "new": bok_1["b_059_b_del_address_postalcode"],
        }

    # if (
    #     "b_057_b_del_address_state" in bok_1
    #     and bok_1["b_057_b_del_address_state"] != old_bok_1.b_057_b_del_address_state
    # ):
    #     result["b_057_b_del_address_state"] = {
    #         "old": old_bok_1.b_057_b_del_address_state,
    #         "new": bok_1["b_057_b_del_address_state"],
    #     }

    # if (
    #     "b_058_b_del_address_suburb" in bok_1
    #     and bok_1["b_058_b_del_address_suburb"] != old_bok_1.b_058_b_del_address_suburb
    # ):
    #     result["b_058_b_del_address_suburb"] = {
    #         "old": old_bok_1.b_058_b_del_address_suburb,
    #         "new": bok_1["b_058_b_del_address_suburb"],
    #     }

    if (
        "b_client_warehouse_code" in bok_1
        and bok_1["b_client_warehouse_code"] != old_bok_1.b_client_warehouse_code
    ):
        result["b_client_warehouse_code"] = {
            "old": old_bok_1.b_client_warehouse_code,
            "new": bok_1["b_client_warehouse_code"],
        }

    if (
        "b_003_b_service_name" in bok_1
        and bok_1["b_003_b_service_name"] != old_bok_1.b_003_b_service_name
    ):
        result["b_003_b_service_name"] = {
            "old": old_bok_1.b_003_b_service_name,
            "new": bok_1["b_003_b_service_name"],
        }

    return result


def _get_bok_2s_3s_modifications(client, old_bok_2s, old_bok_3s, bok_2s):
    result = {"added": [], "modified": [], "deleted": []}

    # Get New
    for bok_2 in bok_2s:
        line_data = bok_2["booking_lines_data"][0]
        exist = False

        for old_bok_3 in old_bok_3s:
            if old_bok_3.ld_002_model_number == line_data["ld_002_model_number"]:
                exist = True
                break

        if not exist:
            result["added"].append(line_data["ld_002_model_number"])

    # Get Deleted
    for old_bok_3 in old_bok_3s:
        exist = True

        for bok_2 in bok_2s:
            line_data = bok_2["booking_lines_data"][0]

            if old_bok_3.ld_002_model_number == line_data["ld_002_model_number"]:
                exist = False
                break

        if exist:
            # for old_bok_2 in old_bok_2s:
            #     if old_bok_2s.pk_booking_lines_id == old_bok_3.fk_booking_lines_id:
            result["deleted"].append(old_bok_3.ld_002_model_number)

    # Get Modified
    for old_bok_3 in old_bok_3s:
        for bok_2 in bok_2s:
            line = bok_2["booking_line"]
            line_data = bok_2["booking_lines_data"][0]

            if old_bok_3.ld_002_model_number == line_data["ld_002_model_number"]:
                # Modified
                _modified = {"booking_line": [], "booking_lines_data": []}

                # Modified Line
                for old_bok_2 in old_bok_2s:
                    if old_bok_2.pk_booking_lines_id == old_bok_3.fk_booking_lines_id:
                        _modified_line = {}

                        if (
                            "l_001_type_of_packaging" in line
                            and old_bok_2.l_001_type_of_packaging
                            != line["l_001_type_of_packaging"]
                        ):
                            _modified_line["l_001_type_of_packaging"] = {
                                "old": old_bok_2.l_001_type_of_packaging,
                                "new": line["l_001_type_of_packaging"],
                            }

                        if (
                            "l_002_qty" in line
                            and old_bok_2.l_002_qty != line["l_002_qty"]
                        ):
                            _modified_line["l_002_qty"] = {
                                "old": old_bok_2.l_002_qty,
                                "new": line["l_002_qty"],
                            }

                        if (
                            "l_003_item" in line
                            and old_bok_2.l_003_item != line["l_003_item"]
                        ):
                            _modified_line["l_003_item"] = {
                                "old": old_bok_2.l_003_item,
                                "new": line["l_003_item"],
                            }

                        if (
                            "l_004_dim_UOM" in line
                            and old_bok_2.l_004_dim_UOM != line["l_004_dim_UOM"]
                        ):
                            _modified_line["l_004_dim_UOM"] = {
                                "old": old_bok_2.l_004_dim_UOM,
                                "new": line["l_004_dim_UOM"],
                            }
                        if (
                            "l_005_dim_length" in line
                            and old_bok_2.l_005_dim_length != line["l_005_dim_length"]
                        ):
                            _modified_line["l_005_dim_length"] = {
                                "old": old_bok_2.l_005_dim_length,
                                "new": line["l_005_dim_length"],
                            }

                        if (
                            "l_006_dim_width" in line
                            and old_bok_2.l_006_dim_width != line["l_006_dim_width"]
                        ):
                            _modified_line["l_006_dim_width"] = {
                                "old": old_bok_2.l_006_dim_width,
                                "new": line["l_006_dim_width"],
                            }

                        if (
                            "l_007_dim_height" in line
                            and old_bok_2.l_007_dim_height != line["l_007_dim_height"]
                        ):
                            _modified_line["l_007_dim_height"] = {
                                "old": old_bok_2.l_007_dim_height,
                                "new": line["l_007_dim_height"],
                            }

                        if (
                            "l_008_weight_UOM" in line
                            and old_bok_2.l_008_weight_UOM != line["l_008_weight_UOM"]
                        ):
                            _modified_line["l_008_weight_UOM"] = {
                                "old": old_bok_2.l_008_weight_UOM,
                                "new": line["l_008_weight_UOM"],
                            }

                        if (
                            "l_009_weight_per_each" in line
                            and old_bok_2.l_009_weight_per_each
                            != line["l_009_weight_per_each"]
                        ):
                            _modified_line["l_009_weight_per_each"] = {
                                "old": old_bok_2.l_009_weight_per_each,
                                "new": line["l_009_weight_per_each"],
                            }

                        if _modified_line:
                            _modified["booking_line"].append(_modified_line)

                # Modified Line Data
                _modified_line_data = {}

                if (
                    "ld_001_qty" in line_data
                    and old_bok_3.ld_001_qty != line_data["ld_001_qty"]
                ):
                    _modified_line_data["ld_001_qty"] = {
                        "old": old_bok_3.ld_001_qty,
                        "new": line_data["ld_001_qty"],
                    }

                if (
                    "ld_003_item_description" in line_data
                    and old_bok_3.ld_003_item_description
                    != line_data["ld_003_item_description"]
                ):
                    _modified_line_data["ld_003_item_description"] = {
                        "old": old_bok_3.ld_003_item_description,
                        "new": line_data["ld_003_item_description"],
                    }

                if (
                    "ld_005_item_serial_number" in line_data
                    and old_bok_3.ld_005_item_serial_number
                    != line_data["ld_005_item_serial_number"]
                ):
                    _modified_line_data["ld_005_item_serial_number"] = {
                        "old": old_bok_3.ld_005_item_serial_number,
                        "new": line_data["ld_005_item_serial_number"],
                    }

                if (
                    "ld_006_insurance_value" in line_data
                    and old_bok_3.ld_006_insurance_value
                    != line_data["ld_006_insurance_value"]
                ):
                    _modified_line_data["ld_006_insurance_value"] = {
                        "old": old_bok_3.ld_006_insurance_value,
                        "new": line_data["ld_006_insurance_value"],
                    }

                if (
                    "ld_007_gap_ra" in line_data
                    and old_bok_3.ld_007_gap_ra != line_data["ld_007_gap_ra"]
                ):
                    _modified_line_data["ld_007_gap_ra"] = {
                        "old": old_bok_3.ld_007_gap_ra,
                        "new": line_data["ld_007_gap_ra"],
                    }

                if _modified_line_data:
                    _modified["booking_lines_data"].append(_modified_line_data)

                if not _modified["booking_line"]:
                    del _modified["booking_line"]

                if not _modified["booking_lines_data"]:
                    del _modified["booking_lines_data"]

                if _modified:
                    result["modified"].append(
                        {old_bok_3.ld_002_model_number: _modified}
                    )

    return result


def _get_bok_2s_3s_modifications_4_plum(client, old_bok_2s, bok_2s):
    result = {"added": [], "modified": [], "deleted": []}
    items = product_oper.get_product_items(bok_2s, client)

    _bok_2s = []
    for index, item in enumerate(items):
        line = {}
        line["l_001_type_of_packaging"] = "Carton"
        line["l_002_qty"] = item["qty"]
        line["l_003_item"] = item["description"]
        line["l_004_dim_UOM"] = item["e_dimUOM"]
        line["l_005_dim_length"] = item["e_dimLength"]
        line["l_006_dim_width"] = item["e_dimWidth"]
        line["l_007_dim_height"] = item["e_dimHeight"]
        line["l_009_weight_per_each"] = item["e_weightPerEach"]
        line["l_008_weight_UOM"] = item["e_weightUOM"]
        line["e_item_type"] = item["e_item_type"]
        _bok_2s.append(line)

    # Get New
    for bok_2 in _bok_2s:
        is_new = True

        for old_bok_2 in old_bok_2s:
            if old_bok_2.e_item_type == bok_2["e_item_type"]:
                is_new = False
                break

        if is_new:
            result["added"].append(
                {"model_number": bok_2["e_item_type"], "qty": bok_2["l_002_qty"]}
            )

    # Get Deleted
    for old_bok_2 in old_bok_2s:
        is_deleted = True

        for bok_2 in _bok_2s:
            if old_bok_2.e_item_type == bok_2["e_item_type"]:
                is_deleted = False
                break

        if is_deleted:
            result["deleted"].append(
                {
                    "model_number": old_bok_2.e_item_type,
                    "qty": old_bok_2.l_002_qty,
                }
            )

    # Get Modified
    for bok_2 in _bok_2s:
        for old_bok_2 in old_bok_2s:
            if (
                old_bok_2.e_item_type == bok_2["e_item_type"]
                and not old_bok_2.l_002_qty == bok_2["l_002_qty"]
            ):
                result["modified"].append(
                    {
                        "old": {
                            "model_number": old_bok_2.e_item_type,
                            "qty": old_bok_2.l_002_qty,
                        },
                        "new": {
                            "model_number": bok_2["e_item_type"],
                            "qty": bok_2["l_002_qty"],
                        },
                    }
                )

    return result


def detect_modified_data(client, old_bok_1, old_bok_2s, old_bok_3s, new_data):
    _modified_data = {}
    bok_1 = new_data["booking"]
    bok_2s = new_data["booking_lines"]

    # bok_1
    _modified_data["booking"] = _get_bok_1_modifications(client, old_bok_1, bok_1)

    if not _modified_data["booking"]:
        del _modified_data["booking"]

    # bok_2
    if "model_number" in bok_2s[0]:  # Product & Child items
        _modified_data["booking_lines"] = _get_bok_2s_3s_modifications_4_plum(
            client, old_bok_2s, bok_2s
        )
    else:
        _modified_data["booking_lines"] = _get_bok_2s_3s_modifications(
            client, old_bok_2s, old_bok_3s, bok_2s
        )

    if not _modified_data["booking_lines"]["added"]:
        del _modified_data["booking_lines"]["added"]

    if not _modified_data["booking_lines"]["modified"]:
        del _modified_data["booking_lines"]["modified"]

    if not _modified_data["booking_lines"]["deleted"]:
        del _modified_data["booking_lines"]["deleted"]

    if not _modified_data["booking_lines"]:
        del _modified_data["booking_lines"]

    if not _modified_data:
        logger.info(f"#350 - Nothing has been modified")
    else:
        logger.info(f"#351 - Modified push data: {_modified_data}")
