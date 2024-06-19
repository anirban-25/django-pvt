import math
import logging
import traceback

from api.models import AlliedETD
from api.common.ratio import _get_dim_amount, _get_weight_amount
from api.fp_apis.constants import BUILT_IN_PRICINGS
from api.fp_apis.built_in.operations import *

logger = logging.getLogger(__name__)


def _get_metro_abbr(postal_code):
    _metro_abbr = "SYD"

    if (
        (postal_code >= 4000 and postal_code <= 4207)
        or (postal_code >= 4300 and postal_code < 4305)
        or (postal_code >= 4500 and postal_code <= 4519)
    ):
        _metro_abbr = "BNE"  # "Brisbane Metro"
    elif postal_code >= 5000 and postal_code <= 5199:
        _metro_abbr = "ADL"  # "Adelaide Metro"
    elif postal_code >= 6000 and postal_code <= 6199:
        _metro_abbr = "PER"  # "Perth Metro"
    elif postal_code >= 2000 and postal_code <= 2234:
        _metro_abbr = "SYD"  # "Sydney Metro"
    elif postal_code >= 3000 and postal_code <= 3207:
        _metro_abbr = "MEL"  # "Melbourne Metro"

    return _metro_abbr


def _get_etd(pu_postal_code, de_zone):
    """
    Get ETD
    """
    LOG_ID = "[_get_etd]"

    metro_abbr = _get_metro_abbr(int(pu_postal_code))

    if not metro_abbr:
        message = f"@735 {LOG_ID} Allied can't support this PU address. PU postal_code: {pu_postal_code}"
        logger.info(message)
        raise Exception(message)

    allied_etds = AlliedETD.objects.filter(zone=de_zone)

    if not metro_abbr or allied_etds.count() == 0:
        message = (
            f"@736 {LOG_ID} ETD not found from 'AlliedETD' table. DE Zone: {de_zone}"
        )
        logger.info(message)
        raise Exception(message)

    if metro_abbr == "SYD":
        return allied_etds.first().syd
    elif metro_abbr == "BNE":
        return allied_etds.first().bne
    elif metro_abbr == "MEL":
        return allied_etds.first().mel
    elif metro_abbr == "ADL":
        return allied_etds.first().adl
    elif metro_abbr == "PER":
        return allied_etds.first().per


def _has_oversize_pallet(fp_name, booking_lines):
    """
    standard pallet
        size: 1.2 x 1.2 x 1.4 meter
        weight: 500 kg

    oversize pallet
        size: 1.2 x 1.2 x 2.1 meter
        weight: 1000 kg
    """

    LOG_ID = "[_has_oversize_pallet]"

    standard_width = 1.2
    standard_length = 1.2
    standard_height = 1.4
    standard_weight = 500

    oversize_width = 1.2
    oversize_length = 1.2
    oversize_height = 2.1
    oversize_weight = 1000

    size_types = []
    for item in booking_lines:
        width = _get_dim_amount(item.e_dimUOM) * item.e_dimWidth
        length = _get_dim_amount(item.e_dimUOM) * item.e_dimLength
        height = _get_dim_amount(item.e_dimUOM) * item.e_dimHeight
        weight = _get_weight_amount(item.e_weightUOM) * item.e_weightPerEach

        if (
            width < standard_width
            and length < standard_length
            and height < standard_height
            and weight < standard_weight
        ):
            size_type = "STANDARD"
        elif (
            width < oversize_width
            and length < oversize_length
            and height < oversize_height
            and weight < oversize_weight
        ):
            size_type = "OVERSIZE"
        else:
            message = f"@731 {LOG_ID} {fp_name.upper()} Booking has a line that size/weight is not supported."
            logger.info(message)
            raise Exception(message)

        if not size_type in size_types:
            size_types.append(size_type)

    if "OVERSIZE" in size_types:
        return True
    else:
        return False


def _select_service_type(fp_name, booking_lines):
    LOG_ID = "[_select_service_type]"
    service_types = BUILT_IN_PRICINGS[fp_name]["service_types"]

    # Check if Booking has only `Carton`s or `Pallet`s
    e_type_of_packagings = []
    for booking_line in booking_lines:
        if booking_line.e_type_of_packaging.upper() in ["CTN", "CARTON"]:
            e_type_of_packaging = "carton"
        else:
            e_type_of_packaging = "pallet"

        if not e_type_of_packaging in e_type_of_packagings:
            e_type_of_packagings.append(e_type_of_packaging)

    if len(e_type_of_packagings) == 0 or len(e_type_of_packagings) == 2:
        message = f"@730 {LOG_ID} {fp_name.upper()} Booking has lines packed by different types."
        logger.info(message)
        raise Exception(message)

    # Only "Road Express" is available for Allied
    return service_types[0]

    # if e_type_of_packagings[0] == "carton":
    #     return service_types[0]  # "Road Express"
    # else:
    #     if not _has_oversize_pallet(fp_name, booking_lines):
    #         return service_types[1]  # "Standard Pallet Rate"
    #     else:
    #         return service_types[2]  # "Oversized Pallet Rate"


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
    LOG_ID = "[BIP ALLIED]"  # BUILT-IN PRICING

    # Select service_type
    service_type = _select_service_type(fp_name, booking_lines)
    logger.info(f"@830 {LOG_ID} {service_type.upper()}")

    # Get pu_zone
    pu_zone, de_zone = None, None

    for _pu_zone in fp_zones:
        if (
            int(_pu_zone.fk_fp) == int(fp.pk)
            and _pu_zone.state == booking.pu_Address_State
            and int(_pu_zone.postal_code) == int(booking.pu_Address_PostalCode)
            and _pu_zone.suburb == booking.pu_Address_Suburb.upper()
        ):
            pu_zone = _pu_zone
            break

    for _de_zone in fp_zones:
        if (
            int(_de_zone.fk_fp) == int(fp.pk)
            and _de_zone.state == booking.de_To_Address_State
            and int(_de_zone.postal_code) == int(booking.de_To_Address_PostalCode)
            and _de_zone.suburb == booking.de_To_Address_Suburb.upper()
        ):
            de_zone = _de_zone
            break

    logger.info(f"@831 {LOG_ID} PU Zone: {pu_zone.zone} DE Zone: {de_zone.zone}")

    if not pu_zone:
        message = f"@833 {LOG_ID} PU address is not supported."
        logger.info(message)
        raise Exception(message)

    if not de_zone:
        message = f"@833 {LOG_ID} DE address is not supported."
        logger.info(message)
        raise Exception(message)

    rules = []
    for rule in fp_rules:
        if (
            rule.freight_provider_id == fp.id
            and rule.service_type.lower() == service_type.lower()
            and rule.pu_zone == pu_zone.zone
            and rule.de_zone == de_zone.zone
        ):
            rules.append(rule)

    if not rules:
        message = f"@834 {LOG_ID} Does not found matching Rule."
        logger.info(message)
        raise Exception(message)

    cost = rules[0].cost
    message = f"@835 {LOG_ID} RuleID: {rules[0]} CostID: {cost}"
    logger.info(message)

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

    if service_type == "Road Express":
        net_price = cost.basic_charge
        net_price += float(cost.per_UOM_charge) * math.ceil(chargable_weight)
        logger.info(
            f"{LOG_ID} cost: #{cost}({cost.basic_charge, cost.per_UOM_charge}), chargable_weight: {chargable_weight}"
        )

        if net_price < cost.min_charge:
            net_price = cost.min_charge
    else:
        net_price = 0

        for item in booking_lines:
            net_price += float(cost.per_UOM_charge) * item.e_qty

    price = {
        "netPrice": net_price,
        "totalTaxes": 0,
        "serviceName": service_type,
        "etd": _get_etd(
            pu_postal_code=booking.pu_Address_PostalCode,
            de_zone=de_zone,
        ),
        "account_code": "DME",
    }

    message = f"@836 {LOG_ID} result: {price}"
    logger.info(message)
    return [price]
