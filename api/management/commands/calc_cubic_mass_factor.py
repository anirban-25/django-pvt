import math
from django.core.management.base import BaseCommand
from api.models import Booking_lines, Bookings

from api.helpers.cubic import get_cubic_meter, getM3ToKgFactor


class Command(BaseCommand):
    def handle(self, *args, **options):
        print("----- Fetching lines... -----")

        booking_lines = Booking_lines.objects.filter(
            e_dimLength__isnull=False,
            e_dimWidth__isnull=False,
            e_dimHeight__isnull=False,
            e_dimUOM__isnull=False,
            e_weightPerEach__isnull=False,
            e_weightUOM__isnull=False,
            e_1_Total_dimCubicMeter__isnull=False,
        ).only(
            "e_dimLength",
            "e_dimWidth",
            "e_dimHeight",
            "e_weightPerEach",
            "e_dimUOM",
            "e_weightUOM",
            "e_1_Total_dimCubicMeter",
            "total_2_cubic_mass_factor_calc",
        )

        fetched_row_count = booking_lines.count()
        print(f"Fetched {fetched_row_count} lines")

        print("----- Calculating cubic meter... -----")
        update_row_count = 0
        for index, booking_line in enumerate(booking_lines):
            booking = (
                Bookings.objects.filter(pk_booking_id=booking_line.fk_booking_id)
                .only("vx_freight_provider")
                .first()
            )
            if not booking:
                continue
            if (index + 1) % 1000 == 0:
                print(f"Processed {index + 1}/{fetched_row_count} lines")

            old_total_2_cubic_mass_factor_calc = (
                booking_line.total_2_cubic_mass_factor_calc
            )
            m3ToKgFactor = getM3ToKgFactor(
                booking.vx_freight_provider,
                booking_line.e_dimLength,
                booking_line.e_dimWidth,
                booking_line.e_dimHeight,
                booking_line.e_weightPerEach,
                booking_line.e_dimUOM,
                booking_line.e_weightUOM,
            )

            booking_line.total_2_cubic_mass_factor_calc = math.ceil(
                booking_line.e_1_Total_dimCubicMeter * m3ToKgFactor
            )

            if (
                old_total_2_cubic_mass_factor_calc
                != booking_line.total_2_cubic_mass_factor_calc
            ):
                update_row_count += 1
                booking_line.save()

        print(
            f"\n'total_2_cubic_mass_factor_calc' updated on {update_row_count} of rows"
        )
        print("\n----- Finished! -----")
