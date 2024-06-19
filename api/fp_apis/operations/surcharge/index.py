import math
import logging

from django.db.models import Q

from api.common.ratio import _get_dim_amount, _get_weight_amount
from api.common.constants import PALLETS, SKIDS
from api.common.convert_price import apply_markups
from api.common.dimension import get_l_w_h
from api.helpers.cubic import get_cubic_meter
from api.models import Booking_lines, Surcharge, Fp_freight_providers, Client_FP
from api.fp_apis.utils import get_m3_to_kg_factor
from api.helpers.line import is_carton, is_pallet

from api.fp_apis.operations.surcharge.tnt import tnt
from api.fp_apis.operations.surcharge.allied import allied
from api.fp_apis.operations.surcharge.hunter import hunter
from api.fp_apis.operations.surcharge.camerons import camerons
from api.fp_apis.operations.surcharge.northline import northline
from api.fp_apis.operations.surcharge.hitrans import hitrans
from api.fp_apis.operations.surcharge.blacks import blacks
from api.fp_apis.operations.surcharge.blanner import blanner
from api.fp_apis.operations.surcharge.bluestar import bluestar
from api.fp_apis.operations.surcharge.vfs import vfs
from api.fp_apis.operations.surcharge.toll import toll
from api.fp_apis.operations.surcharge.startrack import startrack
from api.fp_apis.operations.surcharge.dxt import dxt
from api.fp_apis.operations.surcharge.followmont import followmont
from api.fp_apis.operations.surcharge.sadliers import sadliers
from api.fp_apis.operations.surcharge.afs import afs
from api.fp_apis.operations.surcharge.direct_freight import direct_freight
from api.fp_apis.operations.surcharge.pfm_corp import pfm_corp
from api.fp_apis.operations.surcharge.deliver_me_direct import deliver_me_direct
from api.fp_apis.operations.surcharge.team_global_express import (
    team_global_express_ins,
    team_global_express_ipec,
)


logger = logging.getLogger(__name__)


def build_dict_data(booking_obj, line_objs, quote_obj, data_type):
    """
    Build `Booking` and `Lines` for Surcharge
    """
    booking = {}
    lines = []

    if data_type == "bok_1":
        booking = {
            "pu_Address_Type": booking_obj.b_027_b_pu_address_type,
            "pu_Address_State": booking_obj.b_031_b_pu_address_state,
            "pu_Address_PostalCode": booking_obj.b_033_b_pu_address_postalcode,
            "pu_Address_Suburb": booking_obj.b_032_b_pu_address_suburb,
            "pu_Address_Street": booking_obj.b_029_b_pu_address_street_1,
            "de_To_Address_State": booking_obj.b_057_b_del_address_state,
            "de_To_Address_PostalCode": booking_obj.b_059_b_del_address_postalcode,
            "de_To_Address_Suburb": booking_obj.b_058_b_del_address_suburb,
            "de_To_AddressType": booking_obj.b_053_b_del_address_type,
            "pu_tail_lift": booking_obj.b_019_b_pu_tail_lift,
            "del_tail_lift": booking_obj.b_041_b_del_tail_lift,
            "pu_no_of_assists": booking_obj.b_072_pu_no_of_assists,
            "de_no_of_assists": booking_obj.b_073_de_no_of_assists,
            "vx_serviceName": quote_obj.service_name,
            "vx_freight_provider": quote_obj.freight_provider,
            "client_id": booking_obj.fk_client_id,
        }

        for line_obj in line_objs:
            line = {
                "pk": line_obj.pk_lines_id,
                "e_type_of_packaging": line_obj.l_001_type_of_packaging,
                "e_qty": int(line_obj.l_002_qty),
                "e_item": line_obj.l_003_item,
                "e_dimUOM": line_obj.l_004_dim_UOM,
                "e_dimLength": line_obj.l_005_dim_length,
                "e_dimWidth": line_obj.l_006_dim_width,
                "e_dimHeight": line_obj.l_007_dim_height,
                "e_weightUOM": line_obj.l_008_weight_UOM,
                "e_weightPerEach": line_obj.l_009_weight_per_each,
                "packed_status": line_obj.b_093_packed_status,
                "e_dangerousGoods": False,
            }
            lines.append(line)
    else:
        booking = {
            "pu_Address_Type": booking_obj.pu_Address_Type,
            "pu_Address_State": booking_obj.pu_Address_State,
            "pu_Address_PostalCode": booking_obj.pu_Address_PostalCode,
            "pu_Address_Suburb": booking_obj.pu_Address_Suburb,
            "pu_Address_Street": booking_obj.pu_Address_Street_1,
            "de_To_AddressType": booking_obj.de_To_AddressType,
            "de_To_Address_State": booking_obj.de_To_Address_State,
            "de_To_Address_PostalCode": booking_obj.de_To_Address_PostalCode,
            "de_To_Address_Suburb": booking_obj.de_To_Address_Suburb,
            "pu_tail_lift": int(booking_obj.b_booking_tail_lift_pickup or 0),
            "del_tail_lift": int(booking_obj.b_booking_tail_lift_deliver or 0),
            "pu_no_of_assists": int(booking_obj.pu_no_of_assists or 0),
            "de_no_of_assists": int(booking_obj.de_no_of_assists or 0),
            "vx_serviceName": quote_obj.service_name,
            "vx_freight_provider": quote_obj.freight_provider,
            "client_id": booking_obj.kf_client_id,
        }

        for line_obj in line_objs:
            line = {
                "pk": line_obj.pk_lines_id,
                "e_type_of_packaging": line_obj.e_type_of_packaging,
                "e_qty": int(line_obj.e_qty),
                "e_item": line_obj.e_item,
                "e_dimUOM": line_obj.e_dimUOM,
                "e_dimLength": line_obj.e_dimLength,
                "e_dimWidth": line_obj.e_dimWidth,
                "e_dimHeight": line_obj.e_dimHeight,
                "e_weightUOM": line_obj.e_weightUOM,
                "e_weightPerEach": line_obj.e_weightPerEach,
                "packed_status": line_obj.packed_status,
                "e_dangerousGoods": False,
            }
            lines.append(line)

    return booking, lines


def find_surcharges(
    booking_obj,
    line_objs,
    all_line_objs,
    quote_obj,
    fp,
    data_type="bok_1",
):
    booking, lines = build_dict_data(booking_obj, line_objs, quote_obj, data_type)
    booking, all_lines = build_dict_data(
        booking_obj, all_line_objs, quote_obj, data_type
    )
    m3_to_kg_factor = get_m3_to_kg_factor(fp.fp_company_name)

    dead_weight, cubic_weight, total_qty, total_cubic = 0, 0, 0, 0
    lengths, widths, heights = [], [], []
    lines_data, original_lines_data = [], []
    auto_lines_data, manual_lines_data, scanned_lines_data = [], [], []
    diagonals, lines_max_weight, lines_max_dead_weight = [], [], []
    has_dangerous_item = False
    has_pallet = False

    for line in all_lines:
        dim_amount = _get_dim_amount(line["e_dimUOM"])
        dim_weight = _get_weight_amount(line["e_weightUOM"])
        item_length = line["e_dimLength"] * dim_amount
        item_width = line["e_dimWidth"] * dim_amount
        item_height = line["e_dimHeight"] * dim_amount
        item_length, item_width, item_height = get_l_w_h(
            item_length, item_width, item_height
        )
        item_dead_weight = line["e_weightPerEach"] * dim_weight
        item_cubic = get_cubic_meter(
            line["e_dimLength"],
            line["e_dimWidth"],
            line["e_dimHeight"],
            line["e_dimUOM"],
            1,
        )

        if line["packed_status"] == "original":
            original_lines_data.append(
                {
                    "e_item": line["e_item"],
                    "e_dimLength": item_length,
                    "e_dimWidth": item_width,
                    "e_dimHeight": item_height,
                    "max_dimension": item_length,
                    "weight": item_dead_weight,
                    "cubic": item_cubic,
                    "e_qty": line["e_qty"],
                    "is_pallet": is_pallet(line["e_type_of_packaging"]),
                }
            )
        elif line["packed_status"] == "auto":
            auto_lines_data.append(
                {
                    "e_dimLength": item_length,
                    "e_dimWidth": item_width,
                    "e_dimHeight": item_height,
                    "max_dimension": item_length,
                    "weight": item_dead_weight,
                    "cubic": item_cubic,
                    "e_qty": line["e_qty"],
                    "is_pallet": is_pallet(line["e_type_of_packaging"]),
                }
            )
        elif line["packed_status"] == "manual":
            manual_lines_data.append(
                {
                    "e_dimLength": item_length,
                    "e_dimWidth": item_width,
                    "e_dimHeight": item_height,
                    "max_dimension": item_length,
                    "weight": item_dead_weight,
                    "cubic": item_cubic,
                    "e_qty": line["e_qty"],
                    "is_pallet": is_pallet(line["e_type_of_packaging"]),
                }
            )
        elif line["packed_status"] == "scanned":
            scanned_lines_data.append(
                {
                    "e_dimLength": item_length,
                    "e_dimWidth": item_width,
                    "e_dimHeight": item_height,
                    "max_dimension": item_length,
                    "weight": item_dead_weight,
                    "cubic": item_cubic,
                    "e_qty": line["e_qty"],
                    "is_pallet": is_pallet(line["e_type_of_packaging"]),
                }
            )

    for line in lines:
        if not has_pallet:
            has_pallet = is_pallet(line["e_type_of_packaging"])

        total_qty += line["e_qty"]
        dim_amount = _get_dim_amount(line["e_dimUOM"])
        item_length = line["e_dimLength"] * dim_amount
        item_width = line["e_dimWidth"] * dim_amount
        item_height = line["e_dimHeight"] * dim_amount
        item_diagonal = math.sqrt(item_length ** 2 + item_width ** 2 + item_height ** 2)

        item_dead_weight = line["e_weightPerEach"] * _get_weight_amount(
            line["e_weightUOM"]
        )

        m3_to_kg_factor = get_m3_to_kg_factor(
            fp.fp_company_name,
            {
                "is_pallet": is_pallet(line["e_type_of_packaging"]),
                "item_length": item_length,
                "item_width": item_width,
                "item_height": item_height,
                "item_dead_weight": item_dead_weight,
            },
        )
        item_cubic_weight = (
            get_cubic_meter(
                line["e_dimLength"],
                line["e_dimWidth"],
                line["e_dimHeight"],
                line["e_dimUOM"],
                1,
            )
            * m3_to_kg_factor
        )
        dead_weight += item_dead_weight * line["e_qty"]
        total_cubic += item_cubic_weight * line["e_qty"]

        cubic_weight += (
            get_cubic_meter(
                line["e_dimLength"],
                line["e_dimWidth"],
                line["e_dimHeight"],
                line["e_dimUOM"],
                line["e_qty"],
            )
            * m3_to_kg_factor
        )
        one_item_cubic_meter = get_cubic_meter(
            line["e_dimLength"],
            line["e_dimWidth"],
            line["e_dimHeight"],
            line["e_dimUOM"],
            1,
        )

        lengths.append(item_length)
        widths.append(item_width)
        heights.append(item_height)
        diagonals.append(item_diagonal)

        is_dangerous = False
        if "e_dangerousGoods" in line and line["e_dangerousGoods"]:
            is_dangerous = True
            has_dangerous_item = True

        item_max_weight = max(item_cubic_weight, item_dead_weight)
        lines_max_weight.append(math.ceil(item_max_weight))
        lines_max_dead_weight.append(math.ceil(item_dead_weight))

        lines_data.append(
            {
                "pk": line["pk"],
                "max_dimension": max(item_width, item_length, item_height),
                "length": item_length,
                "width": item_width,
                "height": item_height,
                "diagonal": item_diagonal,
                "dead_weight": math.ceil(item_dead_weight),
                "max_weight": math.ceil(item_max_weight),
                "one_item_cubic_meter": one_item_cubic_meter,
                "is_pallet": is_pallet(line["e_type_of_packaging"]),
                "quantity": line["e_qty"],
                "pu_address_state": booking["pu_Address_State"],
                "pu_address_postcode": booking["pu_Address_PostalCode"],
                "pu_address_suburb": booking["pu_Address_Suburb"],
                "pu_address_street": booking["pu_Address_Street"],
                "de_to_address_state": booking["de_To_Address_State"],
                "de_to_address_postcode": booking["de_To_Address_PostalCode"],
                "de_to_address_suburb": booking["de_To_Address_Suburb"],
                "vx_freight_provider": fp.fp_company_name,
                "vx_service_name": booking["vx_serviceName"],
                "is_dangerous": is_dangerous,
                "is_jason_l": booking["client_id"]
                == "1af6bcd2-6148-11eb-ae93-0242ac130002",
            }
        )

    max_dimension = max(lengths + widths + heights)
    dead_weight = math.ceil(dead_weight)
    cubic_weight = math.ceil(cubic_weight)

    order_data = {
        "pu_address_type": booking["pu_Address_Type"] or "",
        "pu_address_state": booking["pu_Address_State"],
        "pu_address_postcode": booking["pu_Address_PostalCode"],
        "pu_address_suburb": booking["pu_Address_Suburb"],
        "pu_address_street": booking["pu_Address_Street"],
        "de_to_address_type": booking["de_To_AddressType"] or "",
        "de_to_address_state": booking["de_To_Address_State"],
        "de_to_address_postcode": booking["de_To_Address_PostalCode"],
        "de_to_address_suburb": booking["de_To_Address_Suburb"],
        "dead_weight": dead_weight,
        "cubic_weight": cubic_weight,
        "total_cubic": total_cubic,
        "max_weight": max(dead_weight, cubic_weight),
        "min_weight": min(dead_weight, cubic_weight),
        "max_item_weight": max(lines_max_weight),
        "max_item_dead_weight": max(lines_max_dead_weight),
        "max_average_weight": max(dead_weight, cubic_weight) / total_qty,
        "min_average_weight": min(dead_weight, cubic_weight) / total_qty,
        "max_dimension": max_dimension,
        "max_length": max(lengths),
        "min_length": min(lengths),
        "max_width": max(widths),
        "min_width": min(widths),
        "max_height": max(heights),
        "min_height": min(heights),
        "max_diagonal": max(diagonals),
        "min_diagonal": min(diagonals),
        "total_qty": total_qty,
        "vx_freight_provider": fp.fp_company_name,
        "vx_service_name": booking["vx_serviceName"],
        "has_dangerous_item": has_dangerous_item,
        "is_tail_lift": int(booking["pu_tail_lift"] or booking["del_tail_lift"] or 0),
        "pu_tail_lift": int(booking["pu_tail_lift"] or 0),
        "de_tail_lift": int(booking["del_tail_lift"] or 0),
        "pu_no_of_assists": int(booking["pu_no_of_assists"] or 0),
        "de_no_of_assists": int(booking["de_no_of_assists"] or 0),
        "client_id": booking["client_id"],
        "is_jason_l": booking["client_id"] == "1af6bcd2-6148-11eb-ae93-0242ac130002",
        "lines_data": lines_data,
        "original_lines_data": original_lines_data,
        "auto_lines_data": auto_lines_data,
        "manual_lines_data": manual_lines_data,
        "scanned_lines_data": scanned_lines_data,
        "quote_obj": quote_obj,
        "has_pallet": has_pallet,
    }

    surcharges, surcharge_opt_funcs = [], []

    if fp.fp_company_name.lower() == "tnt":
        surcharge_opt_funcs = tnt()
    elif fp.fp_company_name.lower() == "allied":
        surcharge_opt_funcs = allied()
    elif fp.fp_company_name.lower() == "hunter":
        surcharge_opt_funcs = hunter()
    elif fp.fp_company_name.lower() == "camerons":
        surcharge_opt_funcs = camerons()
    elif fp.fp_company_name.lower() == "northline":
        surcharge_opt_funcs = northline()
    elif fp.fp_company_name.lower() == "hi-trans":
        surcharge_opt_funcs = hitrans()
    elif fp.fp_company_name.lower() == "blacks":
        surcharge_opt_funcs = blacks()
    elif fp.fp_company_name.lower() == "blanner":
        surcharge_opt_funcs = blanner()
    elif fp.fp_company_name.lower() == "bluestar":
        surcharge_opt_funcs = bluestar()
    elif fp.fp_company_name.lower() == "vfs":
        surcharge_opt_funcs = vfs()
    elif fp.fp_company_name.lower() == "toll":
        surcharge_opt_funcs = toll()
    elif fp.fp_company_name.lower() == "startrack":
        surcharge_opt_funcs = startrack()
    elif fp.fp_company_name.lower() == "dxt":
        surcharge_opt_funcs = dxt()
    elif fp.fp_company_name.lower() == "followmont":
        surcharge_opt_funcs = followmont()
    elif fp.fp_company_name.lower() == "sadleirs":
        surcharge_opt_funcs = sadliers()
    elif fp.fp_company_name.lower() == "afs":
        surcharge_opt_funcs = afs()
    elif fp.fp_company_name.lower() == "pfm corp":
        surcharge_opt_funcs = pfm_corp()
    elif fp.fp_company_name.lower() == "deliver-me direct":
        surcharge_opt_funcs = deliver_me_direct()
    elif fp.fp_company_name.lower() == "direct freight":
        surcharge_opt_funcs = direct_freight()
    elif fp.fp_company_name.lower() == "team global express":
        if not has_pallet:
            surcharge_opt_funcs = team_global_express_ipec()
        else:
            surcharge_opt_funcs = team_global_express_ins()

    if surcharge_opt_funcs:
        for opt_func in surcharge_opt_funcs["order"]:
            result = opt_func(order_data)

            if result:
                surcharges.append(result)

    if surcharge_opt_funcs:
        if fp.fp_company_name.lower() == "allied":
            line_surcharges = []
            for opt_func in surcharge_opt_funcs["line"]:
                for line in lines_data:
                    result = opt_func(line)

                    if result:
                        line_surcharges.append(
                            {
                                "pk": line["pk"],
                                "quantity": line["quantity"],
                                "name": result["name"],
                                "description": result["description"],
                                "value": result["value"],
                            }
                        )
            line_surcharge_dict = {}
            for item in line_surcharges:
                if item["name"] not in line_surcharge_dict:
                    line_surcharge_dict[item["name"]] = {
                        "name": item["name"],
                        "description": item["description"],
                        "value": item["value"] * item["quantity"],
                        "lines": [
                            {
                                "pk": item["pk"],
                                "quantity": item["quantity"],
                                "value": item["value"],
                            }
                        ],
                    }
                else:
                    line_surcharge_dict[item["name"]]["value"] += (
                        item["value"] * item["quantity"]
                    )
                    line_surcharge_dict[item["name"]]["lines"].append(
                        {
                            "pk": item["pk"],
                            "quantity": item["quantity"],
                            "value": item["value"],
                        }
                    )

            surcharges += list(line_surcharge_dict.values())
        else:
            for opt_func in surcharge_opt_funcs["line"]:
                line_surcharges, total, temp = [], 0, {}
                for line in lines_data:
                    result = opt_func(line)

                    if result:
                        temp = result
                        line_surcharges.append(
                            {
                                "pk": line["pk"],
                                "quantity": line["quantity"],
                                "value": result["value"],
                            }
                        )
                        logger.info(
                            f'[SURCHARGE] quantity: {line["quantity"]}, value: {result["value"]}'
                        )
                        if result["value"]:
                            total += line["quantity"] * result["value"]

                if line_surcharges:
                    surcharges.append(
                        {
                            "name": temp["name"],
                            "description": temp["description"],
                            "value": total,
                            "lines": line_surcharges,
                        }
                    )

    return surcharges


def get_surcharges(quote, booking=None):
    if booking:
        return Surcharge.objects.filter(Q(quote=quote) | Q(booking=booking))
    else:
        return Surcharge.objects.filter(quote=quote)


def get_surcharges_total(quote):
    _total = 0
    surcharges = get_surcharges(quote)

    for surcharge in surcharges.filter(line_id__isnull=True):
        _total += surcharge.amount * (surcharge.qty or 1)

    return _total


def gen_surcharges(
    booking_obj,
    line_objs,
    all_line_objs,
    quote_obj,
    client,
    fp,
    data_type="bok_1",
):
    """
    Surcharge table management

    - Calc new surcharge opts
    - Create new Surcharge objects
    """

    LOG_ID = "[SURCHARGE GENERATOR]"
    result = []
    total = 0

    # Do not process for `Allied` Quote
    # if quote_obj.freight_provider.lower() == "allied":
    #     return result

    # Calc new surcharge opts
    try:
        surcharges = find_surcharges(
            booking_obj, line_objs, all_line_objs, quote_obj, fp, data_type
        )
        logger.info(f"{LOG_ID}, {quote_obj}, {surcharges}")
    except Exception as e:
        logger.error(f"{LOG_ID} Booking: {booking_obj}, Quote: {quote_obj}, Error: {e}")
        raise Exception("One booking line has an extremely big demension!")

    # Create new Surcharge objects
    for surcharge in surcharges:
        lines = surcharge.get("lines")
        total += float(surcharge["value"])

        if lines:
            for line in lines:
                surcharge_obj = Surcharge()
                surcharge_obj.quote = quote_obj
                surcharge_obj.name = surcharge["name"]
                surcharge_obj.amount = round(line["value"], 3)
                surcharge_obj.line_id = line["pk"]
                surcharge_obj.qty = line["quantity"]
                surcharge_obj.fp = fp
                surcharge_obj.visible = True
                surcharge_obj.save()
                result.append(surcharge_obj)
        else:
            surcharge_obj = Surcharge()
            surcharge_obj.quote = quote_obj
            surcharge_obj.name = surcharge["name"]
            surcharge_obj.amount = round(surcharge["value"], 3)
            surcharge_obj.fp = fp
            surcharge_obj.visible = True
            surcharge_obj.qty = surcharge.get("quantity") or 1
            surcharge_obj.save()
            result.append(surcharge_obj)

    # Get manually entered surcharges total
    try:
        manual_surcharges_total = booking_obj.get_manual_surcharges_total()
    except:
        manual_surcharges_total = 0

    quote_obj.client_mu_1_minimum_values = quote_obj.fee
    quote_obj.x_price_surcharge = manual_surcharges_total + total

    # Deactivated 2023-04-18
    # if data_type == "bok_1":
    #     client_fps = Client_FP.objects.filter(client=client, is_active=True)

    #     try:
    #         de_addr = {
    #             "state": booking_obj.de_To_Address_State,
    #             "postal_code": booking_obj.de_To_Address_PostalCode,
    #             "suburb": booking_obj.de_To_Address_Suburb,
    #         }
    #     except:
    #         de_addr = {
    #             "state": booking_obj.b_057_b_del_address_state,
    #             "postal_code": booking_obj.b_059_b_del_address_postalcode,
    #             "suburb": booking_obj.b_058_b_del_address_suburb,
    #         }

    #     quotes = apply_markups(quotes, client, fps, client_fps, de_addr)
    #     apply_markups([quote_obj], client, [fp], client_fps)

    return result
