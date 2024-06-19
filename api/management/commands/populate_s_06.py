from django.core.management.base import BaseCommand

from api.models import Bookings
from api.utils import get_eta_pu_by, get_eta_de_by


class Command(BaseCommand):
    def handle(self, *args, **options):
        # print("----- Populating category from status... -----")
        bookings = (
            Bookings.objects.select_related("api_booking_quote")
            .filter(b_dateBookedDate__isnull=False, api_booking_quote_id__isnull=False)
            .only(
                "id",
                "b_bookingID_Visual",
                "vx_freight_provider",
                "b_status",
                "pu_PickUp_By_Date",
                "pu_PickUp_By_Time_Hours",
                "pu_PickUp_By_Time_Minutes",
                "api_booking_quote",
            )
        )
        bookings_cnt = bookings.count()

        for index, booking in enumerate(bookings):
            if not booking.s_06_Latest_Delivery_Date_TimeSet:
                booking.s_06_Latest_Delivery_Date_TimeSet = get_eta_de_by(
                    booking, booking.api_booking_quote
                )
                # print(
                #     f"Processing {index + 1}/{bookings_cnt} {booking.b_bookingID_Visual}, {booking.pu_PickUp_By_Date}, {booking.s_06_Latest_Delivery_Date_TimeSet}"
                # )
                booking.save()

        # print("\n----- Finished! -----")
