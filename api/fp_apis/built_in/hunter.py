import math
import logging
import traceback

from api.models import Fp_freight_providers, Booking_lines, FP_pricing_rules, FP_costs
from api.fp_apis.constants import BUILT_IN_PRICINGS
from api.fp_apis.built_in.operations import *
from api.common.ratio import _get_dim_amount, _get_weight_amount
from api.common.constants import PALLETS
from api.helpers.cubic import get_cubic_meter
from api.fp_apis.utils import get_m3_to_kg_factor

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
    LOG_ID = "[BIP HUNTER]"  # BUILT-IN PRICING
    service_types = BUILT_IN_PRICINGS[fp_name]["service_types"]
    pricies = []

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

    for service_type in service_types:
        logger.info(f"@830 {LOG_ID} {service_type.upper()}")

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
            continue

        kg_price = 0
        pallet_price = 0
        kg_lines = []
        pallet_lines = []
        for line in booking_lines:
            if line.e_type_of_packaging.upper() in PALLETS:
                pallet_lines.append(line)
            else:
                kg_lines.append(line)

        if kg_lines:  # For KG lines
            # Weight Filter
            logger.info(
                f"{LOG_ID} Applying weight filter... rules cnt: {rules.count()}"
            )
            rules = weight_filter(kg_lines, rules, fp)
            logger.info(f"{LOG_ID} Filtered rules - {rules}")
            if not rules:
                continue

            rule = find_lowest_cost_rule(booking_lines, rules, fp)
            cost = rule.cost
            logger.info(f"{LOG_ID} Final cost - {cost}")
            net_price = cost.basic_charge or 0
            m3_to_kg_factor = 250
            dead_weight, cubic_weight = 0, 0

            for item in kg_lines:
                dead_weight += (
                    item.e_weightPerEach
                    * _get_weight_amount(item.e_weightUOM)
                    * item.e_qty
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

            chargable_weight = math.ceil(
                dead_weight if dead_weight > cubic_weight else cubic_weight
            )
            net_price += float(cost.per_UOM_charge or 0) * (
                chargable_weight - (cost.start_qty or 0)
            )
            logger.info(
                f"{LOG_ID} cost: ({cost.basic_charge, cost.per_UOM_charge}), chargable_weight: {chargable_weight}"
            )

            if cost.min_charge and net_price < cost.min_charge:
                net_price = cost.min_charge

            kg_price = net_price

        if pallet_lines:  # For Pallet lines
            # Size(dim) Filter
            if fp.rule_type.rule_type_code in ["rule_type_01", "rule_type_02"]:
                rules = dim_filter(booking, booking_lines, rules, fp, fp_vehicles)

                if not rules:
                    continue

            net_price = 0
            logger.info(f"{LOG_ID} {fp_name.upper()} - filtered rules - {rules}")
            rules = weight_filter(pallet_lines, rules, fp)
            rule = find_lowest_cost_rule(booking_lines, rules, fp)
            cost = rule.cost
            logger.info(f"{LOG_ID} Final cost - {cost}")
            net_price = cost.basic_charge
            dead_weight, cubic_weight = 0, 0

            for item in pallet_lines:
                dead_weight += (
                    item.e_weightPerEach
                    * _get_weight_amount(item.e_weightUOM)
                    * item.e_qty
                )
                dim_amount = _get_dim_amount(item.e_dimUOM)
                weight_amount = _get_weight_amount(item.e_weightUOM)
                m3_to_kg_factor = get_m3_to_kg_factor(
                    fp_name="hunter",
                    data={
                        "is_pallet": True,
                        "item_length": dim_amount * item.e_dimLength,
                        "item_width": dim_amount * item.e_dimWidth,
                        "item_height": dim_amount * item.e_dimHeight,
                        "item_dead_weight": weight_amount * item.e_weightPerEach,
                    },
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

            chargable_weight = math.ceil(
                dead_weight if dead_weight > cubic_weight else cubic_weight
            )
            net_price += float(cost.per_UOM_charge or 0) * (
                chargable_weight - (cost.start_qty or 0)
            )
            logger.info(
                f"{LOG_ID} cost: #{cost}({cost.basic_charge, cost.per_UOM_charge}), chargable_weight: {chargable_weight}"
            )

            if cost.min_charge and net_price < cost.min_charge:
                net_price = cost.min_charge

            pallet_price = net_price

        logger.info(f"{LOG_ID} KG price: {kg_price}, Pallet price: {pallet_price}")
        price = {
            "netPrice": kg_price + pallet_price,
            "totalTaxes": 0,
            "serviceName": f"{rule.service_type}",
            "etd": rule.etd.fp_delivery_time_description,
            "account_code": "AFS AP" if rule.client_id else "DME",
        }
        pricies.append(price)

    return pricies
