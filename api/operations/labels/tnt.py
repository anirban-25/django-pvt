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

from api.models import Booking_lines, FPRouting
from api.helpers.cubic import get_cubic_meter
from api.operations.api_booking_confirmation_lines import index as api_bcl
from api.common.ratio import _get_dim_amount, _get_weight_amount

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

style_uppercase = ParagraphStyle(
    name="uppercase",
    parent=styles["Normal"],
    alignment=TA_LEFT,
    leading=9,
    spaceBefore=0,
    spaceAfter=0,
    textTransform="uppercase",
)

style_uppercase_lg = ParagraphStyle(
    name="uppercase",
    parent=styles["Normal"],
    alignment=TA_LEFT,
    leading=12,
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


def gen_barcode(booking, booking_lines, line_index, sscc_cnt):
    is_tiny_label = booking.b_client_name == "Tempo Big W"
    TT = "00" if is_tiny_label else "11"
    CCCCCC = "132214"  # DME
    item_index = str(line_index).zfill(3)
    postal_code = str(booking.de_To_Address_PostalCode)
    # label_code = f"{str(booking.b_bookingID_Visual).zfill(9)}{item_index}"
    label_code = f"6104{TT}{CCCCCC}{str(booking.b_bookingID_Visual).zfill(9)}{item_index}{postal_code.zfill(5)}0"
    api_bcl.create(booking, [{"label_code": label_code}])
    return label_code


def gen_itm(booking, booking_lines, line_index, sscc_cnt):
    is_tiny_label = booking.b_client_name == "Tempo Big W"
    TT = "00" if is_tiny_label else "11"
    CCCCCC = "132214"  # DME
    item_index = str(line_index).zfill(3)
    label_code = f"{TT}{CCCCCC}{str(booking.b_bookingID_Visual).zfill(9)}{item_index}"

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
        f"#110 [TNT LABEL] Started building label... (Booking ID: {booking.b_bookingID_Visual}, Lines: {lines})"
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
    logger.info(f"#111 [TNT LABEL] File full path: {filepath}/{filename}")
    # end pdf file name using naming convention

    if not lines:
        lines = Booking_lines.objects.filter(fk_booking_id=booking.pk_booking_id)

    # label_settings = get_label_settings( 146, 104 )[0]

    is_tiny_label = booking.b_client_name == "Tempo Big W"

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
        "barcode_dimension_height": "35",
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

    tnt_logo = "./static/assets/logos/tnt_fedex_logo.png"
    tnt_img = Image(tnt_logo, 30 * mm, 6.6 * mm)

    dme_logo = "./static/assets/logos/dme.png"
    dme_img = Image(dme_logo, 30 * mm, 7.7 * mm)

    Story = []
    j = 1

    # Get routing_group with vx_service_name
    # routing_group = None
    # if booking.vx_serviceName == "Road Express":
    #     routing_group = "EXP"
    # elif booking.vx_serviceName in [
    #     "09:00 Express",
    #     "10:00 Express",
    #     "12:00 Express",
    #     "Overnight Express",
    #     "PAYU - Satchel",
    #     "ONFC Satchel",
    # ]:
    #     routing_group = "PRI"
    # elif booking.vx_serviceName in [
    #     "Technology Express - Sensitive Express",
    #     "Sensitive Express",
    #     "Fashion Delivery",
    # ]:
    #     routing_group = "TE"

    """
    Let's assume service group EXP
    Using the D records relating to that service group, establish the origin depot thaservices the consignment’s origin postcode.
    This should appear in section 3 of the routing label preceded by “Ex “.
    """
    crecords = FPRouting.objects.filter(
        freight_provider=12,
        dest_suburb=booking.de_To_Address_Suburb,
        dest_postcode=booking.de_To_Address_PostalCode,
        dest_state=booking.de_To_Address_State,
        data_code="C"
        # routing_group=routing_group,
    ).only("orig_depot_except", "gateway", "onfwd", "sort_bin")

    routing = None
    orig_depot = ""
    if crecords.exists():
        drecord = (
            FPRouting.objects.filter(
                freight_provider=12,
                orig_postcode=booking.pu_Address_PostalCode,
                # routing_group=routing_group,
                orig_depot__isnull=False,
                data_code="D",
            )
            .only("orig_depot")
            .first()
        )

        if drecord:
            orig_depot = drecord.orig_depot
            for crecord in crecords:
                if crecord.orig_depot_except == drecord.orig_depot:
                    routing = crecord
                    break

        if not routing:
            routing = (
                FPRouting.objects.filter(
                    freight_provider=12,
                    dest_suburb=booking.de_To_Address_Suburb,
                    dest_postcode=booking.de_To_Address_PostalCode,
                    dest_state=booking.de_To_Address_State,
                    orig_depot_except__isnull=True,
                    data_code="C"
                    # routing_group=routing_group,
                )
                .only("orig_depot_except", "gateway", "onfwd", "sort_bin")
                .first()
            )

        logger.info(
            f"#113 [TNT LABEL] Found FPRouting: {routing}, {routing.gateway}, {routing.onfwd}, {routing.sort_bin}, {orig_depot}"
        )
    else:
        logger.info(
            f"#114 [TNT LABEL] FPRouting does not exist: {booking.de_To_Address_Suburb}, {booking.de_To_Address_PostalCode}, {booking.de_To_Address_State}"
        )

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
                    Paragraph(
                        "<font size=%s><b>via %s  to  %s</b></font>"
                        % (
                            16,
                            pre_data["routing"].gateway,
                            pre_data["routing"].onfwd,
                        ),
                        style_right,
                    ),
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
                            16 if len(booking.vx_serviceName) < 12 else 9,
                            booking.vx_serviceName,
                        ),
                        style_left,
                    ),
                    Paragraph(
                        "<font size=%s><b>%s</b></font><font size=%s><b>%s</b></font>"
                        % (8, "Sort bin:", 16, pre_data["routing"].sort_bin),
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
                        % (9, datetime.datetime.now().strftime("%d-%m-%Y")),
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
                            e_Total_KG_weight or "",
                            booking_line.e_weightUOM or "KG",
                        ),
                        style_left,
                    ),
                    Paragraph(
                        "<font size=%s><b>%s</b></font>"
                        % (9, "Ex " + pre_data["orig_depot"]),
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
                > 25
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
                        style_uppercase_lg,
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
                            style_uppercase_lg,
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
                        style_uppercase_lg,
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
                        style_uppercase_lg,
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
                        style_uppercase_lg,
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
                            "<font size=%s>%s, %s, %s, %s, %s, %s</font>"
                            % (
                                8,
                                booking.puCompany or "",
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
                            "<font size=%s>%s, %s, %s, %s, %s</font>"
                            % (
                                8,
                                booking.puCompany or "",
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

            # Gap/RA
            gap_ras = []
            if pre_data["lines_data_cnt"] > 0:
                for line_data in pre_data["lines_data"]:
                    if (
                        line_data.fk_booking_lines_id
                        == booking_line.pk_booking_lines_id
                    ):
                        gap_ras.append(line_data.gap_ra)

            tbl_data1 = [
                [
                    Paragraph(
                        "<font size=%s><b>Senders Ref:</b> %s</font>"
                        % (
                            8,
                            ",".join(gap_ras)
                            if gap_ras
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
            Story.append(Spacer(1, 2))

            special_instruction = booking.pu_pickup_instructions_address or ""

            if special_instruction:
                special_instruction = f"{special_instruction}, {booking.de_to_PickUp_Instructions_Address or ''}"
            else:
                special_instruction = booking.de_to_PickUp_Instructions_Address or ""

            tbl_data1 = [
                [
                    Paragraph(
                        "<font size=%s><b>%s</b></font>" % (9, "Special Instructions:"),
                        style_center,
                    ),
                ],
                [
                    Paragraph(
                        "<font size=%s><b>%s</b></font>" % (7, special_instruction),
                        style_center,
                    ),
                ],
            ]

            t1 = Table(
                tbl_data1,
                colWidths=(float(label_settings["label_image_size_length"]) * mm),
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
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("TOPPADDING", (0, 0), (-1, -1), 0),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                    ("BOTTOMBORDER", (0, 0), (-1, -1), 0),
                    ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ],
            )

            Story.append(shell_table)
            Story.append(Spacer(1, 2))

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
                            booking.de_To_Address_Street_1 or "",
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
                        "<font size=%s>%s</font> "
                        % (
                            label_settings["font_size_normal"],
                            booking.de_To_Address_Suburb or "",
                        ),
                        style_uppercase,
                    ),
                ],
                [
                    Paragraph(
                        "<font size=%s>%s %s</font> "
                        % (
                            label_settings["font_size_normal"],
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
                            booking_line.e_weightPerEach * booking_line.e_qty or "",
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
                        "<font size=%s>%s</font> "
                        % (
                            label_settings["font_size_normal"],
                            booking.pu_Address_Suburb or "",
                        ),
                        style_uppercase,
                    ),
                ],
                [
                    Paragraph(
                        "<font size=%s>%s %s</font> "
                        % (
                            label_settings["font_size_normal"],
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

            barcode = gen_barcode(booking, lines, j, sscc_cnt)

            tbl_data = (
                [[code128.Code128(barcode, barWidth=0.91, barHeight=21 * mm)]]
                if is_tiny_label
                else [[code128.Code128(barcode, barWidth=1.1, barHeight=12 * mm)]]
            )

            t1 = Table(
                tbl_data,
                colWidths=((float(label_settings["label_image_size_length"])) * mm),
                style=[
                    ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                    ("VALIGN", (0, 0), (0, -1), "TOP"),
                    ("TOPPADDING", (0, 0), (-1, -1), 5),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                    ("LEFTPADDING", (0, 0), (0, -1), 0),
                    ("RIGHTPADDING", (0, 0), (0, -1), 0),
                ],
            )

            Story.append(t1)
            Story.append(Spacer(1, 5))

            fp_color_code = pre_data["color_code"] or "808080"

            tbl_data1 = [[tnt_img], [""]]

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

            tbl_data1 = [[dme_img, "", t1]]

            t1 = Table(
                tbl_data1,
                colWidths=(
                    float(label_settings["label_dimension_length"]) * (3 / 10) * mm,
                    float(label_settings["label_dimension_length"]) * (2 / 10) * mm,
                    float(label_settings["label_dimension_length"]) * (5 / 10) * mm,
                ),
                rowHeights=(float(label_settings["line_height_large"]) * 3 / 2 * mm),
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
