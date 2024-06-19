import logging
import traceback

from api.common.ratio import _m3_to_kg
from api.fp_apis.constants import BUILT_IN_PRICINGS
from api.fp_apis.built_in.operations import *
from api.common.constants import PALLETS
from api.common.time import get_eta_with_suburb


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
    LOG_ID = "[BIP TOLL]"  # BUILT-IN PRICING
    service_types = BUILT_IN_PRICINGS[fp_name]["service_types"]

    has_pallet = False
    has_carton = False
    for booking_line in booking_lines:
        if booking_line.e_type_of_packaging.upper() in PALLETS:
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

        _rules = []
        for rule in rules:
            if has_carton and rule.cost.UOM_charge in ["Kilogram", "KG"]:
                _rules.append(rule)
            if has_pallet and rule.cost.UOM_charge == "Pallet":
                _rules.append(rule)
        rules = _rules

        # Address Filter
        pu_postal_code = booking.pu_Address_PostalCode.zfill(4)
        de_postal_code = booking.de_To_Address_PostalCode.zfill(4)
        avail_pu_zone, avail_de_zone = None, None
        avail_pu_zones, avail_de_zones = [], []

        if pu_postal_code:
            for zone in fp_zones:
                if zone.postal_code == pu_postal_code:
                    avail_pu_zones.append(zone)
        if de_postal_code:
            for zone in fp_zones:
                if zone.postal_code == de_postal_code:
                    avail_de_zones.append(zone)

        _rules = []
        for pu_zone in avail_pu_zones:
            for de_zone in avail_de_zones:
                if _rules:
                    break

                for rule in rules:
                    if rule.pu_zone in pu_zone.zone and rule.de_zone in de_zone.zone:
                        _rules.append(rule)
                        avail_pu_zone = pu_zone.zone
                        avail_de_zone = de_zone.zone

        rules = _rules
        if not avail_pu_zone or not avail_de_zone:
            logger.info(f"@831 {LOG_ID} {fp_name.upper()} - not supported address")
            continue
        else:
            logger.info(
                f"@831 {LOG_ID} PU zone: {avail_pu_zone}, DE zone: {avail_de_zone}"
            )

        if not rules:
            logger.info(f"@831 {LOG_ID} {fp_name.upper()} - not supported address")
            continue

        """
            rule_type_03

            Greater of 1) or 2)
            1) 'Basic Charge' + (Booking Qty of the matching 'Charge UOM' x 'Per UOM Charge')
            2) 'Basic Charge' + ((Length in meters x width in meters x height in meters x 'M3 to KG Factor) x 'Per UOM Charge')
        """
        rule = rules[0]
        cost = rule.cost

        if has_pallet:
            price1 = get_booking_lines_count(booking_lines) * cost.per_UOM_charge
        else:
            price1 = 0

            for booking_line in booking_lines:
                price1 += (
                    booking_line.e_qty
                    * booking_line.e_weightPerEach
                    * cost.per_UOM_charge
                )

        price2 = _m3_to_kg(booking_lines, cost.m3_to_kg_factor) * cost.per_UOM_charge
        price0 = price1 if price1 > price2 else price2
        price0 += cost.basic_charge
        net_price = price0 if price0 > cost.min_charge else cost.min_charge

        logger.info(
            f"{LOG_ID} Final cost: {cost} ({cost.basic_charge}, {cost.min_charge}, {cost.per_UOM_charge}, {cost.m3_to_kg_factor})"
        )
        price = {
            "netPrice": net_price,
            "totalTaxes": 0,
            "serviceName": f"{rule.service_timing_code}",
            "etd": f"{get_eta_with_suburb(booking.de_To_Address_Suburb)} days",
        }
        pricies.append(price)

    return pricies
