import logging
from datetime import datetime

from django.conf import settings
from django.db.models import Sum

from api.models import *
from api.common import ratio
from api.common.booking_quote import set_booking_quote
from api.fp_apis.constants import FP_CREDENTIALS, FP_UOM, SPECIAL_FPS
from api.operations.email_senders import send_email_to_admins
from api.helpers.etd import get_etd
from api.fps.startrack import gen_consignment as gen_consignment_num_st
from api.fps.direct_freight import gen_consignment as gen_consignment_num_df
from api.fps.team_global_express import gen_consignment as gen_consignment_num_tge

logger = logging.getLogger(__name__)


def _convert_UOM(value, uom, type, fp_name):
    _fp_name = fp_name.lower()

    try:
        converted_value = value * ratio.get_ratio(uom, FP_UOM[_fp_name][type], type)
        return round(converted_value, 2)
    except Exception as e:
        message = f"#408 Error - FP: {_fp_name}, value: {value}, uom: {uom}, type: {type}, standard_uom: {FP_UOM[_fp_name][type]}, error: {str(e)}"
        logger.info(message)
        raise Exception(message)


def gen_consignment_num(fp_name, uid, kf_client_id=None, booking=None):
    """
    generate consignment

    uid: can be `booking_visual_id` or `b_client_order_num`
    """

    _fp_name = fp_name.lower()

    if _fp_name in ["tnt"]:
        return f"DME{str(uid).zfill(9)}"
    # elif _fp_name == "hunter":
    #     digit_len = 6
    #     limiter = "1"

    #     for i in range(digit_len):
    #         limiter += "0"

    #     limiter = int(limiter)

    #     prefix_index = int(int(uid) / limiter) + 1
    #     prefix = chr(int((prefix_index - 1) / 26) + 65) + chr(
    #         ((prefix_index - 1) % 26) + 65
    #     )

    #     return prefix + str(uid)[-digit_len:].zfill(digit_len)
    # elif _fp_name == "century": # Deactivated
    #     return f"D_jasonl_{str(uid)}"
    elif (
        kf_client_id == "461162D2-90C7-BF4E-A905-000000000004" and _fp_name == "hunter"
    ):
        return f"PLX{str(uid)}"
    elif _fp_name == "startrack":
        return gen_consignment_num_st(booking)
    elif _fp_name == "direct freight":
        return gen_consignment_num_df(booking)
    elif _fp_name == "team global express":
        return gen_consignment_num_tge(booking)
    elif _fp_name == "camerons":
        return f"DME{str(uid).zfill(7)}"
    else:
        return f"DME{str(uid)}"


def get_m3_to_kg_factor(fp_name, data=None):
    if not fp_name:
        return 250
    if fp_name.lower() in ["northline", "sadleirs", "deliver-me direct"]:
        return 333
    elif (
        fp_name.lower() == "hunter"
        and (data and not data["is_pallet"])
        and (
            (data["item_length"] > 1.2 and data["item_width"] > 1.2)
            or (data["item_height"] > 1.8)
            or (
                max(data["item_length"], data["item_width"]) > 1.2
                and data["item_dead_weight"] > 59
            )
        )
    ):
        return 333

    return 250


def get_dme_status_from_fp_status(fp_name, b_status_API, booking=None):
    try:
        rules = Dme_utl_fp_statuses.objects.filter(fp_name__iexact=fp_name)

        def get_dme_status(fp_status):
            dme_status = None
            for rule in rules:
                if fp_name.lower() == "allied":
                    if "XXX" in rule.fp_lookup_status:
                        fp_lookup_status = rule.fp_lookup_status.replace("XXX", "")
                        if fp_lookup_status in fp_status:
                            dme_status = rule.dme_status
                    elif rule.fp_lookup_status == fp_status:
                        dme_status = rule.dme_status
                else:
                    if rule.fp_lookup_status == fp_status:
                        dme_status = rule.dme_status
            return dme_status

        if isinstance(b_status_API, str):
            return get_dme_status(b_status_API)
        else:
            status_info = []
            for fp_status in b_status_API:
                status_info.append(get_dme_status(fp_status))
            return status_info
    except:
        return None


def get_status_category_from_status(status):
    if not status:
        return None

    try:
        utl_dme_status = Utl_dme_status.objects.get(dme_delivery_status=status)
        return utl_dme_status.dme_delivery_status_category
    except Exception as e:
        message = f"#819 Category not found with this status: {status}"
        logger.error(message)
        if "rebooked" not in status.lower():
            send_email_to_admins("Category for Status not Found", message)
        return None


def get_status_time_from_category(booking_id, category):
    from api.common.time import convert_to_AU_SYDNEY_tz

    if not category:
        return None

    try:
        statuses = Utl_dme_status.objects.filter(
            dme_delivery_status_category=category
        ).values_list("dme_delivery_status", flat=True)
        status_times = (
            Dme_status_history.objects.filter(
                fk_booking_id=booking_id, status_last__in=statuses
            )
            .order_by("event_time_stamp")
            .values_list("event_time_stamp", flat=True)
        )

        return convert_to_AU_SYDNEY_tz(status_times[0]) if status_times else None
    except Exception as e:
        message = f"#819 Timestamp not found with this category: {category}"
        logger.error(message)
        send_email_to_admins("Timestamp for Category not Found", message)
        return None


# Get ETD of Pricing in `hours` unit
def get_etd_in_hour(pricing):
    try:
        # logger.info(f"[GET_ETD_IN_HOUR] {pricing.etd}")
        etd, unit = get_etd(pricing.etd)

        if unit == "Days":
            etd *= 24

        return etd
    except:
        try:
            fp = Fp_freight_providers.objects.get(
                fp_company_name__iexact=pricing.freight_provider
            )
            etd = FP_Service_ETDs.objects.get(
                freight_provider_id=fp.id,
                fp_delivery_time_description=pricing.etd,
                fp_delivery_service_code=pricing.service_name,
            )

            return etd.fp_03_delivery_hours
        except Exception as e:
            message = f"#810 [get_etd_in_hour] Missing ETD - {pricing.freight_provider}, {pricing.service_name}, {pricing.etd}"
            logger.info(message)
            # raise Exception(message)
            return None


def _is_deliverable_price(pricing, booking):
    if booking.pu_PickUp_By_Date and booking.de_Deliver_By_Date:
        timeDelta = booking.de_Deliver_By_Date - booking.puPickUpAvailFrom_Date
        delta_min = 0

        if booking.de_Deliver_By_Hours:
            delta_min += booking.de_Deliver_By_Hours * 60
        if booking.de_Deliver_By_Minutes:
            delta_min += booking.de_Deliver_By_Minutes
        if booking.pu_PickUp_By_Time_Hours:
            delta_min -= booking.pu_PickUp_By_Time_Hours * 60
        if booking.pu_PickUp_By_Time_Minutes:
            delta_min -= booking.pu_PickUp_By_Time_Minutes

        delta_min = timeDelta.total_seconds() / 60 + delta_min
        etd = get_etd_in_hour(pricing)

        if not etd:
            return False
        elif delta_min > etd * 60:
            return True
    else:
        return True


# ######################## #
#       Fastest ($$$)      #
# ######################## #
def _get_fastest_price(pricings):
    fastest_pricing = {}
    for pricing in pricings:
        if (
            pricing.freight_provider in SPECIAL_FPS
            or pricing.freight_provider == "MRL Sampson"
        ):
            continue

        etd = get_etd_in_hour(pricing)
        if not fastest_pricing:
            fastest_pricing["pricing"] = pricing
            fastest_pricing["etd_in_hour"] = etd
        elif etd and fastest_pricing and fastest_pricing["etd_in_hour"]:
            if fastest_pricing["etd_in_hour"] > etd:
                fastest_pricing["pricing"] = pricing
                fastest_pricing["etd_in_hour"] = etd
            elif (
                etd
                and fastest_pricing["etd_in_hour"]
                and fastest_pricing["etd_in_hour"] == etd
                and fastest_pricing["pricing"].client_mu_1_minimum_values
                < pricing.client_mu_1_minimum_values
            ):
                fastest_pricing["pricing"] = pricing

    return fastest_pricing.get("pricing")


# ######################## #
#        Lowest ($$$)      #
# ######################## #
def _get_lowest_price(pricings, client=None):
    lowest_pricing = {}

    # JasonL && BSD
    if client and client.dme_account_num in [
        "1af6bcd2-6148-11eb-ae93-0242ac130002",
        "9e72da0f-77c3-4355-a5ce-70611ffd0bc8",
    ]:
        for pricing in pricings:
            if pricing.freight_provider == "Deliver-ME":
                return pricing

    for pricing in pricings:
        if (
            pricing.freight_provider in SPECIAL_FPS
            or pricing.freight_provider == "MRL Sampson"
        ):
            continue

        if not lowest_pricing and pricing.client_mu_1_minimum_values:
            lowest_pricing["pricing"] = pricing
            lowest_pricing["etd"] = get_etd_in_hour(pricing)
        elif lowest_pricing and pricing.client_mu_1_minimum_values:
            if float(lowest_pricing["pricing"].client_mu_1_minimum_values) > float(
                pricing.client_mu_1_minimum_values
            ):
                lowest_pricing["pricing"] = pricing
                lowest_pricing["etd"] = get_etd_in_hour(pricing)
            elif float(lowest_pricing["pricing"].client_mu_1_minimum_values) == float(
                pricing.client_mu_1_minimum_values
            ):
                etd = get_etd_in_hour(pricing)

                if lowest_pricing["etd"] and etd and lowest_pricing["etd"] > etd:
                    lowest_pricing["pricing"] = pricing
                    lowest_pricing["etd"] = pricing

    return lowest_pricing.get("pricing")


def select_best_options(pricings, client=None, original_lines_count=None):
    LOG_ID = "[SELECT BEST OPTION]"
    logger.info(f"{LOG_ID} From {len(pricings)} pricings: {pricings}")

    if not pricings:
        return []

    # JasonL
    _quotes = pricings
    if (
        original_lines_count
        and client
        and client.dme_account_num == "1af6bcd2-6148-11eb-ae93-0242ac130002"
    ):
        send_as_is_quotes = []
        auto_pack_quotes = []
        for pricing in pricings:
            if pricing.packed_status == BOK_2_lines.ORIGINAL:
                send_as_is_quotes.append(pricing)
            if pricing.packed_status == BOK_2_lines.AUTO_PACK:
                auto_pack_quotes.append(pricing)

        logger.info(
            f"{LOG_ID} Lines count: {original_lines_count}, Original quotes: {send_as_is_quotes}, Auto Quotes: {auto_pack_quotes}"
        )
        if original_lines_count < 3:
            _quotes = send_as_is_quotes
        else:
            _quotes = auto_pack_quotes

    lowest_pricing = _get_lowest_price(_quotes, client)
    fastest_pricing = _get_fastest_price(_quotes)

    if lowest_pricing or fastest_pricing:
        if lowest_pricing and fastest_pricing:
            if lowest_pricing.pk == fastest_pricing.pk:
                return [lowest_pricing]
            else:
                return [lowest_pricing, fastest_pricing]
        else:
            return [lowest_pricing or fastest_pricing]
    else:
        return []


def auto_select_pricing(booking, pricings, auto_select_type, client=None):
    if len(pricings) == 0:
        booking.b_errorCapture = "No Freight Provider is available"
        booking.save()
        return None

    filtered_pricings = []

    # filter SCANNED pricings
    pricings_4_scanned = []
    for pricing in pricings:
        if pricing.packed_status == "scanned":
            pricings_4_scanned.append(pricing)
    filtered_pricings = pricings_4_scanned or pricings

    # filter Non AIR pricings and `MRL Sampson` pricings
    non_air_freight_pricings = []
    for pricing in filtered_pricings:
        if (
            not pricing.service_name
            or (pricing.service_name and pricing.service_name != "Air Freight")
            or pricing.freight_provider == "MRL Sampson"
        ):
            non_air_freight_pricings.append(pricing)
    filtered_pricings = non_air_freight_pricings or filtered_pricings

    # Check booking.pu_PickUp_By_Date and booking.de_Deliver_By_Date and Pricings etd
    deliverable_pricings = []
    for pricing in filtered_pricings:
        if _is_deliverable_price(pricing, booking):
            deliverable_pricings.append(pricing)
    filtered_pricings = deliverable_pricings or filtered_pricings

    filtered_pricing = {}
    if filtered_pricings:
        if int(auto_select_type) == 1:  # Lowest
            filtered_pricing = _get_lowest_price(filtered_pricings, client)
        else:  # Fastest
            filtered_pricing = _get_fastest_price(filtered_pricings)

    if filtered_pricing:
        logger.info(f"#854 Filtered Pricing - {filtered_pricing}")
        set_booking_quote(booking, filtered_pricing)
        return True
    else:
        logger.info("#855 - Could not find proper pricing")
        return False


def auto_select_pricing_4_bok(
    bok_1, pricings, is_from_script=False, auto_select_type=1, client=None
):
    LOG_ID = "AUTO SELECT"
    if len(pricings) == 0:
        logger.info("#855 - Could not find proper pricing")
        return None

    # JasonL
    _quotes = pricings
    if bok_1.fk_client_id == "1af6bcd2-6148-11eb-ae93-0242ac130002":
        bok_2_lines_cnt = (
            bok_1.bok_2s()
            .filter(b_093_packed_status=BOK_2_lines.ORIGINAL, is_deleted=False)
            .aggregate(Sum("l_002_qty"))
        )["l_002_qty__sum"]
        send_as_is_quotes = _quotes.filter(packed_status=BOK_2_lines.ORIGINAL)
        auto_pack_quotes = _quotes.filter(packed_status=BOK_2_lines.AUTO_PACK)

        logger.info(f"{LOG_ID} Lines count: {bok_2_lines_cnt}")
        if bok_2_lines_cnt < 3:
            _quotes = send_as_is_quotes
        else:
            _quotes = auto_pack_quotes

    non_air_freight_pricings = []
    for pricing in _quotes:
        if (
            not pricing.service_name
            or (pricing.service_name and pricing.service_name != "Air Freight")
            or pricing.freight_provider == "MRL Sampson"
        ):
            non_air_freight_pricings.append(pricing)

    # Check booking.pu_PickUp_By_Date and booking.de_Deliver_By_Date and Pricings etd
    # deliverable_pricings = []
    # for pricing in non_air_freight_pricings:
    #     if _is_deliverable_price(pricing, booking):
    #         deliverable_pricings.append(pricing)

    deliverable_pricings = non_air_freight_pricings
    filtered_pricing = None

    if is_from_script and bok_1.quote and bok_1.quote.freight_provider in SPECIAL_FPS:
        for pricing in non_air_freight_pricings:
            if pricing.freight_provider == bok_1.quote.freight_provider:
                filtered_pricing = pricing
                break
    else:
        if int(auto_select_type) == 1:  # Lowest
            logger.info(f"{LOG_ID} LOWEST")
            if deliverable_pricings:
                filtered_pricing = _get_lowest_price(deliverable_pricings, client)
            elif non_air_freight_pricings:
                filtered_pricing = _get_lowest_price(non_air_freight_pricings, client)
        else:  # Fastest
            logger.info(f"{LOG_ID} FASTEST")
            if deliverable_pricings:
                filtered_pricing = _get_fastest_price(deliverable_pricings)
            elif non_air_freight_pricings:
                filtered_pricing = _get_fastest_price(non_air_freight_pricings)

    if filtered_pricing:
        logger.info(f"{LOG_ID} Filtered Pricing - {filtered_pricing}")
        bok_1.quote = filtered_pricing
        bok_1.save()
        return True
    else:
        logger.info(f"{LOG_ID} Could not find proper pricing")
        return False
