import os
import logging
from api.outputs.email import send_email
from api.helpers import cubic
from api.common.thread import background

logger = logging.getLogger(__name__)

@background
def send_email_booked(booking, booking_lines):
    from api.clients.bsd.constants import BSD_CS_EMAILS

    LOG_ID = "[BSD Booked Email]"
    subject = f"Booked from {booking.vx_freight_provider} for {booking.b_client_order_num} to {booking.de_To_Address_Suburb}"

    total_weight = 0
    total_lines_cnt = 0
    total_cubic_meter = 0
    message_lines = ""

    for line in booking_lines:
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
            <p>Dear Bathroom Sales Direct,</p>
            <div style='height:1px;'></div>
            <p>Your order({booking.b_client_order_num}) has been booked by {booking.vx_freight_provider}.</p>
            <div style='height:1px;'></div>
            <p>Thank you</p>

            <h2>Main Info: </h2>
            <div>
                <strong>Booking No: </strong><span>{booking.b_bookingID_Visual}</span><br />
                <strong>Consignment No: </strong><span>{booking.v_FPBookingNumber}</span><br />
                <strong>Booking Date: </strong><span>{booking.b_dateBookedDate}</span><br />
                <strong>Client Name: </strong><span>{booking.b_client_name}</span><br />
                <strong>Client Order Number: </strong><span>{booking.b_client_order_num}</span><br />
                <strong>Client Sales Invoice Number: </strong><span>{booking.b_client_sales_inv_num}</span><br />
                <strong>Despatch Date: </strong><span>{booking.puPickUpAvailFrom_Date}</span><br />
                <strong>Booked $: </strong><span>{format(round(booking.inv_booked_quoted if booking.inv_booked_quoted else 0, 2), ".2f")}</span><br />
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
    
    CC_EMAILS = [
        "jeann@deliver-me.com.au",
        "petew@deliver-me.com.au",
        "bookings@deliver-me.com.au",
        "stephenm@deliver-me.com.au",
        "dipendrac@deliver-me.com.au",
    ]
    send_email(BSD_CS_EMAILS, CC_EMAILS, [], subject, message, mime_type="html")
    logger.info(f"{LOG_ID} Sent email - {booking.vx_freight_provider}")
