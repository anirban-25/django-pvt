import math
import logging
import os
import json
import requests

from api.common import trace_error
from api.common.ratio import _get_dim_amount, _get_weight_amount

logger = logging.getLogger(__name__)


def get_number_of_pallets(booking_lines, pallet):
    if len(booking_lines) == 0:
        logger.info(f"No Booking Lines to deliver")
        return None, None

    if not pallet:
        logger.info(f"No Pallet")
        return None, None

    pallet_weight = 500
    m3_to_kg_factor = 250
    dim_list = [2.1, pallet.length / 1000, pallet.width / 1000]
    dim_list.sort()
    pallet_height = dim_list[0]
    pallet_width = dim_list[1]
    pallet_length = dim_list[2]
    pallet_cube = pallet_length * pallet_width * pallet_height * 0.8

    (
        palletized_lines,
        unpalletized_line_pks,
        line_dimensions,
        sum_cube,
        unpalletized_dead_weight,
        unpalletized_cubic_weight,
    ) = ([], [], [], 0, 0, 0)

    for item in booking_lines:
        line_length = _get_dim_amount(item.l_004_dim_UOM) * item.l_005_dim_length
        line_width = _get_dim_amount(item.l_004_dim_UOM) * item.l_006_dim_width
        line_height = _get_dim_amount(item.l_004_dim_UOM) * item.l_007_dim_height
        dim_list = [line_length, line_width, line_height]
        dim_list.sort()
        length = dim_list[2]
        width = dim_list[1]
        height = dim_list[0]

        if (
            length <= pallet_length
            and width <= pallet_width
            and height <= pallet_height
        ):
            palletized_lines.append(item)
            sum_cube += width * height * length * item.l_002_qty
        else:
            unpalletized_line_pks.append(item.pk)
            unpalletized_dead_weight += (
                item.l_002_qty
                * item.l_009_weight_per_each
                * _get_weight_amount(item.l_008_weight_UOM)
            )
            unpalletized_cubic_weight += length * width * height * m3_to_kg_factor

    unpalletized_weight = max(unpalletized_dead_weight, unpalletized_cubic_weight)
    number_of_pallets_for_unpalletized = math.ceil(unpalletized_weight / pallet_weight)
    number_of_pallets_for_palletized = math.ceil(sum_cube / pallet_cube)

    return number_of_pallets_for_palletized, unpalletized_line_pks


def pallet_to_dict(pallets, pallet_self_height):
    pallets_data = []
    for index, pallet in enumerate(pallets):
        pallets_data.append(
            {
                "w": pallet.width / 1000,
                "h": (pallet.height - pallet_self_height) / 1000,
                "d": pallet.length / 1000,
                "max_wg": pallet.max_weight or 0,
                "id": index,
            }
        )

    return pallets_data


def lines_to_dict(bok_2s):
    dim_min_limit = 0.2
    dim_max_limit = 0.5
    lines_data = []

    for index, item in enumerate(bok_2s):
        try:
            item_length = _get_dim_amount(item.l_004_dim_UOM) * item.l_005_dim_length
            item_width = _get_dim_amount(item.l_004_dim_UOM) * item.l_006_dim_width
            item_height = _get_dim_amount(item.l_004_dim_UOM) * item.l_007_dim_height
            item_weight = (
                _get_weight_amount(item.l_008_weight_UOM) * item.l_009_weight_per_each
            )
            item_quantity = item.l_002_qty
        except AttributeError:
            item_length = _get_dim_amount(item.e_dimUOM) * item.e_dimLength
            item_width = _get_dim_amount(item.e_dimUOM) * item.e_dimWidth
            item_height = _get_dim_amount(item.e_dimUOM) * item.e_dimHeight
            item_weight = _get_weight_amount(item.e_weightUOM) * item.e_weightPerEach
            item_quantity = item.e_qty

        dims = [item_length, item_width, item_height]
        dims.sort()

        lines_data.append(
            {
                "w": dims[1],
                "h": dims[0],
                "d": dims[2],
                "q": item_quantity,
                "vr": 0,
                "wg": item_weight,
                "id": index,
            }
        )

    return lines_data


def vehicles_to_dict(vehicles):
    vehicles_dict = []
    for vehicle in vehicles:
        dim_amount = _get_dim_amount(vehicle.dim_UOM)
        dims = [
            dim_amount * vehicle.max_width,
            dim_amount * vehicle.max_height,
            dim_amount * vehicle.max_length,
        ]
        dims.sort()
        vehicles_dict.append(
            {
                "w": dims[1],
                "h": dims[0],
                "d": dims[2],
                "max_wg": vehicle.max_mass,
                "id": vehicle.id,
            }
        )

    return vehicles_dict


def lines_to_pallet(lines_data, pallets_data):
    data = {
        "bins": pallets_data,
        "items": lines_data,
        "username": os.environ["3D_PACKING_API_USERNAME"],
        "api_key": os.environ["3D_PACKING_API_KEY"],
        "params": {
            "images_background_color": "255,255,255",
            "images_bin_border_color": "59,59,59",
            "images_bin_fill_color": "230,230,230",
            "images_item_border_color": "214,79,79",
            "images_item_fill_color": "177,14,14",
            "images_item_back_border_color": "215,103,103",
            "images_sbs_last_item_fill_color": "99,93,93",
            "images_sbs_last_item_border_color": "145,133,133",
            "images_width": 100,
            "images_height": 100,
            "images_source": "file",
            "images_sbs": 1,
            "stats": 1,
            "item_coordinates": 1,
            "images_complete": 1,
            "images_separated": 1,
        },
    }

    url = f"{os.environ['3D_PACKING_API_URL']}/packer/packIntoMany"
    response = requests.post(url, data=json.dumps(data))

    try:
        res_data = response.json()["response"]
        if res_data["status"] == -1:
            msg = ""
            for error in res_data["errors"]:
                msg += f"{error['message']} \n"
            logger.info(f"Packing API Error: {msg}")
    except Exception as e:
        trace_error.print()
        logger.error(
            f"3D_PACKING_API issue - url: {url}\ndata: {data}\n, error: {str(e)}"
        )
        raise Exception("3D_PACKING_API issue")

    return res_data


def refine_pallets(
    packed_results, original_pallets, original_lines, pallet_self_height
):
    formatted_pallets = []
    for pallet in packed_results["bins_packed"]:
        packed_height, items = 0, []
        for item in pallet["items"]:
            if item["coordinates"]["y2"] > packed_height:
                packed_height = item["coordinates"]["y2"]

            try:
                index = [each["line_index"] for each in items].index(item["id"])
            except ValueError:
                index = None

            if index is not None:
                items[index]["quantity"] += 1
            else:
                items.append(
                    {
                        "line_index": item["id"],
                        "line_obj": original_lines[item["id"]],
                        "quantity": 1,
                    }
                )

        new_pallet = {
            "pallet_index": pallet["bin_data"]["id"],
            "pallet_obj": original_pallets[pallet["bin_data"]["id"]],
            "packed_height": packed_height + (pallet_self_height / 1000),
            "quantity": 1,
            "lines": items,
        }

        exists_equal = False
        for formatted_pallet in formatted_pallets:
            if (
                formatted_pallet["pallet_index"] == new_pallet["pallet_index"]
                and formatted_pallet["packed_height"] == new_pallet["packed_height"]
                and len(formatted_pallet["lines"]) == len(new_pallet["lines"])
            ):
                is_equal = True
                for index, line in enumerate(formatted_pallet["lines"]):
                    if (
                        line["line_index"] != new_pallet["lines"][index]["line_index"]
                        or line["quantity"] != new_pallet["lines"][index]["quantity"]
                    ):
                        is_equal = False
                if is_equal:
                    formatted_pallet["quantity"] += 1
                    exists_equal = True
            else:
                continue
        if not exists_equal:
            formatted_pallets.append(new_pallet)

    non_pallets = [
        {
            "line_index": item["id"],
            "line_obj": original_lines[item["id"]],
            "quantity": item["q"],
        }
        for item in packed_results["not_packed_items"]
    ]

    return formatted_pallets, non_pallets


def get_palletized_by_ai(bok_2s, pallets):
    # pallet self height
    pallet_self_height = 150

    # prepare pallets data
    pallets_data = pallet_to_dict(pallets, pallet_self_height)

    # prepare lines data
    lines_data = lines_to_dict(bok_2s)

    packed_results = lines_to_pallet(lines_data, pallets_data)

    # check duplicated Pallets and non palletizable ones with only small itemsf
    palletized, non_palletized = refine_pallets(
        packed_results, pallets, bok_2s, pallet_self_height
    )

    return palletized, non_palletized


def get_pallets():
    payload = {
        "bins": [
            {"w": 5, "h": 5, "d": 5, "max_wg": 0, "id": "Bin1"},
            {"w": 3, "h": 3, "d": 3, "max_wg": 0, "id": "Bin2"},
        ],
        "items": [
            {"w": 5, "h": 3, "d": 2, "q": 2, "vr": 1, "wg": 0, "id": "Item1"},
            {"w": 3, "h": 3, "d": 3, "q": 3, "vr": 1, "wg": 0, "id": "Item2"},
        ],
        "username": "dev@deliver-me.com.au",
        "api_key": "0c24eae8cee659c910fe804bb2084c07",
        "params": {
            "images_background_color": "255,255,255",
            "images_bin_border_color": "59,59,59",
            "images_bin_fill_color": "230,230,230",
            "images_item_border_color": "214,79,79",
            "images_item_fill_color": "177,14,14",
            "images_item_back_border_color": "215,103,103",
            "images_sbs_last_item_fill_color": "99,93,93",
            "images_sbs_last_item_border_color": "145,133,133",
            "images_width": 100,
            "images_height": 100,
            "images_source": "file",
            "images_sbs": 1,
            "stats": 1,
            "item_coordinates": 1,
            "images_complete": 1,
            "images_separated": 1,
        },
    }
    header = {"Content-type": "application/json", "Accept": "text/plain"}
    url = f"{os.environ['3D_PACKING_API_URL']}/packer/packIntoMany"
    response = requests.post(url, data=json.dumps(payload))

    content = response.content.decode("utf8")
    json_data = json.loads(content)
