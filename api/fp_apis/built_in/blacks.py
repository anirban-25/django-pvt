import logging
import traceback

from api.common.ratio import _m3_to_kg
from api.fp_apis.constants import BUILT_IN_PRICINGS
from api.fp_apis.built_in.operations import *

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
    LOG_ID = "[BIP BLACKS]"  # BUILT-IN PRICING
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

        logger.info(
            f"{LOG_ID} {fp_name.upper()} - applying size filter... rules cnt: {len(rules)}"
        )

        # Size(dim) Filter
        if fp.rule_type.rule_type_code in ["rule_type_01", "rule_type_02"]:
            rules = dim_filter(booking, booking_lines, rules, fp, fp_vehicles)

            if not rules:
                continue

        """
            rule_type_03

            Greater of 1) or 2)
            1) 'Basic Charge' + (Booking Qty of the matching 'Charge UOM' x 'Per UOM Charge')
            2) 'Basic Charge' + ((Length in meters x width in meters x height in meters x 'M3 to KG Factor) x 'Per UOM Charge')
        """
        rule = find_lowest_cost_rule(booking_lines, rules, fp)
        cost = rule.cost
        net_price = get_booking_lines_count(booking_lines) * cost.per_UOM_charge
        # price2 = (
        #     _m3_to_kg(booking_lines, (cost.m3_to_kg_factor or 250))
        #     * cost.per_UOM_charge
        # )
        # net_price = price1 if price1 > price2 else price2
        logger.info(f"{LOG_ID} {fp_name.upper()} - final cost - {cost}")

        price = {
            "netPrice": net_price,
            "totalTaxes": 0,
            "serviceName": f"{rule.service_type}",
            "etd": rule.etd.fp_delivery_time_description,
            "account_code": "AFS AP" if rule.client_id else "DME",
        }
        pricies.append(price)

    return pricies
