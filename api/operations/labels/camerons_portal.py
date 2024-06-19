# Python 3.6.6

import pysftp
from api.common.common_times import convert_to_AU_SYDNEY_tz

from api.helpers.cubic import get_cubic_meter

cnopts = pysftp.CnOpts()
cnopts.hostkeys = None
import os
import logging

from reportlab.lib.enums import TA_JUSTIFY, TA_RIGHT, TA_CENTER, TA_LEFT
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
from reportlab.lib.units import mm
from reportlab.graphics.barcode import code128
from reportlab.lib import colors

from api.models import Booking_lines
from api.operations.api_booking_confirmation_lines import index as api_bcl
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
style_right_extra_large = ParagraphStyle(
    name="right", parent=styles["Normal"], alignment=TA_RIGHT, leading=28
)
style_center = ParagraphStyle(
    name="center", parent=styles["Normal"], alignment=TA_CENTER, leading=10
)
style_left_noleading = ParagraphStyle(
    name="left",
    parent=styles["Normal"],
    alignment=TA_LEFT,
    leading=6,
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
style_right = ParagraphStyle(
    name="right", parent=styles["Normal"], alignment=TA_RIGHT, leading=12
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


def get_meter(value, uom="METER"):
    _dimUOM = uom.upper()

    if _dimUOM in ["MM", "MILIMETER"]:
        value = value / 1000
    elif _dimUOM in ["CM", "CENTIMETER"]:
        value = value / 100

    return round(value, 2)


class VerticalParagraph(Paragraph):
    """Paragraph that is printed vertically"""

    def __init__(self, text, style):
        super().__init__(text, style)
        self.horizontal_position = -self.style.leading

    def draw(self):
        """Draw text"""
        canvas = self.canv
        canvas.rotate(90)
        canvas.translate(1, self.horizontal_position)
        super().draw()

    def wrap(self, available_width, _):
        """Wrap text in table"""
        string_width = self.canv.stringWidth(
            self.getPlainText(), self.style.fontName, self.style.fontSize
        )
        self.horizontal_position = -(available_width + self.style.leading) / 2
        height, _ = super().wrap(
            availWidth=1.4 + string_width, availHeight=available_width
        )
        return self.style.leading, height


class InteractiveCheckBox(Flowable):
    def __init__(self, text=""):
        Flowable.__init__(self)
        self.text = text
        self.boxsize = 5

    def draw(self):
        self.canv.saveState()
        form = self.canv.acroForm
        form.checkbox(
            checked=False,
            buttonStyle="check",
            name=self.text,
            tooltip=self.text,
            relative=True,
            fillColor=colors.white,
            size=self.boxsize,
        )
        self.canv.restoreState()
        return


checkbox = InteractiveCheckBox("")


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
        f"#110 [CAMERON LABEL] Started building label... (Booking ID: {booking.b_bookingID_Visual}, Lines: {lines})"
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
    logger.info(f"#111 [CAMERON LABEL] File full path: {filepath}/{filename}.pdf")

    label_settings = {
        "font_family": "Verdana",
        "font_size_smallest": "3",
        "font_size_extra_small": "4",
        "font_size_small": "6",
        "font_size_extra_medium": "7",
        "font_size_medium": "8",
        "font_size_large_title": "9",
        "font_size_large": "10",
        "font_size_slight_large": "12",
        "font_size_extra_large": "30",
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

    width = float(label_settings["label_image_size_length"]) * mm

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

    # Delivery's Copy

    logger.info(
        f"#110 [CAMERON LABEL] Started building Delivery's copy... (Booking ID: {booking.b_bookingID_Visual})"
    )

    label_width = 5 * mm
    width = width - label_width

    tbl_data = [
        [
            VerticalParagraph(
                "<font size=%s><b>RECEIVER'S COPY</b></font>"
                % (label_settings["font_size_extra_medium"],),
                style_left,
            ),
        ]
    ]
    table_label = Table(
        tbl_data,
        colWidths=[label_width],
        style=[
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ],
    )

    # -------------------- Header part ------------------------
    tbl_data = [
        [
            Paragraph(
                "<font size=%s>Cameron Interstate</font>"
                % (label_settings["font_size_large_title"],),
                style_left,
            ),
            Paragraph(
                "<font size=%s>Consignment No<br/><b>%s</b></font>"
                % (label_settings["font_size_extra_medium"], v_FPBookingNumber),
                style_center,
            ),
            code128.Code128(
                v_FPBookingNumber,
                barHeight=7 * mm,
                barWidth=0.8 if len(v_FPBookingNumber) < 10 else 0.5,
                humanReadable=False,
            ),
        ]
    ]

    header = Table(
        tbl_data,
        colWidths=[width * 0.35, width * 0.25, width * 0.4],
        style=[
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ],
    )

    # -------------------- Sender part ------------------------

    sender_part = Table(
        [
            [
                Paragraph(
                    "<font size=%s><b>Sender</b></font>"
                    % (label_settings["font_size_extra_small"],),
                    style_left_noleading,
                ),
                Paragraph(
                    "<font size=%s>%s</font>"
                    % (
                        label_settings["font_size_extra_small"],
                        (booking.puCompany or "")[:30],
                    ),
                    style_left_noleading,
                ),
                "",
                Paragraph(
                    "<font size=%s><b>Receiver</b></font>"
                    % (label_settings["font_size_extra_small"],),
                    style_left_noleading,
                ),
                Paragraph(
                    "<font size=%s>%s</font>"
                    % (
                        label_settings["font_size_extra_small"],
                        (booking.deToCompanyName or "")[:30],
                    ),
                    style_left_noleading,
                ),
                "",
                Paragraph(
                    "<font size=%s><b>%s</b></font>"
                    % (
                        label_settings["font_size_extra_medium"],
                        (booking.de_To_Address_State or "")[:30],
                    ),
                    style_right,
                ),
            ],
            [
                Paragraph(
                    "<font size=%s><b>Address</b></font>"
                    % (label_settings["font_size_extra_small"],),
                    style_left_noleading,
                ),
                Paragraph(
                    "<font size=%s>%s</font>"
                    % (
                        label_settings["font_size_extra_small"],
                        (booking.pu_Address_Street_1 or "")[:30],
                    ),
                    style_left_noleading,
                ),
                "",
                Paragraph(
                    "<font size=%s><b>Address</b></font>"
                    % (label_settings["font_size_extra_small"],),
                    style_left_noleading,
                ),
                Paragraph(
                    "<font size=%s>%s</font>"
                    % (
                        label_settings["font_size_extra_small"],
                        (booking.de_To_Address_Street_1 or "")[:30],
                    ),
                    style_left_noleading,
                ),
                "",
                "",
            ],
            [
                "",
                Paragraph(
                    "<font size=%s>%s</font>"
                    % (
                        label_settings["font_size_extra_small"],
                        (booking.pu_Address_street_2 or "")[:30],
                    ),
                    style_left_noleading,
                ),
                "",
                "",
                Paragraph(
                    "<font size=%s>%s</font>"
                    % (
                        label_settings["font_size_extra_small"],
                        (booking.de_To_Address_Street_2 or "")[:30],
                    ),
                    style_left_noleading,
                ),
                "",
                "",
            ],
            [
                "",
                Paragraph(
                    "<font size=%s>%s</font>"
                    % (
                        label_settings["font_size_extra_small"],
                        (booking.pu_Address_Suburb or "")[:30],
                    ),
                    style_left_noleading,
                ),
                "",
                "",
                Paragraph(
                    "<font size=%s>%s</font>"
                    % (
                        label_settings["font_size_extra_small"],
                        (booking.de_To_Address_Suburb or "")[:30],
                    ),
                    style_left_noleading,
                ),
                "",
                "",
            ],
            [
                "",
                Paragraph(
                    "<font size=%s>%s   %s</font>"
                    % (
                        label_settings["font_size_extra_small"],
                        booking.pu_Address_State or "",
                        booking.pu_Address_PostalCode or "",
                    ),
                    style_left_noleading,
                ),
                "",
                "",
                Paragraph(
                    "<font size=%s>%s   %s</font>"
                    % (
                        label_settings["font_size_extra_small"],
                        booking.de_To_Address_State or "",
                        booking.de_To_Address_PostalCode or "",
                    ),
                    style_left_noleading,
                ),
                "",
                "",
            ],
            [
                Paragraph(
                    "<font size=%s><b>Contanct</b></font>"
                    % (label_settings["font_size_extra_small"],),
                    style_left_noleading,
                ),
                Paragraph(
                    "<font size=%s>%s</font>"
                    % (
                        label_settings["font_size_extra_small"],
                        (booking.pu_Contact_F_L_Name or "")[:30],
                    ),
                    style_left_noleading,
                ),
                Paragraph(
                    "<font size=%s><b>Ph</b> %s</font>"
                    % (
                        label_settings["font_size_extra_small"],
                        (booking.pu_Phone_Main or "")[:20],
                    ),
                    style_left_noleading,
                ),
                Paragraph(
                    "<font size=%s><b>Contanct</b></font>"
                    % (label_settings["font_size_extra_small"],),
                    style_left_noleading,
                ),
                Paragraph(
                    "<font size=%s>%s</font>"
                    % (
                        label_settings["font_size_extra_small"],
                        (booking.de_to_Contact_F_LName or "")[:30],
                    ),
                    style_left_noleading,
                ),
                Paragraph(
                    "<font size=%s><b>Ph</b> %s</font>"
                    % (
                        label_settings["font_size_extra_small"],
                        (booking.de_to_Phone_Main or "")[:20],
                    ),
                    style_left_noleading,
                ),
                "",
            ],
        ],
        colWidths=[
            width * 0.1,
            width * 0.2,
            width * 0.2,
            width * 0.1,
            width * 0.2,
            width * 0.1,
            width * 0.1,
        ],
        rowHeights=[6, 6, 6, 6, 6, 6],
        style=[
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ("SPAN", (6, 0), (6, 1)),
            ("SPAN", (4, 1), (5, 1)),
            ("SPAN", (4, 2), (5, 2)),
            ("SPAN", (4, 3), (5, 3)),
            ("SPAN", (4, 4), (5, 4)),
            ("SPAN", (5, 5), (6, 5)),
            ("LINEBELOW", (0, -1), (-1, -1), 0.5, colors.black),
            ("LINEAFTER", (2, 0), (2, -1), 0.5, colors.black),
            ("LEFTPADDING", (0, 0), (0, -1), 2),
            ("LEFTPADDING", (3, 0), (3, -1), 2),
            ("RIGHTPADDING", (-1, 0), (-1, -1), 2),
        ],
    )

    # -------------------- Charge part ------------------------

    charge_part = Table(
        [
            [
                Paragraph(
                    "<font size=%s><b>Charge</b></font>"
                    % (label_settings["font_size_extra_small"],),
                    style_left,
                ),
                checkbox,
                Paragraph(
                    "<font size=%s>SENDER</font>"
                    % (label_settings["font_size_extra_small"],),
                    style_left,
                ),
                checkbox,
                Paragraph(
                    "<font size=%s>RECEIVER</font>"
                    % (label_settings["font_size_extra_small"],),
                    style_left,
                ),
                checkbox,
                Paragraph(
                    "<font size=%s>THIRD PARTY</font>"
                    % (label_settings["font_size_extra_small"],),
                    style_left,
                ),
                Paragraph(
                    "<font size=%s><b>Special Instructions</b></font>"
                    % (label_settings["font_size_extra_small"],),
                    style_left,
                ),
            ]
        ],
        colWidths=[
            width * 0.1,
            width * 0.03,
            width * 0.1,
            width * 0.03,
            width * 0.1,
            width * 0.03,
            width * 0.11,
            width * 0.5,
        ],
        rowHeights=[8],
        style=[
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ("ALIGN", (1, 0), (1, 0), "LEFT"),
            ("ALIGN", (3, 0), (3, 0), "LEFT"),
            ("ALIGN", (5, 0), (5, 0), "LEFT"),
            ("TOPPADDING", (0, 0), (-1, 0), 8),
            ("LINEAFTER", (6, 0), (6, -1), 0.5, colors.black),
            ("LEFTPADDING", (0, 0), (0, -1), 2),
            ("LEFTPADDING", (7, 0), (7, -1), 2),
            ("RIGHTPADDING", (-1, 0), (-1, -1), 2),
        ],
    )

    # -------------------- A/C Code part ------------------------

    code_part = Table(
        [
            [
                Paragraph(
                    "<font size=%s><b>A/C Code</b></font>"
                    % (label_settings["font_size_extra_small"],),
                    style_left,
                ),
                Paragraph(
                    "<font size=%s>%s</font>"
                    % (label_settings["font_size_extra_small"], "12265"),
                    style_left,
                ),
                Paragraph(
                    "<font size=%s><b>Customer Ref</b></font>"
                    % (label_settings["font_size_extra_small"],),
                    style_left,
                ),
                Paragraph(
                    "<font size=%s>%s</font>"
                    % (
                        label_settings["font_size_extra_small"],
                        booking.b_client_order_num or "",
                    ),
                    style_left,
                ),
                "",
            ]
        ],
        colWidths=[
            width * 0.1,
            width * 0.1,
            width * 0.15,
            width * 0.15,
            width * 0.5,
        ],
        rowHeights=[8],
        style=[
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ("LINEAFTER", (3, 0), (3, -1), 0.5, colors.black),
            ("LEFTPADDING", (0, 0), (0, -1), 2),
            ("LEFTPADDING", (4, 0), (4, -1), 2),
            ("RIGHTPADDING", (-1, 0), (-1, -1), 2),
        ],
    )

    # -------------------- General Service part ----------------

    delivery_time = ''
    if booking.s_06_Latest_Delivery_Date_TimeSet:
        delivery_time = convert_to_AU_SYDNEY_tz(
            booking.s_06_Latest_Delivery_Date_TimeSet
        )
        delivery_time = delivery_time.strftime("%d/%m/%Y %H:%M")

    general_service_part = Table(
        [
            [
                checkbox,
                Paragraph(
                    "<font size=%s>GENERAL SERVICE</font>"
                    % (label_settings["font_size_extra_small"],),
                    style_left,
                ),
                checkbox,
                Paragraph(
                    "<font size=%s>EXPRESS SERVICE</font>"
                    % (label_settings["font_size_extra_small"],),
                    style_left,
                ),
                Paragraph(
                    "<font size=%s><b>Delivery Time</b></font>"
                    % (label_settings["font_size_extra_small"],),
                    style_left,
                ),
                Paragraph(
                    "<font size=%s>%s</font>"
                    % (
                        label_settings["font_size_extra_small"],
                        delivery_time,
                    ),
                    style_left,
                ),
                Paragraph(
                    "<font size=%s><b>Ref</b></font>"
                    % (label_settings["font_size_extra_small"],),
                    style_left,
                ),
            ]
        ],
        colWidths=[
            width * 0.05,
            width * 0.2,
            width * 0.05,
            width * 0.2,
            width * 0.15,
            width * 0.2,
            width * 0.15,
        ],
        rowHeights=[8],
        style=[
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("LINEAFTER", (3, 0), (3, -1), 0.5, colors.black),
            ("LEFTPADDING", (4, 0), (4, -1), 2),
            ("RIGHTPADDING", (-1, 0), (-1, -1), 2),
        ],
    )

    # -------------------- First Section ------------------------

    first_section = Table(
        [[sender_part], [charge_part], [code_part], [general_service_part]],
        colWidths=[width],
        style=[
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ("LINEABOVE", (0, 0), (-1, 0), 0.5, colors.black),
            ("LINEBELOW", (0, -1), (-1, -1), 0.5, colors.black),
            ("LINEBEFORE", (0, 0), (0, -1), 0.5, colors.black),
            ("LINEAFTER", (-1, 0), (-1, -1), 0.5, colors.black),
        ],
    )

    # -------------------- Tailgate Part -------------------------

    tailgate_part = Table(
        [
            [
                checkbox,
                Paragraph(
                    "<font size=%s>TAILGATE DELIVERY</font>"
                    % (label_settings["font_size_extra_small"],),
                    style_left,
                ),
            ],
            [
                checkbox,
                Paragraph(
                    "<font size=%s>HAND UNLOAD</font>"
                    % (label_settings["font_size_extra_small"],),
                    style_left,
                ),
            ],
        ],
        colWidths=[
            width * 0.05,
            width * 0.25,
        ],
        style=[
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ("TOPPADDING", (0, 0), (-1, 0), 2),
        ],
    )

    # -------------------- Pallets Picked Up Part -------------------------

    pallets_pu_part = Table(
        [
            [
                Paragraph(
                    "<font size=%s>Pallets Picked Up</font>"
                    % (label_settings["font_size_extra_small"],),
                    style_center,
                ),
                Paragraph(
                    "<font size=%s>Transfer From Sender</font>"
                    % (label_settings["font_size_extra_small"],),
                    style_center,
                ),
                "",
                "",
            ],
            [
                "",
                Paragraph(
                    "<font size=%s>To Carrier</font>"
                    % (label_settings["font_size_extra_small"],),
                    style_center,
                ),
                Paragraph(
                    "<font size=%s>To Receiver</font>"
                    % (label_settings["font_size_extra_small"],),
                    style_center,
                ),
                Paragraph(
                    "<font size=%s>Docket</font>"
                    % (label_settings["font_size_extra_small"],),
                    style_center,
                ),
            ],
            [
                Paragraph(
                    "<font size=%s>Chep</font>"
                    % (label_settings["font_size_extra_small"],),
                    style_center,
                ),
                "",
                "",
                "",
            ],
            [
                Paragraph(
                    "<font size=%s>Loscam</font>"
                    % (label_settings["font_size_extra_small"],),
                    style_center,
                ),
                "",
                "",
                "",
            ],
        ],
        colWidths=[
            width * 0.08,
            width * 0.1,
            width * 0.1,
            width * 0.1,
        ],
        rowHeights=[8, 8, 8, 8],
        style=[
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("TOPPADDING", (0, 0), (-1, -1), 2),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ("GRID", (1, 0), (-1, -1), 0.5, colors.black),
            ("GRID", (0, 2), (0, -1), 0.5, colors.black),
            ("SPAN", (0, 0), (0, 1)),
            ("SPAN", (1, 0), (-1, 0)),
        ],
    )

    # -------------------- Pallets Delivered Part -------------------------

    pallets_de_part = Table(
        [
            [
                Paragraph(
                    "<font size=%s>Pallets Delivered</font>"
                    % (label_settings["font_size_extra_small"],),
                    style_center,
                ),
                Paragraph(
                    "<font size=%s>Transfer From Sender</font>"
                    % (label_settings["font_size_extra_small"],),
                    style_center,
                ),
                "",
            ],
            [
                "",
                Paragraph(
                    "<font size=%s>To Receiver</font>"
                    % (label_settings["font_size_extra_small"],),
                    style_center,
                ),
                Paragraph(
                    "<font size=%s>Docket</font>"
                    % (label_settings["font_size_extra_small"],),
                    style_center,
                ),
            ],
            [
                Paragraph(
                    "<font size=%s>Chep</font>"
                    % (label_settings["font_size_extra_small"],),
                    style_center,
                ),
                "",
                "",
            ],
            [
                Paragraph(
                    "<font size=%s>Loscam</font>"
                    % (label_settings["font_size_extra_small"],),
                    style_center,
                ),
                "",
                "",
            ],
        ],
        colWidths=[
            width * 0.08,
            width * 0.1,
            width * 0.1,
        ],
        rowHeights=[8, 8, 8, 8],
        style=[
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("TOPPADDING", (0, 0), (-1, -1), 2),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ("GRID", (1, 0), (-1, -1), 0.5, colors.black),
            ("GRID", (0, 2), (0, -1), 0.5, colors.black),
            ("SPAN", (0, 0), (0, 1)),
            ("SPAN", (1, 0), (-1, 0)),
        ],
    )

    # -------------------- Second Section ------------------------

    second_section = Table(
        [[tailgate_part, pallets_pu_part, pallets_de_part]],
        colWidths=[width * 0.3, width * 0.4, width * 0.3],
        style=[
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("TOPPADDING", (0, 0), (-1, -1), 2),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
            ("LEFTPADDING", (0, 0), (-1, -1), 2),
            ("RIGHTPADDING", (0, 0), (-1, -1), 2),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.black),
        ],
    )

    # ------------------------ Line part ------------------------

    line_header_part = Table(
        [
            [
                Paragraph(
                    "<font size=%s> WE ARE NOT COMMON CARRIERS GOODS ARE NOT INSURED PLEASE READ TERMS & CONDITIONS ON WEBSITE</font>"
                    % (label_settings["font_size_extra_small"],),
                    style_center,
                ),
            ],
        ],
        colWidths=[
            width,
        ],
        rowHeights=[6],
        style=[
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("TOPPADDING", (0, 0), (-1, -1), 1),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
        ],
    )

    tbl_data = [
        [
            Paragraph(
                "<font size=%s><b>Reference</b></font>"
                % (label_settings["font_size_extra_small"],),
                style_left,
            ),
            Paragraph(
                "<font size=%s><b>No.</b></font>"
                % (label_settings["font_size_extra_small"],),
                style_left,
            ),
            Paragraph(
                "<font size=%s><b>Items Description</b></font>"
                % (label_settings["font_size_extra_small"],),
                style_left,
            ),
            Paragraph(
                "<font size=%s><b>Space</b></font>"
                % (label_settings["font_size_extra_small"],),
                style_left,
            ),
            Paragraph(
                "<font size=%s><b>Length(m)</b></font>"
                % (label_settings["font_size_extra_small"],),
                style_left,
            ),
            Paragraph(
                "<font size=%s><b>Width(m)</b></font>"
                % (label_settings["font_size_extra_small"],),
                style_left,
            ),
            Paragraph(
                "<font size=%s><b>Height(m)</b></font>"
                % (label_settings["font_size_extra_small"],),
                style_left,
            ),
            Paragraph(
                "<font size=%s><b>Total(m3)</b></font>"
                % (label_settings["font_size_extra_small"],),
                style_left,
            ),
            Paragraph(
                "<font size=%s><b>Weight(kg)</b></font>"
                % (label_settings["font_size_extra_small"],),
                style_left,
            ),
        ],
    ]
    tbl_data_row = []
    total_qty = 0
    total_weight = 0
    total_cubic = 0
    no = 1
    for line in lines:
        tbl_data_row = [
            Paragraph(
                "<font size=%s>%s</font>"
                % (
                    label_settings["font_size_extra_small"],
                    booking.b_client_order_num or "",
                ),
                style_left,
            ),
            Paragraph(
                "<font size=%s>%s</font>"
                % (label_settings["font_size_extra_small"], no),
                style_left,
            ),
            Paragraph(
                "<font size=%s>%s</font>"
                % (label_settings["font_size_extra_small"], line.e_item[:20]),
                style_left,
            ),
            Paragraph(
                "<font size=%s>%s</font>"
                % (label_settings["font_size_extra_small"], "@2"),
                style_left,
            ),
            Paragraph(
                "<font size=%s>%s</font>"
                % (
                    label_settings["font_size_extra_small"],
                    get_meter(line.e_dimLength, line.e_dimUOM),
                ),
                style_left,
            ),
            Paragraph(
                "<font size=%s>%s</font>"
                % (
                    label_settings["font_size_extra_small"],
                    get_meter(line.e_dimWidth, line.e_dimUOM),
                ),
                style_left,
            ),
            Paragraph(
                "<font size=%s>%s</font>"
                % (
                    label_settings["font_size_extra_small"],
                    get_meter(line.e_dimHeight, line.e_dimUOM),
                ),
                style_left,
            ),
            Paragraph(
                "<font size=%s>%s</font>"
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
                style_left,
            ),
            Paragraph(
                "<font size=%s>%s</font>"
                % (
                    label_settings["font_size_extra_small"],
                    round(line.e_qty * line.e_weightPerEach, 2),
                ),
                style_left,
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
        no = no + 1

    tbl_data.append(
        [
            "",
            "",
            "",
            "",
            "",
            "",
            Paragraph(
                "<font size=%s><b>Total</b></font>"
                % (label_settings["font_size_extra_small"],),
                style_left,
            ),
            Paragraph(
                "<font size=%s>%s</font>"
                % (label_settings["font_size_extra_small"], round(total_cubic, 2)),
                style_left,
            ),
            Paragraph(
                "<font size=%s>%s</font>"
                % (label_settings["font_size_extra_small"], round(total_weight, 2)),
                style_left,
            ),
        ],
    )

    line_part = Table(
        tbl_data,
        colWidths=[
            width * 0.12,
            width * 0.08,
            width * 0.2,
            width * 0.1,
            width * 0.1,
            width * 0.1,
            width * 0.1,
            width * 0.1,
            width * 0.1,
        ],
        rowHeights=[8, 8, 8],
        style=[
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ("LEFTPADDING", (0, 0), (0, -1), 2),
        ],
    )

    # -------------------- Third Section ------------------------

    third_section = Table(
        [[line_header_part], [line_part]],
        colWidths=[width],
        style=[
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ("LINEABOVE", (0, 0), (-1, 0), 0.5, colors.black),
            ("LINEBELOW", (0, -1), (-1, -1), 0.5, colors.black),
            ("LINEBEFORE", (0, 0), (0, -1), 0.5, colors.black),
            ("LINEAFTER", (-1, 0), (-1, -1), 0.5, colors.black),
        ],
    )

    # -------------------- Dangerous good part---------------------

    dangerous_part_row1 = Table(
        [
            [
                Paragraph(
                    "<font size=%s><b>Contains Dangerous Good?</b></font>"
                    % (label_settings["font_size_smallest"],),
                    style_left,
                ),
                checkbox,
                Paragraph(
                    "<font size=%s>YES</font>"
                    % (label_settings["font_size_extra_small"],),
                    style_left,
                ),
                checkbox,
                Paragraph(
                    "<font size=%s>NO</font>"
                    % (label_settings["font_size_extra_small"],),
                    style_left,
                ),
                Paragraph(
                    "<font size=%s><b>Contains Food Stuff?</b></font>"
                    % (label_settings["font_size_smallest"],),
                    style_left,
                ),
                checkbox,
                Paragraph(
                    "<font size=%s>YES</font>"
                    % (label_settings["font_size_extra_small"],),
                    style_left,
                ),
                checkbox,
                Paragraph(
                    "<font size=%s>NO</font>"
                    % (label_settings["font_size_extra_small"],),
                    style_left,
                ),
            ]
        ],
        colWidths=[
            width * 0.18,
            width * 0.02,
            width * 0.05,
            width * 0.02,
            width * 0.04,
            width * 0.16,
            width * 0.02,
            width * 0.05,
            width * 0.02,
            width * 0.04,
        ],
        style=[
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("ALIGN", (0, 0), (-1, -1), "LEFT"),
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ("LEFTPADDING", (0, 0), (0, -1), 2),
            ("TOPPADDING", (0, 0), (-1, 0), 2),
        ],
    )

    dangerous_part = Table(
        [
            [dangerous_part_row1],
            [
                Paragraph(
                    "<font size=%s>If DG Yes, I confirm that Transport Documentation is complete and attached</font>"
                    % (label_settings["font_size_smallest"],),
                    style_left,
                )
            ],
        ],
        colWidths=[width * 0.6],
        rowHeights=[8, 8],
        style=[
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ("LEFTPADDING", (0, 0), (0, -1), 2),
        ],
    )

    # -------------------- Signature Part ------------------------

    signature_part = Table(
        [
            [
                Paragraph(
                    "<font size=%s><b>Sender's Signature</b></font>"
                    % (label_settings["font_size_smallest"],),
                    style_left,
                ),
                Paragraph(
                    "<font size=%s><b>Date</b><br/>%s</font>"
                    % (
                        label_settings["font_size_smallest"],
                        booking.b_dateBookedDate.strftime("%d/%m/%Y")
                        if booking.b_dateBookedDate
                        else booking.puPickUpAvailFrom_Date.strftime("%d/%m/%Y"),
                    ),
                    style_left,
                ),
                Paragraph(
                    "<font size=%s><b>Driver's Signature</b></font>"
                    % (label_settings["font_size_smallest"],),
                    style_left,
                ),
                Paragraph(
                    "<font size=%s><b>Unit No</b></font>"
                    % (label_settings["font_size_smallest"],),
                    style_left,
                ),
                Paragraph(
                    "<font size=%s><b>Delivery Unit No</b></font>"
                    % (label_settings["font_size_smallest"],),
                    style_left,
                ),
            ],
        ],
        colWidths=[
            width * 0.17,
            width * 0.1,
            width * 0.15,
            width * 0.08,
            width * 0.1,
        ],
        rowHeights=[16],
        style=[
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.black),
            ("LEFTPADDING", (0, 0), (-1, -1), 2),
        ],
    )

    # -------------------- Order Part ------------------------

    order_part = Table(
        [
            [
                Paragraph(
                    "<font size=%s><b>Received in good order and condition</b></font>"
                    % (label_settings["font_size_extra_small"],),
                    style_left,
                ),
                "",
            ],
            [
                Paragraph(
                    "<font size=%s><b>Receiver's Name(Point)</b></font>"
                    % (label_settings["font_size_smallest"],),
                    style_left,
                ),
                "",
            ],
            [
                Paragraph(
                    "<font size=%s><b>Receiver's Signature:</b></font>"
                    % (label_settings["font_size_smallest"],),
                    style_left,
                ),
                Paragraph(
                    "<font size=%s><b>Date:</b></font>"
                    % (label_settings["font_size_smallest"],),
                    style_left,
                ),
            ],
        ],
        colWidths=[width * 0.25, width * 0.15],
        rowHeights=[8, 8, 8],
        style=[
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ("SPAN", (0, 0), (1, 0)),
            ("SPAN", (0, 1), (1, 1)),
            ("LINEBEFORE", (0, 0), (0, -1), 0.5, colors.black),
            ("LEFTPADDING", (0, 0), (0, -1), 2),
        ],
    )

    # -------------------- Footer Section ------------------------

    footer = Table(
        [
            [
                Table(
                    [[dangerous_part], [signature_part]],
                    colWidths=[width * 0.6],
                    style=[
                        ("VALIGN", (0, 0), (-1, -1), "TOP"),
                        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                        ("TOPPADDING", (0, 0), (-1, -1), 0),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                        ("LEFTPADDING", (0, 0), (-1, -1), 0),
                        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                    ],
                ),
                order_part,
            ],
        ],
        colWidths=[width * 0.6, width * 0.4],
        style=[
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ("LINEABOVE", (0, 0), (-1, 0), 0.5, colors.black),
            ("LINEBELOW", (0, -1), (-1, -1), 0.5, colors.black),
            ("LINEBEFORE", (0, 0), (0, -1), 0.5, colors.black),
            ("LINEAFTER", (-1, 0), (-1, -1), 0.5, colors.black),
        ],
    )

    # ------------------------- Body -----------------------------

    body = Table(
        [
            [header],
            [first_section],
            [second_section],
            [third_section],
            [footer],
        ],
        colWidths=[width],
        style=[
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ("TOPPADDING", (0, 1), (-1, 1), 2),
        ],
    )

    wrapper = Table(
        [[table_label, body]],
        colWidths=[label_width, width],
        style=[
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("ALIGN", (0, 0), (-1, -1), "LEFT"),
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ],
    )

    Story_consignment.append(wrapper)

    Story_consignment.append(Spacer(1, 20))

    # Proof Of Delivery Copy

    logger.info(
        f"#110 [CAMERON LABEL] Started building Proof of Delivery copy... (Booking ID: {booking.b_bookingID_Visual})"
    )

    tbl_data = [
        [
            VerticalParagraph(
                "<font size=%s><b>P.O.D COPY</b></font>"
                % (label_settings["font_size_extra_medium"],),
                style_left,
            ),
        ]
    ]
    table_label = Table(
        tbl_data,
        colWidths=[label_width],
        style=[
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ],
    )

    wrapper = Table(
        [[table_label, body]],
        colWidths=[label_width, width],
        style=[
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("ALIGN", (0, 0), (-1, -1), "LEFT"),
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ],
    )

    Story_consignment.append(wrapper)

    Story_consignment.append(PageBreak())

    # Main Label

    logger.info(
        f"#110 [CAMERON LABEL] Started building main label... (Booking ID: {booking.b_bookingID_Visual})"
    )

    width = float(label_settings["label_image_size_length"]) * mm

    left_part_width = width * (3 / 7)
    right_part_width = width * (4 / 7)

    for line in lines:
        for k in range(line.e_qty):
            if one_page_label and k > 0:
                continue
            logger.info(f"#114 [CAMERON LABEL] Adding: {line}")

            tbl_data = [
                [
                    Paragraph(
                        "<font size=%s>Cameron</font>"
                        % (label_settings["font_size_extra_large"],),
                        style_left_extra_large,
                    ),
                    Paragraph(
                        "<font size=%s>%s</font>"
                        % (
                            label_settings["font_size_extra_large"],
                            booking.de_To_Address_State or "",
                        ),
                        style_right_extra_large,
                    ),
                ],
                [
                    Paragraph(
                        "<font size=%s>Interstate</font>"
                        % (label_settings["font_size_extra_large"],),
                        style_left_extra_large,
                    ),
                    Paragraph(
                        "<font size=%s>%s</font>"
                        % (
                            label_settings["font_size_extra_large"],
                            (pre_data["zone"] or "")[:20],
                        ),
                        style_right_extra_large,
                    ),
                ],
            ]

            # --------------------- Header -----------------------#

            header = Table(
                tbl_data,
                colWidths=(width * (1 / 2), width * (1 / 2)),
                style=[
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                    ("TOPPADDING", (0, 0), (-1, -1), 0),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                    ("LEFTPADDING", (0, 0), (-1, -1), 0),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ],
            )
            Story.append(header)
            Story.append(Spacer(1, 10))

            # --------------------- Left part -----------------------#

            tbl_data = [
                [
                    Paragraph(
                        "<font size=%s><b>FROM:</b></font>"
                        % (label_settings["font_size_large"],),
                        style_left,
                    ),
                ],
                [
                    Paragraph(
                        "<font size=%s><b>%s</b></font>"
                        % (
                            label_settings["font_size_large"],
                            (booking.puCompany or "")[:30],
                        ),
                        style_left,
                    ),
                ],
                [
                    Spacer(1, 10),
                ],
                [
                    Paragraph(
                        "<font size=%s>%s</font>"
                        % (
                            label_settings["font_size_medium"],
                            (
                                booking.pu_Address_Street_1
                                or booking.pu_Address_street_2
                                or ""
                            )[:30],
                        ),
                        style_left,
                    ),
                ],
                [
                    Paragraph(
                        "<font size=%s>%s %s %s</font>"
                        % (
                            label_settings["font_size_medium"],
                            (booking.pu_Address_Suburb or "")[:30],
                            booking.pu_Address_State or "",
                            booking.pu_Address_PostalCode or "",
                        ),
                        style_left,
                    ),
                ],
                [
                    Spacer(1, 10),
                ],
            ]

            table_from = Table(
                tbl_data,
                colWidths=(left_part_width),
                style=[
                    ("TOPPADDING", (0, 0), (-1, -1), 0),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                    ("LEFTPADDING", (0, 0), (-1, -1), 0),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                ],
            )

            tbl_data = [
                [
                    Paragraph(
                        "<font size=%s><b>Contact:</b></font>"
                        % (label_settings["font_size_medium"],),
                        style_left,
                    ),
                    Paragraph(
                        "<font size=%s>%s</font>"
                        % (
                            label_settings["font_size_large"],
                            (booking.pu_Contact_F_L_Name or "")[:30],
                        ),
                        style_left,
                    ),
                ],
                [
                    Paragraph(
                        "<font size=%s><b>Phone:</b></font>"
                        % (label_settings["font_size_medium"],),
                        style_left,
                    ),
                    Paragraph(
                        "<font size=%s>%s</font>"
                        % (
                            label_settings["font_size_large"],
                            (booking.pu_Phone_Main or "")[:30],
                        ),
                        style_left,
                    ),
                ],
                [
                    Paragraph(
                        "<font size=%s><b>Cust Ref:</b></font>"
                        % (label_settings["font_size_medium"],),
                        style_left,
                    ),
                    Paragraph(
                        "<font size=%s>%s</font>"
                        % (
                            label_settings["font_size_large"],
                            (booking.b_client_order_num or "")[:30],
                        ),
                        style_left,
                    ),
                ],
            ]

            table_contact = Table(
                tbl_data,
                colWidths=(left_part_width * (2 / 5), left_part_width * (3 / 5)),
                style=[
                    ("TOPPADDING", (0, 0), (-1, -1), 0),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                    ("LEFTPADDING", (0, 0), (-1, -1), 0),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                ],
            )

            left_part = Table(
                [
                    [table_from],
                    [table_contact],
                ],
                colWidths=(left_part_width),
                style=[
                    ("TOPPADDING", (0, 0), (-1, -1), 0),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                    ("LEFTPADDING", (0, 0), (-1, -1), 0),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                ],
            )

            # --------------------- Right part -----------------------#

            tbl_data = [
                [
                    Paragraph(
                        "<font size=%s><b>To:</b></font>"
                        % (label_settings["font_size_large"],),
                        style_left,
                    ),
                ],
                [
                    Paragraph(
                        "<font size=%s><b>%s</b></font>"
                        % (
                            label_settings["font_size_slight_large"],
                            (booking.deToCompanyName or "")[:30],
                        ),
                        style_left,
                    ),
                ],
                [
                    Spacer(1, 10),
                ],
                [
                    Paragraph(
                        "<font size=%s>%s</font>"
                        % (
                            label_settings["font_size_medium"],
                            (booking.de_To_Address_Street_1 or "")[:30],
                        ),
                        style_left,
                    ),
                ],
                [
                    Paragraph(
                        "<font size=%s>%s</font>"
                        % (
                            label_settings["font_size_medium"],
                            (booking.de_To_Address_Street_2 or "")[:30],
                        ),
                        style_left,
                    ),
                ],
                [
                    Paragraph(
                        "<font size=%s><b>%s</b></font>"
                        % (
                            label_settings["font_size_slight_large"],
                            (booking.de_To_Address_Suburb or "")[:30],
                        ),
                        style_left,
                    ),
                ],
                [
                    Paragraph(
                        "<font size=%s><b>%s %s</b></font>"
                        % (
                            label_settings["font_size_slight_large"],
                            booking.de_To_Address_State or "",
                            booking.de_To_Address_PostalCode or "",
                        ),
                        style_left,
                    ),
                ],
                [
                    Spacer(1, 10),
                ],
            ]

            table_to = Table(
                tbl_data,
                colWidths=(right_part_width),
                style=[
                    ("TOPPADDING", (0, 0), (-1, -1), 0),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                    ("LEFTPADDING", (0, 0), (-1, -1), 0),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                ],
            )

            tbl_data = [
                [
                    Paragraph(
                        "<font size=%s><b>Contact:</b></font>"
                        % (label_settings["font_size_medium"],),
                        style_left,
                    ),
                    Paragraph(
                        "<font size=%s>%s</font>"
                        % (
                            label_settings["font_size_medium"],
                            (booking.de_to_Contact_F_LName or "")[:30],
                        ),
                        style_left,
                    ),
                ],
                [
                    Paragraph(
                        "<font size=%s><b>Phone:</b></font>"
                        % (label_settings["font_size_medium"],),
                        style_left,
                    ),
                    Paragraph(
                        "<font size=%s>%s</font>"
                        % (
                            label_settings["font_size_medium"],
                            (booking.de_to_Phone_Main or "")[:30],
                        ),
                        style_left,
                    ),
                ],
            ]

            table_contact = Table(
                tbl_data,
                colWidths=(right_part_width * (2 / 5), right_part_width * (3 / 5)),
                style=[
                    ("TOPPADDING", (0, 0), (-1, -1), 0),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                    ("LEFTPADDING", (0, 0), (-1, -1), 0),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                ],
            )

            tbl_data = [
                [
                    Paragraph(
                        "<font size=%s><b>Collection Date:</b></font>"
                        % (label_settings["font_size_medium"],),
                        style_left,
                    ),
                    Paragraph(
                        "<font size=%s>%s</font>"
                        % (
                            label_settings["font_size_medium"],
                            booking.puPickUpAvailFrom_Date.strftime("%d/%m/%Y")
                            if booking.puPickUpAvailFrom_Date
                            else "",
                        ),
                        style_left,
                    ),
                ],
                [
                    Paragraph(
                        "<font size=%s><b>Time Slot Del Date:</b></font>"
                        % (label_settings["font_size_medium"],),
                        style_left,
                    ),
                    Paragraph(
                        "<font size=%s>%s</font>"
                        % (
                            label_settings["font_size_medium"],
                            # booking.s_06_Latest_Delivery_Date_TimeSet.strftime(
                            #     "%d/%m/%Y"
                            # )
                            # if booking.s_06_Latest_Delivery_Date_TimeSet
                            # else "",
                            "",
                        ),
                        style_left,
                    ),
                ],
            ]

            table_collection = Table(
                tbl_data,
                colWidths=(right_part_width * (3 / 5), right_part_width * (2 / 5)),
                style=[
                    ("TOPPADDING", (0, 0), (-1, -1), 0),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                    ("LEFTPADDING", (0, 0), (-1, -1), 0),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                ],
            )

            right_part = Table(
                [
                    [table_to],
                    [table_contact],
                    [table_collection],
                ],
                colWidths=(right_part_width),
                style=[
                    ("TOPPADDING", (0, 0), (-1, -1), 0),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                    ("LEFTPADDING", (0, 0), (-1, -1), 0),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                    ("TOPPADDING", (0, 2), (-1, 2), 2),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                ],
            )

            # --------------------- Middle part -----------------------#

            middle_part = Table(
                [
                    [left_part, right_part],
                ],
                colWidths=(left_part_width, right_part_width),
                style=[
                    ("TOPPADDING", (0, 0), (-1, -1), 0),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                    ("LEFTPADDING", (0, 0), (-1, -1), 0),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                    ("LEFTPADDING", (1, 0), (1, -1), 5),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                ],
            )

            Story.append(middle_part)
            Story.append(Spacer(1, 5))

            hr = HRFlowable(
                width=(width),
                thickness=2,
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

            # --------------------- Consignment part -----------------------#

            tbl_data = [
                [
                    Paragraph(
                        "<font size=%s>CONSIGNMENT NO.</font>"
                        % (label_settings["font_size_large"],),
                        style_left,
                    ),
                    KeepInFrame(
                        right_part_width,
                        float(label_settings["line_height_extra_large"]) * mm,
                        [
                            Paragraph(
                                "<font size=%s>%s</font>"
                                % (
                                    label_settings["font_size_extra_large"],
                                    v_FPBookingNumber,
                                ),
                                style_left_extra_large,
                            ),
                        ],
                    ),
                ],
            ]

            consignment_part = Table(
                tbl_data,
                colWidths=(left_part_width, right_part_width),
                style=[
                    ("VALIGN", (0, 0), (1, 0), "MIDDLE"),
                    ("ALIGN", (0, 0), (0, 0), "LEFT"),
                    ("TOPPADDING", (0, 0), (0, 0), 5),
                    ("LEFTPADDING", (0, 0), (-1, -1), 0),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ],
            )

            Story.append(consignment_part)
            Story.append(Spacer(1, 12))

            Story.append(hr)
            Story.append(Spacer(1, 5))

            # --------------------- Barcode part -----------------------#

            barcode = gen_barcode(booking, v_FPBookingNumber, j)

            tbl_data = [
                [
                    code128.Code128(
                        barcode,
                        barHeight=20 * mm,
                        barWidth=2.5 if len(barcode) < 10 else 2,
                        humanReadable=False,
                    )
                ],
            ]

            table_barcode = Table(
                tbl_data,
                colWidths=(width),
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
                        "<font size=%s>%s of %s</font>"
                        % (label_settings["font_size_extra_large"], j, totalQty),
                        style_right_extra_large,
                    ),
                ],
            ]

            table_barcode_label = Table(
                tbl_data,
                colWidths=(width),
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

            # --------------------- Barcode part -----------------------#

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
                    footer_part_width * (4 / 9),
                    footer_part_width * (5 / 9),
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
        f"#119 [CAMERON LABEL] Finished building label... (Booking ID: {booking.b_bookingID_Visual})"
    )
    return filepath, f"{filename}.pdf"
