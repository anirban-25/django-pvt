import math, logging
from datetime import datetime, date

from django.conf import settings

from api.models import Dme_status_history, DME_clients
from api.clients.tempo.index import update_via_api as tempo_update_via_api
from api.clients.jason_l.index import update_via_api as jasonL_push_via_api
from api.operations.sms_senders import send_status_update_sms
from api.operations.email_senders import send_status_update_email
from api.helpers.phone import is_mobile, format_mobile
from api.operations.packing.booking import scanned_repack as booking_scanned_repack
from api.common import time as dme_time_lib
from api.common.thread import background
from api.utils import get_eta_pu_by, get_eta_de_by

logger = logging.getLogger(__name__)


@background
def notify_user_via_email_sms(booking, category_new, category_old, username):
    LOG_ID = "[EMAIL_SMS]"
    from api.helpers.etd import get_etd

    # Ignore unless Plum and BSD
    if not booking.kf_client_id in [
        "9e72da0f-77c3-4355-a5ce-70611ffd0bc8",
        "461162D2-90C7-BF4E-A905-000000000004",
    ]:
        return

    if (
        category_new
        in [
            "Transit",
            "On Board for Delivery",
            "Complete",
            "Futile",
            "Returned",
        ]
        and category_new != category_old
    ):
        url = f"{settings.WEB_SITE_URL}/status/{booking.b_client_booking_ref_num}/"

        s_06 = booking.get_s_06()
        eta = (
            dme_time_lib.convert_to_AU_SYDNEY_tz(s_06).strftime("%d/%m/%Y %H:%M")
            if s_06
            else ""
        )

        pu_name = booking.pu_Contact_F_L_Name or booking.puCompany
        de_name = booking.de_to_Contact_F_LName or booking.deToCompanyName
        de_company = booking.deToCompanyName
        de_address = f"{booking.de_To_Address_Street_1}{f' {booking.de_To_Address_Street_2}' or ''} {booking.de_To_Address_Suburb} {booking.de_To_Address_State} {booking.de_To_Address_Country} {booking.de_To_Address_PostalCode}"
        delivered_time = (
            dme_time_lib.convert_to_AU_SYDNEY_tz(
                booking.s_21_Actual_Delivery_TimeStamp
            ).strftime("%d/%m/%Y %H:%M")
            if booking.s_21_Actual_Delivery_TimeStamp
            else ""
        )

        email_sent = False
        if settings.ENV == "prod":
            try:
                client = DME_clients.objects.get(dme_account_num=booking.kf_client_id)
            except Exception as e:
                logger.info(f"Get client error: {str(e)}")
                client = None

            if client and client.status_send_flag:
                if client.status_email:
                    # Send email to client too -- TEST USAGE
                    send_status_update_email(
                        booking,
                        category_new,
                        eta,
                        username,
                        url,
                        client.status_email,
                    )
                    email_sent = True

                if client.status_phone and is_mobile(client.status_phone):
                    # TEST USAGE --- Send SMS to Plum agent
                    send_status_update_sms(
                        format_mobile(client.status_phone),
                        de_name,
                        booking.b_client_name,
                        booking.b_bookingID_Visual,
                        booking.v_FPBookingNumber,
                        category_new,
                        eta,
                        url,
                        de_company,
                        de_address,
                        delivered_time,
                    )

                # # TEST USAGE --- Send SMS to Stephen (A week period)
                send_status_update_sms(
                    "0499776446",
                    de_name,
                    booking.b_client_name,
                    booking.b_bookingID_Visual,
                    booking.v_FPBookingNumber,
                    category_new,
                    eta,
                    url,
                    de_company,
                    de_address,
                    delivered_time,
                )

        if not email_sent:
            send_status_update_email(booking, category_new, eta, username, url)

        if booking.de_to_Phone_Main and is_mobile(booking.de_to_Phone_Main):
            send_status_update_sms(
                format_mobile(booking.de_to_Phone_Main),
                de_name,
                booking.b_client_name,
                booking.b_bookingID_Visual,
                booking.v_FPBookingNumber,
                category_new,
                eta,
                url,
                de_company,
                de_address,
                delivered_time,
            )

        if booking.de_to_Phone_Mobile and is_mobile(booking.de_to_Phone_Mobile):
            send_status_update_sms(
                format_mobile(booking.de_to_Phone_Mobile),
                de_name,
                booking.b_client_name,
                booking.b_bookingID_Visual,
                booking.v_FPBookingNumber,
                category_new,
                eta,
                url,
                de_company,
                de_address,
                delivered_time,
            )


@background
def notify_user_via_api(booking, event_timestamp):
    # "Tempo"
    if booking.kf_client_id == "37C19636-C5F9-424D-AD17-05A056A8FBDB":
        tempo_update_via_api(booking, event_timestamp)

    # JasonL
    if booking.kf_client_id == "1af6bcd2-6148-11eb-ae93-0242ac130002":
        jasonL_push_via_api(booking, event_timestamp)


def post_new_status(booking, dme_status_history, new_status, event_timestamp, username):
    from api.fp_apis.utils import get_status_category_from_status

    category_new = get_status_category_from_status(dme_status_history.status_last)
    category_old = get_status_category_from_status(dme_status_history.status_old)

    # When get first `In Transit` status
    if category_new == "Transit" and category_old != "Transit":
        if event_timestamp:
            if not booking.b_given_to_transport_date_time:
                booking.b_given_to_transport_date_time = event_timestamp[:10]
            elif not booking.s_20_Actual_Pickup_TimeStamp:
                booking.s_20_Actual_Pickup_TimeStamp = event_timestamp[:10]
        else:
            if not booking.b_given_to_transport_date_time:
                booking.b_given_to_transport_date_time = datetime.now()
            elif not booking.s_20_Actual_Pickup_TimeStamp:
                booking.s_20_Actual_Pickup_TimeStamp = datetime.now()

        booking.s_06_Latest_Delivery_Date_TimeSet = get_eta_de_by(
            booking, booking.api_booking_quote
        )

    if new_status.lower() == "booked":
        booking.s_05_Latest_Pick_Up_Date_TimeSet = get_eta_pu_by(booking)
        booking.s_06_Latest_Delivery_Date_TimeSet = get_eta_de_by(
            booking, booking.api_booking_quote
        )
    elif new_status.lower() == "delivered":
        booking.z_api_issue_update_flag_500 = 0
        booking.z_lock_status = 1

        if event_timestamp:
            booking.s_21_Actual_Delivery_TimeStamp = event_timestamp
            booking.delivery_booking = event_timestamp[:10]

    booking.b_status_category = category_new
    booking.save()
    booking.refresh_from_db()

    notify_user_via_email_sms(booking, category_new, category_old, username)
    notify_user_via_api(booking, event_timestamp)


# Create new status_history for Booking
def create(booking, new_status, username, event_timestamp=None, dme_notes=None):
    if booking.z_lock_status:
        logger.info(f"@699 Booking({booking.b_bookingID_Visual}) is locked!")
        return

    status_histories = Dme_status_history.objects.filter(
        fk_booking_id=booking.pk_booking_id
    ).order_by("-id")

    if status_histories.exists():
        last_status_history = status_histories.first()
    else:
        last_status_history = None

    old_status = booking.b_status
    booking.b_status = new_status
    booking.save()

    if not last_status_history or (
        last_status_history
        and new_status
        and last_status_history.status_last != new_status
    ):
        dme_status_history = Dme_status_history(fk_booking_id=booking.pk_booking_id)
        notes = f"{str(old_status)} ---> {str(new_status)}"
        logger.info(f"@700 New Status! {booking.b_bookingID_Visual}({notes})")

        dme_status_history.status_old = old_status
        dme_status_history.status_last = new_status
        dme_status_history.notes = notes
        dme_status_history.dme_notes = dme_notes
        dme_status_history.event_time_stamp = event_timestamp or datetime.now()
        dme_status_history.recipient_name = ""
        dme_status_history.status_update_via = "Django"
        dme_status_history.z_createdByAccount = username
        dme_status_history.save()

        post_new_status(
            booking, dme_status_history, new_status, event_timestamp, username
        )

        if new_status == "Booked":
            booking_scanned_repack(booking)


# Create new status_history for Bok
def create_4_bok(pk_header_id, status, username, event_timestamp=None):
    status_histories = Dme_status_history.objects.filter(
        fk_booking_id=pk_header_id
    ).order_by("-id")

    if status_histories.exists():
        last_status_history = status_histories.first()
    else:
        last_status_history = None

    if not last_status_history or (
        last_status_history and last_status_history.status_last != status
    ):
        dme_status_history = Dme_status_history(fk_booking_id=pk_header_id)

        if last_status_history:
            dme_status_history.status_old = last_status_history.status_last
            dme_status_history.notes = (
                f"{str(last_status_history.status_last)} ---> {str(status)}"
            )

        dme_status_history.status_last = status
        dme_status_history.event_time_stamp = event_timestamp or datetime.now()
        dme_status_history.recipient_name = ""
        dme_status_history.status_update_via = "Django"
        dme_status_history.z_createdByAccount = username
        dme_status_history.save()
