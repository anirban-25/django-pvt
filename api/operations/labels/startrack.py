import os
import math
import datetime
import pandas as pd
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
from reportlab.platypus.flowables import Image, Spacer, PageBreak
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.graphics.barcode import code128
from reportlab.graphics.barcode.qr import QrCodeWidget
from reportlab.graphics.shapes import Drawing, Rect
from reportlab.lib import colors

from api.models import (
    Booking_lines,
    Fp_freight_providers,
    Bookings,
)
from api.helpers.cubic import get_cubic_meter
from api.fp_apis.constants import FP_CREDENTIALS
from api.operations.api_booking_confirmation_lines import index as api_bcl

logger = logging.getLogger(__name__)

styles = getSampleStyleSheet()
style_right = ParagraphStyle(
    name="right",
    parent=styles["Normal"],
    alignment=TA_RIGHT,
    leading=18,
    fontSize=18,
)
style_left = ParagraphStyle(
    name="left",
    parent=styles["Normal"],
    alignment=TA_LEFT,
    leading=10,
    fontSize=8,
)
style_left_large = ParagraphStyle(
    name="left",
    parent=styles["Normal"],
    alignment=TA_LEFT,
    leading=10,
    fontSize=10,
)
style_extra_large = ParagraphStyle(
    name="left",
    parent=styles["Normal"],
    alignment=TA_LEFT,
    leading=18,
    fontSize=18,
)
style_left_small = ParagraphStyle(
    name="left",
    parent=styles["Normal"],
    alignment=TA_LEFT,
    leading=7,
    fontSize=7,
)
style_center = ParagraphStyle(
    name="center",
    parent=styles["Normal"],
    alignment=TA_CENTER,
    leading=12,
    fontSize=8,
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
    leading=14,
    backColor="black",
)
style_PRD = ParagraphStyle(
    name="PRD",
    parent=styles["Normal"],
    alignment=TA_CENTER,
    fontSize=22,
    leading=24,
)

tableStyle = [
    ("VALIGN", (0, 0), (-1, -1), "CENTER"),
    ("LEFTPADDING", (0, 0), (-1, -1), 0),
    ("RIGHTPADDING", (0, 0), (-1, -1), 0),
    ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ("TOPPADDING", (0, 0), (-1, -1), 0),
]

styles.add(ParagraphStyle(name="Justify", alignment=TA_JUSTIFY))


def myFirstPage(canvas, doc):
    canvas.saveState()
    canvas.rotate(180)
    canvas.restoreState()


def myLaterPages(canvas, doc):
    canvas.saveState()
    canvas.rotate(90)
    canvas.restoreState()


def gen_ReceiverBarcode(booking, location_info):
    service_name = get_serviceLabelCode(str(booking.vx_serviceName))
    postal_code = str(booking.de_To_Address_PostalCode)
    depote_code = str(location_info["R1"] or "")
    label_code = f"{service_name}{postal_code}{depote_code}"
    # api_bcl.create(booking, [{"item_id": label_code}])
    return label_code


def gen_QRcodeString(
    booking,
    booking_line,
    location_info,
    v_FPBookingNumber,
    totalCubic,
    atl_number,
    item_no=0,
):
    item_index = str(item_no).zfill(5)
    receiver_suburb = str(booking.de_To_Address_Suburb).ljust(30)
    postal_code = str(booking.de_To_Address_PostalCode).ljust(4)
    consignment_num = str(v_FPBookingNumber).ljust(12)
    product_code = str(booking.vx_serviceName)
    freight_item_id = consignment_num + product_code + item_index
    payer_account = str("").ljust(8)
    sender_account = ""

    for client_name in FP_CREDENTIALS["startrack"].keys():
        for key in FP_CREDENTIALS["startrack"][client_name].keys():
            if key == booking.b_client_warehouse_code:
                detail = FP_CREDENTIALS["startrack"][client_name][key]
                sender_account = detail["accountCode"].ljust(8)

    if not sender_account:
        raise Exception("[ST gen_QRcodeString] Could`nt find accountCode")

    consignment_quantity = str(booking_line.e_qty).ljust(4)
    consignment_weight = str(math.ceil(booking_line.e_Total_KG_weight)).ljust(5)
    consignment_cube = str(number_format(round(totalCubic, 3))).ljust(5)
    if booking.b_dateBookedDate:
        despatch_date = booking.b_dateBookedDate.strftime("%Y%m%d")
    else:
        despatch_date = booking.puPickUpAvailFrom_Date.strftime("%Y%m%d")
    receiver_name1 = str(booking.de_to_Contact_F_LName or "").ljust(40)
    receiver_name2 = str(
        ""
        if booking.deToCompanyName == booking.de_to_Contact_F_LName
        else (booking.deToCompanyName or "")
    ).ljust(40)
    unit_type = str(
        "CTN"
        if len(booking_line.e_type_of_packaging or "") != 3
        else booking_line.e_type_of_packaging
    )
    destination_depot = str(location_info["R2"] or "").ljust(4)
    receiver_address1 = str(booking.de_To_Address_Street_1).ljust(40)
    receiver_address2 = str("").ljust(40)
    receiver_phone = str(booking.de_to_Phone_Main).ljust(14)
    dangerous_goods_indicator = "Y" if booking_line.e_dangerousGoods == True else "N"
    movement_type_indicator = "N"
    not_before_date = str("").ljust(12)
    not_after_date = str("").ljust(12)
    atl_number = str(atl_number if atl_number else "").ljust(10)
    rl_number = str("").ljust(10)

    label_code = f"{receiver_suburb}{postal_code}{consignment_num}{freight_item_id}{product_code}{payer_account}{sender_account}{consignment_quantity}{consignment_weight}{consignment_cube}{despatch_date}{receiver_name1}{receiver_name2}{unit_type}{destination_depot}{receiver_address1}{receiver_address2}{receiver_phone}{dangerous_goods_indicator}{movement_type_indicator}{not_before_date}{not_after_date}{atl_number}{rl_number}"
    logger.info(label_code)
    return label_code


def number_format(num):
    return str(round(num * 1000))


def gen_barcode(booking, v_FPBookingNumber, item_no=0):
    service_name = str(booking.vx_serviceName)
    item_index = str(item_no).zfill(5)

    label_code = f"{v_FPBookingNumber}{service_name}{item_index}"

    return label_code


def get_ATL_number(booking):
    if booking.fp_atl_number:
        return booking.fp_atl_number
    freight_provider = Fp_freight_providers.objects.filter(
        fp_company_name=booking.vx_freight_provider
    )
    last_atl_number = freight_provider.first().last_atl_number
    freight_provider.update(last_atl_number=last_atl_number + 1)
    return last_atl_number + 1


def get_serviceLabelCode(temp):
    return "PRM" if temp == "FPP" else temp


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
        f"#110 [{booking.vx_freight_provider} LABEL] Started building label... (Booking ID: {booking.b_bookingID_Visual}, Lines: {lines})"
    )
    v_FPBookingNumber = pre_data["v_FPBookingNumber"]
    # if booking.v_FPBookingNumber else gen_consignment_num(
    #     booking.vx_freight_provider, booking.b_bookingID_Visual
    # )

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
    logger.info(
        f"#111 [{booking.vx_freight_provider} LABEL] File full path: {filepath}/{filename}"
    )
    # end pdf file name using naming convention

    if not lines:
        lines = Booking_lines.objects.filter(fk_booking_id=booking.pk_booking_id)

    # label_settings = get_label_settings( 146, 104 )[0]
    label_settings = {
        "font_family": "Arial",
        "font_size_extra_small": "4",
        "font_size_small": "6",
        "font_size_medium": "8",
        "font_size_large": "10",
        "font_size_extra_large": "12",
        "label_dimension_length": "150",
        "label_dimension_width": "100",
        "label_image_size_length": "143",
        "label_image_size_width": "93",
        "header_length": "16",
        "fp_logo_width": "30",
        "fp_logo_length": "4",
        "barcode_dimension_length": "85",
        "barcode_dimension_width": "30",
        "barcode_font_size": "18",
        "line_height_extra_small": "3",
        "line_height_small": "5",
        "line_height_medium": "6",
        "line_height_large": "8",
        "line_height_extra_large": "12",
        "margin_v": "3.5",
        "margin_h": "3.5",
    }

    width = float(label_settings["label_dimension_width"]) * mm
    height = float(label_settings["label_dimension_length"]) * mm
    doc = SimpleDocTemplate(
        f"{filepath}/{filename}",
        pagesize=(width, height),
        rightMargin=float(label_settings["margin_h"]) * mm,
        leftMargin=float(label_settings["margin_h"]) * mm,
        topMargin=float(label_settings["margin_v"]) * mm,
        bottomMargin=float(label_settings["margin_v"]) * mm,
    )

    dme_logo = "./static/assets/logos/dme.png"
    dme_img = Image(dme_logo, 28 * mm, 7.7 * mm)

    fp_logo = "./static/assets/logos/startrack.png"
    fp_img = Image(
        fp_logo,
        float(label_settings["label_image_size_width"]) * (2.5 / 10) * mm,
        6 * mm,
    )

    Story = []
    j = 1

    totalQty = sscc_cnt
    # totalQty = 0
    # for booking_line in lines:
    #     totalQty = totalQty + booking_line.e_qty

    totalWeight = 0
    totalCubic = 0
    for booking_line in lines:
        totalWeight = totalWeight + booking_line.e_qty * booking_line.e_weightPerEach
        totalCubic = totalCubic + get_cubic_meter(
            booking_line.e_dimLength,
            booking_line.e_dimWidth,
            booking_line.e_dimHeight,
            booking_line.e_dimUOM,
            booking_line.e_qty,
        )

    if sscc:
        j = 1 + label_index

    atl_number = None
    if booking.opt_authority_to_leave:
        atl_number = get_ATL_number(booking)
        Bookings.objects.filter(id=booking.id).update(fp_atl_number=atl_number)
        atl_number = f"C{str(atl_number).zfill(9)}"

    locations = pd.read_excel(
        r"./static/assets/xlsx/startrack_rt1_rt2_LOCATION-20210606.xls"
    )
    booking.label_code = get_serviceLabelCode(booking.vx_serviceName)

    for booking_line in lines:
        for k in range(booking_line.e_qty):
            if one_page_label and k > 0:
                continue

            t1_w = float(label_settings["label_image_size_width"]) / 10 * mm
            location_info = {}

            for index in range(len(locations)):
                if str(locations["Postcode"][index]) == str(
                    int(booking.de_To_Address_PostalCode)
                ) and str(
                    locations["Suburb"][index].lower()
                    == str(booking.de_To_Address_Suburb or "").lower()
                ):
                    if booking.vx_serviceName == "EXP":
                        location_info = {
                            "R1": locations["Primary Port"][index],
                            "R2": locations["Nearest Depot"][index],
                        }
                    else:
                        location_info = {
                            "R1": locations["Primary Port"][index],
                            "R2": locations["Seconday Port"][index],
                        }

            prd_data = Table(
                [
                    [
                        Paragraph(
                            "<font color='%s'><b>%s</b></font>"
                            % (
                                colors.white
                                if booking.label_code == "PRM"
                                else colors.black,
                                booking.vx_serviceName,
                            ),
                            style_PRD,
                        ),
                    ],
                ],
                colWidths=[t1_w * 2.5],
                rowHeights=[11 * mm],
                style=[
                    *tableStyle,
                    *(
                        [("BACKGROUND", (0, 0), (-1, -1), "black")]
                        if booking.label_code == "PRM"
                        else []
                    ),
                ],
            )
            data = [
                [
                    [
                        prd_data,
                        fp_img,
                    ],
                    [
                        Table(
                            [
                                [
                                    Spacer(1, 4),
                                ],
                                [
                                    Paragraph(
                                        "<b>CONNOTE:</b>",
                                        style_left,
                                    ),
                                ],
                                [
                                    Paragraph(
                                        "<b>%s</b>" % (v_FPBookingNumber),
                                        style_left,
                                    ),
                                ],
                            ],
                            rowHeights=[4, 10, 10],
                            style=[
                                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                            ],
                        )
                    ],
                    [
                        Paragraph(
                            "<b>AUTHORITY TO LEAVE</b>",
                            style_center,
                        ),
                        code128.Code128(
                            atl_number,
                            barHeight=9 * mm,
                            barWidth=0.9,
                            humanReadable=False,
                        ),
                        Paragraph(
                            "<font size=%s> <b>%s</b> </font>"
                            % (label_settings["font_size_medium"], atl_number),
                            style_center,
                        ),
                    ]
                    if booking.opt_authority_to_leave
                    else [
                        Paragraph(
                            "",
                            style_center,
                        ),
                    ],
                ],
                [
                    [
                        Table(
                            [
                                [
                                    Paragraph(
                                        "<font size=%s>TO: </font>"
                                        % (label_settings["font_size_large"],),
                                        style_left_large,
                                    ),
                                    Paragraph(
                                        "<font size=%s>%s <br/> %s %s <br/> %s %s %s </font>"
                                        % (
                                            label_settings["font_size_large"],
                                            booking.deToCompanyName or "",
                                            booking.de_To_Address_Street_1 or "",
                                            ("<br/>" + booking.de_To_Address_Street_2)
                                            if booking.de_To_Address_Street_2
                                            else "",
                                            booking.de_To_Address_Suburb or "",
                                            booking.de_To_Address_State or "",
                                            booking.de_To_Address_PostalCode or "",
                                        ),
                                        style_left_large,
                                    ),
                                ],
                            ],
                            colWidths=[
                                30,
                                float(label_settings["label_image_size_width"]) * mm
                                - 40,
                            ],
                            style=[
                                *tableStyle,
                                ("LEFTPADDING", (0, 0), (-1, -1), 2),
                                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                            ],
                        )
                    ],
                    "",
                    "",
                ],
                [
                    Table(
                        [
                            [
                                Paragraph(
                                    "<b>PH: %s</b>" % (booking.de_to_Phone_Main or ""),
                                    style_left,
                                ),
                                Paragraph(
                                    "<b>%s</b>" % (booking.de_To_Address_Suburb or ""),
                                    style_extra_large,
                                ),
                                Paragraph(
                                    "<b>%s</b>"
                                    % (booking.de_To_Address_PostalCode or ""),
                                    style_right,
                                ),
                            ]
                        ],
                        colWidths=[t1_w * 2.5, t1_w * 5.5, t1_w * 2],
                        rowHeights=[8 * mm],
                        style=[
                            *tableStyle,
                            ("LEFTPADDING", (0, 0), (-1, -1), 2),
                            ("RIGHTPADDING", (0, 0), (-1, -1), 2),
                            ("LINEBEFORE", (1, 0), (1, 0), 0.25, colors.black),
                            ("LINEAFTER", (1, 1), (1, 1), 0.25, colors.black),
                            ("VALIGN", (0, 0), (-1, -1), "TOP"),
                        ],
                    ),
                    "",
                    "",
                ],
            ]

            header_length = float(label_settings["header_length"]) * mm
            header = Table(
                data,
                colWidths=[t1_w * 2.5, t1_w * 3, t1_w * 4.5],
                rowHeights=[17 * mm, 19 * mm, 8 * mm],
                style=[
                    *tableStyle,
                    ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.black),
                    ("BOX", (0, 0), (-1, -1), 0.25, colors.black),
                    ("SPAN", (0, 1), (-1, 1)),
                    ("SPAN", (0, 2), (-1, 2)),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ],
            )
            Story.append(header)

            tbl_data = [
                [
                    Paragraph("<b>%s</b>" % ("AU"), style_extra_large),
                    Paragraph(
                        "<b>%s</b>"
                        % (
                            ""
                            if booking.vx_serviceName == "EXP"
                            else (location_info["R1"] or "")
                        ),
                        style_extra_large,
                    ),
                    Paragraph(
                        "<b>%s</b>" % (location_info["R2"] or ""), style_extra_large
                    ),
                    Paragraph("<b></b>", style_extra_large),
                ],
            ]

            shell_table = Table(
                tbl_data,
                colWidths=(
                    t1_w * 2,
                    t1_w * 3,
                    t1_w * 2,
                    t1_w * 3,
                ),
                rowHeights=(18),
                style=tableStyle,
            )

            Story.append(shell_table)
            Story.append(Spacer(4, 4))

            barcode = gen_ReceiverBarcode(booking, location_info)

            qrCodeString = gen_QRcodeString(
                booking,
                booking_line,
                location_info,
                v_FPBookingNumber,
                totalCubic,
                atl_number,
                j,
            )
            d = Drawing(36 * mm, 34 * mm)
            d.add(Rect(0, 0, 0, 0, strokeWidth=1, fillColor=None))
            d.add(QrCodeWidget(value=qrCodeString, barWidth=36 * mm, barHeight=36 * mm))

            tbl_data = [
                [
                    Table(
                        [
                            [
                                code128.Code128(
                                    barcode,
                                    barHeight=30 * mm,
                                    barWidth=0.95,
                                    humanReadable=False,
                                ),
                            ],
                            [
                                Paragraph("<b>%s</b>" % (barcode), style_center),
                            ],
                        ],
                        colWidths=(t1_w * 6),
                        style=tableStyle,
                    ),
                    Spacer(3, 3),
                    d,
                ],
            ]

            barcode_table = Table(
                tbl_data,
                colWidths=(t1_w * 5.5, t1_w * 0.5, t1_w * 4),
                style=[
                    ("ALIGN", (1, 0), (1, 0), "LEFT"),
                    ("ALIGN", (0, 0), (0, 0), "RIGHT"),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("TOPPADDING", (0, 0), (-1, -1), 3),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                    ("LEFTPADDING", (0, 0), (-1, -1), 0),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ],
            )

            Story.append(barcode_table)

            from_table = Table(
                [
                    [
                        Table(
                            [
                                [
                                    Paragraph("FROM: ", style_left_small),
                                    Paragraph(
                                        "%s<br/>%s %s <br/>%s %s"
                                        % (
                                            booking.puCompany or "",
                                            booking.pu_Address_Street_1 or "",
                                            ("<br/>" + booking.pu_Address_street_2)
                                            if booking.pu_Address_street_2
                                            else "",
                                            booking.pu_Address_Suburb or "",
                                            booking.pu_Address_PostalCode or "",
                                        ),
                                        style_left_small,
                                    ),
                                    Paragraph(
                                        "PH:   %s" % (booking.pu_Phone_Main),
                                        style_left_small,
                                    ),
                                ],
                            ],
                            colWidths=[t1_w, t1_w * 6, t1_w * 3],
                            style=[
                                *tableStyle,
                                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                            ],
                        ),
                    ],
                    [
                        Table(
                            [
                                [
                                    Paragraph(
                                        "<b>%s<br/> %s <br/> %s <br/></b>"
                                        % (
                                            booking.b_clientReference_RA_Numbers,
                                            "",
                                            "",
                                        ),
                                        style_left_small,
                                    ),
                                    Paragraph(
                                        "BOOK-IN<br/> NOT BEFORE: %s <br/> NOT AFTER: %s"
                                        % (
                                            "",
                                            "",
                                        ),
                                        style_left_small,
                                    ),
                                ],
                                [
                                    Table(
                                        [
                                            [
                                                Paragraph(
                                                    "DATE: %s"
                                                    % (
                                                        booking.b_dateBookedDate.strftime(
                                                            "%d/%m/%Y"
                                                        )
                                                        if booking.b_dateBookedDate
                                                        else booking.puPickUpAvailFrom_Date.strftime(
                                                            "%d/%m/%Y"
                                                        ),
                                                    ),
                                                    style_left_small,
                                                ),
                                                Paragraph(
                                                    "UNIT: %s"
                                                    % (
                                                        str(
                                                            "CTN"
                                                            if len(
                                                                booking_line.e_type_of_packaging
                                                                or ""
                                                            )
                                                            != 3
                                                            else booking_line.e_type_of_packaging
                                                        ),
                                                    ),
                                                    style_left_small,
                                                ),
                                                Paragraph(
                                                    "ITEM %s OF %s"
                                                    % (
                                                        j,
                                                        totalQty,
                                                    ),
                                                    style_left_small,
                                                ),
                                                Paragraph(
                                                    "WEIGHT: %skg"
                                                    % (
                                                        round(
                                                            booking_line.e_weightPerEach,
                                                            0,
                                                        ),
                                                    ),
                                                    style_left_small,
                                                ),
                                                Paragraph(
                                                    "CUBE: %s"
                                                    % (round(totalCubic, 3),),
                                                    style_left_small,
                                                ),
                                            ]
                                        ],
                                        colWidths=[
                                            t1_w * 2.25,
                                            t1_w * 1.45,
                                            t1_w * 2.05,
                                            t1_w * 2.5,
                                            t1_w * 1.75,
                                        ],
                                        style=tableStyle,
                                    ),
                                    "",
                                ],
                            ],
                            colWidths=[t1_w * 6, t1_w * 4],
                            style=[
                                *tableStyle,
                                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                                ("SPAN", (0, 1), (-1, 1)),
                            ],
                        ),
                    ],
                ],
                colWidths=[float(label_settings["label_image_size_width"]) * mm],
                rowHeights=[11 * mm, 11 * mm],
                style=[
                    *tableStyle,
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.black),
                    ("BOX", (0, 0), (-1, -1), 0.25, colors.black),
                    ("LEFTPADDING", (0, 0), (-1, -1), 2),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 2),
                    ("ABOVEPADDING", (0, 0), (-1, -1), 2),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ],
            )

            Story.append(from_table)
            Story.append(Spacer(1, 3))

            barcode = gen_barcode(booking, v_FPBookingNumber, j)

            tbl_data = [
                [
                    code128.Code128(
                        barcode,
                        barHeight=22.5 * mm,
                        barWidth=1,
                        humanReadable=False,
                    ),
                ],
                [
                    Paragraph("<b>Article ID:%s</b>" % (barcode), style_center),
                ],
            ]

            barcode_table = Table(
                tbl_data,
                colWidths=[t1_w * 10],
                style=tableStyle,
            )

            Story.append(barcode_table)

            Story.append(PageBreak())

            j += 1

    doc.build(Story, onFirstPage=myFirstPage, onLaterPages=myLaterPages)
    file.close()
    logger.info(
        f"#119 [{booking.vx_freight_provider} LABEL] Finished building label... (Booking ID: {booking.b_bookingID_Visual})"
    )
    return filepath, filename
