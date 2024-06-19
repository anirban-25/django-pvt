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

from api.models import Booking_lines
from api.helpers.cubic import get_cubic_meter
from api.operations.api_booking_confirmation_lines import index as api_bcl
from api.clients.operations.index import extract_product_code
from api.common.ratio import _get_dim_amount, _get_weight_amount
from api.fps.team_global_express import gen_sscc
from reportlab.platypus.flowables import KeepInFrame

logger = logging.getLogger(__name__)

styles = getSampleStyleSheet()
style_right = ParagraphStyle(name="right", parent=styles["Normal"], alignment=TA_RIGHT)
style_left = ParagraphStyle(
    name="left",
    parent=styles["Normal"],
    alignment=TA_LEFT,
    leading=8,
    spaceBefore=0,
)
style_left_bg = ParagraphStyle(
    name="left",
    parent=styles["Normal"],
    alignment=TA_LEFT,
    leading=20,
    spaceBefore=0,
)
style_center = ParagraphStyle(
    name="center",
    parent=styles["Normal"],
    alignment=TA_CENTER,
    leading=10,
)
style_center_bg = ParagraphStyle(
    name="right",
    parent=styles["Normal"],
    alignment=TA_CENTER,
    leading=16,
    backColor="#64a1fc",
)
style_uppercase = ParagraphStyle(
    name="uppercase",
    parent=styles["Normal"],
    alignment=TA_LEFT,
    leading=9,
    spaceBefore=0,
    spaceAfter=0,
    textTransform="uppercase",
)
style_back_black = ParagraphStyle(
    name="back_black",
    parent=styles["Normal"],
    alignment=TA_CENTER,
    leading=13,
    backColor="black",
)
style_back_black_big = ParagraphStyle(
    name="back_black",
    parent=styles["Normal"],
    alignment=TA_CENTER,
    leading=30,
    backColor="black",
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


def gen_barcode(booking):
    ai_1 = "421"
    iso_country_code = "036"  # AU
    # postcode = booking.de_To_Address_PostalCode.zfill(4)
    postcode = "2171"
    ai_2 = "90"
    service_code = "154"  # Road

    code = f"{ai_1}{iso_country_code}{postcode}{ai_2}{service_code}"
    text = f"({ai_1}) {iso_country_code}{postcode} ({ai_2}) {service_code}"
    return {"code": code, "text": text}


def _gen_sscc(booking, line, index):
    sscc = gen_sscc(booking, line, index)
    code = sscc
    text = f"({sscc[0:2]}){sscc[2:]}"
    return {"code": code, "text": text}


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
        f"#110 [CROSS DOCK LABEL] Started building label... (Booking ID: {booking.b_bookingID_Visual}, Lines: {lines})"
    )
    v_FPBookingNumber = pre_data["v_FPBookingNumber"]

    # start check if pdfs folder exists
    if not os.path.exists(filepath):
        os.makedirs(filepath)
    # end check if pdfs folder exists

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
    logger.info(f"#111 [CROSS DOCK LABEL] File full path: {filepath}/{filename}")
    # end pdf file name using naming convention

    if not lines:
        lines = Booking_lines.objects.filter(fk_booking_id=booking.pk_booking_id)

    # label_settings = get_label_settings( 146, 104 )[0]
    label_settings = {
        "font_family": "Arial",
        "font_size_extra_small": "4",
        "font_size_small": "8",
        "font_size_medium": "8.5",
        "font_size_extra_medium": "12.75",
        "font_size_large": "21",
        "font_size_extra_large": "28.34",
        "label_dimension_length": "102",
        "label_dimension_width": "153",
        "label_image_size_length": "102",
        "label_image_size_width": "153",
        "barcode_dimension_length": "80",
        "barcode_dimension_width": "35",
        "barcode_font_size": "18",
        "line_height_extra_small": "3",
        "line_height_small": "5",
        "line_height_medium": "6",
        "line_height_large": "8",
        "line_height_extra_large": "12",
        "margin_v": "0",
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

    fp_color_code = pre_data["color_code"] or "808080"

    style_center_bg = ParagraphStyle(
        name="right",
        parent=styles["Normal"],
        alignment=TA_CENTER,
        leading=16,
        backColor=f"#{fp_color_code}",
    )

    Story = []
    j = 1

    totalWeight = 0
    totalCubic = 0
    for booking_line in lines:
        totalWeight = totalWeight + booking_line.e_qty * booking_line.e_weightPerEach
        totalCubic = totalCubic + get_cubic_meter(
            booking_line.e_dimLength,
            booking_line.e_dimWidth,
            booking_line.e_dimHeight,
            booking_line.e_dimUOM,
        )

    if sscc:
        j = 1 + label_index

    for line in lines:
        for k in range(line.e_qty):
            if one_page_label and k > 0:
                continue

            Story.append(Spacer(1, 1))

            tbl_data = [
                [
                    Paragraph(
                        "<font size=%s>%s</font>"
                        % (
                            label_settings["font_size_medium"],
                            booking.puCompany[:18] if booking.puCompany else "",
                        ),
                        style_left,
                    ),
                    Paragraph(
                        "<font size=%s>CARRIER: %s</font>"
                        % (
                            label_settings["font_size_medium"],
                            booking.vx_freight_provider,
                        ),
                        style_left,
                    ),
                ]
            ]

            shell_table = Table(
                tbl_data,
                colWidths=(
                    float(label_settings["label_image_size_length"]) * 0.5 * mm,
                    float(label_settings["label_image_size_length"]) * 0.5 * mm,
                ),
                style=[
                    ("TOPPADDING", (0, 0), (-1, -1), 0),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                    ("VALIGN", (0, 0), (0, -1), "TOP"),
                ],
            )

            Story.append(shell_table)

            pu_address = Paragraph(
                "<font size=%s>%s<br/>%s</font>"
                % (
                    label_settings["font_size_medium"],
                    booking.pu_Address_Street_1,
                    f"{booking.pu_Address_Suburb}, {booking.pu_Address_State} {booking.pu_Address_PostalCode}",
                ),
                style_left,
            )

            if booking.pu_Address_street_2:
                pu_address = Paragraph(
                    "<font size=%s>%s<br/>%s<br/>%s</font>"
                    % (
                        label_settings["font_size_medium"],
                        booking.pu_Address_Street_1,
                        booking.pu_Address_street_2,
                        f"{booking.pu_Address_Suburb}, {booking.pu_Address_State} {booking.pu_Address_PostalCode}",
                    ),
                    style_left,
                )

            tbl_data = [
                [
                    KeepInFrame(
                        float(label_settings["label_image_size_length"]) * 0.5 * mm,
                        6 * mm,
                        [pu_address],
                    ),
                    Paragraph(
                        "<font size=%s>CON NO: %s</font>"
                        % (
                            label_settings["font_size_medium"],
                            v_FPBookingNumber,
                        ),
                        style_left,
                    ),
                ]
            ]

            shell_table = Table(
                tbl_data,
                colWidths=(
                    float(label_settings["label_image_size_length"]) * 0.5 * mm,
                    float(label_settings["label_image_size_length"]) * 0.5 * mm,
                ),
                style=[
                    ("TOPPADDING", (0, 0), (-1, -1), 0),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ],
            )

            Story.append(shell_table)
            Story.append(Spacer(5, 15))

            tbl_data = [
                [
                    Paragraph(
                        "<font size=%s>TO:</font>"
                        % (label_settings["font_size_medium"],),
                        style_left,
                    ),
                    Paragraph(
                        "<font size=%s>190</font>"
                        % (label_settings["font_size_extra_large"],),
                        style_left,
                    ),
                    Paragraph(
                        "<font size=%s>FOR:</font>"
                        % (label_settings["font_size_medium"],),
                        style_left,
                    ),
                    Paragraph(
                        "<font size=%s>154</font>"
                        % (label_settings["font_size_extra_large"],),
                        style_left,
                    ),
                ]
            ]

            shell_table = Table(
                tbl_data,
                colWidths=(
                    float(label_settings["label_image_size_length"]) * 0.2 * mm,
                    float(label_settings["label_image_size_length"]) * 0.3 * mm,
                    float(label_settings["label_image_size_length"]) * 0.2 * mm,
                    float(label_settings["label_image_size_length"]) * 0.3 * mm,
                ),
                style=[
                    ("TOPPADDING", (0, 0), (-1, -1), 0),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                    ("VALIGN", (0, 0), (0, -1), "TOP"),
                    ("ROWHEIGHT", (0, 0), (-1, -1), 50),
                ],
            )

            Story.append(shell_table)
            Story.append(Spacer(5, 25))

            tbl_data = [
                [
                    KeepInFrame(
                        float(label_settings["label_image_size_length"]) * 0.5 * mm,
                        15 * mm,
                        [
                            Paragraph(
                                "<font size=%s>%s<br/>%s<br/>%s<br/>%s</font>"
                                % (
                                    label_settings["font_size_medium"],
                                    "Woolworths Group Limited TA Big W - DC190",
                                    "40 Blackbird Close",
                                    "Hoxton Park, 2171 NSW",
                                    booking.pu_Address_Country,
                                    # booking.deToCompanyName,
                                    # booking.de_To_Address_Street_1,
                                    # f"{booking.de_To_Address_Suburb}, {booking.de_To_Address_State} {booking.de_To_Address_PostalCode}",
                                ),
                                style_left,
                            )
                        ],
                    ),
                    KeepInFrame(
                        float(label_settings["label_image_size_length"]) * 0.5 * mm,
                        15 * mm,
                        [
                            Paragraph(
                                "<font size=%s><b>%s</b><br/>%s<br/>%s</font>"
                                % (
                                    label_settings["font_size_medium"],
                                    "CAMPBELLTOWN STORE",
                                    "Gilchrist Rd",
                                    "Ambarvale NSW 2560",
                                ),
                                style_left,
                            )
                        ],
                    ),
                ]
            ]

            shell_table = Table(
                tbl_data,
                colWidths=(
                    float(label_settings["label_image_size_length"]) * 0.5 * mm,
                    float(label_settings["label_image_size_length"]) * 0.5 * mm,
                ),
                style=[
                    ("TOPPADDING", (0, 0), (-1, -1), 0),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ],
            )

            Story.append(shell_table)
            Story.append(Spacer(5, 20))

            tbl_data = [
                [
                    Paragraph(
                        "<font size=%s color='white'>AD</font>"
                        % (label_settings["font_size_extra_large"],),
                        style_back_black_big,
                    ),
                ],
                [
                    Paragraph(
                        "<font size=%s color='white'>88888</font>"
                        % (label_settings["font_size_medium"],),
                        style_back_black,
                    ),
                ],
            ]

            sub_tbl_data1 = Table(
                tbl_data,
                colWidths=(
                    float(label_settings["label_image_size_length"]) * 0.21 * mm,
                ),
                style=[
                    ("TOPPADDING", (0, 0), (-1, -1), 0),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                    ("VALIGN", (0, 0), (0, -1), "TOP"),
                ],
            )

            tbl_data = [
                [
                    Paragraph(
                        "<font size=%s>Purchase Order:</font>"
                        % (label_settings["font_size_medium"],),
                        style_left,
                    ),
                    Paragraph(
                        "<font size=%s>31232783</font>"
                        % (label_settings["font_size_large"],),
                        style_left_bg,
                    ),
                ]
            ]

            sub_sub_tbl_data2 = Table(
                tbl_data,
                colWidths=(
                    float(label_settings["label_image_size_length"]) * 0.27 * mm,
                    float(label_settings["label_image_size_length"]) * 0.49 * mm,
                ),
                style=[
                    ("TOPPADDING", (0, 0), (-1, -1), 0),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ],
            )

            sub_tbl_data2 = Table(
                [[sub_sub_tbl_data2]],
                colWidths=(
                    float(label_settings["label_image_size_length"]) * 0.76 * mm,
                ),
                style=[
                    ("TOPPADDING", (0, 0), (-1, -1), 0),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ],
            )

            shell_table = Table(
                [
                    [
                        sub_tbl_data1,
                        sub_tbl_data2,
                    ]
                ],
                colWidths=(
                    float(label_settings["label_image_size_length"]) * 0.24 * mm,
                    float(label_settings["label_image_size_length"]) * 0.76 * mm,
                ),
                style=[
                    ("TOPPADDING", (0, 0), (-1, -1), 0),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ],
            )

            Story.append(shell_table)
            # Story.append(Spacer(1, 10))

            barcode = gen_barcode(booking)

            tbl_data = [
                [
                    code128.Code128(
                        barcode["code"],
                        barHeight=float(label_settings["barcode_dimension_width"]) * mm,
                        barWidth=1.9,
                        humanReadable=False,
                    )
                ],
            ]

            barcode_table = Table(
                tbl_data,
                colWidths=((float(label_settings["barcode_dimension_length"])) * mm),
                style=[
                    ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                    ("VALIGN", (0, 0), (0, -1), "TOP"),
                    ("TOPPADDING", (0, 0), (-1, -1), 5),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                    ("LEFTPADDING", (0, 0), (0, -1), 0),
                    ("RIGHTPADDING", (0, 0), (0, -1), 0),
                ],
            )

            Story.append(barcode_table)

            Story.append(Spacer(1, 2))

            tbl_data = [
                [
                    Paragraph(
                        "<font size=%s>%s</font>"
                        % (
                            label_settings["font_size_small"],
                            barcode["text"],
                        ),
                        style_center,
                    )
                ],
            ]

            barcode_text = Table(
                tbl_data,
                colWidths=(float(label_settings["label_image_size_length"]) * mm),
                style=[
                    ("TOPPADDING", (0, 0), (-1, -1), 0),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                    ("LEFTPADDING", (0, 0), (-1, -1), 12),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 12),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ],
            )

            Story.append(barcode_text)

            Story.append(Spacer(1, 2))

            sscc = _gen_sscc(booking, line, k)

            tbl_data = [
                [
                    code128.Code128(
                        sscc["code"],
                        barHeight=float(label_settings["barcode_dimension_width"]) * mm,
                        barWidth=1.9,
                        humanReadable=False,
                    )
                ],
            ]

            barcode_table = Table(
                tbl_data,
                colWidths=((float(label_settings["barcode_dimension_length"])) * mm),
                style=[
                    ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                    ("VALIGN", (0, 0), (0, -1), "TOP"),
                    ("TOPPADDING", (0, 0), (-1, -1), 5),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                    ("LEFTPADDING", (0, 0), (0, -1), 0),
                    ("RIGHTPADDING", (0, 0), (0, -1), 0),
                ],
            )

            Story.append(barcode_table)

            Story.append(Spacer(1, 2))

            tbl_data = [
                [
                    Paragraph(
                        "<font size=%s>%s</font>"
                        % (
                            label_settings["font_size_small"],
                            sscc["text"],
                        ),
                        style_center,
                    )
                ],
            ]

            barcode_text = Table(
                tbl_data,
                colWidths=(float(label_settings["label_image_size_length"]) * mm),
                style=[
                    ("TOPPADDING", (0, 0), (-1, -1), 0),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                    ("LEFTPADDING", (0, 0), (-1, -1), 12),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 12),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ],
            )

            Story.append(barcode_text)

            Story.append(PageBreak())

            j += 1

    doc.build(Story, onFirstPage=myFirstPage, onLaterPages=myLaterPages)
    file.close()
    logger.info(
        f"#119 [CROSS DOCK LABEL] Finished building label... (Booking ID: {booking.b_bookingID_Visual})"
    )
    return filepath, filename
