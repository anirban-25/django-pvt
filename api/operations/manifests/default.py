import os
import logging
from datetime import datetime
from reportlab.lib.enums import TA_JUSTIFY, TA_RIGHT, TA_CENTER, TA_LEFT
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Image,
    PageBreak,
    Table,
)
from reportlab.platypus.flowables import (
    Spacer,
    HRFlowable,
    PageBreak,
    Flowable,
    TopPadder,
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
    "font_size_large": "18",
    "font_size_extra_large": "32",
    "label_dimension_height": "297",
    "label_dimension_width": "210",
    "label_image_size_height": "260",
    "label_image_size_width": "170",
    "line_height_extra_small": "3",
    "line_height_small": "5",
    "line_height_medium": "6",
    "line_height_large": "8",
    "line_height_extra_large": "12",
    "margin_v": "20",
    "margin_h": "0",
}

if settings.ENV == "local":
    production = False  # Local
else:
    production = True  # Dev

### DHL constants ###
styles = getSampleStyleSheet()
style_right = ParagraphStyle(
    name="right",
    parent=styles["Normal"],
    alignment=TA_RIGHT,
    leading=24,
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
    backColor="black",
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
style_center_bg = ParagraphStyle(
    name="right_black",
    parent=styles["Normal"],
    alignment=TA_CENTER,
    leading=24,
    backColor="black",
)

styles.add(ParagraphStyle(name="Justify", alignment=TA_JUSTIFY))
ROWS_PER_PAGE = 20
#####################

logger = logging.getLogger(__name__)


class VerticalText(Flowable):

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


class InteractiveCheckBox(Flowable):
    def __init__(self, text=""):
        Flowable.__init__(self)
        self.text = text
        self.boxsize = 12

    def draw(self):
        self.canv.saveState()
        form = self.canv.acroForm
        form.checkbox(
            checked=False,
            buttonStyle="check",
            name=self.text,
            tooltip=self.text,
            relative=True,
            fillColor=colors.white,
            size=self.boxsize,
        )
        self.canv.restoreState()
        return


checkbox = InteractiveCheckBox("")


def build_table(
    bookings,
    start,
    end,
    pallets_per_order,
    packages_per_order,
    kg_per_booking,
    cubic_per_booking,
):
    data = []
    t1_w = float(label_settings["label_image_size_width"]) * (4 / 32) * mm
    t2_w = float(label_settings["label_image_size_width"]) * (6 / 32) * mm
    t3_w = float(label_settings["label_image_size_width"]) * (3 / 32) * mm
    t1_h = float(label_settings["label_image_size_height"]) * (1 / 30) * mm
    t2_h = float(label_settings["label_image_size_height"]) * (1 / 30) * mm
    _rowHeights = []
    for index in range(start, end):
        booking = bookings[index]
        customer_reference = booking.b_client_sales_inv_num

        # Anchor Packaging Pty Ltd
        if booking.kf_client_id == "49294ca3-2adb-4a6e-9c55-9b56c0361953":
            customer_reference = booking.b_client_order_num

        _rowHeights.append(t2_h)
        data.append(
            [
                Paragraph(
                    "<font size=%s>%s</font>"
                    % (
                        label_settings["font_size_extra_small"],
                        bookings[index].v_FPBookingNumber
                        if bookings[index].v_FPBookingNumber
                        else gen_consignment_num(
                            bookings[index].vx_freight_provider,
                            bookings[index].b_bookingID_Visual,
                        ),
                    ),
                    style_center,
                ),
                Paragraph(
                    "<font size=%s>%s</font>"
                    % (
                        label_settings["font_size_extra_small"],
                        customer_reference or "",
                    ),
                    style_center,
                ),
                Paragraph(
                    "<font size=%s>%s</font>"
                    % (
                        label_settings["font_size_extra_small"],
                        bookings[index].de_to_Contact_F_LName
                        if bookings[index].de_to_Contact_F_LName
                        else "",
                    ),
                    style_center,
                ),
                Paragraph(
                    "<font size=%s>%s</font>"
                    % (
                        label_settings["font_size_extra_small"],
                        f"{bookings[index].de_To_Address_Suburb} {bookings[index].de_To_Address_State} {bookings[index].de_To_Address_PostalCode}",
                    ),
                    style_center,
                ),
                Paragraph(
                    "<font size=%s>%s</font>"
                    % (
                        label_settings["font_size_extra_small"],
                        pallets_per_order[index],
                    ),
                    style_center,
                ),
                Paragraph(
                    "<font size=%s>%s</font>"
                    % (
                        label_settings["font_size_extra_small"],
                        packages_per_order[index],
                    ),
                    style_center,
                ),
                Paragraph(
                    "<font size=%s>%s</font>"
                    % (
                        label_settings["font_size_extra_small"],
                        kg_per_booking[index],
                    ),
                    style_center,
                ),
                Paragraph(
                    "<font size=%s>%s</font>"
                    % (
                        label_settings["font_size_extra_small"],
                        cubic_per_booking[index],
                    ),
                    style_center,
                ),
            ]
        )
    booking_table = Table(
        data,
        colWidths=[t1_w, t1_w, t2_w, t2_w, t3_w, t3_w, t3_w, t3_w],
        rowHeights=_rowHeights,
        style=[
            ("VALIGN", (0, 0), (-1, -1), "CENTER"),
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMBORDER", (0, 0), (-1, -1), 0),
            ("GRID", (0, 0), (-1, -1), 0.5, "black"),
        ],
    )
    return booking_table


def make_pagenumber(number, page_number):
    data = [
        [
            "",
            Paragraph(
                "<font size=%s>%s</font>"
                % (
                    label_settings["font_size_medium"],
                    f"Page {number} of {page_number}",
                ),
                style_right,
            ),
        ],
    ]
    t1_w = float(label_settings["label_image_size_width"]) * (13 / 16) * mm
    t2_w = float(label_settings["label_image_size_width"]) * (3 / 16) * mm
    page_table = Table(
        data,
        colWidths=[t1_w, t2_w],
        style=[
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
        ],
    )
    return page_table


def build_manifest(bookings, booking_lines, username, need_truck, timestamp):
    LOG_ID = "[DEFAULT_MANIFEST]"
    fp_name = bookings[0].vx_freight_provider
    fp_info = Fp_freight_providers.objects.get(fp_company_name=fp_name)

    if fp_info and fp_info.hex_color_code:
        fp_bg_color = fp_info.hex_color_code
    else:
        fp_bg_color = "808080"

    if "jasonl" in fp_name.lower().replace(" ", ""):
        fp_name = "Jason L"

    m3_to_kg_factor = 250
    total_dead_weight, total_cubic, total_qty = 0, 0, 0
    kg_per_booking = []
    cubic_per_booking = []
    pallets_per_order = []
    packages_per_order = []
    booking_ids = []

    for booking in bookings:
        booking_ids.append(str(booking.pk))
        lines = [
            item
            for item in booking_lines
            if item.fk_booking_id == booking.pk_booking_id
        ]
        kg, cubic, pallets, packages = 0, 0, 0, 0

        scanned_lines = []
        quote_lines = []
        for line in lines:
            if line.packed_status == "scanned":
                scanned_lines.append(line)
            if (
                booking.api_booking_quote
                and line.packed_status == booking.api_booking_quote.packed_status
            ):
                quote_lines.append(line)

        lines = scanned_lines or quote_lines
        for line in lines:
            logger.info(f"{LOG_ID} {line.pk}")
            total_qty += line.e_qty
            kg += (
                line.e_weightPerEach * _get_weight_amount(line.e_weightUOM) * line.e_qty
            )
            cubic += get_cubic_meter(
                line.e_dimLength,
                line.e_dimWidth,
                line.e_dimHeight,
                line.e_dimUOM,
                line.e_qty,
            )
            if line.e_type_of_packaging and line.e_type_of_packaging.lower() in [
                "pal",
                "pallet",
            ]:
                pallets += line.e_qty
            else:
                packages += line.e_qty

        pallets_per_order.append(pallets)
        packages_per_order.append(packages)
        kg_per_booking.append(round(kg, 3))
        cubic_per_booking.append(round(cubic, 3))
        logger.info(
            f"{LOG_ID} {booking.b_bookingID_Visual}, {pallets_per_order}, {packages_per_order}, {kg_per_booking}, {cubic_per_booking}"
        )
        total_dead_weight += kg
        total_cubic += cubic

    total_cubic_weight = total_cubic * m3_to_kg_factor
    number_of_consignments = len(bookings)

    style_center_fp = ParagraphStyle(
        name="right",
        parent=styles["Normal"],
        alignment=TA_CENTER,
        leading=24,
        backColor="#{}".format(fp_bg_color),
    )

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

    # label_settings = get_label_settings( 146, 104 )[0]
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
    dme_logo = "./static/assets/logos/dme.png"
    dme_img = Image(dme_logo, 40 * mm, 10 * mm)
    data = [
        [
            dme_img,
            Paragraph(
                "<font size=%s color=%s><b>%s</b></font>"
                % (
                    label_settings["font_size_large"],
                    "white",
                    "Order Summary Report",
                ),
                style_center_title,
            ),
            Paragraph(
                "<font size=%s><b>%s</b></font>"
                % (
                    label_settings["font_size_large"],
                    fp_name,
                ),
                style_center_fp,
            ),
        ],
        [
            Paragraph(
                "<font size=%s><b>%s</b></font>"
                % (
                    label_settings["font_size_medium"],
                    "DRIVER COPY",
                ),
                style_right,
            ),
        ],
    ]

    t1_w = float(label_settings["label_image_size_width"]) * (1 / 4) * mm
    t2_w = float(label_settings["label_image_size_width"]) * (2 / 4) * mm
    t3_w = float(label_settings["label_image_size_width"]) * (1 / 4) * mm

    header = Table(
        data,
        colWidths=[t1_w, t2_w, t3_w],
        style=[
            ("SPAN", (0, 1), (-1, 1)),
            ("VALIGN", (0, 0), (-1, -1), "CENTER"),
            ("TOPPADDING", (0, -1), (-1, -1), 2),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, -1), (-1, -1), 4),
            ("BOTTOMBORDER", (0, 0), (-1, -1), 0),
        ],
    )
    Story.append(header)

    hr = HRFlowable(
        width=(float(label_settings["label_image_size_width"]) * mm),
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
    Story.append(Spacer(1, 3))

    data = [
        [
            Paragraph(
                "<font size=%s>%s</font>"
                % (
                    label_settings["font_size_medium"],
                    "Consigner ID/Name:",
                ),
                style_left,
            ),
            Paragraph(
                "<font size=%s>%s</font>"
                % (
                    label_settings["font_size_medium"],
                    bookings[0].b_client_name or "",
                ),
                style_left,
            ),
            Paragraph(
                "<font size=%s><b>%s</b></font>"
                % (
                    label_settings["font_size_large"],
                    bookings[0].vx_serviceName or "",
                ),
                style_right,
            ),
        ],
        [
            Paragraph(
                "<font size=%s>%s</font>"
                % (
                    label_settings["font_size_medium"],
                    "Sender Address:",
                ),
                style_left,
            ),
            Paragraph(
                "<font size=%s>%s</font>"
                % (
                    label_settings["font_size_medium"],
                    f"{bookings[0].pu_Address_Street_1} {f'{bookings[0].pu_Address_street_2},' if bookings[0].pu_Address_street_2 else ''}{f'{bookings[0].pu_Address_City},' if bookings[0].pu_Address_City else ''}{bookings[0].pu_Address_Suburb} {bookings[0].pu_Address_State} {bookings[0].pu_Address_PostalCode} {bookings[0].pu_Address_Country}",
                ),
                style_left,
            ),
        ],
        [
            Paragraph(
                "<font size=%s>%s</font>"
                % (
                    label_settings["font_size_medium"],
                    "Order Created/Manifest Date:",
                ),
                style_left,
            ),
            Paragraph(
                "<font size=%s>%s</font>"
                % (
                    label_settings["font_size_medium"],
                    bookings[0].b_dateBookedDate.strftime("%d/%m/%Y")
                    if bookings[0].b_dateBookedDate
                    else datetime.today().strftime("%d/%m/%Y"),
                ),
                style_left,
            ),
        ],
    ]

    t1_w = float(label_settings["label_image_size_width"]) * (1 / 3) * mm
    t2_w = float(label_settings["label_image_size_width"]) * (1 / 3) * mm
    t3_w = float(label_settings["label_image_size_width"]) * (1 / 3) * mm

    table = Table(
        data,
        colWidths=[t1_w, t2_w, t3_w],
        style=[
            ("SPAN", (-1, 0), (-1, -1)),
            ("VALIGN", (0, 0), (1, -1), "TOP"),
            # ("VALIGN", (-1, 0), (-1, -1), "TOP"),
            ("TOPPADDING", (0, 0), (2, -1), 0),
            ("VALIGN", (-1, 0), (-1, -1), "CENTER"),
            # ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMBORDER", (0, 0), (-1, -1), 0),
        ],
    )
    Story.append(table)
    Story.append(Spacer(1, 3))
    Story.append(hr)
    Story.append(Spacer(1, 3))

    data = [
        [
            Paragraph(
                "<font size=%s><b>%s</b> %s</font>"
                % (
                    label_settings["font_size_medium"],
                    "Number of Consignments: ",
                    number_of_consignments,
                ),
                style_left,
            ),
            Paragraph(
                "<font size=%s><b>%s</b> %s</font>"
                % (
                    label_settings["font_size_medium"],
                    "Number of Articles: ",
                    total_qty,
                ),
                style_left,
            ),
            Paragraph(
                "<font size=%s><b>%s</b> %s</font>"
                % (
                    label_settings["font_size_medium"],
                    "Actual Weight (kg): ",
                    round(total_dead_weight, 3),
                ),
                style_left,
            ),
        ],
        [
            Paragraph(
                "<font size=%s><b>%s (m<super rise=4 size=6>3</super>): </b> %s</font>"
                % (label_settings["font_size_medium"], "Cube", round(total_cubic, 3)),
                style_left,
            ),
            Paragraph(
                "<font size=%s><b>%s</b> %s</font>"
                % (
                    label_settings["font_size_medium"],
                    "Number of Consignments with Dangerous Goods: ",
                    "0",
                ),
                style_left,
            ),
        ],
    ]

    t1_w = float(label_settings["label_image_size_width"]) * (1 / 3) * mm
    t2_w = float(label_settings["label_image_size_width"]) * (1 / 3) * mm
    t3_w = float(label_settings["label_image_size_width"]) * (1 / 3) * mm

    table = Table(
        data,
        colWidths=[t1_w, t2_w, t3_w],
        style=[
            ("SPAN", (1, 1), (-1, 1)),
            ("VALIGN", (0, 0), (-1, -1), "CENTER"),
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMBORDER", (0, 0), (-1, -1), 0),
        ],
    )
    Story.append(table)
    Story.append(Spacer(1, 8))
    # --------------- body part ------------------
    data = [
        [
            Paragraph(
                "<font size=%s><b>%s</b></font>"
                % (
                    label_settings["font_size_extra_small"],
                    "Consignment Number",
                ),
                style_center,
            ),
            Paragraph(
                "<font size=%s><b>%s</b></font>"
                % (
                    label_settings["font_size_extra_small"],
                    "Customer Reference",
                ),
                style_center,
            ),
            Paragraph(
                "<font size=%s><b>%s</b></font>"
                % (
                    label_settings["font_size_extra_small"],
                    "Receiver Name",
                ),
                style_center,
            ),
            Paragraph(
                "<font size=%s><b>%s</b></font>"
                % (
                    label_settings["font_size_extra_small"],
                    "Destination",
                ),
                style_center,
            ),
            Paragraph(
                "<font size=%s><b>%s</b></font>"
                % (
                    label_settings["font_size_extra_small"],
                    "Pallets",
                ),
                style_center,
            ),
            Paragraph(
                "<font size=%s><b>%s</b></font>"
                % (
                    label_settings["font_size_extra_small"],
                    "Packages",
                ),
                style_center,
            ),
            Paragraph(
                "<font size=%s><b>%s</b></font>"
                % (
                    label_settings["font_size_extra_small"],
                    "KG",
                ),
                style_center,
            ),
            Paragraph(
                "<font size=%s><b>Cubic M<super rise=4 size=6>3</super></b></font>"
                % (label_settings["font_size_extra_small"],),
                style_center,
            ),
        ],
    ]

    t1_w = float(label_settings["label_image_size_width"]) * (4 / 32) * mm
    t2_w = float(label_settings["label_image_size_width"]) * (6 / 32) * mm
    t3_w = float(label_settings["label_image_size_width"]) * (3 / 32) * mm
    t1_h = float(label_settings["label_image_size_height"]) * (1 / 30) * mm
    t2_h = float(label_settings["label_image_size_height"]) * (1 / 30) * mm
    _rowHeights = []
    _rowHeights.append(t1_h)
    table_header = Table(
        data,
        colWidths=[t1_w, t1_w, t2_w, t2_w, t3_w, t3_w, t3_w, t3_w],
        rowHeights=_rowHeights,
        style=[
            ("VALIGN", (0, 0), (-1, -1), "CENTER"),
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMBORDER", (0, 0), (-1, -1), 0),
            (
                "BACKGROUND",
                (0, 0),
                (-1, 0),
                colors.Color(red=237 / 255, green=237 / 255, blue=237 / 255),
            ),
            ("GRID", (0, 0), (-1, -1), 0.5, "black"),
        ],
    )
    Story.append(table_header)

    start = 0
    end = len(bookings)
    available = 18
    rest = 0
    sign_rows = 10
    header_rows = 5
    page_rows = 25
    margin = 0
    index = 0
    page_number = int((sign_rows + len(bookings) + header_rows) / 24) + 1
    while True:
        index += 1
        if end > available:
            booking_table = build_table(
                bookings,
                start,
                available,
                pallets_per_order,
                packages_per_order,
                kg_per_booking,
                cubic_per_booking,
            )
            Story.append(booking_table)
            start = available
            Story.append(TopPadder(make_pagenumber(index, page_number)))
            Story.append(PageBreak())
            available += page_rows
        else:
            booking_table = build_table(
                bookings,
                start,
                end,
                pallets_per_order,
                packages_per_order,
                kg_per_booking,
                cubic_per_booking,
            )
            Story.append(booking_table)
            rest = available - end
            if rest > sign_rows:
                margin = rest - sign_rows
                break
            else:
                Story.append(TopPadder(make_pagenumber(index, page_number)))
                Story.append(PageBreak())
                index += 1
                margin = page_rows - sign_rows + 1
                break

    data = [
        [
            Paragraph(
                "<font size=%s><b>%s</b></font>"
                % (
                    label_settings["font_size_medium"],
                    "Driver Name/ID<br />(Please Print): &#95;&#95;&#95;&#95;&#95;&#95;&#95;&#95;&#95;&#95;&#95;&#95;&#95;&#95;&#95;&#95;&#95;&#95;&#95;&#95;",
                ),
                style_left,
            ),
            Paragraph(
                "<font size=%s><b>%s</b></font>"
                % (
                    label_settings["font_size_medium"],
                    "Driver<br />Signature: &#95;&#95;&#95;&#95;&#95;&#95;&#95;&#95;&#95;&#95;&#95;&#95;&#95;&#95;&#95;",
                ),
                style_left,
            ),
            Paragraph(
                "<font size=%s><b>%s</b></font>"
                % (
                    label_settings["font_size_medium"],
                    "Run<br />Number: &#95;&#95;&#95;&#95;&#95;&#95;&#95;&#95;&#95;&#95;",
                ),
                style_left,
            ),
        ],
    ]
    t1_w = float(label_settings["label_image_size_width"]) * (5 / 12) * mm
    t2_w = float(label_settings["label_image_size_width"]) * (4 / 12) * mm
    t3_w = float(label_settings["label_image_size_width"]) * (3 / 12) * mm

    driver_table = Table(
        data,
        colWidths=[t1_w, t2_w, t3_w],
        style=[
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (1, 0), (-1, -1), 0),
        ],
    )

    data = [
        [
            Paragraph(
                "<font size=%s><b>%s</b></font>"
                % (
                    label_settings["font_size_large"],
                    "Does this cargo contain DANGEROUS GOODS?<br />",
                ),
                style_left,
            ),
        ],
    ]
    t1_w = float(label_settings["label_image_size_width"]) * mm
    subtitle_table = Table(
        data,
        colWidths=[t1_w],
        style=[
            ("VALIGN", (0, 0), (-1, -1), "CENTER"),
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
            ("BORDER", (0, 0), (-1, -1), 1),
        ],
    )

    data = [
        [
            checkbox,
            Paragraph(
                "<font size=%s><b>%s</b>%s</font>"
                % (
                    label_settings["font_size_small"],
                    "NO, ",
                    "I, the sender, declare that THIS CARGO DOES NOT CONTAIN DANGEROUS GOODS that legally require declaration",
                ),
                style_left,
            ),
        ],
        [
            checkbox,
            Paragraph(
                "<font size=%s><b>%s</b>%s</font>"
                % (
                    label_settings["font_size_small"],
                    "YES, ",
                    "and a completed and signed Dangerous Goods Declaration or other documentation required by law is attached for every consignment that contains dangerous goods.",
                ),
                style_left,
            ),
        ],
        [
            checkbox,
            Paragraph(
                "<font size=%s>%s</font>"
                % (
                    label_settings["font_size_small"],
                    "I, the sender, acknowledge that this cargo may be carried by air and will be subject to aviation security and clearing procedures and I further acknowledge that it is illegal to consign as cargo any unauthorised explosives or explosive devices.",
                ),
                style_left,
            ),
        ],
        [
            checkbox,
            Paragraph(
                "<font size=%s>%s</font>"
                % (
                    label_settings["font_size_small"],
                    "I further accept that the weights and cubic dimensions set out on this form are correct and are a true representation of the volume of freight shipped under this despatch summary.",
                ),
                style_left,
            ),
        ],
    ]
    t1_w = float(label_settings["label_image_size_width"]) * (1 / 30) * mm
    t2_w = float(label_settings["label_image_size_width"]) * (29 / 30) * mm
    t_h = float(label_settings["label_image_size_height"]) * (1 / 30) * mm
    privacy_table = Table(
        data,
        colWidths=[t1_w, t2_w],
        rowHeights=[t_h, t_h, t_h, t_h],
        style=[
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("TOPPADDING", (0, 0), (0, -1), 16),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
            ("BORDER", (0, 0), (-1, -1), 1),
        ],
    )

    data = [
        [
            Paragraph(
                "<font size=%s><b>%s</b></font>"
                % (
                    label_settings["font_size_medium"],
                    "Senders Signature: &#95;&#95;&#95;&#95;&#95;&#95;&#95;&#95;&#95;&#95;&#95;&#95;&#95;&#95;&#95;&#95;&#95;&#95;&#95;&#95;&#95;&#95;&#95;&#95;&#95;&#95;&#95;&#95;&#95;&#95;&#95;&#95;&#95;",
                ),
                style_left,
            ),
            Paragraph(
                "<font size=%s><b>%s</b></font>"
                % (
                    label_settings["font_size_medium"],
                    "Multiple",
                ),
                style_left,
            ),
            checkbox,
            Paragraph(
                "<font size=%s><b> %s</b></font>"
                % (
                    label_settings["font_size_medium"],
                    "&nbsp;No",
                ),
                style_left,
            ),
            checkbox,
            Paragraph(
                "<font size=%s><b> %s</b></font>"
                % (
                    label_settings["font_size_medium"],
                    "&nbsp;Yes",
                ),
                style_left,
            ),
        ],
        [
            Paragraph(
                "<font size=%s><b>%s</b></font>"
                % (
                    label_settings["font_size_medium"],
                    "Senders Name: &#95;&#95;&#95;&#95;&#95;&#95;&#95;&#95;&#95;&#95;&#95;&#95;&#95;&#95;&#95;&#95;&#95;&#95;&#95;&#95;&#95;&#95;&#95;&#95;&#95;&#95;&#95;&#95;&#95;&#95;&#95;&#95;&#95;&#95;&#95;&#95;&#95;",
                ),
                style_left,
            )
        ],
    ]
    t1_w = float(label_settings["label_image_size_width"]) * (28 / 42) * mm
    t2_w = float(label_settings["label_image_size_width"]) * (5 / 42) * mm
    t3_w = float(label_settings["label_image_size_width"]) * (1 / 42) * mm
    t4_w = float(label_settings["label_image_size_width"]) * (3 / 42) * mm
    t5_w = float(label_settings["label_image_size_width"]) * (1 / 42) * mm
    t6_w = float(label_settings["label_image_size_width"]) * (4 / 42) * mm
    signature_table = Table(
        data,
        colWidths=[t1_w, t2_w, t3_w, t4_w, t5_w, t6_w],
        style=[
            ("SPAN", (0, -1), (-1, -1)),
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
        ],
    )

    data = [
        [
            "",
            Paragraph(
                "<font size=%s color=%s>%s</font>"
                % (label_settings["font_size_large"], "white", "D"),
                style_center_bg,
            ),
        ],
        [
            Paragraph(
                "<font size=%s>%s</font>"
                % (
                    label_settings["font_size_medium"],
                    f"Page {index} of {page_number}",
                ),
                style_right,
            )
        ],
    ]
    t1_w = float(label_settings["label_image_size_width"]) * (15 / 16) * mm
    t2_w = float(label_settings["label_image_size_width"]) * (1 / 16) * mm
    last_page_table = Table(
        data,
        colWidths=[t1_w, t2_w],
        style=[
            ("SPAN", (0, -1), (-1, -1)),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
        ],
    )

    Story.append(Spacer(1, margin * t2_h))
    Story.append(driver_table)
    Story.append(Spacer(1, 12))
    Story.append(hr)
    Story.append(Spacer(1, 12))
    Story.append(subtitle_table)
    Story.append(Spacer(1, 12))
    Story.append(privacy_table)
    Story.append(Spacer(1, 12))
    Story.append(signature_table)
    Story.append(TopPadder(last_page_table))

    doc.build(Story)
    file.close()

    # Add manifest log
    manfiest_log = Dme_manifest_log.objects.create(
        fk_booking_id=bookings[0].pk_booking_id,
        manifest_url=f"{fp_name.lower()}_au/{filename}",
        manifest_number=fp_info.fp_manifest_cnt,
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
