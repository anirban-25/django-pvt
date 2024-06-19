import logging
import traceback

from api.models import (
    Fp_freight_providers,
    Booking_lines,
    FP_pricing_rules,
    FP_costs,
    FP_zones,
)
from api.fp_apis.constants import BUILT_IN_PRICINGS
from api.fp_apis.built_in.operations import *
from api.common.ratio import _m3_to_kg, _get_dim_amount, _get_weight_amount
from api.common.time import get_eta_with_suburb
from api.helpers.line import is_carton, is_pallet

logger = logging.getLogger(__name__)


def get_pricing(
    fp_name,
    booking,
    booking_lines,
    client,
    fp,
    fp_zones,
    fp_vehicles,
    fp_rules,
):
    LOG_ID = "[BIP DF]"  # BUILT-IN PRICING
    pricies = []
    service_types = BUILT_IN_PRICINGS[fp_name]["service_types"]

    has_pallet = False
    has_carton = False
    for booking_line in booking_lines:
        if not has_pallet and is_pallet(booking_line.e_type_of_packaging):
            has_pallet = True
        else:
            has_carton = True

    if has_pallet and has_carton:
        logger.info(f"{LOG_ID} Not supported --- has both Pallet and Carton")
    else:
        if has_pallet:
            logger.info(f"{LOG_ID} Pallet")
        else:
            logger.info(f"{LOG_ID} Carton")

    pu_zone, de_zone = None, None
    for zone in fp_zones:
        if zone.postal_code == booking.pu_Address_PostalCode:
            pu_zone = zone.zone
        if zone.postal_code == booking.de_To_Address_PostalCode:
            de_zone = zone.zone

    if not pu_zone or not de_zone:
        raise Exception(
            f"Not supported postal_code. [PU: {booking.pu_Address_PostalCode}, DE: {booking.de_To_Address_PostalCode}]"
        )
    else:
        logger.info(f"@830 {LOG_ID} {fp_name.upper()}, Zones: ({pu_zone}, {de_zone})")

    for service_type in service_types:
        logger.info(
            f"@830 {LOG_ID} {fp_name.upper()}, {service_type.upper()}, {len(fp_rules)}"
        )

        rules = []
        for rule in fp_rules:
            if (
                rule.freight_provider_id == fp.id
                and rule.service_type.lower() == service_type.lower()
                and rule.pu_zone == pu_zone
                and rule.de_zone == de_zone
            ):
                rules.append(rule)

        if not rules:
            raise Exception(
                f"Not supported address. [PU: {booking.pu_Address_PostalCode}, DE: {booking.de_To_Address_PostalCode}]"
            )
            continue

        _rules = []
        for rule in rules:
            if has_carton and rule.cost.UOM_charge == "Kilogram":
                _rules.append(rule)
            if has_pallet and rule.cost.UOM_charge == "Pallet":
                _rules.append(rule)
        rules = _rules

        # Extract lines info
        total_qty, dead_weight, cubic_weight = 0, 0, 0
        m3_to_kg_factor = 250

        for item in booking_lines:
            dead_weight += (
                item.e_weightPerEach * _get_weight_amount(item.e_weightUOM) * item.e_qty
            )
            cubic_weight += (
                get_cubic_meter(
                    item.e_dimLength,
                    item.e_dimWidth,
                    item.e_dimHeight,
                    item.e_dimUOM,
                    item.e_qty,
                )
                * m3_to_kg_factor
            )
            total_qty += item.e_qty

        # Carton case
        if has_carton:
            total_weight = dead_weight if dead_weight > cubic_weight else cubic_weight

            # Total Qty check
            carton_rule = None
            for rule in rules:
                if True or total_weight <= rule.cost.max_weight:
                    carton_rule = rule
                    break

            if not carton_rule:
                logger.info(f"{LOG_ID} Total Qty check failed")
                return []

            # Max Dim & Max Weight check
            cost = carton_rule.cost
            if carton_rule:
                for item in booking_lines:
                    dim_uom = _get_dim_amount(item.e_dimUOM)
                    weight_uom = _get_weight_amount(item.e_weightUOM)
                    item_length = dim_uom * item.e_dimLength
                    item_width = dim_uom * item.e_dimWidth
                    item_height = dim_uom * item.e_dimHeight
                    item_weight = dim_uom * item.e_weightPerEach

                    if (
                        cost.max_weight < item_weight
                        or cost.max_length < item_length
                        or cost.max_width < item_width
                        or cost.max_height < item_height
                    ):
                        logger.info(f"{LOG_ID} Max Dim & Max Weight check failed")
                        return []

            price1 = cost.basic_charge + cost.per_UOM_charge * total_weight
            price2 = cost.min_charge
            net_price = price1 if price1 > price2 else price2
        else:  # Pallet case
            pallet_rule = rules[0]
            net_price = 0

            # Max Dim & Max Weight check
            cost = pallet_rule.cost
            for item in booking_lines:
                dim_uom = _get_dim_amount(item.e_dimUOM)
                weight_uom = _get_weight_amount(item.e_weightUOM)
                item_length = dim_uom * item.e_dimLength
                item_width = dim_uom * item.e_dimWidth
                item_height = dim_uom * item.e_dimHeight
                item_weight = dim_uom * item.e_weightPerEach
                over_length_ratio = 1
                over_width_ratio = 1

                if cost.price_up_to_length < item_length:
                    over_length_ratio = (item_length / cost.price_up_to_length).ceil()

                if cost.price_up_to_length < item_length:
                    over_width_ratio = (item_length / cost.price_up_to_width).ceil()

                if cost.max_weight > item_weight:
                    price1 = cost.basic_charge + cost.per_UOM_charge * item_weight
                    price2 = cost.min_charge
                    price = price1 if price1 > price2 else price2
                    price *= over_width_ratio * over_length_ratio
                    net_price += price * item.e_qty
                else:
                    ratio = cost.per_UOM_charge / cost.max_weight
                    price = ratio * item_weight + cost.basic_charge
                    price *= over_width_ratio * over_length_ratio
                    net_price += price * item.e_qty

        logger.info(
            f"{LOG_ID} Final cost: {cost} ({cost.basic_charge}, {cost.min_charge}, {cost.per_UOM_charge}, {cost.m3_to_kg_factor})"
        )
        price = {
            "netPrice": net_price,
            "totalTaxes": 0,
            "serviceName": f"{rule.service_timing_code}",
            "etd": f"{get_eta_with_suburb(booking.de_To_Address_Suburb)} days",
            "account_code": "Aberdeen",
        }
        pricies.append(price)

    return pricies
