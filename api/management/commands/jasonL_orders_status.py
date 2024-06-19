import subprocess
from datetime import datetime, timedelta
from django.core.management.base import BaseCommand

from api.models import Bookings


class Command(BaseCommand):
    def handle(self, *args, **options):
        print("----- Get JasonL orders status... -----")
        bookings = (
            Bookings.objects.select_related("api_booking_quote")
            .filter(
                b_dateBookedDate__isnull=True,
                b_client_order_num__isnull=False,
                b_client_name="Jason L",
            )
            .exclude(b_status__in=["Closed", "Cancelled"])
            .order_by("z_CreatedTimestamp")
            .only(
                "id",
                "b_bookingID_Visual",
                "vx_freight_provider",
                "b_status",
                "b_status_category",
                "api_booking_quote",
                "b_client_order_num",
                "z_CreatedTimestamp",
            )
        )
        bookings_cnt = bookings.count()
        print(f"Bookings count: {bookings_cnt}")

        results = []
        for index, booking in enumerate(bookings):
            # - Split `order_num` and `suffix` -
            _order_num, suffix = booking.b_client_order_num, ""
            iters = _order_num.split("-")

            if len(iters) > 1:
                _order_num, suffix = iters[0], iters[1]

            print(f"OrderNum: {_order_num}, Suffix: {suffix}")
            # ---

            subprocess.run(
                [
                    "/home/ubuntu/jason_l/status/src/run.sh",
                    "--context_param",
                    f"param1={_order_num}",
                    "--context_param",
                    f"param2={suffix}",
                ]
            )
            file_path = "/home/ubuntu/jason_l/status/src/status.csv"
            csv_file = open(file_path)

            for i, line in enumerate(csv_file):
                if i == 1:
                    line_piece = line.split("|")
                    if line_piece[-1].isnumeric() and int(line_piece[-1]) > 89:
                        if booking.z_CreatedTimestamp.replace(tzinfo=None) > (
                            datetime.now() - timedelta(days=30)
                        ):
                            results.append(line)
                            booking.b_status = "Closed"
                            booking.b_status_category = "Complete"
                            booking.b_booking_Notes = "Inactive, auto closed"
                            booking.save()
                            print(f"{booking.b_client_order_num} is closed!")
        print(f"\nResult:\n {results}")
        print("\n----- Finished! -----")
