# Python 3.6.6

import datetime
import pysftp
from api.common.common_times import convert_to_AU_SYDNEY_tz
from api.fp_apis.utils import _convert_UOM
from api.fps.camerons import gen_sscc

from api.helpers.cubic import get_cubic_meter
from api.helpers.line import is_carton
from api.helpers.string import add_space

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
from reportlab.graphics.barcode.qr import QrCodeWidget
from reportlab.graphics.shapes import Drawing, Rect
from reportlab.graphics.barcode import createBarcodeDrawing
from reportlab.graphics.barcode import ecc200datamatrix
import uuid
import re
from treepoem import generate_barcode
from PIL import Image as PIL_Image

logger = logging.getLogger("dme_api")

styles = getSampleStyleSheet()
style_right = ParagraphStyle(name="right", parent=styles["Normal"], alignment=TA_RIGHT)
style_left = ParagraphStyle(
    name="left", parent=styles["Normal"], alignment=TA_LEFT, leading=12
)
style_left_large = ParagraphStyle(
    name="left", parent=styles["Normal"], alignment=TA_LEFT, leading=16
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
style_center_extra_large = ParagraphStyle(
    name="center", parent=styles["Normal"], alignment=TA_CENTER, leading=28
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


def gen_qrcode(booking, booking_line, v_FPBookingNumber, sscc, zone_code):
    consignment_num = v_FPBookingNumber

    label_code = (
        f"({sscc[:2]}){sscc[2:]}(401){consignment_num}(403){zone_code}(4320)ROAD {booking.vx_serviceName or 'EXPRESS'}"
        + f"(4321){1 if booking_line.e_dangerousGoods == True else 0}"
    )

    receiver_name = booking.deToCompanyName or booking.de_to_Contact_F_LName or ""[:38]

    if receiver_name:
        receiver_name = receiver_name.replace("(", "").replace(")", "").replace(",", "")
        label_code += f"(4300){receiver_name}"

    receiver_address1 = booking.de_To_Address_Street_1 or ""[:38]

    if receiver_address1:
        receiver_address1 = (
            receiver_name.replace("(", "").replace(")", "").replace(",", "")
        )
        label_code += f"(4302){receiver_address1}"

    receiver_address2 = booking.de_To_Address_Street_2 or ""[:38]

    if receiver_address2:
        receiver_address2 = (
            receiver_address2.replace("(", "").replace(")", "").replace(",", "")
        )
        label_code += f"(4303){receiver_address2}"

    receiver_suburb = booking.de_To_Address_Suburb or ""[:15]

    if receiver_suburb:
        label_code += f"(4304){receiver_suburb}"

    receiver_state = booking.de_To_Address_State or ""[:3]

    if receiver_state:
        label_code += f"(4306){receiver_state}"

    receiver_postcode = booking.de_To_Address_PostalCode or ""[:4]

    if receiver_postcode:
        label_code += f"(420){receiver_postcode}"

    receiver_phone = booking.de_to_Phone_Main or ""
    receiver_phone = receiver_phone.replace(" ", "")

    if receiver_phone:
        label_code += f"(4308){receiver_phone}"

    label_code += f"(4322){1 if booking.opt_authority_to_leave else 0}"

    despatch_date = booking.puPickUpAvailFrom_Date.strftime("%y%m%d%H%M")

    if despatch_date:
        label_code += f"(4324){despatch_date}"

    delivery_date = ""
    if booking.s_06_Latest_Delivery_Date_TimeSet:
        delivery_date = booking.s_06_Latest_Delivery_Date_TimeSet.strftime("%y%m%d%H%M")

        if delivery_date:
            label_code += f"(4325){delivery_date}"

    label_code = label_code.replace(" ", "+")

    return label_code


def gen_barcode(booking):
    ai_1 = "421"
    iso_country_code = "036"  # AU
    postcode = booking.de_To_Address_PostalCode.zfill(4)

    code = f"({ai_1}){iso_country_code}{postcode}"
    text = f"({ai_1}) {iso_country_code}{postcode}"
    return {"code": code, "text": text}


def _gen_sscc(booking, line, index, sscc):
    if not sscc or sscc.startswith("NOSSCC") or len(sscc) < 8:
        sscc = gen_sscc(booking, line, 0)
    if len(sscc.split(",")) > 0:
        sscc = sscc.split(",")[0]
    text = f"({sscc[0:2]}){sscc[2:]}"
    api_bcl.create(booking, [{"label_code": sscc}])
    return {"code": sscc, "text": text}


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


class LeftVerticalParagraph(Paragraph):
    """Paragraph that is printed vertically"""

    def __init__(self, text, style):
        super().__init__(text, style)
        self.horizontal_position = -self.style.leading

    def draw(self):
        """Draw text"""
        canvas = self.canv
        canvas.rotate(90)
        canvas.translate(120, -12)
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


class RightVerticalParagraph(Paragraph):
    """Paragraph that is printed vertically"""

    def __init__(self, text, style):
        super().__init__(text, style)
        self.horizontal_position = -self.style.leading

    def draw(self):
        """Draw text"""
        canvas = self.canv
        canvas.rotate(270)
        canvas.translate(-520, 15)
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


class InteractiveCheckedCheckBox(Flowable):
    def __init__(self, text=""):
        Flowable.__init__(self)
        self.text = text
        self.boxsize = 5

    def draw(self):
        self.canv.saveState()
        form = self.canv.acroForm
        form.checkbox(
            checked=True,
            buttonStyle="check",
            name=self.text,
            tooltip=self.text,
            relative=True,
            fillColor=colors.white,
            size=self.boxsize,
        )
        self.canv.restoreState()
        return


checkbox_checked = InteractiveCheckedCheckBox("")


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

    has_footer = False  # if true, show footer at the bottom

    if not lines:
        lines = Booking_lines.objects.filter(fk_booking_id=booking.pk_booking_id)

    if not os.path.exists(filepath):
        os.makedirs(filepath)

    if lines:
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

    img_filename = str(uuid.uuid4())
    img_filename_barcode1 = str(uuid.uuid4())
    img_filename_barcode2 = str(uuid.uuid4())

    if not os.path.exists(f"{filepath}/temp"):
        os.makedirs(f"{filepath}/temp")

    try:
        for temp_file in os.listdir(f"{filepath}/temp"):
            os.remove(os.path.join(f"{filepath}/temp", temp_file))
    except Exception as e:
        logger.info(f"#110 [Camerons LABEL] Error: {e}")

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
        "font_size_suburb_large": "16",
        "font_size_label_large": "22",
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
            ("SPAN", (1, 0), (2, 0)),
            ("SPAN", (4, 0), (5, 0)),
            ("SPAN", (1, 1), (2, 1)),
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
                checkbox_checked,
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

    # Special Instructions
    specialInstructions1 = ""
    specialInstructions2 = ""
    if booking.pu_pickup_instructions_address:
        specialInstructions1 += booking.pu_pickup_instructions_address
    if booking.pu_PickUp_Instructions_Contact:
        specialInstructions1 += f" {booking.pu_PickUp_Instructions_Contact}"
    if booking.de_to_PickUp_Instructions_Address:
        specialInstructions2 += f" {booking.de_to_PickUp_Instructions_Address}"
    if booking.de_to_Pick_Up_Instructions_Contact:
        specialInstructions2 += f" {booking.de_to_Pick_Up_Instructions_Contact}"

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
                Paragraph(
                    "<font size=%s>%s</font>"
                    % (
                        label_settings["font_size_extra_small"],
                        f"{specialInstructions1} {specialInstructions2}",
                    ),
                    style_left,
                ),
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

    delivery_time = ""
    if booking.s_06_Latest_Delivery_Date_TimeSet:
        delivery_time = convert_to_AU_SYDNEY_tz(
            booking.s_06_Latest_Delivery_Date_TimeSet
        )
        delivery_time = delivery_time.strftime("%d/%m/%Y %H:%M")

    is_general_service = True
    if booking.vx_serviceName and booking.vx_serviceName.lower() == "express":
        is_general_service = False

    # default end time of delivery time is 15:00
    if delivery_time:
        hour = booking.de_Deliver_By_Hours or "15"
        minute = booking.de_Deliver_By_Minutes
        delivery_time = f"{delivery_time}-{str(hour).zfill(2)}:{str(minute).zfill(2)}"

    general_service_part = Table(
        [
            [
                checkbox_checked if is_general_service else checkbox,
                Paragraph(
                    "<font size=%s>GENERAL SERVICE</font>"
                    % (label_settings["font_size_extra_small"],),
                    style_left,
                ),
                checkbox if is_general_service else checkbox_checked,
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
                Paragraph(
                    "<font size=%s>%s</font>"
                    % (
                        label_settings["font_size_extra_small"],
                        booking.b_clientReference_RA_Numbers,
                    ),
                    style_left,
                ),
            ]
        ],
        colWidths=[
            width * 0.05,
            width * 0.2,
            width * 0.05,
            width * 0.2,
            width * 0.12,
            width * 0.18,
            width * 0.05,
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

    is_hand_unload = False
    if (
        booking.b_booking_no_operator_pickup
        and booking.b_booking_no_operator_pickup > 0
    ) or (
        booking.b_bookingNoOperatorDeliver and booking.b_bookingNoOperatorDeliver > 0
    ):
        is_hand_unload = True

    is_tail_gate = False
    if booking.b_booking_tail_lift_pickup or booking.b_booking_tail_lift_deliver:
        is_tail_gate = True

    tailgate_part = Table(
        [
            [
                checkbox_checked if is_tail_gate else checkbox,
                Paragraph(
                    "<font size=%s>TAILGATE DELIVERY</font>"
                    % (label_settings["font_size_extra_small"],),
                    style_left,
                ),
            ],
            [
                checkbox_checked if is_hand_unload else checkbox,
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
    row_heights = [8]
    has_dangerous = False
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
                % (label_settings["font_size_extra_small"], ""),
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
        row_heights.append(8)
        total_qty = total_qty + line.e_qty
        total_weight = total_weight + line.e_qty * line.e_weightPerEach
        total_cubic = total_cubic + get_cubic_meter(
            line.e_dimLength,
            line.e_dimWidth,
            line.e_dimHeight,
            line.e_dimUOM,
            line.e_qty,
        )
        if line.e_dangerousGoods:
            has_dangerous = True
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
    row_heights.append(8)

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
        rowHeights=row_heights,
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
                checkbox_checked if has_dangerous else checkbox,
                Paragraph(
                    "<font size=%s>YES</font>"
                    % (label_settings["font_size_extra_small"],),
                    style_left,
                ),
                checkbox if has_dangerous else checkbox_checked,
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
                checkbox_checked,
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

    for line in lines:
        for k in range(line.e_qty):
            if one_page_label and k > 0:
                continue
            logger.info(f"#114 [CAMERON LABEL] Adding: {line}")

            # --------------------- Header -----------------------#

            tbl_data = [
                [
                    Paragraph(
                        "<font size=%s>DHL</font>"
                        % (label_settings["font_size_label_large"],),
                        style_left_extra_large,
                    ),
                    Paragraph(
                        "<font size=%s>DHL SUPPLY CHAIN</font>"
                        % (label_settings["font_size_large_title"],),
                        style_left,
                    ),
                    # Paragraph(
                    #     "<font size=%s color='white'>Book In</font>"
                    #     % (label_settings["font_size_label_large"],),
                    #     style_center_extra_large,
                    # ),
                    "",
                ],
                [
                    "",
                    Paragraph(
                        "<font size=%s>ROAD %s</font>"
                        % (
                            label_settings["font_size_large"],
                            (booking.vx_serviceName or "EXPRESS")[:20],
                        ),
                        style_left,
                    ),
                    "",
                ],
                [
                    "",
                    Paragraph(
                        "<font size=%s>C/N: <b>%s</b></font>"
                        % (
                            label_settings["font_size_large"],
                            (v_FPBookingNumber or "")[:20],
                        ),
                        style_left,
                    ),
                    # Paragraph(
                    #     "<font size=%s color='white'>DATE:%s</font>"
                    #     % (
                    #         label_settings["font_size_large"],
                    #         booking.b_dateBookedDate.strftime(
                    #             "%d/%m/%Y"
                    #         )
                    #         if booking.b_dateBookedDate
                    #         else booking.puPickUpAvailFrom_Date.strftime(
                    #             "%d/%m/%Y"
                    #         ),
                    #     ),
                    #     style_center,
                    # ),
                    "",
                ],
            ]

            header = Table(
                tbl_data,
                colWidths=[
                    # width * 0.25,
                    # width * 0.4,
                    # width * 0.35,
                    width * 0.3,
                    width * 0.4,
                    width * 0.3,
                ],
                style=[
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                    ("TOPPADDING", (0, 0), (-1, -1), 0),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                    ("LEFTPADDING", (0, 0), (-1, -1), 0),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                    ("LINEBELOW", (0, -1), (-1, -1), 0.5, colors.black),
                    ("SPAN", (0, 0), (0, -1)),
                    ("SPAN", (-1, 0), (-1, 1)),
                    ("VALIGN", (0, 0), (0, 0), "MIDDLE"),
                    ("VALIGN", (2, 0), (2, 0), "MIDDLE"),
                    # ("BACKGROUND", (2, 0), (2, -1), colors.black),
                ],
            )
            Story.append(header)
            Story.append(Spacer(1, 2))

            # --------------------- To Section ----------------------#

            tbl_data = [
                [
                    Paragraph(
                        "<font size=%s><b>To:</b></font>"
                        % (label_settings["font_size_large_title"],),
                        style_left,
                    ),
                    Paragraph(
                        "<font size=%s><b>%s</b></font>"
                        % (
                            label_settings["font_size_large_title"],
                            (booking.deToCompanyName or "")[:30],
                        ),
                        style_left,
                    ),
                ],
                [
                    "",
                    Paragraph(
                        "<font size=%s>%s</font>"
                        % (
                            label_settings["font_size_large_title"],
                            (booking.de_To_Address_Street_1 or "")[:30],
                        ),
                        style_left,
                    ),
                ],
                [
                    "",
                    Paragraph(
                        "<font size=%s>%s</font>"
                        % (
                            label_settings["font_size_large_title"],
                            (booking.de_To_Address_Street_2 or "")[:30],
                        ),
                        style_left,
                    ),
                ],
                [
                    "",
                    Paragraph(
                        "<font size=%s><b>%s %s %s</b></font>"
                        % (
                            label_settings["font_size_suburb_large"],
                            (booking.de_To_Address_Suburb or "")[:30],
                            booking.de_To_Address_State or "",
                            booking.de_To_Address_PostalCode or "",
                        ),
                        style_left_large,
                    ),
                ],
            ]

            to_section = Table(
                tbl_data,
                colWidths=[
                    width * 0.07,
                    width * 0.93,
                ],
                style=[
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                    ("TOPPADDING", (0, 0), (-1, -1), 0),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                    ("LEFTPADDING", (0, 0), (-1, -1), 0),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                    ("LINEBELOW", (0, -1), (-1, -1), 1, colors.black),
                    ("BOTTOMPADDING", (0, -1), (-1, -1), 2),
                ],
            )
            Story.append(to_section)

            # --------------------- Danger Section ----------------------#

            tbl_data = [
                [
                    "",
                    Paragraph(
                        "<font size=%s color='white'><b>%s</b></font>"
                        % (
                            label_settings["font_size_label_large"],
                            (pre_data["zone"] or "")[:20],
                        ),
                        style_left,
                    ),
                    Paragraph(
                        "<font size=%s>DG's</font>"
                        % (label_settings["font_size_medium"],),
                        style_left,
                    ),
                    Paragraph(
                        "<font size=%s>Ph: %s</font>"
                        % (
                            label_settings["font_size_medium"],
                            (booking.de_to_Phone_Main or "")[:30],
                        ),
                        style_left,
                    ),
                ],
                [
                    "",
                    "",
                    Paragraph(
                        "<font size=%s><b>%s</b></font>"
                        % (
                            label_settings["font_size_slight_large"],
                            "Yes" if line.e_dangerousGoods == True else "No",
                        ),
                        style_left,
                    ),
                    Paragraph(
                        "<font size=%s>Desp: %s</font>"
                        % (
                            label_settings["font_size_medium"],
                            booking.puPickUpAvailFrom_Date.strftime("%d/%m/%Y"),
                        ),
                        style_left,
                    ),
                ],
            ]

            danger_section = Table(
                tbl_data,
                colWidths=[
                    width * 0.07,
                    width * 0.4,
                    width * 0.18,
                    width * 0.35,
                ],
                style=[
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                    ("TOPPADDING", (0, 0), (-1, -1), 0),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                    ("LEFTPADDING", (0, 0), (-1, -1), 0),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                    ("LINEBELOW", (0, -1), (-1, -1), 1, colors.black),
                    ("LINEAFTER", (2, 0), (2, -1), 1, colors.black),
                    ("RIGHTPADDING", (2, 0), (2, -1), 2),
                    ("BOTTOMPADDING", (0, -1), (-1, -1), 2),
                    ("LEFTPADDING", (2, 0), (2, -1), 4),
                    ("LEFTPADDING", (3, 0), (3, -1), 4),
                    ("SPAN", (1, 0), (1, -1)),
                    ("BACKGROUND", (0, 0), (1, 1), colors.black),
                ],
            )
            Story.append(danger_section)

            # --------------------- QR Section ----------------------#

            sscc_info = _gen_sscc(booking, line, j - 1, sscc)

            qr_code_string = gen_qrcode(
                booking,
                booking_line,
                v_FPBookingNumber,
                sscc_info["code"],
                pre_data["zone"],
            )
            logger.info(f"#110 [Camerons LABEL] qr_code_string: {qr_code_string}")

            # code = ecc200datamatrix.ECC200DataMatrix(qr_code_string, barHeight=15 * mm, barWidth=1.8,)
            # code = ecc200datamatrix.ECC200DataMatrix(qr_code_string[:150], barHeight=15 * mm, barWidth=1.8)
            # code.x = 0
            # code.y = 0

            datamatrix = generate_barcode(
                barcode_type="gs1datamatrix",
                data=qr_code_string,
                options={
                    "parsefnc": False,
                    "format": "square",
                    "version": "52x52",
                    "includetext": True,
                    "dontlint": True,
                },
            )

            # Resize datamatrix to desired size
            dm_size_px = (190, 190)
            datamatrix = datamatrix.resize(dm_size_px, PIL_Image.NEAREST)

            # Create white picture
            picture_size_px = (200, 200)
            picture = PIL_Image.new("L", picture_size_px, color="white")

            # Position the datamatrix
            barcode_position_px = (5, 5)
            picture.paste(datamatrix, barcode_position_px)

            # Save the image
            picture.save(f"{filepath}/temp/{img_filename}_{j}.png")

            code = Image(f"{filepath}/temp/{img_filename}_{j}.png", 28 * mm, 28 * mm)

            tbl_data = [
                [
                    Paragraph(
                        "<font size=%s>Type:</font>"
                        % (label_settings["font_size_medium"],),
                        style_left,
                    ),
                    Paragraph(
                        "<font size=%s>%s</font>"
                        % (
                            label_settings["font_size_medium"],
                            "Carton"
                            if is_carton(line.e_type_of_packaging)
                            else "Pallet",
                        ),
                        style_left,
                    ),
                    Paragraph(
                        "<font size=%s>%s</font>"
                        % (
                            label_settings["font_size_medium"],
                            "",
                        ),
                        style_left,
                    ),
                    Paragraph(
                        "<font size=%s>Tot Wt: %skgs</font>"
                        % (
                            label_settings["font_size_medium"],
                            round(total_weight, 2),
                        ),
                        style_left,
                    ),
                    code,
                ],
                [
                    Paragraph(
                        "<font size=%s>Itm:</font>"
                        % (label_settings["font_size_medium"],),
                        style_left,
                    ),
                    Paragraph(
                        "<font size=%s><b>%s/%s</b></font>"
                        % (
                            label_settings["font_size_large"],
                            j,
                            totalQty,
                        ),
                        style_left,
                    ),
                    Paragraph(
                        "<font size=%s></font>" % (label_settings["font_size_medium"],),
                        style_left,
                    ),
                    Paragraph(
                        "<font size=%s>Tot Vol: %sm3</font>"
                        % (
                            label_settings["font_size_medium"],
                            round(total_cubic, 2),
                        ),
                        style_left,
                    ),
                    "",
                ],
                [
                    Paragraph(
                        "<font size=%s></font>" % (label_settings["font_size_medium"],),
                        style_left,
                    ),
                    "",
                    "",
                    "",
                    "",
                ],
                [
                    Paragraph(
                        "<font size=%s>%s</font>"
                        % (
                            label_settings["font_size_medium"],
                            booking.b_client_sales_inv_num,
                        ),
                        style_left,
                    ),
                    "",
                    "",
                    "",
                    "",
                ],
                [
                    Paragraph(
                        "<font size=%s>%s</font>"
                        % (
                            label_settings["font_size_medium"],
                            booking.b_client_order_num,
                        ),
                        style_left,
                    ),
                    "",
                    "",
                    "",
                    "",
                ],
                [
                    Paragraph(
                        "<font size=%s>%s</font>"
                        % (label_settings["font_size_medium"], specialInstructions1),
                        style_left,
                    ),
                    "",
                    "",
                    "",
                    "",
                ],
                [
                    Paragraph(
                        "<font size=%s>%s</font>"
                        % (label_settings["font_size_medium"], specialInstructions2),
                        style_left,
                    ),
                    "",
                    "",
                    "",
                    "",
                ],
            ]

            qr_section = Table(
                tbl_data,
                colWidths=[
                    width * 0.08,
                    width * 0.15,
                    width * 0.15,
                    width * 0.25,
                    width * 0.37,
                ],
                style=[
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                    ("TOPPADDING", (0, 0), (-1, -1), 0),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                    ("LEFTPADDING", (0, 0), (-1, -1), 0),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                    ("LINEBELOW", (0, 1), (3, 1), 1, colors.black),
                    ("LINEBELOW", (0, 4), (3, 4), 1, colors.black),
                    ("LINEBELOW", (0, -1), (-1, -1), 1, colors.black),
                    ("SPAN", (4, 0), (4, -1)),
                    ("SPAN", (0, 2), (-1, 2)),
                    ("SPAN", (0, 3), (-1, 3)),
                    ("SPAN", (0, 4), (-1, 4)),
                    ("SPAN", (0, 5), (-1, 5)),
                    ("SPAN", (0, 6), (-1, 6)),
                    ("VALIGN", (4, 0), (4, 0), "MIDDLE"),
                    ("ALIGN", (4, 0), (4, 0), "CENTER"),
                ],
            )
            Story.append(qr_section)

            # --------------------- From Section -----------------------#

            tbl_data = [
                [
                    Paragraph(
                        "<font size=%s>From: %s</font>"
                        % (
                            label_settings["font_size_medium"],
                            (booking.puCompany or "")[:30],
                        ),
                        style_left,
                    ),
                    Paragraph(
                        "<font size=%s>Ph: %s</font>"
                        % (
                            label_settings["font_size_medium"],
                            (booking.pu_Phone_Main or "")[:30],
                        ),
                        style_left,
                    ),
                ],
                [
                    Paragraph(
                        "<font size=%s>Contact: %s</font>"
                        % (
                            label_settings["font_size_medium"],
                            (booking.pu_Contact_F_L_Name or "")[:30],
                        ),
                        style_left,
                    ),
                    Paragraph(
                        "<font size=%s>Payor A/C: %s</font>"
                        % (
                            label_settings["font_size_medium"],
                            "12265",  # for DME
                        ),
                        style_left,
                    ),
                ],
                [
                    Paragraph(
                        "<font size=%s>I hereby declare that this consignment %s DG's as per associated DGD</font>"
                        % (
                            label_settings["font_size_extra_medium"],
                            "contains"
                            if line.e_dangerousGoods == True
                            else "do not contain",
                        ),
                        style_left,
                    ),
                    "",
                ],
            ]

            from_section = Table(
                tbl_data,
                colWidths=[
                    width * 0.7,
                    width * 0.3,
                ],
                style=[
                    ("TOPPADDING", (0, 0), (-1, -1), 0),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                    ("LEFTPADDING", (0, 0), (-1, -1), 0),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                    ("LINEBELOW", (0, -1), (-1, -1), 1, colors.black),
                    ("SPAN", (0, -1), (-1, -1)),
                ],
            )

            Story.append(from_section)
            Story.append(Spacer(1, 2))

            # --------------------- Barcode Section -----------------------#

            Story.append(Spacer(1, 2))
            barcode = gen_barcode(booking)

            image = generate_barcode(
                barcode_type="gs1-128",  # One of the BWIPP supported codes.
                data=barcode["code"],
            )
            image.convert("1").save(f"{filepath}/temp/{img_filename_barcode1}_{j}.png")

            routing_barcode_image = Image(
                f"{filepath}/temp/{img_filename_barcode1}_{j}.png",
                50 * mm,
                (15 if has_footer else 20) * mm,
            )

            image = generate_barcode(
                barcode_type="gs1-128",  # One of the BWIPP supported codes.
                data=sscc_info["text"],
            )
            image.convert("1").save(f"{filepath}/temp/{img_filename_barcode2}_{j}.png")
            sscc_barcode_image = Image(
                f"{filepath}/temp/{img_filename_barcode2}_{j}.png",
                60 * mm,
                (15 if has_footer else 20) * mm,
            )

            tbl_data = [
                [
                    LeftVerticalParagraph(
                        "<font size=%s>CARRIER'S TERMS AND CONDITIONS APPLY</font>"
                        % (label_settings["font_size_extra_small"],),
                        style_left,
                    ),
                    routing_barcode_image,
                    RightVerticalParagraph(
                        "<font size=%s>PRINTED DATE %s  <br/> SUBJECT TO SECURITY SCREENING AND CLEARING</font>"
                        % (
                            label_settings["font_size_extra_small"],
                            datetime.datetime.now().strftime("%d/%m/%Y"),
                        ),
                        ParagraphStyle(
                            name="center",
                            parent=styles["Normal"],
                            alignment=TA_CENTER,
                            leading=6,
                        ),
                    ),
                ],
                [
                    "",
                    Paragraph(
                        "<font size=%s>%s</font>"
                        % (
                            label_settings["font_size_medium"],
                            barcode["text"],
                        ),
                        style_center,
                    ),
                    "",
                ],
                [
                    "",
                    sscc_barcode_image,
                    "",
                ],
                [
                    "",
                    Paragraph(
                        "<font size=%s>%s</font>"
                        % (
                            label_settings["font_size_medium"],
                            f"({sscc_info['code'][0:2]}) {sscc_info['code'][2:]}",
                        ),
                        style_center,
                    ),
                    Paragraph(
                        "<font size=%s></font>"
                        % (label_settings["font_size_slight_large"],),
                        style_right,
                    ),
                ],
                [
                    "",
                    "",
                    "",
                ],
            ]

            row_heights = [55, 15, 55, 15, 5]
            if has_footer:
                row_heights = [42, 15, 42, 15, 30]

            barcode_section = Table(
                tbl_data,
                colWidths=[
                    width * 0.1,
                    width * 0.7,
                    width * 0.2,
                ],
                rowHeights=row_heights,
                style=[
                    ("TOPPADDING", (0, 0), (-1, -1), 0),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                    ("LEFTPADDING", (0, 0), (-1, -1), 0),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                    ("SPAN", (0, 0), (0, -1)),
                    ("SPAN", (-1, 0), (-1, -1)),
                    # ("BACKGROUND", (-1, -1), (-1, -1), colors.black),
                    ("BOTTOMPADDING", (0, -1), (-1, -1), 2),
                ],
            )

            Story.append(barcode_section)

            Story.append(Spacer(1, 2))

            # --------------------- Footer Section -----------------------#

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

            if has_footer:
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
