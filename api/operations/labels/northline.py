# Python 3.6.6

import pysftp

from api.helpers.cubic import get_cubic_meter

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
import logging
import time

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
    TableStyle,
)
from reportlab.platypus.flowables import Spacer, HRFlowable, PageBreak, Flowable
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm, inch
from reportlab.graphics.barcode import code39, code128, code93, qrencoder
from reportlab.graphics.barcode.qr import QrCodeWidget
from reportlab.graphics.barcode import eanbc, qr, usps
from reportlab.graphics.shapes import Drawing, Rect
from reportlab.pdfgen import canvas
from reportlab.graphics import renderPDF
from reportlab.lib import units
from reportlab.lib import colors
from reportlab.graphics.barcode import createBarcodeDrawing

from api.models import Booking_lines, FPRouting, Fp_freight_providers
from api.operations.email_senders import send_email_to_admins
from api.operations.api_booking_confirmation_lines import index as api_bcl
from api.fp_apis.utils import gen_consignment_num
from reportlab.platypus.flowables import KeepInFrame

logger = logging.getLogger("dme_api")

styles = getSampleStyleSheet()
style_right = ParagraphStyle(name="right", parent=styles["Normal"], alignment=TA_RIGHT)
style_left = ParagraphStyle(
    name="left", parent=styles["Normal"], alignment=TA_LEFT, leading=12
)
style_left_extra_large = ParagraphStyle(
    name="left", parent=styles["Normal"], alignment=TA_LEFT, leading=28
)
style_center = ParagraphStyle(
    name="center", parent=styles["Normal"], alignment=TA_CENTER, leading=10
)
style_left_noleading = ParagraphStyle(
    name="left",
    parent=styles["Normal"],
    alignment=TA_LEFT,
    leading=4,
)
style_left_header = ParagraphStyle(
    name="left",
    parent=styles["Normal"],
    alignment=TA_LEFT,
    leading=8,
)
style_left_white = ParagraphStyle(
    name="left",
    parent=styles["Normal"],
    alignment=TA_LEFT,
    leading=10,
    textColor="white",
)
style_right_white = ParagraphStyle(
    name="left",
    parent=styles["Normal"],
    alignment=TA_RIGHT,
    leading=10,
    textColor="white",
)
style_center_noleading = ParagraphStyle(
    name="center",
    parent=styles["Normal"],
    alignment=TA_CENTER,
    leading=4,
)
style_right_noleading = ParagraphStyle(
    name="right",
    parent=styles["Normal"],
    alignment=TA_RIGHT,
    leading=4,
)

style_reference_text = ParagraphStyle(
    name="left",
    parent=styles["Normal"],
    leading=8,
    spaceBefore=0,
)

style_desc_text = ParagraphStyle(
    name="left",
    parent=styles["Normal"],
    leading=14,
    spaceBefore=0,
)

style_footer_text = ParagraphStyle(
    name="left",
    parent=styles["Normal"],
    leading=10,
    spaceBefore=0,
    textTransform="uppercase",
)

styles.add(ParagraphStyle(name="Justify", alignment=TA_JUSTIFY))


def myFirstPage(canvas, doc):
    canvas.saveState()
    canvas.rotate(180)
    canvas.restoreState()


def myLaterPages(canvas, doc):
    canvas.saveState()
    canvas.rotate(90)
    canvas.restoreState()


def gen_barcode(booking, v_FPBookingNumber, line_index):
    item_index = str(line_index).zfill(3)
    label_code = f"{v_FPBookingNumber}{item_index}"
    api_bcl.create(booking, [{"label_code": label_code}])

    return label_code


from reportlab.platypus.flowables import Flowable


class verticalText(Flowable):

    """Rotates a text in a table cell."""

    def __init__(self, text):
        Flowable.__init__(self)
        self.text = text

    def draw(self):
        canvas = self.canv
        canvas.rotate(90)
        fs = canvas._fontsize
        canvas.translate(1, -fs / 1.2)  # canvas._leading?
        canvas.drawString(0, 0, self.text)

    def wrap(self, aW, aH):
        canv = self.canv
        fn, fs = canv._fontname, canv._fontsize
        return canv._leading, 1 + canv.stringWidth(self.text, fn, fs)


from reportlab.platypus.flowables import Image


class RotatedImage(Image):
    def wrap(self, availWidth, availHeight):
        h, w = Image.wrap(self, availHeight, availWidth)
        return w, h

    def draw(self):
        self.canv.rotate(90)
        Image.draw(self)


def get_meter(value, uom="METER"):
    _dimUOM = uom.upper()

    if _dimUOM in ["MM", "MILIMETER"]:
        value = value / 1000
    elif _dimUOM in ["CM", "CENTIMETER"]:
        value = value / 100

    return round(value, 2)


def build_label(
    booking,
    filepath,
    pre_data,
    lines,
    label_index,
    sscc,
    sscc_cnt=1,
    one_page_label=True,
):
    logger.info(
        f"#110 [NORTHLINE LABEL] Started building label... (Booking ID: {booking.b_bookingID_Visual}, Lines: {lines})"
    )
    v_FPBookingNumber = pre_data["v_FPBookingNumber"]

    if not lines:
        lines = Booking_lines.objects.filter(fk_booking_id=booking.pk_booking_id)

    if not os.path.exists(filepath):
        os.makedirs(filepath)

    if lines:
        if sscc:
            filename = (
                booking.pu_Address_State
                + "_"
                + str(booking.b_bookingID_Visual)
                + "_"
                + str(sscc)
            )
        else:
            filename = (
                booking.pu_Address_State
                + "_"
                + str(booking.b_bookingID_Visual)
                + "_"
                + str(lines[0].pk)
            )
    else:
        filename = (
            booking.pu_Address_State
            + "_"
            + v_FPBookingNumber
            + "_"
            + str(booking.b_bookingID_Visual)
        )

    file = open(f"{filepath}/{filename}.pdf", "w")
    file = open(f"{filepath}/{filename}_consignment.pdf", "w")
    logger.info(f"#111 [NORTHLINE LABEL] File full path: {filepath}/{filename}.pdf")

    label_settings = {
        "font_family": "Verdana",
        "font_size_smallest": "3",
        "font_size_extra_small": "4",
        "font_size_small": "6",
        "font_size_extra_medium": "7",
        "font_size_medium": "8",
        "font_size_large": "10",
        "font_size_slight_large": "12",
        "font_size_extra_large": "36",
        "label_dimension_length": "100",
        "label_dimension_width": "150",
        "label_image_size_length": "95",
        "label_image_size_width": "130",
        "barcode_dimension_length": "85",
        "barcode_dimension_width": "30",
        "barcode_font_size": "18",
        "line_height_extra_small": "3",
        "line_height_small": "5",
        "line_height_medium": "6",
        "line_height_large": "8",
        "line_height_extra_large": "12",
        "margin_v": "0",
        "margin_h": "0",
        "font_size_footer_units_small": "8",
        "font_size_footer_desc_small": "9",
        "font_size_footer_desc": "10",
        "font_size_footer_units": "12",
        "font_size_footer": "14",
    }

    width = float(label_settings["label_dimension_length"]) * mm
    height = float(label_settings["label_dimension_width"]) * mm

    doc = SimpleDocTemplate(
        f"{filepath}/{filename}.pdf",
        pagesize=(width, height),
        rightMargin=float(label_settings["margin_h"]) * mm,
        leftMargin=float(label_settings["margin_h"]) * mm,
        topMargin=float(label_settings["margin_v"]) * mm,
        bottomMargin=float(label_settings["margin_v"]) * mm,
    )

    doc_consignment = SimpleDocTemplate(
        f"{filepath}/{filename}_consignment.pdf",
        pagesize=(width, height),
        rightMargin=float(label_settings["margin_h"]) * mm,
        leftMargin=float(label_settings["margin_h"]) * mm,
        topMargin=float(label_settings["margin_v"]) * mm,
        bottomMargin=float(label_settings["margin_v"]) * mm,
    )

    dme_logo = "./static/assets/logos/dme.png"
    dme_img = Image(dme_logo, 30 * mm, 7.7 * mm)

    de_suburb = booking.de_To_Address_Suburb
    de_postcode = booking.de_To_Address_PostalCode
    de_state = booking.de_To_Address_State

    j = 1

    totalQty = 0
    if one_page_label:
        lines = [lines[0]]
        totalQty = 1
    else:
        for booking_line in lines:
            totalQty += booking_line.e_qty

    if sscc:
        j = 1 + label_index
        totalQty = sscc_cnt

    Story = []
    Story_consignment = []

    logger.info(
        f"#110 [NORTHLINE LABEL] Started building Delivery's copy... (Booking ID: {booking.b_bookingID_Visual})"
    )

    column_width = float(label_settings["label_image_size_length"]) * (1 / 3) * mm
    tbl_data = [
        [
            Paragraph(
                "<font size=%s><b>Date: %s</b></font>"
                % (
                    label_settings["font_size_extra_medium"],
                    booking.b_dateBookedDate.strftime("%d/%m/%Y")
                    if booking.b_dateBookedDate
                    else "18/08/2023",
                ),
                style_left_white,
            ),
            Image(dme_logo, 20 * mm, 5 * mm),
            Paragraph(
                "<font size=%s><b>RECEIVER'S COPY</b></font>"
                % (label_settings["font_size_extra_medium"],),
                style_right_white,
            ),
        ]
    ]
    header = Table(
        tbl_data,
        colWidths=[column_width, column_width, column_width],
        rowHeights=[6 * mm],
        style=[
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("ALIGN", (0, 0), (0, 0), "LEFT"),
            ("ALIGN", (1, 0), (1, 0), "CENTER"),
            ("ALIGN", (2, 0), (2, 0), "RIGHT"),
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ("LEFTPADDING", (0, 0), (-1, -1), 5),
            ("RIGHTPADDING", (0, 0), (-1, -1), 5),
            ("BACKGROUND", (0, 0), (-1, -1), colors.black),
            ("TEXTCOLOR", (0, 0), (-1, -1), colors.white),
        ],
    )

    tbl_data = [
        [
            Paragraph(
                "<font size=%s><b>Date: %s</b></font>"
                % (
                    label_settings["font_size_extra_medium"],
                    booking.b_dateBookedDate.strftime("%d/%m/%Y")
                    if booking.b_dateBookedDate
                    else "18/08/2023",
                ),
                style_left_white,
            ),
            Image(dme_logo, 20 * mm, 5 * mm),
            Paragraph(
                "<font size=%s><b>PROOF OF DELIVERY COPY</b></font>"
                % (label_settings["font_size_extra_medium"],),
                style_right_white,
            ),
        ]
    ]
    header_pod = Table(
        tbl_data,
        colWidths=[column_width, column_width * (2 / 3), column_width * (4 / 3)],
        rowHeights=[6 * mm],
        style=[
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("ALIGN", (0, 0), (0, 0), "LEFT"),
            ("ALIGN", (1, 0), (1, 0), "CENTER"),
            ("ALIGN", (2, 0), (2, 0), "RIGHT"),
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ("LEFTPADDING", (0, 0), (-1, -1), 5),
            ("RIGHTPADDING", (0, 0), (-1, -1), 5),
            ("BACKGROUND", (0, 0), (-1, -1), colors.black),
            ("TEXTCOLOR", (0, 0), (-1, -1), colors.white),
        ],
    )

    tbl_data = [
        [
            Paragraph(
                "<font size=%s>CHARGE TO: </font>"
                % (label_settings["font_size_smallest"],),
                style_left_noleading,
            ),
        ],
        [
            Paragraph(
                "<font size=%s><b>%s</b></font>"
                % (
                    label_settings["font_size_extra_small"],
                    v_FPBookingNumber[:-3] if len(v_FPBookingNumber) >= 3 else "9DEL01",
                ),
                style_left_noleading,
            ),
        ],
        [Spacer(1, 5)],
        [
            Paragraph(
                "<font size=%s>CUST REF: </font>"
                % (label_settings["font_size_smallest"],),
                style_left_noleading,
            ),
        ],
        [
            Paragraph(
                "<font size=%s><b>%s</b></font>"
                % (
                    label_settings["font_size_extra_small"],
                    booking.b_client_order_num or "",
                ),
                style_left_noleading,
            ),
        ],
    ]

    left_table = Table(
        tbl_data,
        colWidths=(column_width),
        # rowHeights=(float(label_settings["line_height_small"]) * mm),
        style=[
            ("ALIGN", (0, 0), (-1, -1), "LEFT"),
            ("VALIGN", (0, 0), (0, -1), "TOP"),
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ],
    )

    tbl_data = [
        [
            Paragraph(
                "<font size=%s>CONSIGNMENT: </font>"
                % (label_settings["font_size_smallest"],),
                style_left_noleading,
            ),
        ],
        [
            Paragraph(
                "<font size=%s>%s</font>"
                % (
                    label_settings["font_size_small"],
                    v_FPBookingNumber,
                ),
                style_left_noleading,
            ),
        ],
    ]

    right_table = Table(
        tbl_data,
        colWidths=(column_width),
        style=[
            ("ALIGN", (0, 0), (-1, -1), "LEFT"),
            ("VALIGN", (0, 0), (0, -1), "TOP"),
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ],
    )

    barcode = v_FPBookingNumber

    tbl_data = [
        [code128.Code128(barcode, barHeight=5 * mm, barWidth=0.6, humanReadable=False)],
        [
            Paragraph(
                "<font size=%s>%s</font>"
                % (label_settings["font_size_small"], barcode),
                style_center,
            ),
        ],
    ]

    table_barcode = Table(
        tbl_data,
        colWidths=(column_width),
        style=[
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("VALIGN", (0, 0), (0, -1), "TOP"),
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ("LEFTPADDING", (0, 0), (0, -1), 0),
            ("RIGHTPADDING", (0, 0), (0, -1), 0),
            # ('BOX', (0, 0), (-1, -1), 1, colors.black)
        ],
    )

    barcode_section = Table(
        [[left_table, table_barcode, right_table]],
        colWidths=[column_width, column_width, column_width],
        style=[
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("ALIGN", (0, 0), (-1, -1), "LEFT"),
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMBORDER", (0, 0), (-1, -1), 0),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ],
    )

    tbl_data = [
        [
            Paragraph(
                "<font size=%s><b>%s</b></font>"
                % (
                    label_settings["font_size_extra_small"],
                    (booking.puCompany or "")[:30],
                ),
                style_left_noleading,
            ),
        ],
        [
            Paragraph(
                "<font size=%s><b>%s</b></font>"
                % (
                    label_settings["font_size_extra_small"],
                    (booking.pu_Address_Street_1 or booking.pu_Address_street_2 or "")[
                        :30
                    ],
                ),
                style_left_noleading,
            ),
        ],
        [
            Paragraph(
                "<font size=%s><b>%s, %s, %s</b></font>"
                % (
                    label_settings["font_size_extra_small"],
                    (booking.pu_Address_Suburb or "")[:30],
                    booking.pu_Address_State or "",
                    booking.pu_Address_PostalCode or "",
                ),
                style_left_noleading,
            ),
        ],
    ]

    left_table = Table(
        tbl_data,
        colWidths=(column_width),
        style=[
            ("ALIGN", (0, 0), (-1, -1), "LEFT"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("TOPPADDING", (0, 0), (0, 0), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ],
    )

    tbl_data = [
        [
            Paragraph(
                "<font size=%s><b>%s</b></font>"
                % (
                    label_settings["font_size_extra_small"],
                    (booking.deToCompanyName or "")[:30],
                ),
                style_left_noleading,
            ),
        ],
        [
            Paragraph(
                "<font size=%s><b>%s</b></font>"
                % (
                    label_settings["font_size_extra_small"],
                    (
                        booking.de_To_Address_Street_1
                        or booking.de_To_Address_Street_2
                        or ""
                    )[:30],
                ),
                style_left_noleading,
            ),
        ],
        [
            Paragraph(
                "<font size=%s><b>%s, %s, %s</b></font>"
                % (
                    label_settings["font_size_extra_small"],
                    (booking.de_To_Address_Suburb[:30] or ""),
                    booking.de_To_Address_State or "",
                    booking.de_To_Address_PostalCode or "",
                ),
                style_left_noleading,
            ),
        ],
        [
            Paragraph(
                "<font size=%s><b>Ph: %s</b></font>"
                % (
                    label_settings["font_size_extra_small"],
                    booking.de_to_Phone_Main or "",
                ),
                style_left_noleading,
            ),
        ],
    ]

    middle_table = Table(
        tbl_data,
        colWidths=(column_width),
        style=[
            ("ALIGN", (0, 0), (-1, -1), "LEFT"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("TOPPADDING", (0, 0), (0, 0), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ],
    )

    # Special Instructions
    specialInstructions = ""
    if booking.pu_pickup_instructions_address:
        specialInstructions += booking.pu_pickup_instructions_address
    if booking.pu_PickUp_Instructions_Contact:
        specialInstructions += f" {booking.pu_PickUp_Instructions_Contact}"
    if booking.de_to_PickUp_Instructions_Address:
        specialInstructions += f" {booking.de_to_PickUp_Instructions_Address}"
    if booking.de_to_Pick_Up_Instructions_Contact:
        specialInstructions += f" {booking.de_to_Pick_Up_Instructions_Contact}"

    tbl_data = [
        [
            Paragraph(
                "<font size=%s>%s</font>"
                % (
                    label_settings["font_size_extra_small"],
                    specialInstructions,
                ),
                style_left_noleading,
            ),
        ],
    ]

    right_table = Table(
        tbl_data,
        colWidths=(column_width),
        style=[
            ("ALIGN", (0, 0), (-1, -1), "LEFT"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("TOPPADDING", (0, 0), (0, 0), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ],
    )

    tbl_data = [
        [
            Paragraph(
                "<font size=%s>SENDER: </font>"
                % (label_settings["font_size_smallest"],),
                style_left_noleading,
            ),
            Paragraph(
                "<font size=%s>RECEIVER: </font>"
                % (label_settings["font_size_smallest"],),
                style_left_noleading,
            ),
            Paragraph(
                "<font size=%s>SPECIAL INSTRUCTIONS: </font>"
                % (label_settings["font_size_smallest"],),
                style_left_noleading,
            ),
        ],
        [
            left_table,
            middle_table,
            right_table,
        ],
    ]

    middle_table_section = Table(
        tbl_data,
        colWidths=[column_width, column_width, column_width],
        style=[
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("ALIGN", (0, 0), (-1, -1), "LEFT"),
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ("TOPPADDING", (0, 0), (-1, 0), 3),
            ("BOTTOMPADDING", (0, 0), (-1, 0), 4),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ("LINEABOVE", (0, 0), (-1, 0), 0.6, colors.gray),
            ("LINEBELOW", (0, 0), (-1, 0), 0.6, colors.gray),
        ],
    )

    tbl_data = [
        [
            Paragraph(
                "<font size=%s>REFEREMCE</font>"
                % (label_settings["font_size_smallest"],),
                style_left_noleading,
            ),
            Paragraph(
                "<font size=%s>DESCRIPTION</font>"
                % (label_settings["font_size_smallest"],),
                style_left_noleading,
            ),
            Paragraph(
                "<font size=%s>QTY</font>" % (label_settings["font_size_smallest"],),
                style_center_noleading,
            ),
            Paragraph(
                "<font size=%s>UNIT (KG)</font>"
                % (label_settings["font_size_smallest"],),
                style_center_noleading,
            ),
            Paragraph(
                "<font size=%s>TOTAL (KG)</font>"
                % (label_settings["font_size_smallest"],),
                style_center_noleading,
            ),
            Paragraph(
                "<font size=%s>L (M)</font>" % (label_settings["font_size_smallest"],),
                style_center_noleading,
            ),
            Paragraph(
                "<font size=%s>W (M)</font>" % (label_settings["font_size_smallest"],),
                style_center_noleading,
            ),
            Paragraph(
                "<font size=%s>H (M)</font>" % (label_settings["font_size_smallest"],),
                style_center_noleading,
            ),
            Paragraph(
                "<font size=%s>UNIT (M3)</font>"
                % (label_settings["font_size_smallest"],),
                style_center_noleading,
            ),
            Paragraph(
                "<font size=%s>TOTAL (M3)</font>"
                % (label_settings["font_size_smallest"],),
                style_center_noleading,
            ),
        ],
    ]

    detail_header_table = Table(
        tbl_data,
        colWidths=(
            float(label_settings["label_image_size_length"]) * (3 / 15) * mm,
            float(label_settings["label_image_size_length"]) * (4 / 15) * mm,
            float(label_settings["label_image_size_length"]) * (1 / 15) * mm,
            float(label_settings["label_image_size_length"]) * (1 / 15) * mm,
            float(label_settings["label_image_size_length"]) * (1 / 15) * mm,
            float(label_settings["label_image_size_length"]) * (1 / 15) * mm,
            float(label_settings["label_image_size_length"]) * (1 / 15) * mm,
            float(label_settings["label_image_size_length"]) * (1 / 15) * mm,
            float(label_settings["label_image_size_length"]) * (1 / 15) * mm,
            float(label_settings["label_image_size_length"]) * (1 / 15) * mm,
        ),
        # rowHeights=(float(label_settings["line_height_small"]) * mm),
        style=[
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("ALIGN", (0, 0), (-1, -1), "LEFT"),
            ("ALIGN", (2, 0), (-1, -1), "CENTER"),
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ("TOPPADDING", (0, 0), (-1, 0), 3),
            ("BOTTOMPADDING", (0, 0), (-1, 0), 4),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ("LINEABOVE", (0, 0), (-1, 0), 0.6, colors.gray),
            ("LINEBELOW", (0, 0), (-1, 0), 0.6, colors.gray),
            ("LINEBEFORE", (3, 0), (4, -1), 0.6, colors.gray),
            ("LINEBEFORE", (8, 0), (9, -1), 0.6, colors.gray),
            ("LINEAFTER", (3, 0), (4, -1), 0.6, colors.gray),
            ("LINEAFTER", (8, 0), (8, -1), 0.6, colors.gray),
        ],
    )

    tbl_data_row = []
    tbl_data = []
    total_qty = 0
    total_weight = 0
    total_cubic = 0
    for line in lines:
        tbl_data_row = [
            Paragraph(
                "<font size=%s><b>%s</b></font>"
                % (label_settings["font_size_extra_small"], (line.gap_ras or "")[:30]),
                style_left_noleading,
            ),
            Paragraph(
                "<font size=%s><b>%s</b></font>"
                % (label_settings["font_size_extra_small"], line.e_item[:20]),
                style_left_noleading,
            ),
            Paragraph(
                "<font size=%s><b>%s</b></font>"
                % (label_settings["font_size_extra_small"], line.e_qty),
                style_center_noleading,
            ),
            Paragraph(
                "<font size=%s><b>%s</b></font>"
                % (
                    label_settings["font_size_extra_small"],
                    round(line.e_weightPerEach, 3),
                ),
                style_center_noleading,
            ),
            Paragraph(
                "<font size=%s><b>%s</b></font>"
                % (
                    label_settings["font_size_extra_small"],
                    round(line.e_qty * line.e_weightPerEach, 3),
                ),
                style_center_noleading,
            ),
            Paragraph(
                "<font size=%s><b>%s</b></font>"
                % (
                    label_settings["font_size_extra_small"],
                    get_meter(line.e_dimLength, line.e_dimUOM),
                ),
                style_center_noleading,
            ),
            Paragraph(
                "<font size=%s><b>%s</b></font>"
                % (
                    label_settings["font_size_extra_small"],
                    get_meter(line.e_dimWidth, line.e_dimUOM),
                ),
                style_center_noleading,
            ),
            Paragraph(
                "<font size=%s><b>%s</b></font>"
                % (
                    label_settings["font_size_extra_small"],
                    get_meter(line.e_dimHeight, line.e_dimUOM),
                ),
                style_center_noleading,
            ),
            Paragraph(
                "<font size=%s><b>%s</b></font>"
                % (
                    label_settings["font_size_extra_small"],
                    round(
                        get_cubic_meter(
                            line.e_dimLength,
                            line.e_dimWidth,
                            line.e_dimHeight,
                            line.e_dimUOM,
                        ),
                        3,
                    ),
                ),
                style_center_noleading,
            ),
            Paragraph(
                "<font size=%s><b>%s</b></font>"
                % (
                    label_settings["font_size_extra_small"],
                    round(
                        get_cubic_meter(
                            line.e_dimLength,
                            line.e_dimWidth,
                            line.e_dimHeight,
                            line.e_dimUOM,
                            line.e_qty,
                        ),
                        3,
                    ),
                ),
                style_center_noleading,
            ),
        ]
        tbl_data.append(tbl_data_row)
        total_qty = total_qty + line.e_qty
        total_weight = total_weight + line.e_qty * line.e_weightPerEach
        total_cubic = total_cubic + get_cubic_meter(
            line.e_dimLength,
            line.e_dimWidth,
            line.e_dimHeight,
            line.e_dimUOM,
            line.e_qty,
        )

    tbl_data.append(
        [
            "",
            "",
            Paragraph(
                "<font size=%s><b>%s</b></font>"
                % (label_settings["font_size_extra_small"], total_qty),
                style_center_noleading,
            ),
            "",
            Paragraph(
                "<font size=%s><b>%s</b></font>"
                % (label_settings["font_size_extra_small"], round(total_weight, 2)),
                style_center_noleading,
            ),
            "",
            "",
            "",
            "",
            Paragraph(
                "<font size=%s><b>%s</b></font>"
                % (label_settings["font_size_extra_small"], round(total_cubic, 3)),
                style_center_noleading,
            ),
        ],
    )

    detail_body_table = Table(
        tbl_data,
        colWidths=(
            float(label_settings["label_image_size_length"]) * (3 / 15) * mm,
            float(label_settings["label_image_size_length"]) * (4 / 15) * mm,
            float(label_settings["label_image_size_length"]) * (1 / 15) * mm,
            float(label_settings["label_image_size_length"]) * (1 / 15) * mm,
            float(label_settings["label_image_size_length"]) * (1 / 15) * mm,
            float(label_settings["label_image_size_length"]) * (1 / 15) * mm,
            float(label_settings["label_image_size_length"]) * (1 / 15) * mm,
            float(label_settings["label_image_size_length"]) * (1 / 15) * mm,
            float(label_settings["label_image_size_length"]) * (1 / 15) * mm,
            float(label_settings["label_image_size_length"]) * (1 / 15) * mm,
        ),
        rowHeights=(2 * mm),
        style=[
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("ALIGN", (0, 0), (-1, -1), "LEFT"),
            ("ALIGN", (2, 0), (-1, -1), "CENTER"),
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("TOPPADDING", (0, 0), (0, -1), 2),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ("LINEBEFORE", (3, 0), (4, -1), 0.6, colors.gray),
            ("LINEBEFORE", (8, 0), (9, -2), 0.6, colors.gray),
            ("LINEBEFORE", (9, -1), (9, -1), 0.6, colors.gray),
            ("LINEAFTER", (3, 0), (4, -1), 0.6, colors.gray),
            ("LINEAFTER", (8, 0), (8, -1), 0.6, colors.gray),
            ("LINEBELOW", (0, -2), (-1, -2), 0.6, colors.gray),
            ("LINEBELOW", (2, -1), (-1, -1), 0.6, colors.gray),
        ],
    )

    tbl_data = [
        [
            Paragraph(
                "<font size=%s>DANGEROUS GOODS DESCRIPTION</font>"
                % (label_settings["font_size_smallest"],),
                style_left_noleading,
            ),
            Paragraph(
                "<font size=%s></font>" % (label_settings["font_size_smallest"],),
                style_left_noleading,
            ),
            Paragraph(
                "<font size=%s>DG CLASS</font>"
                % (label_settings["font_size_smallest"],),
                style_center_noleading,
            ),
            Paragraph(
                "<font size=%s>DG SUBCLASS</font>"
                % (label_settings["font_size_smallest"],),
                style_left_noleading,
            ),
            Paragraph(
                "<font size=%s>DG PACKING TYPE</font>"
                % (label_settings["font_size_smallest"],),
                style_left_noleading,
            ),
            Paragraph(
                "<font size=%s>NO OF PACKS</font>"
                % (label_settings["font_size_smallest"],),
                style_left_noleading,
            ),
            Paragraph(
                "<font size=%s>DG PACK GROUP</font>"
                % (label_settings["font_size_smallest"],),
                style_left_noleading,
            ),
            Paragraph(
                "<font size=%s>DG QTY</font>" % (label_settings["font_size_smallest"],),
                style_left_noleading,
            ),
            Paragraph(
                "<font size=%s>UN NUMBER</font>"
                % (label_settings["font_size_smallest"],),
                style_right_noleading,
            ),
        ],
    ]

    dangerous_table = Table(
        tbl_data,
        colWidths=(
            float(label_settings["label_image_size_length"]) * (7 / 24) * mm,
            float(label_settings["label_image_size_length"]) * (1 / 24) * mm,
            float(label_settings["label_image_size_length"]) * (1 / 6) * mm,
            float(label_settings["label_image_size_length"]) * (1 / 12) * mm,
            float(label_settings["label_image_size_length"]) * (1 / 12) * mm,
            float(label_settings["label_image_size_length"]) * (1 / 12) * mm,
            float(label_settings["label_image_size_length"]) * (1 / 12) * mm,
            float(label_settings["label_image_size_length"]) * (1 / 12) * mm,
            float(label_settings["label_image_size_length"]) * (1 / 12) * mm,
        ),
        rowHeights=(float(label_settings["line_height_small"]) * mm),
        style=[
            ("ALIGN", (0, 0), (-1, -1), "LEFT"),
            ("ALIGN", (-1, 0), (-1, 0), "RIGHT"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("LEFTPADDING", (0, 0), (-1, 0), 1),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, 0), 1),
            ("LINEBELOW", (0, -1), (0, -1), 0.6, colors.gray),
            ("LINEBELOW", (2, -1), (-1, -1), 0.6, colors.gray),
        ],
    )

    tbl_data = [
        [
            Paragraph(
                "<font size=%s>PALLET TYPE</font>"
                % (label_settings["font_size_smallest"],),
                style_left_noleading,
            ),
            Paragraph(
                "<font size=%s>TRANSACTION</font>"
                % (label_settings["font_size_smallest"],),
                style_left_noleading,
            ),
            Paragraph(
                "<font size=%s>QTY</font>" % (label_settings["font_size_smallest"],),
                style_left_noleading,
            ),
            Paragraph(
                "<font size=%s></font>" % (label_settings["font_size_smallest"],),
                style_left_noleading,
            ),
            Paragraph(
                "<font size=%s>RECEIVED IN GOOD ORDERED AND CONDITION</font>"
                % (label_settings["font_size_smallest"],),
                style_center_noleading,
            ),
        ],
    ]

    footer_header_table = Table(
        tbl_data,
        colWidths=(
            float(label_settings["label_image_size_length"]) * (1 / 9) * mm,
            float(label_settings["label_image_size_length"]) * (1 / 9) * mm,
            float(label_settings["label_image_size_length"]) * (1 / 9) * mm,
            float(label_settings["label_image_size_length"]) * (1 / 9) * mm,
            float(label_settings["label_image_size_length"]) * (5 / 9) * mm,
        ),
        rowHeights=(float(label_settings["line_height_small"]) * mm),
        style=[
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ("LINEBELOW", (0, -1), (2, -1), 0.6, colors.gray),
            ("LINEBELOW", (4, -1), (-1, -1), 0.6, colors.gray),
        ],
    )

    tbl_data = [
        [
            "",
            Paragraph(
                "<font size=%s>Please refer to conditions of cartage at</font>"
                % (label_settings["font_size_smallest"],),
                style_center_noleading,
            ),
        ],
        [
            "",
            Paragraph(
                "<font size=%s><b>www.northline.com.au/termsandconditions</b></font>"
                % (label_settings["font_size_extra_small"],),
                style_center_noleading,
            ),
        ],
    ]

    footer_body_table = Table(
        tbl_data,
        colWidths=(
            float(label_settings["label_image_size_length"]) * (1 / 3) * mm,
            float(label_settings["label_image_size_length"]) * (2 / 3) * mm,
        ),
        rowHeights=(1 * mm),
        style=[
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ],
    )

    tbl_data = [
        [
            "",
            Paragraph(
                "<font size=%s>x</font>" % (label_settings["font_size_extra_small"]),
                style_left_noleading,
            ),
            "",
            Paragraph(
                "<font size=%s>x</font>" % (label_settings["font_size_extra_small"]),
                style_left_noleading,
            ),
        ],
        [
            "",
            Paragraph(
                "<font size=%s>_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _</font>"
                % (label_settings["font_size_extra_small"]),
                style_left_noleading,
            ),
            "",
            "",
        ],
    ]

    sign_table = Table(
        tbl_data,
        colWidths=(
            float(label_settings["label_image_size_length"]) * (2 / 5) * mm,
            float(label_settings["label_image_size_length"]) * (11 / 40) * mm,
            float(label_settings["label_image_size_length"]) * (1 / 20) * mm,
            float(label_settings["label_image_size_length"]) * (11 / 40) * mm,
        ),
        rowHeights=(2 * mm),
        style=[
            ("ALIGN", (0, 0), (-1, -1), "LEFT"),
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ("VALIGN", (0, 0), (1, 0), "BOTTOM"),
            ("VALIGN", (0, 1), (1, 1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ],
    )

    tbl_data = [
        [
            "",
            Paragraph(
                "<font size=%s>Receivers Signature</font>"
                % (label_settings["font_size_smallest"],),
                style_center_noleading,
            ),
            "",
            Paragraph(
                "<font size=%s>Print Name</font>"
                % (label_settings["font_size_smallest"],),
                style_center_noleading,
            ),
            Paragraph(
                "<font size=%s>Date</font>" % (label_settings["font_size_smallest"],),
                style_center_noleading,
            ),
        ],
    ]

    sign_label_table = Table(
        tbl_data,
        colWidths=(
            float(label_settings["label_image_size_length"]) * (2 / 5) * mm,
            float(label_settings["label_image_size_length"]) * (11 / 40) * mm,
            float(label_settings["label_image_size_length"]) * (1 / 20) * mm,
            float(label_settings["label_image_size_length"]) * (11 / 80) * mm,
            float(label_settings["label_image_size_length"]) * (11 / 80) * mm,
        ),
        rowHeights=(2 * mm),
        style=[
            ("ALIGN", (0, 0), (-1, -1), "LEFT"),
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ("VALIGN", (0, 0), (0, -1), "BOTTOM"),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ],
    )

    # Delivery's Copy
    Story_consignment.append(header)
    Story_consignment.append(Spacer(1, 3))

    Story_consignment.append(barcode_section)

    Story_consignment.append(Spacer(1, 3))
    Story_consignment.append(middle_table_section)

    Story_consignment.append(Spacer(1, 3))

    Story_consignment.append(detail_header_table)
    Story_consignment.append(detail_body_table)

    Story_consignment.append(Spacer(1, 2))

    Story_consignment.append(dangerous_table)
    Story_consignment.append(footer_header_table)

    Story_consignment.append(Spacer(1, 1))

    Story_consignment.append(footer_body_table)

    Story_consignment.append(Spacer(1, 4))

    Story_consignment.append(sign_table)
    Story_consignment.append(sign_label_table)

    logger.info(
        f"#110 [NORTHLINE LABEL] Started building Proof of Delivery copy... (Booking ID: {booking.b_bookingID_Visual})"
    )

    # Proof Of Delivery Copy

    Story_consignment.append(Spacer(1, 10))

    Story_consignment.append(header_pod)
    Story_consignment.append(Spacer(1, 3))

    Story_consignment.append(barcode_section)

    Story_consignment.append(Spacer(1, 3))
    Story_consignment.append(middle_table_section)

    Story_consignment.append(Spacer(1, 3))

    Story_consignment.append(detail_header_table)
    Story_consignment.append(detail_body_table)

    Story_consignment.append(Spacer(1, 2))

    Story_consignment.append(dangerous_table)
    Story_consignment.append(footer_header_table)

    Story_consignment.append(Spacer(1, 1))

    Story_consignment.append(footer_body_table)

    Story_consignment.append(Spacer(1, 4))

    Story_consignment.append(sign_table)
    Story_consignment.append(sign_label_table)

    Story_consignment.append(PageBreak())

    logger.info(
        f"#110 [NORTHLINE LABEL] Started building main label... (Booking ID: {booking.b_bookingID_Visual})"
    )

    dme_img_width = float(label_settings["label_image_size_length"]) * mm

    for line in lines:
        for k in range(line.e_qty):
            if one_page_label and k > 0:
                continue
            data = [
                [
                    dme_img,
                ]
            ]
            logger.info(f"#114 [NORTHLINE LABEL] Adding: {line}")

            header = Table(
                data,
                colWidths=[dme_img_width],
                style=[
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                    ("TOPPADDING", (0, 0), (-1, -1), 0),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                    ("BOTTOMBORDER", (0, 0), (-1, -1), 0),
                    ("LEFTPADDING", (0, 0), (-1, -1), 0),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ],
            )
            Story.append(header)
            Story.append(Spacer(1, 3))

            tbl_data = [
                [
                    Paragraph(
                        "<font size=%s><b>%s</b></font>"
                        % (
                            label_settings["font_size_large"],
                            booking.b_dateBookedDate.strftime("%d/%m/%Y")
                            if booking.b_dateBookedDate
                            else "",
                        ),
                        style_left,
                    ),
                    Paragraph(
                        "<font size=%s><b>ITEM %s of %s</b></font>"
                        % (
                            label_settings["font_size_large"],
                            j,
                            totalQty,
                        ),
                        style_right,
                    ),
                ],
            ]

            table_consignment_date = Table(
                tbl_data,
                colWidths=(
                    float(label_settings["label_image_size_length"]) * (1 / 2) * mm,
                    float(label_settings["label_image_size_length"]) * (1 / 2) * mm,
                ),
                rowHeights=(float(label_settings["line_height_small"]) * mm),
                style=[
                    ("ALIGN", (0, 0), (0, 0), "LEFT"),
                    ("ALIGN", (0, 0), (1, 0), "RIGHT"),
                    ("TOPPADDING", (0, 0), (-1, -1), 0),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                    ("VALIGN", (0, 0), (0, -1), "BOTTOM"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 0),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ],
            )

            Story.append(table_consignment_date)

            tbl_data = [
                [
                    KeepInFrame(
                        (float(label_settings["label_image_size_length"]) * mm),
                        12 * mm,
                        [
                            Paragraph(
                                "<font size=%s><b>%s</b></font>"
                                % (label_settings["font_size_extra_large"], de_suburb),
                                style_left_extra_large,
                            ),
                        ],
                    )
                ],
                [
                    Paragraph(
                        "<font size=%s><b>%s &nbsp;&nbsp; %s</b></font>"
                        % (
                            label_settings["font_size_extra_large"],
                            de_state,
                            de_postcode,
                        ),
                        style_left_extra_large,
                    )
                ],
            ]

            table_receiving_suburb = Table(
                tbl_data,
                colWidths=(float(label_settings["label_image_size_length"]) * mm),
                style=[
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("ALIGN", (0, 0), (0, 0), "LEFT"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 0),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ],
            )

            Story.append(table_receiving_suburb)
            Story.append(Spacer(1, 15))

            hr = HRFlowable(
                width=(width),
                thickness=1,
                lineCap="square",
                color=colors.black,
                spaceBefore=0,
                spaceAfter=0,
                hAlign="CENTER",
                vAlign="BOTTOM",
                dash=None,
            )

            Story.append(hr)
            Story.append(Spacer(1, 5))

            tbl_data = [
                [
                    Paragraph(
                        "<font size=%s>C/N:</font>"
                        % (label_settings["font_size_large"]),
                        style_left,
                    ),
                    Paragraph(
                        "<font size=%s><b>%s</b></font>"
                        % (
                            label_settings["font_size_slight_large"],
                            v_FPBookingNumber,
                        ),
                        style_left,
                    ),
                ],
            ]

            label_width = (
                float(label_settings["label_image_size_length"]) * (1 / 6) * mm
            )
            content_width = (
                float(label_settings["label_image_size_length"]) * (5 / 6) * mm
            )

            table_consignment_number = Table(
                tbl_data,
                colWidths=(
                    label_width,
                    content_width,
                ),
                style=[
                    ("TOPPADDING", (0, 0), (-1, -1), 0),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                    ("LEFTPADDING", (0, 0), (-1, -1), 0),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                ],
            )

            Story.append(table_consignment_number)
            Story.append(Spacer(1, 5))

            Story.append(hr)
            Story.append(Spacer(1, 5))

            tbl_data = [
                [
                    Paragraph(
                        "<font size=%s>TO:</font>"
                        % (label_settings["font_size_large"],),
                        style_left,
                    ),
                    Paragraph(
                        "<font size=%s><b>%s<br/>%s<br/>%s, %s %s</b></font>"
                        % (
                            label_settings[
                                "font_size_slight_large"
                                if len(booking.de_To_Address_Suburb) < 15
                                else "font_size_large"
                            ],
                            (booking.deToCompanyName or "")[:30],
                            (
                                booking.de_To_Address_Street_1
                                or booking.de_To_Address_Street_2
                                or ""
                            )[:30],
                            (booking.de_To_Address_Suburb[:30] or ""),
                            booking.de_To_Address_State or "",
                            booking.de_To_Address_PostalCode or "",
                        ),
                        style_left,
                    ),
                ],
            ]

            table_to = Table(
                tbl_data,
                colWidths=(
                    label_width,
                    content_width,
                ),
                style=[
                    ("TOPPADDING", (0, 0), (-1, -1), 0),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                    ("LEFTPADDING", (0, 0), (-1, -1), 0),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                ],
            )

            Story.append(table_to)
            Story.append(Spacer(1, 8))

            Story.append(hr)
            Story.append(Spacer(1, 5))

            tbl_data = [
                [
                    Paragraph(
                        "<font size=%s>FROM:</font>"
                        % (label_settings["font_size_small"],),
                        style_left,
                    ),
                    Paragraph(
                        "<font size=%s><b>%s<br/>%s<br/>%s, %s %s</b></font>"
                        % (
                            label_settings["font_size_medium"],
                            (booking.puCompany or "")[:30],
                            (
                                booking.pu_Address_Street_1
                                or booking.pu_Address_street_2
                                or ""
                            )[:30],
                            (booking.pu_Address_Suburb or "")[:30],
                            booking.pu_Address_State or "",
                            booking.pu_Address_PostalCode or "",
                        ),
                        style_left,
                    ),
                ],
            ]

            table_from = Table(
                tbl_data,
                colWidths=(
                    label_width,
                    content_width,
                ),
                style=[
                    ("TOPPADDING", (0, 0), (-1, -1), 0),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                    ("LEFTPADDING", (0, 0), (-1, -1), 0),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                ],
            )

            Story.append(table_from)
            Story.append(Spacer(1, 5))

            Story.append(hr)
            Story.append(Spacer(1, 5))

            tbl_data = [
                [
                    Paragraph(
                        "<font size=%s>CUST REF:</font>"
                        % (label_settings["font_size_small"]),
                        style_left,
                    ),
                    Paragraph(
                        "<font size=%s>%s</font>"
                        % (
                            label_settings["font_size_medium"],
                            booking.b_client_order_num or "",
                        ),
                        style_left,
                    ),
                    Paragraph(
                        "<font size=%s>SENDER REF:</font>"
                        % (label_settings["font_size_small"],),
                        style_left,
                    ),
                    Paragraph(
                        "<font size=%s>%s</font>"
                        % (
                            label_settings["font_size_medium"],
                            (line.gap_ras or "")[:30],
                        ),
                        style_left,
                    ),
                ],
            ]

            table_reference = Table(
                tbl_data,
                colWidths=(
                    float(label_settings["label_image_size_length"]) * (1 / 6) * mm,
                    float(label_settings["label_image_size_length"]) * (1 / 3) * mm,
                    float(label_settings["label_image_size_length"]) * (1 / 6) * mm,
                    float(label_settings["label_image_size_length"]) * (1 / 3) * mm,
                ),
                style=[
                    ("TOPPADDING", (0, 0), (-1, -1), 0),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                    ("LEFTPADDING", (0, 0), (-1, -1), 0),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                ],
            )

            Story.append(table_reference)
            Story.append(Spacer(1, 5))

            Story.append(hr)
            Story.append(Spacer(1, 5))

            specialInstructions = ""
            if booking.pu_pickup_instructions_address:
                specialInstructions += booking.pu_pickup_instructions_address
            if booking.pu_PickUp_Instructions_Contact:
                specialInstructions += f" {booking.pu_PickUp_Instructions_Contact}"
            if booking.de_to_PickUp_Instructions_Address:
                specialInstructions += f" {booking.de_to_PickUp_Instructions_Address}"
            if booking.de_to_Pick_Up_Instructions_Contact:
                specialInstructions += f" {booking.de_to_Pick_Up_Instructions_Contact}"

            tbl_data = [
                [
                    Paragraph(
                        "<font size=%s><b>SPECIAL INSTRUCTIONS:</b></font>"
                        % (label_settings["font_size_medium"],),
                        style_left,
                    ),
                ],
                [
                    Paragraph(
                        "<font size=%s>%s</font>"
                        % (
                            label_settings["font_size_medium"],
                            specialInstructions,
                        ),
                        style_left,
                    ),
                ],
                [
                    Paragraph(
                        "<font size=%s><b>DELIVERY:</b>%s</font>"
                        % (
                            label_settings["font_size_medium"],
                            "tailgate" if booking.b_booking_tail_lift_deliver else "",
                        ),
                        style_left,
                    ),
                ],
            ]

            table_special_instructions = Table(
                tbl_data,
                colWidths=(float(label_settings["label_image_size_length"]) * mm,),
                style=[
                    ("TOPPADDING", (0, 0), (-1, -1), 0),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                    ("LEFTPADDING", (0, 0), (-1, -1), 0),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                ],
            )

            Story.append(table_special_instructions)
            Story.append(Spacer(1, 5))

            Story.append(hr)
            Story.append(Spacer(1, 5))

            barcode = gen_barcode(booking, v_FPBookingNumber, j)

            tbl_data = [
                [
                    code128.Code128(
                        barcode,
                        barHeight=15 * mm,
                        barWidth=2 if len(barcode) < 10 else 1.5,
                        humanReadable=False,
                    )
                ],
            ]

            table_barcode = Table(
                tbl_data,
                colWidths=((float(label_settings["label_image_size_length"])) * mm),
                style=[
                    ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                    ("VALIGN", (0, 0), (0, -1), "TOP"),
                    ("TOPPADDING", (0, 0), (-1, -1), 5),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
                    ("LEFTPADDING", (0, 0), (0, -1), 0),
                    ("RIGHTPADDING", (0, 0), (0, -1), 0),
                    # ('BOX', (0, 0), (-1, -1), 1, colors.black)
                ],
            )

            Story.append(table_barcode)

            tbl_data = [
                [
                    Paragraph(
                        "<font size=%s>%s</font>"
                        % (label_settings["font_size_slight_large"], barcode),
                        style_center,
                    ),
                ],
            ]

            table_barcode_label = Table(
                tbl_data,
                colWidths=(float(label_settings["label_image_size_length"]) * mm,),
                style=[
                    ("TOPPADDING", (0, 0), (-1, -1), 0),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                    ("LEFTPADDING", (0, 0), (-1, -1), 0),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                ],
            )

            Story.append(table_barcode_label)

            Story.append(Spacer(1, 8))

            footer_part_width = (
                float(label_settings["label_image_size_length"]) * (1 / 2) * mm
            )

            pkg_units_font_size = "font_size_footer"
            if len(line.e_type_of_packaging) < 8:
                pkg_units_font_size = "font_size_footer"
            elif len(line.e_type_of_packaging) <= 10:
                pkg_units_font_size = "font_size_footer_desc"
            else:
                pkg_units_font_size = "font_size_footer_units_small"

            footer_units_part = Table(
                [
                    [
                        Paragraph(
                            "<font size=%s>PKG UNITS:</font>"
                            % (label_settings["font_size_footer_desc"],),
                            style_reference_text,
                        ),
                        [
                            Paragraph(
                                "<font size=%s><b>%s</b></font>"
                                % (
                                    label_settings[pkg_units_font_size],
                                    line.e_type_of_packaging,
                                ),
                                style_footer_text,
                            ),
                        ],
                    ],
                ],
                colWidths=[
                    footer_part_width * (3 / 7),
                    footer_part_width * (4 / 7),
                ],
                rowHeights=[5 * mm],
                style=[
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                    ("LEFTPADDING", (0, 0), (-1, -1), 0),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                    ("TOPPADDING", (0, 0), (-1, -1), 0),
                ],
            )

            footer_bin_part = Table(
                [
                    [
                        Paragraph(
                            "<font size=%s>BIN:</font>"
                            % (label_settings["font_size_footer_desc"],),
                            style_reference_text,
                        ),
                        Paragraph(
                            "<font size=%s><b>%s</b></font>"
                            % (
                                label_settings["font_size_footer"],
                                "No data"
                                if line.e_bin_number is None
                                or len(line.e_bin_number) == 0
                                else line.e_bin_number[:25],
                            ),
                            style_footer_text,
                        ),
                    ],
                ],
                colWidths=[
                    footer_part_width * (1 / 5),
                    footer_part_width * (4 / 5),
                ],
                rowHeights=[5 * mm],
                style=[
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                    ("LEFTPADDING", (0, 0), (-1, -1), 0),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                    ("TOPPADDING", (0, 0), (-1, -1), 0),
                ],
            )

            str_desc = line.e_item.replace("\n", " ").replace("\t", " ")[:80]
            font_size_desc = "font_size_footer"
            if len(str_desc) < 24:
                font_size_desc = "font_size_footer"
            elif len(str_desc) < 55:
                font_size_desc = "font_size_footer_units"
            else:
                font_size_desc = "font_size_footer_desc_small"

            footer_desc_part = Table(
                [
                    [
                        Paragraph(
                            "<font size=%s>DESC:</font>"
                            % (label_settings["font_size_footer_desc"],),
                            style_reference_text,
                        ),
                        Paragraph(
                            "<font size=%s><b>%s</b></font>"
                            % (
                                label_settings[font_size_desc],
                                str_desc,
                            ),
                            style_desc_text,
                        ),
                    ],
                ],
                colWidths=[
                    footer_part_width * (1 / 4),
                    footer_part_width * (7 / 4),
                ],
                rowHeights=[5 * mm],
                style=[
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                    ("LEFTPADDING", (0, 0), (-1, -1), 0),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                    ("TOPPADDING", (0, 0), (-1, -1), 0),
                ],
            )

            footer_part = Table(
                [
                    [
                        footer_units_part,
                        footer_bin_part,
                    ],
                    [
                        footer_desc_part,
                        "",
                    ],
                ],
                colWidths=[
                    footer_part_width,
                    footer_part_width,
                ],
                rowHeights=[5 * mm, 5 * mm],
                style=[
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                    ("SPAN", (0, 1), (1, 1)),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                    ("LEFTPADDING", (0, 0), (-1, -1), 0),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                    ("TOPPADDING", (0, 0), (-1, -1), 0),
                    ("TOPPADDING", (0, 1), (-1, 1), 1),
                ],
            )

            Story.append(footer_part)

            Story.append(PageBreak())

            j += 1

    doc.build(Story, onFirstPage=myFirstPage, onLaterPages=myLaterPages)

    doc_consignment.build(
        Story_consignment, onFirstPage=myFirstPage, onLaterPages=myLaterPages
    )

    # end writting data into pdf file
    file.close()
    logger.info(
        f"#119 [NORTHLINE LABEL] Finished building label... (Booking ID: {booking.b_bookingID_Visual})"
    )
    return filepath, f"{filename}.pdf"
