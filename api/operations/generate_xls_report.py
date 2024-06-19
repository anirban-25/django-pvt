import os
import math
import logging
import shutil
import xlsxwriter as xlsxwriter
from numpy import busday_count
from datetime import datetime, date, timedelta, time

from django.db.models import Q
from django.conf import settings

from api.models import *
from api.common.time import convert_to_AU_SYDNEY_tz
from api.common.ratio import _get_dim_amount, _get_weight_amount
from api.common.constants import PALLETS
from api.operations.booking.refs import get_gapRas, get_clientRefNumbers
from api.helpers.cubic import get_cubic_meter, getM3ToKgFactor

logger = logging.getLogger(__name__)


def build_xls(bookings, xls_type, username, start_date, end_date, show_field_name):
    if settings.ENV == "local":
        production = False  # Local
    else:
        production = True  # Dev

    # start check if xmls folder exists
    if production:
        local_filepath = "/opt/s3_private/xlss/"
    else:
        local_filepath = "./static/xlss/"

    if not os.path.exists(local_filepath):
        os.makedirs(local_filepath)
    # end check if xmls folder exists

    if start_date and end_date:
        filename = (
            username
            + "__"
            + xls_type
            + "__"
            + str(len(bookings))
            + "__"
            + str(start_date.strftime("%d-%m-%Y"))
            + "__"
            + str(end_date.strftime("%d-%m-%Y"))
            + "__"
            + str(datetime.now().strftime("%d-%m-%Y %H_%M_%S"))
            + ".xlsx"
        )

        date_range = f"{str(start_date.strftime('%d-%m-%Y'))}__{str(end_date.strftime('%d-%m-%Y'))}"

        if xls_type == "booked_bookings":
            filename = f"Shipments Booked ({date_range}).xlsx"
        elif xls_type == "real_time_bookings":
            filename = f"Real Time ({date_range}).xlsx"
        elif xls_type == "picked_up_bookings":
            filename = f"Shipments PickedUp ({date_range}).xlsx"
        elif xls_type == "box":
            filename = f"Bookings to Send Boxes ({date_range}).xlsx"
        elif xls_type == "futile":
            filename = f"Futile Bookings ({date_range}).xlsx"
        elif xls_type == "bookings_delivered":
            filename = f"Bookings Delivered ({date_range}).xlsx"
    else:
        _tail = f'__{str(len(bookings))}__{str(datetime.now().strftime("%d-%m-%Y %H_%M_%S"))}.xlsx'
        filename = f"{username}__{xls_type}__{_tail}"

        if xls_type == "booked_bookings":
            filename = f"Shipments Booked {_tail}"
        elif xls_type == "real_time_bookings":
            filename = f"Real Time {_tail}"
        elif xls_type == "picked_up_bookings":
            filename = f"Shipments PickedUp {_tail}"
        elif xls_type == "box":
            filename = f"Bookings to Send Boxes {_tail}"
        elif xls_type == "futile":
            filename = f"Futile Bookings {_tail}"
        elif xls_type == "bookings_delivered":
            filename = f"Bookings Delivered {_tail}"

    workbook = xlsxwriter.Workbook(filename, {"remove_timezone": True})

    if xls_type != "Whse":
        worksheet = workbook.add_worksheet()

    bold = workbook.add_format({"bold": 1, "align": "left"})
    date_format = workbook.add_format({"num_format": "dd/mm/yyyy"})
    time_format = workbook.add_format({"num_format": "hh:mm:ss"})
    red_bold = workbook.add_format({"font_color": "red", "bold": 1, "align": "left"})
    col = 0

    if xls_type == "Bookings":
        logger.info("#390 Get started to build `Bookings` XLS")
        worksheet.set_column(15, 16, width=40)
        worksheet.set_column(17, 17, width=53)
        worksheet.set_column(0, 14, width=25)
        worksheet.set_column(18, 40, width=25)

        if show_field_name:
            worksheet.write("A1", "b_dateBookedDate(Date)", bold)
            worksheet.write("B1", "b_dateBookedDate(Time)", bold)
            worksheet.write(
                "C1", "fp_received_date_time/b_given_to_transport_date_time", bold
            )
            worksheet.write("D1", "pu_Address_State", bold)
            worksheet.write("E1", "business_group", bold)
            worksheet.write("F1", "deToCompanyName", bold)
            worksheet.write("G1", "de_To_Address_Suburb", bold)
            worksheet.write("H1", "de_To_Address_State", bold)
            worksheet.write("I1", "de_To_Address_PostalCode", bold)
            worksheet.write("J1", "b_client_sales_inv_num", bold)
            worksheet.write("K1", "b_client_order_num", bold)
            worksheet.write("L1", "vx_freight_provider", bold)
            worksheet.write("M1", "v_FPBookingNumber", bold)
            worksheet.write("N1", "b_status", bold)
            worksheet.write("O1", "Total Qty", bold)
            worksheet.write("P1", "Total Scanned Qty", bold)
            worksheet.write("Q1", "Booked to Scanned Variance", bold)
            worksheet.write("R1", "b_fp_qty_delivered", bold)
            worksheet.write("S1", "dme_status_detail", bold)
            worksheet.write("T1", "dme_status_action", bold)
            worksheet.write("U1", "b_booking_Notes", bold)
            worksheet.write("V1", "s_21_Actual_Delivery_TimeStamp", bold)
            worksheet.write("W1", "zc_pod_or_no_pod", bold)
            worksheet.write("X1", "z_pod_url", bold)
            worksheet.write("Y1", "z_pod_signed_url", bold)
            worksheet.write("Z1", "delivery_kpi_days", bold)
            worksheet.write("AA1", "delivery_days_from_booked", bold)
            worksheet.write("AB1", "delivery_actual_kpi_days", bold)
            worksheet.write("AC1", "z_calculated_ETA", bold)
            worksheet.write("AD1", "fp_store_event_date", bold)
            worksheet.write("AE1", "fp_store_event_time", bold)
            worksheet.write("AF2", "fp_store_event_desc", bold)
            worksheet.write("AG1", "inv_billing_status", bold)
            worksheet.write("AH1", "inv_billing_status_note", bold)
            worksheet.write("AI1", "b_booking_project", bold)
            worksheet.write("AJ1", "b_project_due_date", bold)
            worksheet.write("AK1", "delivery_booking", bold)
            worksheet.write("AL1", "b_bookingID_Visual", bold)
            # worksheet.write("AI1", '=IF(N1="In Transit",IF(Z1=7,C1+5,C1+12),"")', bold)
            # worksheet.write("AJ1", '=IF(AD1="";AK1-TODAY;"Store Booked")', bold)

            worksheet.write("A2", "Booked Date", bold)
            worksheet.write("B2", "Booked Time", bold)
            worksheet.write("C2", "Given to / Received by Transport", bold)
            worksheet.write("D2", "From State", bold)
            worksheet.write("E2", "To Entity Group Name", bold)
            worksheet.write("F2", "To Entity", bold)
            worksheet.write("G2", "To Suburb", bold)
            worksheet.write("H2", "To State", bold)
            worksheet.write("I2", "To Postal Code", bold)
            worksheet.write("J2", "Client Sales Invoice", bold)
            worksheet.write("K2", "Client Order Number", bold)
            worksheet.write("L2", "Freight Provider", bold)
            worksheet.write("M2", "Consignment No", bold)
            worksheet.write("N2", "Status", bold)
            worksheet.write("O2", "Total Qty", bold)
            worksheet.write("P2", "Total Scanned Qty", bold)
            worksheet.write("Q2", "Booked to Scanned Variance", bold)
            worksheet.write("R2", "Total Delivered", bold)
            worksheet.write("S2", "Status Detail", bold)
            worksheet.write("T2", "Status Action", bold)
            worksheet.write("U2", "Status History Note", bold)
            worksheet.write("V2", "Actual Delivery", bold)
            worksheet.write("W2", "POD?", bold)
            worksheet.write("X2", "POD LINK", bold)
            worksheet.write("Y2", "POD Signed on Glass Link", bold)
            worksheet.write("Z2", "Target Delivery KPI (Days)", bold)
            worksheet.write("AA2", "Delivery Days from Booked", bold)
            worksheet.write("AB2", "Actual Delivery KPI (Days)", bold)
            worksheet.write("AC2", "Calculated ETA", bold)
            worksheet.write("AD2", "1st Contact For Delivery Booking Date", bold)
            worksheet.write("AE2", "1st Contact For Delivery Booking Time", bold)
            worksheet.write("AF2", "FP Store Activity Description", bold)
            worksheet.write("AG2", "Invoice Billing Status", bold)
            worksheet.write("AH2", "Invoice Billing Status Note", bold)
            worksheet.write("AI2", "Project Name", bold)
            worksheet.write("AJ2", "Project Due Date", bold)
            worksheet.write("AK2", "Delivery Booking Date", bold)
            worksheet.write("AL2", "Booking ID", bold)
            # worksheet.write("AI2", "Delivery Booking Target Date", bold)
            # worksheet.write("AJ2", "Delivery Booking - Days To Target", bold)

            row = 2
        else:
            worksheet.write("A1", "Booked Date", bold)
            worksheet.write("B1", "Booked Time", bold)
            worksheet.write("C1", "Given to / Received by Transport", bold)
            worksheet.write("D1", "From State", bold)
            worksheet.write("E1", "To Entity Group Name", bold)
            worksheet.write("F1", "To Entity", bold)
            worksheet.write("G1", "To Suburb", bold)
            worksheet.write("H1", "To State", bold)
            worksheet.write("I1", "To Postal Code", bold)
            worksheet.write("J1", "Client Sales Invoice", bold)
            worksheet.write("K1", "Client Order Number", bold)
            worksheet.write("L1", "Freigth Provider", bold)
            worksheet.write("M1", "Consignment No", bold)
            worksheet.write("N1", "Status", bold)
            worksheet.write("O1", "Total Qty", bold)
            worksheet.write("P1", "Total Scanned Qty", bold)
            worksheet.write("Q1", "Booked to Scanned Variance", bold)
            worksheet.write("R1", "Total Delivered", bold)
            worksheet.write("S1", "Status Detail", bold)
            worksheet.write("T1", "Status Action", bold)
            worksheet.write("U1", "Status History Note", bold)
            worksheet.write("V1", "Actual Delivery", bold)
            worksheet.write("W1", "POD?", bold)
            worksheet.write("X1", "POD LINK", bold)
            worksheet.write("Y1", "POD Signed on Glass Link", bold)
            worksheet.write("Z1", "Target Delivery KPI (Days)", bold)
            worksheet.write("AA1", "Delivery Days from Booked", bold)
            worksheet.write("AB1", "Actual Delivery KPI (Days)", bold)
            worksheet.write("AC1", "Calculated ETA", bold)
            worksheet.write("AD1", "1st Contact For Delivery Booking Date", bold)
            worksheet.write("AE1", "1st Contact For Delivery Booking Time", bold)
            worksheet.write("AF1", "FP Store Activity Description", bold)
            worksheet.write("AG1", "Invoice Billing Status", bold)
            worksheet.write("AH1", "Invoice Billing Status Note", bold)
            worksheet.write("AI1", "Project Name", bold)
            worksheet.write("AJ1", "Project Due Date", bold)
            worksheet.write("AK1", "Delivery Booking Date", bold)
            worksheet.write("AL1", "Booking ID", bold)
            # worksheet.write("AI1", "Delivery Booking Target Date", bold)
            # worksheet.write("AJ1", "Delivery Booking - Days To Target", bold)

            row = 1

        logger.info(f"#391 Total cnt: {len(bookings)}")
        for booking_ind, booking in enumerate(bookings):
            if booking_ind % 500 == 0:
                logger.info(f"#392 Current index: {booking_ind}")

            booking_lines = Booking_lines.objects.only(
                "e_qty", "e_qty_scanned_fp", "pk_lines_id"
            ).filter(fk_booking_id=booking.pk_booking_id)
            e_qty_total = 0
            e_qty_scanned_fp_total = 0

            for booking_line in booking_lines:
                if booking_line.e_qty is not None:
                    e_qty_total = e_qty_total + booking_line.e_qty

                if booking_line.e_qty_scanned_fp is not None:
                    e_qty_scanned_fp_total = (
                        e_qty_scanned_fp_total + booking_line.e_qty_scanned_fp
                    )

            if booking.b_dateBookedDate:
                worksheet.write_datetime(
                    row,
                    col + 0,
                    convert_to_AU_SYDNEY_tz(booking.b_dateBookedDate).date(),
                    date_format,
                )
                worksheet.write_datetime(
                    row,
                    col + 1,
                    convert_to_AU_SYDNEY_tz(booking.b_dateBookedDate),
                    time_format,
                )

            if booking.fp_received_date_time:
                worksheet.write_datetime(
                    row,
                    col + 2,
                    convert_to_AU_SYDNEY_tz(booking.fp_received_date_time),
                    date_format,
                )
            elif booking.b_given_to_transport_date_time:
                worksheet.write_datetime(
                    row,
                    col + 2,
                    convert_to_AU_SYDNEY_tz(booking.b_given_to_transport_date_time),
                    date_format,
                )

            worksheet.write(row, col + 3, booking.pu_Address_State)

            customer_group_name = ""
            customer_groups = Dme_utl_client_customer_group.objects.all()
            for customer_group in customer_groups:
                if (
                    booking.deToCompanyName
                    and customer_group.name_lookup
                    and customer_group.name_lookup.lower()
                    in booking.deToCompanyName.lower()
                ):
                    customer_group_name = customer_group.group_name
            worksheet.write(row, col + 4, customer_group_name)

            worksheet.write(row, col + 5, booking.deToCompanyName)
            worksheet.write(row, col + 6, booking.de_To_Address_Suburb)
            worksheet.write(row, col + 7, booking.de_To_Address_State)
            worksheet.write(row, col + 8, booking.de_To_Address_PostalCode)
            worksheet.write(row, col + 9, booking.b_client_sales_inv_num)
            worksheet.write(row, col + 10, booking.b_client_order_num)
            worksheet.write(row, col + 11, booking.vx_freight_provider)
            worksheet.write(row, col + 12, booking.v_FPBookingNumber)
            worksheet.write(row, col + 13, booking.b_status)
            worksheet.write(row, col + 14, e_qty_total)
            worksheet.write(row, col + 15, e_qty_scanned_fp_total)
            worksheet.write(row, col + 16, e_qty_total - e_qty_scanned_fp_total)
            worksheet.write(row, col + 17, booking.b_fp_qty_delivered)

            cell_format = workbook.add_format({"text_wrap": True})
            worksheet.write(row, col + 18, booking.dme_status_detail, cell_format)
            worksheet.write(row, col + 19, booking.dme_status_action, cell_format)
            worksheet.write(row, col + 20, booking.b_booking_Notes, cell_format)

            if (
                booking.s_21_Actual_Delivery_TimeStamp
                and booking.s_21_Actual_Delivery_TimeStamp
            ):
                worksheet.write_datetime(
                    row,
                    col + 21,
                    convert_to_AU_SYDNEY_tz(booking.s_21_Actual_Delivery_TimeStamp),
                    date_format,
                )

            if (booking.z_pod_url is not None and len(booking.z_pod_url) > 0) or (
                booking.z_pod_signed_url is not None
                and len(booking.z_pod_signed_url) > 0
            ):
                worksheet.write(row, col + 22, "Y")
            else:
                worksheet.write(row, col + 22, "")

            if settings.ENV == "dev":
                if booking.z_pod_url is not None and len(booking.z_pod_url) > 0:
                    worksheet.write_url(
                        row,
                        col + 23,
                        settings.S3_URL + "/imgs/" + booking.z_pod_url,
                        string=booking.z_pod_url,
                    )

                if (
                    booking.z_pod_signed_url is not None
                    and len(booking.z_pod_signed_url) > 0
                ):
                    worksheet.write_url(
                        row,
                        col + 24,
                        settings.S3_URL + "/imgs/" + booking.z_pod_signed_url,
                        string=booking.z_pod_signed_url,
                    )
            elif settings.ENV == "prod":
                if booking.z_pod_url is not None and len(booking.z_pod_url) > 0:
                    worksheet.write_url(
                        row,
                        col + 23,
                        settings.S3_URL + "/imgs/" + booking.z_pod_url,
                        string=booking.z_pod_url,
                    )

                if (
                    booking.z_pod_signed_url is not None
                    and len(booking.z_pod_signed_url) > 0
                ):
                    worksheet.write_url(
                        row,
                        col + 24,
                        settings.S3_URL + "/imgs/" + booking.z_pod_signed_url,
                        string=booking.z_pod_signed_url,
                    )

            worksheet.write(row, col + 25, booking.delivery_kpi_days)

            if (
                booking.b_status is not None
                and booking.b_status == "Delivered"
                and booking.s_21_Actual_Delivery_TimeStamp is not None
                and booking.b_dateBookedDate is not None
            ):
                worksheet.write(
                    row,
                    col + 26,
                    (
                        booking.s_21_Actual_Delivery_TimeStamp.date()
                        - booking.b_dateBookedDate.date()
                    ).days,
                )
                worksheet.write(
                    row,
                    col + 27,
                    booking.delivery_kpi_days
                    - (
                        booking.s_21_Actual_Delivery_TimeStamp.date()
                        - booking.b_dateBookedDate.date()
                    ).days,
                )

            if booking.z_calculated_ETA:
                worksheet.write_datetime(
                    row,
                    col + 28,
                    convert_to_AU_SYDNEY_tz(booking.z_calculated_ETA),
                    date_format,
                )

            if booking.fp_store_event_date:
                worksheet.write_datetime(
                    row,
                    col + 29,
                    convert_to_AU_SYDNEY_tz(booking.fp_store_event_date),
                    date_format,
                )

            if booking.fp_store_event_time:
                worksheet.write_datetime(
                    row,
                    col + 30,
                    convert_to_AU_SYDNEY_tz(booking.fp_store_event_time, "time"),
                    time_format,
                )

            worksheet.write(row, col + 31, booking.fp_store_event_desc)
            worksheet.write(row, col + 32, booking.inv_billing_status)
            worksheet.write(row, col + 33, booking.inv_billing_status_note)
            worksheet.write(row, col + 34, booking.b_booking_project)
            worksheet.write(
                row,
                col + 35,
                convert_to_AU_SYDNEY_tz(booking.b_project_due_date),
                date_format,
            )

            # Store Scheduled Date
            worksheet.write(
                row,
                col + 36,
                convert_to_AU_SYDNEY_tz(booking.delivery_booking),
                date_format,
            )

            worksheet.write(row, col + 37, booking.b_bookingID_Visual)

            # # Store Booking Date Due By
            # if booking.b_status == "In Transit" and booking.delivery_kpi_days:
            #     if int(booking.delivery_kpi_days) == 7:
            #         time_delta = 5
            #     else:
            #         time_delta = 12

            #     if booking.fp_received_date_time:
            #         worksheet.write_datetime(
            #             row,
            #             col + 34,
            #             booking.fp_received_date_time + timedelta(days=int(time_delta)),
            #             date_format,
            #         )
            #     elif booking.b_given_to_transport_date_time:
            #         worksheet.write_datetime(
            #             row,
            #             col + 34,
            #             booking.b_given_to_transport_date_time
            #             + timedelta(days=int(time_delta)),
            #             date_format,
            #         )

            # # Store Booking Early Late
            # if not booking.fp_store_event_date:
            #     store_booking_early_late = ""
            #     if int(booking.delivery_kpi_days) == 7:
            #         time_delta = 5
            #     else:
            #         time_delta = 12

            #     if booking.fp_received_date_time:
            #         store_booking_early_late = (
            #             sydney_today - booking.fp_received_date_time
            #         ).days + time_delta
            #     elif booking.b_given_to_transport_date_time:
            #         store_booking_early_late = (
            #             sydney_today - booking.b_given_to_transport_date_time
            #         ).days + time_delta
            #     worksheet.write(row, col + 35, str(store_booking_early_late))
            # else:
            #     worksheet.write(row, col + 35, "Store Booked")

            row += 1

        workbook.close()
        shutil.move(filename, local_filepath + filename)
        logger.info("#395 Finished - `Bookings` XLS")
    elif xls_type == "BookingLines":
        logger.info(f"#380 Get started to build `BookingLines` XLS")
        worksheet.set_column(0, 40, width=25)
        if show_field_name:
            worksheet.write("A1", "dme_bookings:v_FPBookingNumber", bold)
            worksheet.write("B1", "dme_bookings:b_dateBookedDate(Date)", bold)
            worksheet.write(
                "C1", "fp_received_date_time/b_given_to_transport_date_time", bold
            )
            worksheet.write(
                "D1",
                "api_booking_confirmation_lines:fp_event_date and fp_event_time",
                bold,
            )
            worksheet.write("E1", "dme_bookings:vx_freight_provider", bold)
            worksheet.write("F1", "dme_bookings:puCompany", bold)
            worksheet.write("G1", "dme_bookings:pu_Address_Suburb", bold)
            worksheet.write("H1", "dme_bookings:deToCompanyName", bold)
            worksheet.write("I1", "dme_bookings:de_To_Address_Suburb", bold)
            worksheet.write("J1", "dme_bookings:de_To_Address_State", bold)
            worksheet.write("K1", "dme_bookings:de_To_Address_PostalCode", bold)
            worksheet.write("L1", "dme_bookings:b_client_order_num", bold)
            worksheet.write("M1", "dme_bookings:b_client_sales_inv_num", bold)
            worksheet.write("N1", "modelNumber", bold)
            worksheet.write("O1", "e_item", bold)
            worksheet.write("P1", "e_item_qty", bold)
            worksheet.write("Q1", "client_item_reference", bold)
            worksheet.write("R1", "gap_ra", bold)
            worksheet.write("S1", "DD Received Date(Date)", bold)
            worksheet.write("T1", "DD Received Date(Time)", bold)
            worksheet.write("U1", "z_calculated_ETA", bold)
            worksheet.write("V1", "Dispatch Date", bold)
            worksheet.write("W1", "ETA Into Store", bold)
            worksheet.write("X1", "dme_bookings:b_status", bold)
            worksheet.write("Y1", "dme_bookings: dme_status_detail", bold)
            worksheet.write("Z1", "dme_bookings: dme_status_action", bold)
            worksheet.write("AA1", "POD Available", bold)
            worksheet.write("AB1", "e_qty_awaiting_inventory", bold)
            worksheet.write("AC1", "e_qty_collected", bold)
            worksheet.write("AD1", "e_qty_scanned_fp", bold)
            worksheet.write("AE1", "e_qty_scanned_depot", bold)
            worksheet.write("AF1", "e_qty_delivered", bold)
            worksheet.write("AG1", "e_qty_damaged", bold)
            worksheet.write("AH1", "e_qty_returned", bold)
            worksheet.write("AI1", "e_qty_shortages", bold)
            worksheet.write("AJ1", "e_qty_adjusted_delivered", bold)
            worksheet.write("AK1", "dme_bookings:b_booking_project", bold)
            worksheet.write("AL1", "dme_bookings:b_project_due_date", bold)
            worksheet.write("AM1", "dme_bookings:b_bookingID_Visual", bold)

            worksheet.write("A2", "Consignment No", bold)
            worksheet.write("B2", "Booked Date", bold)
            worksheet.write("C2", "Given to / Received by Transport", bold)
            worksheet.write("D2", "Date Scanned", bold)
            worksheet.write("E2", "Freight Provider", bold)
            worksheet.write("F2", "Pickup Entity", bold)
            worksheet.write("G2", "Pickup Suburb", bold)
            worksheet.write("H2", "To Entity", bold)
            worksheet.write("I2", "To Suburb", bold)
            worksheet.write("J2", "To State", bold)
            worksheet.write("K2", "To Postal Code", bold)
            worksheet.write("L2", "Customer Client Order No", bold)
            worksheet.write("M2", "Customer Invoice No", bold)
            worksheet.write("N2", "Model", bold)
            worksheet.write("O2", "Product Description", bold)
            worksheet.write("P2", "Booked Qty", bold)
            worksheet.write("Q2", "Client Item Reference", bold)
            worksheet.write("R2", "Gap/Ra", bold)
            worksheet.write("S2", "DD Received Date", bold)
            worksheet.write("T2", "DD Received Time", bold)
            worksheet.write("U2", "Calculated ETA", bold)
            worksheet.write("V2", "Dispatch Date", bold)
            worksheet.write("W2", "ETA Into Store", bold)
            worksheet.write("X2", "Status", bold)
            worksheet.write("Y2", "Status Detail", bold)
            worksheet.write("Z2", "Status Action", bold)
            worksheet.write("AA2", "POD?", bold)
            worksheet.write("AB2", "Inventory on Back Order", bold)
            worksheet.write("AC2", "Qty Confimred Collected by Pickup Entity", bold)
            worksheet.write("AD2", "Qty Scanned at Transporter Depot", bold)
            worksheet.write("AE2", "Same as Col T?", bold)
            worksheet.write("AF2", "Qty Delivered", bold)
            worksheet.write("AG2", "Qty Damaged", bold)
            worksheet.write("AH2", "Qty Returned", bold)
            worksheet.write("AI2", "Qty Short", bold)
            worksheet.write("AJ2", "Adjusted Delivered Qty", bold)
            worksheet.write("AK2", "Project Name", bold)
            worksheet.write("AL2", "Project Due Date", bold)
            worksheet.write("AM2", "DME Booking ID", bold)

            row = 2
        else:
            worksheet.write("A1", "Consignment No", bold)
            worksheet.write("B1", "Booked Date", bold)
            worksheet.write("C1", "Given to / Received by Transport", bold)
            worksheet.write("D1", "Date Scanned", bold)
            worksheet.write("E1", "Freight Provider", bold)
            worksheet.write("F1", "Pickup Entity", bold)
            worksheet.write("G1", "Pickup Suburb", bold)
            worksheet.write("H1", "To Entity", bold)
            worksheet.write("I1", "To Suburb", bold)
            worksheet.write("J1", "To State", bold)
            worksheet.write("K1", "To Postal Code", bold)
            worksheet.write("L1", "Customer Client Order No", bold)
            worksheet.write("M1", "Customer Invoice No", bold)
            worksheet.write("N1", "Model", bold)
            worksheet.write("O1", "Product Description", bold)
            worksheet.write("P1", "Booked Qty", bold)
            worksheet.write("Q1", "Client Item Reference", bold)
            worksheet.write("R1", "Gap/Ra", bold)
            worksheet.write("S1", "DD Received Date", bold)
            worksheet.write("T1", "DD Received Time", bold)
            worksheet.write("U1", "Calculated ETA", bold)
            worksheet.write("V1", "Dispatch Date", bold)
            worksheet.write("W1", "ETA Into Store", bold)
            worksheet.write("X1", "Status", bold)
            worksheet.write("Y1", "Status Detail", bold)
            worksheet.write("Z1", "Status Action", bold)
            worksheet.write("AA1", "POD?", bold)
            worksheet.write("AB1", "Inventory on Back Order", bold)
            worksheet.write("AC1", "Qty Confimred Collected by Pickup Entity", bold)
            worksheet.write("AD1", "Qty Scanned at Transporter Depot", bold)
            worksheet.write("AE1", "Same as Col T?", bold)
            worksheet.write("AF1", "Qty Delivered", bold)
            worksheet.write("AG1", "Qty Damaged", bold)
            worksheet.write("AH1", "Qty Returned", bold)
            worksheet.write("AI1", "Qty Short", bold)
            worksheet.write("AJ1", "Adjusted Delivered Qty", bold)
            worksheet.write("AK1", "Project Name", bold)
            worksheet.write("AL1", "Project Due Date", bold)
            worksheet.write("AM1", "DME Booking ID", bold)

            row = 1

        e_qty_total = 0
        e_qty_scanned_fp_total = 0

        pk_booking_ids = []
        for booking in bookings:
            pk_booking_ids.append(booking.pk_booking_id)
        lines = Booking_lines.objects.filter(fk_booking_id__in=pk_booking_ids).only(
            "pk_lines_id",
            "fk_booking_id",
            "pk_booking_lines_id",
            "e_qty",
            "e_qty_scanned_fp",
            "e_item",
            "e_pallet_type",
            "client_item_reference",
            "e_qty_awaiting_inventory",
            "e_qty_collected",
            "e_qty_scanned_fp",
            "e_qty_scanned_depot",
            "e_qty_delivered",
            "e_qty_damaged",
            "e_qty_returned",
            "e_qty_shortages",
            "e_qty_adjusted_delivered",
        )
        pk_booking_lines_ids = []
        for line in lines:
            pk_booking_lines_ids.append(line.pk_booking_lines_id)
        api_bcls = Api_booking_confirmation_lines.objects.filter(
            fk_booking_line_id__in=pk_booking_lines_ids
        )

        logger.info(f"#381 Total cnt: {len(bookings)}")
        for booking_ind, booking in enumerate(bookings):
            if booking_ind % 500 == 0:
                logger.info(f"#382 Current index: {booking_ind}")

            booking_lines = []
            for booking_line in lines:
                if booking_line.fk_booking_id == booking.pk_booking_id:
                    booking_lines.append(booking_line)

            for booking_line in booking_lines:
                worksheet.write(row, col + 0, booking.v_FPBookingNumber)

                if booking.b_dateBookedDate and booking.b_dateBookedDate:
                    worksheet.write_datetime(
                        row,
                        col + 1,
                        convert_to_AU_SYDNEY_tz(booking.b_dateBookedDate.date()),
                        date_format,
                    )

                if booking.fp_received_date_time:
                    worksheet.write_datetime(
                        row,
                        col + 2,
                        convert_to_AU_SYDNEY_tz(booking.fp_received_date_time),
                        date_format,
                    )
                elif booking.b_given_to_transport_date_time:
                    worksheet.write_datetime(
                        row,
                        col + 2,
                        convert_to_AU_SYDNEY_tz(booking.b_given_to_transport_date_time),
                        date_format,
                    )

                line_api_bcl = None
                for api_bcl in api_bcls:
                    if api_bcl.fk_booking_line_id == booking_line.pk_lines_id:
                        line_api_bcl = api_bcl
                        break

                if (
                    line_api_bcl
                    and line_api_bcl.fp_event_date
                    and line_api_bcl.fp_event_time
                ):
                    worksheet.write(
                        row,
                        col + 3,
                        line_api_bcl.fp_event_date.strftime("%d-%m-%Y")
                        + " "
                        + line_api_bcl.fp_event_time.strftime("%H:%M:%S"),
                    )

                worksheet.write(row, col + 4, booking.vx_freight_provider)
                worksheet.write(row, col + 5, booking.puCompany)
                worksheet.write(row, col + 6, booking.pu_Address_Suburb)
                worksheet.write(row, col + 7, booking.deToCompanyName)
                worksheet.write(row, col + 8, booking.de_To_Address_Suburb)
                worksheet.write(row, col + 9, booking.de_To_Address_State)
                worksheet.write(row, col + 10, booking.de_To_Address_PostalCode)
                worksheet.write(row, col + 11, booking.b_client_order_num)
                worksheet.write(row, col + 12, booking.b_client_sales_inv_num)
                worksheet.write(row, col + 13, booking_line.modelNumbers())
                worksheet.write(row, col + 14, booking_line.e_item)
                worksheet.write(row, col + 15, booking_line.e_qty)
                worksheet.write(row, col + 16, booking_line.client_item_reference)
                worksheet.write(row, col + 17, booking_line.gap_ras)

                if (
                    line_api_bcl
                    and line_api_bcl.fp_event_date
                    and line_api_bcl.fp_event_time
                ):
                    worksheet.write_datetime(
                        row,
                        col + 18,
                        convert_to_AU_SYDNEY_tz(line_api_bcl.fp_event_date),
                        date_format,
                    )
                    worksheet.write_datetime(
                        row,
                        col + 19,
                        convert_to_AU_SYDNEY_tz(line_api_bcl.fp_event_time, "time"),
                        time_format,
                    )

                if booking.z_calculated_ETA:
                    worksheet.write_datetime(
                        row,
                        col + 20,
                        convert_to_AU_SYDNEY_tz(booking.z_calculated_ETA),
                        date_format,
                    )

                if booking.de_Deliver_By_Date:
                    worksheet.write_datetime(
                        row,
                        col + 21,
                        convert_to_AU_SYDNEY_tz(booking.de_Deliver_By_Date),
                        date_format,
                    )

                if booking.de_Deliver_By_Date:
                    delivery_kpi_days = 0

                    if booking.delivery_kpi_days:
                        delivery_kpi_days = booking.delivery_kpi_days

                    worksheet.write(
                        row,
                        col + 22,
                        (
                            booking.de_Deliver_By_Date
                            + timedelta(days=int(delivery_kpi_days))
                        ).strftime("%d-%m-%Y"),
                    )
                else:
                    worksheet.write(row, col + 22, "")

                worksheet.write(row, col + 23, booking.b_status)
                worksheet.write(row, col + 24, booking.dme_status_detail)
                worksheet.write(row, col + 25, booking.dme_status_action)

                if (booking.z_pod_url is not None and len(booking.z_pod_url) > 0) or (
                    booking.z_pod_signed_url is not None
                    and len(booking.z_pod_signed_url) > 0
                ):
                    worksheet.write(row, col + 26, "Y")
                else:
                    worksheet.write(row, col + 26, "")

                worksheet.write(row, col + 27, booking_line.e_qty_awaiting_inventory)
                worksheet.write(row, col + 28, booking_line.e_qty_collected)
                worksheet.write(row, col + 29, booking_line.e_qty_scanned_fp)
                worksheet.write(row, col + 30, booking_line.e_qty_scanned_depot)
                worksheet.write(row, col + 31, booking_line.e_qty_delivered)
                worksheet.write(row, col + 32, booking_line.e_qty_damaged)
                worksheet.write(row, col + 33, booking_line.e_qty_returned)
                worksheet.write(row, col + 34, booking_line.e_qty_shortages)
                worksheet.write(row, col + 35, booking_line.e_qty_adjusted_delivered)
                worksheet.write(row, col + 36, booking.b_booking_project)
                worksheet.write(
                    row,
                    col + 37,
                    convert_to_AU_SYDNEY_tz(booking.b_project_due_date),
                    date_format,
                )

                if booking_line.e_qty is not None:
                    e_qty_total = e_qty_total + booking_line.e_qty

                if booking_line.e_qty_scanned_fp is not None:
                    e_qty_scanned_fp_total = (
                        e_qty_scanned_fp_total + booking_line.e_qty_scanned_fp
                    )

                worksheet.write(row, col + 38, booking.b_bookingID_Visual)

                row += 1

        worksheet.write(row, col + 18, e_qty_total)
        worksheet.write(row, col + 30, e_qty_scanned_fp_total)

        workbook.close()
        shutil.move(filename, local_filepath + filename)
        logger.info("#385 Finished - `Booking Lines` XLS")
    elif xls_type == "BookingsWithGaps":
        logger.info(f"#370 Get started to build `BookingsWithGaps` XLS")
        worksheet.set_column(0, 27, width=25)
        if show_field_name:
            worksheet.write("A1", "b_dateBookedDate(Date)", bold)
            worksheet.write("B1", "b_dateBookedDate(Time)", bold)
            worksheet.write(
                "C1", "fp_received_date_time/b_given_to_transport_date_time", bold
            )
            worksheet.write("D1", "pu_Address_State", bold)
            worksheet.write("E1", "business_group", bold)
            worksheet.write("F1", "deToCompanyName", bold)
            worksheet.write("G1", "de_To_Address_Suburb", bold)
            worksheet.write("H1", "de_To_Address_State", bold)
            worksheet.write("I1", "de_To_Address_PostalCode", bold)
            worksheet.write("J1", "b_client_sales_inv_num", bold)
            worksheet.write("K1", "b_client_order_num", bold)
            worksheet.write("L1", "vx_freight_provider", bold)
            worksheet.write("M1", "v_FPBookingNumber", bold)
            worksheet.write("N1", "b_status", bold)
            worksheet.write("O1", "Total Qty", bold)
            worksheet.write("P1", "Total Scanned Qty", bold)
            worksheet.write("Q1", "Booked to Scanned Variance", bold)
            worksheet.write("R1", "b_fp_qty_delivered", bold)
            worksheet.write("S1", "dme_status_detail", bold)
            worksheet.write("T1", "dme_status_action", bold)
            worksheet.write("U1", "b_booking_Notes", bold)
            worksheet.write("V1", "s_21_Actual_Delivery_TimeStamp", bold)
            worksheet.write("W1", "zc_pod_or_no_pod", bold)
            worksheet.write("X1", "z_pod_url", bold)
            worksheet.write("Y1", "z_pod_signed_url", bold)
            worksheet.write("Z1", "delivery_kpi_days", bold)
            worksheet.write("AA1", "delivery_days_from_booked", bold)
            worksheet.write("AB1", "delivery_actual_kpi_days", bold)
            worksheet.write("AC1", "z_calculated_ETA", bold)
            worksheet.write("AD1", "fp_store_event_date", bold)
            worksheet.write("AE1", "fp_store_event_time", bold)
            worksheet.write("AE1", "fp_store_event_desc", bold)
            worksheet.write("AF1", "client_item_reference", bold)
            worksheet.write("AG1", "Gaps", bold)
            worksheet.write("AH1", "b_bookingID_Visual", bold)

            worksheet.write("A2", "Booked Date", bold)
            worksheet.write("B2", "Booked Time", bold)
            worksheet.write("C2", "Given to / Received by Transport", bold)
            worksheet.write("D2", "From State", bold)
            worksheet.write("E2", "To Entity Group Name", bold)
            worksheet.write("F2", "To Entity", bold)
            worksheet.write("G2", "To Suburb", bold)
            worksheet.write("H2", "To State", bold)
            worksheet.write("I2", "To Postal Code", bold)
            worksheet.write("J2", "Client Sales Invoice", bold)
            worksheet.write("K2", "Client Order Number", bold)
            worksheet.write("L2", "Freight Provider", bold)
            worksheet.write("M2", "Consignment No", bold)
            worksheet.write("N2", "Status", bold)
            worksheet.write("O2", "Total Qty", bold)
            worksheet.write("P2", "Total Scanned Qty", bold)
            worksheet.write("Q2", "Booked to Scanned Variance", bold)
            worksheet.write("R2", "Total Delivered", bold)
            worksheet.write("S2", "Status Detail", bold)
            worksheet.write("T2", "Status Action", bold)
            worksheet.write("U2", "Status History Note", bold)
            worksheet.write("V2", "Actual Delivery", bold)
            worksheet.write("W2", "POD?", bold)
            worksheet.write("X2", "POD LINK", bold)
            worksheet.write("Y2", "POD Signed on Glass Link", bold)
            worksheet.write("Z2", "Target Delivery KPI (Days)", bold)
            worksheet.write("AA2", "Delivery Days from Booked", bold)
            worksheet.write("AB2", "Actual Delivery KPI (Days)", bold)
            worksheet.write("AC2", "Calculated ETA", bold)
            worksheet.write("AD2", "1st Contact For Delivery Booking Date", bold)
            worksheet.write("AE2", "1st Contact For Delivery Booking Time", bold)
            worksheet.write("AF2", "FP Store Activity Description", bold)
            worksheet.write("AG2", "Gaps", bold)
            worksheet.write("AH2", "Booking ID", bold)

            row = 2
        else:
            worksheet.write("A1", "Booked Date", bold)
            worksheet.write("B1", "Booked Time", bold)
            worksheet.write("C1", "Given to / Received by Transport", bold)
            worksheet.write("D1", "From State", bold)
            worksheet.write("E1", "To Entity Group Name", bold)
            worksheet.write("F1", "To Entity", bold)
            worksheet.write("G1", "To Suburb", bold)
            worksheet.write("H1", "To State", bold)
            worksheet.write("I1", "To Postal Code", bold)
            worksheet.write("J1", "Client Sales Invoice", bold)
            worksheet.write("K1", "Client Order Number", bold)
            worksheet.write("L1", "Freight Provider", bold)
            worksheet.write("M1", "Consignment No", bold)
            worksheet.write("N1", "Status", bold)
            worksheet.write("O1", "Total Qty", bold)
            worksheet.write("P1", "Total Scanned Qty", bold)
            worksheet.write("Q1", "Booked to Scanned Variance", bold)
            worksheet.write("R1", "Total Delivered", bold)
            worksheet.write("S1", "Status Detail", bold)
            worksheet.write("T1", "Status Action", bold)
            worksheet.write("U1", "Status History Note", bold)
            worksheet.write("V1", "Actual Delivery", bold)
            worksheet.write("W1", "POD?", bold)
            worksheet.write("X1", "POD LINK", bold)
            worksheet.write("Y1", "POD Signed on Glass Link", bold)
            worksheet.write("Z1", "Target Delivery KPI (Days)", bold)
            worksheet.write("AA1", "Delivery Days from Booked", bold)
            worksheet.write("AB1", "Actual Delivery KPI (Days)", bold)
            worksheet.write("AC1", "Calculated ETA", bold)
            worksheet.write("AD1", "1st Contact For Delivery Booking Date", bold)
            worksheet.write("AE1", "1st Contact For Delivery Booking Time", bold)
            worksheet.write("AF1", "FP Store Activity Description", bold)
            worksheet.write("AG1", "Gaps", bold)
            worksheet.write("AH1", "Booking ID", bold)

            row = 1

        logger.info(f"#371 Total cnt: {len(bookings)}")
        for booking_ind, booking in enumerate(bookings):
            if booking_ind % 500 == 0:
                logger.info(f"#372 Current index: {booking_ind}")

            booking_lines = Booking_lines.objects.only(
                "e_qty", "e_qty_scanned_fp", "pk_lines_id", "client_item_reference"
            ).filter(fk_booking_id=booking.pk_booking_id)
            e_qty_total = 0
            e_qty_scanned_fp_total = 0
            gaps = ""

            for booking_line in booking_lines:
                if booking_line.e_qty is not None:
                    e_qty_total = e_qty_total + booking_line.e_qty

                if booking_line.e_qty_scanned_fp is not None:
                    e_qty_scanned_fp_total = (
                        e_qty_scanned_fp_total + booking_line.e_qty_scanned_fp
                    )

                if booking_line.client_item_reference is not None:
                    if len(gaps) == 0:
                        gaps = gaps + booking_line.client_item_reference
                    else:
                        gaps = gaps + ", " + booking_line.client_item_reference

            if booking.b_dateBookedDate and booking.b_dateBookedDate:
                worksheet.write_datetime(
                    row,
                    col + 0,
                    convert_to_AU_SYDNEY_tz(booking.b_dateBookedDate).date(),
                    date_format,
                )
                worksheet.write_datetime(
                    row,
                    col + 1,
                    convert_to_AU_SYDNEY_tz(booking.b_dateBookedDate),
                    time_format,
                )

            if booking.fp_received_date_time:
                worksheet.write_datetime(
                    row,
                    col + 2,
                    convert_to_AU_SYDNEY_tz(booking.fp_received_date_time),
                    date_format,
                )
            elif booking.b_given_to_transport_date_time:
                worksheet.write_datetime(
                    row,
                    col + 2,
                    convert_to_AU_SYDNEY_tz(booking.b_given_to_transport_date_time),
                    date_format,
                )

            worksheet.write(row, col + 3, booking.pu_Address_State)

            customer_group_name = ""
            customer_groups = Dme_utl_client_customer_group.objects.all()
            for customer_group in customer_groups:
                if (
                    booking.deToCompanyName
                    and customer_group.name_lookup
                    and customer_group.name_lookup.lower()
                    in booking.deToCompanyName.lower()
                ):
                    customer_group_name = customer_group.group_name
            worksheet.write(row, col + 4, customer_group_name)

            worksheet.write(row, col + 5, booking.deToCompanyName)
            worksheet.write(row, col + 6, booking.de_To_Address_Suburb)
            worksheet.write(row, col + 7, booking.de_To_Address_State)
            worksheet.write(row, col + 8, booking.de_To_Address_PostalCode)
            worksheet.write(row, col + 9, booking.b_client_sales_inv_num)
            worksheet.write(row, col + 10, booking.b_client_order_num)
            worksheet.write(row, col + 11, booking.vx_freight_provider)
            worksheet.write(row, col + 12, booking.v_FPBookingNumber)
            worksheet.write(row, col + 13, booking.b_status)
            worksheet.write(row, col + 14, e_qty_total)
            worksheet.write(row, col + 15, e_qty_scanned_fp_total)
            worksheet.write(row, col + 16, e_qty_total - e_qty_scanned_fp_total)
            worksheet.write(row, col + 17, booking.b_fp_qty_delivered)
            worksheet.write(row, col + 18, booking.dme_status_detail)
            worksheet.write(row, col + 19, booking.dme_status_action)
            worksheet.write(row, col + 20, booking.b_booking_Notes)

            if (
                booking.s_21_Actual_Delivery_TimeStamp
                and booking.s_21_Actual_Delivery_TimeStamp
            ):
                worksheet.write_datetime(
                    row,
                    col + 21,
                    convert_to_AU_SYDNEY_tz(booking.s_21_Actual_Delivery_TimeStamp),
                    date_format,
                )

            if (booking.z_pod_url is not None and len(booking.z_pod_url) > 0) or (
                booking.z_pod_signed_url is not None
                and len(booking.z_pod_signed_url) > 0
            ):
                worksheet.write(row, col + 22, "Y")
            else:
                worksheet.write(row, col + 22, "")

            if settings.ENV == "dev":
                if booking.z_pod_url is not None and len(booking.z_pod_url) > 0:
                    worksheet.write_url(
                        row,
                        col + 23,
                        "http://3.105.62.128/static/imgs/" + booking.z_pod_url,
                        string=booking.z_pod_url,
                    )

                if (
                    booking.z_pod_signed_url is not None
                    and len(booking.z_pod_signed_url) > 0
                ):
                    worksheet.write_url(
                        row,
                        col + 24,
                        "http://3.105.62.128/static/imgs/" + booking.z_pod_signed_url,
                        string=booking.z_pod_signed_url,
                    )
            elif settings.ENV == "prod":
                if booking.z_pod_url is not None and len(booking.z_pod_url) > 0:
                    worksheet.write_url(
                        row,
                        col + 23,
                        settings.S3_URL + "/imgs/" + booking.z_pod_url,
                        string=booking.z_pod_url,
                    )

                if (
                    booking.z_pod_signed_url is not None
                    and len(booking.z_pod_signed_url) > 0
                ):
                    worksheet.write_url(
                        row,
                        col + 24,
                        settings.S3_URL + "/imgs/" + booking.z_pod_signed_url,
                        string=booking.z_pod_signed_url,
                    )

            worksheet.write(row, col + 25, booking.delivery_kpi_days)

            if (
                booking.b_status is not None
                and booking.b_status == "Delivered"
                and booking.s_21_Actual_Delivery_TimeStamp is not None
                and booking.b_dateBookedDate is not None
            ):
                worksheet.write(
                    row,
                    col + 26,
                    (
                        booking.s_21_Actual_Delivery_TimeStamp.date()
                        - booking.b_dateBookedDate.date()
                    ).days,
                )
                worksheet.write(
                    row,
                    col + 27,
                    booking.delivery_kpi_days
                    - (
                        booking.s_21_Actual_Delivery_TimeStamp.date()
                        - booking.b_dateBookedDate.date()
                    ).days,
                )

            if booking.z_calculated_ETA:
                worksheet.write_datetime(
                    row,
                    col + 28,
                    convert_to_AU_SYDNEY_tz(booking.z_calculated_ETA),
                    date_format,
                )

            if booking.fp_store_event_date:
                worksheet.write_datetime(
                    row,
                    col + 29,
                    convert_to_AU_SYDNEY_tz(booking.fp_store_event_date),
                    date_format,
                )

            if booking.fp_store_event_time:
                worksheet.write_datetime(
                    row,
                    col + 30,
                    convert_to_AU_SYDNEY_tz(booking.fp_store_event_time, "time"),
                    time_format,
                )

            worksheet.write(row, col + 31, booking.fp_store_event_desc)
            worksheet.write(row, col + 32, gaps)
            worksheet.write(row, col + 33, booking.b_bookingID_Visual)

            row += 1

        workbook.close()
        shutil.move(filename, local_filepath + filename)
        logger.info("#375 Finished - `BookingsWithGaps` XLS")
    elif xls_type == "DMEBookingsWithGaps":
        logger.info(f"#370 Get started to build `BookingsWithGaps` XLS")
        worksheet.set_column(0, 27, width=25)
        if show_field_name:
            worksheet.write("A1", "b_bookingID_Visual", bold)
            worksheet.write("B1", "b_client_name", bold)
            worksheet.write("C1", "b_client_name_sub", bold)
            worksheet.write("D1", "b_dateBookedDate(Date)", bold)
            worksheet.write("E1", "b_dateBookedDate(Time)", bold)
            worksheet.write(
                "F1", "fp_received_date_time/b_given_to_transport_date_time", bold
            )
            worksheet.write("G1", "pu_Address_State", bold)
            worksheet.write("H1", "business_group", bold)
            worksheet.write("I1", "deToCompanyName", bold)
            worksheet.write("J1", "de_To_Address_Suburb", bold)
            worksheet.write("K1", "de_To_Address_State", bold)
            worksheet.write("L1", "de_To_Address_PostalCode", bold)
            worksheet.write("M1", "b_client_sales_inv_num", bold)
            worksheet.write("N1", "b_client_order_num", bold)
            worksheet.write("O1", "vx_freight_provider", bold)
            worksheet.write("P1", "v_FPBookingNumber", bold)
            worksheet.write("Q1", "b_status", bold)
            worksheet.write("R1", "fp_invoice_no", bold)
            worksheet.write("S1", "inv_cost_quoted", bold)
            worksheet.write("T1", "inv_cost_actual", bold)
            worksheet.write("U1", "inv_sell_quoted", bold)
            worksheet.write("V1", "inv_sell_actual", bold)
            worksheet.write("W1", "dme_status_linked_reference_from_fp", bold)
            worksheet.write("X1", "inv_billing_status", bold)
            worksheet.write("Y1", "inv_billing_status_note", bold)
            worksheet.write("Z1", "Total Qty", bold)
            worksheet.write("AA1", "Total Scanned Qty", bold)
            worksheet.write("AB1", "Booked to Scanned Variance", bold)
            worksheet.write("AC1", "b_fp_qty_delivered", bold)
            worksheet.write("AD1", "dme_status_detail", bold)
            worksheet.write("AE1", "dme_status_action", bold)
            worksheet.write("AF1", "b_booking_Notes", bold)
            worksheet.write("AG1", "s_21_Actual_Delivery_TimeStamp", bold)
            worksheet.write("AH1", "zc_pod_or_no_pod", bold)
            worksheet.write("AI1", "z_pod_url", bold)
            worksheet.write("AJ1", "z_pod_signed_url", bold)
            worksheet.write("AK1", "delivery_kpi_days", bold)
            worksheet.write("AL1", "delivery_days_from_booked", bold)
            worksheet.write("AM1", "delivery_actual_kpi_days", bold)
            worksheet.write("AN1", "z_calculated_ETA", bold)
            worksheet.write("AO1", "fp_store_event_date", bold)
            worksheet.write("AP1", "fp_store_event_time", bold)
            worksheet.write("AQ1", "fp_store_event_desc", bold)
            worksheet.write("AR1", "client_item_reference", bold)

            worksheet.write("A2", "Booking ID", bold)
            worksheet.write("B2", "Client Name", bold)
            worksheet.write("C2", "Sub Client Name", bold)
            worksheet.write("D2", "Booked Date", bold)
            worksheet.write("E2", "Booked Time", bold)
            worksheet.write("F2", "Given to / Received by Transport", bold)
            worksheet.write("G2", "From State", bold)
            worksheet.write("H2", "To Entity Group Name", bold)
            worksheet.write("I2", "To Entity", bold)
            worksheet.write("J2", "To Suburb", bold)
            worksheet.write("K2", "To State", bold)
            worksheet.write("L2", "To Postal Code", bold)
            worksheet.write("M2", "Client Sales Invoice", bold)
            worksheet.write("N2", "Client Order Number", bold)
            worksheet.write("O2", "Freight Provider", bold)
            worksheet.write("P2", "Consignment No", bold)
            worksheet.write("Q2", "Status", bold)
            worksheet.write("R2", "FP Invoice No", bold)
            worksheet.write("S2", "Quoted Cost", bold)
            worksheet.write("T2", "Actual Cost", bold)
            worksheet.write("U2", "Quoted Sell", bold)
            worksheet.write("V2", "Actual Sell", bold)
            worksheet.write("W2", "Linked Reference", bold)
            worksheet.write("X2", "Invoice Billing Status", bold)
            worksheet.write("Y2", "Invoice Billing Status Note", bold)
            worksheet.write("Z2", "Total Qty", bold)
            worksheet.write("AA2", "Total Scanned Qty", bold)
            worksheet.write("AB2", "Booked to Scanned Variance", bold)
            worksheet.write("AC2", "Total Delivered", bold)
            worksheet.write("AD2", "Status Detail", bold)
            worksheet.write("AE2", "Status Action", bold)
            worksheet.write("AF2", "Status History Note", bold)
            worksheet.write("AG2", "Actual Delivery", bold)
            worksheet.write("AH2", "POD?", bold)
            worksheet.write("AI2", "POD LINK", bold)
            worksheet.write("AJ2", "POD Signed on Glass Link", bold)
            worksheet.write("AK2", "Target Delivery KPI (Days)", bold)
            worksheet.write("AL2", "Delivery Days from Booked", bold)
            worksheet.write("AM2", "Actual Delivery KPI (Days)", bold)
            worksheet.write("AN2", "Calculated ETA", bold)
            worksheet.write("AO2", "1st Contact For Delivery Booking Date", bold)
            worksheet.write("AP2", "1st Contact For Delivery Booking Time", bold)
            worksheet.write("AQ2", "FP Store Activity Description", bold)
            worksheet.write("AR2", "Gaps", bold)

            row = 2
        else:
            worksheet.write("A1", "Booking ID", bold)
            worksheet.write("B1", "Client Name", bold)
            worksheet.write("C1", "Sub Client Name", bold)
            worksheet.write("D1", "Booked Date", bold)
            worksheet.write("E1", "Booked Time", bold)
            worksheet.write("F1", "Given to / Received by Transport", bold)
            worksheet.write("G1", "From State", bold)
            worksheet.write("H1", "To Entity Group Name", bold)
            worksheet.write("I1", "To Entity", bold)
            worksheet.write("J1", "To Suburb", bold)
            worksheet.write("K1", "To State", bold)
            worksheet.write("L1", "To Postal Code", bold)
            worksheet.write("M1", "Client Sales Invoice", bold)
            worksheet.write("N1", "Client Order Number", bold)
            worksheet.write("O1", "Freight Provider", bold)
            worksheet.write("P1", "Consignment No", bold)
            worksheet.write("Q1", "Status", bold)
            worksheet.write("R1", "FP Invoice No", bold)
            worksheet.write("S1", "Quoted Cost", bold)
            worksheet.write("T1", "Actual Cost", bold)
            worksheet.write("U1", "Quoted Sell", bold)
            worksheet.write("V1", "Actual Sell", bold)
            worksheet.write("W1", "Linked Reference", bold)
            worksheet.write("X1", "Invoice Billing Status", bold)
            worksheet.write("Y1", "Invoice Billing Status Note", bold)
            worksheet.write("Z1", "Total Qty", bold)
            worksheet.write("AA1", "Total Scanned Qty", bold)
            worksheet.write("AB1", "Booked to Scanned Variance", bold)
            worksheet.write("AC1", "Total Delivered", bold)
            worksheet.write("AD1", "Status Detail", bold)
            worksheet.write("AE1", "Status Action", bold)
            worksheet.write("AF1", "Status History Note", bold)
            worksheet.write("AG1", "Actual Delivery", bold)
            worksheet.write("AH1", "POD?", bold)
            worksheet.write("AI1", "POD LINK", bold)
            worksheet.write("AJ1", "POD Signed on Glass Link", bold)
            worksheet.write("AK1", "Target Delivery KPI (Days)", bold)
            worksheet.write("AL1", "Delivery Days from Booked", bold)
            worksheet.write("AM1", "Actual Delivery KPI (Days)", bold)
            worksheet.write("AN1", "Calculated ETA", bold)
            worksheet.write("AO1", "1st Contact For Delivery Booking Date", bold)
            worksheet.write("AP1", "1st Contact For Delivery Booking Time", bold)
            worksheet.write("AQ1", "FP Store Activity Description", bold)
            worksheet.write("AR1", "Gaps", bold)

            row = 1

        logger.info(f"#371 Total cnt: {len(bookings)}")
        for booking_ind, booking in enumerate(bookings):
            if booking_ind % 500 == 0:
                logger.info(f"#372 Current index: {booking_ind}")

            booking_lines = Booking_lines.objects.only(
                "e_qty", "e_qty_scanned_fp", "pk_lines_id", "client_item_reference"
            ).filter(fk_booking_id=booking.pk_booking_id)
            e_qty_total = 0
            e_qty_scanned_fp_total = 0
            gaps = ""

            for booking_line in booking_lines:
                if booking_line.e_qty is not None:
                    e_qty_total = e_qty_total + booking_line.e_qty

                if booking_line.e_qty_scanned_fp is not None:
                    e_qty_scanned_fp_total = (
                        e_qty_scanned_fp_total + booking_line.e_qty_scanned_fp
                    )

                if booking_line.client_item_reference is not None:
                    if len(gaps) == 0:
                        gaps = gaps + booking_line.client_item_reference
                    else:
                        gaps = gaps + ", " + booking_line.client_item_reference

            worksheet.write(row, col + 0, booking.b_bookingID_Visual)
            worksheet.write(row, col + 1, booking.b_client_name)
            worksheet.write(row, col + 2, booking.b_client_name_sub)

            if booking.b_dateBookedDate and booking.b_dateBookedDate:
                worksheet.write_datetime(
                    row,
                    col + 3,
                    convert_to_AU_SYDNEY_tz(booking.b_dateBookedDate).date(),
                    date_format,
                )
                worksheet.write_datetime(
                    row,
                    col + 4,
                    convert_to_AU_SYDNEY_tz(booking.b_dateBookedDate),
                    time_format,
                )

            if booking.fp_received_date_time:
                worksheet.write_datetime(
                    row,
                    col + 5,
                    convert_to_AU_SYDNEY_tz(booking.fp_received_date_time),
                    date_format,
                )
            elif booking.b_given_to_transport_date_time:
                worksheet.write_datetime(
                    row,
                    col + 5,
                    convert_to_AU_SYDNEY_tz(booking.b_given_to_transport_date_time),
                    date_format,
                )

            worksheet.write(row, col + 6, booking.pu_Address_State)

            customer_group_name = ""
            customer_groups = Dme_utl_client_customer_group.objects.all()
            for customer_group in customer_groups:
                if (
                    booking.deToCompanyName
                    and customer_group.name_lookup
                    and customer_group.name_lookup.lower()
                    in booking.deToCompanyName.lower()
                ):
                    customer_group_name = customer_group.group_name
            worksheet.write(row, col + 7, customer_group_name)

            worksheet.write(row, col + 8, booking.deToCompanyName)
            worksheet.write(row, col + 9, booking.de_To_Address_Suburb)
            worksheet.write(row, col + 10, booking.de_To_Address_State)
            worksheet.write(row, col + 11, booking.de_To_Address_PostalCode)
            worksheet.write(row, col + 12, booking.b_client_sales_inv_num)
            worksheet.write(row, col + 13, booking.b_client_order_num)
            worksheet.write(row, col + 14, booking.vx_freight_provider)
            worksheet.write(row, col + 15, booking.v_FPBookingNumber)
            worksheet.write(row, col + 16, booking.b_status)

            worksheet.write(row, col + 17, booking.fp_invoice_no)
            worksheet.write(row, col + 18, booking.inv_cost_quoted)
            worksheet.write(row, col + 19, booking.inv_cost_actual)
            worksheet.write(row, col + 20, booking.inv_sell_quoted)
            worksheet.write(row, col + 21, booking.inv_sell_actual)
            worksheet.write(row, col + 22, booking.dme_status_linked_reference_from_fp)
            worksheet.write(row, col + 23, booking.inv_billing_status)
            worksheet.write(row, col + 24, booking.inv_billing_status_note)

            worksheet.write(row, col + 25, e_qty_total)
            worksheet.write(row, col + 26, e_qty_scanned_fp_total)
            worksheet.write(row, col + 27, e_qty_total - e_qty_scanned_fp_total)
            worksheet.write(row, col + 28, booking.b_fp_qty_delivered)
            worksheet.write(row, col + 29, booking.dme_status_detail)
            worksheet.write(row, col + 30, booking.dme_status_action)
            worksheet.write(row, col + 31, booking.b_booking_Notes)

            if (
                booking.s_21_Actual_Delivery_TimeStamp
                and booking.s_21_Actual_Delivery_TimeStamp
            ):
                worksheet.write_datetime(
                    row,
                    col + 32,
                    convert_to_AU_SYDNEY_tz(booking.s_21_Actual_Delivery_TimeStamp),
                    date_format,
                )

            if (booking.z_pod_url is not None and len(booking.z_pod_url) > 0) or (
                booking.z_pod_signed_url is not None
                and len(booking.z_pod_signed_url) > 0
            ):
                worksheet.write(row, col + 33, "Y")
            else:
                worksheet.write(row, col + 33, "")

            if settings.ENV == "dev":
                if booking.z_pod_url is not None and len(booking.z_pod_url) > 0:
                    worksheet.write_url(
                        row,
                        col + 34,
                        "http://3.105.62.128/static/imgs/" + booking.z_pod_url,
                        string=booking.z_pod_url,
                    )

                if (
                    booking.z_pod_signed_url is not None
                    and len(booking.z_pod_signed_url) > 0
                ):
                    worksheet.write_url(
                        row,
                        col + 35,
                        "http://3.105.62.128/static/imgs/" + booking.z_pod_signed_url,
                        string=booking.z_pod_signed_url,
                    )
            elif settings.ENV == "prod":
                if booking.z_pod_url is not None and len(booking.z_pod_url) > 0:
                    worksheet.write_url(
                        row,
                        col + 34,
                        settings.S3_URL + "/imgs/" + booking.z_pod_url,
                        string=booking.z_pod_url,
                    )

                if (
                    booking.z_pod_signed_url is not None
                    and len(booking.z_pod_signed_url) > 0
                ):
                    worksheet.write_url(
                        row,
                        col + 35,
                        settings.S3_URL + "/imgs/" + booking.z_pod_signed_url,
                        string=booking.z_pod_signed_url,
                    )

            worksheet.write(row, col + 36, booking.delivery_kpi_days)

            if (
                booking.b_status is not None
                and booking.b_status == "Delivered"
                and booking.s_21_Actual_Delivery_TimeStamp is not None
                and booking.b_dateBookedDate is not None
            ):
                worksheet.write(
                    row,
                    col + 37,
                    (
                        booking.s_21_Actual_Delivery_TimeStamp.date()
                        - booking.b_dateBookedDate.date()
                    ).days,
                )
                worksheet.write(
                    row,
                    col + 38,
                    booking.delivery_kpi_days
                    - (
                        booking.s_21_Actual_Delivery_TimeStamp.date()
                        - booking.b_dateBookedDate.date()
                    ).days,
                )

            if booking.z_calculated_ETA:
                worksheet.write_datetime(
                    row,
                    col + 39,
                    convert_to_AU_SYDNEY_tz(booking.z_calculated_ETA),
                    date_format,
                )

            if booking.fp_store_event_date:
                worksheet.write_datetime(
                    row,
                    col + 40,
                    convert_to_AU_SYDNEY_tz(booking.fp_store_event_date),
                    date_format,
                )

            if booking.fp_store_event_time:
                worksheet.write_datetime(
                    row,
                    col + 41,
                    convert_to_AU_SYDNEY_tz(booking.fp_store_event_time, "time"),
                    time_format,
                )

            worksheet.write(row, col + 42, booking.fp_store_event_desc)
            worksheet.write(row, col + 43, gaps)

            row += 1

        workbook.close()
        shutil.move(filename, local_filepath + filename)
        logger.info("#375 Finished - `BookingsWithGaps` XLS")
    elif xls_type == "Whse":
        from api.fp_apis.utils import get_etd_in_hour
        from api.utils import get_sydney_now_time, get_utc_now_time

        logger.info("#360 Get started to build `Whse` XLS")
        sydney_now = get_sydney_now_time("datetime")
        utc_now = get_utc_now_time("datetime")

        for index in range(4):
            # 1 Booked sheet - just show booked that are more than 1 day old (sort by oldest booked date to newest booked date)
            if index == 0:
                worksheet = workbook.add_worksheet("Booked")
                booked_bookings = bookings.filter(b_status="Booked")

                filtered_bookings = []
                for booking in booked_bookings:
                    if (
                        booking.b_dateBookedDate
                        and (utc_now - booking.b_dateBookedDate).days > 1
                    ):
                        filtered_bookings.append(booking)
            # 2 "In Transit" with these statuses (In Transit, On Board for Delivery, Scanned into depot (Sort by ETA date/time)
            elif index == 1:
                worksheet = workbook.add_worksheet("In Transit")
                filtered_bookings = bookings.filter(
                    b_status__in=[
                        "In Transit",
                        "On Board for Delivery",
                        "Scanned into depot",
                    ]
                ).order_by("s_06_Latest_Delivery_Date_TimeSet")
            # 3 "Statuses to Review" with statuses (Futile Pickup. Futile Delivery, Lost in Transit, On Hold, Partial Delivery) (Sort by Status name then ETA)
            elif index == 2:
                worksheet = workbook.add_worksheet("Statuses to Review")
                filtered_bookings = bookings.filter(
                    b_status__in=[
                        "Futile Pickup",
                        "Futile Delivery",
                        "Lost in Transit",
                        "On Hold",
                        "Partial Delivery",
                    ]
                ).order_by("b_status", "s_06_Latest_Delivery_Date_TimeSet")
            # 3 "Statuses to Review" with statuses (Futile Pickup. Futile Delivery, Lost in Transit, On Hold, Partial Delivery) (Sort by Status name then ETA)
            elif index == 3:
                worksheet = workbook.add_worksheet("Housekeeping")
                housekeeping_bookings = bookings.filter(
                    b_status__in=[
                        "Returned",
                        "Imported / Integrated",
                        "Entered",
                        "Picking",
                        "Picked",
                    ]
                ).order_by("b_status")

                filtered_bookings = []
                for booking in housekeeping_bookings:
                    if (utc_now - booking.z_CreatedTimestamp).days > 5:
                        filtered_bookings.append(booking)

            # Set the column width
            worksheet.set_column(0, 50, width=25)
            worksheet.set_column(7, 9, width=50)
            worksheet.set_column(10, 10, width=70)

            # Set the autofilter.
            worksheet.autofilter("A1:CC5000")

            fields = [
                ["b_bookingID_Visual", bold],
                ["b_dateBookedDate(Date)", bold],
                ["fp_received_date_time/b_given_to_transport_date_time", bold],
                ["delivery_kpi_days", bold],
                ["s_06_Latest_Delivery_Date_TimeSet", bold],
                ["s_06_Latest_Delivery_Date_Time_Override", bold],
                ["s_21_Actual_Delivery_TimeStamp", bold],
                ["delivery_actual_kpi_days", bold],
                ["Delivery Days Early / Late ", red_bold],
                ["delivery_days_from_booked", bold],
                ["Pickup Days Late", red_bold],
                ["Query With", bold],
                ["b_client_sales_inv_num", bold],
                ["vx_freight_provider", bold],
                ["v_FPBookingNumber", bold],
                ["b_status", bold],
                ["b_status_category", bold],
                ["dme_status_detail", bold],
                ["dme_status_action", bold],
                ["b_booking_Notes", bold],
                ["", bold],
                ["e_qty", bold],
                # ["e_qty_scanned_fp_total", bold],
                # ["Booked to Scanned Variance", bold],
                # ["b_fp_qty_delivered", bold],
                ["pu_Address_State", bold],
                ["business_group", bold],
                ["deToCompanyName", bold],
                ["de_To_Address_Suburb", bold],
                ["de_To_Address_State", bold],
                ["de_To_Address_PostalCode", bold],
                ["b_client_order_num", bold],
                ["zc_pod_or_no_pod", bold],
                ["z_pod_url", bold],
                ["z_pod_signed_url", bold],
                ["fp_store_event_date", bold],
                ["fp_store_event_desc", bold],
                ["latest DMEBookingCSNote.note", bold],
                ["latest DMEBookingCSNote.timestamp", bold],
                ["Surcharge/Providers", bold],
                ["Surcharge/Services", bold],
                ["Surcharge/Delivery ETAs", bold],
            ]
            columns = [
                ["Booking ID", bold],
                ["Booked Date", bold],
                ["Given to / Received by Transport", bold],
                ["Target Delivery KPI (Days)", bold],
                ["Calculated Delivery ETA", bold],
                ["Updated Delivery ETA", bold],
                ["Actual Delivery", bold],
                ["Actual Delivery KPI (Days)", bold],
                ["Delivery Days Early / Late", red_bold],
                ["Delivery Days from Booked", bold],
                ["Pickup Days Late", red_bold],
                ["Query With", bold],
                ["Client Sales Invoice", bold],
                ["Freight Provider", bold],
                ["Consignment No", bold],
                ["Status", bold],
                ["Status Category", bold],
                ["Status Detail", bold],
                ["Status Action", bold],
                ["Status History Note", bold],
                [
                    "Please put your Feedback / updates in the column if different to Column G, H and / or I",
                    red_bold,
                ],
                ["Qty Booked", bold],
                # ["Qty Scanned", bold],
                # ["Booked to Scanned Variance", bold],
                # ["Total Delivered", bold],
                ["From State", bold],
                ["To Entity Group Name", bold],
                ["To Entity", bold],
                ["To Suburb", bold],
                ["To State", bold],
                ["To Postal Code", bold],
                ["Client Order Number", bold],
                ["POD?", bold],
                ["POD LINK", bold],
                ["POD Signed on Glass Link", bold],
                ["1st Contact For Delivery Booking Date", bold],
                ["FP Store Activity Description", bold],
                ["The latest customer service note", bold],
                ["The latest customer service note timestamp", bold],
                ["Surcharge/Providers", bold],
                ["Surcharge/Services", bold],
                ["Surcharge/Delivery ETAs", bold],
            ]

            logger.info(f"#361 Total cnt: {len(bookings)}")
            rows = []
            for booking_ind, booking in enumerate(filtered_bookings):
                row = []

                if booking_ind % 500 == 0:
                    logger.info(f"#362 Current index: {booking_ind}")

                surcharges = Surcharge.objects.filter(booking=booking).order_by("-id")

                booking_lines = Booking_lines.objects.only(
                    "e_qty", "e_qty_scanned_fp", "pk_lines_id"
                ).filter(fk_booking_id=booking.pk_booking_id)

                e_qty_total = 0
                e_qty_scanned_fp_total = 0

                for booking_line in booking_lines:
                    if booking_line.e_qty is not None:
                        e_qty_total = e_qty_total + booking_line.e_qty

                    if booking_line.e_qty_scanned_fp is not None:
                        e_qty_scanned_fp_total = (
                            e_qty_scanned_fp_total + booking_line.e_qty_scanned_fp
                        )

                actual_delivery_days, kpi_delivery_days = None, None
                if (
                    booking.b_status == "Delivered"
                    and booking.b_dateBookedDate
                    and booking.s_21_Actual_Delivery_TimeStamp
                ):
                    # Actual delivery days = Delivered Dated - Booked Date
                    actual_delivery_days = (
                        booking.s_21_Actual_Delivery_TimeStamp
                        - booking.b_dateBookedDate
                    ).days

                    if booking.api_booking_quote:
                        # KPI Deliver Days = The number of days we get from the pricing service table or provider API the service should take - e.g. 3 days
                        etd_in_hour = get_etd_in_hour(booking.api_booking_quote)
                        etd_in_days = math.ceil(etd_in_hour / 24)
                        kpi_delivery_days = etd_in_days

                # "Booking ID"
                row.append([booking.b_bookingID_Visual, None])

                # "Booked Date"
                if booking.b_dateBookedDate and booking.b_dateBookedDate:
                    b_value = convert_to_AU_SYDNEY_tz(booking.b_dateBookedDate).date()
                    row.append([b_value, date_format])
                else:
                    b_value = None
                    row.append(["", None])

                # "Given to / Received by Transport"
                c_value = None
                if booking.fp_received_date_time:
                    value = convert_to_AU_SYDNEY_tz(
                        booking.fp_received_date_time
                    ).date()
                    c_value = value
                    row.append([value, date_format])
                elif booking.b_given_to_transport_date_time:
                    value = convert_to_AU_SYDNEY_tz(
                        booking.b_given_to_transport_date_time
                    ).date()
                    c_value = value
                    row.append([value, date_format])
                else:
                    row.append(["", None])

                # "Target Delivery KPI (Days)"
                d_value = 0
                if booking.api_booking_quote:
                    etd_in_hour = get_etd_in_hour(booking.api_booking_quote)

                    if etd_in_hour:
                        etd_in_days = math.ceil(etd_in_hour / 24)
                        d_value = etd_in_days or 1
                        row.append([etd_in_days, None])
                    else:
                        row.append(["", None])
                elif booking.vx_freight_provider == "Deliver-ME":
                    d_value = 3
                    row.append([d_value, None])
                else:
                    d_value = booking.delivery_kpi_days or 3
                    row.append([booking.delivery_kpi_days, None])

                # "Calculated Delivery ETA"
                # if booking.z_calculated_ETA:
                #     value = convert_to_AU_SYDNEY_tz(booking.z_calculated_ETA)
                #     row.append([value, date_format])
                # else:
                #     row.append(["", None])
                if booking.s_06_Latest_Delivery_Date_TimeSet:
                    e_value = convert_to_AU_SYDNEY_tz(
                        booking.s_06_Latest_Delivery_Date_TimeSet
                    )
                    row.append([e_value, date_format])
                else:
                    e_value = None
                    row.append(["", None])

                # "Updated Delivery ETA"
                if booking.s_06_Latest_Delivery_Date_Time_Override:
                    value = convert_to_AU_SYDNEY_tz(
                        booking.s_06_Latest_Delivery_Date_Time_Override
                    )
                    row.append([value, date_format])
                else:
                    value = None
                    row.append(["", None])

                # "Actual Delivery"
                if booking.s_21_Actual_Delivery_TimeStamp:
                    f_value = convert_to_AU_SYDNEY_tz(
                        booking.s_21_Actual_Delivery_TimeStamp
                    )
                    row.append([f_value, date_format])
                else:
                    f_value = None
                    row.append(["", None])

                # Actual Delivery KPI (Days)
                # if actual_delivery_days:
                #     row.append([actual_delivery_days, None])
                # else:
                #     row.append(["", None])
                if not c_value:
                    row.append(["", None])
                else:
                    if not c_value or not f_value:
                        row.append(["", None])
                    else:
                        value = busday_count(c_value, f_value.date()) - 1

                # Delivery Days Early / Late
                if booking.b_status == "Delivered":
                    # IF(NETWORKDAYS(F2;E2)>0;NETWORKDAYS(F2;E2)-1;NETWORKDAYS(F2;E2)+1);
                    if e_value and f_value:
                        between_e_and_f = busday_count(f_value.date(), e_value.date())
                        if between_e_and_f > 0:
                            value = between_e_and_f - 1
                        else:
                            value = between_e_and_f + 1

                        row.append([value, None])
                    else:
                        row.append(["", None])
                else:
                    # IF(NETWORKDAYS(TODAY();E2)>0;NETWORKDAYS(TODAY();E2)-1;NETWORKDAYS(TODAY();E2)+1)
                    sydney_now = convert_to_AU_SYDNEY_tz(datetime.now())
                    if e_value:
                        between_today_and_e = busday_count(
                            sydney_now.date(), e_value.date()
                        )
                        if between_today_and_e > 0:
                            value = between_today_and_e - 1
                        else:
                            value = between_today_and_e + 1

                        row.append([value, None])
                    else:
                        row.append(["", None])

                # Delivery Days from Booked
                # if kpi_delivery_days:
                #     row.append([kpi_delivery_days, None])
                # else:
                #     row.append(["", None])

                if b_value and f_value:
                    # IF(NETWORKDAYS(F4;B4)>0;NETWORKDAYS(F4;B4)-1;NETWORKDAYS(F4;B4)+1)))
                    between_f_and_b = busday_count(f_value.date(), b_value)
                    if between_f_and_b > 0:
                        value = between_f_and_b - 1
                    else:
                        value = between_f_and_b + 1

                    row.append([value, None])
                else:
                    row.append(["", None])

                # Pickup Days Late
                if (
                    booking.b_dateBookedDate is not None
                    and booking.b_status is not None
                    and "booked" in booking.b_status.lower()
                ):
                    pickup_days_late = (
                        booking.b_dateBookedDate.date()
                        + timedelta(days=2)
                        - sydney_now.date()
                    ).days

                    if pickup_days_late < 0:
                        cell_format = workbook.add_format({"font_color": "red"})
                        value = f"({str(abs(pickup_days_late))})"
                        row.append([value, cell_format])
                    else:
                        row.append([pickup_days_late, cell_format])
                else:
                    row.append(["", None])

                # "Query With"
                query_with = ""
                if booking.dme_status_action is None or booking.dme_status_action == "":
                    query_with = booking.vx_freight_provider

                    if e_qty_total == e_qty_scanned_fp_total:
                        query_with = "Freight Provider"
                    elif e_qty_scanned_fp_total == 0:
                        query_with = (
                            "Warehouse: Nothing sent yet, warehouse to send "
                            + str(e_qty_total)
                        )
                    elif e_qty_scanned_fp_total is not 0:
                        query_with = (
                            "Warehouse: Partial qty of "
                            + str(e_qty_total - e_qty_scanned_fp_total)
                            + " short, warehouse to send"
                        )
                else:
                    query_with = booking.dme_status_action
                row.append([query_with, None])

                # "Client Sales Invoice"
                row.append([booking.b_client_sales_inv_num, None])

                # "Freight Provider"
                row.append([booking.vx_freight_provider, None])

                # "Consignment No"
                row.append([booking.v_FPBookingNumber, None])

                # "Status"
                row.append([booking.b_status, None])
                cell_format = workbook.add_format({"text_wrap": True})

                # "Status Category"
                row.append([booking.b_status_category, None])
                cell_format = workbook.add_format({"text_wrap": True})

                # "Status Detail"
                row.append([booking.dme_status_detail, cell_format])

                # "Status Action"
                row.append([booking.dme_status_action, cell_format])

                # "Status History Note"
                row.append([booking.b_booking_Notes, cell_format])

                # "Please put your Feedback / updates in the column if different to Column G, H and / or I"
                row.append(["", cell_format])

                # "Qty Booked"
                row.append([e_qty_total, None])

                # # "Qty Scanned"
                # row.append([e_qty_scanned_fp_total, None])

                # # "Booked to Scanned Variance"
                # row.append([e_qty_total - e_qty_scanned_fp_total, None])

                # # "Total Delivered"
                # row.append([booking.b_fp_qty_delivered, None])

                # "From State"
                row.append([booking.pu_Address_State, None])

                # "To Entity Group Name"
                customer_group_name = ""
                customer_groups = Dme_utl_client_customer_group.objects.all()
                for customer_group in customer_groups:
                    if (
                        booking.deToCompanyName
                        and customer_group.name_lookup
                        and customer_group.name_lookup.lower()
                        in booking.deToCompanyName.lower()
                    ):
                        customer_group_name = customer_group.group_name
                row.append([customer_group_name, None])

                # "To Entity"
                row.append([booking.deToCompanyName, None])

                # "To Suburb"
                row.append([booking.de_To_Address_Suburb, None])

                # "To State"
                row.append([booking.de_To_Address_State, None])

                # "To Postal Code"
                row.append([booking.de_To_Address_PostalCode, None])

                # "Client Order Number"
                row.append([booking.b_client_order_num, None])

                # "POD?"
                if booking.z_pod_url or booking.z_pod_signed_url:
                    row.append(["Y", None])
                else:
                    row.append(["", None])

                # "POD LINK"
                if booking.z_pod_url:
                    url = settings.S3_URL + "/imgs/" + booking.z_pod_url
                    string = booking.z_pod_url
                else:
                    url, string = "", ""
                row.append([url, "url", string])

                # "POD Signed on Glass Link"
                if booking.z_pod_signed_url:
                    url = settings.S3_URL + "/imgs/" + booking.z_pod_signed_url
                    string = booking.z_pod_signed_url
                else:
                    url, string = "", ""
                row.append([url, "url", string])

                # "1st Contact For Delivery Booking Date"
                if booking.fp_store_event_date:
                    value = convert_to_AU_SYDNEY_tz(booking.fp_store_event_date)
                    row.append([value, date_format])
                else:
                    row.append(["", None])

                # "FP Store Activity Description"
                row.append([booking.fp_store_event_desc, None])
                rows.append(row)

                # The latest customer service notes field
                cs_notes = DMEBookingCSNote.objects.filter(booking=booking).order_by(
                    "id"
                )
                if cs_notes.exists():
                    last_cs_note = cs_notes.last().note
                    last_cs_note_timestamp = convert_to_AU_SYDNEY_tz(
                        cs_notes.last().z_createdTimeStamp
                    )
                    row.append([last_cs_note, None])
                    rows.append(row)
                    row.append([last_cs_note_timestamp, None])
                    rows.append(row)
                else:
                    row.append(["", None])
                    rows.append(row)
                    row.append(["", None])
                    rows.append(row)

                # Surcharge cols (Providers, Services, Delivery ETAs)
                providers = []
                services = []
                for surcharge in surcharges:
                    if surcharge.fp:
                        providers.append(surcharge.fp.fp_company_name)
                    if surcharge.name:
                        services.append(surcharge.name)

                row.append([", ".join(providers), None])
                rows.append(row)
                row.append([", ".join(services), None])
                rows.append(row)

                eta_de_dates = []
                for surcharge in surcharges:
                    if surcharge.eta_de_date:
                        eta_de_dates.append(
                            convert_to_AU_SYDNEY_tz(surcharge.eta_de_date).strftime(
                                "%d/%m/%Y %H:%M"
                            )
                        )
                row.append([", ".join(eta_de_dates), None])
                rows.append(row)

            # Populate cells
            row_index = 0
            if show_field_name:
                for index, field in enumerate(fields):
                    worksheet.write(row_index, index, field[0], field[1])
                row_index += 1

                for index, column in enumerate(columns):
                    worksheet.write(row_index, index, column[0], column[1])
                row_index += 1
            else:
                for index, column in enumerate(columns):
                    worksheet.write(row_index, index, column[0], column[1])
                row_index += 1

            for index, row in enumerate(rows):
                for col_index, value in enumerate(row):
                    if value[1] == date_format:
                        worksheet.write_datetime(
                            index + row_index, col_index, value[0], value[1]
                        )
                    elif value[1] == "url":
                        worksheet.write_url(
                            index + row_index, col_index, value[0], string=value[2]
                        )
                    else:
                        worksheet.write(
                            index + row_index, col_index, value[0], value[1]
                        )

        workbook.close()
        shutil.move(filename, local_filepath + filename)
        logger.info("#365 Finished - `Whse` XLS")
    elif xls_type == "pending_bookings":
        logger.info("#305 Get started to build `Pending Bookings` XLS")
        worksheet.set_column(0, 10, width=25)

        if show_field_name:
            worksheet.write("A1", "b_bookingID_Visual", bold)
            worksheet.write("B1", "b_status", bold)
            worksheet.write("C1", "b_booking_Category", bold)
            worksheet.write("D1", "line_data/gap_ra", bold)
            worksheet.write("E1", "line/e_qty", bold)
            worksheet.write("F1", "puCompany", bold)
            worksheet.write("G1", "deToCompanyName ", bold)
            worksheet.write("H1", "", bold)
            worksheet.write("I1", "", bold)

            worksheet.write("A2", "DeliverME Booking Ref", bold)
            worksheet.write("B2", "Booking Status", bold)
            worksheet.write("C2", "Booking Category", bold)
            worksheet.write("D2", "GAP/RA numbers", bold)
            worksheet.write("E2", "Quantity", bold)
            worksheet.write("F2", "Pickup Entity", bold)
            worksheet.write("G2", "Deliver to Entity", bold)
            worksheet.write("H2", "Return email with consignment sent", bold)
            worksheet.write("I2", "Booking email with consignment sent", bold)

            row = 2
        else:
            worksheet.write("A1", "DeliverME Booking Ref", bold)
            worksheet.write("B1", "Booking Status", bold)
            worksheet.write("C1", "Booking Category", bold)
            worksheet.write("D1", "GAP/RA numbers", bold)
            worksheet.write("E1", "Quantity", bold)
            worksheet.write("F1", "Pickup Entity", bold)
            worksheet.write("G1", "Deliver to Entity", bold)
            worksheet.write("H1", "Return email with consignment sent", bold)
            worksheet.write("I1", "Booking email with consignment sent", bold)

            row = 1

        line_datas_with_gapRas = get_gapRas(bookings)
        logger.info(f"#306 Total cnt: {len(bookings)}")
        for booking_ind, booking in enumerate(bookings):
            worksheet.write(row, col + 0, booking.b_bookingID_Visual)
            worksheet.write(row, col + 1, booking.b_status)
            worksheet.write(row, col + 2, booking.b_booking_Category)

            booking_gap_ras = []
            for line_data in line_datas_with_gapRas:
                if booking.pk_booking_id == line_data.fk_booking_id:
                    booking_gap_ras.append(line_data.gap_ra)

            worksheet.write(row, col + 3, ", ".join(booking_gap_ras))
            worksheet.write(row, col + 4, booking.get_total_lines_qty())
            worksheet.write(row, col + 5, booking.puCompany)
            worksheet.write(row, col + 6, booking.deToCompanyName)

            general_emails = EmailLogs.objects.filter(
                emailName="General Booking", booking_id=booking.id
            )
            return_emails = EmailLogs.objects.filter(
                emailName="Return Booking", booking_id=booking.id
            )
            worksheet.write(row, col + 7, "Yes" if general_emails else "No")
            worksheet.write(row, col + 8, "Yes" if return_emails else "No")

            row += 1

        workbook.close()
        shutil.move(filename, local_filepath + filename)
        logger.info("#308 Finished - `Pending Bookings` XLS")
    elif xls_type == "booked_bookings":
        logger.info("#310 Get started to build `Booked Bookings` XLS")
        worksheet.set_column(0, 10, width=25)

        if show_field_name:
            worksheet.write("A1", "b_bookingID_Visual", bold)
            worksheet.write("B1", "b_dateBookedDate", bold)
            worksheet.write("C1", "s_05_LatestPickUpDateTimeFinal", bold)
            worksheet.write("D1", "b_status", bold)
            worksheet.write("E1", "b_booking_Category", bold)
            worksheet.write("F1", "line_data/gap_ra", bold)
            worksheet.write("G1", "line/e_qty", bold)
            worksheet.write("H1", "puCompany", bold)
            worksheet.write("I1", "deToCompanyName ", bold)
            worksheet.write("J1", "", bold)
            worksheet.write("K1", "", bold)
            worksheet.write("L1", "CBM", bold)

            worksheet.write("A2", "DeliverME Booking Ref", bold)
            worksheet.write("B2", "Date Time Booked", bold)
            worksheet.write("C2", "Latest Pickup Date 4 Service", bold)
            worksheet.write("D2", "Booking Status", bold)
            worksheet.write("E2", "Booking Category", bold)
            worksheet.write("F2", "GAP/RA numbers", bold)
            worksheet.write("G2", "Quantity", bold)
            worksheet.write("H2", "Pickup Entity", bold)
            worksheet.write("I2", "Deliver to Entity", bold)
            worksheet.write("J2", "Return email with consignment sent", bold)
            worksheet.write("K2", "Booking email with consignment sent", bold)
            worksheet.write("L2", "CBM", bold)

            row = 2
        else:
            worksheet.write("A1", "DeliverME Booking Ref", bold)
            worksheet.write("B1", "Date Time Booked", bold)
            worksheet.write("C1", "Latest Pickup Date 4 Service", bold)
            worksheet.write("D1", "Booking Status", bold)
            worksheet.write("E1", "Booking Category", bold)
            worksheet.write("F1", "GAP/RA numbers", bold)
            worksheet.write("G1", "Quantity", bold)
            worksheet.write("H1", "Pickup Entity", bold)
            worksheet.write("I1", "Deliver to Entity", bold)
            worksheet.write("J1", "Return email with consignment sent", bold)
            worksheet.write("K1", "Booking email with consignment sent", bold)
            worksheet.write("L1", "CBM", bold)

            row = 1

        line_datas_with_gapRas = get_gapRas(bookings)
        pk_booking_ids = []
        for booking in bookings:
            pk_booking_ids.append(booking.pk_booking_id)

        scanned_lines = Booking_lines.objects.filter(
            fk_booking_id__in=pk_booking_ids, packed_status="scanned"
        )

        logger.info(f"#311 Total cnt: {len(bookings)}")
        for booking_ind, booking in enumerate(bookings):
            # Calc total CBM
            total_cbm = 0
            for line in scanned_lines:
                if line.fk_booking_id == booking.pk_booking_id:
                    total_cbm += get_cubic_meter(
                        line.e_dimLength,
                        line.e_dimWidth,
                        line.e_util_height or line.e_dimHeight,
                        line.e_dimUOM,
                        line.e_qty,
                    )

            worksheet.write(row, col + 0, booking.b_bookingID_Visual)

            if booking.b_dateBookedDate:
                worksheet.write_datetime(
                    row,
                    col + 1,
                    convert_to_AU_SYDNEY_tz(booking.b_dateBookedDate).date(),
                    date_format,
                )

            if booking.s_05_Latest_Pick_Up_Date_TimeSet:
                worksheet.write_datetime(
                    row,
                    col + 2,
                    convert_to_AU_SYDNEY_tz(
                        booking.s_05_Latest_Pick_Up_Date_TimeSet
                    ).date(),
                    date_format,
                )

            worksheet.write(row, col + 3, booking.b_status)
            worksheet.write(row, col + 4, booking.b_booking_Category)

            booking_gap_ras = []
            for line_data in line_datas_with_gapRas:
                if booking.pk_booking_id == line_data.fk_booking_id:
                    booking_gap_ras.append(line_data.gap_ra)

            worksheet.write(row, col + 5, ", ".join(booking_gap_ras))
            worksheet.write(row, col + 6, booking.get_total_lines_qty())
            worksheet.write(row, col + 7, booking.puCompany)
            worksheet.write(row, col + 8, booking.deToCompanyName)

            general_emails = EmailLogs.objects.filter(
                emailName="General Booking", booking_id=booking.id
            )
            return_emails = EmailLogs.objects.filter(
                emailName="Return Booking", booking_id=booking.id
            )
            worksheet.write(row, col + 9, "Yes" if general_emails else "No")
            worksheet.write(row, col + 10, "Yes" if return_emails else "No")
            worksheet.write(row, col + 11, round(total_cbm, 3))

            row += 1

        workbook.close()
        shutil.move(filename, local_filepath + filename)
        logger.info("#319 Finished - `Booked Bookings` XLS")
    elif xls_type == "picked_up_bookings":
        # Exclude `Futile` bookings
        pk_booking_ids = [booking.pk_booking_id for booking in bookings]
        q_filter = Q(fk_booking_id__in=pk_booking_ids) & (
            Q(status_last__icontains="futile") | Q(status_old__icontains="futile")
        )
        futile_pk_booking_ids = Dme_status_history.objects.filter(q_filter).values_list(
            "fk_booking_id", flat=True
        )
        filtered_bookings = [
            booking
            for booking in bookings
            if booking.pk_booking_id not in futile_pk_booking_ids
        ]

        logger.info("#320 Get started to build `Picked Up Bookings` XLS")
        worksheet.set_column(0, 10, width=25)

        if show_field_name:
            worksheet.write("A1", "b_bookingID_Visual", bold)
            worksheet.write("B1", "s_20_Actual_Pickup_TimeStamp", bold)
            worksheet.write("C1", "b_booking_Category", bold)
            worksheet.write("D1", "line_data/clientRefNumber", bold)
            worksheet.write("E1", "line/e_qty", bold)
            worksheet.write("F1", "puCompany", bold)
            worksheet.write("G1", "deToCompanyName ", bold)

            worksheet.write("A2", "DeliverME Booking Ref", bold)
            worksheet.write("B2", "Actual Pickup Date", bold)
            worksheet.write("C2", "Booking Category", bold)
            worksheet.write("D2", "Client Reference No's", bold)
            worksheet.write("E2", "Quantity", bold)
            worksheet.write("F2", "Pickup Entity", bold)
            worksheet.write("G2", "Deliver to Entity", bold)

            row = 2
        else:
            worksheet.write("A1", "DeliverME Booking Ref", bold)
            worksheet.write("B1", "Actual Pickup Date", bold)
            worksheet.write("C1", "Booking Category", bold)
            worksheet.write("D1", "Client Reference No's", bold)
            worksheet.write("E1", "Quantity", bold)
            worksheet.write("F1", "Pickup Entity", bold)
            worksheet.write("G1", "Deliver to Entity", bold)

            row = 1

        line_datas_with_clientRefNumbers = get_clientRefNumbers(bookings)
        logger.info(f"#321 Total cnt: {len(filtered_bookings)}")
        for booking_ind, booking in enumerate(filtered_bookings):
            worksheet.write(row, col + 0, booking.b_bookingID_Visual)

            if booking.s_20_Actual_Pickup_TimeStamp:
                worksheet.write_datetime(
                    row,
                    col + 1,
                    convert_to_AU_SYDNEY_tz(
                        booking.s_20_Actual_Pickup_TimeStamp
                    ).date(),
                    date_format,
                )

            worksheet.write(row, col + 2, booking.b_booking_Category)

            booking_clientRefNumbers = []
            for line_data in line_datas_with_clientRefNumbers:
                if booking.pk_booking_id == line_data.fk_booking_id:
                    booking_clientRefNumbers.append(line_data.clientRefNumber)

            worksheet.write(row, col + 3, ", ".join(booking_clientRefNumbers))
            worksheet.write(row, col + 4, booking.get_total_lines_qty())
            worksheet.write(row, col + 5, booking.puCompany)
            worksheet.write(row, col + 6, booking.deToCompanyName)

            row += 1

        workbook.close()
        shutil.move(filename, local_filepath + filename)
        logger.info("#329 Finished - `Picked Up Bookings` XLS")
    elif xls_type == "real_time_bookings":
        from api.fp_apis.utils import get_etd_in_hour

        logger.info("#310 Get started to build `Real Time Bookings` XLS")
        worksheet.set_column(0, 10, width=25)

        if show_field_name:
            worksheet.write("A1", "b_bookingID_Visual", bold)
            worksheet.write("B1", "v_FPBookingNumber", bold)
            worksheet.write("C1", "b_status", bold)
            worksheet.write("D1", "b_dateBookedDate", bold)
            worksheet.write("E1", "puPickUpAvailFrom_Date", bold)
            worksheet.write("F1", "vx_freight_provider", bold)
            worksheet.write("G1", "etd", bold)
            worksheet.write("H1", "s_21_Actual_Delivery_TimeStamp", bold)
            worksheet.write("I1", "delayed_days ", bold)

            worksheet.write("A2", "DME ID/Booking ID", bold)
            worksheet.write("B2", "Consignment Number", bold)
            worksheet.write("C2", "Current Status", bold)
            worksheet.write("D2", "Booked Date", bold)
            worksheet.write("E2", "Actual Collection/Pick Up Date", bold)
            worksheet.write("F2", "Service Provider Used", bold)
            worksheet.write("G2", "Service Provider ETA", bold)
            worksheet.write("H2", "Actual Delivery Completion", bold)
            worksheet.write("I2", "Number of Days Delayed", bold)

            row = 2
        else:
            worksheet.write("A1", "b_bookingID_Visual", bold)
            worksheet.write("B1", "v_FPBookingNumber", bold)
            worksheet.write("C1", "b_status", bold)
            worksheet.write("D1", "b_dateBookedDate", bold)
            worksheet.write("E1", "puPickUpAvailFrom_Date", bold)
            worksheet.write("F1", "vx_freight_provider", bold)
            worksheet.write("G1", "etd", bold)
            worksheet.write("H1", "s_21_Actual_Delivery_TimeStamp", bold)
            worksheet.write("I1", "delayed_days ", bold)

            row = 1

        pk_booking_ids = []
        for booking in bookings:
            pk_booking_ids.append(booking.pk_booking_id)

        scanned_lines = Booking_lines.objects.filter(
            fk_booking_id__in=pk_booking_ids, packed_status="scanned"
        )

        logger.info(f"#311 Total cnt: {len(bookings)}")
        for booking_ind, booking in enumerate(bookings):
            worksheet.write(row, col + 0, booking.b_bookingID_Visual)
            worksheet.write(row, col + 1, booking.v_FPBookingNumber)
            worksheet.write(row, col + 2, booking.b_status)

            if booking.b_dateBookedDate:
                worksheet.write_datetime(
                    row,
                    col + 3,
                    convert_to_AU_SYDNEY_tz(booking.b_dateBookedDate).date(),
                    date_format,
                )

            puPickUpAvailFrom_Date = booking.puPickUpAvailFrom_Date
            if puPickUpAvailFrom_Date:
                if isinstance(puPickUpAvailFrom_Date, date):
                    puPickUpAvailFrom_Date = datetime(
                        puPickUpAvailFrom_Date.year,
                        puPickUpAvailFrom_Date.month,
                        puPickUpAvailFrom_Date.day,
                    )

                puPickUpAvailFrom_Date = convert_to_AU_SYDNEY_tz(puPickUpAvailFrom_Date)

                worksheet.write_datetime(
                    row,
                    col + 4,
                    puPickUpAvailFrom_Date.date(),
                    date_format,
                )

            worksheet.write(row, col + 5, booking.vx_freight_provider)

            etd_in_days = 0
            if booking.api_booking_quote:
                # KPI Deliver Days = The number of days we get from the pricing service table or provider API the service should take - e.g. 3 days
                etd_in_hour = get_etd_in_hour(booking.api_booking_quote)
                etd_in_days = math.ceil(0 if etd_in_hour is None else etd_in_hour / 24)
                worksheet.write(row, col + 6, etd_in_days)

            Actual_Delivery_TimeStamp = booking.s_21_Actual_Delivery_TimeStamp
            if Actual_Delivery_TimeStamp:
                Actual_Delivery_TimeStamp = convert_to_AU_SYDNEY_tz(
                    Actual_Delivery_TimeStamp
                )
                worksheet.write_datetime(
                    row,
                    col + 7,
                    Actual_Delivery_TimeStamp.date(),
                    date_format,
                )

                delivery_days = Actual_Delivery_TimeStamp - puPickUpAvailFrom_Date

                if etd_in_days > 0:
                    worksheet.write(row, col + 8, delivery_days.days - etd_in_days)

            row += 1

        workbook.close()
        shutil.move(filename, local_filepath + filename)
        logger.info("#319 Finished - `Real Time Bookings` XLS")
    elif xls_type == "box":
        logger.info("#330 Get started to build `Box Bookings` XLS")
        worksheet.set_column(0, 15, width=25)

        if show_field_name:
            worksheet.write("A1", "b_bookingID_Visual", bold)
            worksheet.write("B1", "b_dateBookedDate", bold)
            worksheet.write("C1", "s_20_Actual_Pickup_TimeStamp", bold)
            worksheet.write("D1", "line_data/clientRefNumber", bold)
            worksheet.write("E1", "puCompany", bold)
            worksheet.write("F1", "pu_Address_Suburb", bold)
            worksheet.write("G1", "pu_Address_State", bold)
            worksheet.write("H1", "pu_Address_PostalCode", bold)
            worksheet.write("I1", "deToCompanyName ", bold)
            worksheet.write("J1", "de_To_Address_Suburb ", bold)
            worksheet.write("K1", "de_To_Address_State ", bold)
            worksheet.write("L1", "de_To_Address_PostalCode ", bold)

            worksheet.write("A2", "DeliverME Booking Ref", bold)
            worksheet.write("B2", "Date Time Booked", bold)
            worksheet.write("C2", "Actual Pickup Date Time", bold)
            worksheet.write("D2", "Client Reference No's", bold)
            worksheet.write("E2", "Pickup Entity", bold)
            worksheet.write("F2", "Pickup Address Suburb", bold)
            worksheet.write("G2", "Pickup Address State", bold)
            worksheet.write("H2", "Pickup Address Postal Code", bold)
            worksheet.write("I2", "Deliver to Entity", bold)
            worksheet.write("J2", "Delivery Address Suburb", bold)
            worksheet.write("K2", "Delivery Address State", bold)
            worksheet.write("L2", "Delivery Address Postal Code", bold)

            row = 2
        else:
            worksheet.write("A1", "DeliverME Booking Ref", bold)
            worksheet.write("B1", "Date Time Booked", bold)
            worksheet.write("C1", "Actual Pickup Date Time", bold)
            worksheet.write("D1", "Client Reference No's", bold)
            worksheet.write("E1", "Pickup Entity", bold)
            worksheet.write("F1", "Pickup Address Suburb", bold)
            worksheet.write("G1", "Pickup Address State", bold)
            worksheet.write("H1", "Pickup Address Postal Code", bold)
            worksheet.write("I1", "Deliver to Entity", bold)
            worksheet.write("J1", "Delivery Address Suburb", bold)
            worksheet.write("K1", "Delivery Address State", bold)
            worksheet.write("L1", "Delivery Address Postal Code", bold)

            row = 1

        line_datas_with_clientRefNumbers = get_clientRefNumbers(bookings)
        logger.info(f"#331 Total cnt: {len(bookings)}")
        for booking_ind, booking in enumerate(bookings):
            worksheet.write(row, col + 0, booking.b_bookingID_Visual)

            if booking.b_dateBookedDate:
                worksheet.write_datetime(
                    row,
                    col + 1,
                    convert_to_AU_SYDNEY_tz(booking.b_dateBookedDate).date(),
                    date_format,
                )

            if booking.s_20_Actual_Pickup_TimeStamp:
                worksheet.write_datetime(
                    row,
                    col + 2,
                    convert_to_AU_SYDNEY_tz(
                        booking.s_20_Actual_Pickup_TimeStamp
                    ).date(),
                    date_format,
                )

            booking_clientRefNumbers = []
            for line_data in line_datas_with_clientRefNumbers:
                if booking.pk_booking_id == line_data.fk_booking_id:
                    booking_clientRefNumbers.append(line_data.clientRefNumber)

            worksheet.write(row, col + 3, ", ".join(booking_clientRefNumbers))
            worksheet.write(row, col + 4, booking.puCompany)
            worksheet.write(row, col + 5, booking.pu_Address_Suburb)
            worksheet.write(row, col + 6, booking.pu_Address_State)
            worksheet.write(row, col + 7, booking.pu_Address_PostalCode)
            worksheet.write(row, col + 8, booking.deToCompanyName)
            worksheet.write(row, col + 9, booking.de_To_Address_Suburb)
            worksheet.write(row, col + 10, booking.de_To_Address_State)
            worksheet.write(row, col + 11, booking.de_To_Address_PostalCode)

            row += 1

        workbook.close()
        shutil.move(filename, local_filepath + filename)
        logger.info("#339 Finished - `Box Bookings` XLS")
    elif xls_type == "futile":
        logger.info("#340 Get started to build `Futile Bookings` XLS")
        worksheet.set_column(0, 15, width=25)

        if show_field_name:
            worksheet.write("A1", "b_bookingID_Visual", bold)
            worksheet.write("B1", "dme_status_history/event_time_stamp", bold)
            worksheet.write("C1", "b_booking_Category", bold)
            worksheet.write("D1", "line_data/gap_ra", bold)
            worksheet.write("E1", "puCompany", bold)
            worksheet.write("F1", "pu_Address_Suburb", bold)
            worksheet.write("G1", "pu_Address_State", bold)
            worksheet.write("H1", "pu_Address_PostalCode", bold)
            worksheet.write("I1", "deToCompanyName", bold)
            worksheet.write("J1", "de_To_Address_Suburb", bold)
            worksheet.write("K1", "de_To_Address_State ", bold)
            worksheet.write("L1", "de_To_Address_PostalCode", bold)
            worksheet.write("M1", "vx_futile_Booking_Notes", bold)
            worksheet.write("N1", "b_status", bold)
            worksheet.write("O1", "dme_status_history/notes", bold)

            worksheet.write("A2", "DeliverME Booking Ref", bold)
            worksheet.write("B2", "Futile Event Date", bold)
            worksheet.write("C2", "Booking Category", bold)
            worksheet.write("D2", "Gap/RA", bold)
            worksheet.write("E2", "Pickup Entity", bold)
            worksheet.write("F2", "Pickup Address Suburb", bold)
            worksheet.write("G2", "Pickup Address State", bold)
            worksheet.write("H2", "Pickup Address Postal Code", bold)
            worksheet.write("I2", "Deliver to Entity", bold)
            worksheet.write("J2", "Delivery Address Suburb", bold)
            worksheet.write("K2", "Delivery Address State", bold)
            worksheet.write("L2", "Delivery Address Postal Code", bold)
            worksheet.write("M2", "Futile Booking Notes", bold)
            worksheet.write("N2", "Current Booking State", bold)
            worksheet.write("O2", "Status Note", bold)

            row = 2
        else:
            worksheet.write("A1", "DeliverME Booking Ref", bold)
            worksheet.write("B1", "Futile Event Date", bold)
            worksheet.write("C1", "Booking Category", bold)
            worksheet.write("D1", "GAP/RA", bold)
            worksheet.write("E1", "Pickup Entity", bold)
            worksheet.write("F1", "Pickup Address Suburb", bold)
            worksheet.write("G1", "Pickup Address State", bold)
            worksheet.write("H1", "Pickup Address Postal Code", bold)
            worksheet.write("I1", "Deliver to Entity", bold)
            worksheet.write("J1", "Delivery Address Suburb", bold)
            worksheet.write("K1", "Delivery Address State", bold)
            worksheet.write("L1", "Delivery Address Postal Code", bold)
            worksheet.write("M1", "Futile Booking Notes", bold)
            worksheet.write("N1", "Current Booking State", bold)
            worksheet.write("O1", "Status Note", bold)

            row = 1

        line_datas_with_gapRas = get_gapRas(bookings)

        pk_booking_ids = []
        for booking in bookings:
            pk_booking_ids.append(booking.pk_booking_id)
        status_histories = Dme_status_history.objects.filter(
            fk_booking_id__in=pk_booking_ids, status_last__icontains="futile"
        )

        logger.info(f"#341 Total cnt: {len(bookings)}")
        for booking_ind, booking in enumerate(bookings):
            _status_history = None
            for status_history in status_histories:
                if booking.pk_booking_id == status_history.fk_booking_id:
                    _status_history = status_history
                    break

            if not _status_history:
                continue

            worksheet.write(row, col + 0, booking.b_bookingID_Visual)

            if _status_history and _status_history.event_time_stamp:
                worksheet.write_datetime(
                    row,
                    col + 1,
                    convert_to_AU_SYDNEY_tz(_status_history.event_time_stamp).date(),
                    date_format,
                )

            worksheet.write(row, col + 2, booking.b_booking_Category)

            booking_gap_ras = []
            for line_data in line_datas_with_gapRas:
                if booking.pk_booking_id == line_data.fk_booking_id:
                    booking_gap_ras.append(line_data.gap_ra)

            worksheet.write(row, col + 3, ", ".join(booking_gap_ras))
            worksheet.write(row, col + 4, booking.puCompany)
            worksheet.write(row, col + 5, booking.pu_Address_Suburb)
            worksheet.write(row, col + 6, booking.pu_Address_State)
            worksheet.write(row, col + 7, booking.pu_Address_PostalCode)
            worksheet.write(row, col + 8, booking.deToCompanyName)
            worksheet.write(row, col + 9, booking.de_To_Address_Suburb)
            worksheet.write(row, col + 10, booking.de_To_Address_State)
            worksheet.write(row, col + 11, booking.de_To_Address_PostalCode)
            worksheet.write(row, col + 12, booking.vx_futile_Booking_Notes)
            worksheet.write(row, col + 13, booking.b_status)

            if status_histories and status_histories[0].event_time_stamp:
                worksheet.write(row, col + 14, status_histories[0].notes)

            row += 1

        workbook.close()
        shutil.move(filename, local_filepath + filename)
        logger.info("#349 Finished - `Futile Bookings` XLS")
    elif xls_type == "bookings_delivered":
        logger.info("#350 Get started to build `Bookings Delivered` XLS")
        worksheet.set_column(0, 15, width=25)

        if show_field_name:
            worksheet.write("A1", "b_bookingID_Visual", bold)
            worksheet.write("B1", "line_data/gap_ra", bold)
            worksheet.write("C1", "b_status", bold)
            worksheet.write("D1", "delivery_booking", bold)
            worksheet.write("E1", "b_booking_Category", bold)
            worksheet.write("F1", "puCompany", bold)
            worksheet.write("G1", "pu_Address_Suburb", bold)
            worksheet.write("H1", "pu_Address_State", bold)
            worksheet.write("I1", "pu_Address_PostalCode", bold)
            worksheet.write("J1", "deToCompanyName", bold)
            worksheet.write("K1", "de_To_Address_Suburb", bold)
            worksheet.write("L1", "de_To_Address_State ", bold)
            worksheet.write("M1", "de_To_Address_PostalCode", bold)
            worksheet.write("N1", "b_booking_Notes", bold)
            worksheet.write("O1", "line_data/clientRefNumbers", bold)
            worksheet.write("P1", "line/e_qty", bold)
            worksheet.write("Q1", "line_data/modelNumbers", bold)
            worksheet.write("R1", "line_data/itemDescriptions", bold)

            worksheet.write("A2", "DeliverME Booking Ref", bold)
            worksheet.write("B2", "Gap/ra - from line_data", bold)
            worksheet.write("C2", "Booking Status", bold)
            worksheet.write("D2", "Actual Delivery Date", bold)
            worksheet.write("E2", "Booking Category", bold)
            worksheet.write("F2", "Pickup Entity", bold)
            worksheet.write("G2", "Pickup Address Suburb", bold)
            worksheet.write("H2", "Pickup Address State", bold)
            worksheet.write("I2", "Pickup Address Postal Code", bold)
            worksheet.write("J2", "Deliver to Entity", bold)
            worksheet.write("K2", "Delivery Address Suburb", bold)
            worksheet.write("L2", "Delivery Address State", bold)
            worksheet.write("M2", "Delivery Address Postal Code", bold)
            worksheet.write("N2", "Booking Notes", bold)
            worksheet.write("O2", "Client Reference No's", bold)
            worksheet.write("P2", "Quantity", bold)
            worksheet.write("Q2", "ModelNumbers", bold)
            worksheet.write("R2", "ItemDescriptions", bold)

            row = 2
        else:
            worksheet.write("A1", "DeliverME Booking Ref", bold)
            worksheet.write("B1", "Gap/ra - from line_data", bold)
            worksheet.write("C1", "Booking Status", bold)
            worksheet.write("D1", "Actual Delivery Date", bold)
            worksheet.write("E1", "Booking Category", bold)
            worksheet.write("F1", "Pickup Entity", bold)
            worksheet.write("G1", "Pickup Address Suburb", bold)
            worksheet.write("H1", "Pickup Address State", bold)
            worksheet.write("I1", "Pickup Address Postal Code", bold)
            worksheet.write("J1", "Deliver to Entity", bold)
            worksheet.write("K1", "Delivery Address Suburb", bold)
            worksheet.write("L1", "Delivery Address State", bold)
            worksheet.write("M1", "Delivery Address Postal Code", bold)
            worksheet.write("N1", "Booking Notes", bold)
            worksheet.write("O1", "Client Reference No's", bold)
            worksheet.write("P1", "Quantity", bold)
            worksheet.write("Q1", "ModelNumbers", bold)
            worksheet.write("R1", "ItemDescriptions", bold)

            row = 1

        logger.info(f"#351 Total cnt: {len(bookings)}")
        line_datas_with_gapRas = get_gapRas(bookings)
        line_datas_with_clientRefNumbers = get_clientRefNumbers(bookings)

        for booking_ind, booking in enumerate(bookings):
            worksheet.write(row, col + 0, booking.b_bookingID_Visual)

            booking_gap_ras = []
            for line_data in line_datas_with_gapRas:
                if booking.pk_booking_id == line_data.fk_booking_id:
                    booking_gap_ras.append(line_data.gap_ra)

            worksheet.write(row, col + 1, ", ".join(booking_gap_ras))
            worksheet.write(row, col + 2, booking.b_status)

            if booking.s_21_Actual_Delivery_TimeStamp:
                worksheet.write_datetime(
                    row,
                    col + 3,
                    convert_to_AU_SYDNEY_tz(booking.s_21_Actual_Delivery_TimeStamp),
                    date_format,
                )

            worksheet.write(row, col + 4, booking.b_booking_Category)
            worksheet.write(row, col + 5, booking.puCompany)
            worksheet.write(row, col + 6, booking.pu_Address_Suburb)
            worksheet.write(row, col + 7, booking.pu_Address_State)
            worksheet.write(row, col + 8, booking.pu_Address_PostalCode)
            worksheet.write(row, col + 9, booking.deToCompanyName)
            worksheet.write(row, col + 10, booking.de_To_Address_Suburb)
            worksheet.write(row, col + 11, booking.de_To_Address_State)
            worksheet.write(row, col + 12, booking.de_To_Address_PostalCode)
            worksheet.write(row, col + 13, booking.b_booking_Notes)

            booking_clientRefNumbers = []
            for line_data in line_datas_with_clientRefNumbers:
                if booking.pk_booking_id == line_data.fk_booking_id:
                    booking_clientRefNumbers.append(line_data.clientRefNumber)

            worksheet.write(row, col + 14, ", ".join(booking_clientRefNumbers))
            worksheet.write(row, col + 15, booking.get_total_lines_qty())

            modelNumbers = []
            itemDescriptions = []
            booking_lines_data = Booking_lines_data.objects.filter(
                fk_booking_id=booking.pk_booking_id
            )

            for booking_line_data in booking_lines_data:
                if booking_line_data.modelNumber:
                    modelNumbers.append(booking_line_data.modelNumber)

                if booking_line_data.itemDescription:
                    itemDescriptions.append(booking_line_data.itemDescription)

            worksheet.write(row, col + 16, ", ".join(modelNumbers))
            worksheet.write(row, col + 17, ", ".join(itemDescriptions))

            row += 1

        workbook.close()
        shutil.move(filename, local_filepath + filename)
        logger.info("#359 Finished - `Bookings Delivered` XLS")

    elif xls_type == "bookings_sent":
        logger.info("#310 Get started to build `Bookings Sent` XLS")
        worksheet.set_column(0, 20, width=30)

        if show_field_name:
            worksheet.write("A1", "Client Name", bold)
            worksheet.write("B1", "Warehouse Code", bold)
            worksheet.write("C1", "Delivery Entity", bold)
            worksheet.write("D1", "Consignment Number", bold)
            worksheet.write("E1", "Your Invoice No", bold)
            worksheet.write("F1", "Delivery : Street 1", bold)
            worksheet.write("G1", "Delivery : Street 2", bold)
            worksheet.write("H1", "Delivery : Suburb", bold)
            worksheet.write("I1", "Delivery : State", bold)
            worksheet.write("J1", "Delivery : Postal Code ", bold)
            worksheet.write("K1", "Actual Packed : Total Qty*", bold)
            worksheet.write("L1", "Actual Packed : Total KG*", bold)
            worksheet.write("M1", "Actual Packed : Total cbm*", bold)
            worksheet.write("N1", "Delivery : Tel", bold)
            worksheet.write("O1", "Delivery : email", bold)
            worksheet.write("P1", "Qty of Cartons in Actual Packed : Total Qty*", bold)
            worksheet.write("Q1", "Qty of Pallets in Actual Packed : Total Qty*", bold)
            worksheet.write("R1", "Send as Is Item descriptions seperated by , ", bold)
            worksheet.write("S1", "DE Inst Address and DE Inst Contact", bold)
            worksheet.write("T1", "Delivery : Address Type", bold)

            worksheet.write("A2", "Client Name", bold)
            worksheet.write("B2", "Warehouse Code", bold)
            worksheet.write("C2", "Deliver To", bold)
            worksheet.write("D2", "Consignment Number", bold)
            worksheet.write("E2", "Customer Invoice", bold)
            worksheet.write("F2", "Street 1", bold)
            worksheet.write("G2", "Street 2", bold)
            worksheet.write("H2", "Suburb", bold)
            worksheet.write("I2", "State", bold)
            worksheet.write("J2", "Postal Code ", bold)
            worksheet.write("K2", "Qty", bold)
            worksheet.write("L2", "KG", bold)
            worksheet.write("M2", "cbm", bold)
            worksheet.write("N2", "Cust Tel", bold)
            worksheet.write("O2", "Cust Email", bold)
            worksheet.write("P2", "Qty Cartons", bold)
            worksheet.write("Q2", "Qty Pallets", bold)
            worksheet.write("R2", "Items , ", bold)
            worksheet.write("S2", "Instruc & Notes", bold)
            worksheet.write("T2", "Consignment Type. Eg. Delivery", bold)

            row = 2
        else:
            worksheet.write("A1", "Client Name", bold)
            worksheet.write("B1", "Warehouse Code", bold)
            worksheet.write("C1", "Delivery Entity", bold)
            worksheet.write("D1", "Consignment Number", bold)
            worksheet.write("E1", "Your Invoice No", bold)
            worksheet.write("F1", "Delivery : Street 1", bold)
            worksheet.write("G1", "Delivery : Street 2", bold)
            worksheet.write("H1", "Delivery : Suburb", bold)
            worksheet.write("I1", "Delivery : State", bold)
            worksheet.write("J1", "Delivery : Postal Code ", bold)
            worksheet.write("K1", "Actual Packed : Total Qty*", bold)
            worksheet.write("L1", "Actual Packed : Total KG*", bold)
            worksheet.write("M1", "Actual Packed : Total cbm*", bold)
            worksheet.write("N1", "Delivery : Tel", bold)
            worksheet.write("O1", "Delivery : email", bold)
            worksheet.write("P1", "Qty of Cartons in Actual Packed : Total Qty*", bold)
            worksheet.write("Q1", "Qty of Pallets in Actual Packed : Total Qty*", bold)
            worksheet.write("R1", "Send as Is Item descriptions seperated by , ", bold)
            worksheet.write("S1", "DE Inst Address and DE Inst Contact", bold)
            worksheet.write("T1", "Delivery : Address Type", bold)

            row = 1

        pk_booking_ids = []
        for booking in bookings:
            pk_booking_ids.append(booking.pk_booking_id)

        original_lines = Booking_lines.objects.filter(
            fk_booking_id__in=pk_booking_ids, packed_status="original"
        ).only("fk_booking_id", "e_item")
        scanned_lines = Booking_lines.objects.filter(
            fk_booking_id__in=pk_booking_ids, packed_status="scanned"
        ).only(
            "fk_booking_id",
            "e_qty",
            "e_weightPerEach",
            "e_weightUOM",
            "e_1_Total_dimCubicMeter",
            "e_type_of_packaging",
        )

        logger.info(f"#311 Total cnt: {len(bookings)}")
        for booking_ind, booking in enumerate(bookings):
            total_qty = 0
            total_kgs = 0
            total_cbm = 0
            carton_cnt = 0
            pallet_cnt = 0

            for booking_line in scanned_lines:
                if booking_line.fk_booking_id == booking.pk_booking_id:
                    if booking_line.e_qty:
                        total_qty += booking_line.e_qty
                    if booking_line.e_weightPerEach and booking_line.e_weightPerEach:
                        total_kgs = (
                            _get_weight_amount(booking_line.e_weightUOM)
                            * booking_line.e_weightPerEach
                        ) * booking_line.e_qty
                    if booking_line.e_1_Total_dimCubicMeter:
                        total_cbm = (
                            booking_line.e_1_Total_dimCubicMeter * booking_line.e_qty
                        )
                    if (
                        booking_line.e_type_of_packaging
                        and booking_line.e_type_of_packaging.upper() in PALLETS
                    ):
                        pallet_cnt += booking_line.e_qty
                    if (
                        booking_line.e_type_of_packaging
                        and not booking_line.e_type_of_packaging.upper() in PALLETS
                    ):
                        carton_cnt += booking_line.e_qty

            line_descriptions = []
            for booking_line in original_lines:
                if booking_line.fk_booking_id == booking.pk_booking_id:
                    if booking_line.e_item:
                        line_descriptions.append(booking_line.e_item)

            worksheet.write(row, col + 0, booking.b_client_name)
            worksheet.write(row, col + 1, booking.b_client_warehouse_code)
            worksheet.write(row, col + 2, booking.deToCompanyName)
            worksheet.write(row, col + 3, booking.v_FPBookingNumber)
            worksheet.write(row, col + 4, booking.b_client_sales_inv_num)
            worksheet.write(row, col + 5, booking.de_To_Address_Street_1)
            worksheet.write(row, col + 6, booking.de_To_Address_Street_2)
            worksheet.write(row, col + 7, booking.de_To_Address_Suburb)
            worksheet.write(row, col + 8, booking.de_To_Address_State)
            worksheet.write(row, col + 9, booking.de_To_Address_PostalCode)
            worksheet.write(row, col + 10, total_qty)
            worksheet.write(row, col + 11, total_kgs)
            worksheet.write(row, col + 12, total_cbm)
            worksheet.write(row, col + 13, booking.de_to_Phone_Main)
            worksheet.write(row, col + 14, booking.de_Email)
            worksheet.write(row, col + 15, carton_cnt)
            worksheet.write(row, col + 16, pallet_cnt)
            worksheet.write(row, col + 17, ", ".join(line_descriptions))
            worksheet.write(
                row,
                col + 18,
                (booking.de_to_Pick_Up_Instructions_Contact or "")
                + (booking.de_to_PickUp_Instructions_Address or ""),
            )
            worksheet.write(row, col + 19, booking.de_To_AddressType)

            row += 1

        workbook.close()
        shutil.move(filename, local_filepath + filename)
        logger.info("#319 Finished - `Bookings Sent` XLS")

    elif xls_type == "booking_lines_sent":
        logger.info("#310 Get started to build `Booking Lines Sent` XLS")
        worksheet.set_column(0, 20, width=30)

        if show_field_name:
            worksheet.write("A1", "Client Name", bold)
            worksheet.write("B1", "Warehouse Code", bold)
            worksheet.write("C1", "Delivery Entity", bold)
            worksheet.write("D1", "Consignment Number", bold)
            worksheet.write("E1", "Label Code", bold)
            worksheet.write("F1", "Your Invoice No", bold)
            worksheet.write("G1", "Delivery : Street 1", bold)
            worksheet.write("H1", "Delivery : Street 2", bold)
            worksheet.write("I1", "Delivery : Suburb", bold)
            worksheet.write("J1", "Delivery : State", bold)
            worksheet.write("K1", "Delivery : Postal Code ", bold)
            worksheet.write("L1", "Actual Packed : Total Qty*", bold)
            worksheet.write("M1", "Actual Packed : Total KG*", bold)
            worksheet.write("N1", "Actual Packed : Total cbm*", bold)
            worksheet.write("O1", "Delivery : Tel", bold)
            worksheet.write("P1", "Delivery : email", bold)
            worksheet.write("Q1", "Qty of Cartons in Actual Packed : Total Qty*", bold)
            worksheet.write("R1", "Qty of Pallets in Actual Packed : Total Qty*", bold)
            worksheet.write("S1", "Send as Is Item descriptions seperated by , ", bold)
            worksheet.write("T1", "DE Inst Address and DE Inst Contact", bold)
            worksheet.write("U1", "Delivery : Address Type", bold)
            worksheet.write("V1", "e_qty", bold)
            worksheet.write("W1", "e_dimLength", bold)
            worksheet.write("X1", "e_dimWidth", bold)
            worksheet.write("Y1", "e_dimHeight", bold)
            worksheet.write("Z1", "e_weightPerEach", bold)
            worksheet.write("AA1", "Each CBM", bold)
            worksheet.write("AB1", "Item Desc", bold)
            worksheet.write("AC1", "SINV#", bold)
            worksheet.write("AD1", "BookingId", bold)

            worksheet.write("A2", "Client Name", bold)
            worksheet.write("B2", "Warehouse Code", bold)
            worksheet.write("C2", "Deliver To", bold)
            worksheet.write("D2", "Consignment Number", bold)
            worksheet.write("E2", "Label Code", bold)
            worksheet.write("F2", "Customer Invoice", bold)
            worksheet.write("G2", "Street 1", bold)
            worksheet.write("H2", "Street 2", bold)
            worksheet.write("I2", "Suburb", bold)
            worksheet.write("J2", "State", bold)
            worksheet.write("K2", "Postal Code ", bold)
            worksheet.write("L2", "Qty", bold)
            worksheet.write("M2", "KG", bold)
            worksheet.write("N2", "cbm", bold)
            worksheet.write("O2", "Cust Tel", bold)
            worksheet.write("P2", "Cust Email", bold)
            worksheet.write("Q2", "Qty Cartons", bold)
            worksheet.write("R2", "Qty Pallets", bold)
            worksheet.write("S2", "Items , ", bold)
            worksheet.write("T2", "Instruc & Notes", bold)
            worksheet.write("U2", "Consignment Type. Eg. Delivery", bold)
            worksheet.write("V2", "Qty", bold)
            worksheet.write("W2", "Length", bold)
            worksheet.write("X2", "Width", bold)
            worksheet.write("Y2", "Height", bold)
            worksheet.write("Z2", "Weight Per Each", bold)
            worksheet.write("AA2", "Each CBM", bold)
            worksheet.write("AB2", "e_item", bold)
            worksheet.write("AC2", "SINV#", bold)
            worksheet.write("AD2", "b_booking_visualID", bold)

            row = 2
        else:
            worksheet.write("A1", "Client Name", bold)
            worksheet.write("B1", "Warehouse Code", bold)
            worksheet.write("C1", "Delivery Entity", bold)
            worksheet.write("D1", "Consignment Number", bold)
            worksheet.write("E1", "Label Code", bold)
            worksheet.write("F1", "Your Invoice No", bold)
            worksheet.write("G1", "Delivery : Street 1", bold)
            worksheet.write("H1", "Delivery : Street 2", bold)
            worksheet.write("I1", "Delivery : Suburb", bold)
            worksheet.write("J1", "Delivery : State", bold)
            worksheet.write("K1", "Delivery : Postal Code ", bold)
            worksheet.write("L1", "Actual Packed : Total Qty*", bold)
            worksheet.write("M1", "Actual Packed : Total KG*", bold)
            worksheet.write("N1", "Actual Packed : Total cbm*", bold)
            worksheet.write("O1", "Delivery : Tel", bold)
            worksheet.write("P1", "Delivery : email", bold)
            worksheet.write("Q1", "Qty of Cartons in Actual Packed : Total Qty*", bold)
            worksheet.write("R1", "Qty of Pallets in Actual Packed : Total Qty*", bold)
            worksheet.write("S1", "Send as Is Item descriptions seperated by , ", bold)
            worksheet.write("T1", "DE Inst Address and DE Inst Contact", bold)
            worksheet.write("U1", "Delivery : Address Type", bold)
            worksheet.write("V1", "e_qty", bold)
            worksheet.write("W1", "e_dimLength", bold)
            worksheet.write("X1", "e_dimWidth", bold)
            worksheet.write("Y1", "e_dimHeight", bold)
            worksheet.write("Z1", "e_weightPerEach", bold)
            worksheet.write("AA1", "Each CBM", bold)
            worksheet.write("AB1", "e_item", bold)
            worksheet.write("AC1", "SINV#", bold)
            worksheet.write("AD1", "b_booking_visualID", bold)

            row = 1

        pk_booking_ids = []
        for booking in bookings:
            pk_booking_ids.append(booking.pk_booking_id)

        bcls = Api_booking_confirmation_lines.objects
        bcls = bcls.filter(fk_booking_id__in=pk_booking_ids)
        original_lines = Booking_lines.objects.filter(
            fk_booking_id__in=pk_booking_ids, packed_status="original"
        ).only("fk_booking_id", "e_item")
        scanned_lines = Booking_lines.objects.filter(
            fk_booking_id__in=pk_booking_ids, packed_status="scanned"
        ).only(
            "fk_booking_id",
            "e_qty",
            "e_weightPerEach",
            "e_weightUOM",
            "e_1_Total_dimCubicMeter",
            "e_type_of_packaging",
        )
        line_datas = Booking_lines_data.objects.filter(fk_booking_id__in=pk_booking_ids)

        logger.info(f"#311 Total cnt: {len(bookings)}")
        for booking_ind, booking in enumerate(bookings):
            total_qty = 0
            total_kgs = 0
            total_cbm = 0
            carton_cnt = 0
            pallet_cnt = 0

            if booking_ind % 500 == 0:
                logger.info(f"#312 Current index: {booking_ind}")

            booking_lines = []
            for booking_line in scanned_lines:
                if booking_line.fk_booking_id == booking.pk_booking_id:
                    booking_lines.append(booking_line)

                    if booking_line.e_qty:
                        total_qty += booking_line.e_qty
                    if booking_line.e_weightPerEach and booking_line.e_weightPerEach:
                        total_kgs = (
                            _get_weight_amount(booking_line.e_weightUOM)
                            * booking_line.e_weightPerEach
                        ) * booking_line.e_qty
                    if booking_line.e_1_Total_dimCubicMeter:
                        total_cbm = (
                            booking_line.e_1_Total_dimCubicMeter * booking_line.e_qty
                        )
                    if (
                        booking_line.e_type_of_packaging
                        and booking_line.e_type_of_packaging.upper() in PALLETS
                    ):
                        pallet_cnt += booking_line.e_qty
                    if (
                        booking_line.e_type_of_packaging
                        and not booking_line.e_type_of_packaging.upper() in PALLETS
                    ):
                        carton_cnt += booking_line.e_qty

            line_descriptions = []
            for booking_line in original_lines:
                if booking_line.fk_booking_id == booking.pk_booking_id:
                    if booking_line.e_item:
                        line_descriptions.append(booking_line.e_item)

            for index, line in enumerate(booking_lines):
                gap_ra = ""
                line_bcls = []
                line_bcl = None
                for bcl in bcls:
                    if bcl.fk_booking_id == booking.pk_booking_id:
                        line_bcls.append(bcl)

                try:
                    line_bcl = line_bcls[index]
                except:
                    pass

                for line_data in line_datas:
                    if line_data.fk_booking_lines_id == line.pk_booking_lines_id:
                        gap_ra = line_data.gap_ra
                        break

                line_cbm = get_cubic_meter(
                    line.e_dimLength,
                    line.e_dimWidth,
                    line.e_util_height or line.e_dimHeight,
                    line.e_dimUOM,
                    line.e_qty,
                )

                worksheet.write(row, col + 0, booking.b_client_name)
                worksheet.write(row, col + 1, booking.b_client_warehouse_code)
                worksheet.write(row, col + 2, booking.deToCompanyName)
                worksheet.write(row, col + 3, booking.v_FPBookingNumber)
                worksheet.write(row, col + 4, line_bcl.label_code if line_bcl else "")
                worksheet.write(row, col + 5, booking.b_client_sales_inv_num)
                worksheet.write(row, col + 6, booking.de_To_Address_Street_1)
                worksheet.write(row, col + 7, booking.de_To_Address_Street_2)
                worksheet.write(row, col + 8, booking.de_To_Address_Suburb)
                worksheet.write(row, col + 9, booking.de_To_Address_State)
                worksheet.write(row, col + 10, booking.de_To_Address_PostalCode)
                worksheet.write(row, col + 11, total_qty)
                worksheet.write(row, col + 12, total_kgs)
                worksheet.write(row, col + 13, total_cbm)
                worksheet.write(row, col + 14, booking.de_to_Phone_Main)
                worksheet.write(row, col + 15, booking.de_Email)
                worksheet.write(row, col + 16, carton_cnt)
                worksheet.write(row, col + 17, pallet_cnt)
                worksheet.write(row, col + 18, ", ".join(line_descriptions))
                worksheet.write(
                    row,
                    col + 19,
                    (booking.de_to_Pick_Up_Instructions_Contact or "")
                    + (booking.de_to_PickUp_Instructions_Address or ""),
                )
                worksheet.write(row, col + 20, booking.de_To_AddressType)
                worksheet.write(row, col + 21, line.e_qty)
                worksheet.write(
                    row, col + 22, line.e_dimLength * _get_dim_amount(line.e_dimUOM)
                )
                worksheet.write(
                    row, col + 23, line.e_dimWidth * _get_dim_amount(line.e_dimUOM)
                )
                worksheet.write(
                    row, col + 24, line.e_dimHeight * _get_dim_amount(line.e_dimUOM)
                )
                worksheet.write(
                    row,
                    col + 25,
                    line.e_weightPerEach * _get_weight_amount(line.e_weightUOM),
                )
                worksheet.write(row, col + 26, line_cbm)
                worksheet.write(row, col + 27, line.e_item)
                worksheet.write(row, col + 28, gap_ra)
                worksheet.write(row, col + 29, booking.b_bookingID_Visual)

                row += 1

        workbook.close()
        shutil.move(filename, local_filepath + filename)
        logger.info("#319 Finished - `Booking Lines Sent` XLS")
    elif xls_type == "delivery":
        logger.info("#310 Get started to build `Delivery` XLS")
        logger.info(f"#311 Total cnt: {len(bookings)}")
        worksheet.set_column(0, 26, width=30)

        if show_field_name:
            worksheet.write("A1", "b_status", bold)
            worksheet.write("B1", "s_20_Actual_Pickup_TimeStamp", bold)
            worksheet.write("C1", "s_21_Actual_Delivery_TimeStamp", bold)
            worksheet.write("D1", "s_06_Latest_Delivery_Date_TimeSet", bold)
            worksheet.write("E1", "No. of boxes delivered", bold)
            worksheet.write("F1", "Short", bold)
            worksheet.write("G1", "CSV #", bold)
            worksheet.write("H1", "b_client_order_num", bold)
            worksheet.write("I1", "External Document No.", bold)
            worksheet.write("J1", "deToCompanyName", bold)
            worksheet.write("K1", "deToCompanyName 2", bold)
            worksheet.write("L1", "de_To_Address_Street_1", bold)
            worksheet.write("M1", "de_to_address_suburb", bold)
            worksheet.write("N1", "de_To_Address_State", bold)
            worksheet.write("O1", "de_to_address_postcode", bold)
            worksheet.write("P1", "b_booking_visualID", bold)
            worksheet.write("Q1", "v_FPBookingNumber", bold)
            worksheet.write("R1", "No of units", bold)
            worksheet.write("S1", "No of boxes Booked", bold)
            worksheet.write("T1", "note", bold)
            worksheet.write("U1", "vx_freight_provider", bold)

            worksheet.write("A2", "Status", bold)
            worksheet.write("B2", "Pickup Date", bold)
            worksheet.write("C2", "Deliver Date", bold)
            worksheet.write("D2", "Expected Delivery Date", bold)
            worksheet.write("E2", "No. of Boxes Delivered", bold)
            worksheet.write("F2", "Short", bold)
            worksheet.write("G2", "CSV #", bold)
            worksheet.write("H2", "External Document No.", bold)
            worksheet.write("I2", "SINV #", bold)
            worksheet.write("J2", "Ship-to Name", bold)
            worksheet.write("K2", "Ship-to Name2 ", bold)
            worksheet.write("L2", "Ship-to Address", bold)
            worksheet.write("M2", "Ship-to City", bold)
            worksheet.write("N2", "Ship-to County", bold)
            worksheet.write("O2", "Ship-to PostCode", bold)
            worksheet.write("P2", "DME ID", bold)
            worksheet.write("Q2", "Connote Number", bold)
            worksheet.write("R2", "No of Units", bold)
            worksheet.write("S2", "No of Boxes Booked , ", bold)
            worksheet.write("T2", "Notes", bold)
            worksheet.write("U2", "Fright Provider", bold)

            row = 2
        else:
            worksheet.write("A1", "Status", bold)
            worksheet.write("B1", "Pickup Date", bold)
            worksheet.write("C1", "Deliver Date", bold)
            worksheet.write("D1", "Expected Delivery Date", bold)
            worksheet.write("E1", "No. of Boxes Delivered", bold)
            worksheet.write("F1", "Short", bold)
            worksheet.write("G1", "CSV #", bold)
            worksheet.write("H1", "External Document No.", bold)
            worksheet.write("I1", "SINV #", bold)
            worksheet.write("J1", "Ship-to Name", bold)
            worksheet.write("K1", "Ship-to Name2 ", bold)
            worksheet.write("L1", "Ship-to Address", bold)
            worksheet.write("M1", "Ship-to City", bold)
            worksheet.write("N1", "Ship-to County", bold)
            worksheet.write("O1", "Ship-to PostCode", bold)
            worksheet.write("P1", "DME ID", bold)
            worksheet.write("Q1", "Connote Number", bold)
            worksheet.write("R1", "No of Units", bold)
            worksheet.write("S1", "No of Boxes Booked , ", bold)
            worksheet.write("T1", "Notes", bold)
            worksheet.write("U1", "Fright Provider", bold)

            row = 1

        pk_booking_ids = []
        for booking in bookings:
            pk_booking_ids.append(booking.pk_booking_id)

        bcls = Api_booking_confirmation_lines.objects
        bcls = bcls.filter(fk_booking_id__in=pk_booking_ids)
        lines = Booking_lines.objects
        lines = lines.filter(fk_booking_id__in=pk_booking_ids, packed_status="scanned")
        line_datas = Booking_lines_data.objects
        line_datas = line_datas.filter(fk_booking_id__in=pk_booking_ids)
        histories = Dme_status_history.objects
        histories = histories.filter(fk_booking_id__in=pk_booking_ids).order_by("-id")

        for booking_ind, booking in enumerate(bookings):
            status_history_note = ""
            no_unites = 0
            no_boxes_booked = 0
            no_boxes_delivered = 0

            for bcl in bcls:
                if bcl.fk_booking_id == booking.pk_booking_id:
                    if bcl.api_status == "Item Delivered":
                        no_boxes_delivered += 1

            for line in lines:
                if line.fk_booking_id == booking.pk_booking_id:
                    no_boxes_booked += line.e_qty

            for line_data in line_datas:
                if line_data.fk_booking_id == booking.pk_booking_id:
                    no_unites += line_data.quantity

            for history in histories:
                if history.dme_notes:
                    status_history_note = history.dme_notes
                    break

            if booking.b_status == "Delivered" and no_boxes_delivered == 0:
                no_boxes_delivered = no_boxes_booked

            worksheet.write(row, col + 0, booking.b_status)

            if booking.s_20_Actual_Pickup_TimeStamp:
                worksheet.write_datetime(
                    row,
                    col + 1,
                    convert_to_AU_SYDNEY_tz(
                        booking.s_20_Actual_Pickup_TimeStamp
                    ).date(),
                    date_format,
                )

            if booking.s_21_Actual_Delivery_TimeStamp:
                worksheet.write_datetime(
                    row,
                    col + 2,
                    convert_to_AU_SYDNEY_tz(
                        booking.s_21_Actual_Delivery_TimeStamp
                    ).date(),
                    date_format,
                )

            if booking.s_06_Latest_Delivery_Date_TimeSet:
                worksheet.write_datetime(
                    row,
                    col + 3,
                    convert_to_AU_SYDNEY_tz(
                        booking.s_06_Latest_Delivery_Date_TimeSet
                    ).date(),
                    date_format,
                )

            worksheet.write(row, col + 4, no_boxes_delivered)
            worksheet.write(row, col + 5, no_boxes_booked - no_boxes_delivered)
            worksheet.write(row, col + 6, booking.b_booking_project)
            worksheet.write(row, col + 7, booking.b_client_order_num)
            worksheet.write(row, col + 8, booking.b_client_sales_inv_num)
            worksheet.write(row, col + 9, booking.deToCompanyName)
            worksheet.write(row, col + 10, "")
            worksheet.write(row, col + 11, booking.de_To_Address_Street_1)
            worksheet.write(row, col + 12, booking.de_To_Address_Suburb)
            worksheet.write(row, col + 13, booking.de_To_Address_State)
            worksheet.write(row, col + 14, booking.de_To_Address_PostalCode)
            worksheet.write(row, col + 15, booking.b_bookingID_Visual)
            worksheet.write(row, col + 16, booking.v_FPBookingNumber)
            worksheet.write(row, col + 17, no_unites)
            worksheet.write(row, col + 18, no_boxes_booked)
            worksheet.write(row, col + 19, status_history_note)
            worksheet.write(row, col + 20, booking.vx_freight_provider)

            row += 1

        workbook.close()
        shutil.move(filename, local_filepath + filename)
        logger.info("#319 Finished - `Booking Lines Sent` XLS")
    elif xls_type == "cost_report_dme_only":
        logger.info(
            "#350 Get started to build `Bookings Report with  Costs - DME Only` XLS"
        )
        worksheet.set_column(0, 15, width=25)

        if show_field_name:
            worksheet.write("A1", "b_bookingID_Visual", bold)
            worksheet.write("B1", "line_data/gap_ra", bold)
            worksheet.write("C1", "b_status", bold)
            worksheet.write("D1", "delivery_booking", bold)
            worksheet.write("E1", "b_booking_Category", bold)
            worksheet.write("F1", "puCompany", bold)
            worksheet.write("G1", "pu_Address_Suburb", bold)
            worksheet.write("H1", "pu_Address_State", bold)
            worksheet.write("I1", "pu_Address_PostalCode", bold)
            worksheet.write("J1", "deToCompanyName", bold)
            worksheet.write("K1", "de_To_Address_Suburb", bold)
            worksheet.write("L1", "de_To_Address_State ", bold)
            worksheet.write("M1", "de_To_Address_PostalCode", bold)
            worksheet.write("N1", "b_booking_Notes", bold)
            worksheet.write("O1", "line_data/clientRefNumbers", bold)
            worksheet.write("P1", "line/e_qty", bold)
            worksheet.write("Q1", "line_data/modelNumbers", bold)
            worksheet.write("R1", "line_data/itemDescriptions", bold)
            worksheet.write("S1", "vx_freight_provider", bold)
            worksheet.write("T1", "v_FPBookingNumber", bold)
            worksheet.write("U1", "Actual Packed Qty*", bold)
            worksheet.write("V1", "Actual Packed DIMS*", bold)
            worksheet.write("W1", "Actual Packed Utilised DIMS*", bold)
            worksheet.write("X1", "inv_cost_actual", bold)
            worksheet.write("Y1", "b_client_name", bold)
            worksheet.write("Z1", "b_dateBookedDate", bold)
            worksheet.write("AA1", "Dead Weight", bold)
            worksheet.write("AB1", "inv_cost_quoted", bold)
            worksheet.write("AC1", "inv_sell_quoted", bold)
            worksheet.write("AD1", "inv_cost_actual", bold)
            worksheet.write("AE1", "inv_booked_quoted", bold)
            worksheet.write("AF1", "inv_sell_quoted_override", bold)
            worksheet.write("AG1", "inv_sell_actual", bold)
            worksheet.write("AH1", "b_client_name", bold)
            worksheet.write("AI1", "b_client_name_sub", bold)
            worksheet.write("AJ1", "vx_freight_provider", bold)

            worksheet.write("A2", "DeliverME Booking Ref", bold)
            worksheet.write("B2", "Gap/ra - from line_data", bold)
            worksheet.write("C2", "Booking Status", bold)
            worksheet.write("D2", "Actual Delivery Date", bold)
            worksheet.write("E2", "Booking Category", bold)
            worksheet.write("F2", "Pickup Entity", bold)
            worksheet.write("G2", "Pickup Address Suburb", bold)
            worksheet.write("H2", "Pickup Address State", bold)
            worksheet.write("I2", "Pickup Address Postal Code", bold)
            worksheet.write("J2", "Deliver to Entity", bold)
            worksheet.write("K2", "Delivery Address Suburb", bold)
            worksheet.write("L2", "Delivery Address State", bold)
            worksheet.write("M2", "Delivery Address Postal Code", bold)
            worksheet.write("N2", "Booking Notes", bold)
            worksheet.write("O2", "Client Reference No's", bold)
            worksheet.write("P2", "Quantity", bold)
            worksheet.write("Q2", "ModelNumbers", bold)
            worksheet.write("R2", "ItemDescriptions", bold)
            worksheet.write("S2", "Freight Provider", bold)
            worksheet.write("T2", "Consignment No", bold)
            worksheet.write("U2", "Actual Packed Qty*", bold)
            worksheet.write("V2", "Actual Packed CBM*", bold)
            worksheet.write("W2", "Actual Packed Utilised CBM*", bold)
            worksheet.write("X2", "Actual Cost", bold)
            worksheet.write("Y2", "Client Name", bold)
            worksheet.write("Z2", "Booked Date", bold)
            worksheet.write("AA2", "Dead Weight", bold)
            worksheet.write("AB2", "Quoted Cost", bold)
            worksheet.write("AC2", "Quoted $", bold)
            worksheet.write("AD2", "Actual Cost", bold)
            worksheet.write("AE2", "Booked $", bold)
            worksheet.write("AF2", "Quoted $*", bold)
            worksheet.write("AG2", "Actual $", bold)
            worksheet.write("AH2", "Client Name", bold)
            worksheet.write("AI2", "Sub Client Name", bold)
            worksheet.write("AJ2", "Freight Provider", bold)

            row = 2
        else:
            worksheet.write("A1", "DeliverME Booking Ref", bold)
            worksheet.write("B1", "Gap/ra - from line_data", bold)
            worksheet.write("C1", "Booking Status", bold)
            worksheet.write("D1", "Actual Delivery Date", bold)
            worksheet.write("E1", "Booking Category", bold)
            worksheet.write("F1", "Pickup Entity", bold)
            worksheet.write("G1", "Pickup Address Suburb", bold)
            worksheet.write("H1", "Pickup Address State", bold)
            worksheet.write("I1", "Pickup Address Postal Code", bold)
            worksheet.write("J1", "Deliver to Entity", bold)
            worksheet.write("K1", "Delivery Address Suburb", bold)
            worksheet.write("L1", "Delivery Address State", bold)
            worksheet.write("M1", "Delivery Address Postal Code", bold)
            worksheet.write("N1", "Booking Notes", bold)
            worksheet.write("O1", "Client Reference No's", bold)
            worksheet.write("P1", "Quantity", bold)
            worksheet.write("Q1", "ModelNumbers", bold)
            worksheet.write("R1", "ItemDescriptions", bold)
            worksheet.write("S1", "Freight Provider", bold)
            worksheet.write("T1", "Consignment No", bold)
            worksheet.write("U1", "Actual Packed Qty*", bold)
            worksheet.write("V1", "Actual Packed CBM*", bold)
            worksheet.write("W1", "Actual Packed Utilised CBM*", bold)
            worksheet.write("X1", "Actual Cost", bold)
            worksheet.write("Y1", "Client Name", bold)
            worksheet.write("Z1", "Booked Date", bold)
            worksheet.write("AA1", "Dead Weight", bold)
            worksheet.write("AB1", "Quoted Cost", bold)
            worksheet.write("AC1", "Quoted $", bold)
            worksheet.write("AD1", "Actual Cost", bold)
            worksheet.write("AE1", "Booked $", bold)
            worksheet.write("AF1", "Quoted $*", bold)
            worksheet.write("AG1", "Actual $", bold)
            worksheet.write("AH1", "Client Name", bold)
            worksheet.write("AI1", "Sub Client Name", bold)
            worksheet.write("AJ1", "Freight Provider", bold)

            row = 1

        logger.info(f"#351 Total cnt: {len(bookings)}")

        pk_booking_ids = []
        for booking in bookings:
            pk_booking_ids.append(booking.pk_booking_id)
        lines = Booking_lines.objects.filter(
            fk_booking_id__in=pk_booking_ids, packed_status__in=["original", "scanned"]
        ).only(
            "fk_booking_id",
            "e_qty",
            "e_dimLength",
            "e_dimWidth",
            "e_dimHeight",
            "e_dimUOM",
            "e_util_height",
            "e_weightPerEach",
            "e_weightUOM",
            "packed_status",
        )
        line_datas_with_gapRas = get_gapRas(bookings)
        line_datas_with_clientRefNumbers = get_clientRefNumbers(bookings)

        for booking_ind, booking in enumerate(bookings):
            if booking_ind % 500 == 0:
                logger.info(f"#396 Current index: {booking_ind}")

            original_lines = []
            scanned_lines = []
            for line in lines:
                if line.fk_booking_id == booking.pk_booking_id:
                    if line.packed_status == "original":
                        original_lines.append(line)
                    else:
                        scanned_lines.append(line)
            booking_lines = scanned_lines or original_lines
            total_cbm = 0
            total_util_cbm = 0
            total_kgs = 0

            for line in booking_lines:
                total_cbm += get_cubic_meter(
                    line.e_dimLength,
                    line.e_dimWidth,
                    line.e_dimHeight,
                    line.e_dimUOM,
                    line.e_qty,
                )
                total_util_cbm = get_cubic_meter(
                    line.e_dimLength,
                    line.e_dimWidth,
                    line.e_util_height or line.e_dimHeight,
                    line.e_dimUOM,
                    line.e_qty,
                )
                if line.e_weightPerEach and line.e_weightPerEach:
                    total_kgs += (
                        _get_weight_amount(line.e_weightUOM) * line.e_weightPerEach
                    ) * line.e_qty

            worksheet.write(row, col + 0, booking.b_bookingID_Visual)

            booking_gap_ras = []
            for line_data in line_datas_with_gapRas:
                if booking.pk_booking_id == line_data.fk_booking_id:
                    booking_gap_ras.append(line_data.gap_ra)

            worksheet.write(row, col + 1, ", ".join(booking_gap_ras))
            worksheet.write(row, col + 2, booking.b_status)

            if booking.s_21_Actual_Delivery_TimeStamp:
                worksheet.write_datetime(
                    row,
                    col + 3,
                    convert_to_AU_SYDNEY_tz(booking.s_21_Actual_Delivery_TimeStamp),
                    date_format,
                )

            worksheet.write(row, col + 4, booking.b_booking_Category)
            worksheet.write(row, col + 5, booking.puCompany)
            worksheet.write(row, col + 6, booking.pu_Address_Suburb)
            worksheet.write(row, col + 7, booking.pu_Address_State)
            worksheet.write(row, col + 8, booking.pu_Address_PostalCode)
            worksheet.write(row, col + 9, booking.deToCompanyName)
            worksheet.write(row, col + 10, booking.de_To_Address_Suburb)
            worksheet.write(row, col + 11, booking.de_To_Address_State)
            worksheet.write(row, col + 12, booking.de_To_Address_PostalCode)
            worksheet.write(row, col + 13, booking.b_booking_Notes)

            booking_clientRefNumbers = []
            for line_data in line_datas_with_clientRefNumbers:
                if booking.pk_booking_id == line_data.fk_booking_id:
                    booking_clientRefNumbers.append(line_data.clientRefNumber)

            worksheet.write(row, col + 14, ", ".join(booking_clientRefNumbers))
            worksheet.write(row, col + 15, booking.get_total_lines_qty())

            modelNumbers = []
            itemDescriptions = []
            booking_lines_data = Booking_lines_data.objects.filter(
                fk_booking_id=booking.pk_booking_id
            )

            for booking_line_data in booking_lines_data:
                if booking_line_data.modelNumber:
                    modelNumbers.append(booking_line_data.modelNumber)

                if booking_line_data.itemDescription:
                    itemDescriptions.append(booking_line_data.itemDescription)

            worksheet.write(row, col + 16, ", ".join(modelNumbers))
            worksheet.write(row, col + 17, ", ".join(itemDescriptions))
            worksheet.write(row, col + 18, booking.vx_freight_provider)
            worksheet.write(row, col + 19, booking.v_FPBookingNumber)
            worksheet.write(row, col + 20, len(booking_lines))
            worksheet.write(row, col + 21, round(total_cbm, 2))
            worksheet.write(row, col + 22, round(total_util_cbm, 2))
            worksheet.write(row, col + 23, booking.inv_cost_actual)
            worksheet.write(row, col + 24, booking.b_client_name)
            worksheet.write(row, col + 25, booking.b_dateBookedDate)
            worksheet.write(row, col + 26, round(total_kgs, 2))

            worksheet.write(row, col + 27, round(booking.inv_cost_quoted or 0, 3))
            worksheet.write(row, col + 28, round(booking.inv_sell_quoted or 0, 3))
            worksheet.write(row, col + 29, round(booking.inv_cost_actual or 0, 3))
            worksheet.write(row, col + 30, round(booking.inv_booked_quoted or 0, 3))
            worksheet.write(
                row, col + 31, round(booking.inv_sell_quoted_override or 0, 3)
            )
            worksheet.write(row, col + 32, round(booking.inv_sell_actual or 0, 3))
            worksheet.write(row, col + 33, booking.b_client_name)
            worksheet.write(row, col + 34, booking.b_client_name_sub)
            worksheet.write(row, col + 35, booking.vx_freight_provider)

            row += 1

        workbook.close()
        shutil.move(filename, local_filepath + filename)
        logger.info("#359 Finished - `Bookings Report with  Costs - DME Only` XLS")

    return local_filepath + filename
