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

from api.models import Booking_lines, FPRouting, Fp_freight_providers
from api.helpers.cubic import get_cubic_meter
from api.fp_apis.utils import gen_consignment_num
from api.operations.api_booking_confirmation_lines import index as api_bcl

logger = logging.getLogger(__name__)

styles = getSampleStyleSheet()
style_right = ParagraphStyle(name="right", parent=styles["Normal"], alignment=TA_RIGHT)
style_left = ParagraphStyle(
    name="left",
    parent=styles["Normal"],
    alignment=TA_LEFT,
    leading=10,
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
    leading=20,
)
style_uppercase_big = ParagraphStyle(
    name="uppercase",
    parent=styles["Normal"],
    alignment=TA_LEFT,
    leading=12,
    spaceBefore=0,
    spaceAfter=0,
    textTransform="uppercase",
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
    label_code = f"{v_FPBookingNumber}-{item_index}"
    api_bcl.create(booking, [{"label_code": label_code}])
    return label_code


def gen_itm(booking, booking_lines, line_index, sscc_cnt):
    TT = 11
    CCCCCC = "132214"  # DME
    item_index = str(line_index).zfill(3)
    label_code = f"{TT}{CCCCCC}{str(booking.b_bookingID_Visual).zfill(9)}{item_index}"
    return label_code


def build_label(
    booking, filepath, lines, label_index, sscc, sscc_cnt=1, one_page_label=True
):
    logger.info(
        f"#110 [SMALL LABEL] Started building label... (Booking ID: {booking.b_bookingID_Visual}, Lines: {lines})"
    )
    v_FPBookingNumber = booking.v_FPBookingNumber

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
            + "-small.pdf"
        )

    file = open(f"{filepath}/{filename}", "w")
    logger.info(f"#111 [TNT LABEL] File full path: {filepath}/{filename}")
    # end pdf file name using naming convention

    if not lines:
        lines = Booking_lines.objects.filter(fk_booking_id=booking.pk_booking_id)

    # label_settings = get_label_settings( 146, 104 )[0]
    label_settings = {
        "font_family": "Verdana",
        "font_size_extra_small": "4",
        "font_size_small": "6",
        "font_size_normal": "7",
        "font_size_medium": "8",
        "font_size_large": "10",
        "font_size_extra_large": "13",
        "label_dimension_length": "100",
        "label_dimension_width": "150",
        "label_image_size_length": "85",
        "label_image_size_width": "130",
        "barcode_dimension_height": "33",
        "barcode_dimension_width": "0.75",
        "barcode_font_size": "18",
        "line_height_extra_small": "3",
        "line_height_small": "5",
        "line_height_medium": "6",
        "line_height_large": "8",
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
    fp_id = Fp_freight_providers.objects.get(
        fp_company_name=booking.vx_freight_provider
    ).id
    if fp_id == 8:
        fp_logo = "./static/assets/logos/cameron.png"
        fp_img = Image(fp_logo, 30 * mm, 7.7 * mm)
    elif fp_id == 9:
        fp_logo = "./static/assets/logos/northline.png"
        fp_img = Image(fp_logo, 30 * mm, 7.7 * mm)
    elif fp_id == 12:
        fp_logo = "./static/assets/logos/tnt_fedex_logo.png"
        fp_img = Image(fp_logo, 30 * mm, 6.6 * mm)
    elif fp_id == 2:
        fp_logo = "./static/assets/logos/allied.png"
        fp_img = Image(fp_logo, 30 * mm, 7.7 * mm)
    elif fp_id == 3:
        fp_logo = "./static/assets/logos/startrack.png"
        fp_img = Image(fp_logo, 30 * mm, 7.7 * mm)
    else:
        fp_img = None

    dme_logo = "./static/assets/logos/dme.png"
    dme_img = Image(dme_logo, 30 * mm, 7.7 * mm)

    Story = []
    j = 1

    totalQty = 0
    if one_page_label:
        lines = [lines[0]]
        totalQty = 1
    else:
        for booking_line in lines:
            totalQty = totalQty + booking_line.e_qty

    e_Total_KG_weight = 0
    for booking_line in lines:
        e_Total_KG_weight += booking_line.e_weightPerEach * booking_line.e_qty

    if sscc:
        j = 1 + label_index
        totalQty = sscc_cnt

    for booking_line in lines:
        for j_index in range(booking_line.e_qty):
            if one_page_label and j_index > 0:
                continue

            logger.info(f"#114 [TNT LABEL] Adding: {booking_line}")
            tbl_data1 = [
                [
                    Paragraph(
                        "<p style='vertical-align: top; padding: 0px; line-height: 0px'><font size=%s><b> %s </b></font></p>"
                        % (38, booking.de_To_Address_PostalCode or ""),
                        style_left,
                    ),
                    "",
                ],
            ]
            t1 = Table(
                tbl_data1,
                colWidths=(
                    85,
                    float(label_settings["label_image_size_length"]) * mm - 85,
                ),
                rowHeights=(float(label_settings["line_height_small"]) * mm),
                style=[
                    ("TOPPADDING", (0, 0), (-1, -1), 0),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                    ("LEFTPADDING", (0, 0), (-1, -1), 0),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ],
            )

            data = [[t1]]

            t_w = float(label_settings["label_image_size_length"]) * mm

            shell_table = Table(
                data,
                colWidths=[t_w],
                style=[
                    ("TOPPADDING", (0, 0), (-1, -1), 0),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                    ("LEFTPADDING", (0, 0), (-1, -1), 0),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ],
            )

            Story.append(shell_table)

            tbl_data1 = [
                [
                    Paragraph("<font size=%s>%s</font>" % (13, ""), style_left),
                    Paragraph(
                        "<font size=%s><b>%s</b></font>" % (13, v_FPBookingNumber),
                        style_right,
                    ),
                ],
                [
                    Paragraph(
                        "<font size=%s><b>%s</b></font>"
                        % (
                            13 if len(booking.de_To_Address_Suburb) < 13 else 10,
                            booking.de_To_Address_Suburb or "",
                        ),
                        style_left,
                    ),
                    Paragraph(
                        "<font size=%s>Itm: %s</font>"
                        % (6, gen_itm(booking, lines, j, sscc_cnt)),
                        style_right,
                    ),
                ],
            ]

            t1 = Table(
                tbl_data1,
                colWidths=(
                    float(label_settings["label_image_size_length"]) * (3 / 5) * mm,
                    float(label_settings["label_image_size_length"]) * (2 / 5) * mm,
                ),
                rowHeights=(float(label_settings["line_height_medium"]) * mm),
                style=[
                    ("TOPPADDING", (0, 0), (-1, -1), 0),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                    ("LEFTPADDING", (0, 0), (-1, -1), 0),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                    ("VALIGN", (0, 0), (0, -1), "BOTTOM"),
                ],
            )

            data = [[t1]]

            t_w = float(label_settings["label_image_size_length"]) * mm

            shell_table = Table(
                data,
                colWidths=[t_w],
                style=[
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("TOPPADDING", (0, 0), (-1, -1), 0),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                    ("BOTTOMBORDER", (0, 0), (-1, -1), 0),
                    ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ],
            )

            hr = HRFlowable(
                width=(float(label_settings["label_image_size_length"]) * mm),
                thickness=0.2,
                lineCap="square",
                color=colors.black,
                spaceBefore=0,
                spaceAfter=0,
                hAlign="CENTER",
                vAlign="BOTTOM",
                dash=None,
            )

            Story.append(shell_table)
            Story.append(Spacer(1, 5))
            Story.append(hr)

            tbl_data1 = [
                [
                    Paragraph(
                        "<font size=%s><b>%s</b></font>"
                        % (
                            16 if len(booking.vx_serviceName or "") < 12 else 9,
                            (booking.vx_serviceName or ""),
                        ),
                        style_left,
                    ),
                    "",
                ],
            ]

            t1 = Table(
                tbl_data1,
                colWidths=(
                    float(label_settings["label_image_size_length"]) * (3 / 5) * mm,
                    float(label_settings["label_image_size_length"]) * (2 / 5) * mm,
                ),
                rowHeights=(float(label_settings["line_height_small"]) * mm),
                style=[
                    ("TOPPADDING", (0, 0), (-1, -1), 0),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                    ("LEFTPADDING", (0, 0), (-1, -1), 0),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                    ("VALIGN", (0, 0), (0, -1), "TOP"),
                ],
            )

            data = [[t1]]

            t_w = float(label_settings["label_image_size_length"]) * mm

            shell_table = Table(
                data,
                colWidths=[t_w],
                style=[
                    ("TOPPADDING", (0, 0), (-1, -1), 0),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                    ("LEFTPADDING", (0, 0), (-1, -1), 0),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                    ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                    ("VALIGN", (0, 0), (-1, -1), "BOTTOM"),
                ],
            )

            Story.append(shell_table)
            Story.append(Spacer(1, 5))
            Story.append(hr)
            Story.append(Spacer(1, 2))

            tbl_data1 = [
                [
                    Paragraph(
                        "<font size=%s><b>%s</b></font>"
                        % (
                            9,
                            booking.b_dateBookedDate.strftime("%d/%m/%Y")
                            if booking.b_dateBookedDate
                            else booking.puPickUpAvailFrom_Date.strftime("%d/%m/%Y"),
                        ),
                        style_left,
                    ),
                    Paragraph(
                        "<font size=%s><b>%s &#160 of &#160 %s</b></font>"
                        % (9, j, totalQty),
                        style_left,
                    ),
                    Paragraph(
                        "<font size=%s><b>Item Wt.:%s %s.</b></font>"
                        % (
                            9,
                            round(e_Total_KG_weight, 3) or "",
                            booking_line.e_weightUOM or "KG",
                        ),
                        style_left,
                    ),
                    Paragraph(
                        "<font size=%s><b>%s</b></font>" % (9, " "),
                        style_right,
                    ),
                ],
            ]

            t1 = Table(
                tbl_data1,
                colWidths=(
                    float(label_settings["label_image_size_length"]) * (1 / 4) * mm,
                    float(label_settings["label_image_size_length"]) * (1 / 4) * mm,
                    float(label_settings["label_image_size_length"]) * (1 / 3) * mm,
                    float(label_settings["label_image_size_length"]) * (1 / 6) * mm,
                ),
                style=[
                    ("TOPPADDING", (0, 0), (-1, -1), -1),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
                    ("LEFTPADDING", (0, 0), (-1, -1), 0),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                    ("VALIGN", (0, 0), (0, -1), "TOP"),
                ],
            )

            data = [[t1]]

            t_w = float(label_settings["label_image_size_length"]) * mm

            shell_table = Table(
                data,
                colWidths=[t_w],
                style=[
                    ("TOPPADDING", (0, 0), (-1, -1), 0),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
                    ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ],
            )

            Story.append(shell_table)

            Story.append(hr)
            Story.append(Spacer(1, 2))

            tbl_data1 = [
                [
                    Paragraph(
                        "<font size=%s><b>%s</b></font>"
                        % (8, "Does not Contain Dangerous Goods"),
                        style_center,
                    ),
                ],
            ]

            t1 = Table(
                tbl_data1,
                colWidths=(float(label_settings["label_image_size_length"]) * mm),
                rowHeights=(float(label_settings["line_height_extra_small"]) * mm),
                style=[
                    ("TOPPADDING", (0, 0), (-1, -1), 0),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
                    ("LEFTPADDING", (0, 0), (-1, -1), 0),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                    ("VALIGN", (0, 0), (0, -1), "TOP"),
                ],
            )

            data = [[t1]]

            t_w = float(label_settings["label_image_size_length"]) * mm

            shell_table = Table(
                data,
                colWidths=[t_w],
                style=[
                    ("TOPPADDING", (0, 0), (-1, -1), 0),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
                    ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ],
            )

            Story.append(shell_table)

            Story.append(hr)
            Story.append(Spacer(1, 2))

            tbl_data1 = [
                [
                    Paragraph(
                        "<font size=%s><b>%s</b></font>" % (8, "To:"),
                        style_left,
                    )
                ],
            ]

            t1 = Table(
                tbl_data1,
                colWidths=(30),
                style=[
                    ("TOPPADDING", (0, 0), (-1, -1), 0),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                    ("LEFTPADDING", (0, 0), (-1, -1), 0),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ],
            )

            tbl_data2 = []
            font_size = 12

            if (
                len(booking.de_To_Address_Street_1 or "")
                + len(booking.de_To_Address_Street_2 or "")
                > 40
            ):
                font_size = 10

            tbl_data2.append(
                [
                    Paragraph(
                        "<font size=%s><b>%s</b></font>"
                        % (
                            font_size,
                            booking.de_to_Contact_F_LName or "",
                        ),
                        style_uppercase_big,
                    )
                ]
            )

            if (booking.deToCompanyName or "").lower() != (
                booking.de_to_Contact_F_LName or ""
            ).lower():
                tbl_data2.append(
                    [
                        Paragraph(
                            "<font size=%s><b>%s</b></font>"
                            % (
                                font_size,
                                booking.deToCompanyName or "",
                            ),
                            style_uppercase_big,
                        )
                    ]
                )

            tbl_data2.append(
                [
                    Paragraph(
                        "<font size=%s><b>%s</b></font>"
                        % (
                            font_size,
                            booking.de_To_Address_Street_1 or "",
                        ),
                        style_uppercase_big,
                    )
                ]
            )
            tbl_data2.append(
                [
                    Paragraph(
                        "<font size=%s><b>%s</b></font>"
                        % (
                            font_size,
                            booking.de_To_Address_Street_2 or "",
                        ),
                        style_uppercase_big,
                    )
                ]
            )
            tbl_data2.append(
                [
                    Paragraph(
                        "<font size=%s><b>%s %s %s</b></font> "
                        % (
                            font_size,
                            booking.de_To_Address_Suburb or "",
                            booking.de_To_Address_PostalCode or "",
                            booking.de_To_Address_State or "",
                        ),
                        style_uppercase_big,
                    ),
                ]
            )

            t2 = Table(
                tbl_data2,
                colWidths=(float(label_settings["label_image_size_length"]) * mm - 20),
                style=[
                    ("TOPPADDING", (0, 0), (-1, -1), 0),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                    ("LEFTPADDING", (0, 0), (-1, -1), 0),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ],
            )

            data = [[t1, t2]]

            t1_w = 30
            t2_w = float(label_settings["label_image_size_length"]) * mm - 30

            shell_table = Table(
                data,
                colWidths=[t1_w, t2_w],
                style=[
                    ("TOPPADDING", (0, 0), (-1, -1), 0),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ],
            )
            Story.append(shell_table)
            Story.append(Spacer(1, 2))
            Story.append(hr)

            tbl_data1 = [
                [
                    Paragraph(
                        "<font size=%s><b> %s </b></font>" % (8, "From:"),
                        style_left,
                    )
                ],
            ]

            t1 = Table(
                tbl_data1,
                colWidths=(30),
                style=[
                    ("TOPPADDING", (0, 0), (-1, -1), 0),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                    ("LEFTPADDING", (0, 0), (-1, -1), 0),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ],
            )

            if booking.pu_Address_street_2:
                tbl_data2 = [
                    [
                        Paragraph(
                            "<font size=%s>%s%s, %s, %s, %s, %s, %s</font>"
                            % (
                                8,
                                (
                                    (booking.puCompany + ", ")
                                    if (booking.puCompany or "").lower()
                                    != (booking.pu_Contact_F_L_Name or "").lower()
                                    else ""
                                ),
                                booking.pu_Contact_F_L_Name or "",
                                booking.pu_Address_Street_1 or "",
                                booking.pu_Address_street_2 or "",
                                booking.pu_Address_Suburb or "",
                                booking.pu_Address_PostalCode or "",
                                booking.pu_Address_State or "",
                            ),
                            style_uppercase,
                        )
                    ],
                ]
            else:
                tbl_data2 = [
                    [
                        Paragraph(
                            "<font size=%s>%s%s, %s, %s, %s, %s</font>"
                            % (
                                8,
                                (
                                    (booking.puCompany + ", ")
                                    if (booking.puCompany or "").lower()
                                    != (booking.pu_Contact_F_L_Name or "").lower()
                                    else ""
                                ),
                                booking.pu_Contact_F_L_Name or "",
                                booking.pu_Address_Street_1 or "",
                                booking.pu_Address_Suburb or "",
                                booking.pu_Address_PostalCode or "",
                                booking.pu_Address_State or "",
                            ),
                            style_uppercase,
                        )
                    ],
                ]

            t2 = Table(
                tbl_data2,
                colWidths=(float(label_settings["label_image_size_length"]) * mm - 30),
                style=[
                    ("TOPPADDING", (0, 0), (-1, -1), 0),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                    ("LEFTPADDING", (0, 0), (-1, -1), 0),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ],
            )

            data = [[t1, t2]]

            t1_w = 30
            t2_w = float(label_settings["label_image_size_length"]) * mm - 30

            shell_table = Table(
                data,
                colWidths=[t1_w, t2_w],
                style=[
                    ("TOPPADDING", (0, 0), (-1, -1), 0),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ],
            )
            Story.append(shell_table)

            tbl_data1 = [
                [
                    Paragraph(
                        "<font size=%s><b>Senders Ref:</b> %s</font>"
                        % (
                            8,
                            booking_line.gap_ras
                            if booking_line.gap_ras
                            else booking.b_client_order_num,
                        ),
                        style_left,
                    )
                ]
            ]

            t1 = Table(
                tbl_data1,
                colWidths=(float(label_settings["label_image_size_length"]) * mm),
                style=[
                    ("TOPPADDING", (0, 0), (-1, -1), 0),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                    ("LEFTPADDING", (0, 0), (-1, -1), 0),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ],
            )
            Story.append(t1)
            Story.append(Spacer(1, 5))

            special_instruction = booking.pu_pickup_instructions_address or ""

            if special_instruction:
                special_instruction = f"{special_instruction}, {booking.de_to_PickUp_Instructions_Address or ''}"[
                    :35
                ]
            else:
                special_instruction = (booking.de_to_PickUp_Instructions_Address or "")[
                    :35
                ]

            tbl_data1 = [
                [
                    Paragraph(
                        "<font size=%s><b>%s</b></font>" % (9, "Special Instructions:"),
                        style_left,
                    ),
                    Paragraph(
                        "<font size=%s>%s</font>" % (9, special_instruction),
                        style_left,
                    ),
                ],
            ]

            t1 = Table(
                tbl_data1,
                colWidths=(
                    33 * mm,
                    (float(label_settings["label_image_size_length"]) - 33) * mm,
                ),
                style=[
                    ("TOPPADDING", (0, 0), (-1, -1), 0),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                    ("LEFTPADDING", (0, 0), (-1, -1), 0),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ],
            )

            data = [[t1]]

            t_w = float(label_settings["label_image_size_length"]) * mm

            shell_table = Table(
                data,
                colWidths=[t_w],
                style=[
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("TOPPADDING", (0, 0), (-1, -1), 0),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                    ("BOTTOMBORDER", (0, 0), (-1, -1), 0),
                    ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ],
            )

            Story.append(shell_table)
            Story.append(Spacer(1, 5))

            tbl_data1 = [
                [
                    Paragraph(
                        "<font size=%s><b>CN: %s</b></font>"
                        % (
                            label_settings["font_size_normal"],
                            v_FPBookingNumber,
                        ),
                        style_left,
                    )
                ],
                [
                    Paragraph(
                        "<font size=%s><b>Itm: %s</b></font>"
                        % (
                            label_settings["font_size_normal"],
                            gen_itm(booking, lines, j, sscc_cnt),
                        ),
                        style_left,
                    )
                ],
                [
                    Paragraph(
                        "<font size=%s><b>%s &#160 of &#160 %s</b></font>"
                        % (label_settings["font_size_normal"], j, totalQty),
                        style_left,
                    )
                ],
                [
                    Paragraph(
                        "<font size=%s><b>%s</b></font>"
                        % (label_settings["font_size_normal"], "TO:"),
                        style_uppercase,
                    )
                ],
                [
                    Paragraph(
                        "<font size=%s>%s</font>"
                        % (
                            label_settings["font_size_normal"],
                            booking.deToCompanyName or "",
                        ),
                        style_uppercase,
                    )
                ],
                [
                    Paragraph(
                        "<font size=%s>%s</font>"
                        % (
                            label_settings["font_size_normal"],
                            (booking.de_To_Address_Street_1 or "")[:25],
                        ),
                        style_uppercase,
                    ),
                ],
                [
                    Paragraph(
                        "<font size=%s>%s</font> "
                        % (
                            label_settings["font_size_normal"],
                            booking.de_To_Address_Street_2 or "",
                        ),
                        style_uppercase,
                    ),
                ],
                [
                    Paragraph(
                        "<font size=%s>%s %s %s</font> "
                        % (
                            label_settings["font_size_normal"],
                            booking.de_To_Address_Suburb or "",
                            booking.de_To_Address_PostalCode or "",
                            booking.de_To_Address_State or "",
                        ),
                        style_uppercase,
                    ),
                ],
            ]

            t1 = Table(
                tbl_data1,
                colWidths=(
                    float(label_settings["label_image_size_length"]) * (1 / 2) * mm
                ),
                style=[
                    ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                    ("TOPPADDING", (0, 0), (-1, -1), 0),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                    ("LEFTPADDING", (0, 0), (-1, -1), 3),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ],
            )

            tbl_data2 = [
                [
                    Paragraph(
                        "<font size=%s><b>%s</b></font>"
                        % (
                            label_settings["font_size_normal"],
                            booking.vx_serviceName or "",
                        ),
                        style_left,
                    )
                ],
                [
                    Paragraph(
                        "<font size=%s><b>Con Note Wt.: %s %s.</b></font>"
                        % (
                            label_settings["font_size_normal"],
                            round(booking_line.e_weightPerEach * booking_line.e_qty, 3)
                            or "",
                            booking_line.e_weightUOM or "KG",
                        ),
                        style_left,
                    )
                ],
                [
                    Paragraph(
                        "<font size=%s><b>%s</b></font>"
                        % (label_settings["font_size_normal"], "FROM:"),
                        style_left,
                    )
                ],
                [
                    Paragraph(
                        "<font size=%s>%s</font>"
                        % (
                            label_settings["font_size_normal"],
                            booking.puCompany or "",
                        ),
                        style_uppercase,
                    )
                ],
                [
                    Paragraph(
                        "<font size=%s>%s</font>"
                        % (
                            label_settings["font_size_normal"],
                            booking.pu_Address_Street_1 or "",
                        ),
                        style_uppercase,
                    ),
                ],
                [
                    Paragraph(
                        "<font size=%s>%s</font> "
                        % (
                            label_settings["font_size_normal"],
                            booking.pu_Address_street_2 or "",
                        ),
                        style_uppercase,
                    ),
                ],
                [
                    Paragraph(
                        "<font size=%s>%s %s %s</font> "
                        % (
                            label_settings["font_size_normal"],
                            booking.pu_Address_Suburb or "",
                            booking.pu_Address_PostalCode or "",
                            booking.pu_Address_State or "",
                        ),
                        style_uppercase,
                    ),
                ],
            ]

            t2 = Table(
                tbl_data2,
                colWidths=(
                    float(label_settings["label_image_size_length"]) * (1 / 2) * mm
                ),
                style=[
                    ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("TOPPADDING", (0, 0), (-1, -1), 0),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                    ("LEFTPADDING", (0, 0), (-1, -1), 0),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ],
            )

            data = [[t1, t2]]

            t1_w = float(label_settings["label_image_size_length"]) * (1 / 2) * mm
            t2_w = float(label_settings["label_image_size_length"]) * (1 / 2) * mm

            shell_table = Table(
                data,
                colWidths=[t1_w, t2_w],
                style=[
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("TOPPADDING", (0, 0), (-1, -1), 0),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                    ("LEFTPADDING", (0, 0), (-1, -1), 3),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                    ("BOX", (0, 0), (-1, -1), 0.5, colors.black),
                    ("LINEBEFORE", (1, 0), (-1, -1), 0.5, colors.black),
                ],
            )

            Story.append(shell_table)
            Story.append(Spacer(5, 5))

            barcode = gen_barcode(booking, v_FPBookingNumber, j)

            tbl_data = [[code128.Code128(barcode, barWidth=1.1, barHeight=12 * mm)]]

            t1 = Table(
                tbl_data,
                colWidths=((float(label_settings["label_image_size_length"])) * mm),
                style=[
                    ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                    ("VALIGN", (0, 0), (0, -1), "TOP"),
                    ("TOPPADDING", (0, 0), (-1, -1), 0),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                    ("LEFTPADDING", (0, 0), (0, -1), 0),
                    ("RIGHTPADDING", (0, 0), (0, -1), 0),
                ],
            )

            Story.append(t1)
            # Story.append(Spacer(1, 5))

            fp_color_code = (
                Fp_freight_providers.objects.get(fp_company_name="TNT").hex_color_code
                or "808080"
            )

            tbl_data1 = [
                [
                    fp_img
                    if fp_img
                    else Paragraph(
                        "<font size=%s><b>%s</b></font>"
                        % (
                            label_settings["font_size_extra_large"],
                            (booking.vx_freight_provider)
                            if (booking.vx_freight_provider)
                            else "",
                        ),
                        style_center_bg,
                    )
                ],
                [""],
            ]

            t1 = Table(
                tbl_data1,
                colWidths=(
                    float(label_settings["label_image_size_length"]) * (3 / 8) * mm,
                ),
                rowHeights=(
                    float(label_settings["line_height_large"]) * 1 / 1 * mm,
                    float(label_settings["line_height_large"]) * 1 / 2 * mm,
                ),
                style=[
                    ("TOPPADDING", (0, 0), (-1, -1), 0),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                    ("LEFTPADDING", (0, 0), (-1, -1), 0),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                    ("VALIGN", (0, 0), (0, -1), "TOP"),
                    ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                    ("BACKGROUND", (0, 1), (-1, -1), f"#{fp_color_code}"),
                ],
            )

            # codeString = f"DME{booking.b_bookingID_Visual}{str(j).zfill(3)}, {booking.b_bookingID_Visual}, {booking.b_client_name}, {booking.b_client_sales_inv_num}, {booking.de_To_Address_PostalCode}"
            # d = Drawing(20, 20)
            # d.add(Rect(0, 0, 0, 0, strokeWidth=1, fillColor=None))
            # d.add(QrCodeWidget(value=codeString, barWidth=20 * mm, barHeight=20 * mm))

            # tbl_data1 = [[dme_img, d, t1]]
            tbl_data1 = [[dme_img, "", t1]]

            t1 = Table(
                tbl_data1,
                colWidths=(
                    float(label_settings["label_dimension_length"]) * (3 / 10) * mm,
                    float(label_settings["label_dimension_length"]) * (2 / 10) * mm,
                    float(label_settings["label_dimension_length"]) * (5 / 10) * mm,
                ),
                rowHeights=(float(label_settings["line_height_large"]) * 1.9 * mm),
                style=[
                    ("TOPPADDING", (0, 0), (-1, -1), 0),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                    ("LEFTPADDING", (0, 0), (0, -1), 30),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                    ("VALIGN", (0, 0), (0, -1), "CENTER"),
                    ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ],
            )

            data = [[t1]]

            t2_w = float(label_settings["label_dimension_length"]) * mm

            shell_table = Table(
                data,
                colWidths=[t2_w],
                style=[
                    ("VALIGN", (0, 0), (-1, -1), "CENTER"),
                    ("TOPPADDING", (0, 0), (-1, -1), 0),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 3),
                    ("BOTTOMBORDER", (0, 0), (-1, -1), 0),
                    ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 3),
                ],
            )
            Story.append(shell_table)
            Story.append(Spacer(1, 10))
            Story.append(PageBreak())

            j += 1

    doc.build(Story, onFirstPage=myFirstPage, onLaterPages=myLaterPages)
    file.close()
    logger.info(
        f"#119 [TNT LABEL] Finished building label... (Booking ID: {booking.b_bookingID_Visual})"
    )
    return filepath, filename
