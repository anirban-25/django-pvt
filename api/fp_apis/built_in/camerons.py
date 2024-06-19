import math
import logging

from api.fp_apis.constants import BUILT_IN_PRICINGS
from api.fp_apis.built_in.operations import *
from api.helpers.line import is_pallet
from api.common.ratio import _m3_to_kg, _get_dim_amount, _get_weight_amount

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
    LOG_ID = "[BIP CAMERONS]"  # BUILT-IN PRICING
    pricies = []

    # Validations
    if booking.de_To_AddressType and booking.de_To_AddressType.lower() == "residential":
        logger.info(f"@830 {LOG_ID} Not available for `Residential`")
        return pricies
    if booking.pu_Address_Type and booking.pu_Address_Type.lower() == "residential":
        logger.info(f"@830 {LOG_ID} Not available for `Residential`")
        return pricies
    for line in booking_lines:
        if not is_pallet(line.e_type_of_packaging):
            logger.info(f"@830 {LOG_ID} Not available for Cartons")
            return pricies

    service_types = BUILT_IN_PRICINGS[fp_name]["service_types"]
    for service_type in service_types:
        logger.info(
            f"@830 {LOG_ID} {fp_name.upper()}, {service_type.upper()}, {len(fp_rules)}"
        )

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

        # # Size(dim) Filter
        # logger.info(
        #     f"{LOG_ID} {fp_name.upper()} - applying size filter... rules cnt: {len(rules)}"
        # )
        # if fp.rule_type.rule_type_code in ["rule_type_01", "rule_type_02"]:
        #     rules = dim_filter(booking, booking_lines, rules, fp, fp_vehicles)

        #     if not rules:
        #         continue

        # Weight Filter
        """
            rule_type_02

            Booking Qty of the Matching 'Charge UOM' x 'Per UOM Charge
        """
        # logger.info(
        #     f"{LOG_ID} {fp_name.upper()} - applying weight filter... rules cnt: {len(rules)}"
        # )
        # rules = weight_filter(booking_lines, rules, fp)
        # if not rules:
        #     logger.info(
        #         f"{LOG_ID} {fp_name.upper()} - after weight filter, rules cnt: {len(rules)}"
        #     )
        #     continue

        logger.info(f"{LOG_ID} {fp_name.upper()} - filtered rules - {rules}")

        normal_item_count = 0
        oversize_item_count = 0
        for line in booking_lines:
            dim_amount = _get_dim_amount(line.e_dimUOM)
            dim_weight = _get_weight_amount(line.e_weightUOM)
            item_length = dim_amount * line.e_dimLength
            item_width = dim_amount * line.e_dimWidth
            height = round(dim_amount * line.e_dimHeight, 2)
            weight = round(dim_weight * line.e_weightPerEach, 2)
            over_length_ratio = 1
            over_width_ratio = 1
            item_count = 1

            if 1.2 < item_length:
                over_length_ratio = math.ceil(item_length / 1.2)
            if 1.2 < item_width:
                over_width_ratio = math.ceil(item_width / 1.2)
            item_count = over_length_ratio * over_width_ratio * line.e_qty

            if height > 1.4 or weight > 500:
                oversize_item_count += item_count
            else:
                normal_item_count += item_count

        normal_cost = None
        oversize_cost = None
        for rule in rules:
            cost = rule.cost
            if (
                cost.max_weight > 500
                and cost.start_qty <= oversize_item_count
                and cost.end_qty >= oversize_item_count
            ):
                oversize_cost = cost
            if (
                cost.max_weight <= 500
                and cost.start_qty <= normal_item_count
                and cost.end_qty >= normal_item_count
            ):
                normal_cost = cost

        # Final price calculation
        net_price = 0
        if normal_cost:
            net_price += normal_cost.per_UOM_charge * normal_item_count
        if oversize_cost:
            net_price += oversize_cost.per_UOM_charge * oversize_item_count

        logger.info(
            f"{LOG_ID} {fp_name.upper()}\n final cost = {normal_cost.per_UOM_charge if normal_cost else 0} * {normal_item_count} + {oversize_cost.per_UOM_charge if oversize_cost else 0} * {oversize_item_count} = {net_price}"
        )

        price = {
            "netPrice": net_price,
            "totalTaxes": 0,
            "serviceName": f"{rule.service_timing_code}",
            "etd": rule.etd.fp_delivery_time_description,
            "account_code": "AFS AP" if rule.client_id else "DME",
        }
        pricies.append(price)

    return pricies
