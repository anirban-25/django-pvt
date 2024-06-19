import logging

from api.models import DME_SMS_Templates, DME_Options
from api.outputs.sms import send_sms

logger = logging.getLogger(__name__)


def send_status_update_sms(
    phone_number,
    sender,
    client,
    bookingNo,
    trackingNo,
    category,
    eta,
    status_url,
    de_company,
    de_address,
    delivered_time,
):
    LOG_ID = "[SMS - STATUS UPDATE]"

    if not category in ["Transit", "On Board for Delivery", "Complete"]:
        return

    option = DME_Options.objects.get(option_name="send_sms_to_customer")
    if option.option_value == 0:
        logger.info(f"{LOG_ID} Disabled!")
        return

    logger.info(
        f"{LOG_ID} BookingID: {bookingNo}, PhoneNumber: {phone_number}, Category: {category}"
    )

    if category == "Transit":
        template = DME_SMS_Templates.objects.get(smsName="Status Update - Transit")
    elif category == "On Board for Delivery":
        template = DME_SMS_Templates.objects.get(
            smsName="Status Update - On Board for Delivery"
        )
    elif category == "Complete":
        template = DME_SMS_Templates.objects.get(smsName="Status Update - Delivered")

    client_name = ""
    if client == "Jason L":
        client_name = "Jason.l"
    elif client == "Plum Products Australia Ltd":
        client_name = "Plum Play"
    else:
        client_name = client

    if template:
        smsMessage = template.smsMessage
        message = smsMessage.format(
            USERNAME=sender,
            CLIENT_NAME=client_name,
            BOOKING_NO=bookingNo,
            TRACKING_NO=trackingNo,
            ETA=eta,
            TRACKING_URL=status_url,
            DELIVER_TO_COMPANY=de_company,
            DELIVER_TO_ADDRESS=de_address,
            DELIVERED_TIME=delivered_time,
        )

        send_sms(phone_number, message)
