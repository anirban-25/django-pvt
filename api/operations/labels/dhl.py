# Python 3.6.6

import pysftp

cnopts = pysftp.CnOpts()
cnopts.hostkeys = None
import sys, time
import os, base64
import errno
import datetime
import uuid
import redis
import urllib, requests
import pymysql, pymysql.cursors
import json

from reportlab.lib.enums import TA_JUSTIFY, TA_RIGHT, TA_CENTER, TA_LEFT
from reportlab.pdfbase.pdfmetrics import registerFont, registerFontFamily
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.pagesizes import letter, landscape, A6, A4
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Image,
    PageBreak,
    Table,
    NextPageTemplate,
    Frame,
    PageTemplate,
)
from reportlab.platypus.flowables import Spacer, HRFlowable, PageBreak, Flowable
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.graphics.barcode import code39, code128, code93, qrencoder
from reportlab.graphics.barcode.qr import QrCodeWidget
from reportlab.graphics.barcode import eanbc, qr, usps
from reportlab.graphics.shapes import Drawing, Rect
from reportlab.pdfgen import canvas
from reportlab.graphics import renderPDF
from reportlab.lib import units
from reportlab.lib import colors
from reportlab.graphics.barcode import createBarcodeDrawing

from api.models import *
from api.fp_apis.utils import gen_consignment_num
from api.operations.api_booking_confirmation_lines import index as api_bcl

styles = getSampleStyleSheet()
style_right = ParagraphStyle(name="right", parent=styles["Normal"], alignment=TA_RIGHT)
style_left = ParagraphStyle(
    name="left", parent=styles["Normal"], alignment=TA_LEFT, leading=12
)
style_center = ParagraphStyle(
    name="center", parent=styles["Normal"], alignment=TA_CENTER, leading=10
)
styles.add(ParagraphStyle(name="Justify", alignment=TA_JUSTIFY))

if os.environ["ENV"] == "local":
    filepath = "./static/pdfs/dhl_au/"
elif os.environ["ENV"] == "dev":
    filepath = "/opt/s3_public/pdfs/dhl_au/"
elif os.environ["ENV"] == "prod":
    filepath = "/opt/s3_public/pdfs/dhl_au/"


def myFirstPage(canvas, doc):
    canvas.saveState()
    canvas.rotate(180)
    canvas.restoreState()


def myLaterPages(canvas, doc):
    canvas.saveState()
    canvas.rotate(90)
    canvas.restoreState()


class RotatedImage(Image):
    def wrap(self, availWidth, availHeight):
        h, w = Image.wrap(self, availHeight, availWidth)
        return w, h

    def draw(self):
        self.canv.rotate(90)
        Image.draw(self)


def get_barcode_rotated(
    value, width, barHeight=27.6 * mm, barWidth=1, fontSize=18, humanReadable=True
):

    barcode = createBarcodeDrawing(
        "Code128",
        value=value,
        barHeight=barHeight,
        barWidth=barWidth,
        fontSize=fontSize,
        humanReadable=humanReadable,
    )

    drawing_width = width
    barcode_scale = drawing_width / barcode.width
    drawing_height = barcode.height * barcode_scale

    drawing = Drawing(drawing_width, drawing_height)
    drawing.scale(barcode_scale, barcode_scale)
    drawing.add(barcode, name="barcode")

    drawing_rotated = Drawing(drawing_height, drawing_width)
    drawing_rotated.rotate(90)
    drawing_rotated.translate(10, -drawing_height)
    drawing_rotated.add(drawing, name="drawing")

    return drawing_rotated


def build_label(booking):
    logger.info(
        f"#110 [DHL LABEL] Started building label... (Booking ID: {booking.b_bookingID_Visual})"
    )
    v_FPBookingNumber = gen_consignment_num(
        booking.vx_freight_provider, booking.b_bookingID_Visual
    )

    try:
        if not os.path.exists(filepath):
            os.makedirs(filepath)

        # start pdf file name using naming convention
        # date = datetime.datetime.now().strftime("%Y%m%d")+"_"+datetime.datetime.now().strftime("")

        filename = (
            booking.pu_Address_State
            + "_"
            + str(booking.v_FPBookingNumber)
            + "_"
            + str(booking.b_bookingID_Visual)
            + ".pdf"
        )
        file = open(filepath + filename, "w")

        booking_lines = Booking_lines.objects.filter(
            fk_booking_id=booking.pk_booking_id
        )
        api_bcls = Api_booking_confirmation_lines.objects.filter(
            fk_booking_id=booking.pk_booking_id
        ).order_by("-id")

        totalQty = 0
        for booking_line in booking_lines:
            totalQty = totalQty + booking_line.e_qty

        label_settings = {
            "font_family": "Oswald",
            "font_size_small": "10",
            "font_size_medium": "14",
            "font_size_large": "18",
            "label_dimension_length": "150",
            "label_dimension_width": "100",
            "label_image_size_length": "138",
            "label_image_size_width": "90",
            "barcode_dimension_length": "65",
            "barcode_dimension_width": "25",
            "barcode_font_size": "18",
            "line_height_small": "5",
            "line_height_medium": "6",
            "line_height_large": "8",
        }

        doc = SimpleDocTemplate(
            filepath + filename,
            pagesize=(
                float(label_settings["label_dimension_length"]) * mm,
                float(label_settings["label_dimension_width"]) * mm,
            ),
            rightMargin=float(
                float(label_settings["label_dimension_width"])
                - float(label_settings["label_image_size_width"])
            )
            * mm,
            leftMargin=float(
                float(label_settings["label_dimension_width"])
                - float(label_settings["label_image_size_width"])
            )
            * mm,
            topMargin=float(
                float(label_settings["label_dimension_length"])
                - float(label_settings["label_image_size_length"])
            )
            * mm,
            bottomMargin=float(
                float(label_settings["label_dimension_length"])
                - float(label_settings["label_image_size_length"])
            )
            * mm,
        )

        Story = []
        j = 1

        utl_state = Utl_states.objects.get(state_code=booking.pu_Address_State)

        for booking_line in booking_lines:

            for k in range(booking_line.e_qty):

                tbl_data1 = [
                    [
                        Paragraph(
                            "<font size=%s><b>From:</b></font>"
                            % (label_settings["font_size_small"]),
                            style_left,
                        ),
                        Paragraph(
                            "<font size=%s><b>%s</b></font>"
                            % (
                                label_settings["font_size_small"],
                                "DHL(" + utl_state.sender_code + ")",
                            ),
                            styles["BodyText"],
                        ),
                    ],
                    [
                        Paragraph(
                            "<font size=%s><b>Telephone:</b></font>"
                            % label_settings["font_size_small"],
                            style_left,
                        ),
                        Paragraph(
                            "<font size=%s><b>%s</b></font>"
                            % (
                                label_settings["font_size_small"],
                                "1300362194",
                                # booking.pu_Phone_Main,
                            ),
                            styles["BodyText"],
                        ),
                    ],
                    [
                        Paragraph(
                            "<font size=%s><b>Service:</b></font>"
                            % label_settings["font_size_small"],
                            style_left,
                        ),
                        Paragraph(
                            "<font size=%s><b>%s</b></font>"
                            % (
                                label_settings["font_size_small"],
                                "PFM",
                                # booking.vx_serviceName
                                # if booking.vx_serviceName
                                # else "EXPRESS",
                            ),
                            styles["BodyText"],
                        ),
                    ],
                    [
                        Paragraph(
                            "<font size=%s><b>Via:</b></font>"
                            % label_settings["font_size_small"],
                            style_left,
                        ),
                        # Paragraph(
                        #     "<font size=%s><b>DESC</b></font>"
                        #     % label_settings["font_size_large"],
                        #     styles["BodyText"],
                        # ),
                        Paragraph(
                            "<font size=%s><b>PFM</b></font>"
                            % label_settings["font_size_large"],
                            styles["BodyText"],
                        ),
                    ],
                    [
                        Paragraph(
                            "<font size=%s><b>C/note:</b></font>"
                            % label_settings["font_size_small"],
                            style_left,
                        ),
                        Paragraph(
                            "<font size=%s><b>%s</b></font>"
                            % (
                                label_settings["font_size_medium"],
                                booking.v_FPBookingNumber,
                            ),
                            styles["BodyText"],
                        ),
                    ],
                    [
                        Paragraph(
                            "<font size=%s><b>Deliver To:</b></font>"
                            % label_settings["font_size_small"],
                            style_left,
                        ),
                        Paragraph(
                            "<font size=%s><b>%s</b></font>"
                            % (
                                label_settings["font_size_small"],
                                booking.de_to_Contact_F_LName,
                            ),
                            styles["BodyText"],
                        ),
                    ],
                ]

                from_table = {
                    "label_width": float(label_settings["label_image_size_length"])
                    * (2 / 5)
                    * (1 / 3),
                    "data_width": float(label_settings["label_image_size_length"])
                    * (2 / 5)
                    * (2 / 3),
                    "padding": 0,
                }

                t1 = Table(
                    tbl_data1,
                    colWidths=(
                        from_table["label_width"] * mm,
                        from_table["data_width"] * mm,
                    ),
                    rowHeights=(
                        float(label_settings["line_height_small"]) * mm,
                        float(label_settings["line_height_small"]) * mm,
                        float(label_settings["line_height_small"]) * mm,
                        float(label_settings["line_height_large"]) * mm,
                        float(label_settings["line_height_medium"]) * mm,
                        float(label_settings["line_height_small"]) * mm,
                    ),
                    style=[
                        ("VALIGN", (0, 0), (-1, -1), "TOP"),
                        ("TOPPADDING", (0, 0), (-1, -1), 0),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                        ("LEFTPADDING", (0, 0), (-1, -1), 0),
                        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                        # ('BOX', (0, 0), (-1, -1), 1, colors.black)
                    ],
                )

                tbl_data2 = [
                    [
                        Paragraph(
                            "<font size=%s><b>Item:&nbsp;%s of %s</b></font>"
                            % (label_settings["font_size_small"], j, sscc_cnt),
                            style_left,
                        )
                    ],
                    [
                        Paragraph(
                            "<font size=%s><b>Reference No: %s</b></font>"
                            % (
                                label_settings["font_size_small"],
                                booking.b_client_sales_inv_num,
                            ),
                            style_left,
                        )
                    ],
                    [
                        Paragraph(
                            "<font size=%s><b>Date: %s</b></font>"
                            % (
                                label_settings["font_size_small"],
                                booking.b_dateBookedDate.strftime("%d/%m/%y")
                                if booking.b_dateBookedDate
                                else "N/A",
                            ),
                            style_left,
                        )
                    ],
                ]
                t2 = Table(
                    tbl_data2,
                    colWidths=(
                        float(label_settings["label_image_size_length"]) * (2 / 5) * mm
                    ),
                    rowHeights=(
                        float(label_settings["line_height_small"]) * mm,
                        float(label_settings["line_height_small"]) * mm,
                        float(label_settings["line_height_small"]) * mm,
                    ),
                    hAlign="LEFT",
                    vAlign="TOP",
                    style=[
                        # ('BACKGROUND', (0,0), (-1,-1), colors.black),
                        ("VALIGN", (0, 0), (-1, -1), "TOP"),
                        ("TOPPADDING", (0, 0), (-1, -1), 0),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                        ("LEFTPADDING", (0, 0), (-1, -1), 0),
                        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                        # ('BOX', (0, 0), (-1, -1), 1, colors.black)
                    ],
                )

                barcode = (
                    booking.v_FPBookingNumber
                    + api_bcls[j - 1].label_code
                    + booking.de_To_Address_PostalCode
                )

                label_code = f"{booking.v_FPBookingNumber}{api_bcls[j - 1].label_code}"
                api_bcl.create(booking, [{"label_code": label_code}])

                barcode128 = get_barcode_rotated(
                    barcode,
                    (float(label_settings["barcode_dimension_length"])) * mm,
                    float(label_settings["barcode_dimension_width"]) * mm,
                    1,
                    float(label_settings["barcode_font_size"]),
                    True,
                )

                tbl_data3 = [
                    [""],
                    [barcode128],
                ]
                t3 = Table(
                    tbl_data3,
                    colWidths=(
                        float(label_settings["label_image_size_length"]) * (1 / 5) * mm
                    ),
                    rowHeights=(float(label_settings["line_height_small"]) * mm),
                    style=[
                        ("VALIGN", (0, 0), (-1, -1), "TOP"),
                        ("ALIGN", (0, 0), (-1, -1), "RIGHT"),
                        ("TOPPADDING", (0, 0), (-1, -1), 0),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                        ("LEFTPADDING", (0, 0), (-1, -1), 0),
                        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                        # ('BOX', (0, 0), (-1, -1), 1, colors.black)
                    ],
                )

                data = [[t1, t2, t3]]
                # adjust the length of tables
                t1_w = float(label_settings["label_image_size_length"]) * (2 / 5) * mm
                t2_w = float(label_settings["label_image_size_length"]) * (2 / 5) * mm
                t3_w = float(label_settings["label_image_size_length"]) * (1 / 5) * mm
                shell_table = Table(
                    data,
                    colWidths=[t1_w, t2_w, t3_w],
                    style=[
                        ("VALIGN", (0, 0), (-1, -1), "TOP"),
                        # ('SPAN',(0,0),(0,-1)),
                        ("TOPPADDING", (0, 0), (-1, -1), 0),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                        ("LEFTPADDING", (0, 0), (-1, -1), 0),
                        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                        # ('BOX', (0, 0), (-1, -1), 1, colors.black)
                    ],
                )
                Story.append(shell_table)

                tbl_data = [
                    [
                        Paragraph(
                            "<font size=%s><b>%s</b></font>"
                            % (
                                label_settings["font_size_small"],
                                booking.de_to_Contact_F_LName,
                            ),
                            style_left,
                        )
                    ],
                    [
                        Paragraph(
                            "<font size=%s><b>%s</b></font>"
                            % (
                                label_settings["font_size_small"],
                                booking.de_To_Address_Street_1,
                            ),
                            style_left,
                        )
                    ],
                    [""],
                    [
                        Paragraph(
                            "<font size=%s><b>%s</b></font> "
                            % (
                                label_settings["font_size_large"],
                                booking.de_To_Address_Suburb,
                            ),
                            style_left,
                        )
                    ],
                    [
                        Paragraph(
                            "<font size=%s><b>%s %s</b></font> "
                            % (
                                label_settings["font_size_medium"],
                                booking.de_To_Address_State,
                                booking.de_To_Address_PostalCode,
                            ),
                            style_left,
                        )
                    ],
                    [
                        Paragraph(
                            "<font size=%s><b>C/note: %s</b></font> "
                            % (
                                label_settings["font_size_small"],
                                booking.v_FPBookingNumber,
                            ),
                            style_left,
                        )
                    ],
                    [
                        Paragraph(
                            "<font size=%s><b>Total Items %s</b></font> "
                            % (label_settings["font_size_small"], str(totalQty)),
                            style_left,
                        )
                    ],
                ]
                t1 = Table(
                    tbl_data,
                    colWidths=(
                        (float(label_settings["label_image_size_length"]) * (3 / 5))
                        * mm
                    ),
                    rowHeights=(
                        float(label_settings["line_height_small"]) * mm,
                        float(label_settings["line_height_small"]) * mm,
                        float(label_settings["line_height_small"]) * mm,
                        float(label_settings["line_height_large"]) * mm,
                        float(label_settings["line_height_medium"]) * mm,
                        float(label_settings["line_height_small"]) * mm,
                        float(label_settings["line_height_small"]) * mm,
                    ),
                    style=[
                        ("LEFTPADDING", (0, 0), (-1, -1), 5),
                        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                        ("TOPPADDING", (0, 0), (-1, -1), 5),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                        ("BOTTOMMARGIN", (0, 0), (-1, -1), 5),
                        ("BOX", (0, 0), (-1, -1), 1, colors.black),
                    ],
                )

                tbl_data = [
                    [
                        Paragraph(
                            "<font size=%s color=%s><b>S%s</b></font>"
                            % (
                                label_settings["font_size_large"],
                                colors.white,
                                str(j).zfill(2),
                            ),
                            style_left,
                        )
                    ],
                    [""],
                ]
                t2 = Table(
                    tbl_data,
                    colWidths=(
                        (float(label_settings["label_image_size_length"]) * (1 / 5) - 8)
                        * mm
                    ),
                    rowHeights=(
                        float(label_settings["line_height_large"]) * mm,
                        float(label_settings["line_height_small"]) * mm,
                    ),
                    style=[
                        ("BACKGROUND", (0, 0), (-1, 0), colors.black),
                        ("SPAN", (0, 0), (-1, -1)),
                        ("LEFTPADDING", (0, 0), (-1, -1), 13),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 14),
                        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                    ],
                )

                tbl_data = [[""]]
                t3 = Table(
                    tbl_data,
                    colWidths=(
                        float(label_settings["label_image_size_length"]) * (1 / 5) * mm
                    ),
                    style=[
                        ("VALIGN", (0, 0), (0, -1), "TOP"),
                        # ('BOX', (0, 0), (-1, -1), 1, colors.black)
                    ],
                )

                data = [[t1, t2, t3]]
                # adjust the length of tables
                t1_w = (
                    float(label_settings["label_image_size_length"]) * (3 / 5) + 5
                ) * mm
                t2_w = float(label_settings["label_image_size_length"]) * (1 / 5) * mm
                t3_w = float(label_settings["label_image_size_length"]) * (1 / 5) * mm
                shell_table = Table(
                    data,
                    colWidths=[t1_w, t2_w, t3_w],
                    style=[
                        ("TOPPADDING", (0, 0), (-1, -1), 0),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                        ("LEFTPADDING", (0, 0), (-1, -1), 0),
                        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                        # ('BOX', (0, 0), (-1, -1), 1, colors.black)
                    ],
                )
                Story.append(shell_table)

                Story.append(Spacer(1, 5))

                tbl_data = [
                    [
                        Paragraph(
                            "<font size=%s><b>Special Inst:</b></font>"
                            % label_settings["font_size_small"],
                            style_left,
                        ),
                    ],
                    [
                        Paragraph(
                            "<font size=%s><b>%s %s</b></font>"
                            % (
                                label_settings["font_size_small"],
                                str(booking.de_to_PickUp_Instructions_Address)
                                if booking.de_to_PickUp_Instructions_Address
                                else "Instructions",
                                str(booking.de_to_Pick_Up_Instructions_Contact)
                                if booking.de_to_Pick_Up_Instructions_Contact
                                else "Go to Special Inst",
                            ),
                            style_left,
                        )
                    ],
                ]
                t1 = Table(
                    tbl_data,
                    colWidths=(
                        (float(label_settings["label_image_size_length"]) * (4 / 5))
                        * mm
                    ),
                    rowHeights=(
                        float(label_settings["line_height_small"]) * mm,
                        float(label_settings["line_height_small"]) * mm * 2 / 5,
                    ),
                    style=[
                        ("VALIGN", (0, 0), (0, -1), "TOP"),
                        ("TOPPADDING", (0, 0), (-1, -1), 0),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                        ("LEFTPADDING", (0, 0), (0, -1), 0),
                        ("RIGHTPADDING", (0, 0), (0, -1), 0),
                        # ('BOX', (0, 0), (-1, -1), 1, colors.black)
                    ],
                )

                tbl_data = [[""]]
                t2 = Table(
                    tbl_data,
                    colWidths=(
                        (
                            float(label_settings["label_image_size_length"])
                            * (1 / 5)
                            * (1 / 2)
                        )
                        * mm
                    ),
                    rowHeights=(float(label_settings["line_height_large"]) * mm),
                    vAlign="MIDDLE",
                    style=[
                        ("TEXTCOLOR", (0, 0), (0, -1), colors.white),
                        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                        # ('BOX', (0, 0), (-1, -1), 1, colors.black)
                    ],
                )

                tbl_data = [[""]]
                t3 = Table(
                    tbl_data,
                    colWidths=(
                        (
                            float(label_settings["label_image_size_length"])
                            * (1 / 5)
                            * (1 / 2)
                        )
                        * mm
                    ),
                    style=[
                        ("VALIGN", (0, 0), (0, -1), "TOP"),
                        # ('BOX', (0, 0), (-1, -1), 1, colors.black)
                    ],
                )

                data = [[t1, t2, t3]]
                # adjust the length of tables
                t1_w = (float(label_settings["label_image_size_length"]) * (4 / 5)) * mm
                t2_w = (
                    float(label_settings["label_image_size_length"]) * (1 / 5) * (1 / 2)
                ) * mm
                t3_w = (
                    float(label_settings["label_image_size_length"]) * (1 / 5) * (1 / 2)
                ) * mm
                shell_table = Table(
                    data,
                    colWidths=[t1_w, t2_w, t3_w],
                    style=[
                        ("TOPPADDING", (0, 0), (-1, -1), 0),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                        ("LEFTPADDING", (0, 0), (-1, -1), 0),
                        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                        # ('BOX', (0, 0), (-1, -1), 1, colors.black)
                    ],
                )
                Story.append(shell_table)
                Story.append(PageBreak())
                j += 1

        doc.build(Story, onFirstPage=myFirstPage, onLaterPages=myLaterPages)
        file.close()
    except Exception as e:
        exc_type, exc_obj, exc_tb = sys.exc_info()
        fname = os.path.split(exc_tb.tb_frame.f_code.co_filename)[1]
        # print(dir(exc_type), fname, exc_tb.tb_lineno)
        # print("Error: unable to fecth data")
        # print("Error1: " + str(e))

    logger.info(
        f"#119 [DHL LABEL] Finished building label... (Booking ID: {booking.b_bookingID_Visual})"
    )
    return filepath, filename
