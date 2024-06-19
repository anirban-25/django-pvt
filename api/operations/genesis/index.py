# Mail Genesis functions

import logging
from datetime import datetime
from django.conf import settings

from api.models import (
    Bookings,
    Booking_lines,
    S_Bookings,
    S_Booking_Lines,
    FP_status_history,
    Dme_status_history,
    DMEBookingCSNote,
)
from api.helpers.cubic import get_cubic_meter
from api.fp_apis.utils import get_m3_to_kg_factor
from api.common.ratio import _get_dim_amount, _get_weight_amount
from api.common.constants import PALLETS

logger = logging.getLogger(__name__)


def create_shared_booking(booking):
    LOG_ID = "[GENESIS CREATE]"

    # Work for only JasonL
    if booking.kf_client_id != "1af6bcd2-6148-11eb-ae93-0242ac130002":
        return

    logger.info(f"{LOG_ID} Booking: {booking.b_bookingID_Visual}")

    if settings.ENV != "prod":
        logger.info(f"{LOG_ID} Skipped on this env")
        return

    s_booking = (
        S_Bookings.objects.using("shared_mail")
        .filter(b_bookingID_Visual=booking.b_bookingID_Visual)
        .exists()
    )

    if s_booking:
        logger.info(f"{LOG_ID} Already exists")
        return

    lines = Booking_lines.objects.filter(fk_booking_id=booking.pk_booking_id)
    status_histories = FP_status_history.objects.filter(booking_id=booking.pk).order_by(
        "-id"
    )

    if status_histories.count() == 0:
        status_histories = Dme_status_history.objects.filter(
            fk_booking_id=booking.pk_booking_id
        ).order_by("-id")

    cs_notes = DMEBookingCSNote.objects.filter(booking=booking).order_by("-id")

    s_booking = S_Bookings()
    s_booking.b_bookingID_Visual = booking.b_bookingID_Visual
    s_booking.b_client_booking_ref_num = (
        booking.b_client_booking_ref_num or booking.pk_booking_id
    )
    s_booking.b_dateBookedDate = booking.b_dateBookedDate
    s_booking.v_FPBookingNumber = booking.v_FPBookingNumber
    s_booking.b_client_name = booking.b_client_name
    s_booking.b_client_name_sub = booking.b_client_name_sub
    s_booking.b_client_id = booking.kf_client_id
    s_booking.b_client_order_num = booking.b_client_order_num
    s_booking.de_Deliver_By_Date = booking.de_Deliver_By_Date
    s_booking.vx_freight_provider = booking.vx_freight_provider
    s_booking.vx_serviceName = booking.vx_serviceName
    s_booking.b_status = booking.b_status
    s_booking.b_status_category = booking.b_status_category
    s_booking.de_To_Address_Street_1 = booking.de_To_Address_Street_1
    s_booking.de_To_Address_Street_2 = booking.de_To_Address_Street_2
    s_booking.de_To_Address_State = booking.de_To_Address_State
    s_booking.de_To_Address_Suburb = booking.de_To_Address_Suburb
    s_booking.de_To_Address_PostalCode = booking.de_To_Address_PostalCode
    s_booking.de_To_Address_Country = booking.de_To_Address_Country
    s_booking.de_to_Contact_F_LName = booking.de_to_Contact_F_LName
    s_booking.de_Email = booking.de_Email
    s_booking.de_to_Phone_Mobile = booking.de_to_Phone_Mobile
    s_booking.de_to_Phone_Main = booking.de_to_Phone_Main
    s_booking.zoho_summary = None
    s_booking.zoho_event_datetime = None
    s_booking.booked_for_comm_communicate_via = booking.booked_for_comm_communicate_via
    s_booking.b_booking_Priority = booking.b_booking_Priority
    s_booking.s_06_Estimated_Delivery_TimeStamp = (
        booking.s_06_Latest_Delivery_Date_TimeSet
    )
    s_booking.s_06_Latest_Delivery_Date_Time_Override = (
        booking.s_06_Latest_Delivery_Date_Time_Override
    )
    s_booking.s_21_Actual_Delivery_TimeStamp = booking.s_21_Actual_Delivery_TimeStamp
    s_booking.z_createdAt = datetime.now()
    s_booking.z_updatedAt = datetime.now()

    if status_histories.count() > 0:
        s_booking.fp_event_datetime = datetime.now()
        s_booking.fp_message = "Booked"

    if cs_notes.count() > 0:
        s_booking.last_cs_note = cs_notes[0].note
        s_booking.last_cs_note_timestamp = cs_notes[0].z_createdTimeStamp

    s_booking.save(using="shared_mail")

    for line in lines:
        s_booking_line = S_Booking_Lines()
        s_booking_line.booking = s_booking
        s_booking_line.e_type_of_packaging = line.e_type_of_packaging
        s_booking_line.e_item_type = line.e_item_type
        s_booking_line.e_pallet_type = line.e_pallet_type
        s_booking_line.e_item = line.e_item
        s_booking_line.e_qty = line.e_qty
        s_booking_line.e_weightUOM = line.e_weightUOM
        s_booking_line.e_weightPerEach = line.e_weightPerEach
        s_booking_line.e_dimUOM = line.e_dimUOM
        s_booking_line.e_dimLength = line.e_dimLength
        s_booking_line.e_dimWidth = line.e_dimWidth
        s_booking_line.e_dimHeight = line.e_dimHeight
        s_booking_line.e_cubic = get_cubic_meter(
            line.e_dimLength,
            line.e_dimWidth,
            line.e_dimHeight,
            line.e_dimUOM,
            line.e_qty,
        )
        item_length = line.e_dimLength * _get_dim_amount(line.e_dimUOM)
        item_width = line.e_dimWidth * _get_dim_amount(line.e_dimUOM)
        item_height = line.e_dimHeight * _get_dim_amount(line.e_dimUOM)
        is_pallet = line.e_type_of_packaging.lower() in PALLETS
        item_dead_weight = line.e_weightPerEach * _get_weight_amount(line.e_weightUOM)
        s_booking_line.e_cubic_2_mass_factor = get_m3_to_kg_factor(
            booking.vx_freight_provider,
            {
                "is_pallet": is_pallet,
                "item_length": item_length,
                "item_width": item_width,
                "item_height": item_height,
                "item_dead_weight": item_dead_weight,
            },
        )
        s_booking_line.e_cubic_mass = (
            s_booking_line.e_cubic * s_booking_line.e_cubic_2_mass_factor
        )

        if status_histories:
            s_booking_line.fp_event_datetime = datetime.now()
            s_booking_line.fp_status = "Booked"
            s_booking_line.fp_message = "Booked"

        s_booking_line.z_createdAt = datetime.now()
        s_booking_line.z_updatedAt = datetime.now()
        s_booking_line.save(using="shared_mail")


def update_shared_booking(booking, is_for="all"):
    """
    is_for: enums - 'all', 'fp_info', 'zoho_info', 'cs-note'
    """
    LOG_ID = "[GENESIS UPDATE]"

    # Work for only JasonL
    if booking.kf_client_id != "1af6bcd2-6148-11eb-ae93-0242ac130002":
        return

    logger.info(f"{LOG_ID} Booking: {booking.b_bookingID_Visual}, IS FOR: {is_for}")

    if settings.ENV == "dev":
        logger.info(f"{LOG_ID} Skipped on this env")
        return

    s_bookings = S_Bookings.objects.using("shared_mail").filter(
        b_bookingID_Visual=booking.b_bookingID_Visual
    )

    if not s_bookings.exists():
        logger.info(f"{LOG_ID} Does not exist. So it will create shared booking")
        create_shared_booking(booking)
        return

    s_booking = s_bookings.first()
    status_histories = FP_status_history.objects.filter(booking_id=booking.pk).order_by(
        "-id"
    )

    if is_for == "all":
        s_booking.b_bookingID_Visual = booking.b_bookingID_Visual
        s_booking.b_client_booking_ref_num = (
            booking.b_client_booking_ref_num or booking.pk_booking_id
        )
        s_booking.b_dateBookedDate = booking.b_dateBookedDate
        s_booking.v_FPBookingNumber = booking.v_FPBookingNumber
        s_booking.b_client_name = booking.b_client_name
        s_booking.b_client_name_sub = booking.b_client_name_sub
        s_booking.b_client_id = booking.kf_client_id
        s_booking.b_client_order_num = booking.b_client_order_num
        s_booking.de_Deliver_By_Date = booking.de_Deliver_By_Date
        s_booking.vx_freight_provider = booking.vx_freight_provider
        s_booking.vx_serviceName = booking.vx_serviceName
        s_booking.b_status = booking.b_status
        s_booking.de_To_Address_Street_1 = booking.de_To_Address_Street_1
        s_booking.de_To_Address_Street_2 = booking.de_To_Address_Street_2
        s_booking.de_To_Address_State = booking.de_To_Address_State
        s_booking.de_To_Address_Suburb = booking.de_To_Address_Suburb
        s_booking.de_To_Address_PostalCode = booking.de_To_Address_PostalCode
        s_booking.de_To_Address_Country = booking.de_To_Address_Country
        s_booking.de_to_Contact_F_LName = booking.de_to_Contact_F_LName
        s_booking.de_Email = booking.de_Email
        s_booking.de_to_Phone_Mobile = booking.de_to_Phone_Mobile
        s_booking.de_to_Phone_Main = booking.de_to_Phone_Main
        s_booking.zoho_summary = None
        s_booking.zoho_event_datetime = None
        s_booking.booked_for_comm_communicate_via = (
            booking.booked_for_comm_communicate_via
        )
        s_booking.b_booking_Priority = booking.b_booking_Priority
        s_booking.s_06_Estimated_Delivery_TimeStamp = (
            booking.s_06_Latest_Delivery_Date_TimeSet
        )
        s_booking.s_06_Latest_Delivery_Date_Time_Override = (
            booking.s_06_Latest_Delivery_Date_Time_Override
        )
        s_booking.s_21_Actual_Delivery_TimeStamp = (
            booking.s_21_Actual_Delivery_TimeStamp
        )

        if status_histories:
            s_booking.fp_event_datetime = status_histories[0].event_timestamp
            s_booking.fp_message = status_histories[0].desc

    elif is_for == "fp-info":
        if status_histories:
            s_booking.fp_event_datetime = status_histories[0].event_timestamp
            s_booking.fp_message = status_histories[0].desc
    elif is_for == "zoho_info":
        pass
    elif is_for == "cs-note":
        cs_notes = DMEBookingCSNote.objects.filter(booking=booking).order_by("-id")

        if cs_notes.count() > 0:
            s_booking.last_cs_note = cs_notes[0].note
            s_booking.last_cs_note_timestamp = cs_notes[0].z_createdTimeStamp

    s_booking.z_updatedAt = datetime.now()
    s_booking.save(using="shared_mail")


def create_shared_lines(booking):
    LOG_ID = "[GENESIS LINES UPDATE]"
    logger.info(f"{LOG_ID} Booking: {booking.b_bookingID_Visual}")

    # Work for only JasonL
    if booking.kf_client_id != "1af6bcd2-6148-11eb-ae93-0242ac130002":
        return

    if settings.ENV != "prod":
        logger.info(f"{LOG_ID} Skipped on this env")
        return

    s_bookings = S_Bookings.objects.using("shared_mail").filter(
        b_bookingID_Visual=booking.b_bookingID_Visual
    )

    if not s_bookings.exists():
        logger.info(f"{LOG_ID} Does not exist. So it will create shared booking")
        create_shared_booking(booking)
        return

    s_booking = s_bookings.first()
    s_booking.s_booking_lines_set.all().delete()
    lines = Booking_lines.objects.filter(fk_booking_id=booking.pk_booking_id)
    status_histories = FP_status_history.objects.filter(booking_id=booking.pk).order_by(
        "-id"
    )

    for line in lines:
        s_booking_line = S_Booking_Lines()
        s_booking_line.booking = s_booking
        s_booking_line.e_type_of_packaging = line.e_type_of_packaging
        s_booking_line.e_item_type = line.e_item_type
        s_booking_line.e_pallet_type = line.e_pallet_type
        s_booking_line.e_item = line.e_item
        s_booking_line.e_qty = line.e_qty
        s_booking_line.e_weightUOM = line.e_weightUOM
        s_booking_line.e_weightPerEach = line.e_weightPerEach
        s_booking_line.e_dimUOM = line.e_dimUOM
        s_booking_line.e_dimLength = line.e_dimLength
        s_booking_line.e_dimWidth = line.e_dimWidth
        s_booking_line.e_dimHeight = line.e_dimHeight
        s_booking_line.e_cubic = get_cubic_meter(
            line.e_dimLength,
            line.e_dimWidth,
            line.e_dimHeight,
            line.e_dimUOM,
            line.e_qty,
        )
        item_length = line.e_dimLength * _get_dim_amount(line.e_dimUOM)
        item_width = line.e_dimWidth * _get_dim_amount(line.e_dimUOM)
        item_height = line.e_dimHeight * _get_dim_amount(line.e_dimUOM)
        is_pallet = line.e_type_of_packaging.lower() in PALLETS
        item_dead_weight = line.e_weightPerEach * _get_weight_amount(line.e_weightUOM)
        s_booking_line.e_cubic_2_mass_factor = get_m3_to_kg_factor(
            booking.vx_freight_provider,
            {
                "is_pallet": is_pallet,
                "item_length": item_length,
                "item_width": item_width,
                "item_height": item_height,
                "item_dead_weight": item_dead_weight,
            },
        )
        s_booking_line.e_cubic_mass = (
            s_booking_line.e_cubic * s_booking_line.e_cubic_2_mass_factor
        )

        if status_histories:
            s_booking_line.fp_event_datetime = status_histories[0].event_timestamp
            s_booking_line.fp_status = status_histories[0].status
            s_booking_line.fp_message = status_histories[0].desc

        s_booking_line.z_createdAt = datetime.now()
        s_booking_line.z_updatedAt = datetime.now()
        s_booking_line.save(using="shared_mail")
