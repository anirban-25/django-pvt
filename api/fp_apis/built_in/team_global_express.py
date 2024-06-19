import math
import logging
import traceback

from api.helpers.cubic import get_rounded_cubic_meter
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
from api.helpers.line import is_carton, is_pallet, is_skid

logger = logging.getLogger(__name__)


def get_price(booking, rules, has_carton, dead_weight, cubic_weight):
    LOG_ID = "[BIP TGE]"  # BUILT-IN PRICING
    carton_rule, pallet_rule = None, None

    if has_carton:  # Carton case
        total_weight = dead_weight if dead_weight > cubic_weight else cubic_weight
        total_weight = math.ceil(total_weight)
        carton_rule = rules[0]
        cost = carton_rule.cost
        price1 = cost.basic_charge + cost.per_UOM_charge * total_weight
        price2 = cost.min_charge
        net_price = price1 if price1 > price2 else price2
    else:  # Pallet case
        total_weight = dead_weight if dead_weight > cubic_weight else cubic_weight
        total_weight = math.ceil(total_weight)

        # Total Qty check
        pallet_rule = None
        for rule in rules:
            start_qty = rule.cost.start_qty or 0
            end_qty = rule.cost.end_qty or 100000
            if start_qty < total_weight and total_weight < end_qty:
                pallet_rule = rule
                break

        if not pallet_rule:
            logger.info(f"{LOG_ID} Service: Pallet Total Qty check failed")
            return None

        # Max Dim & Max Weight check
        cost = pallet_rule.cost
        price1 = cost.basic_charge + cost.per_UOM_charge * total_weight
        price2 = cost.min_charge
        net_price = price1 if price1 > price2 else price2

    rule = carton_rule or pallet_rule
    logger.info(
        f"{LOG_ID} Final cost: {cost} ({cost.basic_charge}, {cost.min_charge}, {cost.per_UOM_charge}, {cost.m3_to_kg_factor})"
    )
    price = {
        "netPrice": net_price,
        "totalTaxes": 0,
        "serviceName": f"{rule.service_timing_code}",
        "etd": f"{get_eta_with_suburb(booking.de_To_Address_Suburb)} days",
        "account_code": "AFS AP" if rule.client_id else "DME ABP",
    }
    return price


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
    LOG_ID = "[BIP TGE]"  # BUILT-IN PRICING
    pricies = []
    service_types = BUILT_IN_PRICINGS[fp_name]["service_types"]

    has_pallet = False
    has_carton = False
    for booking_line in booking_lines:
        if not has_pallet and (
            is_pallet(booking_line.e_type_of_packaging)
            or is_skid(booking_line.e_type_of_packaging)
        ):
            has_pallet = True
        if not has_carton and not is_pallet(booking_line.e_type_of_packaging):
            has_carton = True

    if has_pallet and has_carton:
        raise Exception(f"{LOG_ID} Not supported --- has both Pallet and Carton")
    else:
        if has_pallet:
            logger.info(f"{LOG_ID} Pallet")
        else:
            logger.info(f"{LOG_ID} Carton")

    # Solution for different zones of IPEC and Pallet service
    pu_zones, de_zones = [], []
    for zone in fp_zones:
        if (
            zone.postal_code == booking.pu_Address_PostalCode
            and zone.suburb == booking.pu_Address_Suburb.upper()
            and zone.zone not in pu_zones
        ):
            pu_zones.append(zone.zone)
        if (
            zone.postal_code == booking.de_To_Address_PostalCode
            and zone.suburb == booking.de_To_Address_Suburb.upper()
            and zone.zone not in de_zones
        ):
            de_zones.append(zone.zone)

    if not pu_zones or not de_zones:
        raise Exception(
            f"Not supported postal_code. [PU: {booking.pu_Address_PostalCode}, DE: {booking.de_To_Address_PostalCode}]"
        )

    for service_type in service_types:
        logger.info(
            f"@830 {LOG_ID} {fp_name.upper()}, {service_type.upper()}, {len(fp_rules)}, Zones: ({pu_zones}, {de_zones})"
        )

        rules = []
        for rule in fp_rules:
            # Allow AP AFS rate cards for only AP orders
            if (
                rule.client_id == 28
                and booking.b_client_name != "Anchor Packaging Pty Ltd"
            ):
                continue

            if (
                rule.freight_provider_id == fp.id
                and rule.service_type.lower() == service_type.lower()
                and rule.pu_zone in pu_zones
                and rule.de_zone in de_zones
            ):
                rules.append(rule)

        if not rules:
            msg = f"Not supported address. Service: {service_type} [PU: {booking.pu_Address_PostalCode}, DE: {booking.de_To_Address_PostalCode}]"
            logger.info(msg)
            continue

        _rules = []
        for rule in rules:
            if has_carton and rule.service_type == "IPEC":
                _rules.append(rule)
            if has_pallet and rule.service_type == "Standard Pallet Service":
                _rules.append(rule)
        rules = _rules

        if not rules:
            msg = f"Not supported address. Service: {service_type} [PU: {booking.pu_Address_PostalCode}, DE: {booking.de_To_Address_PostalCode}]"
            logger.info(msg)
            continue

        # Extract lines info
        total_qty, dead_weight, cubic_weight = 0, 0, 0
        m3_to_kg_factor = 250 if has_carton else 333

        for item in booking_lines:
            dead_weight += (
                item.e_weightPerEach * _get_weight_amount(item.e_weightUOM) * item.e_qty
            )
            cubic_weight += (
                get_rounded_cubic_meter(
                    item.e_dimLength,
                    item.e_dimWidth,
                    item.e_dimHeight,
                    item.e_dimUOM,
                    item.e_qty,
                )
                * m3_to_kg_factor
            )
            total_qty += item.e_qty

        dme_rules, client_rules = [], []
        for rule in rules:
            if rule.client_id:
                client_rules.append(rule)
            else:
                dme_rules.append(rule)

        price = None
        if client_rules:
            price = get_price(
                booking, client_rules, has_carton, dead_weight, cubic_weight
            )

            if price:
                pricies.append(price)
        if dme_rules:
            price = get_price(booking, dme_rules, has_carton, dead_weight, cubic_weight)

            if price:
                pricies.append(price)

    return pricies
