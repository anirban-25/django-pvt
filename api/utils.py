import sys, time
import os
import re
import errno
import datetime
import uuid
import redis
import urllib, requests
import json
import pymysql, pymysql.cursors
import redis
import xml.etree.ElementTree as xml
import pysftp
import shutil
import pytz
import logging
import re
from dateutil.rrule import *
from pytz import timezone
from datetime import timedelta
from os.path import basename

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
from api.models import *
from api.common import trace_error
from api.common.time import (
    next_business_day,
    convert_to_UTC_tz,
    TIME_DIFFERENCE,
    UTC_TZ,
    SYDNEY_TZ,
    get_eta_with_suburb,
)
from api.operations.generate_xls_report import build_xls
from api.outputs.email import send_email
from api.fp_apis.utils import gen_consignment_num
from api.helpers import string

if settings.ENV == "local":
    production = False  # Local
else:
    production = True  # Dev

if production:
    DB_HOST = "deliverme-db.cgc7xojhvzjl.ap-southeast-2.rds.amazonaws.com"
    DB_USER = "fmadmin"
    DB_PASS = "oU8pPQxh"
    DB_PORT = 3306

    if settings.ENV == "dev":
        DB_NAME = "dme_db_dev"  # Dev
    elif settings.ENV == "prod":
        DB_NAME = "dme_db_prod"  # Prod
else:
    DB_HOST = "localhost"
    DB_USER = "root"
    DB_PASS = "password"
    DB_PORT = 3306
    DB_NAME = "deliver_me"

logger = logging.getLogger(__name__)

redis_host = "localhost"
redis_port = 6379
redis_password = ""

### TAS constants ###
# ACCOUNT_CODE = "AATEST"
ACCOUNT_CODE = "SEAWAPO"
styles = getSampleStyleSheet()
style_right = ParagraphStyle(name="right", parent=styles["Normal"], alignment=TA_RIGHT)
style_left = ParagraphStyle(name="left", parent=styles["Normal"], alignment=TA_LEFT)
style_center = ParagraphStyle(
    name="center", parent=styles["Normal"], alignment=TA_CENTER
)
style_cell = ParagraphStyle(name="smallcell", fontSize=6, leading=6)
styles.add(ParagraphStyle(name="Justify", alignment=TA_JUSTIFY))
ROWS_PER_PAGE = 20
#####################


def redis_con():
    try:
        redisCon = redis.StrictRedis(
            host=redis_host, port=redis_port, password=redis_password
        )
    except:
        # print('Redis DB connection error!')
        exit(1)

    return redisCon


def save2Redis(key, value):
    redisCon = redis_con()
    redisCon.set(key, value)


def clearFileCheckHistory(filename):
    redisCon = redis_con()
    errorCnt = redisCon.get(filename)
    redisCon.delete(filename)

    if errorCnt is not None:
        for index in range(int(errorCnt)):
            redisCon.delete(filename + str(index))


def getFileCheckHistory(filename):
    redisCon = redis_con()
    errorCnt = redisCon.get(filename)
    errors = []

    if errorCnt is None:
        return 0
    else:
        if int(errorCnt) > 0:
            for index in range(int(errorCnt)):
                errors.append(redisCon.get(filename + str(index)).decode("utf-8"))
        elif int(errorCnt) == 0:
            return "success"

        return error


def calc_collect_after_status_change(pk_booking_id, status):
    booking_lines = Booking_lines.objects.filter(fk_booking_id=pk_booking_id)

    for booking_line in booking_lines:
        if status == "Collected" and booking_line.e_qty_awaiting_inventory:
            booking_line.e_qty_collected = (
                booking_line.e_qty - booking_line.e_qty_awaiting_inventory
            )
        elif status == "In Transit" or (
            status == "Collected" and not booking_line.e_qty_awaiting_inventory
        ):
            booking_line.e_qty_collected = booking_line.e_qty

        booking_line.save()


def upload_sftp(
    host,
    username,
    password,
    sftp_filepath,
    local_filepath,
    local_filepath_dup,
    filename,
):
    cnopts = pysftp.CnOpts()
    cnopts.hostkeys = None
    with pysftp.Connection(
        host="edi.alliedexpress.com.au",
        username="delvme.external",
        password="987899e64",
        cnopts=cnopts,
    ) as sftp_con:
        with sftp_con.cd(sftp_filepath):
            sftp_con.put(local_filepath + filename)
            sftp_file_size = sftp_con.lstat(sftp_filepath + filename).st_size
            local_file_size = os.stat(local_filepath + filename).st_size

            if sftp_file_size == local_file_size:
                if not os.path.exists(local_filepath_dup):
                    os.makedirs(local_filepath_dup)
                shutil.move(local_filepath + filename, local_filepath_dup + filename)

        sftp_con.close()


def get_sydney_now_time(return_type="char"):
    sydney_tz = pytz.timezone("Australia/Sydney")
    sydney_now = datetime.now().replace(microsecond=0).astimezone(sydney_tz)

    if return_type == "char":
        return sydney_now.strftime("%Y-%m-%d %H:%M:%S")
    elif return_type == "datetime":
        return sydney_now
    elif return_type == "date-char":
        return sydney_now.strftime("%Y-%m-%d")


def get_utc_now_time(return_type="char"):
    utc_tz = pytz.timezone("UTC")
    utc_now = datetime.now().replace(microsecond=0).astimezone(utc_tz)

    if return_type == "char":
        return utc_now.strftime("%Y-%m-%d %H:%M:%S")
    elif return_type == "datetime":
        return utc_now
    elif return_type == "date-char":
        return utc_now.strftime("%Y-%m-%d")


def get_available_bookings(mysqlcon, booking_ids):
    where_clause = " WHERE "
    for id in booking_ids:
        where_clause = where_clause + "id = " + str(id) + " OR "
    where_clause = where_clause[:-4]

    with mysqlcon.cursor() as cursor:
        sql = "SELECT * FROM `dme_bookings` " + where_clause + " ORDER BY `id` ASC"
        cursor.execute(sql)
        result = cursor.fetchall()
        return result


def get_available_booking_lines(mysqlcon, booking):
    with mysqlcon.cursor() as cursor:
        sql = "SELECT * FROM `dme_booking_lines` WHERE `fk_booking_id`=%s"
        cursor.execute(sql, (booking["pk_booking_id"]))
        result = cursor.fetchall()
        # print('Avaliable Booking Lines cnt: ', len(result))
        return result


def make_3digit(num):
    if num > 0 and num < 10:
        return "00" + str(num)
    elif num > 9 and num < 100:
        return "0" + str(num)
    elif num > 99 and num < 1000:
        return str(num)
    else:
        return str("ERROR: Number is bigger than 999")


def get_booked_list(bookings):
    booked_list = []

    for booking in bookings:
        if booking["b_dateBookedDate"] and booking["b_dateBookedDate"] != "":
            booked_list.append(booking["b_bookingID_Visual"])

    return booked_list


def get_item_type(i):
    if i:
        if "UHP" in i:
            return "PCR"
        elif "PCR" in i:
            return "PCR"
        elif "LTR" in i:
            return "LTR"
        elif "TBR" in i:
            return "TBR"
        else:
            return "ERROR"
    else:
        return "ERROR"


def myFirstPage(canvas, doc):
    canvas.saveState()
    canvas.rotate(180)
    canvas.restoreState()


def myLaterPages(canvas, doc):
    canvas.saveState()
    canvas.rotate(90)
    canvas.restoreState()


def get_barcode_rotated(
    value, width, barWidth=0.01 * inch, fontSize=18, humanReadable=True
):
    barcode = createBarcodeDrawing(
        "Code128",
        value=value,
        barHeight=30 * mm,
        barWidth=1.3,
        fontSize=fontSize,
        humanReadable=humanReadable,
    )

    drawing_width = 2.5 * inch
    barcode_scale = drawing_width / barcode.width
    drawing_height = barcode.height * barcode_scale

    drawing = Drawing(drawing_width, drawing_height)
    drawing.scale(barcode_scale, barcode_scale)
    drawing.add(barcode, name="barcode")

    drawing_rotated = Drawing(drawing_height, drawing_width)
    drawing_rotated.rotate(90)
    drawing_rotated.translate(10, -drawing_height)
    drawing_rotated.add(drawing, name="drawing")

    return drawing_rotated


class verticalText(Flowable):
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


class RotatedImage(Image):
    def wrap(self, availWidth, availHeight):
        h, w = Image.wrap(self, availHeight, availWidth)
        return w, h

    def draw(self):
        self.canv.rotate(90)
        Image.draw(self)


def build_pdf(booking_ids, vx_freight_provider):
    try:
        mysqlcon = pymysql.connect(
            host=DB_HOST,
            port=DB_PORT,
            user=DB_USER,
            password=DB_PASS,
            db=DB_NAME,
            charset="utf8mb4",
            cursorclass=pymysql.cursors.DictCursor,
        )
    except:
        exit(1)
    mycursor = mysqlcon.cursor()

    if vx_freight_provider == "TASFR":
        try:
            bookings = get_available_bookings(mysqlcon, booking_ids)

            # start check if pdfs folder exists
            if production:
                local_filepath = "/opt/s3_public/pdfs/tas_au/"
                local_filepath_dup = (
                    "/opt/s3_public/pdfs/tas_au/archive/"
                    + str(datetime.now().strftime("%Y_%m_%d"))
                    + "/"
                )
            else:
                local_filepath = "./static/pdfs/tas_au/"
                local_filepath_dup = (
                    "./static/pdfs/tas_au/archive/"
                    + str(datetime.now().strftime("%Y_%m_%d"))
                    + "/"
                )

            if not os.path.exists(local_filepath):
                os.makedirs(local_filepath)
            # end check if pdfs folder exists

            # start loop through data fetched from dme_bookings table
            i = 1
            for booking in bookings:
                booking_lines = get_available_booking_lines(mysqlcon, booking)

                totalQty = 0
                for booking_line in booking_lines:
                    totalQty = totalQty + booking_line["e_qty"]

                # start pdf file name using naming convention
                filename = (
                    booking["pu_Address_State"]
                    + "_"
                    + str(booking["b_client_sales_inv_num"])
                    + "_"
                    + str(booking["v_FPBookingNumber"])
                    + "_"
                    + "DME"
                    + str(booking["b_bookingID_Visual"])
                    + ".pdf"
                )
                file = open(local_filepath + filename, "w")
                # end pdf file name using naming convention

                date = datetime.now().strftime("%d/%m/%Y %I:%M:%S %p")
                doc = SimpleDocTemplate(
                    local_filepath + filename,
                    pagesize=(6 * inch, 4 * inch),
                    rightMargin=10,
                    leftMargin=10,
                    topMargin=10,
                    bottomMargin=10,
                )
                Story = []

                j = 1
                for booking_line in booking_lines:
                    for k in range(booking_line["e_qty"]):
                        tbl_data = [
                            [
                                Paragraph(
                                    "<font size=10><b>%s FREIGHT<br /></b></font>"
                                    % booking["vx_freight_provider"].upper(),
                                    style_left,
                                )
                            ],
                            [
                                Paragraph("<font size=8>C/N:</font>", style_left),
                                Paragraph(
                                    "<font size=10><b>%s</b></font>"
                                    % booking["v_FPBookingNumber"],
                                    styles["BodyText"],
                                ),
                            ],
                            [
                                Paragraph("<font size=8>Date:</font>", style_left),
                                Paragraph(
                                    "<font size=8><b>%s</b></font>"
                                    % booking["b_dateBookedDate"].strftime(
                                        "%d/%m/%Y %I:%M:%S %p"
                                    ),
                                    styles["BodyText"],
                                ),
                            ],
                            [
                                Paragraph("<font size=8>Reference:</font>", style_left),
                                Paragraph(
                                    "<font size=8><b>%s</b></font>"
                                    % booking_line["client_item_reference"],
                                    styles["BodyText"],
                                ),
                            ],
                            [
                                Paragraph("<font size=8>Service:</font>", style_left),
                                Paragraph(
                                    "<font size=8><b>%s</b></font>"
                                    % booking["vx_serviceName"],
                                    styles["BodyText"],
                                ),
                            ],
                        ]
                        t1 = Table(
                            tbl_data,
                            colWidths=(45, 220),
                            rowHeights=(12),
                            hAlign="LEFT",
                            style=[
                                ("SPAN", (0, 0), (1, 0)),
                                ("TOPPADDING", (0, 0), (-1, -1), 0),
                                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                            ],
                        )

                        tbl_data = [
                            [
                                Paragraph(
                                    "<font size=34><b>%s</b></font>"
                                    % booking["de_To_Address_State"],
                                    styles["Normal"],
                                )
                            ],
                            [
                                Paragraph(
                                    "<font size=8><br /><br />%s, %s\n%s, %s, %s</font>"
                                    % (
                                        ACCOUNT_CODE,
                                        booking["pu_Address_Street_1"],
                                        booking["pu_Address_Suburb"],
                                        booking["pu_Address_PostalCode"],
                                        booking["pu_Address_State"],
                                    ),
                                    styles["Normal"],
                                )
                            ],
                        ]
                        t2 = Table(tbl_data, colWidths=(150), style=[])

                        tbl_data = [
                            [
                                Paragraph(
                                    "<font size=34><b>%s</b></font>"
                                    % booking["de_To_Address_PostalCode"],
                                    style_right,
                                )
                            ],
                            [""],
                            [""],
                            [""],
                        ]
                        t3 = Table(tbl_data, colWidths=(150), style=[])

                        data = [[t1, t2, t3]]
                        # adjust the length of tables
                        t1_w = 2.35 * inch
                        t2_w = 1.2 * inch
                        t3_w = 2 * inch
                        shell_table = Table(
                            data,
                            colWidths=[t1_w, t2_w, t3_w],
                            style=[
                                ("TOPPADDING", (0, 0), (-1, -1), 0),
                                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                            ],
                        )
                        Story.append(shell_table)
                        Story.append(Spacer(1, 10))
                        Story.append(
                            HRFlowable(
                                width="100%",
                                thickness=1,
                                lineCap="round",
                                color="#000000",
                                spaceBefore=0,
                                spaceAfter=0,
                                hAlign="CENTER",
                                vAlign="MIDDLE",
                                dash=None,
                            )
                        )

                        # Story.append(Spacer(1, 3))

                        tbl_data = [
                            [
                                Paragraph(
                                    "<font size=10><b>%s</b></font>"
                                    % booking["de_to_Contact_F_LName"],
                                    style_left,
                                )
                            ],
                            [
                                Paragraph(
                                    "<font size=10><b>%s</b></font>"
                                    % booking["de_To_Address_Street_1"],
                                    style_left,
                                )
                            ],
                            [
                                Paragraph(
                                    "<font size=10><b>%s, %s, %s</b></font> "
                                    % (
                                        booking["de_To_Address_Suburb"],
                                        booking["de_To_Address_PostalCode"],
                                        booking["de_To_Address_State"],
                                    ),
                                    style_left,
                                )
                            ],
                        ]
                        t1 = Table(
                            tbl_data,
                            colWidths=(180),
                            style=[
                                ("TOPPADDING", (0, 0), (-1, -1), 0),
                                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                            ],
                        )

                        tbl_data = [
                            [
                                Paragraph(
                                    "<font size=8>%s %s</font>"
                                    % (
                                        str(
                                            booking["de_to_PickUp_Instructions_Address"]
                                        ),
                                        str(
                                            booking[
                                                "de_to_Pick_Up_Instructions_Contact"
                                            ]
                                        ),
                                    ),
                                    styles["Normal"],
                                )
                            ],
                            [""],
                        ]
                        t2 = Table(tbl_data, colWidths=(160), style=[])

                        data = [[t1, t2]]
                        # adjust the length of tables
                        t1_w = 2.35 * inch
                        t2_w = 3.2 * inch
                        # t3_w = 2 * inch
                        shell_table = Table(
                            data,
                            colWidths=[t1_w, t2_w],
                            style=[
                                ("TOPPADDING", (0, 0), (-1, -1), 0),
                                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                            ],
                        )
                        Story.append(shell_table)

                        Story.append(Spacer(1, 35))

                        barcode = "S" + booking["v_FPBookingNumber"] + str(j).zfill(3)
                        barcode128 = code128.Code128(
                            barcode, barHeight=30 * mm, barWidth=1.2
                        )

                        tbl_data = [
                            [
                                Paragraph(
                                    "<font size=8>Item: </font>", styles["Normal"]
                                ),
                                Paragraph(
                                    "<font size=12><b>%s of %s</b></font>"
                                    % (j, totalQty),
                                    style_left,
                                ),
                            ]
                        ]
                        tbl = Table(
                            tbl_data,
                            colWidths=(80, 140),
                            rowHeights=(20),
                            hAlign="LEFT",
                            style=[
                                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                            ],
                        )
                        Story.append(tbl)

                        tbl_data = [
                            [
                                Paragraph(
                                    "<font size=8><b>Desc</b>: %s</font>"
                                    % (
                                        str(booking_line["e_item"])
                                        if booking_line["e_item"]
                                        else ""
                                    ),
                                    style_left,
                                ),
                                barcode128,
                            ]
                        ]
                        tbl = Table(
                            tbl_data,
                            colWidths=(170, 170),
                            rowHeights=(12),
                            hAlign="LEFT",
                            style=[
                                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                                ("TOPPADDING", (0, 0), (-1, -1), 0),
                                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                            ],
                        )
                        Story.append(tbl)
                        Story.append(
                            HRFlowable(
                                width="45%",
                                thickness=1,
                                lineCap="round",
                                color="#000000",
                                spaceBefore=1,
                                spaceAfter=2,
                                hAlign="LEFT",
                                vAlign="BOTTOM",
                                dash=None,
                            )
                        )

                        tbl_data = [
                            [
                                Paragraph("<font size=8>L</font>", style_center),
                                Paragraph("<font size=8>W</font>", style_center),
                                Paragraph("<font size=8>H</font>", style_center),
                            ],
                            [
                                Paragraph(
                                    "<font size=10><b>%s</b></font>"
                                    % (str(booking_line["e_dimLength"])),
                                    style_center,
                                ),
                                Paragraph(
                                    "<font size=10><b>%s</b></font>"
                                    % str(booking_line["e_dimWidth"]),
                                    style_center,
                                ),
                                Paragraph(
                                    "<font size=10><b>%s</b></font>"
                                    % str(booking_line["e_dimHeight"]),
                                    style_center,
                                ),
                            ],
                        ]
                        tbl = Table(
                            tbl_data,
                            colWidths=(60, 60, 60),
                            rowHeights=10,
                            hAlign="LEFT",
                        )
                        tbl.setStyle(
                            [
                                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                                ("ALIGN", (0, 0), (0, 0), "CENTER"),
                                ("TOPPADDING", (0, 0), (-1, -1), 0),
                                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                            ]
                        )
                        Story.append(tbl)
                        Story.append(
                            HRFlowable(
                                width="45%",
                                thickness=1,
                                lineCap="round",
                                color="#000000",
                                spaceBefore=2,
                                spaceAfter=2,
                                hAlign="LEFT",
                                vAlign="BOTTOM",
                                dash=None,
                            )
                        )

                        tbl_data = [
                            [
                                Paragraph("<font size=8>KG</font>", style_center),
                                Paragraph("<font size=8>VOL</font>", style_center),
                            ],
                            [
                                Paragraph(
                                    "<font size=10><b>%s</b></font>"
                                    % str(
                                        "{0:.2f}".format(
                                            booking_line["e_Total_KG_weight"]
                                            if booking_line["e_Total_KG_weight"]
                                            is not None
                                            else 0
                                        )
                                    ),
                                    style_center,
                                ),
                                Paragraph(
                                    "<font size=10><b>%s</b></font>"
                                    % str(
                                        "{0:.2f}".format(
                                            booking_line["e_1_Total_dimCubicMeter"]
                                            if booking_line["e_1_Total_dimCubicMeter"]
                                            is not None
                                            else 0
                                        )
                                    ),
                                    style_center,
                                ),
                                Paragraph(
                                    "<font size=8>%s</font>" % barcode, style_center
                                ),
                            ],
                        ]
                        tbl = Table(
                            tbl_data,
                            colWidths=(90, 90, 220),
                            rowHeights=10,
                            hAlign="LEFT",
                        )
                        tbl.setStyle(
                            [
                                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                                ("ALIGN", (0, 0), (0, 0), "CENTER"),
                                ("TOPPADDING", (0, 0), (-1, -1), 0),
                                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                            ]
                        )
                        Story.append(tbl)

                        tbl_data = [
                            [
                                Paragraph(
                                    "<font size=8>Client Item Reference: </font>",
                                    styles["Normal"],
                                ),
                                Paragraph(
                                    "<font size=8><b>%s</b></font>"
                                    % booking_line["client_item_reference"],
                                    style_left,
                                ),
                            ]
                        ]
                        tbl = Table(
                            tbl_data,
                            colWidths=(80, 140),
                            rowHeights=(20),
                            hAlign="LEFT",
                            style=[
                                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                            ],
                        )
                        Story.append(tbl)
                        Story.append(PageBreak())

                        j = j + 1

                i = i + 1
                doc.build(Story)
                # end writting data into pdf file

                sql2 = "UPDATE dme_bookings \
                    SET z_label_url = %s \
                    WHERE pk_booking_id = %s"
                adr2 = ("tas_au/" + filename, booking["pk_booking_id"])
                mycursor.execute(sql2, adr2)
                mysqlcon.commit()
                file.close()
        except Exception as e:
            exc_type, exc_obj, exc_tb = sys.exc_info()
            fname = os.path.split(exc_tb.tb_frame.f_code.co_filename)[1]
            logger.info(f"#505 Error: - {e}")
    elif vx_freight_provider.upper() == "DHL":
        try:
            bookings = get_available_bookings(mysqlcon, booking_ids)

            # start check if pdfs folder exists
            if production:
                local_filepath = "/opt/s3_public/pdfs/dhl_au/"
                local_filepath_dup = (
                    "/opt/s3_public/pdfs/dhl_au/archive/"
                    + str(datetime.now().strftime("%Y_%m_%d"))
                    + "/"
                )
            else:
                local_filepath = "./static/pdfs/dhl_au/"
                local_filepath_dup = (
                    "./static/pdfs/dhl_au/archive/"
                    + str(datetime.now().strftime("%Y_%m_%d"))
                    + "/"
                )

            if not os.path.exists(local_filepath):
                os.makedirs(local_filepath)
            # end check if pdfs folder exists

            # start loop through data fetched from dme_bookings table
            i = 1
            for booking in bookings:
                booking_lines = get_available_booking_lines(mysqlcon, booking)

                totalQty = 0
                for booking_line in booking_lines:
                    totalQty = totalQty + booking_line["e_qty"]

                # start pdf file name using naming convention
                filename = (
                    booking["pu_Address_State"]
                    + "_"
                    + str(booking["b_client_sales_inv_num"])
                    + "_"
                    + str(booking["v_FPBookingNumber"])
                    + "_"
                    + "DME"
                    + str(booking["b_bookingID_Visual"])
                    + ".pdf"
                )
                file = open(local_filepath + filename, "w")
                # end pdf file name using naming convention

                date = datetime.now().strftime("%d/%m/%Y %I:%M:%S %p")
                doc = SimpleDocTemplate(
                    local_filepath + filename,
                    pagesize=(6 * inch, 4 * inch),
                    rightMargin=10,
                    leftMargin=10,
                    topMargin=10,
                    bottomMargin=10,
                )
                Story = []

                fp_info = Fp_freight_providers.objects.get(fp_company_name="DHL")
                fp_zone = FP_zones.objects.filter(
                    fk_fp=fp_info.id,
                    state=booking["de_To_Address_State"],
                    suburb=booking["de_To_Address_Suburb"],
                    postal_code=booking["de_To_Address_PostalCode"],
                ).first()

                j = 1
                for booking_line in booking_lines:
                    for k in range(booking_line["e_qty"]):
                        tbl_data = [
                            [
                                Paragraph("<font size=6>From:</font>", style_left),
                                Paragraph(
                                    "<font size=6>%s</font>" % booking["puCompany"],
                                    styles["BodyText"],
                                ),
                            ],
                            [
                                Paragraph("<font size=6>Telephone:</font>", style_left),
                                Paragraph(
                                    "<font size=6>%s</font>" % booking["pu_Phone_Main"],
                                    styles["BodyText"],
                                ),
                            ],
                            [
                                Paragraph("<font size=6>Service:</font>", style_left),
                                Paragraph(
                                    "<font size=6>%s</font>" % fp_zone.service,
                                    styles["BodyText"],
                                ),
                            ],
                            [
                                Paragraph("<font size=6>Via:</font>", style_left),
                                Paragraph(
                                    "<font size=6>%s</font>"
                                    % booking["vx_freight_provider_carrier"],
                                    styles["BodyText"],
                                ),
                            ],
                            [
                                Paragraph("<font size=6>C/note:</font>", style_left),
                                Paragraph(
                                    "<font size=6>%s</font>"
                                    % booking["v_FPBookingNumber"],
                                    styles["BodyText"],
                                ),
                            ],
                            [
                                Paragraph(
                                    "<font size=6>Deliver To:</font>", style_left
                                ),
                                Paragraph(
                                    "<font size=6>%s</font>"
                                    % booking["de_to_Contact_F_LName"],
                                    styles["BodyText"],
                                ),
                            ],
                        ]
                        t1 = Table(
                            tbl_data,
                            colWidths=(40, 120),
                            rowHeights=(12),
                            hAlign="LEFT",
                            style=[
                                ("TOPPADDING", (0, 0), (-1, -1), 0),
                                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                            ],
                        )

                        tbl_data = [
                            [
                                Paragraph(
                                    "<font size=6>Item:&nbsp;&nbsp; %s - Of - %s</font>"
                                    % (j, totalQty),
                                    style_right,
                                ),
                                Paragraph(
                                    "<font size=6>Date:&nbsp;&nbsp; %s</font>"
                                    % booking["b_dateBookedDate"].strftime("%d/%m/%Y"),
                                    style_left,
                                ),
                            ],
                            [
                                Paragraph(
                                    "<font size=6>Reference No:</font>", style_right
                                ),
                                Paragraph(
                                    "<font size=6>%s</font>"
                                    % booking_line["client_item_reference"],
                                    style_left,
                                ),
                            ],
                            [""],
                            [""],
                            [""],
                            [""],
                        ]
                        t2 = Table(
                            tbl_data,
                            colWidths=(55, 120),
                            rowHeights=(12),
                            hAlign="LEFT",
                            style=[],
                        )

                        barcode = (
                            booking["v_FPBookingNumber"]
                            + booking["v_FPBookingNumber"][0:3]
                            + "L"
                            + "00"
                            + str(
                                int(booking["v_FPBookingNumber"][3:])
                                - 100000
                                + 10000000
                            )
                            + booking["de_To_Address_PostalCode"]
                        )
                        barcode128 = code128.Code128(
                            barcode, barHeight=30 * mm, barWidth=1.3
                        )

                        tbl_data = [
                            [Paragraph("<font size=6> </font>", style_left)],
                            [get_barcode_rotated(barcode, 3 * inch)],
                        ]
                        t3 = Table(
                            tbl_data,
                            colWidths=(120),
                            rowHeights=(12, 65),
                            hAlign="LEFT",
                            style=[("VALIGN", (0, 0), (0, -1), "TOP")],
                        )

                        data = [[t1, t2, t3]]
                        # adjust the length of tables
                        t1_w = 1.6 * inch
                        t2_w = 1.9 * inch
                        t3_w = 1.1 * inch
                        shell_table = Table(
                            data,
                            colWidths=[t1_w, t2_w, t3_w],
                            style=[
                                ("TOPPADDING", (0, 0), (-1, -1), 0),
                                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                            ],
                        )
                        Story.append(shell_table)

                        tbl_data = [
                            [
                                Paragraph(
                                    "<font size=7>%s</font>"
                                    % booking["de_to_Contact_F_LName"],
                                    style_left,
                                )
                            ],
                            [
                                Paragraph(
                                    "<font size=7>%s</font>"
                                    % booking["de_to_Phone_Main"],
                                    style_left,
                                )
                            ],
                            [
                                Paragraph(
                                    "<font size=7>%s</font>"
                                    % booking["de_To_Address_Street_1"],
                                    style_left,
                                )
                            ],
                            [
                                Paragraph(
                                    "<font size=7><b>%s</b></font> "
                                    % (booking["de_To_Address_Suburb"]),
                                    style_left,
                                )
                            ],
                            [
                                Paragraph(
                                    "<font size=7>%s %s</font> "
                                    % (
                                        booking["de_To_Address_State"],
                                        booking["de_To_Address_PostalCode"],
                                    ),
                                    style_left,
                                )
                            ],
                            [
                                Paragraph(
                                    "<font size=6>C/note: %s</font> "
                                    % (booking["v_FPBookingNumber"]),
                                    style_left,
                                )
                            ],
                            [
                                Paragraph(
                                    "<font size=6>Total Items %s</font> "
                                    % str(totalQty).zfill(4),
                                    style_left,
                                )
                            ],
                        ]
                        t1 = Table(
                            tbl_data,
                            colWidths=(165),
                            rowHeights=([13, 10, 10, 10, 10, 10, 10]),
                            hAlign="LEFT",
                            style=[
                                ("LEFTPADDING", (0, 0), (-1, -1), 5),
                                ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                                ("TOPPADDING", (0, 0), (-1, -1), 5),
                                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                                ("BOX", (0, 0), (-1, -1), 0.5, colors.black),
                            ],
                        )

                        tbl_data = [
                            [
                                Paragraph(
                                    '<font size=10 color="white">S01</font>', style_left
                                )
                            ]
                        ]
                        t2 = Table(
                            tbl_data,
                            colWidths=(30),
                            rowHeights=(30),
                            hAlign="CENTER",
                            vAlign="MIDDLE",
                            style=[
                                ("BACKGROUND", (0, 0), (-1, 0), colors.black),
                                ("TEXTCOLOR", (0, 0), (0, -1), colors.white),
                                ("VALIGN", (0, 0), (0, -1), "MIDDLE"),
                            ],
                        )

                        tbl_data = [[""]]
                        t3 = Table(
                            tbl_data,
                            colWidths=(250),
                            style=[("VALIGN", (0, 0), (0, -1), "TOP")],
                        )

                        data = [[t1, t2, t3]]
                        # adjust the length of tables
                        t1_w = 2.5 * inch
                        t2_w = 1 * inch
                        t3_w = 1.1 * inch
                        shell_table = Table(
                            data,
                            colWidths=[t1_w, t2_w, t3_w],
                            style=[
                                ("TOPPADDING", (0, 0), (-1, -1), 0),
                                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                            ],
                        )
                        Story.append(shell_table)

                        Story.append(Spacer(1, 5))

                        tbl_data = [
                            [
                                Paragraph(
                                    "<font size=6>Special Inst:</font>", style_left
                                ),
                                Paragraph(
                                    "<font size=6>%s %s</font>"
                                    % (
                                        str(
                                            booking["de_to_PickUp_Instructions_Address"]
                                        )
                                        if booking["de_to_PickUp_Instructions_Address"]
                                        else "",
                                        str(
                                            booking[
                                                "de_to_Pick_Up_Instructions_Contact"
                                            ]
                                        )
                                        if booking["de_to_Pick_Up_Instructions_Contact"]
                                        else "",
                                    ),
                                    style_left,
                                ),
                            ],
                            [""],
                        ]
                        tbl = Table(
                            tbl_data,
                            colWidths=(45, 350),
                            rowHeights=(14),
                            hAlign="LEFT",
                            style=[
                                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                            ],
                        )
                        Story.append(tbl)
                        Story.append(PageBreak())

                        j += 1
                i += 1
                doc.build(Story, onFirstPage=myFirstPage, onLaterPages=myLaterPages)

                sql2 = "UPDATE dme_bookings \
                    SET z_label_url = %s \
                    WHERE pk_booking_id = %s"
                adr2 = ("dhl_au/" + filename, booking["pk_booking_id"])
                mycursor.execute(sql2, adr2)
                mysqlcon.commit()

                file.close()
        except Exception as e:
            exc_type, exc_obj, exc_tb = sys.exc_info()
            fname = os.path.split(exc_tb.tb_frame.f_code.co_filename)[1]
            logger.info(f"#506 Error: - {e}")
    mysqlcon.close()
    return i - 1


def build_xls_and_send(
    bookings,
    email_addr,
    report_type,
    username,
    start_date,
    end_date,
    show_field_name,
    clientname,
):
    if report_type == "booking":
        filepath = build_xls(
            bookings, "Bookings", username, start_date, end_date, show_field_name
        )
        send_email(
            [email_addr],  # Recipient email address(list)
            [],  # CC
            [],  # BCC
            "Bookings XLS Report from Deliver-Me",  # Subject of email
            "Here is the excel report(Bookings) you generated from Deliver-Me.",  # Message of email
            [filepath],  # Attachment file path(list)
        )
    elif report_type == "booking_line":
        filepath = build_xls(
            bookings, "BookingLines", username, start_date, end_date, show_field_name
        )
        send_email(
            [email_addr],  # Recipient email address(list)
            [],
            [],  # BCC
            "BookingLines XLS Report from Deliver-Me",  # Subject of email
            "Here is the excel report(Booking Lines) you generated from Deliver-Me.",  # Message of email
            [filepath],  # Attachment file path(list)
        )
    elif report_type == "booking_with_gaps":
        filepath = build_xls(
            bookings,
            "BookingsWithGaps",
            username,
            start_date,
            end_date,
            show_field_name,
        )
        send_email(
            [email_addr],
            [],
            [],  # BCC
            "Bookings with Gaps XLS Report from Deliver-Me",  # Subject of email
            "Here is the excel report(Booking With Gaps) you generated from Deliver-Me.",  # Message of email
            [filepath],  # Attachment file path(list)
        )
    elif report_type == "dme_booking_with_gaps":
        filepath = build_xls(
            bookings,
            "DMEBookingsWithGaps",
            username,
            start_date,
            end_date,
            show_field_name,
        )
        send_email(
            [email_addr],
            [],
            [],  # BCC
            "Bookings with Gaps XLS Report from Deliver-Me(DME only can generate this report)",  # Subject of email
            "Here is the excel report(DME Booking With Gaps) you generated from Deliver-Me.",  # Message of email
            [filepath],  # Attachment file path(list)
        )
    elif report_type == "whse":
        filepath = build_xls(
            bookings, "Whse", username, start_date, end_date, show_field_name
        )
        send_email(
            [email_addr],
            [],
            [],  # BCC
            "Whse XLS Report from Deliver-Me",  # Subject of email
            "Here is the excel report(Whse) you generated from Deliver-Me.",  # Message of email
            [filepath],  # Attachment file path(list)
        )
    elif report_type == "pending_bookings":
        filepath = build_xls(
            bookings,
            "pending_bookings",
            username,
            start_date,
            end_date,
            show_field_name,
        )
        send_email(
            [email_addr],
            [],
            [],  # BCC
            "Pending Bookings XLS Report from Deliver-Me",  # Subject of email
            "Here is the excel report you generated from Deliver-Me.",  # Message of email
            [filepath],  # Attachment file path(list)
        )
    elif report_type == "booked_bookings":
        filepath = build_xls(
            bookings, "booked_bookings", username, start_date, end_date, show_field_name
        )
        send_email(
            [email_addr],
            [],
            [],  # BCC
            "Booked Bookings XLS Report from Deliver-Me",  # Subject of email
            "Here is the excel report you generated from Deliver-Me.",  # Message of email
            [filepath],  # Attachment file path(list)
        )
    elif report_type == "real_time_bookings":
        filepath = build_xls(
            bookings,
            "real_time_bookings",
            username,
            start_date,
            end_date,
            show_field_name,
        )
        send_email(
            [email_addr],
            [],
            [],  # BCC
            "Real Time Bookings XLS Report from Deliver-Me",  # Subject of email
            "Here is the excel report you generated from Deliver-Me.",  # Message of email
            [filepath],  # Attachment file path(list)
        )
    elif report_type == "picked_up_bookings":
        filepath = build_xls(
            bookings,
            "picked_up_bookings",
            username,
            start_date,
            end_date,
            show_field_name,
        )
        send_email(
            [email_addr],
            [],
            [],  # BCC
            "PickedUp Bookings XLS Report from Deliver-Me",  # Subject of email
            "Here is the excel report you generated from Deliver-Me.",  # Message of email
            [filepath],  # Attachment file path(list)
        )
    elif report_type == "box":
        filepath = build_xls(
            bookings, "box", username, start_date, end_date, show_field_name
        )
        send_email(
            [email_addr],
            [],
            [],  # BCC
            "Box XLS Report from Deliver-Me",  # Subject of email
            "Here is the excel report you generated from Deliver-Me.",  # Message of email
            [filepath],  # Attachment file path(list)
        )
    elif report_type == "futile":
        filepath = build_xls(
            bookings, "futile", username, start_date, end_date, show_field_name
        )
        send_email(
            [email_addr],
            [],
            [],  # BCC
            "Futile XLS Report from Deliver-Me",  # Subject of email
            "Here is the excel report you generated from Deliver-Me.",  # Message of email
            [filepath],  # Attachment file path(list)
        )
    elif report_type == "bookings_delivered":
        filepath = build_xls(
            bookings,
            "bookings_delivered",
            username,
            start_date,
            end_date,
            show_field_name,
        )
        send_email(
            [email_addr],
            [],
            [],  # BCC
            "Bookings Delivered XLS Report from Deliver-Me",  # Subject of email
            "Here is the excel report you generated from Deliver-Me.",  # Message of email
            [filepath],  # Attachment file path(list)
        )
    elif report_type == "bookings_sent":
        filepath = build_xls(
            bookings, "bookings_sent", username, start_date, end_date, show_field_name
        )
        send_email(
            [email_addr],
            [],
            [],  # BCC
            "Bookings Sent XLS Report from Deliver-Me",  # Subject of email
            "Here is the excel report you generated from Deliver-Me.",  # Message of email
            [filepath],  # Attachment file path(list)
        )
    elif report_type == "booking_lines_sent":
        filepath = build_xls(
            bookings,
            "booking_lines_sent",
            username,
            start_date,
            end_date,
            show_field_name,
        )
        send_email(
            [email_addr],
            [],
            [],  # BCC
            "Booking Lines Sent XLS Report from Deliver-Me",  # Subject of email
            "Here is the excel report you generated from Deliver-Me.",  # Message of email
            [filepath],  # Attachment file path(list)
        )
    elif report_type == "delivery":
        filepath = build_xls(
            bookings,
            "delivery",
            username,
            start_date,
            end_date,
            show_field_name,
        )
        send_email(
            [email_addr],
            [],
            [],  # BCC
            "Delivery XLS Report from Deliver-Me",  # Subject of email
            "Here is the excel report you generated from Deliver-Me.",  # Message of email
            [filepath],  # Attachment file path(list)
        )
    elif report_type == "cost_report_dme_only":
        filepath = build_xls(
            bookings,
            "cost_report_dme_only",
            username,
            start_date,
            end_date,
            show_field_name,
        )
        send_email(
            [email_addr],
            [],
            [],  # BCC
            "'Bookings Report with  Costs - DME Only' XLS Report from Deliver-Me",  # Subject of email
            "Here is the excel report you generated from Deliver-Me.",  # Message of email
            [filepath],  # Attachment file path(list)
        )
    elif report_type == "all":
        filepath_booking = build_xls(
            bookings, "Bookings", username, start_date, end_date, show_field_name
        )
        filepath_booking_line = build_xls(
            bookings, "BookingLines", username, start_date, end_date, show_field_name
        )
        filepath_booking_with_gaps = build_xls(
            bookings,
            "BookingsWithGaps",
            username,
            start_date,
            end_date,
            show_field_name,
        )
        filepath_whse = build_xls(
            bookings, "Whse", username, start_date, end_date, show_field_name
        )
        attachments = [
            filepath_booking,
            filepath_booking_line,
            filepath_booking_with_gaps,
            filepath_whse,
        ]

        if clientname == "dme":
            filepath_dme_booking_with_gaps = build_xls(
                bookings,
                "DMEBookingsWithGaps",
                username,
                start_date,
                end_date,
                show_field_name,
            )
            attachments.append(filepath_dme_booking_with_gaps)

        send_email(
            [email_addr],
            [],
            [],  # BCC
            "All XLS Report from Deliver-Me",  # Subject of email
            "Here is the excel report(Bookings & Booking Lines & Booking With Gaps & Whse) you generated from Deliver-Me.",  # Message of email
            attachments,  # Attachment file path(list)
        )


def tables_in_query(sql_str):

    # remove the /* */ comments
    q = re.sub(r"/\*[^*]*\*+(?:[^*/][^*]*\*+)*/", "", sql_str)

    # remove whole line -- and # comments
    lines = [line for line in q.splitlines() if not re.match("^\s*(--|#)", line)]

    # remove trailing -- and # comments
    q = " ".join([re.split("--|#", line)[0] for line in lines])

    # split on blanks, parens and semicolons
    tokens = re.split(r"[\s)(;]+", q)

    # scan the tokens. if we see a FROM or JOIN, we set the get_next
    # flag, and grab the next one (unless it's SELECT).

    result = []
    get_next = False
    for tok in tokens:
        if get_next:
            if tok.lower() not in ["", "select"]:
                result.append(tok)
            get_next = False
        get_next = tok.lower() in ["from", "join"]

    return result


def get_clientname_with_request(request):
    user_id = request.user.id
    dme_employee = (
        DME_employees.objects.select_related().filter(fk_id_user=user_id).first()
    )
    if dme_employee is not None:
        return "dme"
    else:
        client_employee = (
            Client_employees.objects.select_related().filter(fk_id_user=user_id).first()
        )
        client = DME_clients.objects.get(
            pk_id_dme_client=client_employee.fk_id_dme_client_id
        )
        return client.company_name


def get_pu_by(booking):
    pu_by = None

    if booking.s_20_Actual_Pickup_TimeStamp:
        if isinstance(booking.s_20_Actual_Pickup_TimeStamp, str):
            return datetime.strptime(
                booking.s_20_Actual_Pickup_TimeStamp[:10], "%Y-%m-%d"
            )
        else:
            return booking.s_20_Actual_Pickup_TimeStamp
    elif booking.b_dateBookedDate:
        if isinstance(booking.b_dateBookedDate, str):
            return datetime.strptime(booking.b_dateBookedDate[:19], "%Y-%m-%dT%H:%M:%S")
        else:
            return booking.b_dateBookedDate
    elif booking.pu_PickUp_By_Date:
        pu_PickUp_By_Date = booking.pu_PickUp_By_Date

        if isinstance(pu_PickUp_By_Date, str):
            pu_PickUp_By_Date = datetime.strptime(pu_PickUp_By_Date, "%Y-%m-%d")

        pu_by = datetime.combine(
            pu_PickUp_By_Date,
            time(
                int(booking.pu_PickUp_By_Time_Hours or 0),
                int(booking.pu_PickUp_By_Time_Minutes or 0),
                0,
            ),
        )

        return convert_to_UTC_tz(pu_by)
    elif booking.puPickUpAvailFrom_Date:
        puPickUpAvailFrom_Date = booking.puPickUpAvailFrom_Date

        if isinstance(puPickUpAvailFrom_Date, str):
            puPickUpAvailFrom_Date = datetime.strptime(
                puPickUpAvailFrom_Date, "%Y-%m-%d"
            )

        pu_by = datetime.combine(
            puPickUpAvailFrom_Date,
            time(
                int(booking.pu_PickUp_Avail_Time_Hours or 0),
                int(booking.pu_PickUp_Avail_Time_Minutes or 0),
                0,
            ),
        )

        return convert_to_UTC_tz(pu_by)
    else:
        return datetime.now()


def get_eta_pu_by(booking):
    LOG_ID = ["ETA_PU_BY"]

    try:
        return get_pu_by(booking)
    except Exception as e:
        trace_error.print()
        logger.info(f"{LOG_ID} Error #1001: {e}")
        return None


def get_eta_de_by(booking, quote):
    LOG_ID = ["ETA_DE_BY"]
    current_hour = (datetime.now().hour + TIME_DIFFERENCE) % 24

    try:
        eta_pu_by = get_eta_pu_by(booking)
        etd_in_hour = None

        if quote:
            from api.fp_apis.utils import get_etd_in_hour

            etd_in_hour = get_etd_in_hour(quote)
            fp = Fp_freight_providers.objects.get(
                fp_company_name=quote.freight_provider
            )

            # Service cut off time
            if not fp.service_cutoff_time or fp.service_cutoff_time.hour > current_hour:
                etd_de_by = eta_pu_by + timedelta(hours=etd_in_hour)
            else:
                etd_de_by = eta_pu_by + timedelta(hours=etd_in_hour + 24)
        else:
            etd_in_hour = get_eta_with_suburb(booking.de_To_Address_Suburb, "hour")

            # Service cut off time
            if 12 > current_hour:
                etd_de_by = eta_pu_by + timedelta(hours=etd_in_hour)
            else:
                etd_de_by = eta_pu_by + timedelta(hours=etd_in_hour)

        if booking.b_client_name == "Plum Products Australia Ltd":
            etd_de_by = eta_pu_by + timedelta(hours=3 * 24)

        if not etd_de_by.tzinfo:
            etd_de_by = UTC_TZ.localize(etd_de_by)

        if etd_de_by.tzinfo == UTC_TZ:
            etd_hour = 17 - TIME_DIFFERENCE
            if 0 <= etd_de_by.hour <= etd_hour:
                etd_de_by = etd_de_by.replace(hour=etd_hour, minute=0, second=0)
            else:
                etd_de_by += timedelta(hours=10)
                etd_de_by = etd_de_by.replace(hour=etd_hour, minute=0, second=0)
        else:
            etd_hour = 17
            if 9 <= etd_de_by.hour <= etd_hour:
                etd_de_by = etd_de_by.replace(hour=etd_hour, minute=0, second=0)
            elif etd_in_hour and etd_in_hour > 10:
                etd_de_by += timedelta(hours=10)
                etd_de_by = etd_de_by.replace(hour=etd_hour, minute=0, second=0)

        # Workdays
        weekno = etd_de_by.weekday()
        if weekno > 4:
            etd_de_by = etd_de_by + timedelta(days=7 - weekno)

        return etd_de_by
    except Exception as e:
        trace_error.print()
        logger.info(f"{LOG_ID} Error #1001: {e}")
        return None


def sanitize_address(address):
    if address is None:
        return address

    dme_augment_address = DME_Augment_Address.objects.all()
    for rule in dme_augment_address:
        address = string.ireplace(rule.origin_word, rule.augmented_word, address)

    return address
