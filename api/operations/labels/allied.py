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

styles.add(ParagraphStyle(name="Justify", alignment=TA_JUSTIFY))


def myFirstPage(canvas, doc):
    canvas.saveState()
    canvas.rotate(180)
    canvas.restoreState()


def myLaterPages(canvas, doc):
    canvas.saveState()
    canvas.rotate(90)
    canvas.restoreState()


def gen_barcode(booking, v_FPBookingNumber, item_no=0):
    item_index = str(item_no).zfill(3)
    visual_id = str(booking.b_bookingID_Visual)
    label_code = f"{v_FPBookingNumber}-{item_index}"
    api_bcl.create(booking, [{"label_code": label_code}])
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
    logger.info(
        f"#110 [ALLIED LABEL] Started building label... (Booking ID: {booking.b_bookingID_Visual}, Lines: {lines})"
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
    logger.info(f"#111 [ALLIED LABEL] File full path: {filepath}/{filename}")
    # end pdf file name using naming convention

    if not lines:
        lines = Booking_lines.objects.filter(fk_booking_id=booking.pk_booking_id)

    # label_settings = get_label_settings( 146, 104 )[0]
    label_settings = {
        "font_family": "Verdana",
        "font_size_extra_small": "4",
        "font_size_small": "6",
        "font_size_medium": "8",
        "font_size_large": "10",
        "font_size_extra_large": "13",
        "label_dimension_length": "150",
        "label_dimension_width": "100",
        "label_image_size_length": "135",
        "label_image_size_width": "100",
        "barcode_dimension_length": "85",
        "barcode_dimension_width": "30",
        "barcode_font_size": "18",
        "line_height_extra_small": "3",
        "line_height_small": "5",
        "line_height_medium": "6",
        "line_height_large": "8",
        "line_height_extra_large": "12",
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

    dme_logo = "./static/assets/logos/dme.png"
    dme_img = Image(dme_logo, 30 * mm, 7.7 * mm)

    allied_logo = "./static/assets/logos/allied.png"
    allied_img = Image(allied_logo, 30 * mm, 7.7 * mm)

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
        totalQty = sscc_cnt

    for booking_line in lines:
        for k in range(booking_line.e_qty):
            if one_page_label and k > 0:
                continue

            data = [
                [
                    dme_img,
                    # Paragraph(
                    #     "<font size=%s><b>%s</b></font>"
                    #     % (
                    #         label_settings["font_size_extra_large"],
                    #         (booking.vx_freight_provider)
                    #         if (booking.vx_freight_provider)
                    #         else "",
                    #     ),
                    #     style_center_bg,
                    # ),
                    Paragraph(
                        "",
                        style_center,
                    ),
                    allied_img,
                ]
            ]

            t1_w = float(label_settings["label_image_size_length"]) * (1 / 4) * mm
            t2_w = float(label_settings["label_image_size_length"]) * (2 / 4) * mm
            t3_w = float(label_settings["label_image_size_length"]) * (1 / 4) * mm

            header = Table(
                data,
                colWidths=[t1_w, t2_w, t3_w],
                style=[
                    ("VALIGN", (0, 0), (-1, -1), "CENTER"),
                    ("TOPPADDING", (0, 0), (-1, -1), 0),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                    ("BOTTOMBORDER", (0, 0), (-1, -1), 0),
                ],
            )
            Story.append(header)

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
                        "<font size=%s>Date: %s</font>"
                        % (
                            label_settings["font_size_medium"],
                            booking.b_dateBookedDate.strftime("%d/%m/%Y")
                            if booking.b_dateBookedDate
                            else booking.puPickUpAvailFrom_Date.strftime("%d/%m/%Y"),
                        ),
                        style_left,
                    ),
                ]
            ]

            shell_table = Table(
                tbl_data,
                colWidths=(
                    float(label_settings["label_image_size_length"]) * (2 / 3) * mm,
                    float(label_settings["label_image_size_length"]) * (1 / 3) * mm,
                ),
                style=[
                    ("TOPPADDING", (0, 0), (-1, -1), 0),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                    ("VALIGN", (0, 0), (0, -1), "TOP"),
                ],
            )

            Story.append(shell_table)
            Story.append(Spacer(1, 2))

            essentialPart = "%s %s %s %s" % (
                booking.pu_Address_Suburb or "",
                (booking.pu_Address_State or "").upper(),
                booking.pu_Address_PostalCode or "",
                booking.pu_Address_Country,
            )

            addressPart = "%s %s, %s" % (
                booking.pu_Contact_F_L_Name or "",
                booking.pu_Address_Street_1 or "",
                booking.pu_Address_street_2 or "",
            )

            addressLen = 80 - len(essentialPart)

            tbl_data = [
                [
                    Paragraph(
                        "<font size=%s>%s %s</font>"
                        % (
                            label_settings["font_size_medium"],
                            addressPart[:addressLen],
                            essentialPart,
                        ),
                        style_left,
                    )
                ]
            ]

            shell_table = Table(
                tbl_data,
                colWidths=(float(label_settings["label_image_size_length"]) * mm,),
                style=[
                    ("TOPPADDING", (0, 0), (-1, -1), 0),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                    ("VALIGN", (0, 0), (0, -1), "TOP"),
                ],
            )

            Story.append(shell_table)
            Story.append(Spacer(1, 2))

            tbl_data = [
                [
                    Paragraph(
                        "<font size=%s>Contact: %s</font>"
                        % (
                            label_settings["font_size_medium"],
                            (booking.pu_Contact_F_L_Name or "")[:20],
                        ),
                        style_left,
                    ),
                    Paragraph(
                        "<font size=%s>Phone: %s</font>"
                        % (
                            label_settings["font_size_medium"],
                            booking.pu_Phone_Main or "",
                        ),
                        style_left,
                    ),
                    Paragraph(
                        "<font size=%s>Package: %s of %s</font>"
                        % (label_settings["font_size_medium"], j, totalQty),
                        style_left,
                    ),
                ],
            ]

            shell_table = Table(
                tbl_data,
                colWidths=(
                    float(label_settings["label_image_size_length"]) * (1 / 3) * mm,
                    float(label_settings["label_image_size_length"]) * (1 / 3) * mm,
                    float(label_settings["label_image_size_length"]) * (1 / 3) * mm,
                ),
                style=[
                    ("TOPPADDING", (0, 0), (-1, -1), 0),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                    ("VALIGN", (0, 0), (0, -1), "TOP"),
                ],
            )
            Story.append(shell_table)
            Story.append(Spacer(1, 2))

            tbl_data = [
                [
                    Paragraph(
                        "<font size=%s>Parcel ID: <b>%s</b></font>"
                        % (
                            label_settings["font_size_medium"],
                            booking_line.sscc or sscc,
                        ),
                        style_left,
                    ),
                    Paragraph(
                        "<font size=%s>Order Ref: %s</font>"
                        % (
                            label_settings["font_size_medium"],
                            booking.b_client_order_num or "",
                        ),
                        style_left,
                    ),
                ],
            ]

            shell_table = Table(
                tbl_data,
                colWidths=(
                    float(label_settings["label_image_size_length"]) * (2 / 3) * mm,
                    float(label_settings["label_image_size_length"]) * (1 / 3) * mm,
                ),
                style=[
                    ("TOPPADDING", (0, 0), (-1, -1), 0),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                    ("VALIGN", (0, 0), (0, -1), "TOP"),
                ],
            )
            Story.append(shell_table)

            Story.append(Spacer(1, 3))

            barcode = gen_barcode(booking, v_FPBookingNumber, j)

            tbl_data = [
                [
                    code128.Code128(
                        barcode,
                        barHeight=15 * mm,
                        barWidth=2 * 14 / len(barcode),
                        humanReadable=False,
                    )
                ],
            ]

            barcode_table = Table(
                tbl_data,
                colWidths=((float(label_settings["label_image_size_length"])) * mm),
                style=[
                    ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                    ("VALIGN", (0, 0), (0, -1), "TOP"),
                    ("TOPPADDING", (0, 0), (-1, -1), 5),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                    ("LEFTPADDING", (0, 0), (-1, -1), 0),
                    ("RIGHTPADDING", (0, 0), (0, -1), 0),
                ],
            )

            Story.append(barcode_table)

            vx_serviceName = booking.vx_serviceName or ""

            tbl_data2 = [
                [
                    Paragraph(
                        "<font size=%s>Service: </font>"
                        % (label_settings["font_size_medium"]),
                        style_left_bg,
                    ),
                    Paragraph(
                        '<font size=%s color="white"><b>%s</b> </font>'
                        % (
                            label_settings["font_size_large"]
                            if len(vx_serviceName) < 23
                            else label_settings["font_size_medium"],
                            vx_serviceName or "",
                        ),
                        style_back_black,
                    ),
                ],
            ]

            tbl_service = Table(
                tbl_data2,
                colWidths=(
                    45,
                    float(label_settings["label_image_size_length"]) * (5 / 9) * mm
                    - 45,
                ),
                style=[
                    ("TOPPADDING", (0, 0), (-1, -1), 0),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                    ("VALIGN", (0, 0), (-1, -1), "CENTER"),
                ],
            )

            tbl_parcelId = [
                [
                    Paragraph(
                        "<font size=%s>&nbsp;&nbsp; Item No: <b>%s-%s</b></font>"
                        % (
                            label_settings["font_size_medium"],
                            v_FPBookingNumber,
                            str(j).zfill(3),
                        ),
                        style_left,
                    ),
                    Spacer(1, 1),
                    Paragraph(
                        "<font size=%s>&nbsp;&nbsp; Consignment No: <b>%s</b></font>"
                        % (
                            label_settings["font_size_medium"],
                            v_FPBookingNumber,
                        ),
                        style_left,
                    ),
                    Spacer(4, 4),
                    tbl_service,
                ],
            ]

            if booking_line.e_dimUOM:
                _dim_amount = _get_dim_amount(booking_line.e_dimUOM)

            _length = round(_dim_amount * (booking_line.e_dimLength or 0), 3)
            _width = round(_dim_amount * (booking_line.e_dimWidth or 0), 3)
            _height = round(_dim_amount * (booking_line.e_dimHeight or 0), 3)

            tbl_package = [
                [
                    Paragraph(
                        "<font size=%s>Item %s: %sx%sx%s = %s M<super rise=4 size=4>3</super></font>"
                        % (
                            label_settings["font_size_medium"],
                            j,
                            _length,
                            _width,
                            _height,
                            round(
                                get_cubic_meter(
                                    booking_line.e_dimLength,
                                    booking_line.e_dimWidth,
                                    booking_line.e_dimHeight,
                                    booking_line.e_dimUOM,
                                ),
                                3,
                            )
                            or "",
                        ),
                        style_left,
                    ),
                    Spacer(1, 1),
                    Paragraph(
                        "<font size=%s>Weight: %s</font>"
                        % (
                            label_settings["font_size_medium"],
                            str(booking_line.e_qty * booking_line.e_weightPerEach)
                            + "KG",
                        ),
                        style_left,
                    ),
                    Spacer(4, 4),
                    Paragraph(
                        "<font size=%s>Description:&nbsp;%s</font>"
                        % (
                            label_settings["font_size_medium"],
                            extract_product_code(booking_line.e_item)[:20],
                        ),
                        style_left,
                    ),
                ],
            ]

            data = [[tbl_parcelId, tbl_package]]
            shell_table = Table(
                data,
                colWidths=(
                    float(label_settings["label_image_size_length"]) * (7 / 12) * mm,
                    float(label_settings["label_image_size_length"]) * (5 / 12) * mm,
                ),
                style=[
                    ("TOPPADDING", (0, 0), (-1, -1), 0),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ],
            )

            Story.append(shell_table)

            Story.append(Spacer(1, 5))
            # To: row table
            to_del_data = []

            codeString = f"{v_FPBookingNumber}-{str(j).zfill(3)}~{v_FPBookingNumber}~{booking.de_To_Address_PostalCode}~{booking.de_To_Address_Suburb}"
            d = Drawing(15, 15, transform=[1, 0, 0, 1, 0, -35])
            d.add(Rect(0, 0, 0, 0, strokeWidth=1, fillColor=None))
            d.add(QrCodeWidget(value=codeString, barWidth=20 * mm, barHeight=20 * mm))

            # font_size = "font_size_large" if (
            #     len(str(booking.deToCompanyName or "" + booking.de_to_Contact_F_LName or "")) < 45 and
            #     len(str(booking.de_To_Address_Street_1 or "" + booking.de_To_Address_Street_2 or "")) < 45 and
            #     len(str(booking.de_To_Address_State or "" + carrier or "" + booking.de_To_Address_PostalCode or "" + booking.de_To_Address_Suburb or "")) < 40) else "font_size_medium"
            to_del_data.append(
                [
                    Paragraph(
                        "<font size=%s>To:</font>"
                        % (label_settings["font_size_large"],),
                        style_left_bg,
                    ),
                    Paragraph(
                        "<font size=%s><b>%s %s</b> <br/> <b>%s</b> <br/> </font>"
                        % (
                            label_settings["font_size_large"],
                            booking.deToCompanyName or "",
                            ""
                            if booking.deToCompanyName == booking.de_to_Contact_F_LName
                            else (booking.de_to_Contact_F_LName or ""),
                            (
                                (booking.de_To_Address_Street_1 or "")
                                + " "
                                + (booking.de_To_Address_Street_2 or "")
                            )[:30],
                        ),
                        style_left_bg,
                    ),
                    d,
                ]
            )

            to_del_data.append(
                [
                    "",
                    Paragraph(
                        "<font size=%s><b>%s&nbsp;%s&nbsp;%s&nbsp;%s</b></font>"
                        % (
                            label_settings["font_size_large"],
                            booking.de_To_Address_State or "",
                            (pre_data["carrier"] or "")[:20],
                            booking.de_To_Address_PostalCode or "",
                            booking.de_To_Address_Suburb or "",
                        ),
                        style_left_bg,
                    ),
                    "",
                ]
            )

            to_del_data.append(
                [
                    "",
                    Paragraph(
                        "<font size=%s><b>%s</b></font>"
                        % (
                            label_settings["font_size_large"],
                            booking.de_to_Phone_Main[:30],
                        ),
                        style_left,
                    ),
                    "",
                ]
            )

            shell_table = Table(
                to_del_data,
                colWidths=(
                    float(label_settings["label_image_size_length"]) * mm * 0.7 / 10,
                    float(label_settings["label_image_size_length"]) * mm * 6.3 / 10,
                    float(label_settings["label_image_size_length"]) * mm * 3 / 10,
                ),
                style=[
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 0),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                    ("TOPPADDING", (0, 0), (-1, -1), 0),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                ],
            )
            Story.append(shell_table)
            Story.append(Spacer(1, 3))

            tbl_data1 = [
                [
                    Paragraph(
                        "<font size=%s><b>Dangerous Goods Enclosed: %s</b></font>"
                        % (
                            label_settings["font_size_medium"],
                            "YES" if booking_line.e_dangerousGoods == True else "NO",
                        ),
                        style_left,
                    )
                ],
            ]

            shell_table = Table(
                tbl_data1,
                colWidths=(float(label_settings["label_image_size_length"]) * mm),
                style=[
                    ("TOPPADDING", (0, 0), (-1, -1), 0),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ],
            )

            Story.append(shell_table)
            Story.append(Spacer(1, 2))

            tbl_data1 = [
                [
                    Paragraph(
                        "<font size=%s>Instruction: %s</font>"
                        % (
                            label_settings["font_size_medium"],
                            (
                                (booking.de_to_PickUp_Instructions_Address or "")
                                + " "
                                + (booking.de_to_Pick_Up_Instructions_Contact or "")
                            )[:70],
                        ),
                        style_left,
                    )
                ],
            ]

            shell_table = Table(
                tbl_data1,
                colWidths=(float(label_settings["label_image_size_length"]) * mm),
                style=[
                    ("TOPPADDING", (0, 0), (-1, -1), 0),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ],
            )

            Story.append(shell_table)
            Story.append(Spacer(1, 2))

            tbl_data1 = [
                [
                    Paragraph(
                        "<font size=%s>Account: %s</font>"
                        % (
                            label_settings["font_size_medium"],
                            booking.vx_account_code or "",
                        ),
                        style_left,
                    ),
                    Paragraph(
                        "<font size=%s>Date: %s</font>"
                        % (
                            label_settings["font_size_medium"],
                            booking.b_dateBookedDate.strftime("%d/%m/%Y")
                            if booking.b_dateBookedDate
                            else booking.puPickUpAvailFrom_Date.strftime("%d/%m/%Y"),
                        ),
                        style_left,
                    ),
                    Paragraph(
                        "<font size=%s><b>Date %s</b></font>"
                        % (
                            label_settings["font_size_medium"],
                            "&#95;&#95;&#95;&#95;&#95;&#95;&#95;&#95;&#95;&#95;&#95;&#95;&#95;&#95;",
                        ),
                        style_left,
                    ),
                ],
            ]

            signature_table = Table(
                tbl_data1,
                colWidths=(
                    float(label_settings["label_image_size_length"]) * (1 / 3) * mm,
                    float(label_settings["label_image_size_length"]) * (1 / 3) * mm,
                    float(label_settings["label_image_size_length"]) * (1 / 3) * mm,
                ),
                style=[
                    ("TOPPADDING", (0, 0), (-1, -1), 0),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                    ("VALIGN", (0, 0), (0, -1), "BOTTOM"),
                ],
            )

            Story.append(signature_table)
            Story.append(Spacer(1, 2))

            tbl_data1 = [
                [
                    Paragraph(
                        "<font size=%s><b>Name %s</b></font>"
                        % (
                            label_settings["font_size_medium"],
                            "&#95;&#95;&#95;&#95;&#95;&#95;&#95;&#95;&#95;&#95;&#95;&#95;&#95;&#95;",
                        ),
                        style_left,
                    ),
                    Paragraph(
                        "<font size=%s><b>Signature %s</b></font>"
                        % (
                            label_settings["font_size_medium"],
                            "&#95;&#95;&#95;&#95;&#95;&#95;&#95;&#95;&#95;&#95;&#95;&#95;&#95;&#95;",
                        ),
                        style_left,
                    ),
                    Paragraph(
                        "<font size=%s><b>Time %s</b></font>"
                        % (
                            label_settings["font_size_medium"],
                            "&#95;&#95;&#95;&#95;&#95;&#95;&#95;&#95;&#95;&#95;&#95;&#95;&#95;&#95;",
                        ),
                        style_left,
                    ),
                ],
            ]

            signature_table = Table(
                tbl_data1,
                colWidths=(
                    float(label_settings["label_image_size_length"]) * (1 / 3) * mm,
                    float(label_settings["label_image_size_length"]) * (1 / 3) * mm,
                    float(label_settings["label_image_size_length"]) * (1 / 3) * mm,
                ),
                style=[
                    ("TOPPADDING", (0, 0), (-1, -1), 0),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                    ("VALIGN", (0, 0), (0, -1), "BOTTOM"),
                ],
            )

            Story.append(signature_table)
            Story.append(Spacer(1, 2))

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
            Story.append(Spacer(1, 2))

            tbl_data1 = [
                [
                    Paragraph(
                        "<font size=%s>%s</font>"
                        % (
                            label_settings["font_size_small"],
                            "RECEIVED IN GOOD CONDITION. SUBJECT TO CARRIER TERMS AND CONDITIONS.",
                        ),
                        style_center,
                    )
                ],
            ]

            footer_table = Table(
                tbl_data1,
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

            Story.append(footer_table)
            Story.append(PageBreak())

            j += 1

    doc.build(Story, onFirstPage=myFirstPage, onLaterPages=myLaterPages)
    file.close()
    logger.info(
        f"#119 [ALLIED LABEL] Finished building label... (Booking ID: {booking.b_bookingID_Visual})"
    )
    return filepath, filename
