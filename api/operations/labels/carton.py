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

from api.models import Booking_lines, Client_FP
from api.helpers.cubic import get_cubic_meter
from api.operations.api_booking_confirmation_lines import index as api_bcl
from api.clients.operations.index import extract_product_code
from api.common.ratio import _get_dim_amount, _get_weight_amount
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
style_left_space = ParagraphStyle(
    name="left",
    parent=styles["Normal"],
    alignment=TA_LEFT,
    leading=8,
    spaceBefore=8,
)
style_left_large = ParagraphStyle(
    name="left",
    parent=styles["Normal"],
    alignment=TA_LEFT,
    leading=13,
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
        f"#110 [CARTON LABEL] Started building label... (Booking ID: {booking.b_bookingID_Visual}, Lines: {lines})"
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
    logger.info(f"#111 [CARTON LABEL] File full path: {filepath}/{filename}")
    # end pdf file name using naming convention

    if not lines:
        lines = Booking_lines.objects.filter(fk_booking_id=booking.pk_booking_id)

    # label_settings = get_label_settings( 146, 104 )[0]
    label_settings = {
        "font_family": "Arial",
        "font_size_small": "8",
        "font_size_medium": "8",
        "font_size_extra_medium": "11",
        "font_size_large": "9",
        "font_size_extra_large": "20",
        "font_size_extra_less_large": "16",
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
    dme_logo = "./static/assets/logos/dme.png"
    dme_img = Image(dme_logo, 20 * mm, 5 * mm)

    fp_color_code = pre_data["color_code"] or "808080"

    Story = []
    j = 1

    if sscc:
        j = 1 + label_index

    for line in lines:
        for k in range(line.e_qty):
            if one_page_label and k > 0:
                continue

            Story.append(Spacer(1, 1))

            img_data = [
                [
                    dme_img,
                    Paragraph(
                        "<font size=%s>CARTON LABEL</font>"
                        % (label_settings["font_size_extra_large"]),
                        style_left_bg,
                    ),
                ]
            ]

            df_w = float(label_settings["label_image_size_length"]) * 0.26 * mm
            dm_w = float(label_settings["label_image_size_length"]) * 0.73 * mm

            logo = Table(
                img_data,
                colWidths=[df_w, dm_w],
                style=[
                    ("VALIGN", (0, 0), (0, 0), "MIDDLE"),
                    ("ALIGN", (0, 0), (0, 0), "LEFT"),
                ],
            )

            Story.append(logo)
            Story.append(Spacer(1, 5))

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

            tbl_data1 = [
                [
                    Paragraph(
                        "<font size=%s>To:</font>"
                        % (label_settings["font_size_large"]),
                        style_left_large,
                    ),
                ],
                [Spacer(1, 1)],
                [
                    Paragraph(
                        "<font size=%s>%s<br/>%s<br/>%s</font>"
                        % (
                            label_settings["font_size_medium"],
                            booking.deToCompanyName,
                            booking.de_To_Address_Street_1,
                            booking.de_To_Address_Street_2,
                        ),
                        style_left_space,
                    ),
                ],
                [Spacer(1, 4)],
                [
                    Paragraph(
                        "<font size=%s>%s %s %s</font>"
                        % (
                            label_settings["font_size_large"],
                            booking.de_To_Address_Suburb,
                            booking.de_To_Address_State,
                            booking.de_To_Address_PostalCode,
                        ),
                        style_left_space,
                    ),
                ],
                [Spacer(1, 8)],
                [
                    Paragraph(
                        "<font size=%s>From: </font>"
                        % (label_settings["font_size_large"]),
                        style_left,
                    )
                ],
                [Spacer(1, 2)],
                [pu_address],
            ]

            tbl_data2 = [
                [
                    Paragraph(
                        "<font size=%s>Inv No: %s</font>"
                        % (
                            label_settings["font_size_large"],
                            booking.b_client_sales_inv_num
                            or booking.b_client_order_num
                            or "",
                        ),
                        style_left_large,
                    )
                ],
                [
                    Paragraph(
                        "<font size=%s>Carrier: %s</font>"
                        % (
                            label_settings["font_size_large"],
                            booking.vx_freight_provider,
                        ),
                        style_left_large,
                    )
                ],
                [
                    Paragraph(
                        "<font size=%s>Con No: %s</font>"
                        % (label_settings["font_size_large"], v_FPBookingNumber),
                        style_left_large,
                    )
                ],
            ]

            shell_table = Table(
                [
                    [
                        Table(
                            tbl_data1,
                            style=[
                                ("TOPPADDING", (0, 0), (-1, -1), 0),
                                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                                ("LEFTPADDING", (0, 1), (0, 4), 20),
                                ("LEFTPADDING", (0, 7), (0, 8), 20),
                            ],
                        ),
                        Table(
                            tbl_data2,
                            style=[
                                ("TOPPADDING", (0, 0), (-1, -1), 0),
                                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                            ],
                        ),
                    ]
                ],
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
            Story.append(Spacer(5, 1))

            border = Table(
                [
                    [
                        Paragraph("", style_left),
                    ]
                ],
                rowHeights=(5 * mm),
                style=[
                    ("VALIGN", (0, 0), (0, 0), "MIDDLE"),
                    ("ALIGN", (0, 0), (0, 0), "RIGHT"),
                    ("LINEBELOW", (0, 0), (0, 0), 1, colors.HexColor(0x000000)),
                ],
            )

            Story.append(border)

            Story.append(Spacer(5, 10))

            tbl_data = [
                [
                    Paragraph(
                        "<font size=%s>Product Model: </font><font size=%s>%s</font>"
                        % (
                            label_settings["font_size_large"],
                            label_settings["font_size_medium"],
                            line.e_item_type or "",
                        ),
                        style_left_large,
                    ),
                    Paragraph(
                        "<font size=%s>Bin: </font><font size=%s>%s</font>"
                        % (
                            label_settings["font_size_large"],
                            label_settings["font_size_medium"],
                            line.e_bin_number,
                        ),
                        style_left_large,
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
                    ("LEFTPADDING", (0, 0), (1, 0), 12),
                ],
            )

            Story.append(shell_table)

            Story.append(Spacer(5, 1))

            tbl_data1 = [
                [
                    Paragraph(
                        "<font size=%s>Product Description: </font><font size=%s>%s</font>"
                        % (
                            label_settings["font_size_large"],
                            label_settings["font_size_medium"],
                            line.e_item or "",
                        ),
                        style_left_large,
                    ),
                ],
                [Spacer(1, 5)],
                [
                    Paragraph(
                        "<font size=%s>%s</font>"
                        % (
                            label_settings["font_size_medium"],
                            extract_product_code(line.e_item)[:20],
                        ),
                        style_left_space,
                    ),
                ],
            ]

            _dim_amount = _get_dim_amount(line.e_dimUOM)
            _weight_amount = _get_weight_amount(line.e_weightUOM)
            _length = round(_dim_amount * (line.e_dimLength or 0), 3)
            _width = round(_dim_amount * (line.e_dimWidth or 0), 3)
            _height = round(_dim_amount * (line.e_dimHeight or 0), 3)
            _weight = round(_weight_amount * (line.e_dimHeight or 0), 3)
            _cubic = get_cubic_meter(
                line.e_dimLength, line.e_dimWidth, line.e_dimHeight, line.e_dimUOM
            )
            _cubic = round(_cubic, 3)

            tbl_data2 = [
                [
                    Paragraph(
                        "<font size=%s>Item: %s of %s</font>"
                        % (label_settings["font_size_large"], (k + 1), line.e_qty),
                        style_left_large,
                    )
                ],
                [
                    Paragraph(
                        "<font size=%s>Dims: %s x %s x %s</font>"
                        % (label_settings["font_size_large"], _length, _width, _height),
                        style_left_large,
                    )
                ],
                [
                    Paragraph(
                        "<font size=%s>KGs: %s</font>"
                        % (label_settings["font_size_large"], f"{_weight} KG"),
                        style_left_large,
                    )
                ],
                [
                    Paragraph(
                        "<font size=%s>Cubic: %s</font>"
                        % (label_settings["font_size_large"], _cubic),
                        style_left_large,
                    )
                ],
            ]

            shell_table = Table(
                [
                    [
                        Table(
                            tbl_data1,
                            style=[
                                ("TOPPADDING", (0, 0), (-1, -1), 0),
                                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                                ("LEFTPADDING", (0, 1), (0, 2), 20),
                            ],
                        ),
                        Table(
                            tbl_data2,
                            style=[
                                ("TOPPADDING", (0, 0), (-1, -1), 0),
                                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                            ],
                        ),
                    ]
                ],
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

            Story.append(Spacer(5, 75))

            tbl_data = [
                [
                    Paragraph(
                        "<font size=%s>%s</font>"
                        % (
                            label_settings["font_size_extra_less_large"],
                            "NOT A SHIPPING LABEL",
                        ),
                        style_center,
                    )
                ],
            ]

            comment_text = Table(
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

            Story.append(comment_text)

            # tbl_data = [
            #     [
            #         code128.Code128(
            #             line.sscc,
            #             barHeight=float(label_settings["barcode_dimension_width"]) * mm,
            #             barWidth=1.2 if "NOSSCC" in line.sscc else 1.9,
            #             humanReadable=False,
            #         )
            #     ],
            # ]

            # barcode_table = Table(
            #     tbl_data,
            #     colWidths=((float(label_settings["barcode_dimension_length"])) * mm),
            #     style=[
            #         ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            #         ("VALIGN", (0, 0), (0, -1), "TOP"),
            #         ("TOPPADDING", (0, 0), (-1, -1), 5),
            #         ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            #         ("LEFTPADDING", (0, 0), (0, -1), 0),
            #         ("RIGHTPADDING", (0, 0), (0, -1), 0),
            #     ],
            # )

            # Story.append(barcode_table)

            # Story.append(Spacer(1, 2))

            # tbl_data = [
            #     [
            #         Paragraph(
            #             "<font size=%s>%s</font>"
            #             % (
            #                 label_settings["font_size_small"],
            #                 line.sscc,
            #             ),
            #             style_center,
            #         )
            #     ],
            # ]

            # barcode_text = Table(
            #     tbl_data,
            #     colWidths=(float(label_settings["label_image_size_length"]) * mm),
            #     style=[
            #         ("TOPPADDING", (0, 0), (-1, -1), 0),
            #         ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            #         ("LEFTPADDING", (0, 0), (-1, -1), 12),
            #         ("RIGHTPADDING", (0, 0), (-1, -1), 12),
            #         ("VALIGN", (0, 0), (-1, -1), "TOP"),
            #         ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            #     ],
            # )

            # Story.append(barcode_text)

            Story.append(PageBreak())

            j += 1

    doc.build(Story, onFirstPage=myFirstPage, onLaterPages=myLaterPages)
    file.close()
    logger.info(
        f"#119 [CARTON LABEL] Finished building label... (Booking ID: {booking.b_bookingID_Visual})"
    )
    return filepath, filename
