import logging
from datetime import datetime

from django.conf import settings

from api.models import (
    Bookings,
    Booking_lines,
    Api_booking_confirmation_lines,
    API_booking_quotes,
)
from api.fp_apis.utils import gen_consignment_num
from api.operations.labels.index import build_label as build_label_oper
from api.operations.pronto_xi.index import update_note as update_pronto_note
from api.operations.genesis.index import create_shared_booking, update_shared_booking
from api.operations.booking.quote import get_quote_again
from api.common.booking_quote import set_booking_quote
from api.common import trace_error
from api.helpers.list import *
from api.convertors.pdf import pdf_merge


logger = logging.getLogger(__name__)
IMPORTANT_FIELDS = [
    "pu_Address_State",
    "pu_Address_Suburb",
    "pu_Address_PostalCode",
    "pu_Address_Country",
    "de_To_Address_State",
    "de_To_Address_Suburb",
    "de_To_Address_PostalCode",
    "pu_Address_Type",
    "de_To_AddressType",
    "pu_no_of_assists",
    "de_no_of_assists",
    "pu_location",
    "de_to_location",
    "pu_access",
    "de_access",
    "pu_floor_number",
    "de_floor_number",
    "pu_floor_access_by",
    "de_to_floor_access_by",
    "pu_service",
    "de_service",
    "booking_type",
]

GENESIS_FIELDS = [
    "b_dateBookedDate",
    "v_FPBookingNumber",
    "b_client_name",
    "b_client_name_sub",
    "de_Deliver_By_Date",
    "vx_freight_provider",
    "vx_serviceName",
    "b_status",
    "de_To_Address_Street_1",
    "de_To_Address_Street_2",
    "de_To_Address_State",
    "de_To_Address_Suburb",
    "de_To_Address_PostalCode",
    "de_To_Address_Country",
    "de_to_Contact_F_LName",
    "de_Email",
    "de_to_Phone_Mobile",
    "de_to_Phone_Main",
    "booked_for_comm_communicate_via",
    "b_booking_Priority",
    "s_06_Latest_Delivery_Date_TimeSet",
    "s_06_Latest_Delivery_Date_Time_Override",
    "s_21_Actual_Delivery_TimeStamp",
]

if settings.ENV == "local":
    S3_URL = "./static"
elif settings.ENV == "dev":
    S3_URL = "/opt/s3_public"
elif settings.ENV == "prod":
    S3_URL = "/opt/s3_public"


def pre_save_handler(instance, update_fields):
    LOG_ID = "[BOOKING PRE SAVE]"

    if instance.id is None:  # new object will be created
        pass
    else:
        logger.info(f"{LOG_ID} Booking PK: {instance.id}")
        old = Bookings.objects.get(id=instance.id)

        if old.dme_status_detail != instance.dme_status_detail:  # field will be updated
            instance.dme_status_detail_updated_by = "user"
            instance.prev_dme_status_detail = old.dme_status_detail
            instance.dme_status_detail_updated_at = datetime.now()

        # Mail Genesis
        if old.b_dateBookedDate and intersection(GENESIS_FIELDS, update_fields or []):
            update_shared_booking(instance)

        if old.b_status != instance.b_status and not instance.b_dateBookedDate:
            if instance.b_status == "Booked":
                instance.b_dateBookedDate = datetime.now()

            # Mail Genesis
            if old.b_dateBookedDate is None and instance.b_dateBookedDate:
                create_shared_booking(instance)
                # pass
            elif instance.b_status == "In Transit":
                try:
                    booking_Lines_cnt = Booking_lines.objects.filter(
                        fk_booking_id=instance.pk_booking_id
                    ).count()
                    fp_scanned_cnt = Api_booking_confirmation_lines.objects.filter(
                        fk_booking_id=instance.pk_booking_id, tally__gt=0
                    ).count()

                    dme_status_detail = ""
                    if (
                        instance.b_given_to_transport_date_time
                        and not instance.fp_received_date_time
                    ):
                        dme_status_detail = "In transporter's depot"
                    if instance.fp_received_date_time:
                        dme_status_detail = "Good Received by Transport"

                    if fp_scanned_cnt > 0 and fp_scanned_cnt < booking_Lines_cnt:
                        dme_status_detail = dme_status_detail + " (Partial)"

                    instance.dme_status_detail = dme_status_detail
                    instance.dme_status_detail_updated_by = "user"
                    instance.prev_dme_status_detail = old.dme_status_detail
                    instance.dme_status_detail_updated_at = datetime.now()
                except Exception as e:
                    logger.info(f"#505 {LOG_ID} Error {e}")
                    pass
            elif instance.b_status == "Delivered":
                instance.dme_status_detail = ""
                instance.dme_status_detail_updated_by = "user"
                instance.prev_dme_status_detail = old.dme_status_detail
                instance.dme_status_detail_updated_at = datetime.now()

        # BSD
        if instance.kf_client_id == "9e72da0f-77c3-4355-a5ce-70611ffd0bc8":
            if old.z_label_url != instance.z_label_url:
                instance.status = "Ready for Booking"

        # JasonL
        if instance.kf_client_id == "1af6bcd2-6148-11eb-ae93-0242ac130002":
            quote = instance.api_booking_quote

            if quote and (
                old.b_status != instance.b_status  # Status
                or (
                    instance.b_dateBookedDate
                    and old.b_dateBookedDate != instance.b_dateBookedDate  # BookedDate
                )
                or (
                    instance.v_FPBookingNumber
                    and old.v_FPBookingNumber
                    != instance.v_FPBookingNumber  # Consignment
                )
                or (old.api_booking_quote_id != instance.api_booking_quote_id)  # Quote
            ):
                update_pronto_note(quote, instance, [], "booking")

        if (
            instance.api_booking_quote
            and old.api_booking_quote_id != instance.api_booking_quote_id
        ):
            quote = instance.api_booking_quote

            if instance.api_booking_quote.vehicle:
                logger.info(f"#506 {LOG_ID} vehicle changed!")
                instance.v_vehicle_Type = (
                    quote.vehicle.description if quote.vehicle else None
                )

            if quote.packed_status == API_booking_quotes.SCANNED_PACK:
                instance.inv_booked_quoted = quote.client_mu_1_minimum_values
            else:
                instance.inv_sell_quoted = quote.client_mu_1_minimum_values


# def post_save_handler(instance, created, update_fields):
#     LOG_ID = "[BOOKING POST SAVE]"
