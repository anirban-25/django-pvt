import os
import sys
import logging
from datetime import datetime
from reportlab.lib.enums import TA_JUSTIFY, TA_RIGHT, TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import letter, landscape, A6
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
from reportlab.lib.units import inch, mm
from reportlab.graphics.barcode import (
    code39,
    code128,
    code93,
    createBarcodeDrawing,
    eanbc,
    qr,
    usps,
)
from reportlab.graphics.shapes import Drawing
from reportlab.pdfgen import canvas
from reportlab.graphics import renderPDF
from reportlab.lib import colors
from django.conf import settings

from api.models import Fp_freight_providers, Dme_manifest_log
from api.common.ratio import _get_dim_amount, _get_weight_amount
from api.helpers.cubic import get_cubic_meter

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
    leading=12,
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


def build_manifest(bookings, booking_lines, username, need_truck, timestamp):
    fp_name = bookings[0].vx_freight_provider
    fp_info = Fp_freight_providers.objects.get(fp_company_name=fp_name)
    if fp_info and fp_info.hex_color_code:
        fp_bg_color = fp_info.hex_color_code
    else:
        fp_bg_color = "808080"
    # new_manifest_index = fp_info.fp_manifest_cnt
    # new_connot_index = fp_info.

    m3_to_kg_factor = 250
    total_dead_weight, total_cubic, total_qty = 0, 0, 0
    orders = []

    for line in booking_lines:
        total_qty += line.e_qty
        total_dead_weight += (
            line.e_weightPerEach * _get_weight_amount(line.e_weightUOM) * line.e_qty
        )
        total_cubic += get_cubic_meter(
            line.e_dimLength,
            line.e_dimWidth,
            line.e_dimHeight,
            line.e_dimUOM,
            line.e_qty,
        )

    total_cubic_weight = total_cubic * m3_to_kg_factor
    number_of_consignments = len(bookings)

    booking_ids = []
    for booking in bookings:
        booking_ids.append(str(booking.pk))

    style_center_fp = ParagraphStyle(
        name="right",
        parent=styles["Normal"],
        alignment=TA_CENTER,
        leading=24,
        backColor="#{}".format(fp_bg_color),
    )

    # start check if pdfs folder exists
    if production:
        local_filepath = "/opt/s3_public/pdfs/startrack_au"
        local_filepath_dup = (
            "/opt/s3_public/pdfs/startrack_au/archive/"
            + str(datetime.now().strftime("%Y_%m_%d"))
            + "/"
        )
    else:
        local_filepath = "./static/pdfs/startrack_au"
        local_filepath_dup = (
            "./static/pdfs/startrack_au/archive/"
            + str(datetime.now().strftime("%Y_%m_%d"))
            + "/"
        )

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
    label_settings = {
        "font_family": "Verdana",
        "font_size_extra_small": "4",
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

    dme_logo = "./static/assets/logos/dme.png"
    dme_img = Image(dme_logo, 40 * mm, 10 * mm)

    Story = []

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
                    "Payer Account Name:",
                ),
                style_left,
            ),
            Paragraph(
                "<font size=%s>%s</font>"
                % (
                    label_settings["font_size_medium"],
                    "Deliver-ME PTY LTD",
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
                    "Payer Account Number:",
                ),
                style_left,
            ),
            Paragraph(
                "<font size=%s>%s</font>"
                % (
                    label_settings["font_size_medium"],
                    "DELVME",
                ),
                style_left,
            ),
        ],
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
                    "",
                ),
                style_left,
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
                "<font size=%s>%s</font>" % (label_settings["font_size_medium"], ""),
                style_left,
            ),
        ],
        # [
        #     Paragraph(
        #         "<font size=%s>%s</font>"
        #         % (
        #             label_settings["font_size_medium"],
        #             "Despatch/Merchant Location ID:",
        #         ),
        #         style_left,
        #     ),
        #     Paragraph(
        #         "<font size=%s>%s</font>"
        #         % (
        #             label_settings["font_size_medium"],
        #             "9WCZ",
        #         ),
        #         style_left,
        #     ),
        # ],
        # [
        #     Paragraph(
        #         "<font size=%s>%s</font>"
        #         % (
        #             label_settings["font_size_medium"],
        #             "Order ID:",
        #         ),
        #         style_left,
        #     ),
        #     Paragraph(
        #         "<font size=%s>%s</font>"
        #         % (
        #             label_settings["font_size_medium"],
        #             "AP47236140",
        #         ),
        #         style_left,
        #     ),
        # ],
        [
            Paragraph(
                "<font size=%s>%s</font>"
                % (
                    label_settings["font_size_medium"],
                    "Order Created Date:",
                ),
                style_left,
            ),
            Paragraph(
                "<font size=%s>%s</font>"
                % (
                    label_settings["font_size_medium"],
                    "",
                ),
                style_left,
            ),
        ],
        # [
        #     Paragraph(
        #         "<font size=%s>%s</font>"
        #         % (
        #             label_settings["font_size_medium"],
        #             "Lodgement Facility (AP only):",
        #         ),
        #         style_left,
        #     ),
        #     Paragraph(
        #         "<font size=%s>%s</font>"
        #         % (
        #             label_settings["font_size_medium"],
        #             "",
        #         ),
        #         style_left,
        #     ),
        # ],
    ]

    t1_w = float(label_settings["label_image_size_width"]) * (1 / 3) * mm
    t2_w = float(label_settings["label_image_size_width"]) * (1 / 3) * mm
    t3_w = float(label_settings["label_image_size_width"]) * (1 / 3) * mm

    table = Table(
        data,
        colWidths=[t1_w, t2_w, t3_w],
        style=[
            ("SPAN", (-1, 0), (-1, -1)),
            ("VALIGN", (0, 0), (1, -1), "CENTER"),
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

    data = [
        [
            Paragraph(
                "<font size=%s><b>%s</b></font>"
                % (
                    label_settings["font_size_medium"],
                    "Sales #",
                ),
                style_center,
            ),
            Paragraph(
                "<font size=%s><b>%s</b></font>"
                % (
                    label_settings["font_size_medium"],
                    "Deliver To Postal",
                ),
                style_center,
            ),
            Paragraph(
                "<font size=%s><b>%s</b></font>"
                % (
                    label_settings["font_size_medium"],
                    "Number of Articles",
                ),
                style_center,
            ),
            Paragraph(
                "<font size=%s><b>%s</b></font>"
                % (
                    label_settings["font_size_medium"],
                    "Freight Dimensions(mm)",
                ),
                style_center,
            ),
            "",
            "",
            Paragraph(
                "<font size=%s><b>Total KG/Total M<super rise=4 size=6>3</super></b></font>"
                % (label_settings["font_size_medium"],),
                style_center,
            ),
        ],
        [
            "",
            "",
            "",
            Paragraph(
                "<font size=%s><b>%s</b></font>"
                % (
                    label_settings["font_size_medium"],
                    "Length",
                ),
                style_center,
            ),
            Paragraph(
                "<font size=%s><b>%s</b></font>"
                % (
                    label_settings["font_size_medium"],
                    "Width",
                ),
                style_center,
            ),
            Paragraph(
                "<font size=%s><b>%s</b></font>"
                % (
                    label_settings["font_size_medium"],
                    "Height",
                ),
                style_center,
            ),
            "",
        ],
        [
            Paragraph(
                "<font size=%s>%s</font>"
                % (
                    label_settings["font_size_medium"],
                    " ",
                ),
                style_center,
            ),
            Paragraph(
                "<font size=%s>%s</font>"
                % (
                    label_settings["font_size_medium"],
                    " ",
                ),
                style_center,
            ),
            Paragraph(
                "<font size=%s>%s</font>"
                % (
                    label_settings["font_size_medium"],
                    " ",
                ),
                style_center,
            ),
            Paragraph(
                "<font size=%s>%s</font>"
                % (
                    label_settings["font_size_medium"],
                    " ",
                ),
                style_center,
            ),
            Paragraph(
                "<font size=%s>%s</font>"
                % (
                    label_settings["font_size_medium"],
                    " ",
                ),
                style_center,
            ),
            Paragraph(
                "<font size=%s>%s</font>"
                % (
                    label_settings["font_size_medium"],
                    "",
                ),
                style_center,
            ),
            Paragraph(
                "<font size=%s>%s</font>"
                % (
                    label_settings["font_size_medium"],
                    "",
                ),
                style_center,
            ),
        ],
        [
            Paragraph(
                "<font size=%s>%s</font>"
                % (
                    label_settings["font_size_medium"],
                    " ",
                ),
                style_center,
            ),
            Paragraph(
                "<font size=%s>%s</font>"
                % (
                    label_settings["font_size_medium"],
                    " ",
                ),
                style_center,
            ),
            Paragraph(
                "<font size=%s>%s</font>"
                % (
                    label_settings["font_size_medium"],
                    " ",
                ),
                style_center,
            ),
            Paragraph(
                "<font size=%s>%s</font>"
                % (
                    label_settings["font_size_medium"],
                    " ",
                ),
                style_center,
            ),
            Paragraph(
                "<font size=%s>%s</font>"
                % (
                    label_settings["font_size_medium"],
                    " ",
                ),
                style_center,
            ),
            Paragraph(
                "<font size=%s>%s</font>"
                % (
                    label_settings["font_size_medium"],
                    "",
                ),
                style_center,
            ),
            Paragraph(
                "<font size=%s>%s</font>"
                % (
                    label_settings["font_size_medium"],
                    "",
                ),
                style_center,
            ),
        ],
        [
            Paragraph(
                "<font size=%s>%s</font>"
                % (
                    label_settings["font_size_medium"],
                    " ",
                ),
                style_center,
            ),
            Paragraph(
                "<font size=%s>%s</font>"
                % (
                    label_settings["font_size_medium"],
                    " ",
                ),
                style_center,
            ),
            Paragraph(
                "<font size=%s>%s</font>"
                % (
                    label_settings["font_size_medium"],
                    " ",
                ),
                style_center,
            ),
            Paragraph(
                "<font size=%s>%s</font>"
                % (
                    label_settings["font_size_medium"],
                    " ",
                ),
                style_center,
            ),
            Paragraph(
                "<font size=%s>%s</font>"
                % (
                    label_settings["font_size_medium"],
                    " ",
                ),
                style_center,
            ),
            Paragraph(
                "<font size=%s>%s</font>"
                % (
                    label_settings["font_size_medium"],
                    "",
                ),
                style_center,
            ),
            Paragraph(
                "<font size=%s>%s</font>"
                % (
                    label_settings["font_size_medium"],
                    "",
                ),
                style_center,
            ),
        ],
        [
            Paragraph(
                "<font size=%s>%s</font>"
                % (
                    label_settings["font_size_medium"],
                    " ",
                ),
                style_center,
            ),
            Paragraph(
                "<font size=%s>%s</font>"
                % (
                    label_settings["font_size_medium"],
                    " ",
                ),
                style_center,
            ),
            Paragraph(
                "<font size=%s>%s</font>"
                % (
                    label_settings["font_size_medium"],
                    " ",
                ),
                style_center,
            ),
            Paragraph(
                "<font size=%s>%s</font>"
                % (
                    label_settings["font_size_medium"],
                    " ",
                ),
                style_center,
            ),
            Paragraph(
                "<font size=%s>%s</font>"
                % (
                    label_settings["font_size_medium"],
                    " ",
                ),
                style_center,
            ),
            Paragraph(
                "<font size=%s>%s</font>"
                % (
                    label_settings["font_size_medium"],
                    "",
                ),
                style_center,
            ),
            Paragraph(
                "<font size=%s>%s</font>"
                % (
                    label_settings["font_size_medium"],
                    "",
                ),
                style_center,
            ),
        ],
        [
            Paragraph(
                "<font size=%s>%s</font>"
                % (
                    label_settings["font_size_medium"],
                    " ",
                ),
                style_center,
            ),
            Paragraph(
                "<font size=%s>%s</font>"
                % (
                    label_settings["font_size_medium"],
                    " ",
                ),
                style_center,
            ),
            Paragraph(
                "<font size=%s>%s</font>"
                % (
                    label_settings["font_size_medium"],
                    " ",
                ),
                style_center,
            ),
            Paragraph(
                "<font size=%s>%s</font>"
                % (
                    label_settings["font_size_medium"],
                    " ",
                ),
                style_center,
            ),
            Paragraph(
                "<font size=%s>%s</font>"
                % (
                    label_settings["font_size_medium"],
                    " ",
                ),
                style_center,
            ),
            Paragraph(
                "<font size=%s>%s</font>"
                % (
                    label_settings["font_size_medium"],
                    "",
                ),
                style_center,
            ),
            Paragraph(
                "<font size=%s>%s</font>"
                % (
                    label_settings["font_size_medium"],
                    "",
                ),
                style_center,
            ),
        ],
        [
            Paragraph(
                "<font size=%s>%s</font>"
                % (
                    label_settings["font_size_medium"],
                    " ",
                ),
                style_center,
            ),
            Paragraph(
                "<font size=%s>%s</font>"
                % (
                    label_settings["font_size_medium"],
                    " ",
                ),
                style_center,
            ),
            Paragraph(
                "<font size=%s>%s</font>"
                % (
                    label_settings["font_size_medium"],
                    " ",
                ),
                style_center,
            ),
            Paragraph(
                "<font size=%s>%s</font>"
                % (
                    label_settings["font_size_medium"],
                    " ",
                ),
                style_center,
            ),
            Paragraph(
                "<font size=%s>%s</font>"
                % (
                    label_settings["font_size_medium"],
                    " ",
                ),
                style_center,
            ),
            Paragraph(
                "<font size=%s>%s</font>"
                % (
                    label_settings["font_size_medium"],
                    "",
                ),
                style_center,
            ),
            Paragraph(
                "<font size=%s>%s</font>"
                % (
                    label_settings["font_size_medium"],
                    "",
                ),
                style_center,
            ),
        ],
        [
            Paragraph(
                "<font size=%s>%s</font>"
                % (
                    label_settings["font_size_medium"],
                    " ",
                ),
                style_center,
            ),
            Paragraph(
                "<font size=%s>%s</font>"
                % (
                    label_settings["font_size_medium"],
                    " ",
                ),
                style_center,
            ),
            Paragraph(
                "<font size=%s>%s</font>"
                % (
                    label_settings["font_size_medium"],
                    " ",
                ),
                style_center,
            ),
            Paragraph(
                "<font size=%s>%s</font>"
                % (
                    label_settings["font_size_medium"],
                    " ",
                ),
                style_center,
            ),
            Paragraph(
                "<font size=%s>%s</font>"
                % (
                    label_settings["font_size_medium"],
                    " ",
                ),
                style_center,
            ),
            Paragraph(
                "<font size=%s>%s</font>"
                % (
                    label_settings["font_size_medium"],
                    "",
                ),
                style_center,
            ),
            Paragraph(
                "<font size=%s>%s</font>"
                % (
                    label_settings["font_size_medium"],
                    "",
                ),
                style_center,
            ),
        ],
        [
            Paragraph(
                "<font size=%s>%s</font>"
                % (
                    label_settings["font_size_medium"],
                    " ",
                ),
                style_center,
            ),
            Paragraph(
                "<font size=%s>%s</font>"
                % (
                    label_settings["font_size_medium"],
                    " ",
                ),
                style_center,
            ),
            Paragraph(
                "<font size=%s>%s</font>"
                % (
                    label_settings["font_size_medium"],
                    " ",
                ),
                style_center,
            ),
            Paragraph(
                "<font size=%s>%s</font>"
                % (
                    label_settings["font_size_medium"],
                    " ",
                ),
                style_center,
            ),
            Paragraph(
                "<font size=%s>%s</font>"
                % (
                    label_settings["font_size_medium"],
                    " ",
                ),
                style_center,
            ),
            Paragraph(
                "<font size=%s>%s</font>"
                % (
                    label_settings["font_size_medium"],
                    "",
                ),
                style_center,
            ),
            Paragraph(
                "<font size=%s>%s</font>"
                % (
                    label_settings["font_size_medium"],
                    "",
                ),
                style_center,
            ),
        ],
        [
            Paragraph(
                "<font size=%s>%s</font>"
                % (
                    label_settings["font_size_medium"],
                    " ",
                ),
                style_center,
            ),
            Paragraph(
                "<font size=%s>%s</font>"
                % (
                    label_settings["font_size_medium"],
                    " ",
                ),
                style_center,
            ),
            Paragraph(
                "<font size=%s>%s</font>"
                % (
                    label_settings["font_size_medium"],
                    " ",
                ),
                style_center,
            ),
            Paragraph(
                "<font size=%s>%s</font>"
                % (
                    label_settings["font_size_medium"],
                    " ",
                ),
                style_center,
            ),
            Paragraph(
                "<font size=%s>%s</font>"
                % (
                    label_settings["font_size_medium"],
                    " ",
                ),
                style_center,
            ),
            Paragraph(
                "<font size=%s>%s</font>"
                % (
                    label_settings["font_size_medium"],
                    "",
                ),
                style_center,
            ),
            Paragraph(
                "<font size=%s>%s</font>"
                % (
                    label_settings["font_size_medium"],
                    "",
                ),
                style_center,
            ),
        ],
    ]

    t1_w = float(label_settings["label_image_size_width"]) * (3 / 19) * mm
    t2_w = float(label_settings["label_image_size_width"]) * (2 / 19) * mm
    t3_w = float(label_settings["label_image_size_width"]) * (4 / 19) * mm
    t1_h = float(label_settings["label_image_size_height"]) * (1 / 50) * mm
    t2_h = float(label_settings["label_image_size_height"]) * (1 / 45) * mm

    table = Table(
        data,
        colWidths=[t1_w, t1_w, t1_w, t2_w, t2_w, t2_w, t3_w],
        rowHeights=[t1_h, t1_h, t2_h, t2_h, t2_h, t2_h, t2_h, t2_h, t2_h, t2_h, t2_h],
        style=[
            ("SPAN", (0, 0), (0, 1)),
            ("SPAN", (1, 0), (1, 1)),
            ("SPAN", (2, 0), (2, 1)),
            ("SPAN", (3, 0), (5, 0)),
            ("SPAN", (-1, 0), (-1, 1)),
            ("VALIGN", (0, 0), (-1, -1), "CENTER"),
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("LEFTPADDING", (-1, 6), (-1, 6), 42),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMBORDER", (0, 0), (-1, -1), 0),
            (
                "BACKGROUND",
                (0, 0),
                (-1, 1),
                colors.Color(red=237 / 255, green=237 / 255, blue=237 / 255),
            ),
            (
                "BACKGROUND",
                (-1, 2),
                (-1, -1),
                colors.Color(red=221 / 255, green=221 / 255, blue=221 / 255),
            ),
            ("GRID", (0, 0), (-1, -1), 0.5, "black"),
        ],
    )
    Story.append(table)

    # data = [
    #     [
    #         "",
    #         VerticalText("Office use only")
    #     ],
    # ]

    # t1_w = float(label_settings["label_image_size_width"]) * (4 / 5) * mm
    # t2_w = float(label_settings["label_image_size_width"]) * (1 / 5) * mm

    # table = Table(
    #     data,
    #     colWidths=[t1_w, t2_w],
    #     style=[
    #         ("TOPPADDING", (0, 0), (-1, -1), -500),
    #         ("BOTTOMPADDING", (1, 0), (-1, -1), 0),
    #         ("RIGHTPADDING", (0, 0), (-1, -1), -200),
    #     ],
    # )
    # Story.append(table)
    Story.append(Spacer(1, 70))

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

    table = Table(
        data,
        colWidths=[t1_w, t2_w, t3_w],
        style=[
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (1, 0), (-1, -1), 0),
        ],
    )
    Story.append(table)
    Story.append(Spacer(1, 8))
    Story.append(hr)
    Story.append(Spacer(1, 10))

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

    table = Table(
        data,
        colWidths=[t1_w],
        style=[
            ("VALIGN", (0, 0), (-1, -1), "CENTER"),
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
            ("BORDER", (0, 0), (-1, -1), 1),
        ],
    )
    Story.append(table)
    Story.append(Spacer(1, 12))

    data = [
        [
            checkbox,
            Paragraph(
                "<font size=%s><b>%s</b>%s</font>"
                % (
                    label_settings["font_size_small"],
                    "NO: ",
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

    table = Table(
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
    Story.append(table)
    Story.append(Spacer(1, 20))

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

    table = Table(
        data,
        colWidths=[t1_w, t2_w, t3_w, t4_w, t5_w, t6_w],
        style=[
            ("SPAN", (0, -1), (-1, -1)),
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
        ],
    )
    Story.append(table)
    Story.append(Spacer(1, 8))

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
                % (label_settings["font_size_medium"], "Page 1 of 1"),
                style_right,
            )
        ],
    ]

    t1_w = float(label_settings["label_image_size_width"]) * (15 / 16) * mm
    t2_w = float(label_settings["label_image_size_width"]) * (1 / 16) * mm

    table = Table(
        data,
        colWidths=[t1_w, t2_w],
        style=[
            ("SPAN", (0, -1), (-1, -1)),
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
        ],
    )
    Story.append(table)

    doc.build(Story)
    file.close()

    # Add manifest log
    Dme_manifest_log.objects.create(
        fk_booking_id=booking.pk_booking_id,
        manifest_url=f"startrack_au/{filename}",
        manifest_number=manifest,
        bookings_cnt=len(bookings),
        is_one_booking=1,
        z_createdByAccount=username,
        need_truck=need_truck,
        freight_provider="Startrack",
        booking_ids=",".join(booking_ids),
    )
    manfiest_log.z_createdTimeStamp = timestamp
    manfiest_log.save()

    # fp_info.fp_manifest_cnt = fp_info.fp_manifest_cnt + 1
    # fp_info.new_connot_index = fp_info.new_connot_index + len(bookings)
    # fp_info.save()

    return filename
