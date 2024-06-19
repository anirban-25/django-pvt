import uuid
import logging

from django.conf import settings

from api.convertors.pdf import pdf_merge
from api.common.time import convert_to_UTC_tz, convert_to_AU_SYDNEY_tz
from api.operations.labels.index import build_label as build_label_oper
from api.common import trace_error

logger = logging.getLogger(__name__)


def update_label_4_booking(booking, quote):
    LOG_ID = "[LABEL 4 BOOKING]"

    # For `Aberdeen Paper`
    if booking.kf_client_id == "4ac9d3ee-2558-4475-bdbb-9d9405279e81":
        # if quote is None:
        #     booking.z_label_url = None
        #     booking.z_downloaded_shipping_label_timestamp = None
        #     return

        logger.info(f"{LOG_ID} Updating label... Booking: {booking.b_bookingID_Visual}")

        lines = booking.lines().filter(is_deleted=False)
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
            lines = scanned_lines or original_lines

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

        file_path = (
            f"{settings.STATIC_PUBLIC}/pdfs/{booking.vx_freight_provider.lower()}_au"
        )

        try:
            # Build label with SSCC - one sscc should have one page label
            label_data = build_label_oper(
                booking=booking,
                file_path=file_path,
                total_qty=total_qty,
                sscc_list=sscc_list,
                sscc_lines=sscc_lines,
                need_zpl=False,
            )

            if label_data["urls"]:
                entire_label_url = f"{file_path}/DME{booking.b_bookingID_Visual}.pdf"
                pdf_merge(label_data["urls"], entire_label_url)

            message = f"#379 {LOG_ID} - Successfully build label. Booking Id: {booking.b_bookingID_Visual}"
            logger.info(message)

            if not booking.b_client_booking_ref_num:
                booking.b_client_booking_ref_num = (
                    f"{booking.b_bookingID_Visual}_{str(uuid.uuid4())}"
                )

            booking.z_label_url = (
                f"{settings.WEB_SITE_URL}/label/{booking.b_client_booking_ref_num}/"
            )
            booking.save()
        except Exception as e:
            trace_error.print()
            logger.error(f"{LOG_ID} Error: {str(e)}")
