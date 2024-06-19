import math
import logging
import traceback

from api.fp_apis.constants import BUILT_IN_PRICINGS
from api.fp_apis.built_in.operations import *
from api.common.ratio import _get_dim_amount, _get_weight_amount
from api.helpers.cubic import get_cubic_meter

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
    LOG_ID = f"[BIP {fp_name.upper()}]"  # BUILT-IN PRICING
    service_types = BUILT_IN_PRICINGS[fp_name]["service_types"]
    pricies = []

    pu_zone, de_zone = None, None
    for zone in fp_zones:
        if zone.postal_code == booking.pu_Address_PostalCode:
            pu_zone = zone.zone
        if zone.postal_code == booking.de_To_Address_PostalCode:
            de_zone = zone.zone

    if not pu_zone or not de_zone:
        error_msg = f"Not supported postal_code. PU: {booking.pu_Address_PostalCode}, DE: {booking.de_To_Address_PostalCode}"
        raise Exception(error_msg)

    for service_type in service_types:
        logger.info(
            f"@830 {LOG_ID} {fp_name.upper()}, {service_type.upper()}, Zones: ({pu_zone}, {de_zone})"
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
            continue

        # Weight Filter
        logger.info(f"{LOG_ID} Applying weight filter... rules cnt: {len(rules)}")
        rules = weight_filter(booking_lines, rules, fp)
        # logger.info(f"{LOG_ID} Filtered rules - {rules}")
        if not rules:
            continue

        """
            rule_type_02

            Booking Qty of the Matching 'Charge UOM' x 'Per UOM Charge
        """
        rule = find_lowest_cost_rule(booking_lines, rules, fp)
        net_price = rule.cost.basic_charge or 0
        m3_to_kg_factor = 250
        dead_weight, cubic_weight = 0, 0

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

        chargable_weight = dead_weight if dead_weight > cubic_weight else cubic_weight
        if service_type == "Road Express" and chargable_weight > 20:
            chargable_weight -= 20
        net_price += float(rule.cost.per_UOM_charge or 0) * math.ceil(chargable_weight)
        logger.info(f"{LOG_ID} Final cost - {rule.cost}")

        price = {
            "netPrice": net_price,
            "totalTaxes": 0,
            "serviceName": f"{rule.service_type}",
            "etd": 3,
            "account_code": "AFS AP" if rule.client_id else "DME",
        }
        pricies.append(price)

    return pricies
