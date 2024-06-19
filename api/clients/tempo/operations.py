import os
import uuid
import logging
import time as t

from django.conf import settings

from api.outputs.email import send_email
from api.helpers import cubic
from api.common.thread import background
from api.common import common_times as dme_time_lib
from api.models import (
    DME_Tokens,
    Bookings,
    Booking_lines,
    Booking_lines_data,
    BOK_3_lines_data,
    Client_warehouses,
    Client_Products,
    FP_zones,
)
from api.clients.tempo.constants import *

logger = logging.getLogger(__name__)


def find_warehouse(bok_1, bok_2s):
    LOG_ID = "[TEMPO WAREHOUSE FIND]"
    state = bok_1.get("b_031_b_pu_address_state")

    if not state:
        raise Exception("PickUp State is missing!")

    l_003_item = bok_2s[0].get("l_003_item") or ""

    logger.info(f"{LOG_ID} state: {state}, l_003_item: {l_003_item}")

    if l_003_item.upper() == "AK5821S6WOS":
        warehouse_code = "TEMPO_XTENSIVE"
    elif (
        l_003_item.upper() == "MICROWAVE"
        or "MICROWAVE" in l_003_item.upper()
        or "MWO" in l_003_item.upper()
    ):
        if state.upper() in ["ACT", "NSW", "NT", "SA", "TAS", "VIC"]:
            warehouse_code = "TEMPO_REWORX"
        elif state.upper() in ["QLD"]:
            warehouse_code = "TEMPO_REWORX_CARGO"
        elif state.upper() in ["WA"]:
            warehouse_code = "TEMPO_REWORX_QLS"
    else:
        if state.upper() in ["ACT", "NSW"]:
            warehouse_code = "TEMPO_AMERICAN"
        elif state.upper() in ["NT", "SA", "TAS", "VIC"]:
            warehouse_code = "TEMPO_XTENSIVE"
        elif state.upper() in ["QLD"]:
            warehouse_code = "TEMPO_REWORX_CARGO"
        elif state.upper() in ["WA"]:
            warehouse_code = "TEMPO_REWORX_QLS"

    if not warehouse_code:
        error_msg = f"Can`t find warehouse with this state: {state}"
        logger.error(f"{LOG_ID} {error_msg}")
        raise Exception(error_msg)

    warehouse = Client_warehouses.objects.get(client_warehouse_code=warehouse_code)
    return warehouse


def get_price(bok_1):
    """
    Used to get the price for Microwave
    """

    LOG_ID = "[GET PRICE]"

    pu_state = bok_1["b_031_b_pu_address_state"]
    pu_postalcode = str(bok_1["b_033_b_pu_address_postalcode"])
    pu_suburb = bok_1["b_032_b_pu_address_suburb"]

    de_state = bok_1["b_057_b_del_address_state"]
    de_postalcode = str(bok_1["b_059_b_del_address_postalcode"])
    de_suburb = bok_1["b_058_b_del_address_suburb"]

    if (
        pu_state.upper() == "QLD"
        and de_state.upper() == "QLD"
        and de_suburb.lower() == "yatala"
    ):

        """
        Brisbane / Gold Coast Metro and CBD,    Yatala, OLD,            23.42
        QLD Regional,                           Yatala, QLD,            42.33
        OLD Remote Locations,                   Yatala, QLD,            46.40
        """
        zones = FP_zones.objects.filter(fk_fp=7, state="QLD", sender_code__isnull=False)

        for zone in zones:
            if (
                zone.postal_code == pu_postalcode
                and zone.suburb.lower() == pu_suburb.lower()
            ):
                # QLD Regional
                if zone.sender_code == "Regional":
                    logger.info(f"{LOG_ID}, QLD Regional")
                    return 42.33
                # QLD Remote Locations
                elif zone.sender_code == "Remote":
                    logger.info(f"{LOG_ID}, QLD Remote Locations")
                    return 46.40
                # Brisbane / Gold Coast
                elif zone.zone in ["Brisbane", "Gold Coast"]:
                    logger.info(f"{LOG_ID}, Brisbane / Gold Coast")
                    return 23.42

        # QLD Metro and CBD
        pu_postalcode = int(pu_postalcode)
        if 4000 <= pu_postalcode <= 4207 or 9000 <= pu_postalcode <= 9499:
            logger.info(f"{LOG_ID}, QLD Metro and CBD")
            return 23.42
    elif (
        pu_state.upper() == "WA"
        and de_state.upper() == "WA"
        and de_suburb.lower() == "jandakot"
    ):
        """
        Perth Metro and CBD,                    Jandakot, WA,           23.42
        WA Regional,                            Jandakot, WA,           47.80
        WA Remote Locations,                    Jandakot, WA,           46.40
        """
        zones = FP_zones.objects.filter(fk_fp=7, state="WA", sender_code__isnull=False)

        for zone in zones:
            if (
                zone.postal_code == pu_postalcode
                and zone.suburb.lower() == pu_suburb.lower()
            ):
                # WA Regional
                if zone.sender_code == "Regional":
                    logger.info(f"{LOG_ID}, WA Regional")
                    return 47.80
                # WA Remote Locations
                elif zone.sender_code == "Remote":
                    logger.info(f"{LOG_ID}, WA Remote Locations")
                    return 46.40

        # Perth Metro and CBD
        pu_postalcode = int(pu_postalcode)
        if 6000 <= pu_postalcode <= 6199 or 6800 <= pu_postalcode <= 6999:
            logger.info(f"{LOG_ID}, Perth Metro and CBD")
            return 23.42
    elif de_state.upper() == "VIC" and de_suburb.lower() == "dingley village":
        """
        Sydney Metro and CBD,                   Dingley Village, VIC,   24.73
        NSW Regional,                           Dingley Village, VIC,   42.33
        NSW Remote Locations,                   Dingley Village, VIC,   46.40
        Melbourne Metro and CBD,                Dingley Village, VIC,   23.42
        VIC Regional,                           Dingley Village, VIC,   42.33
        VIC Remote Locations,                   Dingley Village, VIC,   46.40
        Adelaide Metro and CBD,                 Dingley Village, VIC,   42.33
        SA Regional,                            Dingley Village, VIC,   42.33
        SA Remote Locations,                    Dingley Village, VIC,   46.40
        Canberra Metro and CBD,                 Dingley Village, VIC,   42.33
        ACT Regional,                           Dingley Village, VIC,   42.33
        ACT Remote Locations,                   Dingley Village, VIC,   46.40
        NT,                                     Dingley Village, VIC,   46.40
        Hobart, Launceston,                     Dingley Village, VIC,   42,33
        TAS Regional,                           Dingley Village, VIC,   42.33
        TAS Remote Locations,                   Dingley Village, VIC,   46.40
        """
        states = ["NSW", "VIC", "SA", "ACT", "NT", "TAS"]
        zones = FP_zones.objects.filter(
            fk_fp=7, state__in=states, sender_code__isnull=False
        )

        # Sydney Metro and CBD
        pu_postalcode = int(pu_postalcode)
        if 1000 <= pu_postalcode <= 2249 or 2760 <= pu_postalcode <= 2770:
            logger.info(f"{LOG_ID}, Sydney Metro and CBD")
            return 24.73

        # Melbourne Metro and CBD
        pu_postalcode = int(pu_postalcode)
        if 3000 <= pu_postalcode <= 3207 or 8000 <= pu_postalcode <= 8499:
            logger.info(f"{LOG_ID}, Melbourne Metro and CBD")
            return 23.42

        # Adelaide Metro and CBD
        pu_postalcode = int(pu_postalcode)
        if 5000 <= pu_postalcode <= 5199 or 5900 <= pu_postalcode <= 5999:
            logger.info(f"{LOG_ID}, Adelaide Metro and CBD")
            return 42.33

        # Canberra Metro and CBD
        pu_postalcode = int(pu_postalcode)
        if 2600 <= pu_postalcode <= 2620 or 2900 <= pu_postalcode <= 2914:
            logger.info(f"{LOG_ID}, Canberra Metro and CBD")
            return 42.33

        for zone in zones:
            if (
                zone.postal_code == pu_postalcode
                and zone.suburb.lower() == pu_suburb.lower()
            ):
                # NSW Regional
                if pu_state.upper == "NSW" and zone.sender_code == "Regional":
                    logger.info(f"{LOG_ID}, NSW Regional")
                    return 42.33
                # NSW Remote Locations
                elif pu_state.upper == "NSW" and zone.sender_code == "Remote":
                    logger.info(f"{LOG_ID}, NSW Remote")
                    return 46.40

                # VIC Regional
                if pu_state.upper == "VIC" and zone.sender_code == "Regional":
                    logger.info(f"{LOG_ID}, VIC Regional")
                    return 42.33
                # VIC Remote Locations
                elif pu_state.upper == "VIC" and zone.sender_code == "Remote":
                    logger.info(f"{LOG_ID}, VIC Remote")
                    return 46.40

                # SA Regional
                if pu_state.upper == "SA" and zone.sender_code == "Regional":
                    logger.info(f"{LOG_ID}, SA Regional")
                    return 42.33
                # SA Remote Locations
                elif pu_state.upper == "SA" and zone.sender_code == "Remote":
                    logger.info(f"{LOG_ID}, SA Remote")
                    return 46.40

                # ACT Regional
                if pu_state.upper == "ACT" and zone.sender_code == "Regional":
                    logger.info(f"{LOG_ID}, ACT Regional")
                    return 42.33
                # ACT Remote Locations
                elif pu_state.upper == "ACT" and zone.sender_code == "Remote":
                    logger.info(f"{LOG_ID}, ACT Remote")
                    return 46.40

                # TAS Regional
                if pu_state.upper == "TAS" and zone.sender_code == "Regional":
                    logger.info(f"{LOG_ID}, TAS Regional")
                    return 42.33
                # TAS Remote Locations
                elif pu_state.upper == "TAS" and zone.sender_code == "Remote":
                    logger.info(f"{LOG_ID}, TAS Remote")
                    return 46.40
                elif pu_state.upper == "TAS" and zone.zone in ["Hobart", "Launceston"]:
                    logger.info(f"{LOG_ID}, Hobart, Launceston")
                    return 42.33

                # NSW Regional
                if pu_state.upper == "NT":
                    logger.info(f"{LOG_ID}, NT")
                    return 46.40

    return 0


@background
def send_email_4_approval(bok_1_obj, best_quote, auto_book_amount):
    LOG_ID = "[Tempo 4 Approval]"
    logger.info(f"{LOG_ID} Email will be sent in a minute...")

    # Delay 4 mins for mapping
    # t.sleep(60 * 4)
    t.sleep(30)

    booking = Bookings.objects.get(pk_booking_id=bok_1_obj.pk_header_id)
    lines = booking.lines()
    line_datas = booking.line_datas()
    quote = best_quote

    token = f"{uuid.uuid4()}_{booking.pk}"
    email = TEMPO_AGENT["email"]

    logger.info(f"{LOG_ID} TEMPO Token: {token}")
    dme_token = DME_Tokens.objects.create(
        token_type="TEMPO-APPROVAL",
        token=token,
        vx_freight_provider=quote.freight_provider,
        booking_id=booking.pk,
        api_booking_quote_id=quote.pk,
        email=email,
    )

    total_weight = 0
    total_lines_cnt = 0
    total_cubic_meter = 0
    message_lines = ""
    gap_ras = []

    for line_data in line_datas:
        gap_ras.append(line_data.gap_ra)

    for line in lines:
        grams = ["g", "gram", "grams"]
        kgs = ["kilogram", "kilograms", "kg", "kgs"]
        tons = ["t", "ton", "tons"]

        pallet_cubic_meter = cubic.get_cubic_meter(
            line.e_dimLength,
            line.e_dimWidth,
            line.e_dimHeight,
            line.e_dimUOM,
            line.e_qty,
        )

        if line.e_weightUOM.lower() in grams:
            total_weight += line.e_qty * line.e_weightPerEach / 1000
        elif line.e_weightUOM.lower() in kgs:
            total_weight += line.e_qty * line.e_weightPerEach
        elif line.e_weightUOM.lower() in tons:
            total_weight += line.e_qty * line.e_weightPerEach * 1000
        total_lines_cnt += line.e_qty
        total_cubic_meter += pallet_cubic_meter

        message_lines += f"""
            <tr>
              <td style='border: 1px solid black;'>{line.e_type_of_packaging}</td>
              <td style='border: 1px solid black;'>{line.e_item}</td>
              <td style='border: 1px solid black;'>{line.e_qty}</td>
              <td style='border: 1px solid black;'>{line.e_dimUOM}</td>
              <td style='border: 1px solid black;'>{line.e_dimLength}</td>
              <td style='border: 1px solid black;'>{line.e_dimWidth}</td>
              <td style='border: 1px solid black;'>{line.e_dimHeight}</td>
              <td style='border: 1px solid black;'>{round(pallet_cubic_meter, 3)} (m3)</td>
              <td style='border: 1px solid black;'>{round(line.e_qty * line.e_weightPerEach, 3)} ({line.e_weightUOM})</td>
            </tr>
        """

        _line_datas = []
        for line_data in line_datas:
            if line_data.fk_booking_lines_id == line.pk_booking_lines_id:
                _line_datas.append(line_data)
        if _line_datas:
            message_lines += f"""
                <tr>
                  <td style='border: 1px solid black;' colspan='9'>
                    <table style='border: 1px solid black;width:calc(100% - 10px);text-align:center;border-spacing: 0;margin:5px;'>
                      <tr>
                        <th style='border: 1px solid black;' rowspan="{len(_line_datas)}">Lines Data</th>
                        <th style='border: 1px solid black;'>Model</th>
                        <th style='border: 1px solid black;'>Item Descripton</th>
                        <th style='border: 1px solid black;'>Qty</th>
                        <th style='border: 1px solid black;'>Fault Description</th>   
                        <th style='border: 1px solid black;'>Gap / RA</th>    
                        <th style='border: 1px solid black;'>Client Reference #</th>   
                      </tr>
            """
            for line_data in _line_datas:
                message_lines += f"""
                    <tr>
                        <td style='border: 1px solid black;'></td>
                        <td style='border: 1px solid black;'>{line_data.modelNumber}</td>
                        <td style='border: 1px solid black;'>{line_data.itemDescription}</td>
                        <td style='border: 1px solid black;'>{line_data.quantity}</td>
                        <td style='border: 1px solid black;'>{line_data.itemFaultDescription}</td>
                        <td style='border: 1px solid black;'>{line_data.gap_ra}</td>
                        <td style='border: 1px solid black;'>{line_data.clientRefNumber}</td>
                    </tr>
                """
            message_lines += f"""
                  </table>
                </td>
              </tr>
            """

    subject = f"Quote for order({', '.join(gap_ras)}) from Deliver-ME!"
    message = f"""
        <html>
        <head></head>
        <body>
            <p>Dear Tempo Pty Ltd,</p>
            <div style='height:1px;'></div>
            <p>Please check the quote and approve. Please get to your booking by using below links.</p>

            <p style='text-align:center;margin:20px 0'>
                <a
                    style='padding:10px 20px;margin-right:80px;background: #2e6da4;color:white;border-radius:4px;text-decoration:none;'
                    href="{settings.WEB_SITE_URL}/approve/{dme_token.token}"
                    title="Approve"
                >
                    Approve
                </a>&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;
                <a
                    style='padding:10px 20px;margin-right:80px;background: #d9534f;color:white;border-radius:4px;text-decoration:none;'
                    href="{settings.WEB_SITE_URL}/disapprove-hold/{dme_token.token}"
                    title="Disapprove and put the booking on hold"
                >
                    Disapprove, hold booking 
                </a>&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;
                <a
                    style='padding:10px 20px;background: #d9534f;color:white;border-radius:4px;text-decoration:none;'
                    href="{settings.WEB_SITE_URL}/disapprove-disposal/{dme_token.token}"
                    title="Disapprove and send an email to the store authorizing item/s disposal"
                >
                    Disapprove, authorize disposal
                </a>
            </p>

            <h2>Main Info: </h2>
            <div>
                <!--<strong>Client Name: </strong><span>{booking.b_client_name}</span><br />-->
                <!--<strong>Client Order Number: </strong><span>{booking.b_client_order_num}</span><br />-->
                <!--<strong>Client Sales Invoice Number: </strong><span>{booking.b_client_sales_inv_num}</span><br />-->
                <!--<strong>Despatch Date: </strong><span>{booking.puPickUpAvailFrom_Date}</span><br />-->
                <strong>Gap/ra(s): </strong><span>{", ".join(gap_ras)}</span><br />
                <strong>Auto Book Amount Max Threshold: </strong><span>${auto_book_amount}</span><br />
                <strong>Quoted Cost: </strong><span>${round(quote.client_mu_1_minimum_values, 3)}</span><br />
            </div>
            <div>
                <div style='display: inline-block;margin-right:100px;'>
                    <h3 style='color: deepskyblue'>Pickup From:</h3>
                    <div>
                        <strong>Entity Name: </strong><span>{booking.puCompany}</span><br />
                        <strong>Street 1: </strong><span>{booking.pu_Address_Street_1}</span><br />
                        <strong>Street 2: </strong><span>{booking.pu_Address_street_2 or ""}</span><br />
                        <strong>Suburb: </strong><span>{booking.pu_Address_Suburb}</span><br />
                        <strong>State: </strong><span>{booking.pu_Address_State}</span><br />
                        <strong>PostalCode: </strong><span>{booking.pu_Address_PostalCode}</span><br />
                        <strong>Country: </strong><span>{booking.pu_Address_Country}</span><br />
                        <strong>Contact: </strong><span>{booking.pu_Contact_F_L_Name}</span><br />
                        <strong>Email: </strong><span>{booking.pu_Email}</span><br />
                        <strong>Phone: </strong><span>{booking.pu_Phone_Main}</span><br />
                    </div>
                </div>
                <div style='display: inline-block;'>
                    <h3 style='color: deepskyblue'>Deliver To:</h3>
                    <div>
                        <strong>Entity Name: </strong><span>{booking.deToCompanyName}</span><br />
                        <strong>Street 1: </strong><span>{booking.de_To_Address_Street_1}</span><br />
                        <strong>Street 2: </strong><span>{booking.de_To_Address_Street_2}</span><br />
                        <strong>Suburb: </strong><span>{booking.de_To_Address_Suburb}</span><br />
                        <strong>State: </strong><span>{booking.de_To_Address_State}</span><br />
                        <strong>PostalCode: </strong><span>{booking.de_To_Address_PostalCode}</span><br />
                        <strong>Country: </strong><span>{booking.de_To_Address_Country}</span><br />
                        <strong>Contact: </strong><span>{booking.de_to_Contact_F_LName}</span><br />
                        <strong>Email: </strong><span>{booking.de_Email}</span><br />
                        <strong>Phone: </strong><span>{booking.de_to_Phone_Main}</span><br />
                    </div>
                </div>
            </div>

            <h2>Lines: </h2>
            <table style='border: 1px solid black;width:100%;text-align:center;border-spacing: 0'>
              <thead>
                <tr>
                  <th style='border: 1px solid black;'>Total Quantity</th>
                  <th style='border: 1px solid black;'>Total Weight (Kg)</th>
                  <th style='border: 1px solid black;'>Total Cubic Meter (M3)</th>
                </tr>
              </thead>
              <tbody>
                <tr>
                  <td style='border: 1px solid black;'>{total_lines_cnt}</td>
                  <td style='border: 1px solid black;'>{round(total_weight, 3)}</td>
                  <td style='border: 1px solid black;'>{round(total_cubic_meter, 3)}</td>
                </tr>
              </tbody>
           </table>
            <br/>
            <table style='border: 1px solid black;width:100%;text-align:center;border-spacing: 0'>
              <thead>
                <tr>
                  <th style='border: 1px solid black;'>Type Of Packaging</th>
                  <th style='border: 1px solid black;'>Item Descripton</th>
                  <th style='border: 1px solid black;'>Qty</th>
                  <th style='border: 1px solid black;'>Dim UOM</th>
                  <th style='border: 1px solid black;'>Length</th>
                  <th style='border: 1px solid black;'>Width</th>
                  <th style='border: 1px solid black;'>Height</th>
                  <th style='border: 1px solid black;'>CBM</th>
                  <th style='border: 1px solid black;'>Total Weight</th>    
                </tr>
              </thead>
              <tbody>
                {message_lines}
              </tbody>
            </table>
            
            <br/>

            <p style='text-align:center;margin:20px 0'>
                <a
                    style='padding:10px 20px;margin-right:80px;background: #2e6da4;color:white;border-radius:4px;text-decoration:none;'
                    href="{settings.WEB_SITE_URL}/approve/{dme_token.token}"
                    title="Approve"
                >
                    Approve
                </a>&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;
                <a
                    style='padding:10px 20px;margin-right:80px;background: #d9534f;color:white;border-radius:4px;text-decoration:none;'
                    href="{settings.WEB_SITE_URL}/disapprove-hold/{dme_token.token}"
                    title="Disapprove and put the booking on hold"
                >
                    Disapprove, hold booking 
                </a>&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;
                <a
                    style='padding:10px 20px;background: #d9534f;color:white;border-radius:4px;text-decoration:none;'
                    href="{settings.WEB_SITE_URL}/disapprove-disposal/{dme_token.token}"
                    title="Disapprove and send an email to the store authorizing item/s disposal"
                >
                    Disapprove, authorize disposal
                </a>
            </p><br />

            <p>Regards,<br />Deliver-ME</p>
        </body>
        </html>
    """

    if settings.ENV != "prod":
        To = [settings.ADMIN_EMAIL_02]
        CCs = [
            settings.ADMIN_EMAIL_02,
            "bookings@deliver-me.com.au",
            "dev.deliverme@gmail.com",
        ]
    else:
        To = [TEMPO_AGENT.email, "bookings@deliver-me.com.au"]

        if bok_1_obj.zb_101_text_1 == "01_Retailer_Collections":
            CCs = RETAILER_COLLECTIONS
            if bok_1_obj.b_036_b_pu_email_group:
                CCs.append(bok_1_obj.b_036_b_pu_email_group)
            if bok_1_obj.b_037_b_pu_email:
                CCs.append(bok_1_obj.b_037_b_pu_email)
        elif bok_1_obj.zb_101_text_1 == "02_Microwave_Portal_Collections":
            CCs = MICROWAVE_PORTAL_COLLECTIONS
        elif bok_1_obj.zb_101_text_1 == "03_ALDI_TV_Collections":
            CCs = ALDI_TV_COLLECTIONS
        elif bok_1_obj.zb_101_text_1 == "04_Other_Customer_Collections":
            CCs = OTHER_CUSTOMER_COLLECTIONS
        # 05, 06 Auto Approval all and keep as Ready to book - send email to bookings only - all will be approved
        elif bok_1_obj.zb_101_text_1 == "05_Brindley_Warehouse_Collections":
            To = ["bookings@deliver-me.com.au"]
            CCs = []
        elif bok_1_obj.zb_101_text_1 == "06_Bulk_Salvage_Collections":
            To = ["bookings@deliver-me.com.au"]
            CCs = []

    send_email(To, CCs, [], subject, message, mime_type="html")
    logger.info(f"{LOG_ID} Sent email - {dme_token.vx_freight_provider}")


@background
def send_email_approved(booking, lines, line_datas, dme_token):
    LOG_ID = "[Tempo Email Approved]"
    subject = f"Quote is disapproved by Tempo Pty Ltd"

    quote = booking.api_booking_quote
    total_weight = 0
    total_lines_cnt = 0
    total_cubic_meter = 0
    message_lines = ""
    gap_ras = []

    for line_data in line_datas:
        gap_ras.append(line_data.gap_ra)

    for line in lines:
        grams = ["g", "gram", "grams"]
        kgs = ["kilogram", "kilograms", "kg", "kgs"]
        tons = ["t", "ton", "tons"]

        pallet_cubic_meter = cubic.get_cubic_meter(
            line.e_dimLength,
            line.e_dimWidth,
            line.e_dimHeight,
            line.e_dimUOM,
            line.e_qty,
        )

        if line.e_weightUOM.lower() in grams:
            total_weight += line.e_qty * line.e_weightPerEach / 1000
        elif line.e_weightUOM.lower() in kgs:
            total_weight += line.e_qty * line.e_weightPerEach
        elif line.e_weightUOM.lower() in tons:
            total_weight += line.e_qty * line.e_weightPerEach * 1000
        total_lines_cnt += line.e_qty
        total_cubic_meter += pallet_cubic_meter

        message_lines += f"""
            <tr>
                <td style='border: 1px solid black;'>{line.e_type_of_packaging}</td>
                <td style='border: 1px solid black;'>{line.e_item}</td>
                <td style='border: 1px solid black;'>{line.e_qty}</td>
                <td style='border: 1px solid black;'>{line.e_dimUOM}</td>
                <td style='border: 1px solid black;'>{line.e_dimLength}</td>
                <td style='border: 1px solid black;'>{line.e_dimWidth}</td>
                <td style='border: 1px solid black;'>{line.e_dimHeight}</td>
                <td style='border: 1px solid black;'>{round(pallet_cubic_meter, 3)} (m3)</td>
                <td style='border: 1px solid black;'>{round(line.e_qty * line.e_weightPerEach, 3)} ({line.e_weightUOM})</td>
            </tr>
        """

        _line_datas = []
        for line_data in line_datas:
            if line_data.fk_booking_lines_id == line.pk_booking_lines_id:
                _line_datas.append(line_data)
        if _line_datas:
            message_lines += f"""
                <tr>
                  <td style='border: 1px solid black;' colspan='9'>
                    <table style='border: 1px solid black;width:calc(100% - 10px);text-align:center;border-spacing: 0;margin:5px;'>
                      <tr>
                        <th style='border: 1px solid black;' rowspan="{len(_line_datas)}">Lines Data</th>
                        <th style='border: 1px solid black;'>Model</th>
                        <th style='border: 1px solid black;'>Item Descripton</th>
                        <th style='border: 1px solid black;'>Qty</th>
                        <th style='border: 1px solid black;'>Fault Description</th>   
                        <th style='border: 1px solid black;'>Gap / RA</th>    
                        <th style='border: 1px solid black;'>Client Reference #</th>   
                      </tr>
            """
            for line_data in _line_datas:
                message_lines += f"""
                    <tr>
                        <td style='border: 1px solid black;'></td>
                        <td style='border: 1px solid black;'>{line_data.modelNumber}</td>
                        <td style='border: 1px solid black;'>{line_data.itemDescription}</td>
                        <td style='border: 1px solid black;'>{line_data.quantity}</td>
                        <td style='border: 1px solid black;'>{line_data.itemFaultDescription}</td>
                        <td style='border: 1px solid black;'>{line_data.gap_ra}</td>
                        <td style='border: 1px solid black;'>{line_data.clientRefNumber}</td>
                    </tr>
                """
            message_lines += f"""
                  </table>
                </td>
              </tr>
            """

    message = f"""
        <html>
        <head></head>
        <body>
            <p>Dear Deliver-ME Customer Support,</p>
            <div style='height:1px;'></div>
            <p>This booking's quote is disapporved by Tempo Pty Ltd.</p>
            <div style='height:1px;'></div>

            <h2>Main Info: </h2>
            <div>
                <strong>Client Name: </strong><span>{booking.b_client_name}</span><br />
                <strong>Gap/ra(s): </strong><span>{", ".join(gap_ras)}</span><br />
                <strong>Despatch Date: </strong><span>{booking.puPickUpAvailFrom_Date}</span><br />
                <strong>Freight Provider: </strong><span>{quote.freight_provider}</span>
            </div>
            <div>
              <div style='display: inline-block;margin-right:100px;'>
                <h3 style='color: deepskyblue'>Pickup From:</h3>
                <div>
                    <strong>Entity Name: </strong><span>{booking.puCompany}</span><br />
                    <strong>Street 1: </strong><span>{booking.pu_Address_Street_1}</span><br />
                    <strong>Street 2: </strong><span>{booking.pu_Address_street_2 or ""}</span><br />
                    <strong>Suburb: </strong><span>{booking.pu_Address_Suburb}</span><br />
                    <strong>State: </strong><span>{booking.pu_Address_State}</span><br />
                    <strong>PostalCode: </strong><span>{booking.pu_Address_PostalCode}</span><br />
                    <strong>Country: </strong><span>{booking.pu_Address_Country}</span><br />
                    <strong>Contact: </strong><span>{booking.pu_Contact_F_L_Name}</span><br />
                    <strong>Email: </strong><span>{booking.pu_Email}</span><br />
                    <strong>Phone: </strong><span>{booking.pu_Phone_Main}</span><br />
                </div>
              </div>
              <div style='display: inline-block;'>
                <h3 style='color: deepskyblue'>Deliver To:</h3>
                <div>
                    <strong>Entity Name: </strong><span>{booking.deToCompanyName}</span><br />
                    <strong>Street 1: </strong><span>{booking.de_To_Address_Street_1}</span><br />
                    <strong>Street 2: </strong><span>{booking.de_To_Address_Street_2}</span><br />
                    <strong>Suburb: </strong><span>{booking.de_To_Address_Suburb}</span><br />
                    <strong>State: </strong><span>{booking.de_To_Address_State}</span><br />
                    <strong>PostalCode: </strong><span>{booking.de_To_Address_PostalCode}</span><br />
                    <strong>Country: </strong><span>{booking.de_To_Address_Country}</span><br />
                    <strong>Contact: </strong><span>{booking.de_to_Contact_F_LName}</span><br />
                    <strong>Email: </strong><span>{booking.de_Email}</span><br />
                    <strong>Phone: </strong><span>{booking.de_to_Phone_Main}</span><br />
                </div>
              </div>
            </div>
            <h2>Lines: </h2>
            
            <table style='border: 1px solid black;width:100%;text-align:center;border-spacing: 0'>
              <thead>
                <tr>
                  <th style='border: 1px solid black;'>Total Quantity</th>
                  <th style='border: 1px solid black;'>Total Weight (Kg)</th>
                  <th style='border: 1px solid black;'>Total Cubic Meter (M3)</th>
                </tr>
              </thead>
              <tbody>
                <tr>
                  <td style='border: 1px solid black;'>{total_lines_cnt}</td>
                  <td style='border: 1px solid black;'>{round(total_weight, 3)}</td>
                  <td style='border: 1px solid black;'>{round(total_cubic_meter, 3)}</td>
                </tr>
              </tbody>
           </table>
            <br/>
            <table style='border: 1px solid black;width:100%;text-align:center;border-spacing: 0'>
              <thead>
                <tr>
                  <th style='border: 1px solid black;'>Type Of Packaging</th>
                  <th style='border: 1px solid black;'>Item Descripton</th>
                  <th style='border: 1px solid black;'>Qty</th>
                  <th style='border: 1px solid black;'>Dim UOM</th>
                  <th style='border: 1px solid black;'>Length</th>
                  <th style='border: 1px solid black;'>Width</th>
                  <th style='border: 1px solid black;'>Height</th>
                  <th style='border: 1px solid black;'>CBM</th>
                  <th style='border: 1px solid black;'>Total Weight</th>    
                </tr>
              </thead>
              <tbody>
                {message_lines}
              </tbody>
            </table>
            
            <br/>

            <p style='text-align:center;'>
                <a
                    style='padding:10px 20px;background: #2e6da4;color:white;border-radius:4px;text-decoration:none;'
                    href="{settings.WEB_SITE_URL}/booking?bookingId={booking.b_bookingID_Visual}"
                >
                    Click here to check on DME portal
                </a>
            </p><br />

            <p>For button link to work, please be sure you are logged into dme before clicking.</p><br />
            
            <p>Regards,<br />Deliver-ME API</p>
        </body>
        </html>
    """

    CCs = []
    if settings.ENV != "prod":
        CCs = [
            settings.ADMIN_EMAIL_02,
            "bookings@deliver-me.com.au",
            "dev.deliverme@gmail.com",
        ]
    else:
        CCs = ["bookings@deliver-me.com.au"]

    send_email(
        [settings.SUPPORT_CENTER_EMAIL], CCs, [], subject, message, mime_type="html"
    )
    logger.info(f"{LOG_ID} Sent email")


@background
def send_email_disposal(booking, lines, line_datas, dme_token):
    LOG_ID = "[Tempo Email Disposal]"

    total_weight = 0
    total_lines_cnt = 0
    total_cubic_meter = 0
    message_lines = ""
    gap_ras = []

    for line_data in line_datas:
        gap_ras.append(line_data.gap_ra)

    for line_data in line_datas:
        message_lines += f"""
            <tr>
                <td style='border: 1px solid black;'>{line_data.modelNumber}</td>
                <td style='border: 1px solid black;'>{line_data.itemDescription}</td>
                <td style='border: 1px solid black;'>{line_data.quantity}</td>
                <td style='border: 1px solid black;'>{line_data.itemFaultDescription}</td>
                <td style='border: 1px solid black;'>{line_data.gap_ra}</td>
                <td style='border: 1px solid black;'>{line_data.clientRefNumber}</td>
            </tr>
        """

    subject = f"Disposal request for order({', '.join(gap_ras)})"
    message = f"""
        <html>
        <head></head>
        <body>
            <p>Dear {booking.pu_Contact_F_L_Name},</p>
            <div style='height:1px;'></div>
            <p>It is not economical for us to collect the unit/s. Please dispose off the claim/s on the table below.</p>
            <div style='height:1px;'></div>

            <table style='border: 1px solid black;width:calc(100% - 10px);text-align:center;border-spacing: 0;margin:5px;'>
              <tr>
                <th style='border: 1px solid black;'>Model</th>
                <th style='border: 1px solid black;'>Item Descripton</th>
                <th style='border: 1px solid black;'>Qty</th>
                <th style='border: 1px solid black;'>Fault Description</th>
                <th style='border: 1px solid black;'>Gap / RA</th>
                <th style='border: 1px solid black;'>Client Reference #</th>
              </tr>
              </thead>
              <tbody>
                {message_lines}
              </tbody>
            </table>

            <br/>
            <p>Regards,<br />Deliver-ME API</p>
        </body>
        </html>
    """

    CCs = []
    if settings.ENV != "prod":
        CCs = [
            settings.ADMIN_EMAIL_02,
            "bookings@deliver-me.com.au",
            "dev.deliverme@gmail.com",
        ]
    else:
        CCs = ["bookings@deliver-me.com.au"] + TEMPO_CS_EMAILS

    send_email([TEMPO_AGENT["email"]], CCs, [], subject, message, mime_type="html")
    logger.info(f"{LOG_ID} Sent email")


def get_product(model_number):
    product = Client_Products.objects.get(parent_model_number=model_number)
    return product
