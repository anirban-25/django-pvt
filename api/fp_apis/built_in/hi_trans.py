import math
import logging
import traceback

from api.common.ratio import _m3_to_kg
from api.fp_apis.constants import BUILT_IN_PRICINGS
from api.fp_apis.built_in.operations import *
from api.common.ratio import _get_dim_amount, _get_weight_amount

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
    LOG_ID = "[BIP HI-TRNAS]"  # BUILT-IN PRICING
    service_types = BUILT_IN_PRICINGS[fp_name]["service_types"]
    pricies = []

    for service_type in service_types:
        logger.info(f"@830 {LOG_ID} {fp_name.upper()}, {service_type.upper()}")

        rules = []
        for rule in fp_rules:
            if (
                rule.freight_provider_id == fp.id
                and rule.service_timing_code.lower() == service_type.lower()
            ):
                rules.append(rule)

        # Address Filter
        rules = address_filter(booking, booking_lines, rules, fp, fp_zones)

        if not rules:
            logger.info(f"@831 {LOG_ID} {fp_name.upper()} - not supported address")
            continue

        """
            rule_type_02

            Booking Qty of the Matching 'Charge UOM' x 'Per UOM Charge
        """
        total_qty = 0
        dead_weight, cubic_weight = 0, 0
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

        best_cost = None
        best_rule = None
        for rule in rules:
            cost = rule.cost
            if cost.end_qty > total_qty:
                best_cost = cost
                best_rule = rule
                break

        net_price = best_cost.basic_charge or 0
        chargable_weight = dead_weight if dead_weight > cubic_weight else cubic_weight
        net_price += float(best_cost.per_UOM_charge or 0) * math.ceil(chargable_weight)
        logger.info(f"{LOG_ID} Final cost - {best_cost}")

        price = {
            "netPrice": net_price,
            "totalTaxes": 0,
            "serviceName": f"{best_rule.service_type}",
            "etd": best_rule.etd.fp_delivery_time_description,
            "account_code": "AFS AP" if rule.client_id else "DME",
        }
        pricies.append(price)

    return pricies
