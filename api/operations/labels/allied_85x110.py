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

from api.models import Booking_lines, FPRouting, FP_zones, Fp_freight_providers
from api.helpers.cubic import get_cubic_meter
from api.fp_apis.utils import gen_consignment_num
from api.operations.api_booking_confirmation_lines import index as api_bcl
from api.common.ratio import _get_dim_amount, _get_weight_amount

logger = logging.getLogger(__name__)

styles = getSampleStyleSheet()
style_right = ParagraphStyle(name="right", parent=styles["Normal"], alignment=TA_RIGHT)
style_left = ParagraphStyle(
    name="left",
    parent=styles["Normal"],
    alignment=TA_LEFT,
    leading=15,
    spaceBefore=0,
)
style_center = ParagraphStyle(
    name="center",
    parent=styles["Normal"],
    alignment=TA_CENTER,
    leading=15,
)
style_uppercase = ParagraphStyle(
    name="uppercase",
    parent=styles["Normal"],
    alignment=TA_LEFT,
    leading=15,
    spaceBefore=0,
    spaceAfter=0,
    textTransform="uppercase",
)
style_back_black = ParagraphStyle(
    name="back_black",
    parent=styles["Normal"],
    alignment=TA_CENTER,
    leading=24,
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


def gen_barcode(booking, item_no=0):
    item_index = str(item_no).zfill(3)
    visual_id = str(booking.b_bookingID_Visual)
    label_code = f"DME{visual_id}-{item_index}"
    api_bcl.create(booking, [{"label_code": label_code}])
    return label_code


def build_label(booking, filepath, lines, label_index, sscc, one_page_label):
    logger.info(
        f"#110 [ALLIED LABEL] Started building label... (Booking ID: {booking.b_bookingID_Visual}, Lines: {lines})"
    )
    v_FPBookingNumber = gen_consignment_num(
        booking.vx_freight_provider, booking.b_bookingID_Visual
    )

    # start check if pdfs folder exists
    if not os.path.exists(filepath):
        os.makedirs(filepath)
    # end check if pdfs folder exists

    fp_id = Fp_freight_providers.objects.get(fp_company_name="Allied").id
    try:
        carrier = FP_zones.objects.get(
            state=booking.de_To_Address_State,
            suburb=booking.de_To_Address_Suburb,
            postal_code=booking.de_To_Address_PostalCode,
            fk_fp=fp_id,
        ).carrier
    except FP_zones.DoesNotExist:
        carrier = ""
    except Exception as e:
        logger.info(f"#110 [ALLIED LABEL] Error: {str(e)}")

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

    totalQty = 0
    if one_page_label:
        lines = [lines[0]]
        totalQty = 1
    else:
        for booking_line in lines:
            totalQty = totalQty + booking_line.e_qty

    # label_settings = get_label_settings( 146, 104 )[0]
    label_settings = {
        "font_family": "Verdana",
        "font_size_extra_small": "8",
        "font_size_small": "10",
        "font_size_medium": "14",
        "font_size_large": "18",
        "font_size_extra_large": "20",
        "label_dimension_length": "280",
        "label_dimension_width": "216",
        "label_image_size_length": "250",
        "label_image_size_width": "186",
        "barcode_size_height": "30",
        "barcode_size_width": "1.5",
        "line_height_extra_small": "2",
        "line_height_small": "5",
        "line_height_medium": "6",
        "line_height_large": "8",
        "line_height_extra_large": "18",
        "margin_v": "10",
        "margin_h": "12",
    }

    width = float(label_settings["label_dimension_length"]) * mm
    height = float(label_settings["label_dimension_width"]) * mm
    doc = SimpleDocTemplate(
        f"{filepath}/{filename}",
        pagesize=(width, height),
        rightMargin=float(label_settings["margin_v"]) * mm,
        leftMargin=float(label_settings["margin_v"]) * mm,
        topMargin=float(label_settings["margin_h"]) * mm,
        bottomMargin=float(label_settings["margin_h"]) * mm,
    )

    dme_logo = "./static/assets/logos/dme.png"
    dme_img = Image(dme_logo, 60 * mm, 12 * mm)

    allied_logo = "./static/assets/logos/allied.png"
    allied_img = Image(allied_logo, 60 * mm, 12 * mm)

    fp_color_code = (
        Fp_freight_providers.objects.get(fp_company_name="Allied").hex_color_code
        or "808080"
    )

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
    totalWeight = 0
    totalCubic = 0
    for booking_line in lines:
        totalQty = totalQty + booking_line.e_qty
        totalWeight = totalWeight + booking_line.e_Total_KG_weight
        totalCubic = totalCubic + booking_line.e_1_Total_dimCubicMeter

    for booking_line in lines:
        for k in range(booking_line.e_qty):
            if one_page_label and k > 0:
                continue

            data = [
                [
                    dme_img,
                    Paragraph(
                        "<font size=%s><b>%s</b></font>"
                        % (
                            label_settings["font_size_extra_large"],
                            (booking.vx_freight_provider)
                            if (booking.vx_freight_provider)
                            else "",
                        ),
                        style_center_bg,
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
            Story.append(Spacer(1, 10))

            tbl_data = [
                [
                    Paragraph(
                        "<font size=%s>From: %s</font>"
                        % (
                            label_settings["font_size_medium"],
                            booking.puCompany or "",
                        ),
                        style_left,
                    ),
                    Paragraph(
                        "<font size=%s>P/U Phone: %s</font>"
                        % (
                            label_settings["font_size_medium"],
                            booking.pu_Phone_Main or "",
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
                    float(label_settings["label_image_size_length"]) * (2 / 5) * mm,
                    float(label_settings["label_image_size_length"]) * (2 / 5) * mm,
                    float(label_settings["label_image_size_length"]) * (1 / 5) * mm,
                ),
                style=[
                    ("TOPPADDING", (0, 0), (-1, -1), 0),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                    ("VALIGN", (0, 0), (0, -1), "TOP"),
                ],
            )

            Story.append(shell_table)
            Story.append(Spacer(1, 10))

            tbl_data = [
                [
                    Paragraph(
                        "<font size=%s>%s %s, %s %s %s %s %s</font>"
                        % (
                            label_settings["font_size_medium"],
                            booking.pu_Contact_F_L_Name or "",
                            booking.pu_Address_Street_1 or "",
                            booking.pu_Address_street_2 or "",
                            booking.pu_Address_Suburb or "",
                            (booking.pu_Address_State or "").upper(),
                            booking.pu_Address_PostalCode or "",
                            booking.pu_Address_Country,
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
            Story.append(Spacer(1, 10))

            tbl_data = [
                [
                    Paragraph(
                        "<font size=%s>Contact: %s</font>"
                        % (
                            label_settings["font_size_medium"],
                            booking.de_to_Contact_F_LName or "",
                        ),
                        style_left,
                    ),
                    Paragraph(
                        "<font size=%s>Phone: %s</font>"
                        % (
                            label_settings["font_size_medium"],
                            booking.de_to_Phone_Main or "",
                        ),
                        style_left,
                    ),
                    Paragraph(
                        "<font size=%s>Package: %s of %s</font>"
                        % (label_settings["font_size_medium"], j, sscc_cnt),
                        style_left,
                    ),
                ],
            ]

            shell_table = Table(
                tbl_data,
                colWidths=(
                    float(label_settings["label_image_size_length"]) * (2 / 5) * mm,
                    float(label_settings["label_image_size_length"]) * (2 / 5) * mm,
                    float(label_settings["label_image_size_length"]) * (1 / 5) * mm,
                ),
                style=[
                    ("TOPPADDING", (0, 0), (-1, -1), 0),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                    ("VALIGN", (0, 0), (0, -1), "TOP"),
                ],
            )
            Story.append(shell_table)
            Story.append(Spacer(1, 10))

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
                    float(label_settings["label_image_size_length"]) * (2 / 5) * mm,
                    float(label_settings["label_image_size_length"]) * (3 / 5) * mm,
                ),
                style=[
                    ("TOPPADDING", (0, 0), (-1, -1), 0),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                    ("VALIGN", (0, 0), (0, -1), "TOP"),
                ],
            )
            Story.append(shell_table)

            Story.append(Spacer(1, 16))

            barcode = gen_barcode(booking, j)

            tbl_data = [
                [
                    code128.Code128(
                        barcode,
                        barHeight=(float(label_settings["barcode_size_height"])) * mm,
                        barWidth=(float(label_settings["barcode_size_width"])) * mm,
                        humanReadable=False,
                    )
                ],
            ]

            barcode_table = Table(
                tbl_data,
                colWidths=((float(label_settings["label_image_size_length"])) * mm),
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
            Story.append(Spacer(1, 10))

            tbl_parcelId = [
                [
                    Paragraph(
                        "<font size=%s><b>&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;AEO%s%s</b></font>"
                        % (
                            label_settings["font_size_medium"],
                            booking.b_bookingID_Visual or "",
                            str(j).zfill(3),
                        ),
                        style_left,
                    ),
                ],
            ]

            tbl_data2 = [
                [
                    Paragraph(
                        "<font size=%s>Service: </font>"
                        % (label_settings["font_size_medium"]),
                        style_left,
                    ),
                    Paragraph(
                        '<font size=%s color="white"><b>%s</b> </font>'
                        % (
                            label_settings["font_size_large"],
                            booking.vx_serviceName or "",
                        ),
                        style_back_black,
                    ),
                ],
            ]

            tbl_service = Table(
                tbl_data2,
                colWidths=(
                    72,
                    float(label_settings["label_image_size_length"]) * (1 / 3) * mm
                    - 72,
                ),
                style=[
                    ("TOPPADDING", (0, 0), (-1, -1), 0),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                ],
            )

            tbl_package = [
                [
                    Paragraph(
                        "<font size=%s>Package: %s of %s</font>"
                        % (label_settings["font_size_medium"], j, sscc_cnt),
                        style_left,
                    ),
                    Paragraph(
                        "<font size=%s>Weight: %s</font>"
                        % (
                            label_settings["font_size_medium"],
                            str(booking_line.e_Total_KG_weight) + "KG" or "",
                        ),
                        style_left,
                    ),
                ],
            ]

            data = [[tbl_parcelId, tbl_service, tbl_package]]
            shell_table = Table(
                data,
                colWidths=(
                    float(label_settings["label_image_size_length"]) * (2 / 5) * mm,
                    float(label_settings["label_image_size_length"]) * (2 / 5) * mm,
                    float(label_settings["label_image_size_length"]) * (1 / 5) * mm,
                ),
                style=[
                    ("TOPPADDING", (0, 0), (-1, -1), 0),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                ],
            )

            Story.append(shell_table)

            Story.append(Spacer(1, 10))

            tbl_data1 = [
                [
                    Paragraph(
                        "<font size=%s>To: %s</font>"
                        % (
                            label_settings["font_size_medium"],
                            booking.deToCompanyName or "",
                        ),
                        style_left,
                    ),
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
            Story.append(Spacer(1, 10))

            tbl_data1 = [
                [
                    Paragraph(
                        "<font size=%s>&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;%s %s, %s</font>"
                        % (
                            label_settings["font_size_medium"],
                            booking.de_to_Contact_F_LName or "",
                            booking.de_To_Address_Street_1 or "",
                            booking.de_To_Address_Street_2 or "",
                        ),
                        style_left,
                    ),
                ]
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
            Story.append(Spacer(1, 10))

            tbl_data1 = [
                [
                    Paragraph(
                        "<font size=%s><b>%s</b></font>"
                        % (
                            label_settings["line_height_extra_large"],
                            booking.de_To_Address_State or "",
                        ),
                        style_left,
                    ),
                ]
            ]

            tbl_data2 = [
                [
                    Paragraph(
                        "<font size=%s><b>%s</b></font>"
                        % (
                            label_settings["line_height_extra_large"],
                            carrier,
                        ),
                        style_left,
                    ),
                ]
            ]

            tbl_data3 = [
                [
                    Paragraph(
                        "<font size=%s><b>%s</b></font>"
                        % (
                            label_settings["line_height_extra_large"],
                            booking.de_To_Address_PostalCode or "",
                        ),
                        style_left,
                    ),
                ]
            ]

            data = [[tbl_data1, tbl_data2, tbl_data3]]

            t1_w = float(label_settings["label_image_size_length"]) * (1 / 6) * mm
            t2_w = float(label_settings["label_image_size_length"]) * (1 / 4) * mm
            t3_w = float(label_settings["label_image_size_length"]) * (1 / 12) * mm

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

            if booking_line.e_dimUOM:
                _dim_amount = _get_dim_amount(booking_line.e_dimUOM)

            _length = round(_dim_amount * (booking_line.e_dimLength or 0), 3)
            _width = round(_dim_amount * (booking_line.e_dimWidth or 0), 3)
            _height = round(_dim_amount * (booking_line.e_dimHeight or 0), 3)

            tbl_data1 = [
                [
                    Paragraph(
                        "<font size=%s>Item %s: %sx%sx%s = %s M<super rise=8 size=8>3</super></font>"
                        % (
                            label_settings["font_size_medium"],
                            j,
                            _length,
                            _width,
                            _height,
                            booking_line.e_1_Total_dimCubicMeter or "",
                        ),
                        style_left,
                    )
                ]
            ]

            tbl_data2 = [
                [
                    Paragraph(
                        "<font size=%s><b>%s</b></font>"
                        % (
                            label_settings["line_height_extra_large"],
                            booking.de_To_Address_Suburb,
                        ),
                        style_left,
                    ),
                ],
                [Spacer(1, 10)],
                [shell_table],
            ]

            data = [[tbl_data1, tbl_data2]]

            t1_w = float(label_settings["label_image_size_length"]) * (1 / 2) * mm
            t2_w = float(label_settings["label_image_size_length"]) * (1 / 2) * mm

            shell_table = Table(
                data,
                colWidths=(t1_w, t2_w),
                style=[
                    ("TOPPADDING", (0, 0), (-1, -1), 0),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                    ("VALIGN", (0, 0), (0, -1), "TOP"),
                ],
            )

            Story.append(shell_table)
            Story.append(Spacer(1, 10))

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
            Story.append(Spacer(1, 10))

            tbl_data1 = [
                [
                    Paragraph(
                        "<font size=%s>Instruction: %s %s</font>"
                        % (
                            label_settings["font_size_medium"],
                            booking.de_to_PickUp_Instructions_Address or "",
                            booking.de_to_Pick_Up_Instructions_Contact or "",
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
            Story.append(Spacer(1, 10))

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
                            "&#95;&#95;&#95;&#95;&#95;&#95;&#95;&#95;&#95;&#95;&#95;&#95;&#95;&#95;&#95;&#95;&#95;&#95;&#95;",
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
            Story.append(Spacer(1, 10))

            tbl_data1 = [
                [
                    Paragraph(
                        "<font size=%s><b>Name %s</b></font>"
                        % (
                            label_settings["font_size_medium"],
                            "&#95;&#95;&#95;&#95;&#95;&#95;&#95;&#95;&#95;&#95;&#95;&#95;&#95;&#95;&#95;&#95;&#95;&#95;&#95;",
                        ),
                        style_left,
                    ),
                    Paragraph(
                        "<font size=%s><b>Signature %s</b></font>"
                        % (
                            label_settings["font_size_medium"],
                            "&#95;&#95;&#95;&#95;&#95;&#95;&#95;&#95;&#95;&#95;&#95;&#95;&#95;&#95;&#95;&#95;&#95;&#95;&#95;",
                        ),
                        style_left,
                    ),
                    Paragraph(
                        "<font size=%s><b>Time %s</b></font>"
                        % (
                            label_settings["font_size_medium"],
                            "&#95;&#95;&#95;&#95;&#95;&#95;&#95;&#95;&#95;&#95;&#95;&#95;&#95;&#95;&#95;&#95;&#95;&#95;&#95;",
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
            Story.append(Spacer(1, 10))

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
            Story.append(Spacer(1, 10))

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
