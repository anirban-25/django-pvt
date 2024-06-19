# Python 3.6.6

from datetime import datetime
import math
import pysftp
from api.common.common_times import convert_to_AU_SYDNEY_tz

from api.helpers.cubic import get_cubic_meter

cnopts = pysftp.CnOpts()
cnopts.hostkeys = None
import os
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
from reportlab.platypus.flowables import Spacer, HRFlowable, PageBreak, Flowable
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.graphics.barcode.code128 import Code128
from reportlab.lib import colors

from api.models import Booking_lines, Booking_lines_data
from api.operations.api_booking_confirmation_lines import index as api_bcl
from reportlab.platypus.flowables import KeepInFrame

logger = logging.getLogger("dme_api")

styles = getSampleStyleSheet()
style_left = ParagraphStyle(
    name="left", parent=styles["Normal"], alignment=TA_LEFT, leading=6
)
style_left_header = ParagraphStyle(
    name="left",
    parent=styles["Normal"],
    alignment=TA_LEFT,
    leading=8,
)
style_center = ParagraphStyle(
    name="center", parent=styles["Normal"], alignment=TA_CENTER, leading=6
)
style_right = ParagraphStyle(
    name="right", parent=styles["Normal"], alignment=TA_RIGHT, leading=6
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


def get_centimeter(value, uom="CENTIMETER"):
    _dimUOM = uom.upper()

    if _dimUOM in ["MM", "MILIMETER"]:
        value = value / 10
    elif _dimUOM in ["M", "METER"]:
        value = value * 100

    return round(value, 2)


def build_docket(
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
        f"#110 [ARISTON WIRE DELIVERY DOCKET] Started building docket... (Booking ID: {booking.b_bookingID_Visual}, Lines: {lines})"
    )
    v_FPBookingNumber = pre_data["v_FPBookingNumber"]
    if not lines:
        lines = Booking_lines.objects.filter(fk_booking_id=booking.pk_booking_id)
    
    if not os.path.exists(filepath):
        os.makedirs(filepath)

    filename = f"DME{booking.b_bookingID_Visual}"

    file = open(f"{filepath}/{filename}_docket.pdf", "w")
    logger.info(f"#111 [ARISTON WIRE DELIVERY DOCKET] File full path: {filepath}/{filename}_docket.pdf")

    label_settings = {
        "font_family": "Verdana",
        "font_size_smallest": "3",
        "font_size_extra_small": "4",
        "font_size_slight_small": "5",
        "font_size_small": "6",
        "font_size_extra_medium": "7",
        "font_size_medium": "8",
        "font_size_large_title": "9",
        "font_size_large": "11",
        "font_size_slight_large": "24",
        "font_size_extra_large": "26",
        "label_dimension_length": "100",
        "label_dimension_width": "150",
        "label_image_size_length": "95",
        "label_image_size_width": "130",
        "barcode_dimension_length": "85",
        "barcode_dimension_width": "30",
        "barcode_font_size": "18",
        "line_height_extra_small": "3",
        "line_height_small": "5",
        "line_height_medium": "6",
        "line_height_large": "8",
        "line_height_extra_large": "12",
        "margin_v": "0",
        "margin_h": "0",
        "font_size_footer_units_small": "8",
        "font_size_footer_desc_small": "9",
        "font_size_footer_desc": "10",
        "font_size_footer_units": "12",
        "font_size_footer": "14",
    }

    width = float(label_settings["label_dimension_length"]) * mm
    height = float(label_settings["label_dimension_width"]) * mm

    doc_docket = SimpleDocTemplate(
        f"{filepath}/{filename}_docket.pdf",
        pagesize=(width, height),
        rightMargin=float(label_settings["margin_h"]) * mm,
        leftMargin=float(label_settings["margin_h"]) * mm,
        topMargin=float(label_settings["margin_v"]) * mm,
        bottomMargin=float(label_settings["margin_v"]) * mm,
    )

    width = float(label_settings["label_image_size_length"]) * mm

    totalQty = 0
    if one_page_label:
        lines = [lines[0]]
        totalQty = 1
    else:
        for booking_line in lines:
            totalQty += booking_line.e_qty

    if sscc:
        j = 1 + label_index
        totalQty = sscc_cnt

    Story_docket = []

    logger.info(
        f"#110 [ARISTON WIRE DELIVERY DOCKET] Started building Delivery Docket... (Booking ID: {booking.b_bookingID_Visual})"
    )

    ariston_wire_logo = "./static/assets/logos/ariston_wire.png"
    ariston_wire__img = Image(ariston_wire_logo, 35 * mm, 12 * mm)

    total_weight = 0
    total_cubic = 0
    total_qty = 0

    for line in lines:
        total_weight = total_weight + line.e_qty * line.e_weightPerEach
        total_qty = total_qty + line.e_qty
        total_cubic = total_cubic + get_cubic_meter(
            line.e_dimLength,
            line.e_dimWidth,
            line.e_dimHeight,
            line.e_dimUOM,
            line.e_qty,
        )

    # -------------------- Header part ------------------------ 

    tbl_data = [
        [
            ariston_wire__img,
            Paragraph(
                "<font size=%s><b>Golden Steel International Pty Ltd t/a Ariston Wire</b></font>"
                % (label_settings["font_size_slight_small"]),
                style_left_header,
            ),
        ],
        [
            "",
            Paragraph(
                "<font size=%s>ABN: 32 129 865 238</font>"
                % (label_settings["font_size_extra_small"]),
                style_left,
            ),
        ],
        [
            "",
            Paragraph(
                "<font size=%s>Suite 608, 9 Bronte Road, Bondi Junction NSW 2022 Australia</font>"
                % (label_settings["font_size_extra_small"]),
                style_left,
            ),
        ],
        [
            "",
            Paragraph(
                "<font size=%s>P: 02 9387 4188 E: sales@aristonwire.com.au</font>"
                % (label_settings["font_size_extra_small"]),
                style_left,
            ),
        ],
        [
            "",
            Paragraph(
                "<font size=%s>www.aristonwire.com.au</font>"
                % (label_settings["font_size_extra_small"]),
                style_left,
            ),
        ],
    ]

    header = Table(
        tbl_data,
        colWidths=[width * 0.4, width * 0.6],
        style=[
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("ALIGN", (0, 0), (-1, -1), "LEFT"),
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ("SPAN", (0, 0), (0, 4)),
        ],
    )

    # -------------------- Title part ------------------------ 

    tbl_data = [
        [
            "",
            Paragraph(
                "<font size=%s><b>DELIVERY DOCKET</b></font>"
                % (label_settings["font_size_slight_small"]),
                style_center,
            ),
            Paragraph(
                "<font size=%s><b>%s</b></font>"
                % (
                    label_settings["font_size_slight_small"],
                    booking.b_client_sales_inv_num,
                ),
                style_right,
            ),
        ],
    ]

    title_part = Table(
        tbl_data,
        colWidths=[width * 0.2, width * 0.6, width * 0.2],
        rowHeights=[8],
        style=[
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("ALIGN", (0, 0), (-1, -1), "LEFT"),
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (-1, -1), (-1, -1), 4),
            ("LINEBELOW", (0, 0), (-1, -1), 0.5, colors.black),
            ("LINEABOVE", (0, 0), (-1, -1), 0.5, colors.black),
            ("LINEBEFORE", (0, 0), (0, 0), 0.5, colors.black),
            ("LINEAFTER", (-1, 0), (-1, 0), 0.5, colors.black),
        ],
    )

    # -------------------- Pick Up Section ------------------------

    pick_up_section = Table(
        [
            [
                Paragraph(
                    "<font size=%s><b>Pick Up By:</b></font>"
                    % (label_settings["font_size_slight_small"],),
                    style_left,
                ),
                Paragraph(
                    "<font size=%s>%s</font>"
                    % (
                        label_settings["font_size_slight_small"],
                        (booking.pu_Contact_F_L_Name or "")[:30],
                    ),
                    style_left,
                ),
            ],
            [
                Paragraph(
                    "<font size=%s><b>Consignee:</b></font>"
                    % (label_settings["font_size_slight_small"],),
                    style_left,
                ),
                Paragraph(
                    "<font size=%s><b>%s</b></font>"
                    % (
                        label_settings["font_size_slight_small"],
                        (booking.puCompany or "")[:30],
                    ),
                    style_left,
                ),
            ],
            [
                "",
                Paragraph(
                    "<font size=%s><b>%s</b></font>"
                    % (
                        label_settings["font_size_slight_small"],
                        (booking.pu_Address_Street_1 or "")[:30],
                    ),
                    style_left,
                ),
            ],
            [
                "",
                Paragraph(
                    "<font size=%s><b>%s, %s, %s</b></font>"
                    % (
                        label_settings["font_size_slight_small"],
                        (booking.pu_Address_Suburb or "")[:30],
                        booking.pu_Address_State or "",
                        booking.pu_Address_PostalCode or "",
                    ),
                    style_left,
                ),
            ],
            [
                Paragraph(
                    "<font size=%s><b>Contact:   Tel:</b> %s</font>"
                    % (
                        label_settings["font_size_slight_small"],
                        (booking.pu_Phone_Main or "")[:30],
                    ),
                    style_left,
                ),
                "",
            ],
            [
                Paragraph(
                    "<font size=%s><b>Note: </b> Please quote reference number on arrival</font>"
                    % (label_settings["font_size_slight_small"],),
                    style_left,
                ),
                "",
            ],
        ],
        colWidths=[
            width * 0.15,
            width * 0.4,
        ],
        rowHeights=[8, 8, 8, 8, 10, 10],
        style=[
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("ALIGN", (0, 0), (-1, -1), "LEFT"),
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ("SPAN", (0, 4), (1, 4)),
            ("SPAN", (0, 5), (1, 5)),
            ("LINEBELOW", (0, -1), (-1, -1), 0.5, colors.black),
            ("LINEABOVE", (0, 0), (-1, 0), 0.5, colors.black),
            ("LINEBEFORE", (0, 0), (0, -1), 0.5, colors.black),
            ("LINEAFTER", (-1, 0), (-1, -1), 0.5, colors.black),
            ("BOTTOMPADDING", (0, -1), (-1, -1), 2),
            ("TOPPADDING", (0, 0), (-1, 0), 2),
            ("LEFTPADDING", (0, 0), (0, -1), 2),
            ("RIGHTPADDING", (-1, 0), (-1, -1), 2),
        ],
    )    

    # -------------------- Delivery From  Section ------------------------

    delivery_from_section = Table(
        [
            [
                Paragraph(
                    "<font size=%s>Deliver From:</font>"
                    % (label_settings["font_size_slight_small"]),
                    style_left,
                ),
            ],
            [
                Paragraph(
                    "<font size=%s><b>%s</b></font>"
                    % (
                        label_settings["font_size_extra_small"],
                        (booking.deToCompanyName or "")[:30],
                    ),
                    style_left,
                ),
            ],
            [
                Paragraph(
                    "<font size=%s><b>%s</b></font>"
                    % (
                        label_settings["font_size_extra_small"],
                        (booking.de_To_Address_Street_1 or "")[:30],
                    ),
                    style_left,
                ),
            ],
            [
                Paragraph(
                    "<font size=%s><b>%s, %s, %s</b></font>"
                    % (
                        label_settings["font_size_extra_small"],
                        (booking.de_To_Address_Suburb or "")[:30],
                        booking.de_To_Address_State or "",
                        booking.de_To_Address_PostalCode or "",
                    ),
                    style_left,
                ),
            ],
            [
                Paragraph(
                    "<font size=%s><b>Contact: %s</b></font>"
                    % (
                        label_settings["font_size_extra_small"],
                        (booking.de_to_Phone_Main or "")[:30],
                    ),
                    style_left,
                ),
            ],
        ],
        colWidths=[width * 0.4],
        style=[
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ],
    )

    # -------------------- Date  Section ------------------------

    date_section = Table(
        [
            [
                Paragraph(
                    "<font size=%s><b>Date: </b></font>"
                    % (label_settings["font_size_extra_small"]),
                    style_left,
                ),
                Paragraph(
                    "<font size=%s>%s</font>"
                    % (
                        label_settings["font_size_extra_small"],
                        booking.b_dateBookedDate.strftime("%d/%m/%Y")
                        if booking.b_dateBookedDate
                        else "",
                    ),
                    style_left,
                ),
            ],
            [
                Paragraph(
                    "<font size=%s><b>Customer PO: </b></font>"
                    % (label_settings["font_size_extra_small"]),
                    style_left,
                ),
                Paragraph(
                    "<font size=%s>%s</font>"
                    % (
                        label_settings["font_size_extra_small"],
                        "5723PH", #hardcoded
                    ),
                    style_left,
                ),
            ],
            [
                Paragraph(
                    "<font size=%s><b>Reference No: </b></font>"
                    % (label_settings["font_size_extra_small"]),
                    style_left,
                ),
                Paragraph(
                    "<font size=%s>%s</font>"
                    % (
                        label_settings["font_size_extra_small"],
                        booking.b_client_sales_inv_num,
                    ),
                    style_left,
                ),
            ],
        ],
        colWidths=[width * 0.2, width * 0.2],
        style=[
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ("LINEBELOW", (0, -1), (-1, -1), 0.5, colors.black),
            ("LINEABOVE", (0, 0), (-1, 0), 0.5, colors.black),
            ("LINEBEFORE", (0, 0), (0, -1), 0.5, colors.black),
            ("LINEAFTER", (-1, 0), (-1, -1), 0.5, colors.black),
            ("BOTTOMPADDING", (0, -1), (-1, -1), 2),
            ("TOPPADDING", (0, 0), (-1, 0), 2),
            ("LEFTPADDING", (0, 0), (0, -1), 2),
            ("RIGHTPADDING", (-1, 0), (-1, -1), 2),
        ],
    )

    # -------------------- Address Part ------------------------

    address_part = Table(
        [
            [pick_up_section, "", delivery_from_section],
            ["", "", date_section],
        ],
        colWidths=[width * 0.55, width * 0.05, width * 0.4],
        style=[
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ("SPAN", (0, 0), (0, -1)),
        ],
    )

    # ----------------------- Warehouse Part -----------------------

    tbl_data = [
        [
            Paragraph(
                "<font size=%s><b>WAREHOUSE TO COMPLETE</b></font>"
                % (label_settings["font_size_slight_small"]),
                style_center,
            ),
        ],
        [
            Paragraph(
                "<font size=%s>Picked and in good condition</font>"
                % (label_settings["font_size_extra_small"]),
                style_left,
            ),
            Paragraph(
                "<font size=%s>Checked and in good condition</font>"
                % (label_settings["font_size_extra_small"]),
                style_left,
            ),
        ],
        [
            Paragraph(
                "<font size=%s>Picked by:</font>"
                % (label_settings["font_size_extra_small"]),
                style_left,
            ),
            Paragraph(
                "<font size=%s>Checked by:</font>"
                % (label_settings["font_size_extra_small"]),
                style_left,
            ),
        ],
        [
            Paragraph(
                "<font size=%s>Date:</font>"
                % (label_settings["font_size_extra_small"]),
                style_left,
            ),
            Paragraph(
                "<font size=%s>Date:</font>"
                % (label_settings["font_size_extra_small"]),
                style_left,
            ),
        ],
        [
            Paragraph(
                "<font size=%s>Warehouse:</font>"
                % (label_settings["font_size_extra_small"]),
                style_left,
            ),
            Table([
                    [                    
                        Paragraph(
                            "<font size=%s>This area was inspected and found clean and clear of debris by:</font>"
                            % (label_settings["font_size_extra_small"]),
                            style_left,
                        ),                
                    ],
                    [
                        Paragraph(
                            "<font size=%s>Employee</font>"
                            % (label_settings["font_size_extra_small"]),
                            style_right,
                        ),
                    ],
                ],
                style=[
                    ("VALIGN", (0, 0), (-1, -1), "CENTER"),
                    ("TOPPADDING", (0, 0), (-1, -1), 0),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                    ("LEFTPADDING", (0, 0), (-1, -1), 0),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                    ("TOPPADDING", (-1, -1), (-1, -1), 2),
                ],
            )
        ],
    ]

    warehouse_part = Table(
        tbl_data,
        colWidths=[width * 0.5, width * 0.5],
        style=[
            ("VALIGN", (0, 0), (-1, -1), "CENTER"),
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            (
                "BACKGROUND",
                (0, 0),
                (-1, 0),
                colors.Color(red=237 / 255, green=237 / 255, blue=237 / 255),
            ),
            ("GRID", (0, 0), (-1, -1), 0.5, "black"),
            ("SPAN", (0, 0), (-1, 0)),
        ],
    )

    # ----------------------- Transporter Part -----------------------

    tbl_data = [
        [
            Paragraph(
                "<font size=%s><b>TRANSPORTER TO COMPLETE</b></font>"
                % (label_settings["font_size_slight_small"]),
                style_center,
            ),
        ],
        [
            Paragraph(
                "<font size=%s>CHAIN OF RESPONSIBILITY</font>"
                % (label_settings["font_size_slight_small"]),
                style_left,
            ),
            "",
            "",
            Paragraph(
                "<font size=%s>Driver to sign below<br/>(please tick the correct box)</font>"
                % (label_settings["font_size_extra_small"]),
                style_center,
            ),
            "",
        ],
        [
            "",
            "",
            "",
            Paragraph(
                "<font size=%s>YES</font>"
                % (label_settings["font_size_extra_small"]),
                style_center,
            ),
            Paragraph(
                "<font size=%s>NO</font>"
                % (label_settings["font_size_extra_small"]),
                style_center,
            ),
        ],
        [
            Paragraph(
                "<font size=%s>I have accepted delivery of the load specified and have been provided with sufficient information to ensure that the consignment will not<br/> \
                    result in a breach of the mass or dimension limits of its vehicle</font>"
                % (label_settings["font_size_smallest"]),
                style_left,
            ),
            "",
            "",
            "",
            "",
        ],
        [
            Paragraph(
                "<font size=%s>I understand and will abide by Ariston Wire and customer's condition of entry, including WHS requirements</font>"
                % (label_settings["font_size_smallest"]),
                style_left,
            ),
            "",
            "",
            "",
            "",
        ],
        [
            Paragraph(
                "<font size=%s>I have had the legally required rest period prior to the commencement of this task</font>"
                % (label_settings["font_size_smallest"]),
                style_left,
            ),
            "",
            "",
            "",
            "",
        ],
        [
            Paragraph(
                "<font size=%s>I will complete the specified journey while operating within all regulated speed limits, observe all traffic rules and regulations, and have \
                    mandatory rest periods during the journey</font>"
                % (label_settings["font_size_smallest"]),
                style_left,
            ),
            "",
            "",
            "",
            "",
        ],
        [
            Paragraph(
                "<font size=%s>The load will be legally loaded, adequately and legally restrained in accordance with applicable guidelines and I understand that each and\
                    every item is to be strapped for transport</font>"
                % (label_settings["font_size_smallest"]),
                style_left,
            ),
            "",
            "",
            "",
            "",
        ],
        [
            Paragraph(
                "<font size=%s>I have sufficient driving hours to perform the task in the time allocated</font>"
                % (label_settings["font_size_smallest"]),
                style_left,
            ),
            "",
            "",
            "",
            "",
        ],
        [
            Paragraph(
                "<font size=%s>I am fit to undertake the trip and am free from the effects of drugs and alcoho</font>"
                % (label_settings["font_size_smallest"]),
                style_left,
            ),
            "",
            "",
            "",
            "",
        ],
        [
            Paragraph(
                "<font size=%s>I am suitably licensed and my vehicle is registered and roadworthy</font>"
                % (label_settings["font_size_smallest"]),
                style_left,
            ),
            "",
            "",
            "",
            "",
        ],
        [
            Paragraph(
                "<font size=%s>Name:</font>"
                % (label_settings["font_size_smallest"]),
                style_left,
            ),
            Paragraph(
                "<font size=%s>Date:</font>"
                % (label_settings["font_size_smallest"]),
                style_left,
            ),
            Paragraph(
                "<font size=%s>Vehicle Rego:</font>"
                % (label_settings["font_size_smallest"]),
                style_left,
            ),
            "",
            "",
        ],
        [
            Paragraph(
                "<font size=%s>Transport Company:</font>"
                % (label_settings["font_size_smallest"]),
                style_left,
            ),
            Paragraph(
                "<font size=%s>Signature:</font>"
                % (label_settings["font_size_smallest"]),
                style_left,
            ),
            "",
            "",
            "",
        ],
    ]

    transporter_part = Table(
        tbl_data,
        colWidths=[
            width * 0.5,
            width * 0.2,
            width * 0.06,
            width * 0.12,
            width * 0.12,
        ],
        rowHeights=[12, 12, 8, 12, 8, 12, 12, 12, 8, 8, 8, 8, 8],
        style=[
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            (
                "BACKGROUND",
                (0, 0),
                (-1, 0),
                colors.Color(red=237 / 255, green=237 / 255, blue=237 / 255),
            ),
            ("GRID", (0, 0), (-1, -1), 0.5, "black"),
            ("SPAN", (0, 0), (-1, 0)),
            ("SPAN", (0, 1), (2, 2)),
            ("SPAN", (0, 3), (2, 3)),
            ("SPAN", (0, 4), (2, 4)),
            ("SPAN", (0, 5), (2, 5)),
            ("SPAN", (0, 6), (2, 6)),
            ("SPAN", (0, 7), (2, 7)),
            ("SPAN", (0, 8), (2, 8)),
            ("SPAN", (0, 9), (2, 9)),
            ("SPAN", (0, 10), (2, 10)),
            ("SPAN", (3, 1), (4, 1)),
            ("SPAN", (2, 11), (4, 11)),
            ("SPAN", (1, 12), (4, 12)),
        ],
    )

    # ----------------------- Customer Part -----------------------

    tbl_data = [
        [
            Paragraph(
                "<font size=%s><b>CUSTOMER TO COMPLETE</b></font>"
                % (label_settings["font_size_slight_small"]),
                style_center,
            ),
        ],
        [
            Paragraph(
                "<font size=%s>Goods received in good order</font>"
                % (label_settings["font_size_smallest"]),
                style_left,
            ),
        ],
        [
            Paragraph(
                "<font size=%s>No credits claims considered unless notified within two (2) days of receipt</font>"
                % (label_settings["font_size_smallest"]),
                style_left,
            ),
        ],
        [
            Paragraph(
                "<font size=%s>Name:</font>"
                % (label_settings["font_size_smallest"]),
                style_left,
            ),
            Paragraph(
                "<font size=%s>Date:</font>"
                % (label_settings["font_size_smallest"]),
                style_left,
            ),
        ],
        [
            Paragraph(
                "<font size=%s>Signature</font>"
                % (label_settings["font_size_smallest"]),
                style_left,
            ),
            "",
        ],
    ]

    customer_part = Table(
        tbl_data,
        colWidths=[width * 0.5, width * 0.5],
        style=[
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            (
                "BACKGROUND",
                (0, 0),
                (-1, 0),
                colors.Color(red=237 / 255, green=237 / 255, blue=237 / 255),
            ),
            ("GRID", (0, 0), (-1, -1), 0.5, "black"),
            ("SPAN", (0, 0), (-1, 0)),
            ("SPAN", (0, 1), (-1, 1)),
            ("SPAN", (0, 2), (-1, 2)),
            ("SPAN", (1, 3), (1, 4)),
        ],
    )

    page_per_rows = 5
    page_count = int((len(lines) - 1) / page_per_rows) + 1

    for j in range(0, len(lines), page_per_rows):
        segment_lines = lines[j:j+page_per_rows]

        # ----------------------- Lines Part -------------------------

        tbl_data = [
            [
                Paragraph(
                    "<font size=%s><b>Code</b></font>"
                    % (label_settings["font_size_extra_small"],),
                    style_center,
                ),
                Paragraph(
                    "<font size=%s><b>Description</b></font>"
                    % (label_settings["font_size_extra_small"],),
                    style_left,
                ),
                Paragraph(
                    "<font size=%s><b>Unit</b></font>"
                    % (label_settings["font_size_extra_small"],),
                    style_center,
                ),
                "",
                Paragraph(
                    "<font size=%s><b>PACK</b></font>"
                    % (label_settings["font_size_extra_small"],),
                    style_center,
                ),
                "",
                "",
                Paragraph(
                    "<font size=%s><b>Dimensions cms</b></font>"
                    % (label_settings["font_size_extra_small"],),
                    style_center,
                ),
            ],
            [
                "",
                "",
                Paragraph(
                    "<font size=%s><b>Qty</b></font>"
                    % (label_settings["font_size_extra_small"],),
                    style_center,
                ),
                Paragraph(
                    "<font size=%s><b>UOM</b></font>"
                    % (label_settings["font_size_extra_small"],),
                    style_center,
                ),
                Paragraph(
                    "<font size=%s><b>Qty</b></font>"
                    % (label_settings["font_size_extra_small"],),
                    style_center,
                ),
                Paragraph(
                    "<font size=%s><b>UOM</b></font>"
                    % (label_settings["font_size_extra_small"],),
                    style_center,
                ),
                Paragraph(
                    "<font size=%s><b>kg</b></font>"
                    % (label_settings["font_size_extra_small"],),
                    style_center,
                ),
                "",
            ],
        ]
        tbl_data_row = []
        rowHeights = [8, 8]

        for line in segment_lines:
            tbl_data_row = [
                Paragraph(
                    "<font size=%s>%s</font>"
                    % (label_settings["font_size_extra_small"], line.e_type_of_packaging),
                    style_left,
                ),
                Paragraph(
                    "<font size=%s>%s</font>"
                    % (label_settings["font_size_extra_small"], line.e_item),
                    style_left,
                ),
                Paragraph(
                    "<font size=%s>%s</font>"
                    % (label_settings["font_size_extra_small"], line.e_qty),
                    style_center,
                ),
                Paragraph(
                    "<font size=%s>%s</font>"
                    % (label_settings["font_size_extra_small"], "each"),
                    style_center,
                ),
                Paragraph(
                    "<font size=%s>%s</font>"
                    % (label_settings["font_size_extra_small"], line.e_qty),
                    style_center,
                ),
                Paragraph(
                    "<font size=%s>%s</font>"
                    % (label_settings["font_size_extra_small"], "each"),
                    style_center,
                ),
                Paragraph(
                    "<font size=%s>%s</font>"
                    % (
                        label_settings["font_size_extra_small"],
                        round(line.e_qty * line.e_weightPerEach, 2),
                    ),
                    style_center,
                ),            
                Paragraph(
                    "<font size=%s>%s x %s x %s</font>"
                    % (
                        label_settings["font_size_smallest"],
                        get_centimeter(line.e_dimLength, line.e_dimUOM),
                        get_centimeter(line.e_dimWidth, line.e_dimUOM),
                        get_centimeter(line.e_dimHeight, line.e_dimUOM),
                    ),
                    style_center,
                ),
            ]
            tbl_data.append(tbl_data_row)
            rowHeights.append(8 * math.ceil(len(line.e_item) / 40))
        if int(j / page_per_rows) + 1 == page_count:
            tbl_data.append(
                [
                    "",
                    "",
                    "",
                    "",
                    "",
                    Paragraph(
                        "<font size=%s><b>TOTAL:</b></font>"
                        % (label_settings["font_size_extra_small"],),
                        style_center,
                    ),
                Paragraph(
                        "<font size=%s><b>%s</b></font>"
                        % (
                            label_settings["font_size_extra_small"],
                            round(total_weight, 2),
                        ),
                        style_center,
                    ),
                    "",
                ]
            )
            rowHeights.append(8)
        lines_part = Table(
            tbl_data,
            colWidths=[
                width * 0.1,
                width * 0.25,
                width * 0.1,
                width * 0.1,
                width * 0.1,
                width * 0.1,
                width * 0.1,
                width * 0.15,
            ],
            rowHeights=rowHeights,
            style=[
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("TOPPADDING", (0, 0), (-1, -1), 2),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                ("LEFTPADDING", (0, 0), (-1, -1), 2),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("LINEBELOW", (0, -1), (-1, -1), 0.5, colors.black),
                ("LINEABOVE", (0, 0), (-1, 0), 0.5, colors.black),
                ("LINEBEFORE", (0, 0), (-1, -1), 0.5, colors.black),
                ("LINEAFTER", (0, 0), (-1, -1), 0.5, colors.black),
                ("LINEBELOW", (0, 2), (-1, -2), 0.5, colors.gray),
                ("LINEABOVE", (0, 0), (-1, 2), 0.5, colors.black),
                ("SPAN", (0, 0), (0, 1)),
                ("SPAN", (1, 0), (1, 1)),
                ("SPAN", (2, 0), (3, 0)),
                ("SPAN", (4, 0), (6, 0)),
                ("SPAN", (7, 0), (7, 1)),
                ("VALIGN", (7, 0), (7, 0), "MIDDLE"),
            ],
        )          

        # -------------------- Footer Section ------------------------

        footer_padding = 40 - len(segment_lines) * 8 if len(segment_lines) < 5 else 4

        footer = Table(
            [
                [
                    Paragraph(
                        "<font size=%s>%s</font> "
                        % (
                            label_settings["font_size_extra_small"],
                            datetime.now().strftime("%H:%M:%S"),
                        ),
                        style_left,
                    ),
                    Paragraph(
                        "<font size=%s>Page %s of %s</font>"
                        % (label_settings["font_size_extra_small"], (int(j / page_per_rows) + 1), page_count),
                        style_center,
                    ),
                    Paragraph(
                        "<font size=%s>%s</font> "
                        % (
                            label_settings["font_size_extra_small"],
                            datetime.now().strftime("%d/%m/%Y"),
                        ),
                        style_right,
                    ),
                ],
            ],
            colWidths=[width * 0.2, width * 0.6, width * 0.2],
            style=[
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), footer_padding),
            ],
        )



        # ------------------------- Wrapper -----------------------------

        wrapper = Table(
            [
                [header],
                [Spacer(1, 2)],
                [title_part],
                [Spacer(1, 4)],
                [address_part],
                [Spacer(1, 4)],
                [lines_part],
                [Spacer(1, 2)],
                [warehouse_part],
                [Spacer(1, 1)],
                [transporter_part],
                [Spacer(1, 1)],
                [customer_part],
                [footer],
            ],
            colWidths=[width],
            style=[
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ],
        )

        Story_docket.append(wrapper)

        Story_docket.append(PageBreak())

    doc_docket.build(
        Story_docket, onFirstPage=myFirstPage, onLaterPages=myLaterPages
    )

    # end writting data into pdf file
    file.close()
    logger.info(
        f"#119 [ARISTON WIRE DELIVERY DOCKET] Finished building docket... (Booking ID: {booking.b_bookingID_Visual})"
    )
    return filepath, f"{filename}.pdf"