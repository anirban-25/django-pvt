import math
import logging
import traceback

from api.common.ratio import _m3_to_kg
from api.fp_apis.constants import BUILT_IN_PRICINGS
from api.fp_apis.built_in.operations import *
from api.common.ratio import _get_dim_amount, _get_weight_amount
from api.helpers.line import is_carton, is_pallet, is_skid

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
    LOG_ID = "[BIP DXT]"  # BUILT-IN PRICING
    service_types = BUILT_IN_PRICINGS[fp_name]["service_types"]
    pricies = []

    has_pallet = False
    has_carton = False
    for booking_line in booking_lines:
        if not has_pallet and (
            is_pallet(booking_line.e_type_of_packaging)
            and not is_skid(booking_line.e_type_of_packaging)
        ):
            has_pallet = True
        if not has_carton and not is_pallet(booking_line.e_type_of_packaging):
            has_carton = True

    # if has_pallet and has_carton:
    #     raise Exception(f"{LOG_ID} Not supported --- has both Pallet and Carton")
    # else:
    #     if has_pallet:
    #         logger.info(f"{LOG_ID} Pallet")
    #     else:
    #         logger.info(f"{LOG_ID} Carton")

    # Solution for different zones of Carton and Pallet services
    pu_zones, de_zones = [], []
    for zone in fp_zones:
        if (
            zone.postal_code == booking.pu_Address_PostalCode
            and zone.suburb.upper() == booking.pu_Address_Suburb.upper()
            and zone.zone not in pu_zones
        ):
            pu_zones.append(zone.zone.upper())
        if (
            zone.postal_code == booking.de_To_Address_PostalCode
            and zone.suburb.upper() == booking.de_To_Address_Suburb.upper()
            and zone.zone not in de_zones
        ):
            de_zones.append(zone.zone.upper())

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
            if (
                rule.freight_provider_id == fp.id
                and rule.service_type.lower() == service_type.lower()
                and rule.pu_zone.upper() in pu_zones
                and rule.de_zone.upper() in de_zones
            ):
                rules.append(rule)

        if not rules:
            msg = f"Not supported address. Service: {service_type} [PU: {booking.pu_Address_PostalCode}, DE: {booking.de_To_Address_PostalCode}]"
            logger.info(msg)
            continue

        # _rules = []
        # for rule in rules:
        #     if has_pallet and rule.service_type == "Pallet":
        #         _rules.append(rule)
            
        #     if not has_pallet and rule.service_type == "Road Service":
        #         _rules.append(rule)
        # rules = _rules

        is_pallet_rule = service_type == "Pallet"

        if not rules:
            msg = f"Not supported address. Service: {service_type} [PU: {booking.pu_Address_PostalCode}, DE: {booking.de_To_Address_PostalCode}]"
            logger.info(msg)
            continue

        """
            rule_type_02

            Booking Qty of the Matching 'Charge UOM' x 'Per UOM Charge
        """
        logger.info(
            f"{LOG_ID} {fp_name.upper()} - applying weight filter... rules cnt: {len(rules)}"
        )
        rules = weight_filter(booking_lines, rules, fp)

        if not rules:
            logger.info(
                f"{LOG_ID} {fp_name.upper()} - after weight filter, rules cnt: {len(rules)}"
            )
            continue

        # Extract lines info
        total_qty, dead_weight, cubic_weight = 0, 0, 0
        m3_to_kg_factor = 250 if not is_pallet_rule else 333
        logger.info(f"{LOG_ID} is_pallet_rule:{is_pallet_rule}")

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
        logger.info(f"{LOG_ID} total_qty:{total_qty}")

        if not is_pallet_rule:  # None Pallet case
            best_rule = rules[0]
            best_cost = best_rule.cost
            total_weight = dead_weight if dead_weight > cubic_weight else cubic_weight
       
            price1 = best_cost.basic_charge + best_cost.per_UOM_charge * total_weight
            price2 = best_cost.min_charge
            net_price = price1 if price1 > price2 else price2
        else:  # Pallet case
            item_count = 0
            best_rule = rules[0]
            best_cost = best_rule.cost

            # Oversize
            for item in booking_lines:
                dim_uom = _get_dim_amount(item.e_dimUOM)
                item_length = dim_uom * item.e_dimLength
                item_width = dim_uom * item.e_dimWidth
                over_length_ratio = 1
                over_width_ratio = 1

                if best_cost.price_up_to_length < item_length:
                    over_length_ratio = math.ceil(item_length / best_cost.price_up_to_length)

                if best_cost.price_up_to_length < item_length:
                    over_width_ratio = math.ceil(item_width / best_cost.price_up_to_width)

                item_count += over_length_ratio * over_width_ratio * item.e_qty

            net_price = best_cost.per_UOM_charge * total_qty * item_count

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
