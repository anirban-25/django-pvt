import os
import datetime
import logging
from reportlab.lib.enums import TA_JUSTIFY, TA_RIGHT, TA_CENTER, TA_LEFT
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
from reportlab.platypus.flowables import Image, Spacer, HRFlowable, PageBreak, Flowable
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.graphics.barcode import code39, code128, code93, qrencoder
from reportlab.graphics.barcode.qr import QrCodeWidget
from reportlab.graphics.shapes import Drawing, Rect
from reportlab.lib import colors
from reportlab.graphics.barcode import createBarcodeDrawing
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

from api.fp_apis.constants import FP_CREDENTIALS
from api.fp_apis.utils import _convert_UOM
from api.helpers.cubic import get_cubic_meter
from api.helpers.string import add_space
from api.helpers.line import is_carton, is_pallet
from api.operations.api_booking_confirmation_lines import index as api_bcl
from api.common.ratio import _get_dim_amount, _get_weight_amount
from reportlab.platypus.flowables import KeepInFrame

folder = os.path.dirname(__file__)

logger = logging.getLogger(__name__)

styles = getSampleStyleSheet()
style_sort_code_0 = ParagraphStyle(
    name="sort_code_0",
    parent=styles["Normal"],
    fontSize=25,
    leading=29,
    spaceBefore=0,
    textTransform="uppercase",
)

style_sort_code_1 = ParagraphStyle(
    name="sort_code_1",
    parent=styles["Normal"],
    leading=73,
    spaceBefore=0,
    textTransform="uppercase",
)

style_sort_code_2 = ParagraphStyle(
    name="sort_code_2",
    parent=styles["Normal"],
    leading=30,
    spaceBefore=0,
    textTransform="uppercase",
)

style_receiver_text = ParagraphStyle(
    name="sort_code_2",
    parent=styles["Normal"],
    leading=16,
    spaceBefore=0,
    textTransform="uppercase",
)

style_center = ParagraphStyle(
    name="center",
    parent=styles["Normal"],
    leading=16,
    spaceBefore=0,
    textTransform="uppercase",
    alignment=TA_CENTER,
)

style_receiver_text_lg = ParagraphStyle(
    name="sort_code_2",
    parent=styles["Normal"],
    leading=24,
    spaceBefore=0,
    textTransform="uppercase",
)

style_reference_text = ParagraphStyle(
    name="sort_code_2",
    parent=styles["Normal"],
    leading=8,
    spaceBefore=0,
)

style_indicator_text = ParagraphStyle(
    name="sort_code_2",
    parent=styles["Normal"],
    leading=10,
    spaceBefore=0,
    textTransform="uppercase",
)

style_peel_text_super_small = ParagraphStyle(
    name="sort_code_2",
    parent=styles["Normal"],
    leading=8,
    spaceBefore=2,
    textTransform="uppercase",
)

style_peel_text_small = ParagraphStyle(
    name="sort_code_2",
    parent=styles["Normal"],
    leading=10,
    spaceBefore=0,
    textTransform="uppercase",
)

style_desc_text = ParagraphStyle(
    name="sort_code_2",
    parent=styles["Normal"],
    leading=14,
    spaceBefore=0,
)

style_footer_text = ParagraphStyle(
    name="sort_code_2",
    parent=styles["Normal"],
    leading=10,
    spaceBefore=0,
    textTransform="uppercase",
)


def myFirstPage(canvas, doc):
    canvas.saveState()
    canvas.rotate(180)
    canvas.restoreState()


def myLaterPages(canvas, doc):
    canvas.saveState()
    canvas.rotate(90)
    canvas.restoreState()


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


def gen_barcode_item(booking, v_FPBookingNumber, item_no=1):
    consignment_num = v_FPBookingNumber
    item_index = str(item_no).zfill(3)
    post_code = str(booking.de_To_Address_PostalCode)
    item_barcode = f"{consignment_num}{item_index}{post_code}"
    return item_barcode


def gen_qrcode(booking, booking_line, lines, v_FPBookingNumber, line_index):
    barcode_identifier = "D2"
    sender_account_number = FP_CREDENTIALS["direct freight"][
        booking.b_client_name.lower()
    ]["live_0"]["accountCode"]
    site_indicator = "1"
    consignment_num = v_FPBookingNumber
    item_number = str(line_index).zfill(3)
    label_track_code = (
        f"{consignment_num}{item_number}{booking.de_To_Address_PostalCode}"
    )

    receiver_name = booking.deToCompanyName or booking.de_to_Contact_F_LName
    receiver_name = add_space(receiver_name, 20, head_or_tail="tail")

    receiver_address = booking.de_To_Address_Street_1
    if booking.de_To_Address_Street_2:
        receiver_address += f"%{booking.de_To_Address_Street_2}"
    receiver_address = add_space(receiver_address, 60, head_or_tail="tail")

    receiver_suburb = booking.de_To_Address_Suburb
    receiver_suburb = add_space(receiver_suburb, 20, head_or_tail="tail")

    receiver_state = booking.de_To_Address_State
    receiver_state = add_space(receiver_state, 3, head_or_tail="tail")

    receiver_postcode = booking.de_To_Address_PostalCode
    receiver_postcode = add_space(receiver_postcode, 4, head_or_tail="tail")

    receiver_service = ""
    if booking.opt_authority_to_leave:
        receiver_service = "ATL"
    receiver_service = add_space(receiver_service, 15, head_or_tail="tail")

    dg_flag = "N"
    reserved_space = "   "

    # Extract params from lines
    carton_count, pallet_count = 0, 0
    carton_total_kgs, pallet_total_kgs = 0, 0
    carton_total_cubic, pallet_total_cubic = 0, 0
    single_item_kgs, single_item_cubic, single_item_rate_type = 0, 0, "Item"
    for line in lines:
        weight = _convert_UOM(
            line.e_weightPerEach,
            line.e_weightUOM,
            "weight",
            "direct freight",
        )
        cubic = get_cubic_meter(
            line.e_dimLength,
            line.e_dimWidth,
            line.e_dimHeight,
            line.e_dimUOM,
            1,
        )

        if is_carton(line.e_type_of_packaging):
            carton_count += line.e_qty
            carton_total_kgs += int(weight) * line.e_qty
            carton_total_cubic += cubic * line.e_qty
        else:
            pallet_count += line.e_qty
            pallet_total_kgs += int(weight) * line.e_qty
            pallet_total_cubic += cubic * line.e_qty

    if carton_count:
        carton_count = f"{carton_count}"
        carton_count = add_space(carton_count, 4, head_or_tail="tail")
        carton_total_kgs = f"{carton_total_kgs}"
        carton_total_kgs = add_space(carton_total_kgs, 5, head_or_tail="tail")
        carton_total_cubic = f"{carton_total_cubic}"
        carton_total_cubic = add_space(carton_total_cubic, 6, head_or_tail="tail")
        pallet_count = add_space("", 3, head_or_tail="tail")
        pallet_total_kgs = add_space("", 5, head_or_tail="tail")
        pallet_total_cubic = add_space("", 6, head_or_tail="tail")
    else:
        carton_count = add_space("", 4, head_or_tail="tail")
        carton_total_kgs = add_space("", 5, head_or_tail="tail")
        carton_total_cubic = add_space("", 6, head_or_tail="tail")
        pallet_count = f"{pallet_count}"
        pallet_count = add_space(pallet_count, 3, head_or_tail="tail")
        pallet_total_kgs = f"{pallet_total_kgs}"
        pallet_total_kgs = add_space(pallet_total_kgs, 5, head_or_tail="tail")
        pallet_total_cubic = f"{pallet_total_cubic}"
        pallet_total_cubic = add_space(pallet_total_cubic, 6, head_or_tail="tail")

    # Extract params from current line
    weight = _convert_UOM(
        booking_line.e_weightPerEach,
        booking_line.e_weightUOM,
        "weight",
        "direct freight",
    )
    single_item_kgs = booking_line.e_qty
    single_item_kgs = add_space(single_item_kgs, 5, head_or_tail="tail")
    single_item_cubic = get_cubic_meter(
        booking_line.e_dimLength,
        booking_line.e_dimWidth,
        booking_line.e_dimHeight,
        booking_line.e_dimUOM,
        booking_line.e_qty,
    )
    single_item_cubic = add_space(single_item_cubic, 6, head_or_tail="tail")
    if not is_carton(booking_line.e_type_of_packaging):
        single_item_rate_type = "Pallet"
    single_item_rate_type = add_space(single_item_rate_type, 8, head_or_tail="tail")

    label_code = (
        f"{barcode_identifier}{sender_account_number}{site_indicator}{consignment_num}"
        + f"{label_track_code}{receiver_name}{receiver_address}{receiver_suburb}"
        + f"{receiver_state}{receiver_postcode}{receiver_service}{dg_flag}{reserved_space}"
    )
    label_code += f"{carton_count}{carton_total_kgs}{carton_total_cubic}"
    label_code += f"{pallet_count}{pallet_total_kgs}{pallet_total_cubic}"
    label_code += f"{single_item_kgs}{single_item_cubic}{single_item_rate_type}"

    return label_code


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
    # start check if pdfs folder exists
    if not os.path.exists(filepath):
        os.makedirs(filepath)
    # end check if pdfs folder exists

    logger.info(
        f"#110 [DIRECT FREIGHT LABEL] Started building label... (Booking ID: {booking.b_bookingID_Visual}, Lines: {lines})"
    )
    v_FPBookingNumber = pre_data["v_FPBookingNumber"]

    # start pdf file name using naming convention
    if lines:
        if sscc:
            filename = (
                booking.pu_Address_State
                + "_"
                + str(booking.b_bookingID_Visual)
                + "_"
                + str(sscc)
                + ".pdf"
            )
        else:
            filename = (
                booking.pu_Address_State
                + "_"
                + str(booking.b_bookingID_Visual)
                + "_"
                + str(lines[0].pk)
                + ".pdf"
            )
    else:
        filename = (
            booking.pu_Address_State
            + "_"
            + v_FPBookingNumber
            + "_"
            + str(booking.b_bookingID_Visual)
            + ".pdf"
        )

    file = open(f"{filepath}/{filename}", "w")
    logger.info(f"#111 [DIRECT FREIGHT LABEL] File full path: {filepath}/{filename}")
    # end pdf file name using naming convention

    label_settings = {
        "font_family": "Verdana",
        "font_size_extra_small": "6",
        "font_size_footer_units_small": "8",
        "font_size_footer_desc_small": "9",
        "font_size_footer_desc": "10",
        "font_size_footer_units": "12",
        "font_size_footer": "14",
        "font_size_small": "7",
        "font_size_medium": "14",
        "font_size_large": "20",
        "font_size_extra_large": "24",
        "font_size_sort_code_0": "25",
        "font_size_sort_code_2": "27",
        "font_size_sort_code_1": "60",
        "label_dimension_length": "102",
        "label_dimension_width": "200",
        "label_image_size_length": "96",
        "label_image_size_width": "100",
        "barcode_dimension_length": "85",
        "barcode_dimension_width": "30",
        "barcode_font_size": "18",
        "line_height_extra_small": "3",
        "line_height_small": "5",
        "line_height_medium": "6",
        "line_height_large": "8",
        "line_height_extra_large": "22",
        "margin_v": "2",
        "margin_h": "0",
    }

    width = float(label_settings["label_dimension_length"]) * mm
    height = float(label_settings["label_dimension_width"]) * mm
    doc = SimpleDocTemplate(
        f"{filepath}/{filename}",
        pagesize=(width, height),
        rightMargin=float(label_settings["margin_h"]) * mm,
        leftMargin=float(label_settings["margin_h"]) * mm,
        topMargin=float(label_settings["margin_v"]) * mm,
        bottomMargin=float(label_settings["margin_v"]) * mm,
    )
    df_logo = "./static/assets/logos/direct_freight.png"
    df_img = Image(df_logo, 30 * mm, 7 * mm)
    dme_logo = "./static/assets/logos/dme.png"
    dme_img = Image(dme_logo, 30 * mm, 7 * mm)

    width = float(label_settings["label_image_size_length"]) * mm
    row_height = float(label_settings["line_height_extra_large"]) * mm

    Story = []
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

    # ------------------------------------ Header Black Bar --------------------------------------
    hr = HRFlowable(
        width=width,
        thickness=6,
        lineCap="square",
        color=colors.black,
        spaceBefore=0,
        spaceAfter=0,
        hAlign="CENTER",
        vAlign="BOTTOM",
        dash=None,
    )

    Story.append(hr)
    Story.append(Spacer(1, 2))

    for booking_line in lines:
        for j_index in range(booking_line.e_qty):
            if one_page_label and j_index > 0:
                continue

            logger.info(f"#114 [DIRECT FREIGHT LABEL] Adding: {booking_line}")

            # ------------------------------------ Logo Section --------------------------------------

            Story.append(Spacer(1, 2))

            logo = Table(
                [[dme_img, df_img]],
                colWidths=[width * 0.5, width * 0.5],
                rowHeights=(8 * mm),
                style=[
                    ("VALIGN", (0, 0), (0, 0), "MIDDLE"),
                    ("ALIGN", (0, 0), (0, 0), "LEFT"),
                    ("ALIGN", (1, 0), (1, 0), "RIGHT"),
                ],
            )

            Story.append(logo)
            Story.append(Spacer(1, 1))

            hr = HRFlowable(
                width=width,
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
            Story.append(Spacer(1, 2))

            # ----------------------------------  QrCode Section ------------------------------------

            sort_bin_part = Table(
                [
                    [
                        VerticalParagraph(
                            "<font size=%s>%s</font>"
                            % (
                                label_settings["font_size_sort_code_0"],
                                pre_data["routing"].sort_bin,
                            ),
                            style_sort_code_0,
                        ),
                    ]
                ],
                colWidths=width * (0.8 / 5),
                rowHeights=row_height * 1.7,
                style=[
                    ("VALIGN", (0, 0), (0, 0), "MIDDLE"),
                    ("ALIGN", (0, 0), (0, 0), "RIGHT"),
                    ("LINEBELOW", (0, 0), (0, 0), 1, colors.black),
                ],
            )

            gateway_part = Table(
                [
                    [
                        KeepInFrame(
                            width * (1.7 / 5),
                            row_height,
                            [
                                Paragraph(
                                    "<font size=%s>%s</font>"
                                    % (
                                        label_settings["font_size_sort_code_1"],
                                        pre_data["routing"].gateway,
                                    ),
                                    style_sort_code_1,
                                )
                            ],
                        )
                    ]
                ],
                colWidths=width * (1.7 / 5),
                rowHeights=row_height,
                style=[
                    ("ALIGN", (0, 0), (0, 0), "RIGHT"),
                    ("TOPPADDING", (0, 0), (-1, -1), 0),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                    ("LEFTPADDING", (0, 0), (-1, -1), 0),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ],
            )

            onfwd_part = Table(
                [
                    [
                        Paragraph(
                            "<font size=%s>%s</font>"
                            % (
                                label_settings["font_size_sort_code_2"],
                                pre_data["routing"].onfwd,
                            ),
                            style_sort_code_2,
                        ),
                    ]
                ],
                colWidths=width * (1.7 / 5),
                rowHeights=row_height * (1.2 / 2),
                style=[
                    ("VALIGN", (0, 0), (0, 0), "TOP"),
                    ("ALIGN", (0, 0), (0, 0), "RIGHT"),
                    ("TOPPADDING", (0, 0), (-1, -1), 0),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                    ("LEFTPADDING", (0, 0), (-1, -1), 0),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                    ("LINEBELOW", (0, 0), (0, 0), 1, colors.black),
                ],
            )

            codeString = gen_qrcode(booking, booking_line, lines, v_FPBookingNumber, j)

            qrrr = QrCodeWidget(
                value=codeString,
                barWidth=35 * mm,
                barHeight=35 * mm,
                barFillColor=colors.black,
            )
            d = Drawing(36, 36)
            d.add(qrrr)

            qr_code_part = Table(
                [[d]],
                colWidths=width * (2.3 / 5),
                rowHeights=row_height * 1.7,
                style=[
                    ("VALIGN", (0, 0), (0, 0), "BOTTOM"),
                    ("ALIGN", (0, 0), (0, 0), "LEFT"),
                    ("TOPPADDING", (0, 0), (-1, -1), 0),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                    ("LEFTPADDING", (0, 0), (-1, -1), 0),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                    ("LINEBELOW", (0, 0), (0, 0), 1, colors.black),
                ],
            )

            qr_code_section = Table(
                [
                    ["", sort_bin_part, gateway_part, qr_code_part, ""],
                    ["", "", onfwd_part, "", ""],
                ],
                colWidths=[
                    width * (0.1 / 5),
                    width * (0.8 / 5),
                    width * (1.7 / 5),
                    width * (2.3 / 5),
                    width * (0.1 / 5),
                ],
                rowHeights=(
                    row_height,
                    row_height * 1.2 / 2,
                ),
                style=[
                    ("SPAN", (0, 0), (0, 1)),
                    ("SPAN", (1, 0), (1, 1)),
                    ("SPAN", (3, 0), (3, 1)),
                    ("ALIGN", (1, 0), (1, 1), "RIGHT"),
                    ("TOPPADDING", (0, 0), (-1, -1), 0),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                    ("LEFTPADDING", (0, 0), (-1, -1), 0),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ],
            )

            Story.append(qr_code_section)
            Story.append(Spacer(1, 2))

            # ----------------------------------  Delivery Section ---------------------------------

            receiver_name = ""
            if booking.de_to_Contact_F_LName == "":
                receiver_name = booking.deToCompanyName
            else:
                receiver_name = booking.de_to_Contact_F_LName

            receiver_name_part = Table(
                [
                    [
                        Paragraph(
                            "<font size=%s>%s</font>"
                            % (label_settings["font_size_medium"], receiver_name[:24]),
                            style_receiver_text,
                        ),
                    ]
                ],
                colWidths=width * (4.8 / 5),
                style=[
                    ("ALIGN", (0, 0), (0, 0), "RIGHT"),
                    ("TOPPADDING", (0, 0), (-1, -1), 0),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                    ("LEFTPADDING", (0, 0), (-1, -1), 0),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ],
            )

            address1_part = Table(
                [
                    [
                        Paragraph(
                            "<font size=%s>%s</font>"
                            % (
                                label_settings["font_size_medium"],
                                booking.de_To_Address_Street_1[:22],
                            ),
                            style_receiver_text,
                        ),
                    ]
                ],
                colWidths=width * (4.8 / 5),
                style=[
                    ("ALIGN", (0, 0), (0, 0), "RIGHT"),
                    ("TOPPADDING", (0, 0), (-1, -1), 0),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                    ("LEFTPADDING", (0, 0), (-1, -1), 0),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ],
            )

            address2_part = Table(
                [
                    [
                        Paragraph(
                            "<font size=%s>%s</font>"
                            % (
                                label_settings["font_size_medium"],
                                booking.de_To_Address_Street_2[:24],
                            ),
                            style_receiver_text,
                        ),
                    ]
                ],
                colWidths=width * (4.8 / 5),
                style=[
                    ("ALIGN", (0, 0), (0, 0), "RIGHT"),
                    ("TOPPADDING", (0, 0), (-1, -1), 0),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                    ("LEFTPADDING", (0, 0), (-1, -1), 0),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ],
            )

            suburb_part = Table(
                [
                    [
                        Paragraph(
                            "<font size=%s>%s</font>"
                            % (
                                label_settings[
                                    "font_size_footer_desc"
                                    if len(booking.de_To_Address_Suburb) > 18
                                    else "font_size_footer_units"
                                    if len(booking.de_To_Address_Suburb) > 10
                                    else "font_size_large"
                                ],
                                booking.de_To_Address_Suburb[:20],
                            ),
                            style_receiver_text_lg,
                        ),
                    ]
                ],
                colWidths=width * (2.8 / 5),
                style=[
                    ("ALIGN", (0, 0), (0, 0), "RIGHT"),
                    ("TOPPADDING", (0, 0), (-1, -1), 0),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                    ("LEFTPADDING", (0, 0), (-1, -1), 0),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                    ("LINEBELOW", (0, 0), (0, 0), 1, colors.black),
                ],
            )

            state_part = Table(
                [
                    [
                        Paragraph(
                            "<font size=%s>%s %s</font>"
                            % (
                                label_settings["font_size_large"],
                                booking.de_To_Address_State,
                                booking.de_To_Address_PostalCode,
                            ),
                            style_receiver_text_lg,
                        ),
                    ]
                ],
                colWidths=width * (2 / 5),
                style=[
                    ("ALIGN", (0, 0), (0, 0), "LEFT"),
                    ("TOPPADDING", (0, 0), (-1, -1), 0),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                    ("LEFTPADDING", (0, 0), (-1, -1), 0),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                    ("LINEBELOW", (0, 0), (0, 0), 1, colors.black),
                ],
            )

            if len(booking.de_To_Address_Street_2) > 0:
                tbl_data = [
                    ["", receiver_name_part, "", ""],
                    ["", address1_part, "", ""],
                    ["", address2_part, "", ""],
                    ["", suburb_part, state_part, ""],
                ]
                styles = [
                    ("SPAN", (0, 0), (0, -1)),
                    ("SPAN", (1, 0), (2, 0)),
                    ("SPAN", (1, 1), (2, 1)),
                    ("SPAN", (1, 2), (2, 2)),
                    ("TOPPADDING", (0, 0), (-1, -1), 0),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                    ("LEFTPADDING", (0, 0), (-1, -1), 0),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ]
            else:
                tbl_data = [
                    ["", receiver_name_part, "", ""],
                    ["", address1_part, "", ""],
                    ["", suburb_part, state_part, ""],
                ]
                styles = [
                    ("SPAN", (0, 0), (0, -1)),
                    ("SPAN", (1, 0), (2, 0)),
                    ("SPAN", (1, 1), (2, 1)),
                    ("TOPPADDING", (0, 0), (-1, -1), 0),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                    ("LEFTPADDING", (0, 0), (-1, -1), 0),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ]

            delivery_section = Table(
                tbl_data,
                colWidths=[
                    width * (0.1 / 5),
                    width * (2.8 / 5),
                    width * (2 / 5),
                    width * (0.1 / 5),
                ],
                style=styles,
            )

            Story.append(delivery_section)
            Story.append(Spacer(1, 6))

            # ----------------------------------  Ref Section ------------------------------------

            ref_part = Table(
                [
                    [
                        "",
                        Paragraph(
                            "<font size=%s>REF: %s</font>"
                            % (
                                label_settings["font_size_extra_small"],
                                booking.b_clientReference_RA_Numbers,
                            ),
                            style_reference_text,
                        ),
                        Paragraph(
                            "<font size=%s><b>ITEM: %s of %s</b></font>"
                            % (label_settings["font_size_extra_small"], j, totalQty),
                            style_reference_text,
                        ),
                        "",
                    ]
                ],
                colWidths=[
                    width * (0.1 / 5),
                    width * (2.8 / 5),
                    width * (2 / 5),
                    width * (0.1 / 5),
                ],
                style=[
                    ("TOPPADDING", (0, 0), (-1, -1), 0),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                    ("LEFTPADDING", (0, 0), (-1, -1), 0),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ],
            )

            Story.append(ref_part)
            Story.append(Spacer(1, 6))

            not_before_part = Table(
                [
                    [
                        "",
                        Paragraph(
                            "<font size=%s>Not Before: %s</font>"
                            % (
                                label_settings["font_size_extra_small"],
                                booking.puPickUpAvailFrom_Date,
                            ),
                            style_reference_text,
                        ),
                        Paragraph(
                            "<font size=%s>Not After: %s</font>"
                            % (
                                label_settings["font_size_extra_small"],
                                booking.pu_PickUp_By_Date,
                            ),
                            style_reference_text,
                        ),
                        "",
                    ]
                ],
                colWidths=[
                    width * (0.1 / 5),
                    width * (1.8 / 5),
                    width * (3 / 5),
                    width * (0.1 / 5),
                ],
                style=[
                    ("TOPPADDING", (0, 0), (-1, -1), 0),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                    ("LEFTPADDING", (0, 0), (-1, -1), 0),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ],
            )

            Story.append(not_before_part)
            Story.append(Spacer(1, 5))

            authority_part = Table(
                [
                    [
                        "",
                        "",  # Paragraph("Authority to leave", style_indicator_text),
                        "",
                        "",  # Paragraph("DG", style_indicator_text),
                        "",
                    ]
                ],
                colWidths=[
                    width * (0.1 / 5),
                    width * (1.8 / 5),
                    width * (2 / 5),
                    width * (1 / 5),
                    width * (0.1 / 5),
                ],
                rowHeights=(8 * mm),
                style=[
                    ("TOPPADDING", (0, 0), (-1, -1), 0),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                    ("LEFTPADDING", (0, 0), (-1, -1), 0),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                    ("GRID", (1, 0), (1, 0), 1, colors.black),
                    ("GRID", (3, 0), (3, 0), 1, colors.black),
                ],
            )

            Story.append(authority_part)
            Story.append(Spacer(1, 10))

            special_instructions_header = Table(
                [
                    [
                        "",
                        Paragraph(
                            "<font size=%s>Special Instructions: </font>"
                            % label_settings["font_size_extra_small"],
                            style_peel_text_super_small,
                        ),
                        "",
                    ]
                ],
                colWidths=[
                    width * (0.1 / 5),
                    width * (4.8 / 5),
                    width * (0.1 / 5),
                ],
                rowHeights=(3 * mm),
                style=[
                    ("TOPPADDING", (0, 0), (-1, -1), 0),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                    ("LEFTPADDING", (0, 0), (-1, -1), 0),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ],
            )

            Story.append(special_instructions_header)

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

            special_instructions_body = Table(
                [
                    [
                        "",
                        Paragraph(
                            "<font size=%s>%s</font>"
                            % (
                                label_settings["font_size_small"],
                                specialInstructions,
                            ),
                            style_peel_text_small,
                        ),
                        "",
                    ]
                ],
                colWidths=[
                    width * (0.1 / 5),
                    width * (4.8 / 5),
                    width * (0.1 / 5),
                ],
                rowHeights=(3 * mm),
                style=[
                    ("TOPPADDING", (0, 0), (-1, -1), 0),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                    ("LEFTPADDING", (0, 0), (-1, -1), 0),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ],
            )

            if specialInstructions:
                Story.append(special_instructions_body)

            Story.append(Spacer(1, 5))

            # ----------------------------------  Connote Section -------------------------------

            receiver_name = ""
            if booking.de_to_Contact_F_LName == "":
                receiver_name = booking.deToCompanyName
            else:
                receiver_name = booking.de_to_Contact_F_LName

            # Weight in KG
            weight_ratio = _get_weight_amount(booking_line.e_weightUOM)
            weight = weight_ratio * booking_line.e_weightPerEach

            cubic = round(
                get_cubic_meter(
                    booking_line.e_dimLength,
                    booking_line.e_dimWidth,
                    booking_line.e_dimHeight,
                    booking_line.e_dimUOM,
                ),
                3,
            )

            if booking.de_To_Address_Street_2 == "":
                paragraph_line1 = Paragraph(
                    "<font size=%s><b>&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;%s&nbsp;&nbsp;%s&nbsp;&nbsp;%s</b></font>"
                    % (
                        label_settings["font_size_small"],
                        booking.de_To_Address_Suburb,
                        booking.de_To_Address_State,
                        booking.de_To_Address_PostalCode,
                    ),
                    style_peel_text_small,
                )
                paragraph_line2 = Paragraph(
                    "<font size=%s><b>From: %s</b></font>"
                    % (
                        label_settings["font_size_small"],
                        booking.puCompany[:20],
                    ),
                    style_peel_text_small,
                )
                paragraph_line3 = ""
            else:
                paragraph_line1 = Paragraph(
                    "<font size=%s><b>&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;%s</b></font>"
                    % (
                        label_settings["font_size_small"],
                        booking.de_To_Address_Street_2[:22],
                    ),
                    style_peel_text_small,
                )
                paragraph_line2 = Paragraph(
                    "<font size=%s><b>&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;%s&nbsp;&nbsp;%s&nbsp;&nbsp;%s</b></font>"
                    % (
                        label_settings["font_size_small"],
                        booking.de_To_Address_Suburb,
                        booking.de_To_Address_State,
                        booking.de_To_Address_PostalCode,
                    ),
                    style_peel_text_small,
                )
                paragraph_line3 = Paragraph(
                    "<font size=%s><b>From: %s</b></font>"
                    % (
                        label_settings["font_size_small"],
                        booking.puCompany[:20],
                    ),
                    style_peel_text_small,
                )

            connote_section = Table(
                [
                    [
                        "",
                        Paragraph(
                            "<font size=%s>C/NOTE: %s</font>"
                            % (label_settings["font_size_small"], v_FPBookingNumber),
                            style_peel_text_small,
                        ),
                        Paragraph(
                            "<font size=%s><b>Date: %s</b></font>"
                            % (
                                label_settings["font_size_extra_small"],
                                booking.puPickUpAvailFrom_Date,
                            ),
                            style_peel_text_super_small,
                        ),
                        "",
                    ],
                    [
                        "",
                        Paragraph(
                            "<font size=%s><b>TO: %s</b></font>"
                            % (label_settings["font_size_small"], receiver_name[:22]),
                            style_peel_text_small,
                        ),
                        Paragraph(
                            "<font size=%s><b>QTY: %s</b></font>"
                            % (label_settings["font_size_extra_small"], "1"),
                            style_peel_text_super_small,
                        ),
                        "",
                    ],
                    [
                        "",
                        Paragraph(
                            "<font size=%s><b>&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;%s</b></font>"
                            % (
                                label_settings["font_size_small"],
                                booking.de_To_Address_Street_1[:22],
                            ),
                            style_peel_text_small,
                        ),
                        Paragraph(
                            "<font size=%s><b>Kgs: %s</b></font>"
                            % (
                                label_settings["font_size_extra_small"],
                                round(weight, 3),
                            ),
                            style_peel_text_super_small,
                        ),
                        "",
                    ],
                    [
                        "",
                        paragraph_line1,
                        Paragraph(
                            "<font size=%s><b>DIM: %s %s %s</b></font>"
                            % (
                                label_settings["font_size_extra_small"],
                                round(float(booking_line.e_dimWidth), 2),
                                round(float(booking_line.e_dimHeight), 2),
                                round(float(booking_line.e_dimLength), 2),
                            ),
                            style_peel_text_super_small,
                        ),
                        "",
                    ],
                    [
                        "",
                        paragraph_line2,
                        Paragraph(
                            "<font size=%s><b>M3: %s</b></font>"
                            % (label_settings["font_size_extra_small"], cubic),
                            style_peel_text_super_small,
                        ),
                        "",
                    ],
                    [
                        "",
                        paragraph_line3,
                        Paragraph(
                            "<font size=%s><b>Item: %s</b></font>"
                            % (
                                label_settings["font_size_extra_small"],
                                booking_line.e_item[:20],
                            ),
                            style_peel_text_super_small,
                        ),
                        "",
                    ],
                ],
                colWidths=[
                    width * (0.1 / 5),
                    width * (2.9 / 5),
                    width * (1.9 / 5),
                    width * (0.1 / 5),
                ],
                rowHeights=[
                    4 * mm,
                    3 * mm,
                    3 * mm,
                    3 * mm,
                    3 * mm,
                    3 * mm,
                ],
                style=[
                    ("SPAN", (2, 3), (3, 3)),
                    ("SPAN", (2, 4), (3, 4)),
                    ("SPAN", (2, 5), (3, 5)),
                    ("TOPPADDING", (0, 0), (-1, -1), 0),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                    ("LEFTPADDING", (0, 0), (-1, -1), 0),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                    ("LINEABOVE", (1, 0), (2, 0), 1, colors.black),
                    ("LINEBELOW", (1, -1), (2, -1), 1, colors.black),
                    ("TOPPADDING", (0, 0), (-1, 0), 2),
                ],
            )

            Story.append(connote_section)

            # ----------------------------------  Barcode Section -------------------------------

            barcode = gen_barcode_item(booking, v_FPBookingNumber, j)

            received_good_part = Table(
                [
                    [
                        "",
                        Paragraph(
                            "<font size=%s>Received Good Order</font>"
                            % label_settings["font_size_extra_small"],
                            style_peel_text_super_small,
                        ),
                        "",
                        "",
                    ],
                    [
                        "",
                        Paragraph(
                            "<font size=%s>Signed: _____________________________________________________________</font>"
                            % label_settings["font_size_extra_small"],
                            style_peel_text_super_small,
                        ),
                        "",
                        "",
                    ],
                    [
                        "",
                        Paragraph(
                            "<font size=%s>Print Name: _____________________________</font>"
                            % label_settings["font_size_extra_small"],
                            style_peel_text_super_small,
                        ),
                        Paragraph(
                            "<font size=%s>Date: _____/_____/_____</font>"
                            % label_settings["font_size_extra_small"],
                            style_peel_text_super_small,
                        ),
                        "",
                    ],
                ],
                colWidths=[
                    width * (0.1 / 5),
                    width * (2.9 / 5),
                    width * (1.9 / 5),
                    width * (0.1 / 5),
                ],
                rowHeights=(4 * mm),
                style=[
                    ("SPAN", (1, 0), (2, 0)),
                    ("SPAN", (1, 1), (2, 1)),
                    ("TOPPADDING", (0, 0), (-1, -1), 0),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                    ("LEFTPADDING", (0, 0), (-1, -1), 0),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ],
            )

            Story.append(received_good_part)

            barcode_part = Table(
                [
                    [
                        "",
                        code128.Code128(
                            barcode,
                            barHeight=28 * mm,
                            barWidth=1.23,
                            humanReadable=False,
                        ),
                        "",
                    ],
                ],
                colWidths=[
                    width * (0.1 / 5),
                    width * (4.8 / 5),
                    width * (0.1 / 5),
                ],
                rowHeights=(30 * mm),
                style=[
                    ("TOPPADDING", (0, 0), (-1, -1), 0),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                    ("LEFTPADDING", (0, 0), (-1, -1), 0),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                    ("ALIGN", (1, 0), (1, 0), "CENTER"),
                ],
            )

            Story.append(barcode_part)

            barcode_text_part = Table(
                [
                    [
                        "",
                        Paragraph(
                            "<font size=%s>%s</font>"
                            % (label_settings["font_size_medium"], barcode),
                            style_center,
                        ),
                        "",
                    ],
                ],
                colWidths=[
                    width * (0.1 / 5),
                    width * (4.8 / 5),
                    width * (0.1 / 5),
                ],
                rowHeights=(6 * mm),
                style=[
                    ("TOPPADDING", (0, 0), (-1, -1), 0),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                    ("LEFTPADDING", (0, 0), (-1, -1), 0),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                    ("ALIGN", (0, 0), (0, 0), "CENTER"),
                ],
            )

            Story.append(barcode_text_part)

            # ----------------------------------  Footer Section -------------------------------

            footer_part_width = (
                float(label_settings["label_image_size_length"]) * (1 / 2) * mm
            )
            pkg_units_font_size = "font_size_footer"
            if len(booking_line.e_type_of_packaging) < 7:
                pkg_units_font_size = "font_size_footer"
            elif len(booking_line.e_type_of_packaging) <= 10:
                pkg_units_font_size = "font_size_footer_desc"
            else:
                pkg_units_font_size = "font_size_footer_units_small"

            if is_carton(booking_line.e_type_of_packaging):
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
                                        booking_line.e_type_of_packaging,
                                    ),
                                    style_footer_text,
                                ),
                            ],
                        ],
                    ],
                    colWidths=[
                        footer_part_width * (3 / 7),
                        footer_part_width * (3 / 7 + 0.03),
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
            else:
                packet_img = Image("./static/assets/logos/packet.png", 5 * mm, 5 * mm)
                footer_units_part = Table(
                    [
                        [
                            Paragraph(
                                "<font size=%s>PKG UNITS:</font>"
                                % (label_settings["font_size_footer_desc"],),
                                style_reference_text,
                            ),
                            packet_img,
                            [
                                Paragraph(
                                    "<font size=%s><b>%s</b></font>"
                                    % (
                                        label_settings[pkg_units_font_size],
                                        booking_line.e_type_of_packaging,
                                    ),
                                    style_footer_text,
                                ),
                            ],
                        ],
                    ],
                    colWidths=[
                        footer_part_width * (3 / 7),
                        footer_part_width * (1 / 7 - 0.03),
                        footer_part_width * (3 / 7 + 0.03),
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
                                if booking_line.e_bin_number is None
                                or len(booking_line.e_bin_number) == 0
                                else booking_line.e_bin_number[:25],
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

            str_desc = booking_line.e_item.replace("\n", " ").replace("\t", " ")[:80]
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

            footer_section = Table(
                [
                    ["", footer_part, ""],
                ],
                colWidths=[
                    width * (0.1 / 5),
                    width * (4.8 / 5),
                    width * (0.1 / 5),
                ],
                style=[
                    ("TOPPADDING", (0, 0), (-1, -1), 0),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                    ("LEFTPADDING", (0, 0), (-1, -1), 0),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ],
            )

            Story.append(footer_section)

            Story.append(PageBreak())

            j += 1

    doc.build(Story, onFirstPage=myFirstPage, onLaterPages=myLaterPages)

    file.close()
    logger.info(
        f"#119 [DIRECT FREIGHT LABEL] Finished building label... (Booking ID: {booking.b_bookingID_Visual})"
    )
    return filepath, filename


#################
#   Test Usage  #
#################

# class Booking:
#     def __init__(self):
#         self.vx_freight_provider = 'Direct Freight'
#         self.b_bookingID_Visual = 290000
#         self.v_FPBookingNumber = 'XX393948'
#         self.b_client_order_num = 'S3848'
#         self.b_dateBookedDate = "2023-05-08"
#         self.b_client_name = 'JasonL'
#         self.pu_Contact_F_L_Name = 'John'
#         self.pu_Address_Street_1 = 'AAA AAA AAA'
#         self.pu_Address_street_2 = 'BBB BBB BBB'
#         self.pu_Address_Suburb = 'Botany'
#         self.pu_Address_PostalCode = '2019'
#         self.pu_Address_State = 'NSW'
#         self.pu_Address_Country = 'AU'
#         self.de_to_Contact_F_LName = 'Pete'
#         self.de_To_Address_Street_1 = 'CCC CCC CCC'
#         self.de_To_Address_Street_2 = 'DDD DDD DDD'
#         self.de_To_Address_Suburb = 'Melbourn'
#         self.de_To_Address_State = 'MEL'
#         self.de_To_Address_Country = 'AU'
#         self.de_To_Address_PostalCode = '3000'
#         self.de_to_Phone_Main = '1020020203'
#         self.pu_Phone_Main = '1020020203'
#         self.puCompany = "Direct Freight"
#         self.deToCompanyName = "GOLD"
#         self.de_To_Service = 'ATL%TBA'
#         self.sort_codes = ["B212", "20", "134"]
#         if (self.de_to_Contact_F_LName == ''):
#             self.receiver_name = self.deToCompanyName
#         else:
#             self.receiver_name = self.de_to_Contact_F_LName

#         if len(self.receiver_name) < 20:
#             self.receiver_name += " " * (20 - len(self.receiver_name))

#         self.receiver_address_1 = self.de_To_Address_Street_1
#         self.receiver_address_2 = self.de_To_Address_Street_2

#         if len(self.receiver_address_1 + '%' + self.receiver_address_2) < 60:
#             self.receiver_address_2 += " " * (60 - len(self.receiver_address_1 + '%' + self.receiver_address_2))

#         self.receiver_suburb = self.de_To_Address_Suburb
#         if len(self.receiver_suburb) < 20:
#             self.receiver_suburb += " " * (20 - len(self.receiver_suburb))

#         if len(self.de_To_Service) < 15:
#             self.de_To_Service += " " * (15 - len(self.de_To_Service))

#         self.receiver_state = self.de_To_Address_State
#         self.receiver_postcode = self.de_To_Address_PostalCode
#         self.customer_reference = 'XXXXXXXXXX'
#         self.total_item = '   3'
#         self.total_kg = '  500'
#         self.not_before_date = '01/07/2015'
#         self.not_after_date = '30/08/2015'
#         self.special_instruction = 'xxxxxxxxxxx xxxxxxxxxxx xxxxxxxxxxx xxxxxx'
#         self.consignment_number = f'{self.b_client_order_num}00000002'
#         self.consignment_d_date = "30/03/2015"
#         self.consignment_dimention = "50 50 50"
#         self.total_cubic = "1.4640"
#         self.sender_detail = "ABC company limited"
#         self.label_track_code = f'{self.consignment_number}123{self.de_To_Address_PostalCode}'

#         if len(self.label_track_code) < 20:
#             self.label_track_code += " " * (20 - len(self.label_track_code))

#         self.dg_flag = 'Y'
#         self.reserved = "   "
#         self.total_pallet = '2.3'
#         self.total_kg_pallet = '12345'
#         self.total_cubic_pallet = '123456'
#         self.single_item = '4.522'
#         self.single_item_cubic = '3.5112'
#         self.single_item_rate = 'Pallet  '

# if __name__ == '__main__':
#     booking = Booking()
#     build_label(booking, folder+"/pdfs")
