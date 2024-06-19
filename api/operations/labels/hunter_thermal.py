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

from api.models import Booking_lines, API_booking_quotes, FPRouting
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

style_border = ParagraphStyle(
    name="center",
    parent=styles["Normal"],
    alignment=TA_CENTER,
    leading=14,
    borderWidth=1,
    borderColor="black",
)


def myFirstPage(canvas, doc):
    canvas.saveState()
    canvas.rotate(180)
    canvas.restoreState()


def myLaterPages(canvas, doc):
    canvas.saveState()
    canvas.rotate(90)
    canvas.restoreState()


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


def build_label(
    booking, filepath, lines, label_index, sscc, sscc_cnt=1, one_page_label=True
):
    v_FPBookingNumber = gen_consignment_num(
        booking.vx_freight_provider, booking.b_bookingID_Visual
    )

    logger.info(
        f"#110 [HUNTER THERMAL LABEL] Started building label... (Booking ID: {booking.b_bookingID_Visual}, Lines: {lines}, Con: {v_FPBookingNumber})"
    )

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
    logger.info(f"#111 [HUNTER THERMAL LABEL] File full path: {filepath}/{filename}")
    # end pdf file name using naming convention

    if not lines:
        lines = Booking_lines.objects.filter(fk_booking_id=booking.pk_booking_id)

    label_settings = {
        "font_family": "Verdana",
        "font_size_extra_small": "5",
        "font_size_small": "7.5",
        "font_size_medium": "9",
        "font_size_large": "11",
        "font_size_extra_large": "13",
        "label_dimension_length": "160",
        "label_dimension_width": "110",
        "label_image_size_length": "150",
        "label_image_size_width": "102",
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
        topMargin=float(
            float(label_settings["label_dimension_width"])
            - float(label_settings["label_image_size_width"])
        )
        * mm,
        bottomMargin=float(
            float(label_settings["label_dimension_width"])
            - float(label_settings["label_image_size_width"])
        )
        * mm,
        rightMargin=float(
            float(label_settings["label_dimension_length"])
            - float(label_settings["label_image_size_length"])
        )
        * mm,
        leftMargin=float(
            float(label_settings["label_dimension_length"])
            - float(label_settings["label_image_size_length"])
        )
        * mm,
    )
    document = []

    Story = []
    j = 1

    totalQty = 0
    if one_page_label:
        lines = [lines[0]]
        totalQty = 1
    else:
        for booking_line in lines:
            totalQty = totalQty + booking_line.e_qty

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

            logger.info(f"#114 [HUNTER THERMAL LABEL] Adding: {line}")

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

            Story.append(hr)
            Story.append(Spacer(1, 2))
            tbl_data1 = [
                [
                    Paragraph(
                        "<font size=%s>To: %s</font>"
                        % (
                            label_settings["font_size_large"],
                            booking.deToCompanyName or "",
                        ),
                        style_left,
                    )
                ],
                [
                    Paragraph(
                        "<font size=%s>%s</font>"
                        % (
                            label_settings["font_size_large"],
                            booking.de_To_Address_Street_1 or "",
                        ),
                        style_left,
                    ),
                ],
                [
                    Paragraph(
                        "<font size=%s><b>%s</b></font> "
                        % (
                            label_settings["font_size_medium"],
                            booking.de_To_Address_Street_2 or "",
                        ),
                        style_left,
                    ),
                ],
                [
                    Paragraph(
                        "<font size=%s><b>%s %s %s</b></font> "
                        % (
                            label_settings["font_size_medium"],
                            booking.de_To_Address_Suburb or "",
                            booking.de_To_Address_State or "",
                            booking.de_To_Address_PostalCode or "",
                        ),
                        style_left,
                    ),
                ],
                [
                    Paragraph(
                        "<font size=%s>%s %s</font>"
                        % (
                            label_settings["font_size_medium"],
                            booking.de_to_Phone_Main or "",
                            booking.de_to_Contact_F_LName or "",
                        ),
                        style_left,
                    )
                ],
                [
                    Paragraph(
                        "<font size=%s>%s %s</font>"
                        % (
                            label_settings["font_size_medium"],
                            "Ref:",
                            line.sscc if line.sscc else "",
                        ),
                        style_left,
                    )
                ],
                [
                    Paragraph(
                        "<font size=%s>%s %s</font>"
                        % (
                            label_settings["font_size_medium"],
                            "Item Ref:",
                            extract_product_code(line.e_item),
                        ),
                        style_left,
                    )
                ],
                [
                    Paragraph(
                        "<font size=%s>%s %s<br/></font>"
                        % (
                            label_settings["font_size_large"],
                            "CONSIGNMENT:",
                            v_FPBookingNumber,
                        ),
                        style_left,
                    )
                ],
            ]

            t1 = Table(
                tbl_data1,
                colWidths=(
                    float(label_settings["label_image_size_length"]) * (2 / 3) * mm
                ),
                style=[
                    ("TOPPADDING", (0, 0), (-1, -1), 0),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                ],
            )

            try:
                account_code = API_booking_quotes.objects.get(
                    id=booking.api_booking_quote_id
                ).account_code
            except Exception as e:
                account_code = ""

            de_suburb = booking.de_To_Address_Suburb
            de_postcode = booking.de_To_Address_PostalCode
            de_state = booking.de_To_Address_State
            head_port = ""
            port_code = ""

            fp_routing = FPRouting.objects.filter(
                freight_provider=13,
                dest_suburb=de_suburb,
                dest_postcode=de_postcode,
                dest_state=de_state,
            )
            if fp_routing:
                head_port = fp_routing[0].orig_depot
                port_code = fp_routing[0].gateway

            tbl_data2 = [
                [
                    Paragraph(
                        "<font size=%s><b>%s</b></font>"
                        % (label_settings["font_size_large"], head_port),
                        style_border,
                    )
                ],
                [
                    Paragraph(
                        "<font size=%s><b>%s</b></font>"
                        % (label_settings["font_size_large"], port_code),
                        style_border,
                    )
                ],
                [
                    Paragraph(
                        "<font size=%s>%s</font>"
                        % (label_settings["font_size_medium"], "Print:"),
                        style_left,
                    )
                ],
                [hr],
                [
                    Paragraph(
                        "<font size=%s>%s</font>"
                        % (label_settings["font_size_medium"], "Signature:"),
                        style_left,
                    )
                ],
                [hr],
                [
                    Paragraph(
                        "<font size=%s>%s</font>"
                        % (label_settings["font_size_medium"], "Date/Time:"),
                        style_left,
                    )
                ],
                [hr],
                [
                    Paragraph(
                        "<font size=%s>%s %s</font>"
                        % (
                            label_settings["font_size_medium"],
                            "Account:",
                            account_code,
                        ),
                        style_center,
                    )
                ],
                [
                    Paragraph(
                        "<font size=%s>Item %s/%s Weight %s %s</font>"
                        % (
                            label_settings["font_size_medium"],
                            j,
                            totalQty,
                            line.e_Total_KG_weight or "",
                            line.e_weightUOM or "",
                        ),
                        style_center,
                    )
                ],
                [
                    Paragraph(
                        "<font size=%s><b>%s</b><br/></font>"
                        % (
                            label_settings["font_size_medium"],
                            "Road Express",
                        ),
                        style_center,
                    )
                ],
            ]

            t2 = Table(
                tbl_data2,
                colWidths=(
                    float(label_settings["label_image_size_length"]) * (1 / 3) * mm
                ),
                style=[
                    ("TOPPADDING", (0, 0), (-1, -1), 0),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                ],
            )

            data = [[t1, t2]]

            t1_w = float(label_settings["label_image_size_length"]) * (2 / 3) * mm
            t2_w = float(label_settings["label_image_size_length"]) * (1 / 3) * mm

            shell_table = Table(
                data,
                colWidths=[t1_w, t2_w],
                style=[
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("SPAN", (0, 0), (0, -1)),
                    ("TOPPADDING", (0, 0), (-1, -1), 0),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                    # ('LEFTPADDING',(0,0),(-1,-1), 0),
                    # ('RIGHTPADDING',(0,0),(-1,-1), 0),
                    ("BOX", (0, 0), (1, -1), 1, colors.black),
                ],
            )

            Story.append(shell_table)

            barcode = gen_barcode(booking, lines, j, sscc_cnt)

            tbl_data = [
                [
                    code128.Code128(
                        barcode, barHeight=15 * mm, barWidth=2.2, humanReadable=False
                    )
                ],
            ]

            t1 = Table(
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

            Story.append(t1)

            human_readable = [
                [
                    Paragraph(
                        "<font size=%s>%s</font>"
                        % (label_settings["font_size_medium"], barcode),
                        style_center,
                    )
                ],
            ]

            t1 = Table(
                human_readable,
                colWidths=(float(label_settings["label_image_size_length"]) * mm),
                style=[
                    ("TOPPADDING", (0, 0), (-1, -1), 0),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                ],
            )

            Story.append(t1)
            Story.append(Spacer(1, 5))

            tbl_data1 = [
                [
                    Paragraph(
                        "<font size=%s>%s %s</font>"
                        % (
                            label_settings["font_size_medium"],
                            "FROM:",
                            booking.puCompany or "",
                        ),
                        style_left,
                    )
                ],
                [
                    Paragraph(
                        "<font size=%s>%s</font>"
                        % (
                            label_settings["font_size_medium"],
                            booking.pu_Address_Street_1 or "",
                        ),
                        style_left,
                    ),
                ],
                [
                    Paragraph(
                        "<font size=%s>%s</font> "
                        % (
                            label_settings["font_size_medium"],
                            booking.pu_Address_street_2 or "",
                        ),
                        style_left,
                    ),
                ],
                [
                    Paragraph(
                        "<font size=%s><b>%s %s %s</b></font> "
                        % (
                            label_settings["font_size_medium"],
                            booking.pu_Address_Suburb or "",
                            booking.pu_Address_State or "",
                            booking.pu_Address_PostalCode or "",
                        ),
                        style_left,
                    ),
                ],
                [
                    Paragraph(
                        "<font size=%s>%s %s</font> "
                        % (
                            label_settings["font_size_medium"],
                            booking.pu_Phone_Main or "",
                            booking.pu_Contact_F_L_Name or "",
                        ),
                        style_left,
                    ),
                ],
                [
                    Paragraph(
                        "<font size=%s>Item %s/%s Weight %s %s</font>"
                        % (
                            label_settings["font_size_medium"],
                            j,
                            totalQty,
                            line.e_Total_KG_weight or "",
                            line.e_weightUOM or "",
                        ),
                        style_left,
                    )
                ],
                [
                    Paragraph(
                        "<font size=%s>%s</font> "
                        % (
                            label_settings["font_size_medium"],
                            datetime.datetime.now().strftime("%d/%m/%Y"),
                        ),
                        style_left,
                    ),
                ],
            ]

            t1 = Table(
                tbl_data1,
                colWidths=(
                    float(label_settings["label_image_size_length"]) * (3 / 8) * mm
                ),
                style=[
                    ("TOPPADDING", (0, 0), (-1, -1), 0),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                ],
            )

            tbl_data2 = [
                [
                    Paragraph(
                        "<font size=%s>To: %s</font>"
                        % (
                            label_settings["font_size_medium"],
                            booking.deToCompanyName or "",
                        ),
                        style_left,
                    )
                ],
                [
                    Paragraph(
                        "<font size=%s>%s</font>"
                        % (
                            label_settings["font_size_medium"],
                            booking.de_To_Address_Street_1 or "",
                        ),
                        style_left,
                    ),
                ],
                [
                    Paragraph(
                        "<font size=%s>%s</font> "
                        % (
                            label_settings["font_size_medium"],
                            booking.de_To_Address_Street_2 or "",
                        ),
                        style_left,
                    ),
                ],
                [
                    Paragraph(
                        "<font size=%s><b>%s %s %s</b></font> "
                        % (
                            label_settings["font_size_medium"],
                            booking.de_To_Address_Suburb or "",
                            booking.de_To_Address_State or "",
                            booking.de_To_Address_PostalCode or "",
                        ),
                        style_left,
                    ),
                ],
                [
                    Paragraph(
                        "<font size=%s>%s %s</font>"
                        % (
                            label_settings["font_size_medium"],
                            booking.de_to_Phone_Main or "",
                            booking.de_to_Contact_F_LName or "",
                        ),
                        style_left,
                    )
                ],
                [
                    Paragraph(
                        "<font size=%s>%s %s</font>"
                        % (
                            label_settings["font_size_medium"],
                            "CON.",
                            v_FPBookingNumber,
                        ),
                        style_left,
                    )
                ],
                [
                    Paragraph(
                        "<font size=%s>%s %s</font>"
                        % (
                            label_settings["font_size_medium"],
                            "Item Ref:",
                            extract_product_code(line.e_item),
                        ),
                        style_left,
                    )
                ],
            ]

            t2 = Table(
                tbl_data2,
                colWidths=(
                    float(label_settings["label_image_size_length"]) * (3 / 8) * mm
                ),
                style=[
                    ("TOPPADDING", (0, 0), (-1, -1), 0),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                ],
            )

            tbl_data3 = [
                [
                    Paragraph(
                        "<font size=%s>Instructions: %s</font>"
                        % (
                            label_settings["font_size_medium"],
                            str(booking.de_to_Pick_Up_Instructions_Contact)
                            if booking.de_to_Pick_Up_Instructions_Contact
                            else "",
                        ),
                        style_left,
                    )
                ],
            ]

            t3 = Table(
                tbl_data3,
                colWidths=(
                    float(label_settings["label_image_size_length"]) * (2 / 8) * mm
                ),
                style=[
                    ("TOPPADDING", (0, 0), (-1, -1), 0),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                ],
            )

            data = [[t1, t2, t3]]

            t1_w = float(label_settings["label_image_size_length"]) * (3 / 8) * mm
            t2_w = float(label_settings["label_image_size_length"]) * (3 / 8) * mm
            t3_w = float(label_settings["label_image_size_length"]) * (2 / 8) * mm

            shell_table = Table(
                data,
                colWidths=[t1_w, t2_w, t3_w],
                style=[
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("SPAN", (0, 0), (0, -1)),
                    ("TOPPADDING", (0, 0), (-1, -1), 0),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                    # ('LEFTPADDING',(0,0),(-1,-1), 0),
                    # ('RIGHTPADDING',(0,0),(-1,-1), 0),
                    ("BOX", (0, 0), (2, -1), 1, colors.black),
                ],
            )

            Story.append(shell_table)

            Story.append(PageBreak())

            j += 1

    doc.build(Story, onFirstPage=myFirstPage, onLaterPages=myLaterPages)
    file.close()
    logger.info(
        f"#119 [HUNTER LABEL] Finished building label... (Booking ID: {booking.b_bookingID_Visual})"
    )
    return filepath, filename
