import logging
from api.models import (
    Bookings,
    Booking_lines,
    Booking_lines_data,
    Surcharge,
    Dme_status_history,
)
from api.common import trace_error, constants as dme_constants

logger = logging.getLogger(__name__)


def _get_pk_booking_ids(bookings):
    _pk_booking_ids = []

    try:
        for booking in bookings:
            _pk_booking_ids.append(booking.pk_booking_id)
    except:
        for booking in bookings:
            _pk_booking_ids.append(booking["pk_booking_id"])

    return _pk_booking_ids


def _get_booking_pks(bookings):
    _booking_pks = []

    try:
        for booking in bookings:
            _booking_pks.append(booking.pk)
    except:
        for booking in bookings:
            _booking_pks.append(booking["id"])

    return _booking_pks


def get_gapRas(bookings):
    pk_booking_ids = _get_pk_booking_ids(bookings)
    return Booking_lines_data.objects.filter(
        fk_booking_id__in=pk_booking_ids, gap_ra__isnull=False
    ).only("fk_booking_id", "gap_ra")


def get_clientRefNumbers(bookings):
    pk_booking_ids = _get_pk_booking_ids(bookings)
    return Booking_lines_data.objects.filter(
        fk_booking_id__in=pk_booking_ids, clientRefNumber__isnull=False
    ).only("fk_booking_id", "clientRefNumber")


def get_connoteOrReference(bookings):
    pk_booking_ids = _get_booking_pks(bookings)
    return Surcharge.objects.filter(
        booking_id__in=pk_booking_ids, connote_or_reference__isnull=False
    ).only("booking_id", "connote_or_reference")


def get_lines_in_bulk(bookings):
    pk_booking_ids = _get_pk_booking_ids(bookings)
    return Booking_lines.objects.filter(
        fk_booking_id__in=pk_booking_ids,
        packed_status__in=["original", "scanned"],
        is_deleted=False,
    ).only(
        "fk_booking_id",
        "e_Total_KG_weight",
        "e_1_Total_dimCubicMeter",
        "e_type_of_packaging",
    )


def get_surcharges_in_bulk(bookings):
    booking_pks = _get_booking_pks(bookings)
    return Surcharge.objects.filter(booking_id__in=booking_pks).only("booking_id")


def get_status_histories_in_bulk(bookings):
    pk_booking_ids = _get_pk_booking_ids(bookings)
    return Dme_status_history.objects.filter(fk_booking_id__in=pk_booking_ids).only(
        "fk_booking_id",
        "status_old",
        "status_last",
        "event_time_stamp",
        "z_createdTimeStamp",
    )
