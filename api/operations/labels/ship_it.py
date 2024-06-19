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
from api.fp_apis.utils import gen_consignment_num
from api.operations.api_booking_confirmation_lines import index as api_bcl

logger = logging.getLogger(__name__)

styles = getSampleStyleSheet()
style_right = ParagraphStyle(name="right", parent=styles["Normal"], alignment=TA_RIGHT)
style_left = ParagraphStyle(
    name="left",
    parent=styles["Normal"],
    alignment=TA_LEFT,
    leading=12,
)
style_center = ParagraphStyle(
    name="center",
    parent=styles["Normal"],
    alignment=TA_CENTER,
    leading=10,
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


def get_barcode_rotated(
    value,
    width,
    barHeight=27.6 * mm,
    barWidth=1,
    fontSize=18,
    humanReadable=True,
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


class RotatedImage(Image):
    def wrap(self, availWidth, availHeight):
        h, w = Image.wrap(self, availHeight, availWidth)
        return w, h

    def draw(self):
        self.canv.rotate(90)
        Image.draw(self)


def gen_barcode(booking, booking_lines, line_index, sscc_cnt):
    consignment_num = gen_consignment_num(
        booking.vx_freight_provider, booking.b_bookingID_Visual, booking.kf_client_id, booking
    )
    item_index = str(line_index).zfill(3)
    items_count = str(sscc_cnt).zfill(3)
    postal_code = booking.de_To_Address_PostalCode

    label_code = f"{consignment_num}{item_index}"
    api_bcl.create(booking, [{"label_code": label_code}])

    return f"{consignment_num}{item_index}{items_count}{postal_code}"


def build_label(booking, filepath, lines=[], label_index=0):
    logger.info(
        f"#110 [SHIP-IT LABEL] Started building label... (Booking ID: {booking.b_bookingID_Visual}, Lines: {lines})"
    )
    v_FPBookingNumber = gen_consignment_num(
        booking.vx_freight_provider, booking.b_bookingID_Visual
    )

    # start check if pdfs folder exists
    if not os.path.exists(filepath):
        os.makedirs(filepath)
    # end check if pdfs folder exists

    # start pdf file name using naming convention
    if lines:
        filename = (
            booking.pu_Address_State
            + "_"
            + str(booking.b_bookingID_Visual)
            + "_"
            + str(lines[0].pk)
            + "_"
            + str(len(lines))
            + ".pdf"
        )
    else:
        filename = (
            booking.pu_Address_State
            + "_"
            + str(booking.v_FPBookingNumber)
            + "_"
            + str(booking.b_bookingID_Visual)
            + ".pdf"
        )

    file = open(f"{filepath}/{filename}", "w")
    # end pdf file name using naming convention

    if not lines:
        lines = Booking_lines.objects.filter(fk_booking_id=booking.pk_booking_id)

    totalQty = 0
    for booking_line in lines:
        totalQty = totalQty + booking_line.e_qty

    # label_settings = get_label_settings( 146, 104 )[0]
    label_settings = {
        "font_family": "Verdana",
        "font_size_extra_small": "4",
        "font_size_small": "6",
        "font_size_medium": "8",
        "font_size_large": "10",
        "font_size_extra_large": "13",
        "label_dimension_length": "100",
        "label_dimension_width": "150",
        "label_image_size_length": "85",
        "label_image_size_width": "130",
        "label_image_size_height": "130",
        "barcode_dimension_length": "85",
        "barcode_dimension_width": "30",
        "barcode_font_size": "18",
        "line_height_extra_small": "3",
        "line_height_small": "5",
        "line_height_medium": "6",
        "line_height_large": "8",
        "margin_v": "5",
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
    dme_img = Image(dme_logo, 30 * mm, 8 * mm)

    Story = []
    j = 1

    for booking_line in lines:
        for j_index in range(booking_line.e_qty):
            logger.info(f"#114 [SHIP-IT LABEL] Adding: {booking_line}")
            tbl_data1 = [[dme_img]]
            t1 = Table(
                tbl_data1,
                colWidths=(
                    float(label_settings["label_image_size_length"]) * (1 / 3) * mm
                ),
                rowHeights=(float(label_settings["line_height_large"]) * mm),
                style=[
                    ("TOPPADDING", (0, 0), (-1, -1), 0),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                    ("LEFTPADDING", (0, 0), (-1, -1), 0),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                    ("VALIGN", (0, 0), (0, -1), "TOP"),
                ],
            )

            tbl_data2 = [
                [
                    Paragraph(
                        "<font size=%s><b>%s</b></font>"
                        % (
                            label_settings["font_size_extra_large"],
                            (booking.vx_freight_provider)
                            if (booking.vx_freight_provider)
                            else "",
                        ),
                        style_right,
                    )
                ]
            ]

            t2 = Table(
                tbl_data2,
                colWidths=(
                    float(label_settings["label_image_size_length"]) * (2 / 3) * mm
                ),
                rowHeights=(float(label_settings["line_height_medium"]) * mm),
                style=[
                    ("TOPPADDING", (0, 0), (-1, -1), 0),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                    ("VALIGN", (0, 0), (0, -1), "TOP"),
                ],
            )

            data = [[t1, t2]]

            t1_w = float(label_settings["label_image_size_length"]) * (1 / 3) * mm
            t2_w = float(label_settings["label_image_size_length"]) * (2 / 3) * mm

            title_row = Table(
                data,
                colWidths=[t1_w, t2_w],
                style=[
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("TOPPADDING", (0, 0), (-1, -1), 0),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                    ("BOTTOMBORDER", (0, 0), (-1, -1), 0),
                ],
            )

            hr = HRFlowable(
                width=(float(label_settings["label_image_size_length"]) * mm),
                thickness=1,
                lineCap="square",
                color=colors.black,
                spaceBefore=0,
                spaceAfter=0,
                hAlign="CENTER",
                vAlign="BOTTOM",
                dash=None,
            )

            tbl_data1 = [
                [
                    Paragraph(
                        "<font size=%s>Connote: %s </font>"
                        % (
                            label_settings["font_size_medium"],
                            v_FPBookingNumber or "",
                        ),
                        style_left,
                    ),
                    Paragraph(
                        "<font size=%s><b>%s</b></font> "
                        % (label_settings["font_size_extra_large"], ""),
                        style_left,
                    ),
                ],
                [
                    Paragraph(
                        "<font size=%s>Order: %s</font>"
                        % (
                            label_settings["font_size_medium"],
                            booking.b_client_order_num,
                        ),
                        style_left,
                    )
                ],
                [
                    Paragraph(
                        "<font size=%s>Date: %s</font> "
                        % (
                            label_settings["font_size_medium"],
                            booking.b_dateBookedDate.strftime("%d/%m/%Y")
                            if booking.b_dateBookedDate
                            else "N/A",
                        ),
                        style_left,
                    )
                ],
            ]

            order_row = Table(
                tbl_data1,
                colWidths=(
                    float(label_settings["label_image_size_length"]) * (1 / 2) * mm,
                    float(label_settings["label_image_size_length"]) * (1 / 2) * mm,
                ),
                rowHeights=(float(label_settings["line_height_extra_small"]) * mm),
                style=[
                    ("TOPPADDING", (0, 0), (-1, -1), 0),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                    # ("LEFTPADDING", (0, 0), (-1, -1), 0),
                    # ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ],
            )

            barcode = gen_barcode(booking, lines, j, sscc_cnt)

            tbl_data1 = [
                [
                    code128.Code128(
                        barcode,
                        barHeight=10 * mm,
                        barWidth=1,
                        humanReadable=True,
                    )
                ]
            ]

            barcode_row = Table(
                tbl_data1,
                colWidths=(float(label_settings["label_image_size_length"]) * mm),
                style=[
                    ("TOPPADDING", (0, 0), (-1, -1), 0),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ],
            )

            tbl_data1 = [
                [
                    Paragraph(
                        "<font size=%s><b>FROM:</b> %s</font>"
                        % (
                            label_settings["font_size_medium"],
                            (booking.b_client_name or ""),
                        ),
                        style_left,
                    )
                ],
                [
                    Paragraph(
                        "<font size=%s>%s</font>"
                        % (
                            label_settings["font_size_medium"],
                            (booking.pu_Contact_F_L_Name or ""),
                        ),
                        style_left,
                    )
                ],
                [
                    Paragraph(
                        "<font size=%s>%s %s</font>"
                        % (
                            label_settings["font_size_medium"],
                            str(booking.pu_Address_Street_1 or ""),
                            str(booking.pu_Address_street_2 or ""),
                        ),
                        style_left,
                    )
                ],
                [
                    Paragraph(
                        "<font size=%s>%s</font>"
                        % (
                            label_settings["font_size_medium"],
                            booking.pu_Address_Suburb or "",
                        ),
                        style_left,
                    )
                ],
                [
                    Paragraph(
                        "<font size=%s>%s %s %s</font>"
                        % (
                            label_settings["font_size_medium"],
                            (booking.pu_Address_State or "").upper(),
                            booking.pu_Address_Country,
                            str(booking.pu_Address_PostalCode or ""),
                        ),
                        style_left,
                    )
                ],
            ]

            from_row = Table(
                tbl_data1,
                colWidths=(float(label_settings["label_image_size_length"]) * mm),
                style=[
                    ("TOPPADDING", (0, 0), (-1, -1), 0),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ],
            )

            tbl_data1 = [
                [
                    Paragraph(
                        "<font size=%s><b>TO:</b> %s</font>"
                        % (
                            label_settings["font_size_medium"],
                            booking.de_to_Contact_F_LName,
                        ),
                        style_left,
                    )
                ],
                [
                    Paragraph(
                        "<font size=%s>%s</font>"
                        % (
                            label_settings["font_size_medium"],
                            booking.de_To_Address_Street_1,
                        ),
                        style_left,
                    )
                ],
                [
                    Paragraph(
                        "<font size=%s>%s</font> "
                        % (label_settings["font_size_medium"], ""),
                        style_left,
                    )
                ],
                [
                    Paragraph(
                        "<font size=%s>%s</font> "
                        % (
                            label_settings["font_size_medium"],
                            booking.de_To_Address_Suburb or "",
                        ),
                        style_left,
                    )
                ],
                [
                    Paragraph(
                        "<font size=%s>%s %s %s</font> "
                        % (
                            label_settings["font_size_medium"],
                            (booking.de_To_Address_State or "").upper(),
                            booking.de_To_Address_Country,
                            str(booking.de_To_Address_PostalCode or ""),
                        ),
                        style_left,
                    )
                ],
                [
                    Paragraph(
                        "<font size=%s><b>TEL:</b> %s</font>"
                        % (
                            label_settings["font_size_medium"],
                            booking.de_to_Phone_Main or "",
                        ),
                        style_left,
                    )
                ],
            ]

            t1 = Table(
                tbl_data1,
                colWidths=(
                    float(label_settings["label_image_size_length"]) * (1 / 2) * mm
                ),
                style=[
                    ("TOPPADDING", (0, 0), (-1, -1), 0),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                    ("LEFTPADDING", (0, 0), (-1, -1), 0),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ],
            )

            tbl_data2 = [
                [
                    Paragraph(
                        "<font size=%s>Items: %s</font>"
                        % (label_settings["font_size_small"], totalQty),
                        style_left,
                    )
                ],
                [
                    Paragraph(
                        "<font size=%s>Reference: %s</font>"
                        % (
                            label_settings["font_size_small"],
                            booking_line.sscc or "N/A",
                        ),
                        style_left,
                    )
                ],
                [
                    Paragraph(
                        "<font size=%s>Weight: %s KG</font>"
                        % (
                            label_settings["font_size_small"],
                            booking_line.e_Total_KG_weight or "N/A",
                        ),
                        style_left,
                    )
                ],
                [
                    Paragraph(
                        "<font size=%s>Cube: %s M<super rise=4 size=4>3</super></font>"
                        % (
                            label_settings["font_size_small"],
                            booking_line.e_1_Total_dimCubicMeter,
                        ),
                        style_left,
                    )
                ],
                [
                    Paragraph(
                        "<font size=%s>Ref: %s</font>"
                        % (
                            label_settings["font_size_small"],
                            booking_line.gap_ras or "N/A",
                        ),
                        style_left,
                    )
                ],
            ]

            t2 = Table(
                tbl_data2,
                colWidths=(
                    float(label_settings["label_image_size_length"]) * (1 / 2) * mm
                ),
                style=[
                    ("TOPPADDING", (0, 0), (-1, -1), 0),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                    # ("LEFTPADDING", (0, 0), (-1, -1), 0),
                    # ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ],
            )

            data = [[t1, t2]]

            t1_w = float(label_settings["label_image_size_length"]) * (1 / 2) * mm
            t2_w = float(label_settings["label_image_size_length"]) * (1 / 2) * mm

            to_row = Table(
                data,
                colWidths=[t1_w, t2_w],
                style=[
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("TOPPADDING", (0, 0), (-1, -1), 0),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                ],
            )

            tbl_data1 = [
                [
                    Paragraph(
                        "<font size=%s>Instructions: %s</font>"
                        % (
                            label_settings["font_size_small"],
                            booking.pu_pickup_instructions_address or "",
                        ),
                        style_left,
                    )
                ]
            ]

            instructions_row = Table(
                tbl_data1,
                colWidths=(float(label_settings["label_image_size_length"]) * mm),
                style=[
                    ("TOPPADDING", (0, 0), (-1, -1), 0),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                ],
            )

            tbl_data1 = [
                [
                    Paragraph(
                        "<font size=%s>%s of %s</font>"
                        % (label_settings["font_size_small"], j, sscc_cnt),
                        style_center,
                    )
                ]
            ]

            t1 = Table(
                tbl_data1,
                colWidths=(float(label_settings["label_image_size_length"]) * mm),
                style=[
                    ("TOPPADDING", (0, 0), (-1, -1), 0),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                    # ("LEFTPADDING", (0, 0), (-1, -1), 0),
                    # ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ],
            )

            tbl_data1 = [
                [
                    Paragraph(
                        "<font size=%s color=%s >%s</font>"
                        % (
                            label_settings["font_size_small"],
                            colors.white,
                            "Powered by DeliverMe Learn more at Deliverme.com",
                        ),
                        style_center,
                    )
                ]
            ]

            t2 = Table(
                tbl_data1,
                colWidths=(float(label_settings["label_image_size_length"]) * mm),
                style=[
                    ("TOPPADDING", (0, 0), (-1, -1), 0),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                    # ("LEFTPADDING", (0, 0), (-1, -1), 0),
                    # ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                    ("BACKGROUND", (0, 0), (-1, -1), colors.black),
                ],
            )

            if totalQty > 1:
                data = [[t1], [t2]]
            else:
                data = [[t2]]

            t_w = float(label_settings["label_image_size_length"]) * mm

            footer_row = Table(
                data,
                colWidths=[t_w],
                style=[
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("TOPPADDING", (0, 0), (-1, -1), 0),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                    ("LEFTPADDING", (0, 0), (-1, -1), 0),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ],
            )

            content_data = [
                [title_row],
                [hr],
                [Spacer(1, 5)],
                [order_row],
                [hr],
                [Spacer(1, 10)],
                [barcode_row],
                [Spacer(1, 15)],
                [hr],
                [Spacer(1, 5)],
                [from_row],
                [hr],
                [Spacer(1, 5)],
                [to_row],
                [Spacer(1, 5)],
                [hr],
                [Spacer(1, 5)],
                [instructions_row],
            ]

            content = Table(
                content_data,
                colWidths=(float(label_settings["label_image_size_length"]) * mm),
                style=[
                    ("TOPPADDING", (0, 0), (-1, -1), 0),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                    ("LEFTPADDING", (0, 0), (-1, -1), 0),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ],
            )

            page_data = [[content], [footer_row]]

            page = Table(
                page_data,
                colWidths=(float(label_settings["label_image_size_length"]) * mm),
                rowHeights=(
                    [
                        float(label_settings["label_image_size_height"])
                        * (14 / 15)
                        * mm,
                        float(label_settings["label_image_size_height"])
                        * (1 / 15)
                        * mm,
                    ]
                ),
                style=[
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("TOPPADDING", (0, 0), (-1, -1), 0),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                    ("LEFTPADDING", (0, 0), (-1, -1), 0),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ],
            )
            Story.append(page)
            Story.append(PageBreak())

            j += 1

    doc.build(Story, onFirstPage=myFirstPage, onLaterPages=myLaterPages)
    file.close()
    logger.info(
        f"#119 [SHIP-IT LABEL] Finished building label... (Booking ID: {booking.b_bookingID_Visual})"
    )
    return filepath, filename
