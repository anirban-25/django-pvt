import json
import logging
import requests

from django.core.management.base import BaseCommand

from api.models import (
    Bookings,
    Dme_status_history,
    FP_status_history,
    Dme_utl_fp_statuses,
    Utl_dme_status,
)
from api.fp_apis.utils import (
    get_dme_status_from_fp_status,
    get_status_category_from_status,
)


logger = logging.getLogger(__name__)

STATUS_TO_BE_EXCLUDED = [
    "Entered",
    "Imported / Integrated",
    "Ready for Despatch",
    "Ready for Booking",
    "Picking",
    "Picked",
    "Closed",
    "Cancelled",
]

TRANSIT_STATUSES = [
    "In Transit",
    "Returning",
    "Futile",
    "Partially Delivered",
    "Partially In Transit",
    "Delivery Delayed",
    "Scanned into Depot",
    "Carded",
    "Insufficient Address",
    "Picked Up",
    "On-Forwarded",
]


FPS_TO_BE_PROCESSED = ["TNT", "HUNTER", "SENDLE", "ALLIED"]

# PLUM & JasonL
CLIENTS_TO_BE_PROCESSED = [
    "461162D2-90C7-BF4E-A905-000000000004",
    "1af6bcd2-6148-11eb-ae93-0242ac130002",
]


class Command(BaseCommand):
    def add_arguments(self, parser):
        parser.add_argument("booking_ids")
        parser.add_argument("is_check_only")

    def handle(self, *args, **options):
        print("----- Checking status_histories... -----")

        booking_ids = options["booking_ids"]
        is_check_only = options["is_check_only"] == "True"

        if booking_ids:
            print(f"    Bookings to process: {booking_ids.split(', ')}")

        # Prepare data
        if booking_ids:
            bookings = Bookings.objects.filter(pk__in=booking_ids.split(", "))
        else:
            bookings = (
                Bookings.objects.all()
                .filter(kf_client_id__in=CLIENTS_TO_BE_PROCESSED)
                .exclude(b_status__in=STATUS_TO_BE_EXCLUDED)
                .order_by("id")
                .only(
                    "id",
                    "pk_booking_id",
                    "b_bookingID_Visual",
                    "vx_freight_provider",
                    "b_status",
                )
            )
        bookings_cnt = bookings.count()
        print(f"    Bookings to process: {bookings_cnt}")

        pk_booking_ids = []
        for booking in bookings:
            pk_booking_ids.append(booking.pk_booking_id)

        dme_shs = Dme_status_history.objects.filter(fk_booking_id__in=pk_booking_ids)
        dme_shs = dme_shs.order_by("id")
        fp_shs = FP_status_history.objects.filter(booking__in=bookings)
        fp_shs = fp_shs.filter(is_active=True).order_by("id")
        status_mappings = Dme_utl_fp_statuses.objects.all()
        category_mappings = Utl_dme_status.objects.all()

        # Processing...
        for booking in bookings:
            print(
                f"@100 - Booking: {booking.b_bookingID_Visual} ({booking.pk_booking_id})"
            )

            b_fp_shs = []
            for fp_sh in fp_shs:
                if booking == fp_sh.booking:
                    b_fp_shs.append(fp_sh)

            expected_shs = get_expected_status_histories(
                booking, b_fp_shs, status_mappings, category_mappings, is_check_only
            )

            if not expected_shs:
                message = "@104 - No expected statusHistories."
                print(message)
                continue

            b_dme_shs = []
            for dme_sh in dme_shs:
                if booking.pk_booking_id == dme_sh.fk_booking_id:
                    b_dme_shs.append(dme_sh)

            populate_status_history(booking, b_dme_shs, expected_shs, is_check_only)


def populate_status_history(booking, dme_shs, expected_shs, is_check_only):
    index = 0
    has_wrong_sh = None
    print("Expected StatusHistories - ", expected_shs)

    if is_check_only:
        print("CHECK_ONLY so no write operations!")
        return

    for dme_sh in dme_shs:
        if dme_sh.status_last in [
            None,
            "Imported / Integrated",
            "Ordered",
            "Entered",
            "Picking",
            "Picked",
            "Booked",
        ]:
            continue

        if has_wrong_sh:
            dme_sh.delete()  # WRITE OPERATION - DELETE
            continue

        try:
            expected_sh = expected_shs[index]
        except:
            return False

        index += 1

        if (
            dme_sh.status_old != expected_sh["status_old"]
            or dme_sh.status_last != expected_sh["status_last"]
            or dme_sh.event_time_stamp != expected_sh["event_time_stamp"]
        ):
            print("    @106 Wrong statusHistory", dme_sh, expected_sh)
            has_wrong_sh = True
            index -= 1  # Rollback index
            dme_sh.delete()  # WRITE OPERATION - DELETE

    for index_1, expected_sh in enumerate(expected_shs):
        if index < len(expected_shs) and index_1 >= index:
            expected_sh = expected_shs[index_1]
            print("    @107 New statusHistory", expected_sh)
            new_dme_sh = Dme_status_history()
            new_dme_sh.fk_booking_id = booking.pk_booking_id
            new_dme_sh.status_old = expected_sh["status_old"]
            new_dme_sh.status_last = expected_sh["status_last"]
            new_dme_sh.notes = expected_sh["notes"]
            new_dme_sh.event_time_stamp = expected_sh["event_time_stamp"]
            new_dme_sh.status_update_via = "MANAGE COMM"  # Management command
            new_dme_sh.save()  # WRITE OPERATION - CREATE


def get_expected_status_histories(
    booking, fp_shs, status_mappings, category_mappings, is_check_only
):
    fp_name = booking.vx_freight_provider.lower()
    old_category = "Booked"
    old_status = "Booked"
    expected_shs = []

    for fp_sh in fp_shs:
        dme_status = get_dme_status_from_fp_status(
            fp_name, fp_sh.status, status_mappings
        )
        category = get_status_category_from_status(dme_status, category_mappings)

        if is_check_only:
            print(
                f"FP Name: {fp_name.upper()}, FP status: {fp_sh.status}, DME status: {dme_status}, Category: {category}"
            )

        if dme_status and dme_status != old_status:
            latest_expected_sh = expected_shs[:-1] if expected_shs else None
            status_old = old_status
            status_last = dme_status
            notes = f"{status_old} --> {status_last}"
            event_timestamp = fp_sh.event_timestamp
            expected_shs.append(
                {
                    "b_status_API": fp_sh.status,
                    "status_old": status_old,
                    "status_last": status_last,
                    "notes": notes,
                    "event_time_stamp": event_timestamp,
                }
            )
            old_status = dme_status

    return expected_shs


def get_dme_status_from_fp_status(fp_name, fp_status, status_mappings):
    rules = []
    status_info = None

    for status_mapping in status_mappings:
        if status_mapping.fp_name.lower() == fp_name:
            rules.append(status_mapping)

    if fp_name.lower() == "allied":
        for rule in rules:
            if "XXX" in rule.fp_lookup_status:
                fp_lookup_status = rule.fp_lookup_status.replace("XXX", "")

                if fp_lookup_status in fp_status:
                    status_info = rule
            elif rule.fp_lookup_status == fp_status:
                status_info = rule
    else:
        for rule in rules:
            if rule.fp_lookup_status == fp_status:
                status_info = rule

    try:
        return status_info.dme_status
    except Exception as e:
        message = f"    @101 - Missing status rule: {fp_status}"
        print(message)


def get_status_category_from_status(status, category_mappings):
    if not status:
        return None

    for category_mapping in category_mappings:
        if category_mapping.dme_delivery_status == status:
            return category_mapping.dme_delivery_status_category

    message = f"    @102 Category not found with this status: {status}"
    print(message)
    return None
