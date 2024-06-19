from api.models import Bookings, Booking_lines
from api.operations.manifests.dhl import build_manifest as build_DHL_manifest  # DHL
from api.operations.manifests.northline import (
    build_manifest as build_NORTHLINE_manifest,
)  # NORTHLINE
from api.operations.manifests.tas import build_manifest as build_TAS_manifest  # TAS
from api.operations.manifests.camerons import build_manifest as build_CAMERONS_manifest  # Cameron
from api.operations.manifests.default import (
    build_manifest as build_default_manifest,
)  # ST


# def get_manifested_list(bookings):
#     manifested_list = []

#     for booking in bookings:
#         if booking["manifest_timestamp"] is not None:
#             manifested_list.append(booking["b_bookingID_Visual"])

#     return manifested_list


def get_booking_lines(bookings):
    pk_booking_ids = bookings.values_list("pk_booking_id", flat=True)

    return Booking_lines.objects.filter(
        fk_booking_id__in=pk_booking_ids, is_deleted=False
    )


def build_manifest(booking_ids, username="", need_truck=False, timestamp=None):
    bookings = Bookings.objects.filter(pk__in=booking_ids)
    booking_lines = get_booking_lines(bookings)
    vx_freight_provider = bookings.first().vx_freight_provider.upper()

    if vx_freight_provider == "DHL":
        file_name = build_DHL_manifest(
            bookings, booking_lines, username, need_truck, timestamp
        )
    elif vx_freight_provider == "TAS":
        file_name = build_TAS_manifest(
            bookings, booking_lines, username, need_truck, timestamp
        )
    elif vx_freight_provider == "NORTHLINE":
        file_name = build_NORTHLINE_manifest(
            bookings, booking_lines, username, need_truck, timestamp
        )
    elif vx_freight_provider == "CAMERONS":
        file_name = build_CAMERONS_manifest(
            bookings, booking_lines, username, need_truck, timestamp
        )
    else:
        file_name = build_default_manifest(
            bookings, booking_lines, username, need_truck, timestamp
        )

    return bookings, file_name
