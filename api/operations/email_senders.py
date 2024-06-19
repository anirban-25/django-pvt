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


def send_booking_status_email(bookingId, emailName, sender):
    """
    When 'Tempo Pty Ltd', 'Reworx' bookings status is updated
    """
    from api.common.time import convert_to_AU_SYDNEY_tz

    LOG_ID = "[Tempo Reworx Status Email]"

    if settings.ENV in ["local", "dev"]:
        logger.info("Email trigger is ignored on LOCAL & DEV.")
        return

    option = DME_Options.objects.get(option_name="send_email_to_customer")
    if option.option_value == 0:
        logger.info(f"{LOG_ID} Disabled!")
        return

    templates = DME_Email_Templates.objects.filter(emailName=emailName)
    booking = Bookings.objects.get(pk=int(bookingId))

    # Works for only `Tempo Pty Ltd` | `Big W` | `Reworx`
    if not booking.kf_client_id in [
        "37C19636-C5F9-424D-AD17-05A056A8FBDB",
        "feb8c98f-3156-4241-8413-86c7af99bf4e",
        "d69f550a-9327-4ff9-bc8f-242dfca00f7e",
    ]:
        return

    if booking.api_booking_quote:
        booking_lines = Booking_lines.objects.filter(
            fk_booking_id=booking.pk_booking_id,
            packed_status=booking.api_booking_quote.packed_status,
        ).order_by("-z_createdTimeStamp")
    else:
        booking_lines = Booking_lines.objects.filter(
            fk_booking_id=booking.pk_booking_id,
            packed_status=Booking_lines.SCANNED_PACK,
        ).order_by("-z_createdTimeStamp")

        if not booking_lines.exists():
            booking_lines = Booking_lines.objects.filter(
                fk_booking_id=booking.pk_booking_id,
                packed_status=Booking_lines.ORIGINAL,
            ).order_by("-z_createdTimeStamp")

    booking_lines_data = Booking_lines_data.objects.filter(
        fk_booking_id=booking.pk_booking_id
    ).order_by("-z_createdTimeStamp")

    gaps = []
    refs = []
    for lines_data in booking_lines_data:
        if lines_data.gap_ra:
            gaps.append(lines_data.gap_ra)

        if lines_data.clientRefNumber:
            refs.append(lines_data.clientRefNumber)

    totalQty = 0
    totalWeight = 0
    for booking_line in booking_lines:
        totalQty += booking_line.e_qty
        totalWeight += booking_line.e_qty * booking_line.e_weightPerEach

    files = []
    DMEBOOKINGNUMBER = booking.b_bookingID_Visual

    BOOKEDDATE = ""
    if booking.b_dateBookedDate:
        BOOKEDDATE = convert_to_AU_SYDNEY_tz(booking.b_dateBookedDate)
        BOOKEDDATE = BOOKEDDATE.strftime("%d/%m/%Y %H:%M")

    DELIVERYDATE = ""
    if booking.s_21_Actual_Delivery_TimeStamp:
        DELIVERYDATE = convert_to_AU_SYDNEY_tz(booking.s_21_Actual_Delivery_TimeStamp)
        DELIVERYDATE = DELIVERYDATE.strftime("%d/%m/%Y %H:%M")

    TOADDRESSCONTACT = f" {booking.pu_Contact_F_L_Name}"
    FUTILEREASON = booking.vx_futile_Booking_Notes
    BOOKING_NUMBER = booking.b_bookingID_Visual
    FREIGHT_PROVIDER = booking.vx_freight_provider
    FREIGHT_PROVIDER_BOOKING_NUMBER = booking.v_FPBookingNumber
    REFERENCE_NUMBER = booking.b_clientReference_RA_Numbers
    TOT_PACKAGES = totalQty
    TOT_CUBIC_WEIGHT = totalWeight
    SERVICE_TYPE = ""

    etd = None
    uom = None

    try:
        etd, uom = booking.get_etd()

        if etd:
            SERVICE_TYPE = f"{etd} {uom}"
    except:
        pass

    SERVICE = booking.vx_serviceName
    LATEST_PICKUP_TIME = ""
    if booking.s_05_Latest_Pick_Up_Date_TimeSet:
        LATEST_PICKUP_TIME = convert_to_AU_SYDNEY_tz(
            booking.s_05_Latest_Pick_Up_Date_TimeSet
        )
        LATEST_PICKUP_TIME = LATEST_PICKUP_TIME.strftime("%d/%m/%Y %H:%M")

    LATEST_DELIVERY_TIME = ""
    if booking.s_06_Latest_Delivery_Date_TimeSet:
        LATEST_DELIVERY_TIME = convert_to_AU_SYDNEY_tz(
            booking.s_06_Latest_Delivery_Date_TimeSet
        )
        LATEST_DELIVERY_TIME = LATEST_DELIVERY_TIME.strftime("%d/%m/%Y %H:%M")

    DELIVERY_ETA = booking.z_calculated_ETA
    INSTRUCTIONS = booking.b_handling_Instructions

    PICKUP_CONTACT = f"{booking.pu_Contact_F_L_Name} - {booking.pu_Phone_Main}"
    PICKUP_SUBURB = f"{booking.puCompany}, {booking.pu_Address_Suburb}"

    PICKUP_INSTRUCTIONS = ""
    if booking.pu_pickup_instructions_address:
        PICKUP_INSTRUCTIONS = f"{booking.pu_pickup_instructions_address}"
    if booking.pu_PickUp_Instructions_Contact:
        PICKUP_INSTRUCTIONS += f" {booking.pu_PickUp_Instructions_Contact}"

    PICKUP_OPERATING_HOURS = booking.pu_Operting_Hours
    DELIVERY_CONTACT = f"{booking.de_to_Contact_F_LName} - {booking.de_to_Phone_Main}"
    DELIVERY_SUBURB = f"{booking.deToCompanyName}, {booking.de_To_Address_Suburb}"

    DELIVERY_INSTRUCTIONS = ""
    if booking.de_to_PickUp_Instructions_Address:
        DELIVERY_INSTRUCTIONS = f"{booking.de_to_PickUp_Instructions_Address}"
    if booking.de_to_Pick_Up_Instructions_Contact:
        DELIVERY_INSTRUCTIONS += f" {booking.de_to_Pick_Up_Instructions_Contact}"

    DELIVERY_OPERATING_HOURS = booking.de_Operating_Hours
    ATTENTION_NOTES = booking.DME_Notes

    if emailName == "General Booking":
        emailVarList = {
            "TOADDRESSCONTACT": TOADDRESSCONTACT,
            "FUTILEREASON": FUTILEREASON,
            "BOOKING_NUMBER": BOOKING_NUMBER,
            "FREIGHT_PROVIDER": FREIGHT_PROVIDER,
            "FREIGHT_PROVIDER_BOOKING_NUMBER": FREIGHT_PROVIDER_BOOKING_NUMBER,
            "REFERENCE_NUMBER": ", ".join(refs),
            "TOT_PACKAGES": TOT_PACKAGES,
            "TOT_CUBIC_WEIGHT": TOT_CUBIC_WEIGHT,
            "SERVICE_TYPE": SERVICE_TYPE,
            "SERVICE": SERVICE,
            "LATEST_PICKUP_TIME": LATEST_PICKUP_TIME,
            "LATEST_DELIVERY_TIME": LATEST_DELIVERY_TIME,
            "DELIVERY_ETA": DELIVERY_ETA,
            "INSTRUCTIONS": INSTRUCTIONS,
            "PICKUP_CONTACT": PICKUP_CONTACT,
            "PICKUP_SUBURB": PICKUP_SUBURB,
            "PICKUP_INSTRUCTIONS": PICKUP_INSTRUCTIONS,
            "PICKUP_OPERATING_HOURS": PICKUP_OPERATING_HOURS,
            "DELIVERY_CONTACT": DELIVERY_CONTACT,
            "DELIVERY_SUBURB": DELIVERY_SUBURB,
            "DELIVERY_INSTRUCTIONS": DELIVERY_INSTRUCTIONS,
            "DELIVERY_OPERATING_HOURS": DELIVERY_OPERATING_HOURS,
            "ATTENTION_NOTES": ATTENTION_NOTES,
            "BODYREPEAT": "",
        }

        if booking.z_label_url is not None and len(booking.z_label_url) is not 0:
            if settings.ENV == "local":
                files.append("./static/pdfs/" + booking.z_label_url)
            else:
                files.append("/opt/s3_public/pdfs/" + booking.z_label_url)
    elif emailName == "Return Booking":
        emailVarList = {
            "TOADDRESSCONTACT": TOADDRESSCONTACT,
            "FUTILEREASON": FUTILEREASON,
            "BOOKING_NUMBER": BOOKING_NUMBER,
            "FREIGHT_PROVIDER": FREIGHT_PROVIDER,
            "FREIGHT_PROVIDER_BOOKING_NUMBER": FREIGHT_PROVIDER_BOOKING_NUMBER,
            "REFERENCE_NUMBER": ", ".join(refs),
            "TOT_PACKAGES": TOT_PACKAGES,
            "TOT_CUBIC_WEIGHT": TOT_CUBIC_WEIGHT,
            "SERVICE_TYPE": SERVICE_TYPE,
            "SERVICE": SERVICE,
            "LATEST_PICKUP_TIME": LATEST_PICKUP_TIME,
            "LATEST_DELIVERY_TIME": LATEST_DELIVERY_TIME,
            "DELIVERY_ETA": DELIVERY_ETA,
            "INSTRUCTIONS": INSTRUCTIONS,
            "PICKUP_CONTACT": PICKUP_CONTACT,
            "PICKUP_SUBURB": PICKUP_SUBURB,
            "PICKUP_INSTRUCTIONS": PICKUP_INSTRUCTIONS,
            "PICKUP_OPERATING_HOURS": PICKUP_OPERATING_HOURS,
            "DELIVERY_CONTACT": DELIVERY_CONTACT,
            "DELIVERY_SUBURB": DELIVERY_SUBURB,
            "DELIVERY_INSTRUCTIONS": DELIVERY_INSTRUCTIONS,
            "DELIVERY_OPERATING_HOURS": DELIVERY_OPERATING_HOURS,
            "ATTENTION_NOTES": ATTENTION_NOTES,
            "BODYREPEAT": "",
        }

        if booking.z_label_url is not None and len(booking.z_label_url) is not 0:
            if settings.ENV == "local":
                files.append("./static/pdfs/" + booking.z_label_url)
            else:
                files.append("/opt/s3_public/pdfs/" + booking.z_label_url)
    elif emailName == "POD":
        emailVarList = {
            "BOOKEDDATE": BOOKEDDATE,
            "DELIVERYDATE": DELIVERYDATE,
            "DMEBOOKINGNUMBER": DMEBOOKINGNUMBER,
            "TOADDRESSCONTACT": TOADDRESSCONTACT,
            "FUTILEREASON": FUTILEREASON,
            "BOOKING_NUMBER": BOOKING_NUMBER,
            "FREIGHT_PROVIDER": FREIGHT_PROVIDER,
            "FREIGHT_PROVIDER_BOOKING_NUMBER": FREIGHT_PROVIDER_BOOKING_NUMBER,
            "REFERENCE_NUMBER": ", ".join(refs),
            "TOT_PACKAGES": TOT_PACKAGES,
            "TOT_CUBIC_WEIGHT": TOT_CUBIC_WEIGHT,
            "SERVICE_TYPE": SERVICE_TYPE,
            "SERVICE": SERVICE,
            "LATEST_PICKUP_TIME": LATEST_PICKUP_TIME,
            "LATEST_DELIVERY_TIME": LATEST_DELIVERY_TIME,
            "DELIVERY_ETA": DELIVERY_ETA,
            "INSTRUCTIONS": INSTRUCTIONS,
            "PICKUP_CONTACT": PICKUP_CONTACT,
            "PICKUP_SUBURB": PICKUP_SUBURB,
            "PICKUP_INSTRUCTIONS": PICKUP_INSTRUCTIONS,
            "PICKUP_OPERATING_HOURS": PICKUP_OPERATING_HOURS,
            "DELIVERY_CONTACT": DELIVERY_CONTACT,
            "DELIVERY_SUBURB": DELIVERY_SUBURB,
            "DELIVERY_INSTRUCTIONS": DELIVERY_INSTRUCTIONS,
            "DELIVERY_OPERATING_HOURS": DELIVERY_OPERATING_HOURS,
            "ATTENTION_NOTES": ATTENTION_NOTES,
            "BODYREPEAT": "",
        }

        if booking.z_pod_url is not None and len(booking.z_pod_url) is not 0:
            if settings.ENV == "local":
                files.append("./static/imgs/" + booking.z_pod_url)
            else:
                files.append("/opt/s3_public/imgs/" + booking.z_pod_url)
    elif emailName == "Futile Pickup":
        emailVarList = {
            "TOADDRESSCONTACT": TOADDRESSCONTACT,
            "FUTILEREASON": FUTILEREASON,
            "BOOKING_NUMBER": BOOKING_NUMBER,
            "FREIGHT_PROVIDER": FREIGHT_PROVIDER,
            "FREIGHT_PROVIDER_BOOKING_NUMBER": FREIGHT_PROVIDER_BOOKING_NUMBER,
            "REFERENCE_NUMBER": ", ".join(refs),
            "TOT_PACKAGES": TOT_PACKAGES,
            "TOT_CUBIC_WEIGHT": TOT_CUBIC_WEIGHT,
            "SERVICE_TYPE": SERVICE_TYPE,
            "SERVICE": SERVICE,
            "LATEST_PICKUP_TIME": LATEST_PICKUP_TIME,
            "LATEST_DELIVERY_TIME": LATEST_DELIVERY_TIME,
            "DELIVERY_ETA": DELIVERY_ETA,
            "INSTRUCTIONS": INSTRUCTIONS,
            "PICKUP_CONTACT": PICKUP_CONTACT,
            "PICKUP_SUBURB": PICKUP_SUBURB,
            "PICKUP_INSTRUCTIONS": PICKUP_INSTRUCTIONS,
            "PICKUP_OPERATING_HOURS": PICKUP_OPERATING_HOURS,
            "DELIVERY_CONTACT": DELIVERY_CONTACT,
            "DELIVERY_SUBURB": DELIVERY_SUBURB,
            "DELIVERY_INSTRUCTIONS": DELIVERY_INSTRUCTIONS,
            "DELIVERY_OPERATING_HOURS": DELIVERY_OPERATING_HOURS,
            "ATTENTION_NOTES": ATTENTION_NOTES,
            "BODYREPEAT": "",
        }

        if booking.z_label_url is not None and len(booking.z_label_url) is not 0:
            if settings.ENV == "local":
                files.append("./static/pdfs/" + booking.z_label_url)
            else:
                files.append("/opt/s3_public/pdfs/" + booking.z_label_url)
    elif emailName == "Unpacked Return Booking":
        emailVarList = {
            "TOADDRESSCONTACT": TOADDRESSCONTACT,
            "FUTILEREASON": FUTILEREASON,
            "BOOKING_NUMBER": BOOKING_NUMBER,
            "FREIGHT_PROVIDER": FREIGHT_PROVIDER,
            "FREIGHT_PROVIDER_BOOKING_NUMBER": FREIGHT_PROVIDER_BOOKING_NUMBER,
            "REFERENCE_NUMBER": ", ".join(refs),
            "TOT_PACKAGES": TOT_PACKAGES,
            "TOT_CUBIC_WEIGHT": TOT_CUBIC_WEIGHT,
            "SERVICE_TYPE": SERVICE_TYPE,
            "SERVICE": SERVICE,
            "LATEST_PICKUP_TIME": LATEST_PICKUP_TIME,
            "LATEST_DELIVERY_TIME": LATEST_DELIVERY_TIME,
            "DELIVERY_ETA": DELIVERY_ETA,
            "INSTRUCTIONS": INSTRUCTIONS,
            "PICKUP_CONTACT": PICKUP_CONTACT,
            "PICKUP_SUBURB": PICKUP_SUBURB,
            "PICKUP_INSTRUCTIONS": PICKUP_INSTRUCTIONS,
            "PICKUP_OPERATING_HOURS": PICKUP_OPERATING_HOURS,
            "DELIVERY_CONTACT": DELIVERY_CONTACT,
            "DELIVERY_SUBURB": DELIVERY_SUBURB,
            "DELIVERY_INSTRUCTIONS": DELIVERY_INSTRUCTIONS,
            "DELIVERY_OPERATING_HOURS": DELIVERY_OPERATING_HOURS,
            "ATTENTION_NOTES": ATTENTION_NOTES,
            "BODYREPEAT": "",
        }

        if booking.z_label_url is not None and len(booking.z_label_url) is not 0:
            if settings.ENV == "local":
                files.append("./static/pdfs/" + booking.z_label_url)
            else:
                files.append("/opt/s3_public/pdfs/" + booking.z_label_url)
    html = ""
    for template in templates:
        emailBody = template.emailBody

        for idx, booking_line in enumerate(booking_lines):
            descriptions = []
            modelNumbers = []
            gaps = []
            refs = []

            booking_lines_data = Booking_lines_data.objects.filter(
                fk_booking_lines_id=booking_line.pk_booking_lines_id
            )

            for line_data in booking_lines_data:
                if line_data.itemDescription:
                    descriptions.append(line_data.itemDescription)

                if line_data.gap_ra:
                    gaps.append(line_data.gap_ra)

                if line_data.clientRefNumber:
                    refs.append(line_data.clientRefNumber)

                if line_data.modelNumber:
                    modelNumbers.append(line_data.modelNumber)

            REF = ", ".join(refs)
            RA = ", ".join(gaps)
            DESCRIPTION = ", ".join(descriptions)
            PRODUCT = ", ".join(modelNumbers)
            QTY = str(booking_line.e_qty) if booking_line.e_qty else ""
            TYPE = (
                str(booking_line.e_type_of_packaging)
                if booking_line.e_type_of_packaging
                else ""
            )
            LENGTH = (
                (str(booking_line.e_dimLength) if booking_line.e_dimLength else "")
                + " X "
                + (str(booking_line.e_dimWidth) if booking_line.e_dimWidth else "")
                + " X "
                + (str(booking_line.e_dimHeight) if booking_line.e_dimHeight else "")
                + " "
                + (str(booking_line.e_dimUOM) if booking_line.e_dimUOM else "")
            )
            WEIGHT = (
                (
                    str(booking_line.e_Total_KG_weight)
                    if booking_line.e_Total_KG_weight
                    else ""
                )
                + " "
                + (str(booking_line.e_weightUOM) if booking_line.e_weightUOM else "")
            )

            if idx % 2 == 0:
                emailBodyRepeatEven = (
                    str(template.emailBodyRepeatEven)
                    if template.emailBodyRepeatEven
                    else ""
                )
                emailVarListEven = {
                    "PRODUCT": PRODUCT,
                    "RA": RA,
                    "DESCRIPTION": DESCRIPTION,
                    "QTY": QTY,
                    "REF": REF,
                    "TYPE": TYPE,
                    "LENGTH": LENGTH,
                    "WEIGHT": WEIGHT,
                }

                for key in emailVarListEven.keys():
                    emailBodyRepeatEven = emailBodyRepeatEven.replace(
                        "{" + str(key) + "}",
                        str(emailVarListEven[key]) if emailVarListEven[key] else "",
                    )

                emailVarList["BODYREPEAT"] += emailBodyRepeatEven
            else:
                emailBodyRepeatOdd = (
                    str(template.emailBodyRepeatOdd)
                    if template.emailBodyRepeatOdd
                    else ""
                )
                emailVarListOdd = {
                    "PRODUCT": PRODUCT,
                    "RA": RA,
                    "DESCRIPTION": DESCRIPTION,
                    "QTY": QTY,
                    "REF": REF,
                    "TYPE": TYPE,
                    "LENGTH": LENGTH,
                    "WEIGHT": WEIGHT,
                }

                for key in emailVarListOdd.keys():
                    emailBodyRepeatOdd = emailBodyRepeatOdd.replace(
                        "{" + str(key) + "}",
                        str(emailVarListOdd[key]) if emailVarListOdd[key] else "",
                    )

                emailVarList["BODYREPEAT"] += emailBodyRepeatOdd

        for key in emailVarList.keys():
            emailBody = emailBody.replace(
                "{" + str(key) + "}",
                str(emailVarList[key]) if emailVarList[key] else "",
            )

        html += emailBody
        emailVarList["BODYREPEAT"] = ""

    # TEST Usage
    # fp1 = open("dme_booking_email_" + emailName + ".html", "w+")
    # fp1.write(html)

    cc_emails = []

    if emailName == "General Booking":
        subject = f"{booking.b_client_name} Freight Booking - DME#{booking.b_bookingID_Visual} / Freight Provider# {booking.v_FPBookingNumber}"
    else:
        subject = f"{booking.b_client_name} {emailName} - DME#{booking.b_bookingID_Visual} / Freight Provider# {booking.v_FPBookingNumber}"
    mime_type = "html"

    if settings.ENV in ["local", "dev"]:
        to_emails = [
            "bookings@deliver-me.com.au",
            "goldj@deliver-me.com.au",
        ]
        subject = f"FROM TEST SERVER - {subject}"
    else:
        to_emails = ["bookings@deliver-me.com.au"]

        if booking.pu_Email:
            to_emails.append(booking.pu_Email)
        if booking.de_Email:
            cc_emails.append(booking.de_Email)
        if booking.pu_email_Group:
            cc_emails = cc_emails + booking.pu_email_Group.split(",")
        if booking.de_Email_Group_Emails:
            cc_emails = cc_emails + booking.de_Email_Group_Emails.split(",")
        if booking.booking_Created_For_Email:
            cc_emails.append(booking.booking_Created_For_Email)

        cc_emails.append("dev.deliverme@gmail.com")

    send_email(to_emails, cc_emails, [], subject, html, files, mime_type)

    EmailLogs.objects.create(
        booking_id=bookingId,
        emailName=emailName,
        to_emails=COMMASPACE.join(to_emails),
        cc_emails=COMMASPACE.join(cc_emails),
        z_createdTimeStamp=str(datetime.now()),
        z_createdByAccount=sender,
    )


def send_status_update_email(
    booking, category, eta, sender, status_url, client_status_email=None
):
    """
    When 'Plum Products Australia Ltd' bookings status is updated
    """
    from api.fp_apis.utils import get_status_time_from_category
    from api.common.time import convert_to_AU_SYDNEY_tz

    LOG_ID = "[STATUS UPDATE EMAIL]"
    logger.info(
        f"{LOG_ID} BookingID: {booking.b_bookingID_Visual}, OrderNum: {booking.b_client_order_num}, New Status: {booking.b_status}"
    )

    option = DME_Options.objects.get(option_name="send_email_to_customer")
    if option.option_value == 0:
        logger.info(f"{LOG_ID} Disabled!")
        return

    b_status = booking.b_status
    quote = booking.api_booking_quote

    status_histories = Dme_status_history.objects.filter(
        fk_booking_id=booking.pk_booking_id
    ).order_by("-z_createdTimeStamp")

    last_updated = ""
    if status_histories and status_histories.first().event_time_stamp:
        last_updated = convert_to_AU_SYDNEY_tz(
            status_histories.first().event_time_stamp
        ).strftime("%d/%m/%Y %H:%M")

    last_milestone = "Delivered"
    if b_status in [
        "Picking",
        "Ready for Booking",
        "Ready for Despatch",
        "Booked",
        "Futile Pickup",
        "Pickup Rebooked",
    ]:
        step = 2
    elif b_status in [
        "In Transit",
        "Partial In Transit",
        "On-Forwarded",
        "Delivery Rebooked",
        "Delivery Delayed",
    ]:
        step = 3
    elif b_status == "On Board for Delivery":
        step = 4
    elif b_status in [
        "Lost In Transit",
        "Damaged",
        "Returning",
        "Returned",
        "Cancelled",
        "Closed",
        "Delivered",
        "Collected",
        "Partially Delivered",
    ]:
        step = 5
        last_milestone = b_status if b_status != "Collected" else "Delivered"
    else:
        step = 1
        b_status = "Processing"

    steps = [
        "Processing",
        "Booked",
        "Transit",
        "On Board for Delivery",
        "Complete",
    ]

    try:
        logo_url = DME_clients.objects.get(
            dme_account_num=booking.kf_client_id
        ).logo_url
    except Exception as e:
        logger.error(f"Client logo url error: {str(e)}")
        logo_url = None

    timestamps = []
    for index, item in enumerate(steps):
        if index == 0:
            timestamps.append(
                booking.z_CreatedTimestamp.strftime("%d/%m/%Y %H:%M")
                if booking and booking.z_CreatedTimestamp
                else ""
            )
        elif index >= step:
            timestamps.append("")
        else:
            if category == "Complete" and index == 4:
                timestamps.append(
                    booking.s_21_Actual_Delivery_TimeStamp.strftime("%d/%m/%Y %H:%M")
                    if booking.s_21_Actual_Delivery_TimeStamp
                    else ""
                )
            else:
                category_datetime = get_status_time_from_category(
                    booking.pk_booking_id, item
                )
                timestamps.append(
                    category_datetime.strftime("%d/%m/%Y %H:%M")
                    if category_datetime
                    else ""
                )

    to_emails = []
    cc_emails = []

    templates = DME_Email_Templates.objects.filter(emailName="Status Update")
    emailVarList = {
        "STATUS": b_status,
        "FP_NAME": quote.freight_provider if quote and quote.freight_provider else "",
        "DE_TO_ADDRESS": f"{booking.de_to_Contact_F_LName}<br />{booking.de_To_Address_Street_1}{f' {booking.de_To_Address_Street_2}' if booking.de_To_Address_Street_2 else ''} {booking.de_To_Address_Suburb} {booking.de_To_Address_State} {booking.de_To_Address_Country} {booking.de_To_Address_PostalCode}",
        "LAST_UPDATED_TIME": last_updated,
        "IS_PROCESSING": "checked" if step >= 1 else "",
        "IS_BOOKED": "checked" if step >= 2 else "",
        "IS_TRANSIT": "checked" if step >= 3 else "",
        "IS_ON_BOARD": "checked" if step >= 4 else "",
        "IS_DELIVERED": "checked" if step >= 5 else "",
        "LAST_MILESTONE": last_milestone,
        "PROCESSING_TIME": timestamps[0],
        "BOOKING_TIME": timestamps[1],
        "TRANSIT_TIME": timestamps[2],
        "ON_BOARD_TIME": timestamps[3],
        "DELIVERED_TIME": timestamps[4],
        "CUSTOMER_NAME": booking.de_to_Contact_F_LName,
        "ORDER_NUMBER": booking.b_client_order_num,
        "SHIPMENT_NUMBER": booking.v_FPBookingNumber,
        "DME_NUMBER": booking.b_bookingID_Visual,
        "ETA": eta,
        "BODY_REPEAT": "",
        "NOTICE_DISPLAY": "none"
        if step == 5 and last_milestone == "Delivered"
        else "table-row",
    }

    booking_lines = Booking_lines.objects.filter(
        fk_booking_id=booking.pk_booking_id, e_item_type__isnull=False
    ).order_by("z_createdTimeStamp")

    # BSD
    if (
        booking.kf_client_id == "9e72da0f-77c3-4355-a5ce-70611ffd0bc8"
        and booking.api_booking_quote
    ):
        booking_lines = Booking_lines.objects.filter(
            fk_booking_id=booking.pk_booking_id,
            packed_status=booking.api_booking_quote.packed_status,
        ).order_by("z_createdTimeStamp")

    lines_data = []
    for booking_line in booking_lines:
        try:
            product = Client_Products.objects.get(
                child_model_number=booking_line.e_item_type
            ).description
        except Exception as e:
            logger.error(f"Client product doesn't exist: {e}")
            product = ""

        lines_data.append(
            {
                "PRODUCT_NAME": product,
                "ITEM_NUMBER": booking_line.e_item_type,
                "ITEM_DESCRIPTION": booking_line.e_item,
                "ITEM_QUANTITY": booking_line.e_qty,
            }
        )

    html = ""

    for template in templates:
        emailBody = template.emailBody
        emailBodyRepeatOdd = template.emailBodyRepeatOdd
        emailBodyRepeatEven = template.emailBodyRepeatEven
        emailVarList["USERNAME"] = sender
        emailVarList["BOOKIGNO"] = booking.b_client_order_num
        emailVarList["STATUS_URL"] = status_url
        emailVarList["DME_LOGO_URL"] = os.path.abspath("./static/assets/logos/dme.png")
        emailVarList["CLIENT_LOGO_URL"] = os.path.abspath(
            f"./static/assets/logos/{logo_url}"
        )

        body_repeat = ""
        for idx, line_data in enumerate(lines_data):
            if idx % 2 == 0:
                repeat_part = emailBodyRepeatEven
            else:
                repeat_part = emailBodyRepeatOdd

            for key in line_data:
                repeat_part = repeat_part.replace(
                    "{" + str(key) + "}",
                    str(line_data[key]) if line_data[key] else "",
                )
            body_repeat += repeat_part

        emailVarList["BODY_REPEAT"] = body_repeat

        for key in emailVarList.keys():
            emailBody = emailBody.replace(
                "{" + str(key) + "}",
                str(emailVarList[key]) if emailVarList[key] else "",
            )

        html += emailBody

    mime_type = "html"
    client_name = ""
    if booking.b_client_name == "Jason L":
        client_name = "Jason.l"
    elif booking.b_client_name == "Plum Products Australia Ltd":
        client_name = "Plum Play"
    else:
        client_name = booking.b_client_name

    subject = f"Your {client_name} Order status has been updated"

    to_emails = []

    if settings.ENV in ["local", "dev"]:
        to_emails = ["goldj@deliver-me.com.au"]
        subject = f"FROM TEST SERVER - {subject}"
    else:
        if client_status_email:
            to_emails.append(client_status_email)
        if booking.de_Email:
            to_emails.append(booking.de_Email)
        else:
            to_emails.append("bookings@deliver-me.com.au")

        if booking.pu_email_Group:
            cc_emails = cc_emails + booking.pu_email_Group.split(",")
        if booking.de_Email_Group_Emails:
            cc_emails = cc_emails + booking.de_Email_Group_Emails.split(",")
        if booking.booking_Created_For_Email:
            cc_emails.append(booking.booking_Created_For_Email)

        cc_emails.append("bookings@deliver-me.com.au")
        cc_emails.append("dev.deliverme@gmail.com")

        # Plum agent
        if booking.kf_client_id in ["461162D2-90C7-BF4E-A905-000000000004"]:
            cc_emails.append("JManiquis@plumproducts.com")
            cc_emails.append("aushelpdesk@plumproducts.com")

    send_email(
        to_emails,
        cc_emails,
        [],
        subject,
        html,
        [],
        mime_type,
    )

    EmailLogs.objects.create(
        booking_id=booking.pk,
        emailName="Status Update",
        to_emails=COMMASPACE.join(to_emails),
        cc_emails=COMMASPACE.join(cc_emails),
        z_createdTimeStamp=str(datetime.now()),
        z_createdByAccount=sender,
    )


def send_picking_slip_printed_email(
    b_client_order_num, b_092_booking_type, b_053_b_del_address_type
):
    """
    Only used for `Jason L` client's orders

    Example of subject:
    JasonL | 1034525- | picking slip printed
    """

    _b_client_order_num = (
        b_client_order_num if "-" in b_client_order_num else f"{b_client_order_num}-"
    )
    subject = f"JasonL | {_b_client_order_num} | {b_092_booking_type} | {b_053_b_del_address_type} | picking slip printed"
    message = f"JasonL | {_b_client_order_num} | {b_092_booking_type} | {b_053_b_del_address_type} | picking slip printed (Sent from DME platform)"
    to_emails = [
        "data.deliver-me@outlook.com",
        "dev.deliverme@gmail.com",
        "goldj@deliver-me.com.au",
    ]

    # if settings.ENV != "prod":
    #     to_emails.append("goldj@deliver-me.com.au")

    if settings.ENV in ["dev", "local"]:
        logger.info(
            f"@109 [send_picking_slip_printed_email] DEV MODE --- subject: {subject}"
        )
    else:
        send_email(to_emails, [], [], subject, message)


def send_email_missing_dims(client_name, order_num, lines_missing_dims):
    """
    Only used for `Jason L` client's orders

    When an Order has missing dims Lines, DME send this email.
    """
    subject = f"JasonL | {order_num}"
    message = f"Hi Regina, Order({order_num}) has lines with missing dims: {lines_missing_dims}"
    to_emails = ["dims@jasonl.com.au"]
    cc_emails = ["dev.deliverme@gmail.com"]
    send_email(to_emails, cc_emails, [], subject, message)


def send_email_missing_status(booking, fp_name, b_status_API):
    # Deactivated on 2022-02-16
    return None

    message = f"#818 FP name: {fp_name.upper()}, New status: {b_status_API}"
    logger.error(message)

    subject = f"Unknown Status From Freight Provider"
    message = (
        f"DME Booking ID: {booking.b_bookingID_Visual}\nOrderNumber: {booking.b_client_order_num}\n"
        + f"Freight Provider: {booking.vx_freight_provider.upper()}\nConsignmentNo: {booking.v_FPBookingNumber}\nUnknown Status: {b_status_API}\n\n\n"
        + f"Please reply to this email with the definition of the status code ASAP."
    )
    to_emails = ["bookings@deliver-me.com.au"]
    cc_emails = [
        "dev.deliverme@gmail.com",
    ]

    if fp_name.upper() == "ALLIED":
        to_emails.append("betty.petrov@alliedexpress.com.au")

    send_email(to_emails, cc_emails, [], subject, message)


def send_email_manual_book(booking):
    subject = f"URGENT | Manual Booking Required!"
    message = (
        f"Hi DME Customer Support,\n\nPlease manually book the following:\nBooking ID: {booking.b_bookingID_Visual}"
        + f"\nFreight Provider: {booking.vx_freight_provider.upper()}\nConsignmentNo: {booking.v_FPBookingNumber}\n\n"
        + f"Please use mentioned consignment number if possible, else update it on DME portal after booked.\nPlease reply to this email with name of resolver.\nBest\nDME_API"
    )

    if settings.ENV in ["local", "dev"]:
        to_emails = ["dev.deliverme@gmail.com"]
        cc_emails = ["goldj@deliver-me.com.au"]
    else:
        to_emails = ["bookings@deliver-me.com.au", "care@deliver-me.com.au"]
        cc_emails = ["dev.deliverme@gmail.com"]

    send_email(to_emails, cc_emails, [], subject, message)


def send_email_to_admins(subject, message):
    dme_option_4_email_to_admin = DME_Options.objects.filter(
        option_name="send_email_to_admins"
    ).first()

    if (
        dme_option_4_email_to_admin
        and int(dme_option_4_email_to_admin.option_value) == 1
    ):
        if settings.ENV in ["prod"]:
            to_emails = ["dev.deliverme@gmail.com", "bookings@deliver-me.com.au"]
        else:
            to_emails = ["dev.deliverme@gmail.com"]

        cc_emails = ["goldj@deliver-me.com.au", "darianw@deliver-me.com.au"]
        send_email(to_emails, cc_emails, [], subject, message)


def send_email_to_developers(subject, message):
    cc_emails = ["dev.deliverme@gmail.com", "goldj@deliver-me.com.au"]
    send_email(to_emails, cc_emails, [], subject, message)
