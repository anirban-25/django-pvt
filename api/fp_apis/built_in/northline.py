import math
import logging
import traceback

from api.fp_apis.constants import BUILT_IN_PRICINGS
from api.fp_apis.built_in.operations import *
from api.common.ratio import _get_dim_amount, _get_weight_amount
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
    LOG_ID = "[BIP NORTHLINE]"  # BUILT-IN PRICING
    service_types = BUILT_IN_PRICINGS[fp_name]["service_types"]
    pricies = []

    # if booking.de_To_AddressType and booking.de_To_AddressType.lower() == "residential":
    #     logger.info(f"@830 {LOG_ID} Not available for `Residential`")
    #     return pricies

    # Skip for Sydney Metro
    de_postal_code = int(booking.de_To_Address_PostalCode or 0)
    if (1000 <= de_postal_code and de_postal_code <= 2249) or (
        2760 <= de_postal_code and de_postal_code <= 2770
    ):
        logger.info(f"@830 {LOG_ID} Sydney Metro --- skipped!")
        return pricies

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

        # Weight Filter
        logger.info(
            f"{LOG_ID} {fp_name.upper()} - applying size filter... rules cnt: {len(rules)}"
        )
        if fp.rule_type.rule_type_code in ["rule_type_01", "rule_type_02"]:
            rules = weight_filter(booking_lines, rules, fp)

            if not rules:
                continue

        """
            rule_type_02

            Booking Qty of the Matching 'Charge UOM' x 'Per UOM Charge
        """
        logger.info(f"{LOG_ID} {fp_name.upper()} - filtered rules - {rules}")
        rule = find_lowest_cost_rule(booking_lines, rules, fp)
        net_price = rule.cost.basic_charge
        dead_weight, cubic_weight = 0, 0

        for item in booking_lines:
            dead_weight += (
                item.e_weightPerEach * _get_weight_amount(item.e_weightUOM) * item.e_qty
            )
            cubic_weight += round(
                get_cubic_meter(
                    item.e_dimLength,
                    item.e_dimWidth,
                    item.e_dimHeight,
                    item.e_dimUOM,
                    item.e_qty,
                )
                * get_m3_to_kg_factor(fp_name)
            )

        chargable_weight = dead_weight if dead_weight > cubic_weight else cubic_weight
        net_price += float(rule.cost.per_UOM_charge) * math.ceil(chargable_weight)

        if net_price < rule.cost.min_charge:
            net_price = rule.cost.min_charge

        logger.info(f"{LOG_ID} {fp_name.upper()} - final cost - {rule.cost}")

        price = {
            "netPrice": net_price,
            "totalTaxes": 0,
            "serviceName": f"{rule.service_timing_code}",
            "etd": rule.etd.fp_delivery_time_description,
            "account_code": "AFS AP" if rule.client_id else "DME",
        }
        pricies.append(price)

    return pricies
