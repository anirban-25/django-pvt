import json
import copy
import time as t
import random
import logging
import requests
import threading
from datetime import datetime

from django.conf import settings
from django.db import connection
from django.core.cache import cache
from django.db.models import Q

from api.common import trace_error
from api.common.build_object import Struct
from api.common.convert_price import interpolate_gaps, apply_markups
from api.common.constants import PALLETS, SKIDS
from api.serializers import ApiBookingQuotesSerializer
from api.fp_apis.operations.common import _set_error
from api.fp_apis.operations.surcharge.index import gen_surcharges
from api.operations.redis.pricing import save_2_redis, read_from_redis
from api.fp_apis.built_in.index import get_pricing as get_self_pricing
from api.fp_apis.response_parser import parse_pricing_response
from api.fp_apis.payload_builder import get_pricing_payload
from api.fp_apis.constants import (
    S3_URL,
    SPECIAL_FPS,
    PRICING_TIME,
    FP_CREDENTIALS,
    BUILT_IN_PRICINGS,
    DME_LEVEL_API_URL,
    AVAILABLE_FPS_4_FC,
    HEADER_FOR_NODE,
)
from api.clients.jason_l.operations import get_total_sales, get_value_by_formula
from api.fp_apis.built_in.mrl_sampson import (
    can_use as can_use_mrl_sampson,
    get_value_by_formula as get_price_of_mrl_sampson,
    get_etd_by_formula,
)
from api.fp_apis.utils import _convert_UOM
from api.fp_apis.built_in.deliver_me import can_use_linehaul
from api.clients.anchor_packaging.constants import AP_FREIGHTS
from api.models import (
    Bookings,
    Booking_lines,
    Log,
    API_booking_quotes,
    Client_FP,
    FP_Service_ETDs,
    Surcharge,
    DME_clients,
    Fp_freight_providers,
    FP_zones,
    FP_vehicles,
    FP_pricing_rules,
)

logger = logging.getLogger(__name__)


def _lower_dme_price(quotes):
    LOG_ID = "[LOWER DME PRICE]"
    original_dme_quotes = []
    auto_dme_quotes = []
    mannual_dme_quotes = []
    scanned_dme_quotes = []

    original_ap_quotes = []
    auto_ap_quotes = []
    mannual_ap_quotes = []
    scanned_ap_quotes = []

    # Put in each bucket
    for quote in quotes:
        if quote.freight_provider in SPECIAL_FPS:
            continue

        if quote.packed_status == Booking_lines.ORIGINAL:
            if quote.freight_provider in AP_FREIGHTS:
                original_ap_quotes.append(quote)
            else:
                original_dme_quotes.append(quote)

        if quote.packed_status == Booking_lines.AUTO_PACK:
            if quote.freight_provider in AP_FREIGHTS:
                auto_ap_quotes.append(quote)
            else:
                auto_dme_quotes.append(quote)

        if quote.packed_status == Booking_lines.MANUAL_PACK:
            if quote.freight_provider in AP_FREIGHTS:
                mannual_ap_quotes.append(quote)
            else:
                mannual_dme_quotes.append(quote)

        if quote.packed_status == Booking_lines.SCANNED_PACK:
            if quote.freight_provider in AP_FREIGHTS:
                scanned_ap_quotes.append(quote)
            else:
                scanned_dme_quotes.append(quote)

    # Original
    if original_dme_quotes and original_ap_quotes:
        lowest_dme_quote = original_dme_quotes[0]
        lowest_ap_quote = original_ap_quotes[0]
        lowerPercent = random.randrange(9300, 9500) / 10000

        for quote in original_dme_quotes:
            price = quote.client_mu_1_minimum_values
            if price < lowest_dme_quote.client_mu_1_minimum_values:
                lowest_dme_quote = quote

        for quote in original_ap_quotes:
            price = quote.client_mu_1_minimum_values
            if price < lowest_ap_quote.client_mu_1_minimum_values:
                lowest_ap_quote = quote

        price = lowest_ap_quote.client_mu_1_minimum_values
        if price < lowest_dme_quote.client_mu_1_minimum_values:
            price = lowest_ap_quote.client_mu_1_minimum_values
            old_dme_price = lowest_dme_quote.client_mu_1_minimum_values
            new_dme_price = price * lowerPercent
            ratio = new_dme_price / old_dme_price
            lowest_dme_quote.fee *= ratio
            lowest_dme_quote.fuel_levy_base *= ratio
            lowest_dme_quote.client_mu_1_minimum_values *= ratio

            if lowest_dme_quote.x_price_surcharge:
                lowest_dme_quote.x_price_surcharge *= ratio

            lowest_dme_quote.save()
            logger.info(f"@171 {LOG_ID} Original {lowest_dme_quote}")

    # Auto
    if auto_dme_quotes and auto_ap_quotes:
        lowest_dme_quote = auto_dme_quotes[0]
        lowest_ap_quote = auto_ap_quotes[0]
        lowerPercent = random.randrange(9300, 9500) / 10000

        for quote in auto_dme_quotes:
            price = quote.client_mu_1_minimum_values
            if price < lowest_dme_quote.client_mu_1_minimum_values:
                lowest_dme_quote = quote

        for quote in auto_ap_quotes:
            price = quote.client_mu_1_minimum_values
            if price < lowest_ap_quote.client_mu_1_minimum_values:
                lowest_ap_quote = quote

        price = lowest_ap_quote.client_mu_1_minimum_values
        if price < lowest_dme_quote.client_mu_1_minimum_values:
            price = lowest_ap_quote.client_mu_1_minimum_values
            old_dme_price = lowest_dme_quote.client_mu_1_minimum_values
            new_dme_price = price * lowerPercent
            ratio = new_dme_price / old_dme_price
            lowest_dme_quote.fee *= ratio
            lowest_dme_quote.fuel_levy_base *= ratio
            lowest_dme_quote.client_mu_1_minimum_values *= ratio

            if lowest_dme_quote.x_price_surcharge:
                lowest_dme_quote.x_price_surcharge *= ratio

            lowest_dme_quote.save()
            logger.info(f"@172 {LOG_ID} Auto {lowest_dme_quote}")

    # Manual
    if mannual_dme_quotes and mannual_ap_quotes:
        lowest_dme_quote = mannual_dme_quotes[0]
        lowest_ap_quote = mannual_ap_quotes[0]
        lowerPercent = random.randrange(9300, 9500) / 10000

        for quote in mannual_dme_quotes:
            price = quote.client_mu_1_minimum_values
            if price < lowest_dme_quote.client_mu_1_minimum_values:
                lowest_dme_quote = quote

        for quote in mannual_ap_quotes:
            price = quote.client_mu_1_minimum_values
            if price < lowest_ap_quote.client_mu_1_minimum_values:
                lowest_ap_quote = quote

        price = lowest_ap_quote.client_mu_1_minimum_values
        if price < lowest_dme_quote.client_mu_1_minimum_values:
            price = lowest_ap_quote.client_mu_1_minimum_values
            old_dme_price = lowest_dme_quote.client_mu_1_minimum_values
            new_dme_price = price * lowerPercent
            ratio = new_dme_price / old_dme_price
            lowest_dme_quote.fee *= ratio
            lowest_dme_quote.fuel_levy_base *= ratio
            lowest_dme_quote.client_mu_1_minimum_values *= ratio

            if lowest_dme_quote.x_price_surcharge:
                lowest_dme_quote.x_price_surcharge *= ratio

            lowest_dme_quote.save()
            logger.info(f"@173 {LOG_ID} Auto {lowest_dme_quote}")

    # Scanned
    if scanned_dme_quotes and scanned_ap_quotes:
        lowest_dme_quote = scanned_dme_quotes[0]
        lowest_ap_quote = scanned_ap_quotes[0]
        lowerPercent = random.randrange(9300, 9500) / 10000

        for quote in scanned_dme_quotes:
            price = quote.client_mu_1_minimum_values
            if price < lowest_dme_quote.client_mu_1_minimum_values:
                lowest_dme_quote = quote

        for quote in scanned_ap_quotes:
            price = quote.client_mu_1_minimum_values
            if price < lowest_ap_quote.client_mu_1_minimum_values:
                lowest_ap_quote = quote

        price = lowest_ap_quote.client_mu_1_minimum_values
        if price < lowest_dme_quote.client_mu_1_minimum_values:
            price = lowest_ap_quote.client_mu_1_minimum_values
            old_dme_price = lowest_dme_quote.client_mu_1_minimum_values
            new_dme_price = price * lowerPercent
            ratio = new_dme_price / old_dme_price
            lowest_dme_quote.fee *= ratio
            lowest_dme_quote.fuel_levy_base *= ratio
            lowest_dme_quote.client_mu_1_minimum_values *= ratio

            if lowest_dme_quote.x_price_surcharge:
                lowest_dme_quote.x_price_surcharge *= ratio

            lowest_dme_quote.save()
            logger.info(f"@174 {LOG_ID} Auto {lowest_dme_quote}")


def _confirm_visible(booking, booking_lines, quotes):
    """
    `Allied` - if DE address_type is `residential` and 2+ Line dim is over 1.2m, then hide it
    """
    _quotes = []
    is_visible = True
    for quote in quotes:
        if (
            quote.freight_provider == "Allied"
            and booking.pu_Address_Type == "residential"
        ):
            for line in booking_lines:
                width = _convert_UOM(
                    line.e_dimWidth,
                    line.e_dimUOM,
                    "dim",
                    quote.freight_provider.lower(),
                )
                height = _convert_UOM(
                    line.e_dimHeight,
                    line.e_dimUOM,
                    "dim",
                    quote.freight_provider.lower(),
                )
                length = _convert_UOM(
                    line.e_dimLength,
                    line.e_dimUOM,
                    "dim",
                    quote.freight_provider.lower(),
                )

                if (
                    (width > 120 and height > 120)
                    or (width > 120 and length > 120)
                    or (height > 120 and length > 120)
                ):
                    quote.is_used = True
                    quote.save()
                    is_visible = False

        # JasonL + SA -> ignore Allied
        if (
            booking.kf_client_id == "1af6bcd2-6148-11eb-ae93-0242ac130002"
            and booking.de_To_Address_State.upper() == "SA"
            and quote.freight_provider == "Allied"
        ):
            quote.is_used = True
            quote.save()
            is_visible = False

        if is_visible:
            _quotes.append(quote)

    return _quotes


def build_special_fp_pricings(
    pricing_id,
    booking,
    booking_lines,
    packed_status,
    client,
    fps,
):
    # # Get manually entered surcharges total
    # try:
    #     manual_surcharges_total = booking.get_manual_surcharges_total()
    # except:
    #     manual_surcharges_total = 0

    # Build default quote object
    default_quote = {
        "api_results_id": f"special-pricing-{str(random.randrange(0, 100000)).zfill(6)}",
        "account_code": None,
        "fk_booking_id": booking.pk_booking_id,
        "fk_client_id": booking.b_client_name,
        "service_name": None,
        "service_code": None,
        "vehicle": None,
        "fee": 0,
        "etd": 3,
        "tax_value_1": 0,
        "packed_status": packed_status,
        "x_price_surcharge": 0,
        "mu_percentage_fuel_levy": 0,
        "client_mu_1_minimum_values": 0,
        "is_from_api": False,
    }
    de_postal_code = int(booking.de_To_Address_PostalCode or 0)

    # Find each FP
    in_house_fleet_fp = None
    deliver_me_fp = None
    customer_collect_fp = None
    mrl_sampson_fp = None
    for fp in fps:
        if fp.fp_company_name == "In House Fleet":
            in_house_fleet_fp = fp
        if fp.fp_company_name == "Deliver-ME":
            deliver_me_fp = fp
        if fp.fp_company_name == "Customer Collect":
            customer_collect_fp = fp
        if fp.fp_company_name == "MRL Sampson":
            mrl_sampson_fp = fp

    # JasonL (SYD - SYD)
    if (
        in_house_fleet_fp
        and booking.kf_client_id == "1af6bcd2-6148-11eb-ae93-0242ac130002"
        and (
            (de_postal_code >= 1000 and de_postal_code <= 2249)
            or (de_postal_code >= 2760 and de_postal_code <= 2770)
        )
    ):
        quote = copy.deepcopy(default_quote)
        quote["freight_provider"] = "In House Fleet"
        value_by_formula = get_value_by_formula(booking_lines)
        logger.info(f"[In House Fleet] value_by_formula: {value_by_formula}")
        quote["client_mu_1_minimum_values"] = value_by_formula
        save_2_redis(pricing_id, quote, booking, client, in_house_fleet_fp)

    # JasonL & BSD & Anchor Packaging
    if deliver_me_fp and (
        booking.kf_client_id == "1af6bcd2-6148-11eb-ae93-0242ac130002"
        or booking.kf_client_id == "9e72da0f-77c3-4355-a5ce-70611ffd0bc8"
        or booking.kf_client_id == "49294ca3-2adb-4a6e-9c55-9b56c0361953"
    ):
        if can_use_linehaul(booking, booking_lines):
            quote = copy.deepcopy(default_quote)
            quote["freight_provider"] = "Deliver-ME"
            result = get_self_pricing(
                quote["freight_provider"],
                booking,
                client,
                deliver_me_fp,
                [],
                [],
                [],
                booking_lines,
            )
            quote["fee"] = result["price"]["inv_cost_quoted"]
            quote["mu_percentage_fuel_levy"] = 0.25
            quote["fuel_levy_base"] = float(quote["fee"]) * 0.25
            quote["client_mu_1_minimum_values"] = result["price"]["inv_sell_quoted"]
            quote["tax_value_5"] = result["price"]["inv_dme_quoted"]
            quote["service_name"] = result["price"]["service_name"]
            save_2_redis(pricing_id, quote, booking, client, deliver_me_fp)

    # Plum & JasonL & BSD & Cadrys & Ariston Wire & Anchor Packaging & Pricing Only
    if customer_collect_fp and (
        booking.kf_client_id == "461162D2-90C7-BF4E-A905-000000000004"
        or booking.kf_client_id == "1af6bcd2-6148-11eb-ae93-0242ac130002"
        or booking.kf_client_id == "9e72da0f-77c3-4355-a5ce-70611ffd0bc8"
        or booking.kf_client_id == "f821586a-d476-434d-a30b-839a04e10115"
        or booking.kf_client_id == "15732b05-d597-419b-8dc5-90e633d9a7e9"
        or booking.kf_client_id == "49294ca3-2adb-4a6e-9c55-9b56c0361953"
        or booking.kf_client_id == "461162D2-90C7-BF4E-A905-0242ac130003"
    ):
        quote = copy.deepcopy(default_quote)
        quote["fee"] = 0
        quote["client_mu_1_minimum_values"] = 0
        quote["service_name"] = None
        quote["freight_provider"] = "Customer Collect"
        quote["tax_value_5"] = None
        save_2_redis(pricing_id, quote, booking, client, customer_collect_fp)

    # Plum & JasonL & BSD
    if mrl_sampson_fp and (
        booking.kf_client_id == "461162D2-90C7-BF4E-A905-000000000004"
        or booking.kf_client_id == "1af6bcd2-6148-11eb-ae93-0242ac130002"
        or booking.kf_client_id == "9e72da0f-77c3-4355-a5ce-70611ffd0bc8"
    ):
        if can_use_mrl_sampson(booking):
            quote = copy.deepcopy(default_quote)
            quote["freight_provider"] = "MRL Sampson"
            quote["service_name"] = None
            value_by_formula = get_price_of_mrl_sampson(booking, booking_lines)
            logger.info(f"[MRL Sampson] value_by_formula: {value_by_formula}")
            quote["fee"] = value_by_formula
            quote["etd"] = get_etd_by_formula(booking)
            save_2_redis(pricing_id, quote, booking, client, mrl_sampson_fp)


def pricing(
    body, booking_id, is_pricing_only=False, packed_statuses=[Booking_lines.ORIGINAL]
):
    """
    @params:
        * is_pricing_only: only get pricing info
        * packed_statuses: array of options (ORIGINAL, AUTO_PACKED, MANUAL_PACKED, SCANNED_PACKED)
    """
    LOG_ID = "[PRICING]"
    booking_lines = []
    booking = None
    client = None
    time1, time2 = None, None
    pricing_id = f"P-{str(random.randrange(0, 100000)).zfill(6)}"
    logger.info(f"{LOG_ID} {booking_id} {packed_statuses} Pricing ID: {pricing_id}")

    ##########################
    #   Prepare Data Start   #
    ##########################
    time1 = t.time()
    logger.info(f"Check point #1 DB hits: {len(connection.queries)}")

    # Only quote mode
    if is_pricing_only and not booking_id:
        booking = Struct(**body["booking"])

        for booking_line in body["booking_lines"]:
            booking_lines.append(Struct(**booking_line))
    elif not is_pricing_only:
        booking = Bookings.objects.filter(id=booking_id).order_by("id").first()

        if not booking:
            return None, False, "Booking does not exist", None, client

        pk_booking_id = booking.pk_booking_id
        booking_lines = Booking_lines.objects.filter(
            fk_booking_id=booking.pk_booking_id, is_deleted=False
        )

    # Set is_used flag for existing old pricings (except Customer FP Quotes)
    if booking.pk_booking_id:
        API_booking_quotes.objects.filter(
            fk_booking_id=booking.pk_booking_id,
            is_used=False,
            packed_status__in=packed_statuses,
            provider__isnull=True,
        ).update(is_used=True)

    try:
        # Client
        client = DME_clients.objects.get(company_name__iexact=booking.b_client_name)
        # Client & FP
        client_fps = Client_FP.objects.prefetch_related("fp")
        client_fps = client_fps.filter(client=client, is_active=True)
        # FP
        fps = [client_fp.fp for client_fp in client_fps]
        # Zones
        pu_postal_code = booking.pu_Address_PostalCode.zfill(4)
        de_postal_code = booking.de_To_Address_PostalCode.zfill(4)
        or_filters = Q()
        or_filters.connector = Q.OR
        for fp in fps:
            or_filters.add(Q(fk_fp=fp.id), Q.OR)
        zones = FP_zones.objects.filter(or_filters)
        zones = zones.filter(
            Q(postal_code__in=[pu_postal_code, de_postal_code]) |
            Q(fk_fp=115)
        )  # Include Deliver-Me Direct zones

        # Prepare zones for each FP
        fp_zones = {}
        for zone in zones:
            key = str(zone.fk_fp)
            if not fp_zones.get(key):
                fp_zones[key] = [zone]
            else:
                fp_zones[key].append(zone)

        # Vehicles
        or_filters = Q()
        or_filters.connector = Q.OR
        for fp in fps:
            or_filters.add(Q(freight_provider_id=fp.id), Q.OR)
        vehicles = FP_vehicles.objects.filter(or_filters)

        # Prepare zones for each FP
        fp_vehicles = {}
        for vehicle in vehicles:
            key = str(vehicle.freight_provider_id)
            if not fp_vehicles.get(key):
                fp_vehicles[key] = [vehicle]
            else:
                fp_vehicles[key].append(vehicle)

        # Prepare fp names
        fp_names = [fp.fp_company_name.lower() for fp in fps]

        # Services
        fp_services = []
        if "auspost" in fp_names:
            fp_services = FP_Service_ETDs.objects.filter(
                freight_provider__fp_company_name="AUSPost"
            ).only("fp_delivery_time_description", "fp_delivery_service_code")

        # Rules
        zone_rules, vehicle_rules = [], []
        zone_codes = [zone.zone for zone in zones]
        zone_codes = set(zone_codes)
        rules = FP_pricing_rules.objects.prefetch_related("cost")
        rules = rules.filter(or_filters)
        rules = rules.order_by("id")

        if vehicles:
            vehicle_rules = rules.filter(
                pu_postal_code=pu_postal_code, de_postal_code=de_postal_code
            )
        if zone_codes:
            zone_rules = rules.filter(
                Q(pu_zone__in=zone_codes) | Q(de_zone__in=zone_codes)
            )

        # Prepare zones for each FP
        fp_rules = {}
        for rule in vehicle_rules:
            key = str(rule.freight_provider_id)
            if not fp_rules.get(key):
                fp_rules[key] = [rule]
            elif not rule in fp_rules[key]:
                fp_rules[key].append(rule)

        for rule in zone_rules:
            key = str(rule.freight_provider_id)
            if not fp_rules.get(key):
                fp_rules[key] = [rule]
            elif not rule in fp_rules[key]:
                fp_rules[key].append(rule)

        time2 = t.time()
        time_delta = str(int(round(time2 - time1)))
        logger.info(
            f"Check point #2 DB hits: {len(connection.queries)} time delta: {time_delta}s"
        )
        time1 = time2
    except Exception as e:
        logger.error(f"{LOG_ID} Error while build pre-data: {e}")
        client = None
        client_fps = []
    ##########################
    #    Prepare Data End    #
    ##########################

    # Validation #1
    if not booking.puPickUpAvailFrom_Date:
        error_msg = "PU Available From Date is required."

        if not is_pricing_only:
            _set_error(booking, error_msg)

        return None, False, error_msg, None, client

    try:
        threads = []
        for packed_status in packed_statuses:
            _booking_lines = []
            for booking_line in booking_lines:
                if booking_line.packed_status != packed_status:
                    continue
                _booking_lines.append(booking_line)

            if not _booking_lines:
                continue

            time2 = t.time()
            time_delta = str(int(round(time2 - time1)))
            logger.info(
                f"Check point #3 DB hits: {len(connection.queries)} time delta: {time_delta}s"
            )
            time1 = time2

            _threads = build_threads(
                pricing_id,
                booking,
                _booking_lines,
                is_pricing_only,
                packed_status,
                client,
                fps,
                fp_names,
                client_fps,
                fp_zones,
                fp_services,
                fp_vehicles,
                fp_rules,
            )
            threads += _threads
            build_special_fp_pricings(
                pricing_id, booking, _booking_lines, packed_status, client, fps
            )

        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        # timeout=PRICING_TIME,
        # logger.info(f"#990 [PRICING] - {PRICING_TIME}s Timeout! stop threads! ;)")

        # Read from Redis & save as Quote on DB
        quotes = []
        for fp in fps:
            for packed_status in ["original", "auto", "manual", "scanned"]:
                for index in range(0, 16):
                    prefix = f"{pricing_id}:{fp.pk}:{packed_status}:{index}"
                    has_data = cache.get(prefix)
                    if not has_data:
                        continue
                    data = read_from_redis(pricing_id, fp, packed_status, index)
                    context = {"booking": booking}
                    serializer = ApiBookingQuotesSerializer(data=data, context=context)

                    if serializer.is_valid():
                        quote = serializer.save()
                        quotes.append(quote)
                    else:
                        logger.info(
                            f"@402 [PRICING] Serializer error: {serializer.errors}"
                        )

        time2 = t.time()
        time_delta = str(int(round(time2 - time1)))
        logger.info(
            f"Check point #4 DB hits: {len(connection.queries)} time delta: {time_delta}s"
        )
        time1 = time2

        # After process
        _after_process(
            booking,
            booking_lines,
            is_pricing_only,
            client,
            fps,
            client_fps,
            quotes,
        )

        time2 = t.time()
        time_delta = str(int(round(time2 - time1)))
        logger.info(
            f"Check point #5: {len(connection.queries)} time delta: {time_delta}"
        )
        time1 = time2

        # Deactivated for DEV test
        # # JasonL + SA -> ignore Allied
        # if booking.kf_client_id == "1af6bcd2-6148-11eb-ae93-0242ac130002":
        #     if booking.de_To_Address_State.upper() == "SA":
        #         API_booking_quotes.objects.filter(
        #             fk_booking_id=booking.pk_booking_id,
        #             is_used=False,
        #             freight_provider="Allied",
        #         ).update(is_used=True)

        #     try:
        #         if booking.v_customer_code != "U":
        #             API_booking_quotes.objects.filter(
        #                 fk_booking_id=booking.pk_booking_id,
        #                 is_used=False,
        #                 freight_provider__icontains="toll",
        #             ).update(is_used=True)
        #         else:
        #             hasPallet = False
        #             for line in entire_booking_lines:
        #                 if line.packed_status == "original" and (
        #                     line.e_type_of_packaging.upper() in PALLETS
        #                     or line.e_type_of_packaging.upper() in SKIDS
        #                 ):
        #                     hasPallet = True
        #                     break
        #             if not hasPallet:
        #                 API_booking_quotes.objects.filter(
        #                     fk_booking_id=booking.pk_booking_id,
        #                     is_used=False,
        #                     freight_provider="StarTrack",
        #                 ).update(is_used=True)
        #     except:
        #         pass

        # save and sort
        for quote in quotes:
            quote.save()

        time2 = t.time()
        time_delta = str(int(round(time2 - time1)))
        logger.info(
            f"Check point #6: {len(connection.queries)} time delta: {time_delta}"
        )
        time1 = time2

        return booking, True, "Retrieved all Pricing info", quotes, client
    except Exception as e:
        trace_error.print()
        logger.error(f"{LOG_ID} Booking: {booking}, Error: {e}")
        return booking, False, str(e), [], client


def _after_process(
    booking,
    booking_lines,
    is_pricing_only,
    client,
    fps,
    client_fps,
    quotes,
):
    # JasonL: update `client sales total`
    if booking.kf_client_id == "1af6bcd2-6148-11eb-ae93-0242ac130002":
        try:
            booking.client_sales_total = get_total_sales(booking.b_client_order_num)
            booking.save()
        except Exception as e:
            logger.error(f"Client sales total: {str(e)}")
            booking.client_sales_total = None
            pass

    if not quotes:
        return

    if client:
        # Interpolate gaps (for Plum client now)
        quotes = interpolate_gaps(quotes, client)

    # Calculate Surcharges
    for quote in quotes:
        _booking_lines = []
        quote_fp = None

        if quote.freight_provider in SPECIAL_FPS:  # Skip Special FPs
            continue

        for booking_line in booking_lines:
            if booking_line.packed_status == quote.packed_status:
                _booking_lines.append(booking_line)

        if not _booking_lines:
            continue

        for fp in fps:
            if quote.freight_provider.lower() == fp.fp_company_name.lower():
                quote_fp = fp
                break

        gen_surcharges(
            booking,
            _booking_lines,
            booking_lines,
            quote,
            client,
            quote_fp,
            "booking",
        )

    # Confirm visible
    quotes = _confirm_visible(booking, _booking_lines, quotes)

    # Apply Markups (FP Markup and Client Markup)
    de_addr = {
        "state": booking.de_To_Address_State,
        "postal_code": booking.de_To_Address_PostalCode,
        "suburb": booking.de_To_Address_Suburb,
    }
    quotes = apply_markups(quotes, client, fps, client_fps, de_addr, booking)

    # AP: Lower the DME price manually
    if booking.kf_client_id in ["49294ca3-2adb-4a6e-9c55-9b56c0361953"]:
        # _lower_dme_price(quotes)
        pass


def build_threads(
    pricing_id,
    booking,
    booking_lines,
    is_pricing_only,
    packed_status,
    client,
    fps,
    fp_names,
    client_fps,
    fp_zones,
    fp_services,
    fp_vehicles,
    fp_rules,
):
    # Schedule n pricing works *concurrently*:
    threads = []
    logger.info(
        f"#910 [PRICING] - Building Pricing threads for [{packed_status.upper()}]"
    )

    for fp_name in AVAILABLE_FPS_4_FC:
        _fp_name = fp_name.lower()
        fp = None

        for _fp in fps:
            if _fp.fp_company_name.lower() == _fp_name:
                fp = _fp

        try:
            if (
                booking.b_dateBookedDate
                and booking.vx_freight_provider.lower() != _fp_name
                and booking.vx_freight_provider not in SPECIAL_FPS
            ):
                continue
        except:
            pass

        # If not allowed for this Client
        if _fp_name not in fp_names:
            continue

        # If no credential
        if _fp_name not in FP_CREDENTIALS and _fp_name not in BUILT_IN_PRICINGS:
            continue

        if _fp_name == "auspost":
            logger.info(f"#904 [PRICING] services: {fp_services}")

        if _fp_name in FP_CREDENTIALS:
            fp_client_names = FP_CREDENTIALS[_fp_name].keys()
            b_client_name = booking.b_client_name.lower()

            for client_name in fp_client_names:
                if _fp_name == "startrack":
                    # Only built-in pricing for Startrack
                    continue
                    # pass

                if client_name == "test":
                    pass
                elif b_client_name in fp_client_names and b_client_name != client_name:
                    continue
                elif b_client_name not in fp_client_names and client_name not in [
                    "dme",
                    "test",
                ]:
                    continue

                logger.info(f"#905 [PRICING] - {_fp_name}, {client_name}")
                for key in FP_CREDENTIALS[_fp_name][client_name].keys():
                    logger.info(f"#905 [PRICING] - {key}")
                    account_detail = FP_CREDENTIALS[_fp_name][client_name][key]

                    # Allow live pricing credentials only on PROD
                    if settings.ENV == "prod" and "test" in key:
                        continue

                    # Allow test credential only Sendle+DEV
                    if (
                        settings.ENV == "dev"
                        and _fp_name == "sendle"
                        and "dme" == client_name
                    ):
                        continue

                    # Pricing only accounts can be used on pricing_only mode
                    if "pricingOnly" in account_detail and not is_pricing_only:
                        continue

                    logger.info(f"#906 [PRICING] - {_fp_name}, {client_name}")

                    if _fp_name == "auspost" and fp_services:
                        for service in fp_services:
                            thread = threading.Thread(
                                target=_api_pricing_worker_builder,
                                args=(
                                    pricing_id,
                                    _fp_name,
                                    booking,
                                    booking_lines,
                                    is_pricing_only,
                                    packed_status,
                                    account_detail,
                                    client,
                                    fp,
                                    fp_services.fp_delivery_service_code,
                                    fp_services.fp_delivery_time_description,
                                ),
                            )
                            threads.append(thread)
                    else:
                        thread = threading.Thread(
                            target=_api_pricing_worker_builder,
                            args=(
                                pricing_id,
                                _fp_name,
                                booking,
                                booking_lines,
                                is_pricing_only,
                                packed_status,
                                account_detail,
                                client,
                                fp,
                            ),
                        )
                        threads.append(thread)

        if _fp_name in BUILT_IN_PRICINGS:
            logger.info(f"#908 [BUILT_IN PRICING] - {_fp_name}")
            thread = threading.Thread(
                target=_built_in_pricing_worker_builder,
                args=(
                    pricing_id,
                    _fp_name,
                    booking,
                    booking_lines,
                    is_pricing_only,
                    packed_status,
                    client,
                    fp,
                    fp_zones.get(str(fp.pk), []),
                    fp_vehicles.get(str(fp.pk), []),
                    fp_rules.get(str(fp.pk), []),
                ),
            )
            threads.append(thread)

    logger.info("#911 [PRICING] - Pricing workers will start soon")
    return threads
    logger.info("#919 [PRICING] - Pricing workers finished all")


def _api_pricing_worker_builder(
    pricing_id,
    _fp_name,
    booking,
    booking_lines,
    is_pricing_only,
    packed_status,
    account_detail,
    client,
    fp,
    service_code=None,
    service_name=None,
):
    headers = HEADER_FOR_NODE
    url = DME_LEVEL_API_URL + "/pricing/calculateprice"
    payload = get_pricing_payload(
        booking, _fp_name, fp, account_detail, booking_lines, service_code
    )

    if not payload:
        if is_pricing_only:
            message = f"#907 [PRICING] Failed to build payload - {booking.pk_booking_id}, {_fp_name}"
        else:
            message = f"#907 [PRICING] Failed to build payload - {booking.b_bookingID_Visual}, {_fp_name}"

        logger.info(message)
        return None

    if _fp_name == "mrl sampson":
        from api.fps.team_global_express import get_headers as get_spojit_headers
        from api.fps.mrl_sampson import get_base_url

        headers = get_spojit_headers(booking)
        url = get_base_url()

    logger.info(f"### [PRICING] ({_fp_name.upper()}) API url: {url}")
    logger.info(f"### [PRICING] ({_fp_name.upper()}) Payload: {payload}")

    try:
        response = requests.post(url, params={}, json=payload, headers=headers)
        logger.info(
            f"### [PRICING] Response ({_fp_name.upper()}): {response.status_code}"
        )
        res_content = response.content.decode("utf8").replace("'", '"')
        json_data = json.loads(res_content)
        s0 = json.dumps(json_data, indent=2, sort_keys=True)  # Just for visual
        logger.info(f"### [PRICING] Response Detail ({_fp_name.upper()}): {s0}")

        # if not is_pricing_only:
        #     Log.objects.create(
        #         request_payload=payload,
        #         request_status="SUCCESS",
        #         request_type=f"{_fp_name.upper()} PRICING",
        #         response=res_content,
        #         fk_booking_id=booking.id,
        #     )

        parse_results = parse_pricing_response(
            response,
            _fp_name,
            client,
            fp,
            booking,
            False,
            service_name,
            payload["spAccountDetails"]["accountCode"],
        )

        if parse_results and not "error" in parse_results:
            for index, parse_result in enumerate(parse_results):
                parse_result["packed_status"] = packed_status
                save_2_redis(pricing_id, parse_result, booking, client, fp, index)
    except Exception as e:
        trace_error.print()
        logger.info(f"@402 [PRICING] Exception: {str(e)}")


def _built_in_pricing_worker_builder(
    pricing_id,
    _fp_name,
    booking,
    booking_lines,
    is_pricing_only,
    packed_status,
    client,
    fp,
    fp_zones,
    fp_vehicles,
    fp_rules,
):
    results = get_self_pricing(
        _fp_name,
        booking,
        client,
        fp,
        fp_zones,
        fp_vehicles,
        fp_rules,
        booking_lines,
        is_pricing_only,
    )
    logger.info(
        f"#909 [BUILT_IN PRICING] - {_fp_name}, Result cnt: {len(results['price'])}, Results: {results['price']}"
    )

    parse_results = parse_pricing_response(
        results, _fp_name, client, fp, booking, True, None
    )

    for index, parse_result in enumerate(parse_results):
        if parse_results and not "error" in parse_results:
            parse_result["packed_status"] = packed_status
            save_2_redis(pricing_id, parse_result, booking, client, fp, index)
