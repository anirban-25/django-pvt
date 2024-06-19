import os
import logging
from datetime import datetime
from reportlab.lib.enums import TA_JUSTIFY, TA_RIGHT, TA_CENTER, TA_LEFT
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
)
from reportlab.platypus.flowables import (
    Spacer,
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.lib import colors
from django.conf import settings

from api.models import Fp_freight_providers, Dme_manifest_log
from api.common.ratio import _get_weight_amount
from api.fp_apis.utils import gen_consignment_num
from api.helpers.cubic import get_cubic_meter

label_settings = {
    "font_family": "Verdana",
    "font_size_extra_small": "7",
    "font_size_small": "8",
    "font_size_medium": "10",
    "font_size_extra_medium": "12",
    "font_size_large": "16",
    "font_size_extra_large": "26",
    "label_dimension_height": "297",
    "label_dimension_width": "210",
    "label_image_size_height": "260",
    "label_image_size_width": "190",
    "line_height_extra_small": "3",
    "line_height_small": "5",
    "line_height_medium": "6",
    "line_height_large": "8",
    "line_height_extra_large": "12",
    "margin_v": "0",
    "margin_h": "0",
}

if settings.ENV == "local":
    production = False  # Local
else:
    production = True  # Dev

styles = getSampleStyleSheet()
style_right = ParagraphStyle(
    name="right",
    parent=styles["Normal"],
    alignment=TA_RIGHT,
    leading=12,
)
style_left = ParagraphStyle(
    name="left",
    parent=styles["Normal"],
    alignment=TA_LEFT,
    leading=12,
    spaceBefore=0,
)
style_center = ParagraphStyle(
    name="center",
    parent=styles["Normal"],
    alignment=TA_CENTER,
    leading=8,
)
style_center_title = ParagraphStyle(
    name="center_title",
    parent=styles["Normal"],
    alignment=TA_CENTER,
    leading=24,
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
ROWS_PER_PAGE = 20
#####################

logger = logging.getLogger(__name__)

def filter_booking_lines(booking, booking_lines):
    original_lines = []
    scanned_lines = []

    for booking_line in booking_lines:
        if booking.pk_booking_id == booking_line.fk_booking_id:
            if booking_line.packed_status == "original":
                original_lines.append(booking_line)
            elif booking_line.packed_status == "scanned":
                scanned_lines.append(booking_line)

    return scanned_lines or original_lines

def build_manifest(bookings, booking_lines, username, need_truck, timestamp):
    LOG_ID = "[CAMERONS_MANIFEST]"
    fp_name = bookings[0].vx_freight_provider
    fp_info = Fp_freight_providers.objects.get(fp_company_name=fp_name)
    new_manifest_index = fp_info.fp_manifest_cnt

    booking_ids = []

    # start check if pdfs folder exists
    if production:
        local_filepath = f"/opt/s3_public/pdfs/{fp_name.lower()}_au"
    else:
        local_filepath = f"./static/pdfs/{fp_name.lower()}_au"

    if not os.path.exists(local_filepath):
        os.makedirs(local_filepath)
    # end check if pdfs folder exists

    # start loop through data fetched from dme_bookings table
    date = datetime.now().strftime("%Y%m%d") + "_" + datetime.now().strftime("%H%M%S")
    filename = "MANIFEST_" + date + "_m.pdf"
    file = open(local_filepath + filename, "a")
    logger.info(f"#111 [MANIFEST] File full path: {local_filepath}/{filename}")
    # end pdf file name using naming convention

    width = float(label_settings["label_dimension_width"]) * mm
    height = float(label_settings["label_dimension_height"]) * mm
    doc = SimpleDocTemplate(
        f"{local_filepath}/{filename}",
        pagesize=(width, height),
        rightMargin=float(label_settings["margin_h"]) * mm,
        leftMargin=float(label_settings["margin_h"]) * mm,
        topMargin=float(label_settings["margin_v"]) * mm,
        bottomMargin=float(label_settings["margin_v"]) * mm,
    )

    Story = []
    manifest = "#" + str(new_manifest_index).zfill(6)

    width = float(label_settings["label_image_size_width"]) * mm

    # -------------------- Header Part ---------------------------

    tbl_data = [
        [
            Paragraph(
                "<font size=%s><b>Despatch Summary - Sender's Copy</b></font>"
                % (label_settings["font_size_extra_large"],),
                style_center_title,
            ),
            "",
        ],
        [
            Paragraph(
                "<font size=%s>Cameron Interstate</font>"
                % (label_settings["font_size_extra_large"],),
                style_left,
            ),
            Paragraph(
                "<font size=%s>%s</font>"
                % (
                    label_settings["font_size_extra_large"],
                    manifest,
                ),
                style_right,
            ),
        ],
    ]

    header = Table(
        tbl_data,
        colWidths=[width * 0.6, width * 0.4],
        style=[
            ("VALIGN", (0, 0), (-1, -1), "BOTTOM"),
            ("TOPPADDING", (0, -1), (-1, -1), 2),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
            ("SPAN", (0, 0), (1, 0)),
        ],
    )
    Story.append(header)

    Story.append(Spacer(1, 20))

    # -------------------- Consignments Table ---------------------------

    tbl_data = [
        [
            Paragraph(
                "<font size=%s><b>%s</b></font>"
                % (
                    label_settings["font_size_extra_medium"],
                    "Consignments:",
                ),
                style_left,
            ),
            "",
            "",
            "",
            "",
            "",
            "",
        ],
        [
            Paragraph(
                "<font size=%s><b>Con Note # Receiver</b></font>"
                % (label_settings["font_size_medium"],),
                style_left,
            ),
            "",
            Paragraph(
                "<font size=%s><b>Suburb</b></font>"
                % (label_settings["font_size_medium"],),
                style_left,
            ),
            "",
            Paragraph(
                "<font size=%s><b>Customer Ref</b></font>"
                % (label_settings["font_size_medium"],),
                style_left,
            ),
            Paragraph(
                "<font size=%s><b>Chep</b></font>"
                % (label_settings["font_size_medium"],),
                style_right,
            ),
            Paragraph(
                "<font size=%s><b>Los</b></font>"
                % (label_settings["font_size_medium"],),
                style_right,
            ),
        ],
        [
            Paragraph(
                "<font size=%s><b>Reference</b></font>"
                % (label_settings["font_size_medium"],),
                style_left,
            ),
            Paragraph(
                "<font size=%s><b>#Units</b></font>"
                % (label_settings["font_size_medium"],),
                style_left,
            ),
            Paragraph(
                "<font size=%s><b>Logistics Unit</b></font>"
                % (label_settings["font_size_medium"],),
                style_left,
            ),
            Paragraph(
                "<font size=%s><b>Weight</b></font>"
                % (label_settings["font_size_medium"],),
                style_left,
            ),
            Paragraph(
                "<font size=%s><b>Cubic</b></font>"
                % (label_settings["font_size_medium"],),
                style_left,
            ),
            "",
            "",
        ],
    ]

    consignment_table_header = Table(
        tbl_data,
        colWidths=[
            width * 0.2,
            width * 0.1,
            width * 0.2,
            width * 0.1,
            width * 0.2,
            width * 0.1,
            width * 0.1,
        ],
        style=[
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, -1), (-1, -1), 2),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
            ("TOPPADDING", (0, 1), (-1, 1), 4),
            ("SPAN", (0, 1), (1, 1)),
            ("SPAN", (2, 1), (3, 1)),
            ("LINEABOVE", (0, 1), (-1, 1), 2, colors.black),
            ("LINEBELOW", (0, -1), (-1, -1), 2, colors.black),
        ],
    )
    Story.append(consignment_table_header)

    Story.append(Spacer(1, 6))

    tbl_data = []
    tbl_data_row = []
    total_qty = 0
    total_weight = 0
    total_cubic = 0

    for booking in bookings:
        _booking_lines = filter_booking_lines(booking, booking_lines)
        # -------------------- Consignments Table Body ---------------------------

        tbl_data = [
            [
                Paragraph(
                    "<font size=%s>%s  %s</font>"
                    % (
                        label_settings["font_size_medium"],
                        booking.v_FPBookingNumber or "",
                        (booking.deToCompanyName or "")[:30],
                    ),
                    style_left,
                ),
                "",
                Paragraph(
                    "<font size=%s>%s</font>"
                    % (
                        label_settings["font_size_medium"],
                        (booking.de_To_Address_Suburb or "")[:30],
                    ),
                    style_left,
                ),
                "",
                Paragraph(
                    "<font size=%s>%s</font>"
                    % (
                        label_settings["font_size_medium"],
                        booking.b_client_order_num or "",
                    ),
                    style_left,
                ),
                Paragraph(
                    "<font size=%s>%s</font>"
                    % (
                        label_settings["font_size_medium"],
                        "0",
                    ),
                    style_right,
                ),
                Paragraph(
                    "<font size=%s>%s</font>"
                    % (
                        label_settings["font_size_medium"],
                        "0",
                    ),
                    style_right,
                ),
            ],
        ]

        consignment_table_body_booking = Table(
            tbl_data,
            colWidths=[
                width * 0.2,
                width * 0.1,
                width * 0.2,
                width * 0.1,
                width * 0.2,
                width * 0.1,
                width * 0.1,
            ],
            style=[
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 2),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
                ("SPAN", (0, 0), (1, 0)),
                ("SPAN", (2, 0), (3, 0)),
            ],
        )
        Story.append(consignment_table_body_booking)

        tbl_data = []

        for _, line in enumerate(_booking_lines):
            tbl_data_row = [
                Paragraph(
                    "<font size=%s>%s</font>"
                    % (
                        label_settings["font_size_medium"],
                        booking.b_client_order_num or "",
                    ),
                    style_left,
                ),
                Paragraph(
                    "<font size=%s>%s</font>"
                    % (
                        label_settings["font_size_medium"],
                        line.e_qty,
                    ),
                    style_left,
                ),
                Paragraph(
                    "<font size=%s>%s</font>"
                    % (
                        label_settings["font_size_medium"],
                        line.e_item[:20],
                    ),
                    style_left,
                ),
                Paragraph(
                    "<font size=%s>%s</font>"
                    % (
                        label_settings["font_size_medium"],
                        round(line.e_qty * line.e_weightPerEach, 3),
                    ),
                    style_left,
                ),
                Paragraph(
                    "<font size=%s>%s</font>"
                    % (
                        label_settings["font_size_medium"],
                        round(
                            get_cubic_meter(
                                line.e_dimLength,
                                line.e_dimWidth,
                                line.e_dimHeight,
                                line.e_dimUOM,
                            ),
                            3,
                        ),
                    ),
                    style_left,
                ),
                "",
                "",
            ]

            tbl_data.append(tbl_data_row)
            total_qty = total_qty + line.e_qty
            total_weight = total_weight + line.e_qty * line.e_weightPerEach
            total_cubic = total_cubic + get_cubic_meter(
                line.e_dimLength,
                line.e_dimWidth,
                line.e_dimHeight,
                line.e_dimUOM,
                line.e_qty,
            )

        consignment_table_body_lines = Table(
            tbl_data,
            colWidths=[
                width * 0.2,
                width * 0.1,
                width * 0.2,
                width * 0.1,
                width * 0.2,
                width * 0.1,
                width * 0.1,
            ],
            style=[
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, -1), (-1, -1), 2),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, -1), (-1, -1), 2),
            ],
        )
        Story.append(consignment_table_body_lines)

    Story.append(Spacer(1, 6))

    # -------------------- Total Table ---------------------------

    tbl_data = [
        [
            Paragraph(
                "<font size=%s><b>Totals:</b></font>"
                % (label_settings["font_size_extra_medium"],),
                style_left,
            ),
            "",
            "",
            "",
            Paragraph(
                "<font size=%s><b>Chep</b></font>"
                % (label_settings["font_size_medium"],),
                style_right,
            ),
            Paragraph(
                "<font size=%s><b>Los</b></font>"
                % (label_settings["font_size_medium"],),
                style_right,
            ),
        ],
        [
            "",
            "",
            "",
            "",
            Paragraph(
                "<font size=%s>%s</font>"
                % (
                    label_settings["font_size_medium"],
                    "0",
                ),
                style_right,
            ),
            Paragraph(
                "<font size=%s>%s</font>"
                % (
                    label_settings["font_size_medium"],
                    "0",
                ),
                style_right,
            ),
        ],
        [
            Paragraph(
                "<font size=%s><b>Consignments:</b> %s</font>"
                % (
                    label_settings["font_size_medium"],
                    len(bookings),
                ),
                style_left,
            ),
            Paragraph(
                "<font size=%s><b>Units</b></font>"
                % (label_settings["font_size_medium"],),
                style_left,
            ),
            Paragraph(
                "<font size=%s><b>Weight</b></font>"
                % (label_settings["font_size_medium"],),
                style_left,
            ),
            Paragraph(
                "<font size=%s><b>Cubic</b></font>"
                % (label_settings["font_size_medium"],),
                style_left,
            ),
            "",
            "",
        ],
        [
            "",
            Paragraph(
                "<font size=%s>%s</font>"
                % (label_settings["font_size_medium"], total_qty),
                style_left,
            ),
            Paragraph(
                "<font size=%s>%s</font>"
                % (label_settings["font_size_medium"], round(total_weight, 3)),
                style_left,
            ),
            Paragraph(
                "<font size=%s>%s</font>"
                % (label_settings["font_size_medium"], round(total_cubic, 3)),
                style_left,
            ),
            "",
            "",
        ],
    ]

    total_table = Table(
        tbl_data,
        colWidths=[
            width * 0.2,
            width * 0.3,
            width * 0.1,
            width * 0.2,
            width * 0.1,
            width * 0.1,
        ],
        style=[
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, 0), 8),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, -1), (-1, -1), 8),
            ("LINEABOVE", (0, 0), (-1, 0), 1, colors.black),
            ("LINEBELOW", (0, -1), (-1, -1), 1, colors.black),
        ],
    )
    Story.append(total_table)

    # -------------------- Signature Table ---------------------------

    Story.append(Spacer(1, 30))

    tbl_data = [
        [
            Paragraph(
                "<font size=%s>Driver Signature______________________________</font>"
                % (label_settings["font_size_medium"]),
                style_left,
            ),
            Paragraph(
                "<font size=%s>Manifest Date: %s</font>"
                % (
                    label_settings["font_size_large"],
                    bookings[0].b_dateBookedDate.strftime("%d/%m/%Y")
                    if bookings[0].b_dateBookedDate
                    else datetime.today().strftime("%d/%m/%Y"),
                ),
                style_right,
            ),
        ],
    ]

    signature_table = Table(
        tbl_data,
        colWidths=[
            width * 0.5,
            width * 0.5,
        ],
        style=[
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, -1), (-1, -1), 2),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, -1), (-1, -1), 2),
        ],
    )
    Story.append(signature_table)

    doc.build(Story)
    file.close()

    # Add manifest log
    manfiest_log = Dme_manifest_log.objects.create(
        fk_booking_id=bookings[0].pk_booking_id,
        manifest_url=f"{fp_name.lower()}_au/{filename}",
        manifest_number=manifest,
        bookings_cnt=len(bookings),
        is_one_booking=1,
        z_createdByAccount=username,
        need_truck=need_truck,
        freight_provider=fp_name,
        booking_ids=",".join(booking_ids),
    )
    manfiest_log.z_createdTimeStamp = timestamp
    manfiest_log.save()

    fp_info.fp_manifest_cnt = fp_info.fp_manifest_cnt + 1
    fp_info.new_connot_index = fp_info.new_connot_index + len(bookings)
    fp_info.save()

    return filename
