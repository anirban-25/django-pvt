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
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus.flowables import KeepInFrame
from reportlab.lib.colors import white, black, darkgray

from api.helpers.cubic import get_cubic_meter
from api.helpers.string import add_letter, add_space
from api.helpers.line import is_carton, is_pallet
from api.common.ratio import _get_dim_amount, _get_weight_amount
from api.operations.api_booking_confirmation_lines import index as api_bcl
from api.fps.team_global_express import gen_sscc, get_account_detail, get_client_fp_info
from api.common.sscc import calc_checksum as calc_sscc_checksum
from api.clients.biopak.constants import (
    FP_INFO as BIOPAK_INFO,
)
from api.clients.tempo_big_w.constants import FP_INFO as BIGW_INFO
from api.clients.jason_l.constants import (
    FP_INFO as JASONL_INFO,
)
from api.clients.bsd.constants import FP_INFO as BSD_INFO
from api.clients.plum.constants import FP_INFO as PLUM_INFO
from api.clients.anchor_packaging.constants import FP_INFO as AP_INFO
from api.clients.aberdeen_paper.constants import FP_INFO as ABP_INFO


logger = logging.getLogger(__name__)

folder = os.path.dirname(__file__)
font_dir = "./static/assets/fonts/"
pdfmetrics.registerFont(TTFont("Vernada", f"{font_dir}verdana.ttf"))
pdfmetrics.registerFont(TTFont("VernadaBd", f"{font_dir}verdanab.ttf"))
pdfmetrics.registerFont(TTFont("VernadaIt", f"{font_dir}verdana.ttf"))
pdfmetrics.registerFont(TTFont("VernadaBI", f"{font_dir}verdana.ttf"))
pdfmetrics.registerFontFamily(
    "Vernada",
    normal="Vernada",
    bold="VernadaBd",
    italic="VernadaIt",
    boldItalic="VernadaBI",
)

styles = getSampleStyleSheet()
style_reference_text = ParagraphStyle(
    name="left",
    parent=styles["Normal"],
    leading=8,
    spaceBefore=0,
)

style_desc_text = ParagraphStyle(
    name="left",
    parent=styles["Normal"],
    leading=8,
    spaceBefore=0,
)

style_footer_text = ParagraphStyle(
    name="left",
    parent=styles["Normal"],
    leading=8,
    spaceBefore=0,
    textTransform="uppercase",
)


def myFirstPage(canvas, doc):
    canvas.saveState()
    canvas.rotate(180)
    canvas.restoreState()


def myLaterPages(canvas, doc):
    canvas.saveState()
    canvas.rotate(90)
    canvas.restoreState()


def gen_qr_code_string(booking, line, v_FPBookingNumber, item_no, carrier):
    # TGE Label specification section #6
    item_no = add_space(item_no, 22, head_or_tail="tail")

    if carrier == "IPEC":
        bu_code = "B"  # IPEC
    else:
        bu_code = "E"  # I & S

    connote_id = add_space(v_FPBookingNumber, 20, head_or_tail="tail")

    despatch_date = booking.puPickUpAvailFrom_Date.strftime("%y%m%d")

    item_weight = int(_get_weight_amount(line.e_weightUOM) * line.e_weightPerEach * 10)
    item_weight = add_letter(item_weight, 6, head_or_tail="head")

    item_commod = (
        "0" if is_pallet(line.e_type_of_packaging) else "Z"
    )  # if IPEC "Z" else "0"
    item_commod = add_space(item_commod, 2, head_or_tail="tail")

    cubic_length = int(_get_dim_amount(line.e_dimUOM) * line.e_dimLength * 100)
    cubic_length = add_letter(cubic_length, 4, head_or_tail="head")

    cubic_width = int(_get_dim_amount(line.e_dimUOM) * line.e_dimWidth * 100)
    cubic_width = add_letter(cubic_width, 4, head_or_tail="head")

    cubic_height = int(_get_dim_amount(line.e_dimUOM) * line.e_dimHeight * 100)
    cubic_height = add_letter(cubic_height, 4, head_or_tail="head")

    cubic_volume = int(
        get_cubic_meter(
            line.e_dimLength,
            line.e_dimWidth,
            line.e_dimHeight,
            line.e_dimUOM,
            1,
        )
        * 1000
    )
    cubic_volume = add_letter(cubic_volume, 5, head_or_tail="head")

    if carrier == "IPEC":
        service_code = "004"  # Road
    else:
        service_code = "GEN"  # General
    service_code = add_space(service_code, 3, head_or_tail="tail")

    delivery_early_date = (
        booking.de_Deliver_From_Date.strftime("%y%m%d")
        if booking.de_Deliver_From_Date
        else ""
    )
    delivery_early_date = add_space(delivery_early_date, 6, head_or_tail="tail")

    delivery_late_date = (
        booking.de_Deliver_By_Date.strftime("%y%m%d")
        if booking.de_Deliver_By_Date
        else ""
    )
    delivery_late_date = add_space(delivery_late_date, 6, head_or_tail="tail")

    release_date = ""
    release_date = add_space(release_date, 6, head_or_tail="tail")

    dg_flag = "N"
    dg_flag = add_space(dg_flag, 1, head_or_tail="tail")

    primary_elect = "N"
    primary_elect = add_space(primary_elect, 1, head_or_tail="tail")

    primary_elect_adp_identifer = ""
    primary_elect_adp_identifer = add_space(
        primary_elect_adp_identifer, 10, head_or_tail="tail"
    )

    adp_authorised_flag = "N"
    adp_authorised_flag = add_space(adp_authorised_flag, 1, head_or_tail="tail")

    nsr_flag = "Y" if booking.opt_authority_to_leave else "N"
    nsr_flag = add_space(nsr_flag, 1, head_or_tail="tail")

    security_flag = "N"
    security_flag = add_space(security_flag, 1, head_or_tail="tail")

    signature_required = "N"
    signature_required = add_space(signature_required, 1, head_or_tail="tail")

    id_check_required = "N"
    id_check_required = add_space(id_check_required, 1, head_or_tail="tail")

    id_check_validation_number = ""
    id_check_validation_number = add_space(
        id_check_validation_number, 4, head_or_tail="tail"
    )

    dg_un_number = "N"
    dg_un_number = add_space(dg_un_number, 4, head_or_tail="tail")

    dg_packing_group = ""
    dg_packing_group = add_space(dg_packing_group, 1, head_or_tail="tail")

    dg_class = ""
    dg_class = add_space(dg_class, 4, head_or_tail="tail")

    spare = ""
    spare = add_space(spare, 2, head_or_tail="tail")

    payor_code = "S"
    payor_code = add_space(payor_code, 1, head_or_tail="tail")

    payor_account = (
        "U56439" if is_pallet(line.e_type_of_packaging) else "80798424"
    )  # if IPEC "80798424" else "U56439"
    payor_account = add_space(payor_account, 10, head_or_tail="tail")

    extra_svc_amount = ""
    extra_svc_amount = add_space(extra_svc_amount, 7, head_or_tail="tail")

    extra_charge_codes = ""
    extra_charge_codes = add_space(extra_charge_codes, 2, head_or_tail="tail")

    receiver_name = booking.deToCompanyName
    receiver_name = add_space(receiver_name, 40, head_or_tail="tail")

    receiver_street_1 = booking.de_To_Address_Street_1
    receiver_street_1 = add_space(receiver_street_1, 30, head_or_tail="tail")

    receiver_street_2 = booking.de_To_Address_Street_2 or ""
    receiver_street_2 = add_space(receiver_street_2, 30, head_or_tail="tail")

    receiver_town = booking.de_To_Address_Suburb or ""
    receiver_town = add_space(receiver_town, 30, head_or_tail="tail")

    receiver_postcode = booking.de_To_Address_PostalCode
    receiver_postcode = add_space(receiver_postcode, 10, head_or_tail="tail")

    receiver_country_code = "AU"
    receiver_country_code = add_space(receiver_country_code, 2, head_or_tail="tail")

    receiver_gnaf_pid = ""  # Not sure
    receiver_gnaf_pid = add_space(receiver_gnaf_pid, 14, head_or_tail="tail")

    receiver_address_business_residential_code = (
        "R" if booking.de_To_AddressType == "residential" else "B"
    )
    receiver_address_business_residential_code = add_space(
        receiver_address_business_residential_code, 1, head_or_tail="tail"
    )

    receiver_contact_phone = booking.de_to_Phone_Main
    receiver_contact_phone = add_space(receiver_contact_phone, 10, head_or_tail="tail")

    routing_code = ""
    routing_code = add_space(routing_code, 15, head_or_tail="tail")

    customs_duties = ""
    customs_duties = add_space(customs_duties, 3, head_or_tail="tail")

    carrier_identifier = "TF"
    carrier_identifier = add_space(carrier_identifier, 2, head_or_tail="tail")

    version_number = "2"
    version_number = add_space(version_number, 1, head_or_tail="tail")

    return (
        f"{item_no}{bu_code}{connote_id}{despatch_date}{item_weight}{item_commod}"
        + f"{cubic_length}{cubic_width}{cubic_height}{cubic_volume}{service_code}"
        + f"{delivery_early_date}{delivery_late_date}{release_date}{dg_flag}{primary_elect}"
        + f"{primary_elect_adp_identifer}{adp_authorised_flag}{nsr_flag}{security_flag}{signature_required}"
        + f"{id_check_required}{id_check_validation_number}{dg_un_number}{dg_packing_group}{dg_class}"
        + f"{spare}{payor_code}{payor_account}{extra_svc_amount}{extra_charge_codes}"
        + f"{receiver_name}{receiver_street_1}{receiver_street_2}{receiver_town}{receiver_postcode}"
        + f"{receiver_country_code}{receiver_gnaf_pid}{receiver_address_business_residential_code}"
        + f"{receiver_contact_phone}{routing_code}{customs_duties}{carrier_identifier}{version_number}"
    )


def gen_barcode_1(booking, carrier):
    GS1_FNC1_CHAR = "\xf1"
    if carrier == "IPEC":
        ai_1 = "421"
        iso_country_code = "036"  # AU
        postcode = booking.de_To_Address_PostalCode.zfill(4)
        ai_2 = "403"
        service_code = "004"  # Road

        code = f"{GS1_FNC1_CHAR}{ai_1}{iso_country_code}{postcode}{GS1_FNC1_CHAR}{ai_2}{service_code}"
        text = f"({ai_1}) {iso_country_code}{postcode} ({ai_2}) {service_code}"
    else:
        ai_1 = "401"
        # BioPak
        if booking.kf_client_id == "7EAA4B16-484B-3944-902E-BC936BFEF535":
            global_company_prefiex = BIOPAK_INFO["TGE"]["ins"]["ssccPrefix"][
                booking.b_client_warehouse_code
            ]
        # Non-BioPak
        else:
            fp_info = get_client_fp_info(booking.kf_client_id)
            global_company_prefiex = fp_info["ins"]["ssccPrefix"]

        extension_digit = "0"
        connote_number = booking.v_FPBookingNumber
        ai_2 = "420"
        postcode = booking.de_To_Address_PostalCode.zfill(5)
        check_digit = calc_sscc_checksum(
            "", global_company_prefiex, extension_digit, connote_number
        )
        code = f"{GS1_FNC1_CHAR}{ai_1}{global_company_prefiex}{extension_digit}{connote_number}{check_digit}{GS1_FNC1_CHAR}{ai_2}{postcode}"
        text = f"({ai_1}) {global_company_prefiex}{extension_digit}{connote_number}{check_digit} ({ai_2}) {postcode}"
    return {"label_bar": code, "label_text": text}


# SSCC
def gen_barcode_2(booking, line, j_index):
    GS1_FNC1_CHAR = "\xf1"
    label_code = gen_sscc(booking, line, j_index)
    label_code_text = label_code
    api_bcl.create(booking, [{"label_code": label_code}])

    return {"label_bar": f"{GS1_FNC1_CHAR}{label_code}", "label_text": label_code_text}


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
    # start check if pdfs folder exists
    if not os.path.exists(filepath):
        os.makedirs(filepath)
    # end check if pdfs folder exists

    logger.info(
        f"#110 [TGE LABEL] Started building label... (Booking ID: {booking.b_bookingID_Visual}, Lines: {lines})"
    )
    v_FPBookingNumber = pre_data["v_FPBookingNumber"]

    global order_number
    order_number = booking.b_client_order_num

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
            + v_FPBookingNumber
            + "_"
            + str(booking.b_bookingID_Visual)
            + ".pdf"
        )

    file = open(f"{filepath}/{filename}", "w")
    logger.info(f"#111 [TGE LABEL] File full path: {filepath}/{filename}")
    # end pdf file name using naming convention

    carrier = pre_data["carrier"]

    label_settings = {
        "font_family": "Verdana",
        "font_size_extra_small": "4",
        "font_size_small": "6",
        "font_size_medium": "8",
        "font_size_large": "10",
        "font_size_extra_large": "13",
        "label_dimension_width": "100",
        "label_dimension_height": "150",
        "label_dimension_width_a4": "210",
        "label_dimension_height_a4": "297",
        "landscape_label_dimension_width": "160",
        "landscape_label_dimension_height": "115",
        "label_image_size_width": "47",
        "label_image_size_height": "100",
        "barcode_dimension_width": "85",
        "barcode_dimension_height": "30",
        "barcode_font_size": "18",
        "line_height_extra_small": "3",
        "line_height_small": "5",
        "line_height_medium": "6",
        "line_height_large": "8",
        "line_height_extra_large": "22",
        "margin_v": "0",
        "margin_h": "5",
        "font_size_footer_units_small": "6",
        "font_size_footer_desc_small": "8",
        "font_size_footer_desc": "6",
        "font_size_footer_units": "8",
        "font_size_footer": "8",
    }

    width = float(label_settings["label_dimension_width"]) * mm
    height = float(label_settings["label_dimension_height"]) * mm
    frame_width = float(label_settings["label_dimension_width_a4"]) * mm
    frame_height = float(label_settings["label_dimension_height_a4"]) * mm

    depot_code = pre_data["orig_depot"]

    if carrier == "I & S":
        width = float(label_settings["landscape_label_dimension_width"]) * mm
        height = float(label_settings["landscape_label_dimension_height"]) * mm

    # Tempo Big W
    if (
        booking.kf_client_id == "d69f550a-9327-4ff9-bc8f-242dfca00f7e"
        and carrier == "IPEC"
    ):
        doc = SimpleDocTemplate(
            f"{filepath}/{filename}",
            pagesize=(frame_width, frame_height),
            rightMargin=float(label_settings["margin_h"]) * mm,
            leftMargin=float(label_settings["margin_h"]) * mm,
            topMargin=float(label_settings["margin_v"]) * mm,
            bottomMargin=float(label_settings["margin_v"]) * mm,
        )
    else:
        doc = SimpleDocTemplate(
            f"{filepath}/{filename}",
            pagesize=(width, height),
            rightMargin=float(label_settings["margin_h"]) * mm,
            leftMargin=float(label_settings["margin_h"]) * mm,
            topMargin=float(label_settings["margin_v"]) * mm,
            bottomMargin=float(label_settings["margin_v"]) * mm,
        )

    tge_logo_url = "./static/assets/logos/team_global_express.png"
    tge_logo = Image(tge_logo_url, 30 * mm, 7 * mm)
    dme_logo_url = "./static/assets/logos/dme.png"
    dme_logo = Image(dme_logo_url, 20 * mm, 4 * mm)

    Story = []
    j = 1

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

    lines_data = pre_data["lines_data"]

    has_black_bar = False
    # For `Aberdeen Paper`
    if booking.kf_client_id == "4ac9d3ee-2558-4475-bdbb-9d9405279e81":
        # ------------------------------------ Header Black Bar --------------------------------------
        hr = HRFlowable(
            width=frame_width,
            thickness=4,
            lineCap="square",
            color=colors.black,
            spaceBefore=0,
            spaceAfter=0,
            hAlign="CENTER",
            vAlign="BOTTOM",
            dash=None,
        )

        frame = Table(
            [[hr],[Spacer(1, 4)]],
            colWidths=[frame_width],
            style=[
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
            ],
        )
        Story.append(frame)
        has_black_bar = True

    for line in lines:
        line_data = None
        for _line_data in lines_data:
            if line.pk_booking_lines_id == _line_data.fk_booking_lines_id:
                line_data = _line_data
                break
        for j_index in range(line.e_qty):
            if one_page_label and j_index > 0:
                continue

            logger.info(f"#114 [TGE LABEL] Adding: {line} Label type: {carrier}")

            # Story.append(Spacer(1, 2))

            carrier_name = Paragraph(
                "<font name='Vernada'>" + carrier + "</font>",
                ParagraphStyle(
                    name="header_text",
                    parent=styles["Normal"],
                    fontSize=7.5,
                    leading=8.5,
                    spaceBefore=0,
                    textColor=colors.black,
                ),
            )

            desp_date = Paragraph(
                "<font name='Vernada'>DESP: %s</font>"
                % (booking.puPickUpAvailFrom_Date.strftime("%d/%m/%Y")),
                ParagraphStyle(
                    name="header_text",
                    parent=styles["Normal"],
                    fontSize=7.5,
                    leading=8.5,
                    spaceBefore=0,
                    textColor=colors.black,
                    alignment=TA_RIGHT,
                ),
            )

            depot_code_table = Paragraph(
                "<font name='VernadaBd'>%s</font>" % depot_code,
                ParagraphStyle(
                    name="header_text",
                    parent=styles["Normal"],
                    fontSize=9,
                    leading=10,
                    spaceBefore=0,
                    textColor=colors.black,
                    alignment=TA_CENTER,
                ),
            )

            residential_code = (
                "R" if booking.de_To_AddressType == "residential" else "B"
            )

            residential_code_table = Paragraph(
                "<font name='VernadaBd'>%s</font>" % residential_code,
                ParagraphStyle(
                    name="header_text",
                    parent=styles["Normal"],
                    fontSize=9,
                    leading=10,
                    spaceBefore=0,
                    textColor=colors.black if residential_code == "B" else colors.white,
                    alignment=TA_CENTER,
                ),
            )

            depot_code_width = 10 * mm
            residential_indicator_width = 8 * mm
            depot_residential_height = 4 * mm
            tge_img_width = 30 * mm
            depot_residential_width = 20 * mm
            ipec_width = 16 * mm
            header_data_width = float(
                width - tge_img_width - ipec_width - depot_residential_width
            )
            header_express_width = float(width - 37 * mm)

            if carrier == "I & S":
                header_express_width = 60 * mm

            header_sign_data = [[depot_code_table, residential_code_table]]

            header_sign = Table(
                header_sign_data,
                colWidths=[depot_code_width, residential_indicator_width],
                rowHeights=[depot_residential_height],
                style=[
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                    ("LEFTPADDING", (0, 0), (-1, -1), 0),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                    ("TOPPADDING", (0, 0), (-1, -1), 0),
                    (
                        "BACKGROUND",
                        (1, 0),
                        (1, 0),
                        colors.white if residential_code == "B" else colors.black,
                    ),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.black),
                ],
            )

            if carrier == "IPEC":
                service_name = "Road Express"  # Road
            else:
                service_name = "General"  # General

            header_express = Table(
                [
                    [
                        Paragraph(
                            "<font name='VernadaBd'>%s</font>" % (service_name),
                            ParagraphStyle(
                                name="header_text",
                                parent=styles["Normal"],
                                fontSize=7.5,
                                leading=7.5,
                                spaceBefore=0,
                                textColor=colors.white,
                            ),
                        )
                    ]
                ],
                colWidths=[header_express_width],
                rowHeights=(5 * mm),
                style=[
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                    ("LEFTPADDING", (0, 0), (-1, -1), 3),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                    ("TOPPADDING", (0, 0), (-1, -1), 0),
                    ("BACKGROUND", (0, 0), (-1, 0), colors.black),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
                ],
            )

            header_data = [
                [dme_logo, carrier_name, desp_date, header_sign],
                [tge_logo, header_express, "", ""],
            ]

            header = Table(
                header_data,
                colWidths=[
                    tge_img_width,
                    ipec_width,
                    header_data_width,
                    depot_residential_width,
                ],
                style=[
                    # ("SPAN", (3, 0), (3, 1)),
                    ("SPAN", (1, 1), (3, 1)),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                    ("ALIGN", (3, 0), (3, 0), "RIGHT"),
                    # ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                    # ("LEFTPADDING", (0, 0), (-1, -1), 0),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
                    ("TOPPADDING", (0, 0), (-1, -1), 0),
                    ("RIGHTPADDING", (0, 0), (0, 0), 0),
                ],
            )

            connote = Table(
                [
                    [
                        Paragraph(
                            "<font name='VernadaBd'>CONNOTE #: %s</font>"
                            % (v_FPBookingNumber),
                            ParagraphStyle(
                                name="header_text",
                                parent=styles["Normal"],
                                fontSize=7,
                                leading=8,
                                spaceBefore=0,
                                textColor=colors.black,
                            ),
                        )
                    ]
                ],
                colWidths=[width],
                style=[
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                    # ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                    # ("LEFTPADDING", (0, 0), (-1, -1), 0),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
                    ("TOPPADDING", (0, 0), (-1, -1), 0),
                    ("RIGHTPADDING", (0, 0), (0, 0), 0),
                ],
            )

            receiver_to_text = Paragraph(
                "<font name='VernadaBd'>TO:</font>",
                ParagraphStyle(
                    name="header_text",
                    parent=styles["BodyText"],
                    fontSize=7.5,
                    leading=8,
                    spaceBefore=0,
                    textColor=colors.black,
                ),
            )

            receiver_filed_width = width / 2

            if carrier == "I & S":
                receiver_filed_width = 50 * mm

            receiver_to_name = KeepInFrame(
                (receiver_filed_width - (8 * mm)),
                4 * mm,
                [
                    Paragraph(
                        "<font name='Vernada'>%s</font>" % (booking.deToCompanyName),
                        ParagraphStyle(
                            name="header_text",
                            parent=styles["Normal"],
                            fontSize=7.5,
                            leading=8,
                            spaceBefore=0,
                            textColor=colors.black,
                        ),
                    )
                ],
            )

            receiver_to = Table(
                [[receiver_to_text, receiver_to_name]],
                colWidths=[(8 * mm), (receiver_filed_width - (8 * mm))],
                rowHeights=(4 * mm),
                style=[
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                    # ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                    ("LEFTPADDING", (0, 0), (0, 0), 0),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                    ("TOPPADDING", (0, 0), (-1, -1), 0),
                ],
            )

            receiver_street = Table(
                [
                    [
                        KeepInFrame(
                            receiver_filed_width,
                            4 * mm,
                            [
                                Paragraph(
                                    "<font name='Vernada'>%s</font>"
                                    % (booking.de_To_Address_Street_1),
                                    ParagraphStyle(
                                        name="header_text",
                                        parent=styles["Normal"],
                                        fontSize=7,
                                        leading=7,
                                        spaceBefore=0,
                                        textColor=colors.black,
                                    ),
                                )
                            ],
                            mode="truncate",
                        )
                    ]
                ],
                colWidths=[receiver_filed_width],
                rowHeights=(3 * mm),
                style=[
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                    # ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                    ("LEFTPADDING", (0, 0), (0, 0), 0),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                    ("TOPPADDING", (0, 0), (-1, -1), 0),
                ],
            )

            receiver_suburb = Table(
                [
                    [
                        Paragraph(
                            "<font name='VernadaBd'>%s</font>"
                            % (booking.de_To_Address_Suburb),
                            ParagraphStyle(
                                name="header_text",
                                parent=styles["Normal"],
                                fontSize=8,
                                leading=8,
                                spaceBefore=0,
                                textColor=colors.black,
                            ),
                        )
                    ]
                ],
                colWidths=[receiver_filed_width],
                rowHeights=(3 * mm),
                style=[
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                    # ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                    ("LEFTPADDING", (0, 0), (0, 0), 0),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                    ("TOPPADDING", (0, 0), (-1, -1), 0),
                ],
            )

            receiver_state = Paragraph(
                "<font name='VernadaBd'>%s</font>" % (booking.de_To_Address_State),
                ParagraphStyle(
                    name="header_text",
                    parent=styles["Normal"],
                    fontSize=12,
                    leading=13,
                    spaceBefore=0,
                    textColor=colors.black,
                ),
            )

            receiver_postcode = Paragraph(
                "<font name='VernadaBd'>%s</font>" % (booking.de_To_Address_PostalCode),
                ParagraphStyle(
                    name="header_text",
                    parent=styles["Normal"],
                    fontSize=7.5,
                    leading=8,
                    spaceBefore=0,
                    textColor=colors.black,
                ),
            )

            receiver_state_postcode = Table(
                [[receiver_state, receiver_postcode]],
                colWidths=[(receiver_filed_width / 2), (receiver_filed_width / 2)],
                style=[
                    ("VALIGN", (0, 0), (-1, -1), "BOTTOM"),
                    ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                    # ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                    ("LEFTPADDING", (0, 0), (0, 0), 0),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                    ("TOPPADDING", (0, 0), (-1, -1), 0),
                ],
            )

            receiver_country = Table(
                [
                    [
                        Paragraph(
                            "<font name='VernadaBd'>%s</font>"
                            % (booking.de_To_Address_Country),
                            ParagraphStyle(
                                name="header_text",
                                parent=styles["Normal"],
                                fontSize=7,
                                leading=8,
                                spaceBefore=0,
                                textColor=colors.black,
                            ),
                        )
                    ]
                ],
                colWidths=[receiver_filed_width],
                rowHeights=(4 * mm),
                style=[
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                    # ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                    ("LEFTPADDING", (0, 0), (0, 0), 0),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                    ("TOPPADDING", (0, 0), (-1, -1), 0),
                ],
            )

            contact_number = Table(
                [
                    [
                        Paragraph(
                            "<font name='Vernada'>Phone: %s</font>"
                            % (booking.de_to_Phone_Main),
                            ParagraphStyle(
                                name="header_text",
                                parent=styles["Normal"],
                                fontSize=5,
                                leading=6,
                                spaceBefore=0,
                                textColor=colors.black,
                            ),
                        )
                    ]
                ],
                colWidths=[receiver_filed_width],
                style=[
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                    # ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                    ("LEFTPADDING", (0, 0), (0, 0), 0),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                    ("TOPPADDING", (0, 0), (-1, -1), 0),
                ],
            )

            contact_name = Table(
                [
                    [
                        Paragraph(
                            "<font name='Vernada'>Contact: %s</font>"
                            % (booking.de_to_Contact_F_LName),
                            ParagraphStyle(
                                name="header_text",
                                parent=styles["Normal"],
                                fontSize=5,
                                leading=6,
                                spaceBefore=0,
                                textColor=colors.black,
                            ),
                        )
                    ]
                ],
                colWidths=[receiver_filed_width],
                style=[
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                    # ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                    ("LEFTPADDING", (0, 0), (0, 0), 0),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                    ("TOPPADDING", (0, 0), (-1, -1), 0),
                ],
            )

            special_ins_header = Table(
                [
                    [
                        Paragraph(
                            "<font name='VernadaBd'>Special Instructions:</font>",
                            ParagraphStyle(
                                name="header_text",
                                parent=styles["Normal"],
                                fontSize=6,
                                leading=7,
                                spaceBefore=0,
                                textColor=colors.black,
                            ),
                        )
                    ]
                ],
                colWidths=[receiver_filed_width],
                rowHeights=(4 * mm),
                style=[
                    ("VALIGN", (0, 0), (-1, -1), "BOTTOM"),
                    ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                    ("LEFTPADDING", (0, 0), (0, 0), 0),
                    ("BOTTOMPADDING", (0, 0), (0, 0), 0),
                    ("TOPPADDING", (0, 0), (-1, -1), 0),
                ],
            )

            # Special Instructions
            specialInstructions = ""
            if booking.pu_pickup_instructions_address:
                specialInstructions += booking.pu_pickup_instructions_address
            if booking.pu_PickUp_Instructions_Contact:
                specialInstructions += f" {booking.pu_PickUp_Instructions_Contact}"
            if booking.de_to_PickUp_Instructions_Address:
                specialInstructions += f" {booking.de_to_PickUp_Instructions_Address}"
            if booking.de_to_Pick_Up_Instructions_Contact:
                specialInstructions += f" {booking.de_to_Pick_Up_Instructions_Contact}"

            if (
                booking.b_client_name == "Tempo Pty Ltd"
                and "xtensive" in booking.deToCompanyName.lower()
                and line_data
            ):
                specialInstructions = (
                    f"Quote {line_data.clientRefNumber} at pickup"
                    if line_data.clientRefNumber
                    else ""
                )

            special_instruction = Table(
                [
                    [
                        Paragraph(
                            "<font name='Vernada'>%s</font>" % (specialInstructions),
                            ParagraphStyle(
                                name="header_text",
                                parent=styles["Normal"],
                                fontSize=5,
                                leading=6,
                                spaceBefore=0,
                                textColor=colors.black,
                            ),
                        )
                    ]
                ],
                colWidths=[receiver_filed_width],
                rowHeights=(4 * mm),
                style=[
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                    # ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                    ("LEFTPADDING", (0, 0), (0, 0), 0),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                    ("TOPPADDING", (0, 0), (-1, -1), 0),
                ],
            )

            visual_aid_banner = Table(
                [[""]],
                colWidths=[receiver_filed_width],
                rowHeights=(4 * mm),
                style=[
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                    # ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                    # ("LEFTPADDING", (0, 0), (-1, -1), 0),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                    ("TOPPADDING", (0, 0), (-1, -1), 0),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.black),
                ],
            )

            receiver_data = [
                [receiver_to],
                [receiver_street],
                [receiver_suburb],
                [receiver_state_postcode],
                [receiver_country],
                [contact_number],
                [contact_name],
                [special_ins_header],
                [special_instruction],
                [visual_aid_banner],
            ]

            receiver = Table(
                receiver_data,
                colWidths=[receiver_filed_width],
                style=[
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                    # ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                    # ("LEFTPADDING", (0, 0), (-1, -1), 0),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                    ("TOPPADDING", (0, 0), (-1, -1), 0),
                ],
            )

            line_length = _get_dim_amount(line.e_dimUOM) * line.e_dimLength
            line_width = _get_dim_amount(line.e_dimUOM) * line.e_dimWidth
            line_height = _get_dim_amount(line.e_dimUOM) * line.e_dimHeight
            line_weight = _get_weight_amount(line.e_weightUOM) * line.e_weightPerEach

            original_sscc = line.sscc
            sscc_barcode_labels = gen_barcode_2(booking, line, j_index)

            qr_code_string = gen_qr_code_string(
                booking,
                line,
                v_FPBookingNumber,
                sscc_barcode_labels["label_text"],
                carrier,
            )

            qr_canvas_width = receiver_filed_width - 6 * mm
            qr_code_width = qr_canvas_width
            if carrier == "I & S":
                qr_canvas_width = 50 * mm
                qr_code_width = 42 * mm

            qr_canvas = Drawing(qr_code_width, qr_code_width)
            qr_canvas.add(Rect(0, 0, 0, 0, strokeWidth=1, fillColor=None))
            qr_canvas.add(
                QrCodeWidget(
                    value=qr_code_string,
                    barWidth=qr_code_width,
                    barHeight=qr_code_width,
                )
            )

            if carrier == "I & S":
                qr_code = Table(
                    [[qr_canvas]],
                    colWidths=[qr_canvas_width],
                    rowHeights=[qr_canvas_width],
                    style=[
                        ("VALIGN", (0, 0), (0, 0), "MIDDLE"),
                        ("ALIGN", (0, 0), (0, 0), "CENTER"),
                        ("TOPPADDING", (0, 0), (-1, -1), 0),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                        ("LEFTPADDING", (0, 0), (-1, -1), 0),
                        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                    ],
                )
            else:
                qr_code = Table(
                    [[qr_canvas]],
                    colWidths=[qr_canvas_width],
                    rowHeights=[qr_canvas_width - (7.5 * mm)],
                    style=[
                        ("VALIGN", (0, 0), (0, 0), "BOTTOM"),
                        ("ALIGN", (0, 0), (0, 0), "LEFT"),
                        ("TOPPADDING", (0, 0), (-1, -1), 0),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                        ("LEFTPADDING", (0, 0), (-1, -1), 0),
                        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                    ],
                )

            recevier_line_data = [[receiver, qr_code]]
            recevier_line = Table(
                recevier_line_data,
                colWidths=[receiver_filed_width, receiver_filed_width],
                style=[
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                    ("LEFTPADDING", (0, 0), (-1, -1), 0),
                    ("LEFTPADDING", (1, 0), (1, 0), 9),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                    ("TOPPADDING", (0, 0), (-1, -1), 0),
                ],
            )

            indicator_width = width / 7 - (2 * mm)
            indicator_height = indicator_width * (3 / 5)
            if carrier == "I & S":
                indicator_height = 15 * mm

            dg_doods_indicator = Table(
                [
                    [
                        Paragraph(
                            "<font name='VernadaBd'>DG's:<br />No</font>",
                            ParagraphStyle(
                                name="header_text",
                                parent=styles["Normal"],
                                fontSize=7,
                                leading=8,
                                spaceBefore=0,
                                textColor=colors.black,
                                alignment=TA_CENTER,
                            ),
                        )
                    ]
                ],
                colWidths=[indicator_width],
                rowHeights=[indicator_height],
                style=[
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 2),
                    ("LEFTPADDING", (0, 0), (-1, -1), 2),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
                    ("TOPPADDING", (0, 0), (-1, -1), 0),
                    ("GRID", (0, 0), (0, 0), 0.7, colors.black),
                ],
            )

            adp = Table(
                [[""]],
                colWidths=[indicator_width],
                rowHeights=[indicator_height],
                style=[
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 2),
                    ("LEFTPADDING", (0, 0), (-1, -1), 2),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
                    ("TOPPADDING", (0, 0), (-1, -1), 0),
                    ("GRID", (0, 0), (0, 0), 0.7, colors.black),
                ],
            )

            nsr = Table(
                [[""]],
                colWidths=[indicator_width],
                rowHeights=[indicator_height],
                style=[
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 2),
                    ("LEFTPADDING", (0, 0), (-1, -1), 2),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
                    ("TOPPADDING", (0, 0), (-1, -1), 0),
                    ("GRID", (0, 0), (0, 0), 0.7, colors.black),
                ],
            )

            items = Table(
                [
                    [
                        Paragraph(
                            "<font name='VernadaBd'>%s of %s</font>" % (j, totalQty),
                            ParagraphStyle(
                                name="header_text",
                                parent=styles["Normal"],
                                fontSize=5,
                                leading=6,
                                spaceBefore=0,
                                textColor=colors.black,
                                alignment=TA_CENTER,
                            ),
                        )
                    ]
                ],
                colWidths=[indicator_width],
                rowHeights=[indicator_height],
                style=[
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 2),
                    ("LEFTPADDING", (0, 0), (-1, -1), 2),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
                    ("TOPPADDING", (0, 0), (-1, -1), 0),
                    ("GRID", (0, 0), (0, 0), 0.7, colors.black),
                ],
            )

            dimentions = Table(
                [
                    [
                        Paragraph(
                            "<font name='VernadaBd'>L: %s<br />W: %s<br />H: %s</font>"
                            % (
                                int(line_length * 100),
                                int(line_width * 100),
                                int(line_height * 100),
                            ),
                            ParagraphStyle(
                                name="header_text",
                                parent=styles["Normal"],
                                fontSize=5,
                                leading=6,
                                spaceBefore=0,
                                textColor=colors.black,
                                alignment=TA_CENTER,
                            ),
                        )
                    ]
                ],
                colWidths=[indicator_width],
                rowHeights=[indicator_height],
                style=[
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 2),
                    ("LEFTPADDING", (0, 0), (-1, -1), 2),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
                    ("TOPPADDING", (0, 0), (-1, -1), 0),
                    ("GRID", (0, 0), (0, 0), 0.7, colors.black),
                ],
            )

            weight = Table(
                [
                    [
                        Paragraph(
                            "<font name='VernadaBd' color='white'>%s<br />KG</font>"
                            % (line.e_weightPerEach),
                            ParagraphStyle(
                                name="header_text",
                                parent=styles["Normal"],
                                fontSize=6,
                                leading=7,
                                spaceBefore=0,
                                textColor=colors.black,
                                alignment=TA_CENTER,
                                backColor="black",
                            ),
                        )
                    ]
                ],
                colWidths=[indicator_width],
                rowHeights=[indicator_height],
                style=[
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 2),
                    ("LEFTPADDING", (0, 0), (-1, -1), 2),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
                    ("TOPPADDING", (0, 0), (-1, -1), 0),
                    ("GRID", (0, 0), (0, 0), 0.7, colors.black),
                    ("BACKGROUND", (0, 0), (0, 0), colors.black),
                ],
            )

            rectangle_line = Table(
                [[dg_doods_indicator, adp, nsr, items, dimentions, weight]],
                rowHeights=[indicator_height],
                style=[
                    ("VALIGN", (0, 0), (-1, -1), "BOTTOM"),
                    ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                    # ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                    # ("LEFTPADDING", (0, 0), (-1, -1), 0),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                    ("TOPPADDING", (0, 0), (-1, -1), 0),
                ],
            )

            service_barcode_labels = gen_barcode_1(booking, carrier)

            service_barcode_width = width
            bottom_barcode_width = width
            service_barcode_height = 26 * mm
            barWidth = 1.6
            serviceBarWidth = 1.6
            if carrier == "I & S":
                bottom_barcode_width = 140 * mm
                service_barcode_width = 120 * mm
                service_barcode_height = 17 * mm
                barWidth = 2.6
                serviceBarWidth = 1.3

            service_barcode = Table(
                [
                    [
                        code128.Code128(
                            service_barcode_labels["label_bar"],
                            barHeight=service_barcode_height,
                            barWidth=serviceBarWidth,
                            humanReadable=False,
                            subset="C",
                        )
                    ],
                    [
                        Paragraph(
                            "<font name='Vernada'>%s</font>"
                            % (service_barcode_labels["label_text"]),
                            ParagraphStyle(
                                name="header_text",
                                parent=styles["Normal"],
                                fontSize=7,
                                leading=8,
                                spaceBefore=0,
                                textColor=colors.black,
                                alignment=TA_CENTER,
                            ),
                        )
                    ],
                ],
                colWidths=[service_barcode_width],
                rowHeights=[service_barcode_height, (5 * mm)],
                style=[
                    ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                    ("VALIGN", (0, 0), (0, 0), "TOP"),
                    ("LEFTPADDING", (0, 0), (0, 0), 10),
                ],
            )

            sscc_barcode = Table(
                [
                    [
                        code128.Code128(
                            sscc_barcode_labels["label_bar"],
                            barHeight=26 * mm,
                            barWidth=barWidth,
                            humanReadable=False,
                            subset="C",
                        )
                    ],
                    [
                        Paragraph(
                            "<font name='Vernada'>%s</font>"
                            % (sscc_barcode_labels["label_text"]),
                            ParagraphStyle(
                                name="header_text",
                                parent=styles["Normal"],
                                fontSize=7,
                                leading=8,
                                spaceBefore=0,
                                textColor=colors.black,
                                alignment=TA_CENTER,
                            ),
                        )
                    ],
                ],
                colWidths=[width],
                rowHeights=[(27 * mm), (3 * mm)],
                style=[
                    ("ALIGN", (0, 0), (0, 0), "LEFT"),
                    ("VALIGN", (0, 0), (0, 0), "BOTTOM"),
                    ("LEFTPADDING", (0, 0), (0, 0), 0),
                ],
            )

            hr = HRFlowable(
                width=(width),
                thickness=1,
                lineCap="square",
                color=colors.black,
                spaceBefore=0,
                spaceAfter=0,
                hAlign="CENTER",
                vAlign="BOTTOM",
                dash=None,
            )

            sender_from_text = Paragraph(
                "<font name='VernadaBd'>FROM:</font>",
                ParagraphStyle(
                    name="header_text",
                    parent=styles["Normal"],
                    fontSize=5,
                    leading=6,
                    spaceBefore=0,
                    textColor=colors.black,
                ),
            )

            sender_from_name = Paragraph(
                "<font name='Vernada'>%s</font>" % (booking.puCompany),
                ParagraphStyle(
                    name="header_text",
                    parent=styles["Normal"],
                    fontSize=5,
                    leading=6,
                    spaceBefore=0,
                    textColor=colors.black,
                ),
            )

            sender_filed_width = width / 2

            sender_from = Table(
                [[sender_from_text, sender_from_name]],
                colWidths=[(10 * mm), (sender_filed_width - (10 * mm))],
                style=[
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                    ("LEFTPADDING", (1, 0), (-1, -1), 0),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                    ("TOPPADDING", (0, 0), (-1, -1), 0),
                ],
            )

            sender_suburb_state = Table(
                [
                    [
                        Paragraph(
                            "<font name='Vernada'>%s %s</font>"
                            % (booking.pu_Address_Suburb, booking.pu_Address_State),
                            ParagraphStyle(
                                name="header_text",
                                parent=styles["Normal"],
                                fontSize=5,
                                leading=6,
                                spaceBefore=0,
                                textColor=colors.black,
                            ),
                        )
                    ]
                ],
                colWidths=[receiver_filed_width],
                style=[
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                    # ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                    # ("LEFTPADDING", (0, 0), (-1, -1), 0),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                    ("TOPPADDING", (0, 0), (-1, -1), 0),
                ],
            )

            sender_postcode_country = Table(
                [
                    [
                        Paragraph(
                            "<font name='Vernada'>%s</font>"
                            % (booking.pu_Address_PostalCode),
                            ParagraphStyle(
                                name="header_text",
                                parent=styles["Normal"],
                                fontSize=5,
                                leading=6,
                                spaceBefore=0,
                                textColor=colors.black,
                            ),
                        ),
                        Paragraph(
                            "<font name='VernadaBd'>%s</font>"
                            % (booking.pu_Address_Country),
                            ParagraphStyle(
                                name="header_text",
                                parent=styles["Normal"],
                                fontSize=5,
                                leading=6,
                                spaceBefore=0,
                                textColor=colors.black,
                            ),
                        ),
                    ]
                ],
                colWidths=[(12 * mm), (sender_filed_width - (12 * mm))],
                style=[
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                    # ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                    # ("LEFTPADDING", (0, 0), (-1, -1), 0),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                    ("TOPPADDING", (0, 0), (-1, -1), 0),
                ],
            )
            account = get_account_detail(booking)
            sender_payer_ac = Table(
                [
                    [
                        Paragraph(
                            "<font name='VernadaBd'>Payor A/C: %s</font>"
                            % (
                                account["account_number"]
                                if "account_number" in account
                                else ""
                            ),
                            ParagraphStyle(
                                name="header_text",
                                parent=styles["Normal"],
                                fontSize=5,
                                leading=6,
                                spaceBefore=0,
                                textColor=colors.black,
                            ),
                        )
                    ]
                ],
                colWidths=[receiver_filed_width],
                style=[
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                    ("LEFTPADDING", (0, 0), (-1, -1), 0),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                    ("TOPPADDING", (0, 0), (-1, -1), 0),
                ],
            )

            sender_contact_name = Table(
                [
                    [
                        Paragraph(
                            "<font name='VernadaBd'>Contact: %s</font>"
                            % (booking.pu_Contact_F_L_Name),
                            ParagraphStyle(
                                name="header_text",
                                parent=styles["Normal"],
                                fontSize=5,
                                leading=6,
                                spaceBefore=0,
                                textColor=colors.black,
                            ),
                        )
                    ]
                ],
                colWidths=[receiver_filed_width],
                style=[
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                    ("LEFTPADDING", (0, 0), (-1, -1), 0),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                    ("TOPPADDING", (0, 0), (-1, -1), 0),
                ],
            )

            sender_contact_number = Table(
                [
                    [
                        Paragraph(
                            "<font name='VernadaBd'>PH: %s</font>"
                            % (booking.pu_Contact_F_L_Name),
                            ParagraphStyle(
                                name="header_text",
                                parent=styles["Normal"],
                                fontSize=5,
                                leading=6,
                                spaceBefore=0,
                                textColor=colors.black,
                            ),
                        )
                    ]
                ],
                colWidths=[receiver_filed_width],
                style=[
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                    ("LEFTPADDING", (0, 0), (-1, -1), 0),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                    ("TOPPADDING", (0, 0), (-1, -1), 0),
                ],
            )

            sender_data = [
                [Spacer(1, 1), Spacer(1, 1)],
                [sender_from, sender_payer_ac],
                [Spacer(1, 1), Spacer(1, 1)],
                [sender_suburb_state, sender_contact_name],
                [Spacer(1, 1), Spacer(1, 1)],
                [sender_postcode_country, sender_contact_number],
                [Spacer(1, 1), Spacer(1, 1)],
            ]

            sender = Table(
                sender_data,
                colWidths=[sender_filed_width, sender_filed_width],
                style=[
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                    ("LEFTPADDING", (0, 0), (-1, -1), 0),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                    ("TOPPADDING", (0, 0), (-1, -1), 0),
                ],
            )

            # BioPak
            if booking.kf_client_id == "7EAA4B16-484B-3944-902E-BC936BFEF535":
                ref_number = booking.b_clientReference_RA_Numbers or ""
            # Tempo Big W
            elif booking.kf_client_id == "d69f550a-9327-4ff9-bc8f-242dfca00f7e":
                ref_number = (line_data and line_data.clientRefNumber) or ""
            # Not BioPak
            else:
                ref_number = f"{booking.b_client_order_num or booking.b_client_sales_inv_num or ''}-{original_sscc}"

            ref_width = width
            if carrier == "I & S":
                ref_width = 40 * mm
            ref = Table(
                [
                    [
                        Paragraph(
                            "<font name='Vernada' size=%s>REF: %s</font>"
                            % (label_settings["font_size_footer_desc"], ref_number[:55] if has_black_bar else ref_number[:80]),
                            style_reference_text,
                        )
                    ]
                ],
                colWidths=[ref_width],
                style=[
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                    # ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                    # ("LEFTPADDING", (0, 0), (-1, -1), 0),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                    ("TOPPADDING", (0, 0), (-1, -1), 0),
                ],
            )
            description_goods_width = 25 * mm
            # if carrier == "I & S":
            #     description_goods_width = 0 * mm

            description_goods = Table(
                [
                    [
                        Paragraph(
                            "<font name='VernadaBd'>Description of Goods:</font>",
                            ParagraphStyle(
                                name="header_text",
                                parent=styles["Normal"],
                                fontSize=5,
                                leading=6,
                                spaceBefore=0,
                                textColor=colors.black,
                            ),
                        ),
                        Paragraph(
                            "<font name='Vernada'>%s</font>" % (line.e_item[:50] if has_black_bar else line.e_item),
                            ParagraphStyle(
                                name="header_text",
                                parent=styles["Normal"],
                                fontSize=5,
                                leading=6,
                                spaceBefore=0,
                                textColor=colors.black,
                            ),
                        ),
                    ]
                ],
                colWidths=[description_goods_width, (width - description_goods_width)],
                style=[
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                    ("LEFTPADDING", (1, 0), (-1, -1), 0),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                    ("TOPPADDING", (0, 0), (-1, -1), 0),
                ],
            )

            declaration_by = Table(
                [
                    [
                        Paragraph(
                            "<font name='VernadaBd'>DECLARATION BY:</font>",
                            ParagraphStyle(
                                name="header_text",
                                parent=styles["Normal"],
                                fontSize=5,
                                leading=6,
                                spaceBefore=0,
                                textColor=colors.black,
                            ),
                        ),
                        Paragraph(
                            "<font name='Vernada'>%s</font>"
                            % (booking.pu_Contact_F_L_Name),
                            ParagraphStyle(
                                name="header_text",
                                parent=styles["Normal"],
                                fontSize=5,
                                leading=6,
                                spaceBefore=0,
                                textColor=colors.black,
                            ),
                        ),
                    ]
                ],
                colWidths=[(22 * mm), (width - (22 * mm))],
                style=[
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                    ("LEFTPADDING", (1, 0), (-1, -1), 0),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                    ("TOPPADDING", (0, 0), (-1, -1), 0),
                ],
            )

            dangerous_goods_declaration = Table(
                [
                    [
                        Paragraph(
                            "<font name='Vernada'>%s</font>" % (""),
                            ParagraphStyle(
                                name="header_text",
                                parent=styles["Normal"],
                                fontSize=4.5,
                                leading=5,
                                spaceBefore=0,
                                textColor=colors.black,
                            ),
                        )
                    ]
                ],
                colWidths=[width],
                style=[
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                    # ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                    # ("LEFTPADDING", (0, 0), (-1, -1), 0),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                    ("TOPPADDING", (0, 0), (-1, -1), 0),
                ],
            )

            footer_part_width = width * (1 / 2)

            pkg_units_font_size = "font_size_footer"
            if len(booking_line.e_type_of_packaging) < 8:
                pkg_units_font_size = "font_size_footer"
            elif len(booking_line.e_type_of_packaging) <= 10:
                pkg_units_font_size = "font_size_footer_desc"
            else:
                pkg_units_font_size = "font_size_footer_units_small"

            footer_units_part = Table(
                [
                    [
                        Paragraph(
                            "<font size=%s><b>PKG UNITS:</b></font>"
                            % (label_settings["font_size_footer_desc"],),
                            style_reference_text,
                        ),
                        [
                            Paragraph(
                                "<font size=%s><b>%s</b></font>"
                                % (
                                    label_settings[pkg_units_font_size],
                                    booking_line.e_type_of_packaging,
                                ),
                                style_footer_text,
                            ),
                        ],
                    ],
                ],
                colWidths=[
                    footer_part_width * (2 / 7),
                    footer_part_width * (5 / 7),
                ],
                rowHeights=[5 * mm],
                style=[
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                    ("LEFTPADDING", (0, 0), (-1, -1), 0),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                    ("TOPPADDING", (0, 0), (-1, -1), 0),
                ],
            )

            footer_bin_part = Table(
                [
                    [
                        Paragraph(
                            "<font size=%s><b>BIN:</b></font>"
                            % (label_settings["font_size_footer_desc"],),
                            style_reference_text,
                        ),
                        Paragraph(
                            "<font size=%s><b>%s</b></font>"
                            % (
                                label_settings["font_size_footer"],
                                "No data"
                                if booking_line.e_bin_number is None
                                or len(booking_line.e_bin_number) == 0
                                else booking_line.e_bin_number[:25],
                            ),
                            style_footer_text,
                        ),
                    ],
                ],
                colWidths=[
                    footer_part_width * (1 / 8),
                    footer_part_width * (7 / 8),
                ],
                rowHeights=[3 * mm],
                style=[
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                    ("LEFTPADDING", (0, 0), (-1, -1), 0),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                    ("TOPPADDING", (0, 0), (-1, -1), 0),
                ],
            )

            str_desc = booking_line.e_item.replace("\n", " ").replace("\t", " ")[:80]
            font_size_desc = "font_size_footer"
            if len(str_desc) < 24:
                font_size_desc = "font_size_footer"
            elif len(str_desc) < 55:
                font_size_desc = "font_size_footer_units"
            else:
                font_size_desc = "font_size_footer_desc_small"

            footer_desc_part = Table(
                [
                    [
                        Paragraph(
                            "<font size=%s><b>DESC:</b></font>"
                            % (label_settings["font_size_footer_desc"],),
                            style_reference_text,
                        ),
                        Paragraph(
                            "<font size=%s><b>%s</b></font>"
                            % (
                                label_settings[font_size_desc],
                                str_desc[:50] if has_black_bar else str_desc,
                            ),
                            style_desc_text,
                        ),
                    ],
                ],
                colWidths=[
                    footer_part_width * (1 / 7),
                    footer_part_width * (13 / 7),
                ],
                rowHeights=[3 * mm],
                style=[
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                    ("LEFTPADDING", (0, 0), (-1, -1), 0),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                    ("TOPPADDING", (0, 0), (-1, -1), 0),
                ],
            )

            if (
                booking.b_client_name == "Tempo Pty Ltd"
                and "xtensive" in booking.deToCompanyName.lower()
                and line_data
            ):
                footer_part = Table(
                    [
                        [
                            Paragraph(
                                "<font size=%s><b>FAULT DESCRIPTION:</b></font>"
                                % (label_settings["font_size_footer_desc"],),
                                style_reference_text,
                            ),
                            [
                                Paragraph(
                                    "<font size=%s><b>%s</b></font>"
                                    % (
                                        label_settings[pkg_units_font_size],
                                        line_data.itemFaultDescription or "",
                                    ),
                                    style_footer_text,
                                ),
                            ],
                        ],
                    ],
                    colWidths=[
                        width * (1 / 4),
                        width * (3 / 4),
                    ],
                    rowHeights=[5 * mm],
                    style=[
                        ("VALIGN", (0, 0), (-1, -1), "TOP"),
                        ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                        ("LEFTPADDING", (0, 0), (-1, -1), 6),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                        ("TOPPADDING", (0, 0), (-1, -1), 0),
                    ],
                )
            else:
                footer_part = Table(
                    [
                        [
                            footer_units_part,
                            footer_bin_part,
                        ],
                        [
                            footer_desc_part,
                            "",
                        ],
                    ],
                    colWidths=[
                        footer_part_width,
                        footer_part_width,
                    ],
                    rowHeights=[3 * mm, 3 * mm],
                    style=[
                        ("VALIGN", (0, 0), (-1, -1), "TOP"),
                        ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                        ("SPAN", (0, 1), (1, 1)),
                        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                        ("LEFTPADDING", (0, 0), (-1, -1), 0),
                        ("LEFTPADDING", (0, 0), (0, -1), 6),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                        ("TOPPADDING", (0, 0), (-1, -1), 0),
                        ("TOPPADDING", (0, 0), (-1, 0), 2),
                        ("TOPPADDING", (0, 1), (-1, 1), 2),
                    ],
                )

            frame_content_data = [
                [header],
                [connote],
                [recevier_line],
                [rectangle_line],
                [service_barcode],
                [sscc_barcode],
                [hr],
                [Spacer(1, 1)],
                [sender],
                [ref],
                [description_goods],
                [declaration_by],
                # [dangerous_goods_declaration],
                [footer_part],
            ]

            if carrier == "Priority":
                frame_content_data = [
                    [header],
                    [connote],
                    [recevier_line],
                    [Spacer(1, 3)],
                    [rectangle_line],
                    [Spacer(1, 3)],
                    [Spacer(1, 10)],
                    [hr],
                    [Spacer(1, 20)],
                    [sscc_barcode],
                    [Spacer(1, 20)],
                    [hr],
                    [Spacer(1, 10)],
                    [sender],
                    [ref],
                    [description_goods],
                    [declaration_by],
                    [dangerous_goods_declaration],
                    [footer_part],
                ]
            elif carrier == "I & S":
                header_width = float(width - qr_canvas_width)
                service_width = 50 * mm
                connote_suffix_width = 30 * mm
                receiver_left_width = 80 * mm
                receiver_right_width = float(header_width - receiver_left_width)
                tge_img_width = 15 * mm
                tge_logo = Image(tge_logo_url, 15 * mm, 5 * mm)
                carrier_name = Paragraph(
                    "<font name='Vernada'>Intermodal & Specialised</font>",
                    ParagraphStyle(
                        name="header_text",
                        parent=styles["Normal"],
                        fontSize=6,
                        leading=7,
                        spaceBefore=0,
                        textColor=colors.black,
                    ),
                )

                connote = Table(
                    [
                        [
                            Paragraph(
                                "<font name='VernadaBd'>CONNOTE #: </font>",
                                ParagraphStyle(
                                    name="header_text",
                                    parent=styles["Normal"],
                                    fontSize=7,
                                    leading=8,
                                    spaceBefore=0,
                                    textColor=colors.black,
                                ),
                            ),
                            Paragraph(
                                "<font name='VernadaBd'>%s</font>"
                                % (v_FPBookingNumber),
                                ParagraphStyle(
                                    name="header_text",
                                    parent=styles["Normal"],
                                    fontSize=11,
                                    leading=11,
                                    spaceBefore=0,
                                    textColor=colors.black,
                                ),
                            ),
                        ]
                    ],
                    colWidths=[service_width * (2 / 5), service_width * (4 / 5)],
                    style=[
                        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                        ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                        ("LEFTPADDING", (0, 0), (-1, -1), 0),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                        ("TOPPADDING", (0, 0), (-1, -1), 0),
                        ("RIGHTPADDING", (0, 0), (0, 0), 0),
                    ],
                )

                header_data = [
                    [dme_logo, ""],
                    [tge_logo, carrier_name],
                    [header_express, ""],
                    [connote, ""],
                ]

                header_left = Table(
                    header_data,
                    colWidths=[
                        tge_img_width,
                        service_width - tge_img_width,
                    ],
                    style=[
                        # ("SPAN", (3, 0), (3, 1)),
                        # ("SPAN", (2, 0), (2, 1)),
                        ("SPAN", (0, 3), (1, 3)),
                        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                        ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
                        ("TOPPADDING", (0, 0), (-1, -1), 0),
                        ("RIGHTPADDING", (0, 0), (0, 0), 0),
                    ],
                )

                indicator_width = header_width - service_width - connote_suffix_width

                connote_suffix = Table(
                    [
                        [
                            Paragraph(
                                "<font name='VernadaBd'>%s</font>"
                                % v_FPBookingNumber[-5:],
                                ParagraphStyle(
                                    name="header_text",
                                    parent=styles["Normal"],
                                    fontSize=20,
                                    leading=22,
                                    spaceBefore=0,
                                    textColor=colors.black,
                                    alignment=TA_CENTER,
                                ),
                            )
                        ]
                    ],
                    colWidths=[connote_suffix_width],
                    style=[
                        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                        ("LEFTPADDING", (0, 0), (-1, -1), 0),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                        ("TOPPADDING", (0, 0), (-1, -1), 0),
                        ("GRID", (0, 0), (0, 0), 0.7, colors.black),
                    ],
                )

                rectangle_line1 = Table(
                    [
                        [
                            Paragraph(
                                "<font name='VernadaBd' color='white'>%s</font>"
                                % depot_code,
                                ParagraphStyle(
                                    name="header_text",
                                    parent=styles["Normal"],
                                    fontSize=20,
                                    leading=22,
                                    spaceBefore=0,
                                    textColor=colors.black,
                                    alignment=TA_CENTER,
                                ),
                            )
                        ]
                    ],
                    colWidths=[indicator_width],
                    # rowHeights=[indicator_height],
                    style=[
                        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                        ("LEFTPADDING", (0, 0), (-1, -1), 0),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                        ("TOPPADDING", (0, 0), (-1, -1), 0),
                        ("GRID", (0, 0), (0, 0), 0.7, colors.black),
                        ("BACKGROUND", (0, 0), (0, 0), colors.black),
                    ],
                )

                rectangle_line2 = Table(
                    [
                        [
                            Paragraph(
                                "<font name='VernadaBd'>DG's:<br />No</font>",
                                ParagraphStyle(
                                    name="header_text",
                                    parent=styles["Normal"],
                                    fontSize=10,
                                    leading=10,
                                    spaceBefore=0,
                                    textColor=colors.black,
                                    alignment=TA_CENTER,
                                ),
                            ),
                            Paragraph(
                                "<font name='VernadaBd'>%s of %s</font>"
                                % (j, totalQty),
                                ParagraphStyle(
                                    name="header_text",
                                    parent=styles["Normal"],
                                    fontSize=10,
                                    leading=10,
                                    spaceBefore=0,
                                    textColor=colors.black,
                                    alignment=TA_CENTER,
                                ),
                            ),
                        ]
                    ],
                    colWidths=[indicator_width / 2, indicator_width / 2],
                    rowHeights=[indicator_height],
                    style=[
                        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                        ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                        # ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                        # ("LEFTPADDING", (0, 0), (-1, -1), 0),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                        ("TOPPADDING", (0, 0), (-1, -1), 0),
                        ("GRID", (0, 0), (-1, -1), 0.7, colors.black),
                    ],
                )

                rectangle_line = [
                    [rectangle_line1],
                    [rectangle_line2],
                ]

                header = Table(
                    [
                        [header_left, connote_suffix, rectangle_line],
                    ],
                    colWidths=[
                        service_width,
                        connote_suffix_width,
                        header_width - service_width - connote_suffix_width,
                    ],
                    style=[
                        ("VALIGN", (0, 0), (-1, -1), "TOP"),
                        ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                        ("TOPPADDING", (0, 0), (-1, -1), 0),
                        ("RIGHTPADDING", (0, 0), (0, 0), 0),
                    ],
                )

                receiver_to_name = Paragraph(
                    "<font name='Vernada'>%s</font>"
                    % (booking.deToCompanyName or "")[:30],
                    ParagraphStyle(
                        name="header_text",
                        parent=styles["Normal"],
                        fontSize=7.5,
                        leading=8,
                        spaceBefore=0,
                        textColor=colors.black,
                    ),
                )

                receiver_data = [
                    [receiver_to_name, ""],
                    [receiver_street, ""],
                    [receiver_suburb, ""],
                    [receiver_state_postcode, special_ins_header],
                    [receiver_country, special_instruction],
                    # [contact_number],
                    # [contact_name],
                ]

                receiver_left = Table(
                    receiver_data,
                    colWidths=[receiver_left_width * 0.5, receiver_left_width * 0.5],
                    style=[
                        ("VALIGN", (0, 0), (-1, -1), "TOP"),
                        ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                        ("TOPPADDING", (0, 0), (-1, -1), 0),
                        ("SPAN", (0, 0), (1, 0)),
                        ("SPAN", (0, 1), (1, 1)),
                        ("SPAN", (0, 2), (1, 2)),
                    ],
                )

                indicator_width = 20 * mm
                indicator_height = 10 * mm

                adp = Table(
                    [[""]],
                    colWidths=[indicator_width / 2],
                    rowHeights=[indicator_height],
                    style=[
                        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                        ("LEFTPADDING", (0, 0), (-1, -1), 0),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                        ("TOPPADDING", (0, 0), (-1, -1), 0),
                        ("GRID", (0, 0), (0, 0), 0.7, colors.black),
                    ],
                )

                weight = Table(
                    [
                        [
                            Paragraph(
                                "<font name='VernadaBd' color='white'>%s<br />KG</font>"
                                % (line.e_weightPerEach),
                                ParagraphStyle(
                                    name="header_text",
                                    parent=styles["Normal"],
                                    fontSize=6,
                                    leading=7,
                                    spaceBefore=0,
                                    textColor=colors.black,
                                    alignment=TA_CENTER,
                                    backColor="black",
                                ),
                            )
                        ]
                    ],
                    colWidths=[indicator_width / 2],
                    rowHeights=[indicator_height],
                    style=[
                        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                        ("LEFTPADDING", (0, 0), (-1, -1), 0),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                        ("TOPPADDING", (0, 0), (-1, -1), 0),
                        ("GRID", (0, 0), (0, 0), 0.7, colors.black),
                        ("BACKGROUND", (0, 0), (0, 0), colors.black),
                    ],
                )

                rectangle_line1 = Table(
                    [[adp, weight]],
                    colWidths=[indicator_width / 2, indicator_width / 2],
                    rowHeights=[indicator_height],
                    style=[
                        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                        ("LEFTPADDING", (0, 0), (-1, -1), 0),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                        ("TOPPADDING", (0, 0), (-1, -1), 0),
                    ],
                )

                rectangle_line2 = Table(
                    [
                        [
                            Paragraph(
                                "<font name='VernadaBd'>L: %s<br />W: %s<br />H: %s</font>"
                                % (
                                    int(line_length * 100),
                                    int(line_width * 100),
                                    int(line_height * 100),
                                ),
                                ParagraphStyle(
                                    name="header_text",
                                    parent=styles["Normal"],
                                    fontSize=5,
                                    leading=6,
                                    spaceBefore=0,
                                    textColor=colors.black,
                                    alignment=TA_CENTER,
                                ),
                            )
                        ]
                    ],
                    colWidths=[indicator_width],
                    rowHeights=[indicator_height],
                    style=[
                        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                        ("LEFTPADDING", (0, 0), (-1, -1), 0),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
                        ("TOPPADDING", (0, 0), (-1, -1), 2),
                        ("GRID", (0, 0), (0, 0), 0.7, colors.black),
                    ],
                )

                receiver_data = [
                    [rectangle_line1],
                    [rectangle_line2],
                ]

                receiver_right = Table(
                    receiver_data,
                    colWidths=[receiver_right_width],
                    style=[
                        ("VALIGN", (0, 0), (-1, -1), "TOP"),
                        ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                        ("TOPPADDING", (0, 0), (-1, -1), 0),
                    ],
                )

                receiver = Table(
                    [
                        [receiver_left, receiver_right],
                    ],
                    colWidths=[
                        receiver_left_width,
                        receiver_right_width,
                    ],
                    style=[
                        ("VALIGN", (0, 0), (-1, -1), "TOP"),
                        ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                        ("TOPPADDING", (0, 0), (-1, -1), 0),
                        ("RIGHTPADDING", (0, 0), (0, 0), 0),
                    ],
                )

                left_part_data = [
                    [header],
                    [receiver],
                ]

                left_part = Table(
                    left_part_data,
                    colWidths=[header_width],
                    style=[
                        ("VALIGN", (0, 0), (-1, -1), "TOP"),
                        ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                        ("LEFTPADDING", (0, 0), (-1, -1), 0),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                        ("TOPPADDING", (0, 0), (-1, -1), 0),
                    ],
                )

                qr_code = Table(
                    [[qr_canvas]],
                    colWidths=[qr_code_width],
                    rowHeights=[qr_code_width - (7.5 * mm)],
                    style=[
                        ("VALIGN", (0, 0), (0, 0), "BOTTOM"),
                        ("ALIGN", (0, 0), (0, 0), "LEFT"),
                        ("TOPPADDING", (0, 0), (-1, -1), 0),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                        ("LEFTPADDING", (0, 0), (-1, -1), 0),
                        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                    ],
                )

                top_part_data = [
                    [left_part, qr_code],
                ]

                top_part = Table(
                    top_part_data,
                    colWidths=[header_width, qr_canvas_width],
                    style=[
                        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                        ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                        ("VALIGN", (1, 0), (1, 0), "MIDDLE"),
                        ("ALIGN", (1, 0), (1, 0), "CENTER"),
                        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                        ("LEFTPADDING", (0, 0), (-1, -1), 0),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                        ("TOPPADDING", (0, 0), (-1, -1), 0),
                    ],
                )

                right_part_data = [
                    [sender],
                    [ref],
                    [description_goods],
                ]

                right_part = Table(
                    right_part_data,
                    colWidths=[qr_canvas_width],
                    style=[
                        ("VALIGN", (0, 0), (-1, -1), "TOP"),
                        ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                        ("LEFTPADDING", (0, 0), (-1, -1), 0),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                        ("TOPPADDING", (0, 0), (-1, -1), 0),
                    ],
                )

                middle_part_data = [
                    [service_barcode, right_part],
                ]

                from_width = 45 * mm

                middle_part = Table(
                    middle_part_data,
                    colWidths=[float(width - from_width), from_width],
                    style=[
                        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                        ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                        ("LEFTPADDING", (0, 0), (-1, -1), 0),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                        ("TOPPADDING", (0, 0), (-1, -1), 0),
                    ],
                )

                bottom_part_data = [
                    # [declaration_by, dangerous_goods_declaration],
                    [
                        Paragraph(
                            "<font name='VernadaBd'>CARRIER'S TERMS AND CONDITIONS APPLY</font>",
                            ParagraphStyle(
                                name="header_text",
                                parent=styles["Normal"],
                                fontSize=5,
                                leading=6,
                                spaceBefore=0,
                                textColor=colors.black,
                            ),
                        ),
                        Paragraph(
                            "<font name='Vernada'>I hereby declare that this consignment does not contain dangerous goods</font>",
                            ParagraphStyle(
                                name="header_text",
                                parent=styles["Normal"],
                                fontSize=5,
                                leading=6,
                                spaceBefore=0,
                                textColor=colors.black,
                            ),
                        ),
                    ],
                ]

                bottom_part = Table(
                    bottom_part_data,
                    colWidths=[bottom_barcode_width * 0.4, bottom_barcode_width * 0.6],
                    style=[
                        ("VALIGN", (0, 0), (-1, -1), "TOP"),
                        ("ALIGN", (0, 0), (-1, -1), "RIGHT"),
                        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                        ("LEFTPADDING", (0, 0), (-1, -1), 0),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                        ("TOPPADDING", (0, 0), (-1, -1), 0),
                    ],
                )

                footer_part_width = width * (1 / 2)

                pkg_units_font_size = "font_size_footer"
                if len(booking_line.e_type_of_packaging) < 8:
                    pkg_units_font_size = "font_size_footer"
                elif len(booking_line.e_type_of_packaging) <= 10:
                    pkg_units_font_size = "font_size_footer_desc"
                else:
                    pkg_units_font_size = "font_size_footer_units_small"

                footer_units_part = Table(
                    [
                        [
                            Paragraph(
                                "<font size=%s><b>PKG UNITS:</b></font>"
                                % (label_settings["font_size_footer_desc"],),
                                style_reference_text,
                            ),
                            [
                                Paragraph(
                                    "<font size=%s><b>%s</b></font>"
                                    % (
                                        label_settings[pkg_units_font_size],
                                        booking_line.e_type_of_packaging,
                                    ),
                                    style_footer_text,
                                ),
                            ],
                        ],
                    ],
                    colWidths=[
                        footer_part_width * (1 / 5),
                        footer_part_width * (4 / 5),
                    ],
                    rowHeights=[5 * mm],
                    style=[
                        ("VALIGN", (0, 0), (-1, -1), "TOP"),
                        ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                        ("LEFTPADDING", (0, 0), (-1, -1), 0),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                        ("TOPPADDING", (0, 0), (-1, -1), 0),
                    ],
                )

                footer_bin_part = Table(
                    [
                        [
                            Paragraph(
                                "<font size=%s><b>BIN:</b></font>"
                                % (label_settings["font_size_footer_desc"],),
                                style_reference_text,
                            ),
                            Paragraph(
                                "<font size=%s><b>%s</b></font>"
                                % (
                                    label_settings["font_size_footer"],
                                    "No data"
                                    if booking_line.e_bin_number is None
                                    or len(booking_line.e_bin_number) == 0
                                    else booking_line.e_bin_number[:25],
                                ),
                                style_footer_text,
                            ),
                        ],
                    ],
                    colWidths=[
                        footer_part_width * (1 / 10),
                        footer_part_width * (9 / 10),
                    ],
                    rowHeights=[5 * mm],
                    style=[
                        ("VALIGN", (0, 0), (-1, -1), "TOP"),
                        ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                        ("LEFTPADDING", (0, 0), (-1, -1), 0),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                        ("TOPPADDING", (0, 0), (-1, -1), 0),
                    ],
                )

                str_desc = booking_line.e_item.replace("\n", " ").replace("\t", " ")[
                    :80
                ]
                font_size_desc = "font_size_footer"
                if len(str_desc) < 24:
                    font_size_desc = "font_size_footer"
                elif len(str_desc) < 55:
                    font_size_desc = "font_size_footer_units"
                else:
                    font_size_desc = "font_size_footer_desc_small"

                footer_desc_part = Table(
                    [
                        [
                            Paragraph(
                                "<font size=%s><b>DESC:</b></font>"
                                % (label_settings["font_size_footer_desc"],),
                                style_reference_text,
                            ),
                            Paragraph(
                                "<font size=%s><b>%s</b></font>"
                                % (
                                    label_settings[font_size_desc],
                                    str_desc[:50] if has_black_bar else str_desc,
                                ),
                                style_desc_text,
                            ),
                        ],
                    ],
                    colWidths=[
                        footer_part_width * (1 / 8),
                        footer_part_width * (15 / 8),
                    ],
                    rowHeights=[5 * mm],
                    style=[
                        ("VALIGN", (0, 0), (-1, -1), "TOP"),
                        ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                        ("LEFTPADDING", (0, 0), (-1, -1), 0),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                        ("TOPPADDING", (0, 0), (-1, -1), 0),
                    ],
                )

                if (
                    booking.b_client_name == "Tempo Pty Ltd"
                    and "xtensive" in booking.deToCompanyName.lower()
                    and line_data
                ):
                    footer_part = Table(
                        [
                            [
                                Paragraph(
                                    "<font size=%s><b>FAULT DESCRIPTION:</b></font>"
                                    % (label_settings["font_size_footer_desc"],),
                                    style_reference_text,
                                ),
                                [
                                    Paragraph(
                                        "<font size=%s><b>%s</b></font>"
                                        % (
                                            label_settings[pkg_units_font_size],
                                            line_data.itemFaultDescription or "",
                                        ),
                                        style_footer_text,
                                    ),
                                ],
                            ],
                        ],
                        colWidths=[
                            width * (1 / 4),
                            width * (3 / 4),
                        ],
                        rowHeights=[5 * mm],
                        style=[
                            ("VALIGN", (0, 0), (-1, -1), "TOP"),
                            ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                            ("LEFTPADDING", (0, 0), (-1, -1), 6),
                            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                            ("TOPPADDING", (0, 0), (-1, -1), 0),
                        ],
                    )
                    footer_part = Table(
                        [
                            [
                                footer_units_part,
                                footer_bin_part,
                            ],
                            [
                                footer_desc_part,
                                "",
                            ],
                        ],
                        colWidths=[
                            footer_part_width,
                            footer_part_width,
                        ],
                        rowHeights=[4 * mm, 4 * mm],
                        style=[
                            ("VALIGN", (0, 0), (-1, -1), "TOP"),
                            ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                            ("SPAN", (0, 1), (1, 1)),
                            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                            ("LEFTPADDING", (0, 0), (-1, -1), 0),
                            ("LEFTPADDING", (0, 0), (0, -1), 12),
                            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                            ("TOPPADDING", (0, 0), (-1, -1), 0),
                            ("TOPPADDING", (0, 0), (-1, 0), 2),
                        ],
                    )
                else:
                    footer_part = Table(
                        [
                            [
                                footer_units_part,
                                footer_bin_part,
                            ],
                            [
                                footer_desc_part,
                                "",
                            ],
                        ],
                        colWidths=[
                            footer_part_width,
                            footer_part_width,
                        ],
                        rowHeights=[4 * mm, 4 * mm],
                        style=[
                            ("VALIGN", (0, 0), (-1, -1), "TOP"),
                            ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                            ("SPAN", (0, 1), (1, 1)),
                            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                            ("LEFTPADDING", (0, 0), (-1, -1), 0),
                            ("LEFTPADDING", (0, 0), (0, -1), 12),
                            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                            ("TOPPADDING", (0, 0), (-1, -1), 0),
                            ("TOPPADDING", (0, 0), (-1, 0), 2),
                        ],
                    )

                frame_content_data = [
                    [top_part],
                    [middle_part],
                    [Spacer(1, 2)],
                    [sscc_barcode],
                    # [Spacer(1, 2)],
                    [bottom_part],
                    [footer_part],
                ]

            frame_content = Table(
                frame_content_data,
                colWidths=[width],
                style=[
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                    ("ALIGN", (0, 3), (0, 4), "CENTER"),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                    ("LEFTPADDING", (0, 0), (-1, -1), 0),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                    ("TOPPADDING", (0, 0), (-1, -1), 0),
                ],
            )

            # Tempo Big W
            if (
                booking.kf_client_id == "d69f550a-9327-4ff9-bc8f-242dfca00f7e"
                and carrier == "IPEC"
            ):
                frame = Table(
                    [[frame_content]],
                    colWidths=[frame_width],
                    style=[
                        ("VALIGN", (0, 0), (-1, -1), "TOP"),
                        ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                        ("LEFTPADDING", (0, 0), (-1, -1), 0),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                        ("TOPPADDING", (0, 0), (-1, -1), 0),
                    ],
                )
                Story.append(frame)
            else:
                Story.append(frame_content)

            Story.append(PageBreak())

            j += 1
            has_black_bar = False

    doc.build(Story, onFirstPage=myFirstPage, onLaterPages=myLaterPages)
    file.close()
    logger.info(
        f"#119 [TGE LABEL] Finished building label... (Booking ID: {booking.b_bookingID_Visual})"
    )
    return filepath, filename
