from django.core.management.base import BaseCommand
from api.models import Booking_lines

from api.helpers.cubic import get_cubic_meter


class Command(BaseCommand):
    def handle(self, *args, **options):
        print("----- Fetching lines... -----")
        booking_lines = Booking_lines.objects.filter(
            e_dimLength__isnull=False,
            e_dimWidth__isnull=False,
            e_dimHeight__isnull=False,
            e_dimUOM__isnull=False,
        ).only(
            "e_dimLength",
            "e_dimWidth",
            "e_dimHeight",
            "e_dimUOM",
            "e_1_Total_dimCubicMeter",
        )
        print(f"Fetched {booking_lines.count()} lines")

        print("----- Calculating cubic meter... -----")
        update_row_count = 0
        for index, booking_line in enumerate(booking_lines):
            if (index + 1) % 1000 == 0:
                print(f"Processed {index + 1}/{fetched_row_count} lines")

            old_e_1_Total_dimCubicMeter = booking_line.e_1_Total_dimCubicMeter
            booking_line.e_1_Total_dimCubicMeter = get_cubic_meter(
                booking_line.e_dimLength,
                booking_line.e_dimWidth,
                booking_line.e_dimHeight,
                booking_line.e_dimUOM,
            )

            if old_e_1_Total_dimCubicMeter != booking_line.e_1_Total_dimCubicMeter:
                update_row_count += 1
                booking_line.save()

        print(f"\n'e_1_Total_dimCubicMeter' updated on {update_row_count} of rows")
        print("\n----- Finished! -----")


# from api.models import Bookings, Booking_lines
# from api.helpers.cubic import get_cubic_meter
# from api.fp_apis.constants import SPECIAL_FPS
# from api.common.time import convert_to_AU_SYDNEY_tz
# from api.common.ratio import _get_dim_amount, _get_weight_amount
# from api.helpers.cubic import get_cubic_meter

# print("----- Fetching bookings & lines ... -----")
# bookings = Bookings.objects.filter(kf_client_id__in=['461162D2-90C7-BF4E-A905-000000000004', '1af6bcd2-6148-11eb-ae93-0242ac130002', '9e72da0f-77c3-4355-a5ce-70611ffd0bc8'], b_dateBookedDate__isnull=True)
# bookings = bookings.only('id', 'b_bookingID_Visual', 'pk_booking_id')
# pk_booking_ids = [booking.pk_booking_id for booking in bookings]
# lines = Booking_lines.objects.filter(fk_booking_id__in=pk_booking_ids, e_dimUOM__isnull=False).only(
#     "e_dimLength",
#     "e_dimWidth",
#     "e_dimHeight",
#     "e_dimUOM",
#     "e_1_Total_dimCubicMeter",
# )
# fetched_row_count = lines.count()
# print(f"Fetched {lines.count()} lines")


# print("----- Calculating cubic meter... -----")
# update_row_count = 0
# for index, booking_line in enumerate(lines):
#     if (index + 1) % 1000 == 0:
#         print(f"Processed {index + 1}/{fetched_row_count} lines")
#     old_e_1_Total_dimCubicMeter = booking_line.e_1_Total_dimCubicMeter
#     booking_line.e_1_Total_dimCubicMeter = get_cubic_meter(
#         booking_line.e_dimLength,
#         booking_line.e_dimWidth,
#         booking_line.e_dimHeight,
#         booking_line.e_dimUOM,
#     )
#     if old_e_1_Total_dimCubicMeter != booking_line.e_1_Total_dimCubicMeter:
#         update_row_count += 1
#         booking_line.save()

# print(f"\n'e_1_Total_dimCubicMeter' updated on {update_row_count} of rows")
# print("\n----- Finished! -----")
