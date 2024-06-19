import os, sys
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

### TAS constants ###
# ACCOUNT_CODE = "AATEST"
ACCOUNT_CODE = "SEAWAPO"
styles = getSampleStyleSheet()
style_right = ParagraphStyle(name="right", parent=styles["Normal"], alignment=TA_RIGHT)
style_left = ParagraphStyle(name="left", parent=styles["Normal"], alignment=TA_LEFT)
style_center = ParagraphStyle(
    name="center", parent=styles["Normal"], alignment=TA_CENTER
)
style_cell = ParagraphStyle(name="smallcell", fontSize=6, leading=6)
styles.add(ParagraphStyle(name="Justify", alignment=TA_JUSTIFY))
ROWS_PER_PAGE = 20
#####################


def filter_booking_lines(booking, booking_lines):
    _booking_lines = []

    for booking_line in booking_lines:
        if booking.pk_booking_id == booking_line.fk_booking_id:
            _booking_lines.append(booking_line)

    return _booking_lines


def build_manifest(bookings, booking_lines, username, need_truck, timestamp):
    fp_info = Fp_freight_providers.objects.get(fp_company_name="Tas")
    new_manifest_index = fp_info.fp_manifest_cnt
    new_connot_index = fp_info.new_connot_index

    # start check if pdfs folder exists
    if production:
        local_filepath = "/opt/s3_public/pdfs/tas_au"
        local_filepath_dup = (
            "/opt/s3_public/pdfs/tas_au/archive/"
            + str(datetime.now().strftime("%Y_%m_%d"))
            + "/"
        )
    else:
        local_filepath = "./static/pdfs/tas_au"
        local_filepath_dup = (
            "./static/pdfs/tas_au/archive/"
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
        pagesize=(297 * mm, 210 * mm),
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

    for k in range(2):
        i = 1
        row_cnt = 0
        page_cnt = 1

        ent_qty = 0
        ent_weight = 0
        ent_vol = 0
        ent_rows = 0

        for booking in bookings:
            _booking_lines = filter_booking_lines(booking, booking_lines)
            totalQty = 0
            totalWght = 0
            totalVol = 0

            for booking_line in _booking_lines:
                totalQty = (
                    totalQty + booking_line.e_qty
                    if booking_line.e_qty is not None
                    else 0
                )
                totalWght = (
                    totalWght + booking_line.e_Total_KG_weight
                    if booking_line.e_Total_KG_weight is not None
                    else 0
                )
                totalVol = (
                    totalVol + booking_line.e_1_Total_dimCubicMeter
                    if booking_line.e_1_Total_dimCubicMeter is not None
                    else 0
                )
            ent_qty = ent_qty + totalQty
            ent_weight = ent_weight + totalWght
            ent_vol = ent_vol + totalVol
            ent_rows = ent_rows + len(booking_lines)

            booking.manifest_timestamp = datetime.utcnow()
            booking.save()

        for booking_ind, booking in enumerate(bookings):
            try:
                _booking_lines = filter_booking_lines(booking, booking_lines)

                carrierName = booking.vx_freight_provider
                senderName = ACCOUNT_CODE
                ConNote = ACCOUNT_CODE + str(new_connot_index + i - 1).zfill(5)
                Reference = "TEST123"
                created_date = str(datetime.now().strftime("%d/%m/%Y"))
                printed_timestamp = str(datetime.now().strftime("%d/%m/%Y %I:%M:%S %p"))
                barcode = manifest
                barcode128 = code128.Code128(barcode, barHeight=30 * mm, barWidth=0.8)

                if k == 0:
                    ptext = "Customer Copy - Detail"
                else:
                    ptext = "Driver Copy - Detail"

                col1_w = 20
                col2_w = 70
                col3_w = 70
                col4_w = 140
                col5_w = 100
                col6_w = 80
                col7_w = 60
                col8_w = 60
                col9_w = 40
                col10_w = 55
                col11_w = 55
                col12_w = 60

                j = 1
                totalQty = 0
                totalWght = 0
                totalVol = 0

                for booking_line_ind, booking_line in enumerate(_booking_lines):
                    if row_cnt == 0:  # Add page header and table header
                        paragraph = Paragraph(
                            "<font size=12><b>%s</b></font>" % ptext,
                            styles["Normal"],
                        )
                        Story.append(paragraph)
                        Story.append(Spacer(1, 5))

                        tbl_data = [
                            [
                                Paragraph(
                                    '<font size=8 color="white"><b>MANIFEST DETAILS</b></font>',
                                    style_left,
                                )
                            ],
                            [
                                Paragraph(
                                    "<font size=8><b>Carrier:</b></font>",
                                    styles["BodyText"],
                                ),
                                Paragraph(
                                    "<font size=8>%s</font>" % carrierName,
                                    styles["BodyText"],
                                ),
                            ],
                            [
                                Paragraph(
                                    "<font size=8><b>Manifest:</b></font>",
                                    styles["BodyText"],
                                ),
                                Paragraph(
                                    "<font size=8>%s</font>" % manifest,
                                    styles["BodyText"],
                                ),
                            ],
                            [
                                Paragraph(
                                    "<font size=8><b>Accounts:</b></font>",
                                    styles["BodyText"],
                                ),
                                Paragraph(
                                    "<font size=8>%s</font>" % senderName,
                                    styles["BodyText"],
                                ),
                            ]
                            # [Paragraph('<font size=8><b>Total Qty:</b></font>', styles["BodyText"]), Paragraph('<font size=8>%s</font>' %  str(ent_qty), styles["BodyText"])],
                            # [Paragraph('<font size=8><b>Total Kgs:</b></font>', styles["BodyText"]), Paragraph('<font size=8>%s</font>' % str("{0:.2f}".format(ent_weight)), styles["BodyText"])],
                            # [Paragraph('<font size=8><b>Total VOL:</b></font>', styles["BodyText"]), Paragraph('<font size=8>%s</font>' % str(ent_vol), styles["BodyText"])],
                        ]
                        t1 = Table(
                            tbl_data,
                            colWidths=(20 * mm, 60 * mm),
                            rowHeights=18,
                            hAlign="LEFT",
                            vAlign="BOTTOM",
                            style=[
                                ("BACKGROUND", (0, 0), (0, 0), colors.black),
                                ("COLOR", (0, 0), (-1, -1), colors.white),
                                ("SPAN", (0, 0), (1, 0)),
                                ("BOX", (0, 0), (-1, -1), 0.5, (0, 0, 0)),
                            ],
                        )

                        tbl_data = [[barcode128]]
                        t2 = Table(
                            tbl_data,
                            colWidths=(127 * mm),
                            rowHeights=(30 * mm),
                            hAlign="CENTER",
                            vAlign="BOTTOM",
                            style=[("ALIGN", (0, 0), (0, 0), "CENTER")],
                        )

                        tbl_data = [
                            [
                                Paragraph(
                                    '<font size=8 color="white"><b>GENERAL DETAILS</b></font>',
                                    style_left,
                                )
                            ],
                            [
                                Paragraph(
                                    "<font size=8><b>Created:</b></font>",
                                    styles["BodyText"],
                                ),
                                Paragraph(
                                    "<font size=8>%s <b>Printed:</b> %s</font>"
                                    % (created_date, printed_timestamp),
                                    styles["BodyText"],
                                ),
                            ],
                            [
                                Paragraph(
                                    "<font size=8><b>Page:</b></font>",
                                    styles["BodyText"],
                                ),
                                Paragraph(
                                    "<font size=8>%s of %s</font>"
                                    % (page_cnt, int(ent_rows / ROWS_PER_PAGE) + 1),
                                    styles["BodyText"],
                                ),
                            ],
                            [
                                Paragraph(
                                    "<font size=8><b>Sender:</b></font>",
                                    styles["BodyText"],
                                ),
                                Paragraph(
                                    "<font size=8>%s, %s</font>"
                                    % (senderName, booking.pu_Address_Street_1),
                                    styles["Normal"],
                                ),
                            ],
                            [
                                Paragraph(
                                    "<font size=8><b></b></font>",
                                    styles["BodyText"],
                                ),
                                Paragraph(
                                    "<font size=8>%s, %s, %s</font>"
                                    % (
                                        booking.pu_Address_Suburb,
                                        booking.pu_Address_PostalCode,
                                        booking.pu_Address_State,
                                    ),
                                    styles["Normal"],
                                ),
                            ],
                        ]
                        t3 = Table(
                            tbl_data,
                            colWidths=(17 * mm, 63 * mm),
                            rowHeights=16,
                            hAlign="RIGHT",
                            vAlign="MIDDLE",
                            style=[
                                ("BACKGROUND", (0, 0), (0, 0), colors.black),
                                ("COLOR", (0, 0), (-1, -1), colors.white),
                                ("SPAN", (0, 0), (1, 0)),
                                ("BOX", (0, 0), (-1, -1), 0.5, (0, 0, 0)),
                            ],
                        )

                        data = [[t1, t2, t3]]
                        # adjust the length of tables
                        t1_w = 80 * mm
                        t2_w = 127 * mm
                        t3_w = 80 * mm
                        shell_table = Table(
                            data,
                            colWidths=[t1_w, t2_w, t3_w],
                            style=[
                                ("TOPPADDING", (0, 0), (-1, -1), 0),
                                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                            ],
                        )
                        Story.append(shell_table)
                        Story.append(Spacer(1, 10))

                        tbl_data = [
                            [
                                Paragraph(
                                    '<font size=10 color="white"></font>',
                                    styles["Normal"],
                                ),
                                Paragraph(
                                    '<font size=10 color="white"><b>CONNOTE</b></font>',
                                    styles["Normal"],
                                ),
                                Paragraph(
                                    '<font size=10 color="white"><b>REF</b></font>',
                                    styles["Normal"],
                                ),
                                Paragraph(
                                    '<font size=10 color="white"><b>DESCRIPTION</b></font>',
                                    styles["Normal"],
                                ),
                                Paragraph(
                                    '<font size=10 color="white"><b>RECEIVER</b></font>',
                                    styles["Normal"],
                                ),
                                Paragraph(
                                    '<font size=10 color="white"><b>SUBURB</b></font>',
                                    styles["Normal"],
                                ),
                                Paragraph(
                                    '<font size=10 color="white"><b>STATE</b></font>',
                                    styles["Normal"],
                                ),
                                Paragraph(
                                    '<font size=10 color="white"><b>PCODE</b></font>',
                                    styles["Normal"],
                                ),
                                Paragraph(
                                    '<font size=10 color="white"><b>QTY</b></font>',
                                    styles["Normal"],
                                ),
                                Paragraph(
                                    '<font size=10 color="white"><b>KG</b></font>',
                                    styles["Normal"],
                                ),
                                Paragraph(
                                    '<font size=10 color="white"><b>VOL</b></font>',
                                    styles["Normal"],
                                ),
                                Paragraph(
                                    '<font size=10 color="white"><b>ROUTE</b></font>',
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
                                col6_w,
                                col7_w,
                                col8_w,
                                col9_w,
                                col10_w,
                                col11_w,
                                col12_w,
                            ),
                            rowHeights=20,
                            hAlign="LEFT",
                            style=[("BACKGROUND", (0, 0), (11, 1), colors.black)],
                        )
                        Story.append(tbl)

                    totalQty = (
                        totalQty + booking_line.e_qty
                        if booking_line.e_qty is not None
                        else 0
                    )
                    totalWght = (
                        totalWght + booking_line.e_Total_KG_weight
                        if booking_line.e_Total_KG_weight is not None
                        else 0
                    )
                    totalVol = (
                        totalVol + booking_line.e_1_Total_dimCubicMeter
                        if booking_line.e_1_Total_dimCubicMeter is not None
                        else 0
                    )

                    tbl_data = [
                        [
                            Paragraph("<font size=6>%s</font>" % j, styles["Normal"]),
                            Paragraph("<font size=6>%s</font>" % ConNote, style_cell),
                            Paragraph(
                                "<font size=6>%s</font>"
                                % (
                                    str(booking_line.client_item_reference)
                                    if booking_line.client_item_reference
                                    else ""
                                ),
                                style_cell,
                            ),
                            Paragraph(
                                "<font size=6>%s</font>"
                                % (
                                    str(booking_line.e_item)
                                    if booking_line.e_item
                                    else ""
                                ),
                                style_cell,
                            ),
                            Paragraph(
                                "<font size=6>%s</font>"
                                % booking.de_to_Contact_F_LName,
                                style_cell,
                            ),
                            Paragraph(
                                "<font size=6>%s</font>" % booking.de_To_Address_Suburb,
                                style_cell,
                            ),
                            Paragraph(
                                "<font size=6>%s</font>" % booking.de_To_Address_State,
                                styles["Normal"],
                            ),
                            Paragraph(
                                "<font size=6>%s</font>"
                                % booking.de_To_Address_PostalCode,
                                styles["Normal"],
                            ),
                            Paragraph(
                                "<font size=6>%s</font>" % str(booking_line.e_qty),
                                styles["Normal"],
                            ),
                            Paragraph(
                                "<font size=6>%s</font>"
                                % str(
                                    "{0:,.2f}".format(
                                        booking_line.e_Total_KG_weight
                                        if booking_line.e_Total_KG_weight is not None
                                        else ""
                                    )
                                ),
                                styles["Normal"],
                            ),
                            Paragraph("<font size=6></font>", styles["Normal"]),
                            Paragraph("<font size=6></font>", styles["Normal"]),
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
                            col6_w,
                            col7_w,
                            col8_w,
                            col9_w,
                            col10_w,
                            col11_w,
                            col12_w,
                        ),
                        rowHeights=18,
                        hAlign="LEFT",
                        style=[("GRID", (0, 0), (-1, -1), 0.5, colors.black)],
                    )
                    Story.append(tbl)

                    j += 1
                    row_cnt += 1

                    if (
                        booking_ind == len(bookings) - 1
                        and booking_line_ind == len(booking_lines) - 1
                    ):  # Add Total
                        tbl_data = [
                            [
                                Paragraph(
                                    "<font size=10><b>Total Per Booking:</b></font>",
                                    style_right,
                                ),
                                Paragraph(
                                    "<font size=10>%s</font>"
                                    % str("{:,}".format(ent_qty)),
                                    styles["Normal"],
                                ),
                                Paragraph(
                                    "<font size=10>%s</font>"
                                    % str("{0:,.2f}".format(ent_weight)),
                                    styles["Normal"],
                                ),
                                Paragraph(
                                    "<font size=10>%s</font>"
                                    % str("{0:,.2f}".format(ent_vol)),
                                    styles["Normal"],
                                ),
                                Paragraph(
                                    "<font size=10><b>Freight:</b></font>",
                                    styles["Normal"],
                                ),
                            ]
                        ]
                        tbl = Table(
                            tbl_data,
                            colWidths=(
                                col1_w
                                + col2_w
                                + col3_w
                                + col4_w
                                + col5_w
                                + col6_w
                                + col7_w
                                + col8_w,
                                col9_w,
                                col10_w,
                                col11_w,
                                col12_w,
                            ),
                            rowHeights=18,
                            hAlign="LEFT",
                            style=[("GRID", (1, 0), (-2, 0), 0.5, colors.black)],
                        )
                        Story.append(tbl)

                        if k == 0:
                            tbl_data = [
                                [
                                    Paragraph(
                                        "<font size=12><b>Driver Name:</b></font>",
                                        styles["BodyText"],
                                    ),
                                    Paragraph(
                                        "<font size=12><b>Driver Sig:</b></font>",
                                        styles["BodyText"],
                                    ),
                                    Paragraph(
                                        "<font size=12><b>Date:</b></font>",
                                        styles["BodyText"],
                                    ),
                                ]
                            ]
                        else:
                            tbl_data = [
                                [
                                    Paragraph(
                                        "<font size=12><b>Customer Name:</b></font>",
                                        styles["BodyText"],
                                    ),
                                    Paragraph(
                                        "<font size=12><b>Customer Sig:</b></font>",
                                        styles["BodyText"],
                                    ),
                                    Paragraph(
                                        "<font size=12><b>Date:</b></font>",
                                        styles["BodyText"],
                                    ),
                                ]
                            ]

                        tbl = Table(
                            tbl_data,
                            colWidths=350,
                            rowHeights=(ROWS_PER_PAGE - row_cnt) * 20,
                            hAlign="LEFT",
                            vAlign="BOTTOM",
                            style=[
                                ("TOPPADDING", (0, 0), (-1, -1), 0),
                                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                            ],
                        )
                        Story.append(tbl)
                        Story.append(
                            HRFlowable(
                                width="100%",
                                thickness=1,
                                lineCap="round",
                                color="#000000",
                                spaceBefore=1,
                                spaceAfter=1,
                                hAlign="CENTER",
                                vAlign="BOTTOM",
                                dash=None,
                            )
                        )

                        Story.append(PageBreak())

                    if row_cnt == ROWS_PER_PAGE:  # Add Sign area
                        if k == 0:
                            tbl_data = [
                                [
                                    Paragraph(
                                        "<font size=12><b>Driver Name:</b></font>",
                                        styles["BodyText"],
                                    ),
                                    Paragraph(
                                        "<font size=12><b>Driver Sig:</b></font>",
                                        styles["BodyText"],
                                    ),
                                    Paragraph(
                                        "<font size=12><b>Date:</b></font>",
                                        styles["BodyText"],
                                    ),
                                ]
                            ]
                        else:
                            tbl_data = [
                                [
                                    Paragraph(
                                        "<font size=12><b>Customer Name:</b></font>",
                                        styles["BodyText"],
                                    ),
                                    Paragraph(
                                        "<font size=12><b>Customer Sig:</b></font>",
                                        styles["BodyText"],
                                    ),
                                    Paragraph(
                                        "<font size=12><b>Date:</b></font>",
                                        styles["BodyText"],
                                    ),
                                ]
                            ]

                        tbl = Table(
                            tbl_data,
                            colWidths=350,
                            rowHeights=30,
                            hAlign="LEFT",
                            vAlign="BOTTOM",
                            style=[
                                ("TOPPADDING", (0, 0), (-1, -1), 0),
                                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                            ],
                        )
                        Story.append(tbl)

                        Story.append(
                            HRFlowable(
                                width="100%",
                                thickness=1,
                                lineCap="round",
                                color="#000000",
                                spaceBefore=1,
                                spaceAfter=1,
                                hAlign="CENTER",
                                vAlign="BOTTOM",
                                dash=None,
                            )
                        )
                        Story.append(PageBreak())
                        row_cnt = 0
                        page_cnt += 1

                # Add manifest log
                Dme_manifest_log.objects.create(
                    fk_booking_id=booking.pk_booking_id,
                    manifest_url=filename,
                    manifest_number=manifest,
                    bookings_cnt=1,
                    is_one_booking=1,
                    z_createdByAccount=username,
                    z_createdTimeStamp=timestamp,
                )

                i += 1

            except Exception as e:
                exc_type, exc_obj, exc_tb = sys.exc_info()
                fname = os.path.split(exc_tb.tb_frame.f_code.co_filename)[1]
                logger.info(f"ERROR @303 - {str(e)}")

        k += 1
    doc.build(Story)
    file.close()

    # Add manifest log
    Dme_manifest_log.objects.create(
        fk_booking_id=booking.pk_booking_id,
        manifest_url=f"{tas_au}/{filename}",
        manifest_number=manifest,
        bookings_cnt=len(bookings),
        is_one_booking=1,
        z_createdByAccount=username,
        need_truck=need_truck,
        freight_provider="TASFR",
        booking_ids=",".join(booking_ids),
    )
    manfiest_log.z_createdTimeStamp = timestamp
    manfiest_log.save()

    fp_info.fp_manifest_cnt = fp_info.fp_manifest_cnt + 1
    fp_info.new_connot_index = fp_info.new_connot_index + len(bookings)
    fp_info.save()

    return filename
