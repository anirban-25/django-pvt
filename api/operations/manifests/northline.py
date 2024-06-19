import os
import sys
import logging
from datetime import datetime
from reportlab.lib.enums import TA_JUSTIFY, TA_RIGHT, TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import letter, landscape, A6
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Image,
    PageBreak,
    Table,
)
from reportlab.platypus.flowables import Spacer, HRFlowable, PageBreak, Flowable
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch, mm
from reportlab.graphics.barcode import (
    code39,
    code128,
    code93,
    createBarcodeDrawing,
    eanbc,
    qr,
    usps,
)
from reportlab.graphics.shapes import Drawing
from reportlab.pdfgen import canvas
from reportlab.graphics import renderPDF
from reportlab.lib import colors
from django.conf import settings

from api.models import Fp_freight_providers, Dme_manifest_log

if settings.ENV == "local":
    production = False  # Local
else:
    production = True  # Dev

### NORTHLINE constants ###
ACCOUNT_CODE = "NORTHLINE"
styles = getSampleStyleSheet()
style_right = ParagraphStyle(name="right", parent=styles["Normal"], alignment=TA_RIGHT)
style_left = ParagraphStyle(name="left", parent=styles["Normal"], alignment=TA_LEFT)
style_center = ParagraphStyle(
    name="center", parent=styles["Normal"], alignment=TA_CENTER
)
style_cell = ParagraphStyle(name="smallcell", fontSize=6, leading=6)
styles.add(ParagraphStyle(name="Justify", alignment=TA_JUSTIFY))
#####################

logger = logging.getLogger(__name__)


def filter_booking_lines(booking, booking_lines):
    original_lines = []
    scanned_lines = []

    for booking_line in booking_lines:
        if booking.pk_booking_id == booking_line.fk_booking_id:
            if booking_line.packed_status == "original":
                original_lines.append(booking_line)
            elif booking_line.packed_status == "scanned":
                scanned_lines.append(booking_line)

    return scanned_lines or original_lines


def build_manifest(bookings, booking_lines, username, need_truck, timestamp):
    fp_info = Fp_freight_providers.objects.get(fp_company_name="Northline")
    new_manifest_index = fp_info.fp_manifest_cnt
    new_connot_index = fp_info.new_connot_index

    # start check if pdfs folder exists
    if production:
        local_filepath = "/opt/s3_public/pdfs/northline_au/"
        local_filepath_dup = (
            "/opt/s3_public/pdfs/northline_au/archive/"
            + str(datetime.now().strftime("%Y_%m_%d"))
            + "/"
        )
    else:
        local_filepath = "./static/pdfs/northline_au/"
        local_filepath_dup = (
            "./static/pdfs/northline_au/archive/"
            + str(datetime.now().strftime("%Y_%m_%d"))
            + "/"
        )

    if not os.path.exists(local_filepath):
        os.makedirs(local_filepath)
    # end check if pdfs folder exists

    # start loop through data fetched from dme_bookings table
    date = datetime.now().strftime("%Y%m%d") + "_" + datetime.now().strftime("%H%M%S")
    filename = "MANIFEST_" + date + "_m.pdf"
    file = open(local_filepath + filename, "a")
    doc = SimpleDocTemplate(
        local_filepath + filename,
        pagesize=(223 * mm, 25 * mm),
        rightMargin=10,
        leftMargin=10,
        topMargin=10,
        bottomMargin=10,
    )
    Story = []
    manifest = "M" + ACCOUNT_CODE + str(new_manifest_index).zfill(4)

    booking_ids = []
    for booking in bookings:
        booking_ids.append(str(booking.pk))
        _booking_lines = filter_booking_lines(booking, booking_lines)
        booking.manifest_timestamp = datetime.utcnow()
        booking.save()

    for _, booking in enumerate(bookings):
        try:
            _booking_lines = filter_booking_lines(booking, booking_lines)

            col1_w = 150
            col2_w = 150
            col3_w = 100
            col4_w = 100
            col5_w = 100

            for _, booking_line in enumerate(_booking_lines):
                tbl_data = [
                    [
                        Paragraph(
                            '<font size=10 color="white"><b>CONNOTE</b></font>',
                            styles["Normal"],
                        ),
                        Paragraph(
                            '<font size=10 color="white"><b>Rec Details</b></font>',
                            styles["Normal"],
                        ),
                        Paragraph(
                            '<font size=10 color="white"><b>Qty</b></font>',
                            styles["Normal"],
                        ),
                        Paragraph(
                            '<font size=10 color="white"><b>Weight</b></font>',
                            styles["Normal"],
                        ),
                        Paragraph(
                            '<font size=10 color="white"><b>Cubic</b></font>',
                            styles["Normal"],
                        ),
                    ]
                ]
                tbl = Table(
                    tbl_data,
                    colWidths=(
                        col1_w,
                        col2_w,
                        col3_w,
                        col4_w,
                        col5_w,
                    ),
                    rowHeights=20,
                    hAlign="LEFT",
                    style=[("BACKGROUND", (0, 0), (11, 1), colors.black)],
                )
                Story.append(tbl)

            tbl_data = [
                [
                    Paragraph(
                        "<font size=10>%s</font>"
                        % (
                            str(booking.v_FPBookingNumber)
                            if booking.v_FPBookingNumber
                            else ""
                        ),
                        style_left,
                    ),
                    Paragraph(
                        "<font size=10>%s, %s %s </font>"
                        % (
                            booking.de_To_Address_Suburb,
                            booking.de_To_Address_State,
                            booking.de_To_Address_PostalCode,
                        ),
                        style_left,
                    ),
                    Paragraph(
                        "<font size=10>%s</font>" % str(booking_line.e_qty),
                        style_left,
                    ),
                    Paragraph(
                        "<font size=10>%s</font>"
                        % str(
                            "{0:,.2f}".format(
                                booking_line.e_Total_KG_weight
                                if booking_line.e_Total_KG_weight is not None
                                else ""
                            )
                        ),
                        style_left,
                    ),
                    Paragraph(
                        "<font size=10>%s</font>"
                        % str(booking_line.e_1_Total_dimCubicMeter),
                        style_left,
                    ),
                ]
            ]
            tbl = Table(
                tbl_data,
                colWidths=(
                    col1_w,
                    col2_w,
                    col3_w,
                    col4_w,
                    col5_w,
                ),
                rowHeights=18,
                hAlign="LEFT",
                style=[("GRID", (0, 0), (-1, -1), 0.5, colors.black)],
            )
            Story.append(tbl)

            Story.append(PageBreak())

        except Exception as e:
            exc_type, exc_obj, exc_tb = sys.exc_info()
            fname = os.path.split(exc_tb.tb_frame.f_code.co_filename)[1]
            logger.info(f"ERROR @303 - {str(e)}")

    doc.build(Story)
    file.close()

    # Add manifest log
    manfiest_log = Dme_manifest_log.objects.create(
        fk_booking_id=booking.pk_booking_id,
        manifest_url=f"northline_au/{filename}",
        manifest_number=manifest,
        bookings_cnt=len(bookings),
        is_one_booking=1,
        z_createdByAccount=username,
        need_truck=need_truck,
        freight_provider="Northline",
        booking_ids=",".join(booking_ids),
    )
    manfiest_log.z_createdTimeStamp = timestamp
    manfiest_log.save()

    fp_info.fp_manifest_cnt = fp_info.fp_manifest_cnt + 1
    fp_info.new_connot_index = fp_info.new_connot_index + len(bookings)
    fp_info.save()

    return filename
