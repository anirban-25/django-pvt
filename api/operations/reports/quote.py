import os
from django.conf import settings

from api.models import Bookings, Booking_lines
from api.helpers.cubic import get_cubic_meter
from api.fp_apis.constants import SPECIAL_FPS
from api.fp_apis.utils import get_m3_to_kg_factor
from api.common.time import convert_to_AU_SYDNEY_tz, get_sydney_now_time
from api.common.ratio import _get_dim_amount, _get_weight_amount


def build_quote_report(kf_client_ids, start_date, end_date):
    bookings = Bookings.objects.prefetch_related("api_booking_quote").filter(
        b_dateBookedDate__isnull=False,
        z_CreatedTimestamp__gte=start_date,
        z_CreatedTimestamp__lte=end_date,
    )

    if kf_client_ids:
        bookings = bookings.filter(kf_client_id__in=kf_client_ids)

    bookings = bookings.only(
        "id",
        "b_bookingID_Visual",
        "pk_booking_id",
        "b_client_order_num",
        "b_client_sales_inv_num",
        "b_status",
        "api_booking_quote_id",
        "inv_sell_quoted",
        "inv_booked_quoted",
        "vx_freight_provider",
        "b_dateBookedDate",
        "x_manual_booked_flag",
    )
    pk_booking_ids = [booking.pk_booking_id for booking in bookings]
    lines = Booking_lines.objects.filter(fk_booking_id__in=pk_booking_ids)
    lines = lines.only(
        "fk_booking_id",
        "packed_status",
        "e_qty",
        "sscc",
        "e_dimUOM",
        "e_dimLength",
        "e_dimWidth",
        "e_dimHeight",
    )

    # Open CSV file
    now_str = str(get_sydney_now_time("datetime").strftime("%d-%m-%Y__%H_%M_%S"))
    csv_name = f"quote_report_{now_str}.csv"
    path = f"{settings.STATIC_PUBLIC}/csvs/reports"
    if not os.path.exists(path):
        os.makedirs(path)
    fileHandler = open(f"{path}/{csv_name}", "w")

    # Write Header
    fileHandler.write(
        "b_bookingID_Visual, pk_booking_id, b_dateBookedDate, vx_freight_provider, b_client_order_num"
        + ", qty, total_kg_actual, t_actual_cubic_meter, t_actual_cubic_kg, t_cubic_meter_utilized, t_cubic_kg_utilized"
        + ", inv_booked_quoted, inv_sell_quoted, pallet_sized_booked, b_booking_project, x_manual_booked_flag\n"
    )
    fileHandler.write(
        "BookingID, pk_booking_id, BookedDate, FP, OrderNo"
        + ", QTY, Weight in Kg, Cubic in M3, Cubic Weight, Utilized Cubic Meter in M3, Utilized Weight in Kg"
        + ", Quoted Dollar, Booked Dollar, Pallet Sized Booked Dollar, Vehicle or Project, Manual BOOK\n"
    )

    # Write Each Line
    comma = ","
    newLine = "\n"
    for booking in bookings:
        if booking.vx_freight_provider in SPECIAL_FPS:
            price = 0
        booking_lines = []
        sscc_lines = []
        total_qty_1, total_qty_2 = 0, 0
        for line in lines:
            if booking.pk_booking_id == line.fk_booking_id:
                booking_lines.append(line)
                if line.sscc and not "NO" in line.sscc:
                    sscc_lines.append(line)
                    total_qty_1 += line.e_qty
        _lines = []
        if sscc_lines:
            _lines = sscc_lines
        else:
            has_scanned = False
            for line in booking_lines:
                if line.packed_status == "scanned":
                    has_scanned = True
            for line in booking_lines:
                if line.e_item != "Auto repacked item":
                    if has_scanned and line.packed_status != "scanned":
                        continue
                    total_qty_2 += line.e_qty
                    _lines.append(line)

        total_weight = 0
        cubic_meter = 0
        total_cubic_weight = 0
        util_cbm = 0
        util_kgs = 0
        dim_ratio = _get_dim_amount(line.e_dimUOM)
        for line in _lines:
            cubic_meter += get_cubic_meter(
                line.e_dimLength,
                line.e_dimWidth,
                line.e_dimHeight,
                line.e_dimUOM,
                line.e_qty,
            )
            total_weight += (
                _get_weight_amount(line.e_weightUOM) * line.e_weightPerEach * line.e_qty
            )
            _m3_to_kg_factor = get_m3_to_kg_factor(booking.vx_freight_provider)
            total_cubic_weight += cubic_meter * _m3_to_kg_factor
            util_cbm += line.e_util_cbm or 0
            util_kgs += line.e_util_kg or 0

        if booking.vx_freight_provider in SPECIAL_FPS:
            eachLineText = (
                str(booking.b_bookingID_Visual)
                + comma
                + booking.pk_booking_id
                + comma
                + convert_to_AU_SYDNEY_tz(booking.b_dateBookedDate).strftime(
                    "%d/%m/%Y %H:%M:%S"
                )
                + comma
                + (booking.vx_freight_provider or "")
                + comma
                + (booking.b_client_order_num or "")
                + comma
                + str(total_qty_1 or total_qty_2)
                + comma
                + f"{round(total_weight, 3)}"
                + comma
                + f"{round(cubic_meter, 3)}"
                + comma
                + f"{round(total_cubic_weight, 3)}"
                + comma
                + f"{round(util_cbm, 3)}"
                + comma
                + f"{round(util_kgs, 3)}"
                + comma
                + f"${booking.inv_sell_quoted}"
                + comma
                + f"${booking.inv_booked_quoted}"
                + comma
                + f"${booking.api_booking_quote.tax_value_5 if booking.api_booking_quote else 'N/A'}"
                + comma
                + f"{booking.b_booking_project}"
                + comma
                + f"{'Manual' if booking.x_manual_booked_flag else 'AUTO'}"
            )
        else:
            eachLineText = (
                str(booking.b_bookingID_Visual)
                + comma
                + booking.pk_booking_id
                + comma
                + convert_to_AU_SYDNEY_tz(booking.b_dateBookedDate).strftime(
                    "%d/%m/%Y %H:%M:%S"
                )
                + comma
                + (booking.vx_freight_provider or "")
                + comma
                + (booking.b_client_order_num or "")
                + comma
                + str(total_qty_1 or total_qty_2)
                + comma
                + f"{round(total_weight, 3)}"
                + comma
                + f"{round(cubic_meter, 3)}"
                + comma
                + f"{round(total_cubic_weight, 3)}"
                + comma
                + f"{round(util_cbm, 3)}"
                + comma
                + f"{round(util_kgs, 3)}"
                + comma
                + f"${booking.inv_sell_quoted}"
                + comma
                + f"${booking.inv_booked_quoted}"
                + comma
                + f"${booking.api_booking_quote.tax_value_5 if booking.api_booking_quote else 'N/A'}"
                + comma
                + f"{booking.b_booking_project}"
                + comma
                + f"{'Manual' if booking.x_manual_booked_flag else 'AUTO'}"
            )

        fileHandler.write(eachLineText + newLine)

    return f"{path}/{csv_name}"
