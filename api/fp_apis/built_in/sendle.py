import logging
import traceback

from api.models import Fp_freight_providers, Booking_lines, FP_pricing_rules, FP_costs
from api.fp_apis.constants import BUILT_IN_PRICINGS
from api.fp_apis.built_in.operations import *
from api.common.ratio import _get_dim_amount, _get_weight_amount
from api.common.constants import PALLETS
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
    LOG_ID = "[BIP SENDLE]"  # BUILT-IN PRICING
    service_types = BUILT_IN_PRICINGS[fp_name]["service_types"]
    pricies = []
    total_weight = 0

    for line in booking_lines:
        total_weight += (
            line.e_qty * _get_weight_amount(line.e_weightUOM) * line.e_weightPerEach
        )

        if _get_dim_amount(line.e_dimUOM) * line.e_dimLength > 1.2:
            raise Exception(
                f"{LOG_ID} Exceed max length(1.2m): {_get_dim_amount(line.e_dimUOM) * line.e_dimLength}"
            )

        if _get_dim_amount(line.e_dimUOM) * line.e_dimLength > 1.2:
            raise Exception(
                f"{LOG_ID} Exceed max width(1.2m): {_get_dim_amount(line.e_dimUOM) * line.e_dimLength}"
            )

        if _get_dim_amount(line.e_dimUOM) * line.e_dimLength > 1.2:
            raise Exception(
                f"{LOG_ID} Exceed max height(1.2m): {_get_dim_amount(line.e_dimUOM) * line.e_dimLength}"
            )

    if total_weight > 25:
        raise Exception(f"{LOG_ID} Exceed max weight(25kg): {total_weight}")

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
            logger.info(f"{LOG_ID} {fp_name.upper()} - not supported address")
            continue

        rules = weight_filter(booking_lines, rules, fp)
        logger.info(f"{LOG_ID} Weight filtered: {len(rules)}")

        if not rules:
            logger.info(f"{LOG_ID} {fp_name.upper()} - weight exceeded")
            continue

        rules = volume_filter(booking_lines, rules, fp)
        logger.info(f"{LOG_ID} Volume filtered: {len(rules)}")

        if not rules:
            logger.info(f"{LOG_ID} {fp_name.upper()} - volumn exceeded")
            continue

        cost = rules[0].cost
        price = {
            "netPrice": cost.basic_charge,
            "totalTaxes": 0,
            "serviceName": f"{rules[0].service_timing_code}",
            "etd": rules[0].etd.fp_delivery_time_description,
            "account_code": "AFS AP" if rules[0].client_id else "DME",
        }
        pricies.append(price)

    return pricies
