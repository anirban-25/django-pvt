import logging
from datetime import datetime, timedelta

from django.conf import settings

from api.models import (
    Bookings,
    BookingSets,
    BOK_1_headers,
    BookingSets,
    Api_booking_confirmation_lines,
)
from api.operations.packing.booking import duplicate_line_linedata
from api.operations.labels.index import build_label as build_label_oper
from api.common.time import convert_to_UTC_tz, convert_to_AU_SYDNEY_tz
from api.common import trace_error
from api.common.thread import background
from api.convertors.pdf import pdf_merge
from api.outputs.email import send_email

logger = logging.getLogger(__name__)


def createNewSet():
    """
    Aberdeen Paper workflow #1

        Create BookingSet with newly pushed Aberdeen Paper bookings
    """
    LOG_ID = "[ABP ADD SET]"

    # Check Bok table
    boks_to_map = BOK_1_headers.objects.filter(
        fk_client_id="4ac9d3ee-2558-4475-bdbb-9d9405279e81"
    ).exclude(success=1)
    boks_to_map_count = boks_to_map.count()
    if boks_to_map_count > 0:
        logger.info(f"{LOG_ID} There are {boks_to_map_count} BOKs to map")
        return True

    sets = BookingSets.objects.all()
    booking_ids_in_sets = []

    for _set in sets:
        booking_ids = _set.booking_ids.split(", ")
        for booking_id in booking_ids:
            booking_ids_in_sets.append(booking_id)

    bookings = Bookings.objects.filter(
        kf_client_id="4ac9d3ee-2558-4475-bdbb-9d9405279e81",
        b_dateBookedDate__isnull=True,
        z_CreatedTimestamp__gte="2023-07-01",
    ).exclude(pk__in=booking_ids_in_sets)
    booking_ids = [str(booking.pk) for booking in bookings]

    if not bookings.exists():
        logger.info(f"{LOG_ID} No new bookings for SET.")
        return True

    new_set = BookingSets()
    new_set.name = (
        f"Aberdeen Paper {datetime.now().strftime('%Y-%m-%d_%M:%H')} {sets.count()}"
    )
    new_set.booking_ids = ", ".join(booking_ids)
    new_set.note = "Automaitcally created set"
    new_set.status = "Created"
    new_set.auto_select_type = 1
    new_set.line_haul_date = None
    new_set.z_createdByAccount = "dme (cron)"
    new_set.save()
    logger.info(f"{LOG_ID} New set is created --- {new_set.name}")

    return True


def genLabel():
    """
    Aberdeen Paper workflow #2

        - Copy original items to scanned items
        - Select lowest quote
        - Generate label
    """
    LOG_ID = "[ABP GET LABEL]"

    booking_sets = BookingSets.objects.all()
    booking_sets = booking_sets.filter(note__icontains="use send as is")
    booking_sets = booking_sets.exclude(status__icontains="in progress:")
    booking_sets = booking_sets.exclude(status__icontains="completed:")
    _booking_set = None

    if not booking_sets:
        logger.info(f"{LOG_ID} There are no bookingSets to process")
        return True
    else:
        _booking_set = booking_sets.first()

    # Update Set status
    _booking_set.status = "In progress: Building label 0%"
    _booking_set.save()

    # Find Bookings
    keyword = "use Send As Is:"
    start_index = _booking_set.note.find(keyword) + len(keyword)
    booking_ids = _booking_set.note[start_index:-1].split(",")
    bookings = Bookings.objects.filter(pk__in=booking_ids)
    logger.info(
        f"{LOG_ID} Start #2 workflow. Set: {_booking_set.pk}, Bookings PKs: {booking_ids}"
    )

    for index, booking in enumerate(bookings):
        try:
            lines = booking.lines().filter(is_deleted=False)
            duplicate_line_linedata(booking)

            # # Reset all Api_booking_confirmation_lines
            # Api_booking_confirmation_lines.objects.filter(
            #     fk_booking_id=booking.pk_booking_id
            # ).delete()

            for line in lines:
                if line.sscc and "NOSSCC_" in line.sscc:
                    line.sscc = None
                    line.save()

            scanned_lines = []
            for line in lines:
                if line.packed_status == "scanned":
                    scanned_lines.append(line)

            original_lines = []
            for line in lines:
                if line.packed_status == "original":
                    original_lines.append(line)

            if booking.api_booking_quote:
                selected_lines = []

                for line in lines:
                    if line.packed_status == booking.api_booking_quote.packed_status:
                        selected_lines.append(line)

                lines = selected_lines
            else:
                if scanned_lines:
                    lines = scanned_lines
                else:
                    lines = original_lines

            # Populate SSCC if doesn't exist
            for line in lines:
                if not line.sscc:
                    line.sscc = f"NOSSCC_{booking.b_bookingID_Visual}_{line.pk}"
                    line.save()

            label_urls = []
            sscc_list = []
            sscc_lines = {}
            total_qty = 0
            for line in lines:
                if line.sscc not in sscc_list:
                    sscc_list.append(line.sscc)
                    total_qty += line.e_qty
                    _lines = []

                    for line1 in lines:
                        if line1.sscc == line.sscc:
                            _lines.append(line1)

                    sscc_lines[line.sscc] = _lines
            logger.info(
                f"{LOG_ID} \nsscc_list: {sscc_list}\nsscc_lines: {sscc_lines}\nTotal QTY: {total_qty}"
            )

            if not booking.puPickUpAvailFrom_Date:
                booking.puPickUpAvailFrom_Date = convert_to_AU_SYDNEY_tz(
                    datetime.now()
                ).date()

            file_path = f"{settings.STATIC_PUBLIC}/pdfs/{booking.vx_freight_provider.lower()}_au"

            # Build label with SSCC - one sscc should have one page label
            label_data = build_label_oper(
                booking=booking,
                file_path=file_path,
                total_qty=total_qty,
                sscc_list=sscc_list,
                sscc_lines=sscc_lines,
                need_zpl=False,
            )

            ### SKIP THIS FOR Aberdeen Paper ###
            # if label_data["urls"]:
            #     entire_label_url = f"{file_path}/DME{booking.b_bookingID_Visual}.pdf"
            #     pdf_merge(label_data["urls"], entire_label_url)

            message = f"#379 {LOG_ID} - Successfully build label. Booking Id: {booking.b_bookingID_Visual}"
            logger.info(message)

            if not booking.b_client_booking_ref_num:
                booking.b_client_booking_ref_num = (
                    f"{booking.b_bookingID_Visual}_{str(uuid.uuid4())}"
                )

            booking.z_label_url = (
                f"{settings.WEB_SITE_URL}/label/{booking.b_client_booking_ref_num}/"
            )
            booking.b_error_Capture = None
            booking.save()

            _booking_set.status = (
                f"In progress: Building label {index + 1}/{len(bookings)}"
            )
            _booking_set.save()
        except Exception as e:
            trace_error.print()
            booking.b_error_Capture = "Error while building label."
            booking.save()
            _booking_set.status = f"In progress: Booking ({booking}) has error: {e}"
            _booking_set.save()
            pass

    _booking_set.status = "Completed: building label"
    _booking_set.save()
    return True


@background
def send_email_wrong_address(bok_1):
    from api.clients.aberdeen_paper.constants import CS_EMAIL

    subject = f"Wrong address"
    message = (
        f"Hi Franklin,\n\nPlease note that we picked up an address error for the following customer for sales order: {bok_1['b_client_order_num']}\n"
        + f"The address in NetSuite is showing:\n\n"
        + f"    Street 1: {bok_1.get('b_055_b_del_address_street_1')}\n"
        + f"    Street 2: {bok_1.get('b_056_b_del_address_street_2')}\n"
        + f"    Suburb: {bok_1.get('b_058_b_del_address_suburb')}\n"
        + f"    Postal Code: {bok_1.get('b_059_b_del_address_postalcode')}\n"
        + f"    State: {bok_1.get('b_057_b_del_address_state')}\n\n"
        + f"Can you please update it as soon as possible in NetSuite?\n\nKind regards,\nBookings @ Deliver-ME"
    )

    if settings.ENV in ["local", "dev"]:
        to_emails = [CS_EMAIL]
        cc_emails = ["goldj@deliver-me.com.au"]
    else:
        to_emails = [CS_EMAIL]
        cc_emails = ["dev.deliverme@gmail.com"]

    send_email(to_emails, cc_emails, [], subject, message)
