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
from api.clients.operations.index import extract_product_code

logger = logging.getLogger(__name__)

styles = getSampleStyleSheet()
style_right = ParagraphStyle(name="right", parent=styles["Normal"], alignment=TA_RIGHT)
style_left = ParagraphStyle(
    name="left", parent=styles["Normal"], alignment=TA_LEFT, leading=12
)
style_center = ParagraphStyle(
    name="center", parent=styles["Normal"], alignment=TA_CENTER, leading=10
)
styles.add(ParagraphStyle(name="Justify", alignment=TA_JUSTIFY))

TERMS = (
    "I hereby declare that this shipment does not contain dangerous goods."
    + " Subject to the Terms and Conditions of contract and the Carrier&rsquo;s Proposal of Rates and Services,"
    + " please accept the goods described above for delivery. WE ARE NOT A COMMON CARRIER."
)


def myFirstPage(canvas, doc):
    canvas.saveState()
    canvas.rotate(180)
    canvas.restoreState()


def myLaterPages(canvas, doc):
    canvas.saveState()
    canvas.rotate(90)
    canvas.restoreState()


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


def buildSenderSection(
    Story, booking, booking_lines, booking_line, dme_img, label_settings, barcode
):
    tbl_data1 = [[dme_img]]

    t1 = Table(
        tbl_data1,
        colWidths=(float(label_settings["label_image_size_length"]) * (1 / 2) * mm),
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
                "<font size=%s>%s</font>"
                % (
                    label_settings["font_size_small"],
                    "Section 1: Detach - This is your copy",
                ),
                style_right,
            )
        ],
        [
            Paragraph(
                "<font size=%s><b>%s</b></font>"
                % (label_settings["font_size_small"], "Customer Service: 1300 556 232"),
                style_right,
            )
        ],
    ]
    t2 = Table(
        tbl_data2,
        colWidths=(float(label_settings["label_image_size_length"]) * (1 / 2) * mm),
        rowHeights=(float(label_settings["line_height_extra_small"]) * mm),
        style=[
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ("VALIGN", (0, 0), (0, -1), "TOP"),
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
            # ('SPAN',(0,0),(0,-1)),
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMBORDER", (0, 0), (-1, -1), 0),
            # ('BOX', (0, 0), (-1, -1), 1, colors.black)
        ],
    )

    Story.append(shell_table)

    sender_table = {
        "label_width": float(label_settings["label_image_size_length"])
        * (1 / 3)
        * (1 / 3),
        "data_width": float(label_settings["label_image_size_length"])
        * (1 / 3)
        * (2 / 3),
    }

    tbl_data1 = [
        [
            Paragraph(
                "<font size=%s>Sender:</font>" % (label_settings["font_size_medium"]),
                style_left,
            ),
            Paragraph(
                "<font size=%s>%s</font>"
                % (
                    label_settings["font_size_medium"],
                    (booking.pu_Contact_F_L_Name)
                    if (booking.pu_Contact_F_L_Name)
                    else "",
                ),
                style_left,
            ),
        ],
        [
            Paragraph(
                "<font size=%s>%s </font>" % (label_settings["font_size_medium"], ""),
                style_left,
            ),
            Paragraph(
                "<font size=%s>%s %s</font>"
                % (
                    label_settings["font_size_medium"],
                    str(booking.pu_Address_Street_1),
                    str(booking.pu_Address_street_2)
                    if booking.pu_Address_street_2
                    else "",
                ),
                style_left,
            ),
        ],
        [
            Paragraph(
                "<font size=%s>  %s</font> " % (label_settings["font_size_medium"], ""),
                style_left,
            ),
        ],
        [
            Paragraph(
                "<font size=%s>%s </font>" % (label_settings["font_size_medium"], ""),
                style_left,
            ),
            Paragraph(
                "<font size=%s>%s %s</font>"
                % (
                    label_settings["font_size_medium"],
                    str(booking.pu_Address_Suburb) if booking.pu_Address_Suburb else "",
                    str(booking.pu_Address_PostalCode)
                    if booking.pu_Address_PostalCode
                    else "",
                ),
                style_left,
            ),
        ],
    ]

    t1 = Table(
        tbl_data1,
        colWidths=(sender_table["label_width"] * mm, sender_table["data_width"] * mm),
        style=[
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ],
    )

    receiver_table = {
        "label_width": float(label_settings["label_image_size_length"])
        * (1 / 2)
        * (1 / 3),
        "data_width": float(label_settings["label_image_size_length"])
        * (1 / 2)
        * (2 / 3),
    }

    tbl_data2 = [
        [
            Paragraph(
                "<font size=%s>Receiver: </font>"
                % (label_settings["font_size_medium"]),
                style_left,
            ),
            Paragraph(
                "<font size=%s><b>%s</b></font>"
                % (
                    label_settings["font_size_extra_large"],
                    booking.de_To_Address_Street_1,
                ),
                style_left,
            ),
        ],
        [
            Paragraph(
                "<font size=%s>%s </font>" % (label_settings["font_size_medium"], ""),
                style_left,
            ),
            Paragraph(
                "<font size=%s><b>%s</b></font>"
                % (
                    label_settings["font_size_extra_large"],
                    str(booking.de_To_Address_Street_2)
                    if booking.de_To_Address_Street_2
                    else "",
                ),
                style_left,
            ),
        ],
        [
            Paragraph(
                "<font size=%s>%s </font>" % (label_settings["font_size_medium"], ""),
                style_left,
            ),
            Paragraph(
                "<font size=%s><b>%s</b></font>"
                % (
                    label_settings["font_size_extra_large"],
                    str(booking.de_To_Address_Street_2)
                    if booking.de_To_Address_Street_2
                    else "",
                ),
                style_left,
            ),
        ],
        [
            Paragraph(
                "<font size=%s>%s </font>" % (label_settings["font_size_medium"], ""),
                style_left,
            ),
            Paragraph(
                "<font size=%s><b>%s %s</b></font>"
                % (
                    label_settings["font_size_extra_large"],
                    str(booking.de_To_Address_Suburb)
                    if booking.de_To_Address_Suburb
                    else "",
                    str(booking.de_To_Address_PostalCode)
                    if booking.de_To_Address_PostalCode
                    else "",
                ),
                style_left,
            ),
        ],
    ]

    t2 = Table(
        tbl_data2,
        colWidths=(
            receiver_table["label_width"] * mm,
            receiver_table["data_width"] * mm,
        ),
        style=[
            ("LEFTPADDING", (0, 1), (0, 1), 5),
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ],
    )

    barcode128 = get_barcode_rotated(
        barcode,
        (float(label_settings["barcode_dimension_length"])) * mm,
        float(label_settings["barcode_dimension_width"]) * mm,
        1,
        float(label_settings["barcode_font_size"]),
        True,
    )

    dme_senderscopy = "./static/assets/logos/hunter_senders_copy.png"
    img_senderscopy = Image(dme_senderscopy, 10 * mm, 65 * mm)
    tbl_data3 = [[""], [img_senderscopy]]
    t3 = Table(
        tbl_data3,
        colWidths=(float(label_settings["label_image_size_length"]) * (1 / 6) * mm),
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
    t1_w = float(label_settings["label_image_size_length"]) * (1 / 3) * mm
    t2_w = float(label_settings["label_image_size_length"]) * (1 / 2) * mm
    t3_w = float(label_settings["label_image_size_length"]) * (1 / 6) * mm

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
    Story.append(Spacer(1, 5))

    tbl_data1 = [
        [
            Paragraph(
                "<font size=%s>Instructions: %s %s</font>"
                % (
                    label_settings["font_size_medium"],
                    str(booking.de_to_PickUp_Instructions_Address)
                    if booking.de_to_PickUp_Instructions_Address
                    else "",
                    str(booking.de_to_Pick_Up_Instructions_Contact)
                    if booking.de_to_Pick_Up_Instructions_Contact
                    else "",
                ),
                style_left,
            )
        ],
    ]

    t1 = Table(
        tbl_data1,
        colWidths=(float(label_settings["label_image_size_length"]) * (1 / 8) * mm),
        style=[
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ],
    )

    tbl_data2 = [
        [
            code128.Code128(
                barcode, barHeight=10 * mm, barWidth=0.7, humanReadable=False
            )
        ],
    ]

    t2 = Table(
        tbl_data2,
        colWidths=(float(label_settings["label_image_size_length"]) * (13 / 18) * mm),
        style=[
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            # ('ALIGN',(0,0),(-1,-1),'CENTER'),
        ],
    )

    t1_w = float(label_settings["label_image_size_length"]) * (1 / 8) * mm
    t2_w = float(label_settings["label_image_size_length"]) * (7 / 8) * mm
    data = [[t1, t2]]
    shell_table = Table(
        data,
        colWidths=[t1_w, t2_w],
        style=[
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ],
    )
    Story.append(shell_table)

    Story.append(Spacer(1, 25))

    tbl_data1 = [
        [
            Paragraph(
                "<font size=%s>Date: </font>" % (label_settings["font_size_medium"]),
                style_left,
            ),
            Paragraph(
                "<font size=%s>%s</font>"
                % (
                    label_settings["font_size_medium"],
                    booking.b_dateBookedDate.strftime("%d/%m/%Y")
                    if booking.b_dateBookedDate
                    else "N/A",
                ),
                style_left,
            ),
        ],
        [
            Paragraph(
                "<font size=%s>Item Description: </font>"
                % (label_settings["font_size_medium"]),
                style_left,
            ),
            Paragraph(
                "<font size=%s>%s</font>"
                % (
                    label_settings["font_size_medium"],
                    booking_line.e_type_of_packaging or "N/A",
                ),
                style_left,
            ),
        ],
        [
            Paragraph(
                "<font size=%s>Item Reference: </font>"
                % (label_settings["font_size_medium"]),
                style_left,
            ),
            Paragraph(
                "<font size=%s>%s</font>"
                % (
                    label_settings["font_size_medium"],
                    extract_product_code(booking_line.e_item),
                ),
                style_left,
            ),
        ],
    ]

    t1 = Table(
        tbl_data1,
        colWidths=(sender_table["label_width"] * mm, sender_table["data_width"] * mm),
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
                "<font size=%s>Consignment Note: </font>"
                % (label_settings["font_size_medium"]),
                style_left,
            ),
            Paragraph(
                "<font size=%s><b>%s</b></font>"
                % (
                    label_settings["font_size_large"],
                    gen_consignment_num(
                        booking.vx_freight_provider, booking.b_bookingID_Visual
                    ),
                ),
                style_left,
            ),
        ],
        [
            Paragraph(
                "<font size=%s>Service:</font>" % (label_settings["font_size_medium"]),
                style_left,
            ),
            Paragraph(
                "<font size=%s><b>%s</b></font>"
                % (
                    label_settings["font_size_large"],
                    booking.vx_serviceName if booking.vx_serviceName else "N/A",
                ),
                style_left,
            ),
        ],
    ]

    t2 = Table(
        tbl_data2,
        colWidths=(
            receiver_table["label_width"] * mm,
            receiver_table["data_width"] * mm,
        ),
        style=[
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ],
    )

    data = [[t1, t2]]

    t1_w = float(label_settings["label_image_size_length"]) * (1 / 3) * mm
    t2_w = float(label_settings["label_image_size_length"]) * (2 / 3) * mm

    shell_table = Table(
        data,
        colWidths=[t1_w, t2_w],
        style=[
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ],
    )

    Story.append(shell_table)

    tbl_data1 = [
        [
            Paragraph(
                "<font size=%s>%s of %s items </font>"
                % (label_settings["font_size_medium"], 0, get_total_qty(booking_lines)),
                style_left,
            ),
            Paragraph(
                "<font size=%s>Total dead weight:    %s kg</font>"
                % (label_settings["font_size_medium"], get_total_weight(booking_lines)),
                style_left,
            ),
        ],
    ]

    t1 = Table(
        tbl_data1,
        colWidths=(sender_table["label_width"] * mm, sender_table["data_width"] * mm),
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
                "<font size=%s>Item dead weight: </font>"
                % (label_settings["font_size_medium"]),
                style_left,
            ),
            Paragraph(
                "<font size=%s>%s kg</font>"
                % (
                    label_settings["font_size_medium"],
                    booking_line.e_Total_KG_weight
                    if booking_line.e_Total_KG_weight
                    else "N/A",
                ),
                style_left,
            ),
        ],
    ]

    item_detail = {
        "label_width": float(label_settings["label_image_size_length"])
        * (1 / 2)
        * (1 / 3),
        "data_width": float(label_settings["label_image_size_length"])
        * (1 / 2)
        * (1 / 4),
    }

    t2 = Table(
        tbl_data2,
        colWidths=(
            receiver_table["label_width"] * mm,
            receiver_table["data_width"] * mm,
        ),
        style=[
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ],
    )

    tbl_data3 = [
        [
            Paragraph(
                "<font size=%s>Item Dimensions: %s x %s x %s</font>"
                % (
                    label_settings["font_size_medium"],
                    float(booking_line.e_dimWidth),
                    float(booking_line.e_dimHeight),
                    float(booking_line.e_dimLength),
                ),
                style_left,
            ),
        ],
        [
            Paragraph(
                "<font size=%s>Charge: %s</font>"
                % (label_settings["font_size_medium"], "DMEELK"),
                style_left,
            ),
        ],
    ]

    t3 = Table(
        tbl_data3,
        colWidths=(sender_table["data_width"] * mm),
        style=[
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ],
    )

    tbl_data4 = [
        [
            Paragraph(
                "<font size=%s></font>" % (label_settings["font_size_medium"]),
                style_left,
            ),
        ]
    ]

    t4 = Table(
        tbl_data4,
        colWidths=(sender_table["data_width"] * mm),
        style=[
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ],
    )

    data = [[t1, t2, t3, t4]]

    t1_w = float(label_settings["label_image_size_length"]) * (1 / 3) * mm
    t2_w = float(label_settings["label_image_size_length"]) * (1 / 4) * mm
    t3_w = float(label_settings["label_image_size_length"]) * (1 / 4) * mm
    t4_w = float(label_settings["label_image_size_length"]) * (1 / 6) * mm

    shell_table = Table(
        data,
        colWidths=[t1_w, t2_w, t3_w, t4_w],
        style=[
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ],
    )

    Story.append(shell_table)

    Story.append(Spacer(1, 25))

    tbl_data1 = [
        [
            Paragraph(
                "<font size=%s>%s</font>" % (label_settings["font_size_small"], TERMS),
                style_left,
            ),
        ],
    ]

    t1_w = float(label_settings["label_image_size_length"]) * mm

    t1 = Table(
        tbl_data1,
        colWidths=(t1_w),
        style=[
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ],
    )

    data = [[t1]]

    shell_table = Table(
        data,
        colWidths=[t1_w],
        style=[
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ],
    )

    Story.append(shell_table)

    Story.append(Spacer(1, 15))

    signature = "&#95; &#95; &#95; &#95; &#95; &#95; &#95; &#95; &#95; &#95; &#95; &#95; &#95; &#95; &#95; &#95; &#95; &#95; &#95; &#95; &#95; &#95; &#95; &#95; &#95; &#95; &#95; &#95; &#95; &#95; &#95; &#95; &#95; &#95; &#95; &#95; &#95; &#95; &#95; &#95; &#95; &#95; &#95; &#95; &#95; &#95; &#95; &#95; &#95; &#95; &#95; &#95; &#95; &#95; &#95; &#95; &#95; &#95; &#95;"
    tbl_data1 = [
        [
            Paragraph(
                "<font size=%s>Sender&rsquo;s Signature: &nbsp;%s</font>"
                % (label_settings["font_size_small"], signature),
                style_left,
            ),
        ],
    ]

    t1_w = float(label_settings["label_image_size_length"]) * mm

    t1 = Table(
        tbl_data1,
        colWidths=(t1_w),
        style=[
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ],
    )

    data = [[t1]]

    shell_table = Table(
        data,
        colWidths=[t1_w],
        style=[
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ],
    )

    Story.append(shell_table)
    return Story


def buildReceiverSection(
    Story, booking, booking_lines, booking_line, dme_img, label_settings, barcode
):
    tbl_data1 = [[dme_img]]
    t1 = Table(
        tbl_data1,
        colWidths=(float(label_settings["label_image_size_length"]) * (1 / 2) * mm),
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
                "<font size=%s>%s</font>"
                % (
                    label_settings["font_size_small"],
                    "Section 2: Detach - Attach to the item",
                ),
                style_right,
            )
        ],
        [
            Paragraph(
                "<font size=%s><b>%s</b></font>"
                % (label_settings["font_size_small"], "Customer Service: 1300 556 232"),
                style_right,
            )
        ],
    ]
    t2 = Table(
        tbl_data2,
        colWidths=(float(label_settings["label_image_size_length"]) * (1 / 2) * mm),
        rowHeights=(float(label_settings["line_height_extra_small"]) * mm),
        style=[
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ("VALIGN", (0, 0), (0, -1), "TOP"),
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
            # ('SPAN',(0,0),(0,-1)),
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMBORDER", (0, 0), (-1, -1), 0),
            # ('BOX', (0, 0), (-1, -1), 1, colors.black)
        ],
    )

    Story.append(shell_table)

    sender_table = {
        "label_width": float(label_settings["label_image_size_length"])
        * (1 / 3)
        * (1 / 3),
        "data_width": float(label_settings["label_image_size_length"])
        * (1 / 3)
        * (2 / 3),
    }

    tbl_data1 = [
        [
            Paragraph(
                "<font size=%s>Sender:</font>" % (label_settings["font_size_medium"]),
                style_left,
            ),
            Paragraph(
                "<font size=%s>%s</font>"
                % (
                    label_settings["font_size_medium"],
                    (booking.pu_Contact_F_L_Name)
                    if (booking.pu_Contact_F_L_Name)
                    else "",
                ),
                style_left,
            ),
        ],
        [
            Paragraph(
                "<font size=%s>%s </font>" % (label_settings["font_size_medium"], ""),
                style_left,
            ),
            Paragraph(
                "<font size=%s>%s %s</font>"
                % (
                    label_settings["font_size_medium"],
                    str(booking.pu_Address_Street_1)
                    if booking.pu_Address_Street_1
                    else "",
                    str(booking.pu_Address_street_2)
                    if booking.pu_Address_street_2
                    else "",
                ),
                style_left,
            ),
        ],
        [
            Paragraph(
                "<font size=%s>  %s</font> " % (label_settings["font_size_medium"], ""),
                style_left,
            ),
        ],
        [
            Paragraph(
                "<font size=%s>%s </font>" % (label_settings["font_size_medium"], ""),
                style_left,
            ),
            Paragraph(
                "<font size=%s>%s %s</font>"
                % (
                    label_settings["font_size_medium"],
                    str(booking.pu_Address_Suburb) if booking.pu_Address_Suburb else "",
                    str(booking.pu_Address_PostalCode)
                    if booking.pu_Address_PostalCode
                    else "",
                ),
                style_left,
            ),
        ],
    ]

    t1 = Table(
        tbl_data1,
        colWidths=(sender_table["label_width"] * mm, sender_table["data_width"] * mm),
        style=[
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ],
    )

    receiver_table = {
        "label_width": float(label_settings["label_image_size_length"])
        * (1 / 2)
        * (1 / 3),
        "data_width": float(label_settings["label_image_size_length"])
        * (1 / 2)
        * (2 / 3),
    }

    tbl_data2 = [
        [
            Paragraph(
                "<font size=%s>Receiver: </font>"
                % (label_settings["font_size_medium"]),
                style_left,
            ),
            Paragraph(
                "<font size=%s><b>%s</b></font>"
                % (
                    label_settings["font_size_extra_large"],
                    booking.de_To_Address_Street_1,
                ),
                style_left,
            ),
        ],
        [
            Paragraph(
                "<font size=%s>%s </font>" % (label_settings["font_size_medium"], ""),
                style_left,
            ),
            Paragraph(
                "<font size=%s><b>%s</b></font>"
                % (
                    label_settings["font_size_extra_large"],
                    str(booking.de_To_Address_Street_2)
                    if booking.de_To_Address_Street_2
                    else "",
                ),
                style_left,
            ),
        ],
        [
            Paragraph(
                "<font size=%s>%s </font>" % (label_settings["font_size_medium"], ""),
                style_left,
            ),
            Paragraph(
                "<font size=%s><b>%s</b></font>"
                % (
                    label_settings["font_size_extra_large"],
                    str(booking.de_To_Address_Street_2)
                    if booking.de_To_Address_Street_2
                    else "",
                ),
                style_left,
            ),
        ],
        [
            Paragraph(
                "<font size=%s>%s </font>" % (label_settings["font_size_medium"], ""),
                style_left,
            ),
            Paragraph(
                "<font size=%s><b>%s %s</b></font>"
                % (
                    label_settings["font_size_extra_large"],
                    str(booking.de_To_Address_Suburb)
                    if booking.de_To_Address_Suburb
                    else "",
                    str(booking.de_To_Address_PostalCode)
                    if booking.de_To_Address_PostalCode
                    else "",
                ),
                style_left,
            ),
        ],
    ]

    t2 = Table(
        tbl_data2,
        colWidths=(
            receiver_table["label_width"] * mm,
            receiver_table["data_width"] * mm,
        ),
        style=[
            ("LEFTPADDING", (0, 1), (0, 1), 5),
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ],
    )

    dme_receiverscopy = "./static/assets/logos/hunter_receivers_copy.png"
    img_receiverscopy = Image(dme_receiverscopy, 10 * mm, 65 * mm)
    tbl_data3 = [
        [""],
        [img_receiverscopy],
    ]

    t3 = Table(
        tbl_data3,
        colWidths=(float(label_settings["label_image_size_length"]) * (1 / 6) * mm),
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
    t1_w = float(label_settings["label_image_size_length"]) * (1 / 3) * mm
    t2_w = float(label_settings["label_image_size_length"]) * (1 / 2) * mm
    t3_w = float(label_settings["label_image_size_length"]) * (1 / 6) * mm

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
    Story.append(Spacer(1, 5))

    tbl_data1 = [
        [
            Paragraph(
                "<font size=%s>Instructions: %s %s</font>"
                % (
                    label_settings["font_size_medium"],
                    str(booking.de_to_PickUp_Instructions_Address)
                    if booking.de_to_PickUp_Instructions_Address
                    else "",
                    str(booking.de_to_Pick_Up_Instructions_Contact)
                    if booking.de_to_Pick_Up_Instructions_Contact
                    else "",
                ),
                style_left,
            )
        ],
    ]

    t1 = Table(
        tbl_data1,
        colWidths=(float(label_settings["label_image_size_length"]) * (1 / 8) * mm),
        style=[
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ],
    )

    tbl_data2 = [
        [
            code128.Code128(
                barcode, barHeight=10 * mm, barWidth=0.7, humanReadable=False
            )
        ],
    ]

    t2 = Table(
        tbl_data2,
        colWidths=(float(label_settings["label_image_size_length"]) * (13 / 18) * mm),
        style=[
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            # ('ALIGN',(0,0),(-1,-1),'CENTER'),
        ],
    )

    t1_w = float(label_settings["label_image_size_length"]) * (1 / 8) * mm
    t2_w = float(label_settings["label_image_size_length"]) * (7 / 8) * mm
    data = [[t1, t2]]
    shell_table = Table(
        data,
        colWidths=[t1_w, t2_w],
        style=[
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ],
    )
    Story.append(shell_table)

    Story.append(Spacer(1, 25))

    tbl_data1 = [
        [
            Paragraph(
                "<font size=%s>Date: </font>" % (label_settings["font_size_medium"]),
                style_left,
            ),
            Paragraph(
                "<font size=%s>%s</font>"
                % (
                    label_settings["font_size_medium"],
                    booking.b_dateBookedDate.strftime("%d/%m/%Y")
                    if booking.b_dateBookedDate
                    else "N/A",
                ),
                style_left,
            ),
        ],
        [
            Paragraph(
                "<font size=%s>Item Description: </font>"
                % (label_settings["font_size_medium"]),
                style_left,
            ),
            Paragraph(
                "<font size=%s>%s</font>"
                % (
                    label_settings["font_size_medium"],
                    booking_line.e_type_of_packaging
                    if booking_line.e_type_of_packaging
                    else "N/A",
                ),
                style_left,
            ),
        ],
        [
            Paragraph(
                "<font size=%s>Item Reference: </font>"
                % (label_settings["font_size_medium"]),
                style_left,
            ),
            Paragraph(
                "<font size=%s>%s</font>"
                % (
                    label_settings["font_size_medium"],
                    extract_product_code(booking_line.e_item),
                ),
                style_left,
            ),
        ],
    ]

    t1 = Table(
        tbl_data1,
        colWidths=(sender_table["label_width"] * mm, sender_table["data_width"] * mm),
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
                "<font size=%s>Consignment Note: </font>"
                % (label_settings["font_size_medium"]),
                style_left,
            ),
            Paragraph(
                "<font size=%s><b>%s</b></font>"
                % (
                    label_settings["font_size_large"],
                    gen_consignment_num(
                        booking.vx_freight_provider, booking.b_bookingID_Visual
                    ),
                ),
                style_left,
            ),
        ],
        [
            Paragraph(
                "<font size=%s>Service:</font>" % (label_settings["font_size_medium"]),
                style_left,
            ),
            Paragraph(
                "<font size=%s><b>%s</b></font>"
                % (
                    label_settings["font_size_large"],
                    booking.vx_serviceName if booking.vx_serviceName else "N/A",
                ),
                style_left,
            ),
        ],
    ]

    t2 = Table(
        tbl_data2,
        colWidths=(
            receiver_table["label_width"] * mm,
            receiver_table["data_width"] * mm,
        ),
        style=[
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ],
    )

    data = [[t1, t2]]

    t1_w = float(label_settings["label_image_size_length"]) * (1 / 3) * mm
    t2_w = float(label_settings["label_image_size_length"]) * (2 / 3) * mm

    shell_table = Table(
        data,
        colWidths=[t1_w, t2_w],
        style=[
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ],
    )

    Story.append(shell_table)

    tbl_data1 = [
        [
            Paragraph(
                "<font size=%s>%s of %s items </font>"
                % (label_settings["font_size_medium"], 0, get_total_qty(booking_lines)),
                style_left,
            ),
            Paragraph(
                "<font size=%s>Total dead weight:    %s kg</font>"
                % (label_settings["font_size_medium"], get_total_weight(booking_lines)),
                style_left,
            ),
        ],
    ]

    t1 = Table(
        tbl_data1,
        colWidths=(sender_table["label_width"] * mm, sender_table["data_width"] * mm),
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
                "<font size=%s>Item dead weight: </font>"
                % (label_settings["font_size_medium"]),
                style_left,
            ),
            Paragraph(
                "<font size=%s>%s kg</font>"
                % (
                    label_settings["font_size_medium"],
                    booking_line.e_Total_KG_weight
                    if booking_line.e_Total_KG_weight
                    else "N/A",
                ),
                style_left,
            ),
        ],
    ]

    item_detail = {
        "label_width": float(label_settings["label_image_size_length"])
        * (1 / 2)
        * (1 / 3),
        "data_width": float(label_settings["label_image_size_length"])
        * (1 / 2)
        * (1 / 4),
    }

    t2 = Table(
        tbl_data2,
        colWidths=(
            receiver_table["label_width"] * mm,
            receiver_table["data_width"] * mm,
        ),
        style=[
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ],
    )

    tbl_data3 = [
        [
            Paragraph(
                "<font size=%s>Item Dimensions: %s x %s x %s</font>"
                % (
                    label_settings["font_size_medium"],
                    float(booking_line.e_dimWidth),
                    float(booking_line.e_dimHeight),
                    float(booking_line.e_dimLength),
                ),
                style_left,
            ),
        ],
        [
            Paragraph(
                "<font size=%s>Charge: %s</font>"
                % (label_settings["font_size_medium"], "DMEELK"),
                style_left,
            ),
        ],
    ]

    t3 = Table(
        tbl_data3,
        colWidths=(sender_table["data_width"] * mm),
        style=[
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ],
    )

    tbl_data4 = [
        [
            Paragraph(
                "<font size=%s></font>" % (label_settings["font_size_medium"]),
                style_left,
            ),
        ]
    ]

    t4 = Table(
        tbl_data4,
        colWidths=(sender_table["data_width"] * mm),
        style=[
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ],
    )

    data = [[t1, t2, t3, t4]]

    t1_w = float(label_settings["label_image_size_length"]) * (1 / 3) * mm
    t2_w = float(label_settings["label_image_size_length"]) * (1 / 4) * mm
    t3_w = float(label_settings["label_image_size_length"]) * (1 / 4) * mm
    t4_w = float(label_settings["label_image_size_length"]) * (1 / 6) * mm

    shell_table = Table(
        data,
        colWidths=[t1_w, t2_w, t3_w, t4_w],
        style=[
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ],
    )

    Story.append(shell_table)

    Story.append(Spacer(1, 25))

    tbl_data1 = [
        [
            Paragraph(
                "<font size=%s>%s</font>" % (label_settings["font_size_small"], TERMS),
                style_left,
            ),
        ],
    ]

    t1_w = float(label_settings["label_image_size_length"]) * mm

    t1 = Table(
        tbl_data1,
        colWidths=(t1_w),
        style=[
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ],
    )

    data = [[t1]]

    shell_table = Table(
        data,
        colWidths=[t1_w],
        style=[
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ],
    )

    Story.append(shell_table)

    Story.append(Spacer(1, 15))

    signature = "&#95; &#95; &#95; &#95; &#95; &#95; &#95; &#95; &#95; &#95; &#95; &#95; &#95; &#95; &#95; &#95; &#95; &#95; &#95; &#95; &#95; &#95; &#95; &#95; &#95; &#95; &#95; &#95; &#95; &#95; &#95; &#95; &#95; &#95; &#95; &#95; &#95; &#95; &#95; &#95; &#95; &#95; &#95; &#95; &#95; &#95; &#95; &#95; &#95; &#95; &#95; &#95; &#95; &#95; &#95; &#95; &#95; &#95; &#95;"
    tbl_data1 = [
        [
            Paragraph(
                "<font size=%s>Sender&rsquo;s Signature: &nbsp;%s</font>"
                % (label_settings["font_size_small"], signature),
                style_left,
            ),
        ],
    ]

    t1_w = float(label_settings["label_image_size_length"]) * mm

    t1 = Table(
        tbl_data1,
        colWidths=(t1_w),
        style=[
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ],
    )

    data = [[t1]]

    shell_table = Table(
        data,
        colWidths=[t1_w],
        style=[
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ],
    )

    Story.append(shell_table)
    return Story


def buildPodSection(
    Story, booking, booking_lines, booking_line, dme_img, label_settings, barcode
):
    tbl_data1 = [
        [
            Paragraph(
                "<font size=%s><b>%s</b></font>"
                % (label_settings["font_size_extra_large"], "PROOF OF DELIVERY COPY"),
                style_center,
            ),
        ],
        [],
        [
            Paragraph(
                "<font size=%s><b>%s</b></font>"
                % (
                    label_settings["font_size_small"],
                    "Leave this section loose. Do not tape or glue down. The delivery driver will use to obtain a signature from the receiver.",
                ),
                style_center,
            ),
        ],
    ]

    t1_w = float(label_settings["label_image_size_length"]) * mm

    t1 = Table(
        tbl_data1,
        colWidths=(t1_w),
        style=[
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ],
    )

    data = [[t1]]

    shell_table = Table(
        data,
        colWidths=[t1_w],
        style=[
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ],
    )

    Story.append(Spacer(1, 10))
    Story.append(shell_table)

    tbl_data1 = [[dme_img]]

    t1 = Table(
        tbl_data1,
        colWidths=(float(label_settings["label_image_size_length"]) * (1 / 2) * mm),
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
                "<font size=%s>%s</font>"
                % (label_settings["font_size_small"], "Section 3"),
                style_right,
            )
        ],
        [
            Paragraph(
                "<font size=%s><b>%s</b></font>"
                % (label_settings["font_size_small"], "Customer Service: 1300 556 232"),
                style_right,
            )
        ],
    ]
    t2 = Table(
        tbl_data2,
        colWidths=(float(label_settings["label_image_size_length"]) * (1 / 2) * mm),
        rowHeights=(float(label_settings["line_height_extra_small"]) * mm),
        style=[
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ("VALIGN", (0, 0), (0, -1), "TOP"),
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
            # ('SPAN',(0,0),(0,-1)),
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMBORDER", (0, 0), (-1, -1), 0),
            # ('BOX', (0, 0), (-1, -1), 1, colors.black)
        ],
    )

    Story.append(shell_table)

    sender_table = {
        "label_width": float(label_settings["label_image_size_length"])
        * (1 / 3)
        * (1 / 3),
        "data_width": float(label_settings["label_image_size_length"])
        * (1 / 3)
        * (2 / 3),
    }

    tbl_data1 = [
        [
            Paragraph(
                "<font size=%s>Sender:</font>" % (label_settings["font_size_medium"]),
                style_left,
            ),
            Paragraph(
                "<font size=%s>%s</font>"
                % (
                    label_settings["font_size_medium"],
                    (booking.pu_Contact_F_L_Name)
                    if (booking.pu_Contact_F_L_Name)
                    else "",
                ),
                style_left,
            ),
        ],
        [
            Paragraph(
                "<font size=%s>%s </font>" % (label_settings["font_size_medium"], ""),
                style_left,
            ),
            Paragraph(
                "<font size=%s>%s %s</font>"
                % (
                    label_settings["font_size_medium"],
                    str(booking.pu_Address_Street_1)
                    if booking.pu_Address_Street_1
                    else "",
                    str(booking.pu_Address_street_2)
                    if booking.pu_Address_street_2
                    else "",
                ),
                style_left,
            ),
        ],
        [
            Paragraph(
                "<font size=%s>  %s</font> " % (label_settings["font_size_medium"], ""),
                style_left,
            ),
        ],
        [
            Paragraph(
                "<font size=%s>%s </font>" % (label_settings["font_size_medium"], ""),
                style_left,
            ),
            Paragraph(
                "<font size=%s>%s %s</font>"
                % (
                    label_settings["font_size_medium"],
                    str(booking.pu_Address_Suburb) if booking.pu_Address_Suburb else "",
                    str(booking.pu_Address_PostalCode)
                    if booking.pu_Address_PostalCode
                    else "",
                ),
                style_left,
            ),
        ],
    ]

    t1 = Table(
        tbl_data1,
        colWidths=(sender_table["label_width"] * mm, sender_table["data_width"] * mm),
        style=[
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ],
    )

    receiver_table = {
        "label_width": float(label_settings["label_image_size_length"])
        * (1 / 2)
        * (1 / 3),
        "data_width": float(label_settings["label_image_size_length"])
        * (1 / 2)
        * (2 / 3),
    }

    tbl_data2 = [
        [
            Paragraph(
                "<font size=%s>Receiver: </font>"
                % (label_settings["font_size_medium"]),
                style_left,
            ),
            Paragraph(
                "<font size=%s><b>%s</b></font>"
                % (
                    label_settings["font_size_extra_large"],
                    booking.de_To_Address_Street_1,
                ),
                style_left,
            ),
        ],
        [
            Paragraph(
                "<font size=%s>%s </font>" % (label_settings["font_size_medium"], ""),
                style_left,
            ),
            Paragraph(
                "<font size=%s><b>%s</b></font>"
                % (
                    label_settings["font_size_extra_large"],
                    str(booking.de_To_Address_Street_2)
                    if booking.de_To_Address_Street_2
                    else "",
                ),
                style_left,
            ),
        ],
        [
            Paragraph(
                "<font size=%s>%s </font>" % (label_settings["font_size_medium"], ""),
                style_left,
            ),
            Paragraph(
                "<font size=%s><b>%s</b></font>"
                % (
                    label_settings["font_size_extra_large"],
                    str(booking.de_To_Address_Street_2)
                    if booking.de_To_Address_Street_2
                    else "",
                ),
                style_left,
            ),
        ],
        [
            Paragraph(
                "<font size=%s>%s </font>" % (label_settings["font_size_medium"], ""),
                style_left,
            ),
            Paragraph(
                "<font size=%s><b>%s %s</b></font>"
                % (
                    label_settings["font_size_extra_large"],
                    str(booking.de_To_Address_Suburb)
                    if booking.de_To_Address_Suburb
                    else "",
                    str(booking.de_To_Address_PostalCode)
                    if booking.de_To_Address_PostalCode
                    else "",
                ),
                style_left,
            ),
        ],
    ]

    t2 = Table(
        tbl_data2,
        colWidths=(
            receiver_table["label_width"] * mm,
            receiver_table["data_width"] * mm,
        ),
        style=[
            ("LEFTPADDING", (0, 1), (0, 1), 5),
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ],
    )

    tbl_data3 = [
        [""],
    ]
    t3 = Table(
        tbl_data3,
        colWidths=(float(label_settings["label_image_size_length"]) * (1 / 6) * mm),
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
    t1_w = float(label_settings["label_image_size_length"]) * (1 / 3) * mm
    t2_w = float(label_settings["label_image_size_length"]) * (1 / 2) * mm
    t3_w = float(label_settings["label_image_size_length"]) * (1 / 6) * mm

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
    Story.append(Spacer(1, 5))

    tbl_data1 = [
        [
            Paragraph(
                "<font size=%s>Instructions: %s %s</font>"
                % (
                    label_settings["font_size_medium"],
                    str(booking.de_to_PickUp_Instructions_Address)
                    if booking.de_to_PickUp_Instructions_Address
                    else "",
                    str(booking.de_to_Pick_Up_Instructions_Contact)
                    if booking.de_to_Pick_Up_Instructions_Contact
                    else "",
                ),
                style_left,
            )
        ],
    ]

    t1 = Table(
        tbl_data1,
        colWidths=(float(label_settings["label_image_size_length"]) * (1 / 8) * mm),
        style=[
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ],
    )

    tbl_data2 = [
        [
            code128.Code128(
                barcode, barHeight=10 * mm, barWidth=0.7, humanReadable=False
            )
        ],
    ]

    t2 = Table(
        tbl_data2,
        colWidths=(float(label_settings["label_image_size_length"]) * (13 / 18) * mm),
        style=[
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            # ('ALIGN',(0,0),(-1,-1),'CENTER'),
        ],
    )

    t1_w = float(label_settings["label_image_size_length"]) * (1 / 8) * mm
    t2_w = float(label_settings["label_image_size_length"]) * (7 / 8) * mm
    data = [[t1, t2]]
    shell_table = Table(
        data,
        colWidths=[t1_w, t2_w],
        style=[
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ],
    )
    Story.append(shell_table)

    Story.append(Spacer(1, 25))

    tbl_data1 = [
        [
            Paragraph(
                "<font size=%s>Date: </font>" % (label_settings["font_size_medium"]),
                style_left,
            ),
            Paragraph(
                "<font size=%s>%s</font>"
                % (
                    label_settings["font_size_medium"],
                    booking.b_dateBookedDate.strftime("%d/%m/%Y")
                    if booking.b_dateBookedDate
                    else "N/A",
                ),
                style_left,
            ),
        ],
        [
            Paragraph(
                "<font size=%s>Item Description: </font>"
                % (label_settings["font_size_medium"]),
                style_left,
            ),
            Paragraph(
                "<font size=%s>%s</font>"
                % (
                    label_settings["font_size_medium"],
                    booking_line.e_type_of_packaging
                    if booking_line.e_type_of_packaging
                    else "N/A",
                ),
                style_left,
            ),
        ],
        [
            Paragraph(
                "<font size=%s>Item Reference: </font>"
                % (label_settings["font_size_medium"]),
                style_left,
            ),
            Paragraph(
                "<font size=%s>%s</font>"
                % (
                    label_settings["font_size_medium"],
                    extract_product_code(booking_line.e_item),
                ),
                style_left,
            ),
        ],
    ]

    t1 = Table(
        tbl_data1,
        colWidths=(sender_table["label_width"] * mm, sender_table["data_width"] * mm),
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
                "<font size=%s>Consignment Note: </font>"
                % (label_settings["font_size_medium"]),
                style_left,
            ),
            Paragraph(
                "<font size=%s><b>%s</b></font>"
                % (
                    label_settings["font_size_large"],
                    gen_consignment_num(
                        booking.vx_freight_provider, booking.b_bookingID_Visual
                    ),
                ),
                style_left,
            ),
        ],
        [
            Paragraph(
                "<font size=%s>Service:</font>" % (label_settings["font_size_medium"]),
                style_left,
            ),
            Paragraph(
                "<font size=%s><b>%s</b></font>"
                % (
                    label_settings["font_size_large"],
                    booking.vx_serviceName if booking.vx_serviceName else "N/A",
                ),
                style_left,
            ),
        ],
    ]

    t2 = Table(
        tbl_data2,
        colWidths=(
            receiver_table["label_width"] * mm,
            receiver_table["data_width"] * mm,
        ),
        style=[
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ],
    )

    data = [[t1, t2]]

    t1_w = float(label_settings["label_image_size_length"]) * (1 / 3) * mm
    t2_w = float(label_settings["label_image_size_length"]) * (2 / 3) * mm

    shell_table = Table(
        data,
        colWidths=[t1_w, t2_w],
        style=[
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ],
    )

    Story.append(shell_table)

    tbl_data1 = [
        [
            Paragraph(
                "<font size=%s>%s of %s items </font>"
                % (label_settings["font_size_medium"], 0, get_total_qty(booking_lines)),
                style_left,
            ),
            Paragraph(
                "<font size=%s>Total dead weight:    %s kg</font>"
                % (label_settings["font_size_medium"], get_total_weight(booking_lines)),
                style_left,
            ),
        ],
    ]

    t1 = Table(
        tbl_data1,
        colWidths=(sender_table["label_width"] * mm, sender_table["data_width"] * mm),
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
                "<font size=%s>Item dead weight: </font>"
                % (label_settings["font_size_medium"]),
                style_left,
            ),
            Paragraph(
                "<font size=%s>%s kg</font>"
                % (
                    label_settings["font_size_medium"],
                    booking_line.e_Total_KG_weight
                    if booking_line.e_Total_KG_weight
                    else "N/A",
                ),
                style_left,
            ),
        ],
    ]

    item_detail = {
        "label_width": float(label_settings["label_image_size_length"])
        * (1 / 2)
        * (1 / 3),
        "data_width": float(label_settings["label_image_size_length"])
        * (1 / 2)
        * (1 / 4),
    }

    t2 = Table(
        tbl_data2,
        colWidths=(
            receiver_table["label_width"] * mm,
            receiver_table["data_width"] * mm,
        ),
        style=[
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ],
    )

    tbl_data3 = [
        [
            Paragraph(
                "<font size=%s>Item Dimensions: %s x %s x %s</font>"
                % (
                    label_settings["font_size_medium"],
                    float(booking_line.e_dimWidth),
                    float(booking_line.e_dimHeight),
                    float(booking_line.e_dimLength),
                ),
                style_left,
            ),
        ]
    ]

    t3 = Table(
        tbl_data3,
        colWidths=(sender_table["data_width"] * mm),
        style=[
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ],
    )

    tbl_data4 = [
        [
            Paragraph(
                "<font size=%s></font>" % (label_settings["font_size_medium"]),
                style_left,
            ),
        ]
    ]

    t4 = Table(
        tbl_data4,
        colWidths=(sender_table["data_width"] * mm),
        style=[
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ],
    )

    data = [[t1, t2, t3, t4]]

    t1_w = float(label_settings["label_image_size_length"]) * (1 / 3) * mm
    t2_w = float(label_settings["label_image_size_length"]) * (1 / 4) * mm
    t3_w = float(label_settings["label_image_size_length"]) * (1 / 4) * mm
    t4_w = float(label_settings["label_image_size_length"]) * (1 / 6) * mm

    shell_table = Table(
        data,
        colWidths=[t1_w, t2_w, t3_w, t4_w],
        style=[
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ],
    )

    Story.append(shell_table)

    Story.append(Spacer(1, 25))

    tbl_data1 = [
        [
            Paragraph(
                "<font size=%s><b>%s</b></font>"
                % (
                    label_settings["font_size_small"],
                    "Items Received in Good Order and Condition:",
                ),
                style_left,
            ),
        ],
    ]

    t1_w = float(label_settings["label_image_size_length"]) * mm

    t1 = Table(
        tbl_data1,
        colWidths=(t1_w),
        style=[
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ],
    )

    data = [[t1]]

    shell_table = Table(
        data,
        colWidths=[t1_w],
        style=[
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ],
    )

    Story.append(shell_table)

    Story.append(Spacer(1, 15))

    signature = "&#95; &#95; &#95; &#95; &#95; &#95; &#95; &#95; &#95; &#95; &#95; &#95; &#95; &#95; &#95; &#95; &#95; &#95; &#95; &#95; &#95; &#95; &#95; &#95; &#95; &#95; &#95; &#95; &#95; &#95; &#95; &#95; &#95; &#95; &#95;"
    tbl_data1 = [
        [
            Paragraph(
                "<font size=%s>&nbsp;%s</font>"
                % (label_settings["font_size_small"], signature),
                style_left,
            ),
        ],
        [
            Paragraph(
                "<font size=%s>(Please Print Surname)</font>"
                % (label_settings["font_size_small"]),
                style_center,
            ),
        ],
    ]

    t1 = Table(
        tbl_data1,
        colWidths=(float(label_settings["label_image_size_length"]) * (1 / 3) * mm),
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
                "<font size=%s>&nbsp;%s</font>"
                % (label_settings["font_size_small"], signature),
                style_left,
            ),
        ],
        [
            Paragraph(
                "<font size=%s>(Receiver&rsquo;s Signature)</font>"
                % (label_settings["font_size_small"]),
                style_center,
            ),
        ],
    ]

    t2 = Table(
        tbl_data2,
        colWidths=(float(label_settings["label_image_size_length"]) * (1 / 3) * mm),
        style=[
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ],
    )

    tbl_data3 = [
        [
            Paragraph(
                "<font size=%s>&nbsp;%s</font>"
                % (label_settings["font_size_small"], signature),
                style_left,
            ),
        ],
        [
            Paragraph(
                "<font size=%s>(Date and Time)</font>"
                % (label_settings["font_size_small"]),
                style_center,
            ),
        ],
    ]

    t3 = Table(
        tbl_data3,
        colWidths=(float(label_settings["label_image_size_length"]) * (1 / 3) * mm),
        style=[
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ],
    )

    data = [[t1, t2, t3]]

    t1_w = float(label_settings["label_image_size_length"]) * (1 / 3) * mm
    t2_w = float(label_settings["label_image_size_length"]) * (1 / 3) * mm
    t3_w = float(label_settings["label_image_size_length"]) * (1 / 3) * mm

    shell_table = Table(
        data,
        colWidths=[t1_w, t2_w, t3_w],
        style=[
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ],
    )

    Story.append(shell_table)

    tbl_data1 = [
        [
            Paragraph(
                "<font size=%s>%s</font>"
                % (label_settings["font_size_small"], "WE ARE NOT A COMMON CARRIER"),
                style_center,
            ),
        ],
    ]

    t1_w = float(label_settings["label_image_size_length"]) * mm

    t1 = Table(
        tbl_data1,
        colWidths=(t1_w),
        style=[
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ],
    )

    data = [[t1]]

    shell_table = Table(
        data,
        colWidths=[t1_w],
        style=[
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ],
    )

    Story.append(Spacer(1, 15))
    Story.append(shell_table)

    return Story


def get_total_qty(lines):
    _total_qty = 0

    for booking_line in lines:
        _total_qty += booking_line.e_qty

    return _total_qty


def get_total_weight(lines):
    _total_weight = 0

    for booking_line in lines:
        _total_weight += booking_line.e_Total_KG_weight

    return _total_weight


def gen_barcode(booking, booking_lines, line_index, sscc_cnt):
    consignment_num = gen_consignment_num(
        booking.vx_freight_provider, booking.b_bookingID_Visual, booking.kf_client_id
    )
    item_index = str(line_index).zfill(3)
    items_count = str(sscc_cnt).zfill(3)
    postal_code = booking.de_To_Address_PostalCode

    label_code = f"{consignment_num}{item_index}"
    api_bcl.create(booking, [{"label_code": label_code}])

    return f"{consignment_num}{item_index}{items_count}{postal_code}"


def build_label(booking, filepath=None, lines=[], label_index=0):
    logger.info(
        f"#110 [HUNTER LABEL] Started building label... (Booking ID: {booking.b_bookingID_Visual}, Lines: {lines})"
    )

    # start pdf file name using naming convention
    if lines:
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
            + gen_consignment_num(
                booking.vx_freight_provider, booking.b_bookingID_Visual
            )
            + "_"
            + str(booking.b_bookingID_Visual)
            + ".pdf"
        )

    file = open(f"{filepath}/{filename}", "w")
    # end pdf file name using naming convention

    if not lines:
        lines = Booking_lines.objects.filter(fk_booking_id=booking.pk_booking_id)

    # start check if pdfs folder exists
    if not os.path.exists(filepath):
        os.makedirs(filepath)
    # end check if pdfs folder exists

    # label_settings = get_label_settings( 146, 104 )[0]
    label_settings = {
        "font_family": "Verdana",
        "font_size_extra_small": "5",
        "font_size_small": "7.5",
        "font_size_medium": "9",
        "font_size_large": "11",
        "font_size_extra_large": "13",
        "label_dimension_length": "250",
        "label_dimension_width": "330",
        "label_image_size_length": "240",
        "label_image_size_width": "320",
        "barcode_dimension_length": "65",
        "barcode_dimension_width": "30",
        "barcode_font_size": "18",
        "line_height_extra_small": "3",
        "line_height_small": "5",
        "line_height_medium": "6",
        "line_height_large": "8",
    }

    doc = SimpleDocTemplate(
        f"{filepath}/{filename}",
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

    dme_logo = "./static/assets/logos/dme.png"
    dme_img = Image(dme_logo, 30 * mm, 8 * mm)
    Story = []
    line_index = 0

    for line in lines:
        for j in range(line.e_qty):
            barcode = gen_barcode(booking, lines, j, sscc_cnt)
            buildSenderSection(
                Story, booking, lines, line, dme_img, label_settings, barcode
            )
            Story.append(Spacer(1, 15))
            hr = HRFlowable(
                width=(float(label_settings["label_image_size_length"]) * mm),
                thickness=1,
                lineCap="square",
                color=colors.black,
                spaceBefore=1,
                spaceAfter=1,
                vAlign="BOTTOM",
                dash=None,
            )
            Story.append(hr)
            Story.append(Spacer(1, 5))
            buildReceiverSection(
                Story, booking, lines, line, dme_img, label_settings, barcode
            )
            Story.append(hr)
            Story.append(Spacer(1, 5))
            buildPodSection(
                Story, booking, lines, line, dme_img, label_settings, barcode
            )
            Story.append(PageBreak())

            line_index += 1

    doc.build(Story, onFirstPage=myFirstPage, onLaterPages=myLaterPages)
    file.close()

    logger.info(
        f"#119 [HUNTER LABEL] Finished building label... (Booking ID: {booking.b_bookingID_Visual})"
    )
    return filepath, filename
