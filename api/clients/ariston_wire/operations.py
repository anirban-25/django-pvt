import time as t
import os
import math
import logging
from datetime import datetime, timedelta
from email.utils import COMMASPACE, formatdate

from django.conf import settings
from rest_framework import serializers

from api.models import (
    DME_Email_Templates,
    Bookings,
    Booking_lines,
    Booking_lines_data,
    EmailLogs,
    DME_Options,
    DME_clients,
    Utl_dme_status,
    Dme_status_history,
    API_booking_quotes,
    Client_Products,
    DME_Options,
)
from api.outputs.email import send_email
from api.helpers.etd import get_etd
from api.helpers import cubic
from api.common.thread import background
from api.common import common_times as dme_time_lib

logger = logging.getLogger(__name__)


@background
def send_email_open_bidding(to_emails, booking, bok_lines, token, freight_provider):
    LOG_ID = "[AW Open Bidding Email]"

    # Delay 30 mins
    t.sleep(60 * 0)
    booking.refresh_from_db()

    if booking.api_booking_quote:
        from api.clients.ariston_wire.constants import ARISTON_WIRE_FP_NAMES

        if not booking.api_booking_quote.freight_provider in ARISTON_WIRE_FP_NAMES:
            logger.info(
                f"DME FP is already selected for this order({booking.b_client_order_num})"
            )
            return

    total_weight = 0
    total_lines_cnt = 0
    total_cubic_meter = 0
    message_lines = ""

    for line in bok_lines:
        grams = ["g", "gram", "grams"]
        kgs = ["kilogram", "kilograms", "kg", "kgs"]
        tons = ["t", "ton", "tons"]

        pallet_cubic_meter = cubic.get_cubic_meter(
            line.l_005_dim_length,
            line.l_006_dim_width,
            line.l_007_dim_height,
            line.l_004_dim_UOM,
            line.l_002_qty,
        )

        if line.l_008_weight_UOM.lower() in grams:
            total_weight += line.l_002_qty * line.l_009_weight_per_each / 1000
        elif line.l_008_weight_UOM.lower() in kgs:
            total_weight += line.l_002_qty * line.l_009_weight_per_each
        elif line.l_008_weight_UOM.lower() in tons:
            total_weight += line.l_002_qty * line.l_009_weight_per_each * 1000
        total_lines_cnt += line.l_002_qty
        total_cubic_meter += pallet_cubic_meter

        message_lines += f"""
                <tr>
                  <td style='border: 1px solid black;'>{line.l_001_type_of_packaging}</td>
                  <td style='border: 1px solid black;'>{line.l_003_item}</td>
                  <td style='border: 1px solid black;'>{line.l_002_qty}</td>
                  <td style='border: 1px solid black;'>{line.l_004_dim_UOM}</td>
                  <td style='border: 1px solid black;'>{line.l_005_dim_length}</td>
                  <td style='border: 1px solid black;'>{line.l_006_dim_width}</td>
                  <td style='border: 1px solid black;'>{line.l_007_dim_height}</td>
                  <td style='border: 1px solid black;'>{round(pallet_cubic_meter, 3)} (m3)</td>
                  <td style='border: 1px solid black;'>{round(line.l_002_qty * line.l_009_weight_per_each, 3)} ({line.l_008_weight_UOM})</td>
                </tr>
        """
    # now = datetime.now() + timedelta(days=1)
    bid_closing_at = booking.bid_closing_at
    subject = f"Don't miss this chance from Deliver-Me!"

    message = f"""
        <html>
        <head></head>
        <body>
            <p>Dear {freight_provider},</p>
            <div style='height:1px;'></div>
            <p>Deliver-ME has a booking you may be able to assist us with that needs a quote by {bid_closing_at.strftime("%d-%m-%Y %H:%M")} East Coast time.</p>
            <p>If you are able to perform this job please can you click on this link to let us know your timing and cost.</p>
            <div style='height:1px;'></div>
            <p>Thank you</p>
            
            <!--<div style='margin-top: 20px;'>              
                <strong style='width:150px;float:left;'>Availability Date: </strong> <input style='width:250px'  type='text' /><br />
            </div>
            <div style='margin-top: 20px;'>   
                <strong style='width:150px;float:left;'>From Time: </strong> <input style='width:250px' type='text' /></span><br />
            </div>
            <div style='margin-top: 20px;'>   
                <strong style='width:150px;float:left;'>To Time: </strong> <input style='width:250px' type='text' /><br />
            </div>
            <div style='margin-top: 20px;'>   
                <strong style='width:150px;float:left;'>Total Price ex GST: </strong> <input style='width:250px' type='text' /><br />
            </div>
            <div style='margin-top: 20px;'>   
                <strong style='width:150px;float:left;'>Anything we should know?: </strong> <input style='width:250px;height: 100px;' type='text' /><br />
            </div>-->

            <p style='text-align:center;margin:20px 0'>
                <a
                    style='padding:10px 20px;background: #2e6da4;color:white;border-radius:4px;text-decoration:none;'
                    href="{os.environ["WEB_SITE_URL"]}/bid/{token}"
                >
                    Click here to quote
                </a>
            </p>

            <h2>Main Info: </h2>
            <div>
                <strong>Client Name: </strong><span>{booking.b_client_name}</span><br />
                <strong>Client Order Number: </strong><span>{booking.b_client_order_num}</span><br />
                <strong>Client Sales Invoice Number: </strong><span>{booking.b_client_sales_inv_num}</span><br />
                <strong>Despatch Date: </strong><span>{booking.puPickUpAvailFrom_Date}</span><br />
            </div>
            <div style='display:flex;'>
              <div>
                <h3 style='color: deepskyblue'>Pickup From: </h3>
                <div>
                    <strong>Entity Name: </strong><span>{booking.puCompany}</span><br />
                    <strong>Street 1: </strong><span>{booking.pu_Address_Street_1}</span><br />
                    <strong>Street 2: </strong><span>{booking.pu_Address_street_2}</span><br />
                    <strong>Suburb: </strong><span>{booking.pu_Address_Suburb}</span><br />
                    <strong>State: </strong><span>{booking.pu_Address_State}</span><br />
                    <strong>PostalCode: </strong><span>{booking.pu_Address_PostalCode}</span><br />
                    <strong>Country: </strong><span>{booking.pu_Address_Country}</span><br />
                    <strong>Contact: </strong><span>{booking.pu_Contact_F_L_Name}</span><br />
                    <strong>Email: </strong><span>{booking.pu_Email}</span><br />
                    <strong>Phone: </strong><span>{booking.pu_Phone_Main}</span><br />
                </div>
              </div>
              <div  style='margin-left:100px;'>
                <h3 style='color: deepskyblue'>Deliver To: </h3>
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
                    href="{os.environ["WEB_SITE_URL"]}/bid/{token}"
                >
                    Click here to quote
                </a>
            </p>

        </body>
        </html>
    """

    send_email(to_emails, [], [], subject, message, mime_type="html")
    logger.info(f"{LOG_ID} Sent email - {freight_provider}")


@background
def send_email_close_bidding(booking, bok_lines, dme_token, quote):
    LOG_ID = "[AW Close Bidding Email]"

    # Delay 30 mins
    t.sleep(60 * 1)
    booking.refresh_from_db()

    if booking.api_booking_quote:
        if booking.api_booking_quote.freight_provider != quote.freight_provider:
            logger.info(
                f"{LOG_ID} Other FP is selected for this order({booking.b_client_order_num}): {quote.freight_provider} ---> {booking.api_booking_quote.freight_provider}"
            )
            return

    selected = True if dme_token.api_booking_quote_id == quote.pk else False
    if not selected:
        return
    total_weight = 0
    total_lines_cnt = 0
    total_cubic_meter = 0
    message_lines = ""

    for line in bok_lines:
        grams = ["g", "gram", "grams"]
        kgs = ["kilogram", "kilograms", "kg", "kgs"]
        tons = ["t", "ton", "tons"]

        pallet_cubic_meter = cubic.get_cubic_meter(
            line.l_005_dim_length,
            line.l_006_dim_width,
            line.l_007_dim_height,
            line.l_004_dim_UOM,
            line.l_002_qty,
        )

        if line.l_008_weight_UOM.lower() in grams:
            total_weight += line.l_002_qty * line.l_009_weight_per_each / 1000
        elif line.l_008_weight_UOM.lower() in kgs:
            total_weight += line.l_002_qty * line.l_009_weight_per_each
        elif line.l_008_weight_UOM.lower() in tons:
            total_weight += line.l_002_qty * line.l_009_weight_per_each * 1000
        total_lines_cnt += line.l_002_qty
        total_cubic_meter += pallet_cubic_meter

        message_lines += f"""
                <tr>
                  <td style='border: 1px solid black;'>{line.l_001_type_of_packaging}</td>
                  <td style='border: 1px solid black;'>{line.l_003_item}</td>
                  <td style='border: 1px solid black;'>{line.l_002_qty}</td>
                  <td style='border: 1px solid black;'>{line.l_004_dim_UOM}</td>
                  <td style='border: 1px solid black;'>{line.l_005_dim_length}</td>
                  <td style='border: 1px solid black;'>{line.l_006_dim_width}</td>
                  <td style='border: 1px solid black;'>{line.l_007_dim_height}</td>
                  <td style='border: 1px solid black;'>{round(pallet_cubic_meter, 3)} (m3)</td>
                  <td style='border: 1px solid black;'>{round(line.l_002_qty * line.l_009_weight_per_each, 3)} ({line.l_008_weight_UOM})</td>
                </tr>
        """

    subject = f"The bid from Deliver-ME is ended!"

    notes = quote.notes
    pickup_timestamp = dme_time_lib.convert_to_AU_SYDNEY_tz(quote.pickup_timestamp)
    delivery_timestamp = dme_time_lib.convert_to_AU_SYDNEY_tz(quote.delivery_timestamp)
    client_mu_1_minimum_values = quote.client_mu_1_minimum_values
    message = f"""
        <html>
        <head></head>
        <body>
            <p>Dear {dme_token.vx_freight_provider}</p>
            <div style='height:1px;'></div>
            <p>Thank you for you quote. Please find our booking confirmation as per the details below.</p>
            <div style='height:1px;'></div>
            <div style='margin-top: 20px;'>   
                <strong style='width:200px;float:left;'>Collection Date and Time: </strong>
                <input style='width:250px' type='text' disabled='disabled' value='{pickup_timestamp.strftime("%d-%m-%Y %H:%M")}' /></span><br />
            </div>
            <div style='margin-top: 20px;'>   
                <strong style='width:200px;float:left;'>Delivery Date and Time: </strong>
                <input style='width:250px' type='text' disabled='disabled' value='{delivery_timestamp.strftime("%d-%m-%Y %H:%M")}' /><br />
            </div>
            <div style='margin-top: 20px;'>   
                <strong style='width:200px;float:left;'>Total Price ex GST: </strong>
                <input style='width:250px' type='text' disabled='disabled' value='{client_mu_1_minimum_values}' /><br />
            </div>
            <div style='margin-top: 20px;'>   
                <strong style='width:200px;float:left;'>Anything we should know?: </strong>
                <input style='width:250px;height: 100px;' type='text' disabled='disabled' value='{notes}' /><br />
            </div>

            <p style='text-align:center;margin:20px 0'>
                <a
                    style='padding:10px 20px;background: #2e6da4;color:white;border-radius:4px;text-decoration:none;'
                    href="{os.environ["WEB_SITE_URL"]}/confirm/{dme_token.token}"
                >
                    Confirm Booking Acceptance and Timing
                </a>
            </p>

            <h2>Main Info: </h2>
            <!--<div>
                <strong>Client Name: </strong><span>{booking.b_client_name}</span><br />
                <strong>Client Order Number: </strong><span>{booking.b_client_order_num}</span><br />
                <strong>Client Sales Invoice Number: </strong><span>{booking.b_client_sales_inv_num}</span><br />
                <strong>Despatch Date: </strong><span>{booking.puPickUpAvailFrom_Date}</span><br />
            </div>-->
            <div style='display:flex;'>
              <div>
                <h3 style='color: deepskyblue'>Pickup From: </h3>
                <div>
                    <strong>Entity Name: </strong><span>{booking.puCompany}</span><br />
                    <strong>Street 1: </strong><span>{booking.pu_Address_Street_1}</span><br />
                    <strong>Street 2: </strong><span>{booking.pu_Address_street_2}</span><br />
                    <strong>Suburb: </strong><span>{booking.pu_Address_Suburb}</span><br />
                    <strong>State: </strong><span>{booking.pu_Address_State}</span><br />
                    <strong>PostalCode: </strong><span>{booking.pu_Address_PostalCode}</span><br />
                    <strong>Country: </strong><span>{booking.pu_Address_Country}</span><br />
                    <strong>Contact: </strong><span>{booking.pu_Contact_F_L_Name}</span><br />
                    <strong>Email: </strong><span>{booking.pu_Email}</span><br />
                    <strong>Phone: </strong><span>{booking.pu_Phone_Main}</span><br />
                </div>
              </div>
              <div  style='margin-left:100px;'>
                <h3 style='color: deepskyblue'>Deliver To: </h3>
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
                    style='padding:10px 20px;background: #2e6da4;color:white;border-radius:4px;text-decoration:none;'
                    href="{os.environ["WEB_SITE_URL"]}/confirm/{dme_token.token}"
                >
                    Confirm Booking Acceptance and Timing
                </a>
            </p>

        </body>
        </html>
    """

    send_email([dme_token.email], [], [], subject, message, mime_type="html")
    logger.info(f"{LOG_ID} Sent email - {dme_token.vx_freight_provider}")


@background
def send_email_confirmed(booking, bok_lines, dme_token, quote):
    from api.clients.ariston_wire.constants import ARISTON_WIRE_CS_EMAILS

    LOG_ID = "[AW Confirmed Email]"
    subject = f"Order confirmation from {dme_token.vx_freight_provider} for {booking.b_client_order_num} to {booking.de_To_Address_Suburb}"

    total_weight = 0
    total_lines_cnt = 0
    total_cubic_meter = 0
    message_lines = ""

    for line in bok_lines:
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

    message = f"""
        <html>
        <head></head>
        <body>
            <p>Dear Arison Wire CS,</p>
            <div style='height:1px;'></div>
            <p>Your order({booking.b_client_order_num}) has been confirmed by {dme_token.vx_freight_provider}.</p>
            <div style='height:1px;'></div>
            <p>Thank you</p>

            <h2>Main Info: </h2>
            <div>
                <strong>Client Name: </strong><span>{booking.b_client_name}</span><br />
                <strong>Client Order Number: </strong><span>{booking.b_client_order_num}</span><br />
                <strong>Client Sales Invoice Number: </strong><span>{booking.b_client_sales_inv_num}</span><br />
                <strong>Despatch Date: </strong><span>{booking.puPickUpAvailFrom_Date}</span><br />
            </div>
            <div style='display:flex;'>
              <div>
                <h3 style='color: deepskyblue'>Pickup From: </h3>
                <div>
                    <strong>Entity Name: </strong><span>{booking.puCompany}</span><br />
                    <strong>Street 1: </strong><span>{booking.pu_Address_Street_1}</span><br />
                    <strong>Street 2: </strong><span>{booking.pu_Address_street_2}</span><br />
                    <strong>Suburb: </strong><span>{booking.pu_Address_Suburb}</span><br />
                    <strong>State: </strong><span>{booking.pu_Address_State}</span><br />
                    <strong>PostalCode: </strong><span>{booking.pu_Address_PostalCode}</span><br />
                    <strong>Country: </strong><span>{booking.pu_Address_Country}</span><br />
                    <strong>Contact: </strong><span>{booking.pu_Contact_F_L_Name}</span><br />
                    <strong>Email: </strong><span>{booking.pu_Email}</span><br />
                    <strong>Phone: </strong><span>{booking.pu_Phone_Main}</span><br />
                </div>
              </div>
              <div  style='margin-left:100px;'>
                <h3 style='color: deepskyblue'>Deliver To: </h3>
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
                    href="{os.environ["WEB_SITE_URL"]}/booking?bookingId={booking.b_bookingID_Visual}"
                >
                    Click here to check on DME portal
                </a>
            </p>

            <p>For button link to work, please be sure you are logged into dme before clicking.</p>
        </body>
        </html>
    """

    send_email(ARISTON_WIRE_CS_EMAILS, [], [], subject, message, mime_type="html")
    logger.info(f"{LOG_ID} Sent email - {dme_token.vx_freight_provider}")
