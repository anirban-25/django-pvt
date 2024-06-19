from twilio.rest import Client

from django.conf import settings


def send_sms(phone_number, message):
    client = Client(settings.TWILIO["APP_SID"], settings.TWILIO["TOKEN"])
    msg = client.messages.create(
        to=phone_number, from_=settings.TWILIO["NUMBER"], body=message
    )
