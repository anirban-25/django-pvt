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
from reportlab.graphics.barcode.code128 import Code128
from reportlab.lib import colors

from api.models import Booking_lines, Booking_lines_data
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


class VerticalBarcode(Flowable):
    """Barcode that is printed vertically"""

    def __init__(self, barCode, barHeight, barWidth, humanReadable):
        super().__init__()
        self.barcode = Code128(
            barCode, barHeight=barHeight, barWidth=barWidth, humanReadable=humanReadable
        )
        self.width = self.barcode.width
        self.height = self.barcode.height

    def draw(self):
        """Draw text"""
        canvas = self.canv
        canvas.rotate(90)
        self.barcode.drawOn(canvas, -self.width / 2, -self.height)
        # super().draw()

    def wrap(self, available_width, available_height):
        """Wrap the vertical barcode"""
        self.width, self.height = self.barcode.wrap(available_height, available_width)
        return self.width, self.height  # Return width and height as swapped


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
        f"#110 [DXT LABEL] Started building label... (Booking ID: {booking.b_bookingID_Visual}, Lines: {lines})"
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
    logger.info(f"#111 [DXT LABEL] File full path: {filepath}/{filename}.pdf")

    label_settings = {
        "font_family": "Verdana",
        "font_size_smallest": "3",
        "font_size_extra_small": "4",
        "font_size_slight_small": "5",
        "font_size_small": "6",
        "font_size_extra_medium": "7",
        "font_size_medium": "8",
        "font_size_large_title": "9",
        "font_size_large": "11",
        "font_size_slight_large": "24",
        "font_size_extra_large": "26",
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

    # Main Label

    logger.info(
        f"#110 [DXT LABEL] Started building main label... (Booking ID: {booking.b_bookingID_Visual})"
    )

    width = float(label_settings["label_image_size_length"]) * mm

    left_part_width = width * 0.9
    right_part_width = width * 0.1

    dxt_logo = "./static/assets/logos/dxt_logo.png"

    closed = "1:00 PM"

    closed_hours = (
        booking.pu_PickUp_By_Time_Hours if booking.pu_PickUp_By_Time_Hours else 0
    )
    closed_minutes = (
        booking.pu_PickUp_By_Time_Minutes if booking.pu_PickUp_By_Time_Minutes else 0
    )

    if closed_hours > 0:
        closed = f"{closed_hours - 12 if closed_hours > 12 else closed_hours}:{closed_minutes} {'PM' if closed_hours > 12 else 'AM'}"

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

    dxt_img = Image(dxt_logo, 30 * mm, 20 * mm)

    total_weight = 0
    total_cubic = 0

    for line in lines:
        total_weight = total_weight + line.e_qty * line.e_weightPerEach
        total_cubic = total_cubic + get_cubic_meter(
            line.e_dimLength,
            line.e_dimWidth,
            line.e_dimHeight,
            line.e_dimUOM,
            line.e_qty,
        )


    for line in lines:
        for k in range(line.e_qty):
            if one_page_label and k > 0:
                continue
            logger.info(f"#114 [DXT LABEL] Adding: {line}")

            # --------------------- Header -----------------------#

            tbl_data = [
                [
                    Paragraph(
                        "<font size=%s><b>%s</b></font>"
                        % (
                            label_settings["font_size_extra_large"],
                            (pre_data["zone"] or "")[:10],
                        ),
                        style_left_extra_large,
                    ),
                    "",
                    "",
                    dxt_img,
                ],
                [
                    Paragraph(
                        "<font size=%s>Weight (kg)</font>"
                        % (label_settings["font_size_extra_medium"],),
                        style_left,
                    ),
                    Paragraph(
                        "<font size=%s>Volumue (m3)</font>"
                        % (label_settings["font_size_extra_medium"],),
                        style_left,
                    ),
                    Paragraph(
                        "<font size=%s><b>%s / %s</b></font>"
                        % (label_settings["font_size_slight_large"], j, totalQty),
                        style_center,
                    ),
                    "",
                ],
                [
                    Paragraph(
                        "<font size=%s>%s</font>"
                        % (
                            label_settings["font_size_extra_medium"],
                            round(total_weight, 2),
                        ),
                        style_left,
                    ),
                    Paragraph(
                        "<font size=%s>%s</font>"
                        % (
                            label_settings["font_size_extra_medium"],
                            round(total_cubic, 4),
                        ),
                        style_left,
                    ),
                    "",
                    "",
                ],
                [
                    Paragraph(
                        "<font size=%s><b>%s</b></font>"
                        % (label_settings["font_size_large"], v_FPBookingNumber),
                        style_left,
                    ),
                    "",
                    "",
                    Paragraph(
                        "<font size=%s>%s</font>"
                        % (
                            label_settings["font_size_large"],
                            booking.b_dateBookedDate.strftime("%d/%m/%Y")
                            if booking.b_dateBookedDate
                            else "",
                        ),
                        style_right,
                    ),
                ],
            ]

            header = Table(
                tbl_data,
                colWidths=(width * 0.2, width * 0.2, width * 0.3, width * 0.3),
                style=[
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                    ("TOPPADDING", (0, 0), (-1, -1), 0),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                    ("LEFTPADDING", (0, 0), (-1, -1), 0),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                    ("SPAN", (0, 0), (1, 0)),
                    ("SPAN", (2, 0), (3, 0)),
                    ("SPAN", (2, 1), (2, 2)),
                    ("SPAN", (0, 3), (2, 3)),
                    ("SPAN", (3, 0), (3, 2)),
                    ("TOPPADDING", (0, 1), (-1, 1), 4),
                    ("TOPPADDING", (0, -1), (-1, -1), 4),
                ],
            )
            Story.append(header)
            Story.append(Spacer(1, 5))

            # --------------------- Left part -----------------------#

            tbl_data = [
                [
                    Paragraph(
                        "<font size=%s><b>Sender:</b></font>"
                        % (label_settings["font_size_extra_medium"],),
                        style_left,
                    ),
                ],
                [
                    Paragraph(
                        "<font size=%s>%s %s</font>"
                        % (
                            label_settings["font_size_extra_medium"],
                            (booking.puCompany or "")[:30],
                            (
                                booking.pu_Address_Street_1
                                or booking.pu_Address_street_2
                                or "",
                            )[:30],
                        ),
                        style_left,
                    ),
                ],
                [
                    Paragraph(
                        "<font size=%s>%s</font>"
                        % (
                            label_settings["font_size_extra_medium"],
                            (booking.pu_Address_Suburb or "")[:30],
                        ),
                        style_left,
                    ),
                ],
                [
                    Paragraph(
                        "<font size=%s>%s, %s</font>"
                        % (
                            label_settings["font_size_extra_medium"],
                            booking.pu_Address_State or "",
                            booking.pu_Address_PostalCode or "",
                        ),
                        style_left,
                    ),
                ],
                [
                    Paragraph(
                        "<font size=%s>%s</font>"
                        % (
                            label_settings["font_size_extra_medium"],
                            (booking.clientRefNumbers or "")[:30],
                        ),
                        style_left,
                    ),
                ],
                [
                    Paragraph(
                        "<font size=%s>%s %s</font>"
                        % (
                            label_settings["font_size_extra_medium"],
                            (booking.pu_Contact_F_L_Name or "")[:30],
                            (booking.pu_Phone_Main or "")[:30],
                        ),
                        style_right,
                    ),
                ],
                [
                    Paragraph(
                        "<font size=%s><b>Booking</b> %s</font>"
                        % (
                            label_settings["font_size_large"],
                            booking.puPickUpAvailFrom_Date.strftime(
                                "%d/%m/%Y %I:%M %p"
                            ),
                        ),
                        style_left,
                    ),
                ],
                [
                    Paragraph(
                        "<font size=%s><b>Close</b> %s</font>"
                        % (
                            label_settings["font_size_large"],
                            closed,
                        ),
                        style_left,
                    ),
                ],
                [
                    Spacer(1, 5),
                ],
                [
                    Paragraph(
                        "<font size=%s><b>Special Instructions:</b></font>"
                        % (label_settings["font_size_extra_medium"],),
                        style_left,
                    ),
                ],
                [
                    Paragraph(
                        "<font size=%s>%s</font>"
                        % (
                            label_settings["font_size_extra_medium"],
                            specialInstructions,
                        ),
                        style_left,
                    ),
                ],
                [
                    Spacer(1, 5),
                ],
                [
                    Paragraph(
                        "<font size=%s><b>Receiver:</b></font>"
                        % (label_settings["font_size_extra_medium"],),
                        style_left,
                    ),
                ],
                [
                    Paragraph(
                        "<font size=%s>%s</font>"
                        % (
                            label_settings["font_size_large"],
                            (booking.deToCompanyName or "")[:30],
                        ),
                        style_left,
                    ),
                ],
                [
                    Paragraph(
                        "<font size=%s>%s</font>"
                        % (
                            label_settings["font_size_large"],
                            (
                                booking.de_To_Address_Street_1
                                or booking.de_To_Address_Street_2
                                or ""
                            )[:30],
                        ),
                        style_left,
                    ),
                ],
                [
                    Paragraph(
                        "<font size=%s>%s</font>"
                        % (
                            label_settings["font_size_large"],
                            (booking.de_To_Address_Suburb or "")[:30],
                        ),
                        style_left,
                    ),
                ],
                [
                    Paragraph(
                        "<font size=%s>%s, %s</font>"
                        % (
                            label_settings["font_size_large"],
                            booking.de_To_Address_State or "",
                            booking.de_To_Address_PostalCode or "",
                        ),
                        style_left,
                    ),
                ],
                [Spacer(1, 10)],
                [
                    Paragraph(
                        "<font size=%s>%s %s</font>"
                        % (
                            label_settings["font_size_extra_medium"],
                            (booking.de_to_Contact_F_LName or "")[:30],
                            (booking.de_to_Phone_Main or "")[:20],
                        ),
                        style_right,
                    ),
                ],
            ]

            left_part = Table(
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

            # --------------------- Right part -----------------------#

            barcode = gen_barcode(booking, v_FPBookingNumber, j)

            barcode_part = VerticalBarcode(
                barcode,
                barHeight=8 * mm,
                barWidth=2 if len(barcode) < 10 else 1.5,
                humanReadable=False,
            )

            right_part = Table(
                [
                    [barcode_part],
                ],
                colWidths=(right_part_width),
                style=[
                    ("TOPPADDING", (0, 0), (-1, -1), 80),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                    ("LEFTPADDING", (0, 0), (-1, -1), 4),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 0),
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
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                ],
            )

            Story.append(middle_part)
            Story.append(Spacer(1, 10))

            clientRefNumbers = [] # Get client ref Numbers
            try:
                booking_lines_data = Booking_lines_data.objects.filter(
                    fk_booking_lines_id=line.pk_booking_lines_id
                ).only("clientRefNumber")

                for booking_line_data in booking_lines_data:
                    clientRefNumber = booking_line_data.clientRefNumber
                    if clientRefNumber and not clientRefNumber in clientRefNumbers:
                        clientRefNumbers.append(clientRefNumber)

                if booking.b_client_sales_inv_num: # Concatenate this according to Pete's requirement
                    clientRefNumbers.append(booking.b_client_sales_inv_num)
            except Exception as e:
                logger.error(f"#554 [clientRefNumbers] - {str(e)}")

            # --------------------- Bottom part -----------------------#

            tbl_data = [
                [
                    Paragraph(
                        "<font size=%s>%s, %s</font>"
                        % (
                            label_settings["font_size_extra_medium"],
                            line.e_type_of_packaging or "N/A",
                            ", ".join(clientRefNumbers) or "N/A",
                        ),
                        style_center,
                    ),
                ],
                [
                    Code128(
                        barcode,
                        barHeight=20 * mm,
                        barWidth=2.5 if len(barcode) < 10 else 2,
                        humanReadable=False,
                    )
                ],
                [
                    Paragraph(
                        "<font size=%s><b>%s</b></font>"
                        % (
                            label_settings["font_size_large_title"],
                            barcode,
                        ),
                        style_center,
                    ),
                ],
            ]

            bottom_part = Table(
                tbl_data,
                colWidths=(width),
                style=[
                    ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                    ("VALIGN", (0, 0), (0, -1), "TOP"),
                    ("TOPPADDING", (0, 0), (-1, -1), 0),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
                    ("LEFTPADDING", (0, 0), (0, -1), 0),
                    ("RIGHTPADDING", (0, 0), (0, -1), 0),
                ],
            )

            Story.append(bottom_part)

            Story.append(Spacer(1, 5))

            # --------------------- Footer part -----------------------#

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

            # Aberdeen Paper
            if booking.kf_client_id == "4ac9d3ee-2558-4475-bdbb-9d9405279e81":
                Story.append(footer_part)

            Story.append(PageBreak())

            j += 1

    doc.build(Story, onFirstPage=myFirstPage, onLaterPages=myLaterPages)

    # end writting data into pdf file
    file.close()
    logger.info(
        f"#119 [DXT LABEL] Finished building label... (Booking ID: {booking.b_bookingID_Visual})"
    )
    return filepath, f"{filename}.pdf"

def build_consignment(
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
        f"#110 [DXT CONSIGNMENT] Started building consignment... (Booking ID: {booking.b_bookingID_Visual}, Lines: {lines})"
    )
    v_FPBookingNumber = pre_data["v_FPBookingNumber"]
    if not lines:
        lines = Booking_lines.objects.filter(fk_booking_id=booking.pk_booking_id)
    
    if not os.path.exists(filepath):
        os.makedirs(filepath)

    filename = f"DME{booking.b_bookingID_Visual}"

    file = open(f"{filepath}/{filename}_consignment.pdf", "w")
    logger.info(f"#111 [DXT CONSIGNMENT] File full path: {filepath}/{filename}_consignment.pdf")

    label_settings = {
        "font_family": "Verdana",
        "font_size_smallest": "3",
        "font_size_extra_small": "4",
        "font_size_slight_small": "5",
        "font_size_small": "6",
        "font_size_extra_medium": "7",
        "font_size_medium": "8",
        "font_size_large_title": "9",
        "font_size_large": "11",
        "font_size_slight_large": "24",
        "font_size_extra_large": "26",
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

    Story_consignment = []

    # Delivery's Copy

    logger.info(
        f"#110 [DXT CONSIGNMENT] Started building Delivery's copy... (Booking ID: {booking.b_bookingID_Visual})"
    )

    dxt_logo_consignment = "./static/assets/logos/dxt_logo_consignment.png"
    dxt_img = Image(dxt_logo_consignment, 38 * mm, 10 * mm)

    closed = "1:00 PM"

    closed_hours = (
        booking.pu_PickUp_By_Time_Hours if booking.pu_PickUp_By_Time_Hours else 0
    )
    closed_minutes = (
        booking.pu_PickUp_By_Time_Minutes if booking.pu_PickUp_By_Time_Minutes else 0
    )

    if closed_hours > 0:
        closed = f"{closed_hours - 12 if closed_hours > 12 else closed_hours}:{closed_minutes} {'PM' if closed_hours > 12 else 'AM'}"

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

    total_weight = 0
    total_cubic = 0
    total_qty = 0

    for line in lines:
        total_weight = total_weight + line.e_qty * line.e_weightPerEach
        total_qty = total_qty + line.e_qty
        total_cubic = total_cubic + get_cubic_meter(
            line.e_dimLength,
            line.e_dimWidth,
            line.e_dimHeight,
            line.e_dimUOM,
            line.e_qty,
        )

    # -------------------- Header part ------------------------

    GS1_FNC1_CHAR = "\xf1"
    barcode = f"{GS1_FNC1_CHAR}{v_FPBookingNumber}"

    tbl_data = [
        [
            dxt_img,
            Paragraph(
                "<font size=%s><b>PROOF OF DELIVERY</b></font>"
                % (label_settings["font_size_slight_small"]),
                style_center,
            ),
            Paragraph(
                "<font size=%s><b>Standard</b></font>"
                % (label_settings["font_size_extra_small"]),
                style_right,
            ),
            Paragraph(
                "<font size=%s><b>%s</b></font>"
                % (
                    label_settings["font_size_extra_small"],
                    booking.b_dateBookedDate.strftime("%d/%m/%Y")
                    if booking.b_dateBookedDate
                    else "",
                ),
                style_right,
            ),
        ],
        [
            "",
            "",
            Code128(
                barcode,
                barHeight=6 * mm,
                barWidth=0.5 if len(barcode) < 10 else 0.4,
                humanReadable=False,
            ),
            "",
        ],
        [
            Paragraph(
                "<font size=%s>DELIVER-ME PTY LTD</font>"
                % (label_settings["font_size_slight_small"]),
                style_left,
            ),
            "",
            Paragraph(
                "<font size=%s><b>%s</b></font>"
                % (label_settings["font_size_slight_small"], v_FPBookingNumber),
                style_center,
            ),
            "",
        ],
    ]

    header = Table(
        tbl_data,
        colWidths=[width * 0.4, width * 0.3, width * 0.15, width * 0.15],
        rowHeights=[6, 22, 6],
        style=[
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("VALIGN", (2, 1), (2, 1), "BOTTOM"),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("ALIGN", (0, 0), (0, 0), "LEFT"),
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ("SPAN", (0, 0), (0, 1)),
            ("SPAN", (2, 1), (3, 1)),
            ("SPAN", (2, 2), (3, 2)),
        ],
    )

    # -------------------- First Section ------------------------

    first_section = Table(
        [
            [
                Paragraph(
                    "<font size=%s>Sender</font>"
                    % (label_settings["font_size_slight_small"],),
                    style_left_noleading,
                ),
                "",
                Paragraph(
                    "<font size=%s>Receiver</font>"
                    % (label_settings["font_size_slight_small"],),
                    style_left_noleading,
                ),
                "",
                "",
            ],
            [
                Paragraph(
                    "<font size=%s><b>%s</b></font>"
                    % (
                        label_settings["font_size_extra_small"],
                        (booking.puCompany or "")[:30],
                    ),
                    style_left_noleading,
                ),
                "",
                Paragraph(
                    "<font size=%s><b>%s</b></font>"
                    % (
                        label_settings["font_size_extra_small"],
                        (booking.deToCompanyName or "")[:30],
                    ),
                    style_left_noleading,
                ),
                "",
                "",
            ],
            [
                Paragraph(
                    "<font size=%s><b>%s</b></font>"
                    % (
                        label_settings["font_size_extra_small"],
                        (booking.pu_Address_Street_1 or "")[:30],
                    ),
                    style_left_noleading,
                ),
                "",
                Paragraph(
                    "<font size=%s><b>%s</b></font>"
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
                Paragraph(
                    "<font size=%s><b>%s</b></font>"
                    % (
                        label_settings["font_size_extra_small"],
                        (booking.pu_Address_street_2 or "")[:30],
                    ),
                    style_left_noleading,
                ),
                "",
                Paragraph(
                    "<font size=%s><b>%s</b></font>"
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
                Paragraph(
                    "<font size=%s><b>%s %s, %s</b></font>"
                    % (
                        label_settings["font_size_extra_small"],
                        (booking.pu_Address_Suburb or "")[:30],
                        booking.pu_Address_State or "",
                        booking.pu_Address_PostalCode or "",
                    ),
                    style_left_noleading,
                ),
                "",
                Paragraph(
                    "<font size=%s><b>%s %s, %s</b></font>"
                    % (
                        label_settings["font_size_extra_small"],
                        (booking.de_To_Address_Suburb or "")[:30],
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
                    "<font size=%s>%s %s</font>"
                    % (
                        label_settings["font_size_extra_small"],
                        (booking.pu_Contact_F_L_Name or "")[:30],
                        (booking.pu_Phone_Main or "")[:30],
                    ),
                    style_left_noleading,
                ),
                "",
                Paragraph(
                    "<font size=%s>%s %s</font>"
                    % (
                        label_settings["font_size_extra_small"],
                        (booking.de_to_Contact_F_LName or "")[:30],
                        (booking.de_to_Phone_Main or "")[:20],
                    ),
                    style_left_noleading,
                ),
                "",
                "",
            ],
            [
                Paragraph(
                    "<font size=%s>SenderReference: %s</font>"
                    % (
                        label_settings["font_size_extra_small"],
                        booking.clientRefNumbers,
                    ),
                    style_left_noleading,
                ),
                "",
                Paragraph(
                    "<font size=%s>ReceiverReference: %s</font>"
                    % (
                        label_settings["font_size_extra_small"],
                        booking.gap_ras,
                    ),
                    style_left_noleading,
                ),
                "",
                "",
            ],
            [
                "",
                "",
                Paragraph(
                    "<font size=%s>Dangerous Goods</font>"
                    % (label_settings["font_size_extra_small"],),
                    style_left_noleading,
                ),
                Paragraph(
                    "<font size=%s>Booking: %s</font>"
                    % (
                        label_settings["font_size_extra_small"],
                        booking.puPickUpAvailFrom_Date.strftime("%d/%m/%Y %I:%M %p"),
                    ),
                    style_left_noleading,
                ),
                Paragraph(
                    "<font size=%s>Close: %s</font>"
                    % (
                        label_settings["font_size_extra_small"],
                        closed,
                    ),
                    style_left_noleading,
                ),
            ],
            [
                Paragraph(
                    "<font size=%s>Instructions:</font>"
                    % (label_settings["font_size_extra_small"],),
                    style_left_noleading,
                ),
                "",
                "",
                Paragraph(
                    "<font size=%s><b>Instructions: %s</b></font>"
                    % (
                        label_settings["font_size_extra_medium"],
                        specialInstructions,
                    ),
                    style_left_noleading,
                ),
                "",
            ],
            # [
            #     Paragraph(
            #         "<font size=%s>Equipment Type</font>"
            #         % (label_settings["font_size_extra_small"],),
            #         style_left_noleading,
            #     ),
            #     Paragraph(
            #         "<font size=%s>Count</font>"
            #         % (label_settings["font_size_extra_small"],),
            #         style_left_noleading,
            #     ),
            #     "",
            #     "",
            #     "",
            # ],
            # [
            #     Paragraph(
            #         "<font size=%s>%s</font>"
            #         % (label_settings["font_size_extra_small"], ""),
            #         style_left_noleading,
            #     ),
            #     Paragraph(
            #         "<font size=%s>%s</font>"
            #         % (label_settings["font_size_extra_small"], len(lines)),
            #         style_left_noleading,
            #     ),
            #     "",
            #     "",
            #     "",
            # ],
        ],
        colWidths=[
            width * 0.15,
            width * 0.3,
            width * 0.15,
            width * 0.25,
            width * 0.15,
        ],
        rowHeights=[7, 6, 6, 6, 6, 6, 6, 6, 8],
        # rowHeights=[7, 6, 6, 6, 6, 6, 6, 6, 8, 6, 6],
        style=[
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ("SPAN", (0, 0), (1, 0)),
            ("SPAN", (0, 1), (1, 1)),
            ("SPAN", (0, 2), (1, 2)),
            ("SPAN", (0, 3), (1, 3)),
            ("SPAN", (0, 4), (1, 4)),
            ("SPAN", (0, 5), (1, 5)),
            ("SPAN", (0, 6), (1, 6)),
            ("SPAN", (2, 0), (3, 0)),
            ("SPAN", (2, 1), (3, 1)),
            ("SPAN", (2, 2), (3, 2)),
            ("SPAN", (2, 3), (3, 3)),
            ("SPAN", (2, 4), (3, 4)),
            ("SPAN", (2, 5), (3, 5)),
            ("SPAN", (2, 6), (3, 6)),
            ("SPAN", (3, 8), (4, 8)),
            ("LEFTPADDING", (0, 0), (0, 8), 2),
            ("LEFTPADDING", (2, 0), (2, 6), 16),
        ],
    )    

    # -------------------- Third Section ------------------------

    tbl_data = [
        [
            Paragraph(
                "<font size=%s>Total Qty %s</font>"
                % (label_settings["font_size_extra_small"], total_qty),
                style_left,
            ),
            Paragraph(
                "<font size=%s>Total Weigth %s</font>"
                % (label_settings["font_size_extra_small"], round(total_weight, 2)),
                style_left,
            ),
            Paragraph(
                "<font size=%s>Total Cubic %s</font>"
                % (label_settings["font_size_extra_small"], round(total_cubic, 4)),
                style_left,
            ),
        ],
        [
            Paragraph(
                "<font size=%s>Office Use</font>"
                % (label_settings["font_size_extra_small"]),
                style_right,
            ),
            Paragraph(
                "<font size=%s>We are not COMMON CARRIERS. Insurance is not included unless otherwise stated.</font>"
                % (label_settings["font_size_extra_small"]),
                style_center,
            ),
            "",
        ],
        [
            "",
            Paragraph(
                "<font size=%s>Received in good order and condition.</font>"
                % (label_settings["font_size_extra_small"]),
                style_center,
            ),
            "",
        ],
    ]

    third_section = Table(
        tbl_data,
        colWidths=[
            width * 0.3,
            width * 0.4,
            width * 0.3,
        ],
        rowHeights=[8, 6, 15],
        style=[
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ("SPAN", (1, 1), (2, 1)),
            ("SPAN", (1, 2), (2, 2)),
        ],
    )    

    page_per_rows = 5
    page_count = int((len(lines) - 1) / page_per_rows) + 1

    for j in range(0, len(lines), page_per_rows):
        segment_lines = lines[j:j+page_per_rows]

        # -------------------- Second Section ------------------------

        tbl_data = [
            [
                Paragraph(
                    "<font size=%s>Reference</font>"
                    % (label_settings["font_size_extra_small"],),
                    style_left,
                ),
                Paragraph(
                    "<font size=%s>Quantity</font>"
                    % (label_settings["font_size_extra_small"],),
                    style_left,
                ),
                Paragraph(
                    "<font size=%s>Description</font>"
                    % (label_settings["font_size_extra_small"],),
                    style_left,
                ),
                Paragraph(
                    "<font size=%s>Weight</font>"
                    % (label_settings["font_size_extra_small"],),
                    style_left,
                ),
                Paragraph(
                    "<font size=%s>Length x Width x Height</font>"
                    % (label_settings["font_size_extra_small"],),
                    style_left,
                ),
                Paragraph(
                    "<font size=%s>Cubic</font>"
                    % (label_settings["font_size_extra_small"],),
                    style_left,
                ),
            ],
        ]
        tbl_data_row = []
        row_heights = [8]

        for line in segment_lines:
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
                    % (label_settings["font_size_extra_small"], line.e_qty),
                    style_left,
                ),
                Paragraph(
                    "<font size=%s>%s</font>"
                    % (label_settings["font_size_extra_small"], line.e_type_of_packaging),
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
                Paragraph(
                    "<font size=%s>%s x %s x %s</font>"
                    % (
                        label_settings["font_size_extra_small"],
                        get_meter(line.e_dimLength, line.e_dimUOM),
                        get_meter(line.e_dimWidth, line.e_dimUOM),
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
                            4,
                        ),
                    ),
                    style_left,
                ),
            ]
            tbl_data.append(tbl_data_row)
            row_heights.append(8)

        tbl_data.append(
            [
                "",
                "",
                "",
                "",
                "",
                "",
            ]
        )
        row_heights.append(5 * (page_per_rows - len(segment_lines)))
        second_section = Table(
            tbl_data,
            colWidths=[
                width * 0.2,
                width * 0.1,
                width * 0.3,
                width * 0.1,
                width * 0.2,
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
            ],
        )        

        # -------------------- Footer Section ------------------------

        footer = Table(
            [
                [
                    "",
                    Paragraph(
                        "<font size=%s>(Received Date/Time)</font>"
                        % (label_settings["font_size_extra_small"],),
                        style_left,
                    ),
                    Paragraph(
                        "<font size=%s>(Received Name)</font>"
                        % (label_settings["font_size_extra_small"],),
                        style_left,
                    ),
                    Paragraph(
                        "<font size=%s>(Received Signature)</font>"
                        % (label_settings["font_size_extra_small"],),
                        style_left,
                    ),
                ],
                [
                    Paragraph(
                        "<font size=%s>https://www.transvirtual.com</font>"
                        % (label_settings["font_size_slight_small"],),
                        style_left,
                    ),
                    "",
                    "",
                    Paragraph(
                        "<font size=%s>Page %s of %s</font>"
                        % (label_settings["font_size_extra_small"], (int(j / page_per_rows) + 1), page_count),
                        style_right,
                    ),
                ],
            ],
            colWidths=[width * 0.4, width * 0.2, width * 0.2, width * 0.2],
            rowHeights=[6, 6],
            style=[
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("LEFTPADDING", (0, 0), (0, -1), 2),
                ("LINEABOVE", (0, 1), (-1, 1), 0.5, colors.black),
                ("LINEABOVE", (1, 0), (-1, 0), 0.5, colors.black, None, (2, 2)),
            ],
        )

        # ------------------------- Body -----------------------------

        body = Table(
            [
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
                ("LINEABOVE", (0, 0), (-1, 0), 0.5, colors.black),
                ("LINEABOVE", (0, 1), (-1, 1), 0.5, colors.black),
                ("LINEABOVE", (0, 2), (-1, 2), 0.5, colors.black),
            ],
        )

        wrapper = Table(
            [[header], [body]],
            colWidths=[width],
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

        Story_consignment.append(Spacer(1, 2))

        # Proof Of Delivery Copy

        logger.info(
            f"#110 [DXT CONSIGNMENT] Started building Proof of Delivery copy... (Booking ID: {booking.b_bookingID_Visual})"
        )

        tbl_data = [
            [
                dxt_img,
                Paragraph(
                    "<font size=%s><b>RECEIVERS COPY</b></font>"
                    % (label_settings["font_size_slight_small"]),
                    style_center,
                ),
                Paragraph(
                    "<font size=%s><b>Standard</b></font>"
                    % (label_settings["font_size_extra_small"]),
                    style_right,
                ),
                Paragraph(
                    "<font size=%s><b>%s</b></font>"
                    % (
                        label_settings["font_size_extra_small"],
                        booking.b_dateBookedDate.strftime("%d/%m/%Y")
                        if booking.b_dateBookedDate
                        else "",
                    ),
                    style_right,
                ),
            ],
            [
                "",
                "",
                Code128(
                    barcode,
                    barHeight=6 * mm,
                    barWidth=0.5 if len(barcode) < 10 else 0.4,
                    humanReadable=False,
                ),
                "",
            ],
            [
                "",
                "",
                Paragraph(
                    "<font size=%s><b>%s</b></font>"
                    % (label_settings["font_size_slight_small"], v_FPBookingNumber),
                    style_center,
                ),
                "",
            ],
        ]

        header = Table(
            tbl_data,
            colWidths=[width * 0.4, width * 0.3, width * 0.15, width * 0.15],
            rowHeights=[6, 22, 6],
            style=[
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("VALIGN", (2, 1), (2, 1), "BOTTOM"),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("SPAN", (0, 0), (0, 2)),
                ("SPAN", (2, 1), (3, 1)),
                ("SPAN", (2, 2), (3, 2)),
                ("TOPPADDING", (0, 0), (-1, 0), 2),
                ("LINEABOVE", (0, 0), (-1, 0), 0.5, colors.black, None, (2, 2)),
            ],
        )

        wrapper = Table(
            [[header], [body]],
            colWidths=[width],
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

    doc_consignment.build(
        Story_consignment, onFirstPage=myFirstPage, onLaterPages=myLaterPages
    )

    # end writting data into pdf file
    file.close()
    logger.info(
        f"#119 [DXT CONSIGNMENT] Finished building label... (Booking ID: {booking.b_bookingID_Visual})"
    )
    return filepath, f"{filename}.pdf"