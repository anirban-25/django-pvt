from datetime import datetime

from django.core.management.base import BaseCommand

from api.models import Bookings, Utl_dme_status
from api.fp_apis.utils import get_status_category_from_status


class Command(BaseCommand):
    def handle(self, *args, **options):
        # print("----- Populating category from status... -----")
        bookings = (
            Bookings.objects.filter(
                b_status__isnull=False, b_dateBookedDate__isnull=False
            )
            .exclude(
                b_status__in=[
                    "On Hold",
                    "Imported / Integrated",
                    "Entered",
                    "Picking",
                    "Picked",
                    "Closed",
                    "Cancelled",
                ],
                b_status_category="Completed",
            )
            .exclude(z_lock_status=True)
            .only(
                "id",
                "b_bookingID_Visual",
                "b_status",
                "b_status_category",
                "z_ModifiedTimestamp",
            )
            .order_by("z_ModifiedTimestamp")
        )
        utl_categories = Utl_dme_status.objects.all()
        bookings_cnt = bookings.count()
        print(f"Bookings Cnt: {bookings_cnt}")

        for index, booking in enumerate(bookings):
            category = None

            for utl_category in utl_categories:
                if booking.b_status == utl_category.dme_delivery_status:
                    category = utl_category.dme_delivery_status_category
                    break

            if category and category != booking.b_status_category:
                print(
                    f"Processing {index + 1}/{bookings_cnt} {booking.b_bookingID_Visual}, {booking.b_status}({booking.b_status_category}) -> {category}, {booking.z_ModifiedTimestamp}"
                )
                booking.z_ModifiedTimestamp = datetime.now()
                booking.b_status_category = category
                booking.save()

        # print("\n----- Finished! -----")
