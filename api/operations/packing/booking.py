import uuid
import logging

from django.db.models import Q

from api.models import (
    Bookings,
    Booking_lines,
    Booking_lines_data,
    Pallet,
    API_booking_quotes,
)
from api.serializers import BookingLineSerializer, BookingLineDetailSerializer
from api.common.pallet import get_palletized_by_ai
from api.common.booking_quote import set_booking_quote
from api.helpers.line import is_carton, is_pallet

logger = logging.getLogger(__name__)


def auto_repack(booking, repack_status, need_soft_delete=False):
    LOG_ID = "[BOOKING AUTO REPACK]"
    logger.info(
        f"@830 {LOG_ID} Booking: {booking.b_bookingID_Visual}, Repack Status: {repack_status}"
    )
    lines = (
        booking.lines()
        .filter(Q(packed_status=Booking_lines.ORIGINAL) | Q(packed_status__isnull=True))
        .filter(is_deleted=False)
    )
    auto_repacked_lines = []

    # Select suitable pallet and get required pallets count
    if booking.b_client_name == "Bathroom Sales Direct":
        pallets = Pallet.objects.filter(pk=7)  # 1.2 x 1.2
    else:
        pallets = Pallet.objects.all()
    palletized, non_palletized = get_palletized_by_ai(lines, pallets)
    logger.info(
        f"@831 {LOG_ID} Palletized: {palletized}\nNon-Palletized: {non_palletized}"
    )

    # Create one PAL Line
    for item in non_palletized:  # Non Palletized
        item["line_obj"].pk = None
        item["line_obj"].packed_status = Booking_lines.AUTO_PACK
        item["line_obj"].save()
        auto_repacked_lines.append(item["line_obj"])

    for palletized_item in palletized:  # Palletized
        pallet = pallets[palletized_item["pallet_index"]]

        total_weight = 0
        for _iter in palletized_item["lines"]:
            line_in_pallet = _iter["line_obj"]
            total_weight += (
                line_in_pallet.e_weightPerEach
                * _iter["quantity"]
                / palletized_item["quantity"]
            )

        new_line = {}
        new_line["fk_booking_id"] = booking.pk_booking_id
        new_line["pk_booking_lines_id"] = str(uuid.uuid1())
        new_line["e_type_of_packaging"] = "PAL"
        new_line["e_qty"] = palletized_item["quantity"]
        new_line["e_item"] = "Auto repacked item"
        new_line["e_dimUOM"] = "mm"
        new_line["e_dimLength"] = pallet.length
        new_line["e_dimWidth"] = pallet.width
        new_line["e_dimHeight"] = palletized_item["packed_height"] * 1000
        new_line["e_weightPerEach"] = round(total_weight, 2)
        new_line["e_weightUOM"] = "KG"
        new_line["is_deleted"] = False
        new_line["packed_status"] = Booking_lines.AUTO_PACK

        line_serializer = BookingLineSerializer(data=new_line)
        if line_serializer.is_valid():
            # Create LineData
            for _iter in palletized_item["lines"]:
                line = _iter["line_obj"]  # line_in_pallet
                bok_3 = {}
                bok_3["fk_booking_id"] = booking.pk_booking_id
                bok_3["fk_booking_lines_id"] = new_line["pk_booking_lines_id"]
                bok_3["itemSerialNumbers"] = line.zbl_131_decimal_1  # Sequence
                bok_3["quantity"] = palletized_item["quantity"] * _iter["quantity"]
                bok_3["itemDescription"] = line.e_item
                bok_3["modelNumber"] = line.e_item_type

                line_data_serializer = BookingLineDetailSerializer(data=bok_3)
                if line_data_serializer.is_valid():
                    line_data_serializer.save()

                    # Soft delete `line in pallet`
                    line.is_deleted = need_soft_delete
                    line.save()
                else:
                    message = f"Serialiser Error - {line_data_serializer.errors}"
                    logger.info(f"@834 {LOG_ID} {message}")
                    raise Exception(message)

            line_serializer.save()
            auto_repacked_lines.append(new_line)
        else:
            message = f"Serialiser Error - {line_serializer.errors}"
            logger.info(f"@835 {LOG_ID} {message}")
            raise Exception(message)

    logger.info(
        f"@839 {LOG_ID} Booking: {booking.b_bookingID_Visual} --- Finished successfully!"
    )


def manual_repack(booking, repack_status):
    """
    Duplicate line and lineData for `manual` repacked status

    @params:
        booking:
        repack_status: 'manual-from-original' | 'manual-from-auto'
    """
    LOG_ID = "[LINE & LINEDATA BULK DUPLICATION]"
    logger.info(
        f"@840 {LOG_ID} Booking: {booking.b_bookingID_Visual}, Repack Status: {repack_status}"
    )

    if repack_status == "manual-from-original":  # Original
        lines = (
            booking.lines()
            .filter(
                Q(packed_status=Booking_lines.ORIGINAL) | Q(packed_status__isnull=True)
            )
            .filter(is_deleted=False)
        )
    else:  # Auto Repacked
        lines = (
            booking.lines()
            .filter(Q(packed_status=Booking_lines.AUTO_PACK))
            .filter(is_deleted=False)
        )

    if lines.count() == 0:
        logger.info(
            f"@841 {LOG_ID} Booking: {booking.b_bookingID_Visual} --- No lines to be duplicated!"
        )
        return

    for line in lines:
        line_datas = Booking_lines_data.objects.filter(
            fk_booking_lines_id=line.pk_booking_lines_id
        )

        line.pk = None
        line.pk_booking_lines_id = str(uuid.uuid4())
        line.packed_status = Booking_lines.MANUAL_PACK
        line.save()

        for line_data in line_datas:
            line_data.pk = None
            line_data.fk_booking_lines_id = line.pk_booking_lines_id
            line_data.save()

    logger.info(
        f"@849 {LOG_ID} Booking: {booking.b_bookingID_Visual} --- Finished successfully! {len(lines)} Lines are duplicated."
    )


def reset_repack(booking, repack_status):
    """
    Delete line and lineData of specified repacked status

    @params:
        booking:
        repack_status: 'manual' | 'auto'
    """
    LOG_ID = "[REPACK RESET]"
    logger.info(
        f"@840 {LOG_ID} Booking: {booking.b_bookingID_Visual}, Repack Status: {repack_status}"
    )

    lines = booking.lines().filter(packed_status=repack_status).filter(is_deleted=False)

    if lines.count() == 0:
        logger.info(f"@841 {LOG_ID} Booking: {booking} --- No lines to be reset!")
        return

    for line in lines:
        line_datas = Booking_lines_data.objects.filter(
            fk_booking_lines_id=line.pk_booking_lines_id
        ).delete()
        line.delete()

    logger.info(
        f"@849 {LOG_ID} Booking: {booking.b_bookingID_Visual} --- Finished successfully! {len(lines)} Lines are reset."
    )


def scanned_repack(booking):
    """
    Populate scanned repack

    @params:
        booking: Booking
    """
    LOG_ID = "[REPACK SCANNED]"
    logger.info(f"@870 {LOG_ID} Booking: {booking.b_bookingID_Visual}")

    scanned_lines = (
        booking.lines()
        .filter(packed_status=Booking_lines.SCANNED_PACK)
        .filter(is_deleted=False)
    )

    if scanned_lines.exists():
        logger.info(
            f"@871 {LOG_ID} Booking: {booking.b_bookingID_Visual}, Scanned lines are already exist!"
        )
        return

    if booking.api_booking_quote:
        packed_status = booking.api_booking_quote.packed_status
    else:
        # Get latest modified `packed status`
        original_lines = (
            booking.lines()
            .filter(packed_status=Booking_lines.ORIGINAL)
            .filter(is_deleted=False)
        )
        auto_lines = (
            booking.lines()
            .filter(packed_status=Booking_lines.AUTO_PACK)
            .filter(is_deleted=False)
        )
        manual_lines = (
            booking.lines()
            .filter(packed_status=Booking_lines.MANUAL_PACK)
            .filter(is_deleted=False)
        )

        latest_modified_line = original_lines[0]
        latest_modified_timestamp = (
            latest_modified_line.z_modifiedTimeStamp
            if latest_modified_line.z_modifiedTimeStamp
            else latest_modified_line.z_createdTimeStamp
        )

        for line in original_lines:
            timestamp = (
                line.z_modifiedTimeStamp
                if line.z_modifiedTimeStamp
                else line.z_createdTimeStamp
            )

            if timestamp > latest_modified_timestamp:
                latest_modified_timestamp = timestamp
                latest_modified_line = line

        for line in auto_lines:
            timestamp = (
                line.z_modifiedTimeStamp
                if line.z_modifiedTimeStamp
                else line.z_createdTimeStamp
            )

            if timestamp > latest_modified_timestamp:
                latest_modified_timestamp = timestamp
                latest_modified_line = line

        for line in scanned_lines:
            timestamp = (
                line.z_modifiedTimeStamp
                if line.z_modifiedTimeStamp
                else line.z_createdTimeStamp
            )

            if timestamp > latest_modified_timestamp:
                latest_modified_timestamp = timestamp
                latest_modified_line = line

        packed_status = latest_modified_line.packed_status

    if packed_status:
        # Duplicate Lines
        lines = (
            booking.lines().filter(packed_status=packed_status).filter(is_deleted=False)
        )

        for line in lines:
            line_datas = Booking_lines_data.objects.filter(
                fk_booking_lines_id=line.pk_booking_lines_id
            )

            line.pk = None
            line.pk_booking_lines_id = str(uuid.uuid4())
            line.packed_status = Booking_lines.SCANNED_PACK
            line.save()

            for line_data in line_datas:
                line_data.pk = None
                line_data.fk_booking_lines_id = line.pk_booking_lines_id
                line_data.packed_status = Booking_lines.SCANNED_PACK
                line_data.save()

        # Duplicate Quotes
        quotes = API_booking_quotes.objects.filter(
            fk_booking_id=booking.pk_booking_id,
            is_used=False,
            packed_status=packed_status,
        )
        for quote in quotes:
            is_selected_dup = False

            if booking.api_booking_quote and booking.api_booking_quote == quote:
                is_selected_dup = True

            quote.pk = None
            quote.packed_status = Booking_lines.SCANNED_PACK
            quote.save()

            if is_selected_dup:
                set_booking_quote(booking, quote)

    logger.info(
        f"@879 {LOG_ID} Booking: {booking.b_bookingID_Visual} --- Finished successfully!"
    )


def duplicate_line_linedata(booking):
    """
    Duplicate line and lineData

    original -> scanned | scanned -> original
    """
    LOG_ID = "[LINE & LINEDATA BULK DUPLICATION]"
    logger.info(f"@840 {LOG_ID} Booking: {booking.b_bookingID_Visual}")

    original_lines = (
        booking.lines()
        .filter(Q(packed_status=Booking_lines.ORIGINAL) | Q(packed_status__isnull=True))
        .filter(is_deleted=False)
    )
    scanned_lines = (
        booking.lines()
        .filter(
            Q(packed_status=Booking_lines.SCANNED_PACK) | Q(packed_status__isnull=True)
        )
        .filter(is_deleted=False)
    )

    if original_lines.count() == 0 and scanned_lines.count() == 0:
        logger.info(
            f"@841 {LOG_ID} Booking: {booking.b_bookingID_Visual} --- No lines to be duplicated!"
        )
        return
    elif original_lines.count() > 0 and scanned_lines.count() > 0:
        logger.info(
            f"@842 {LOG_ID} Booking: {booking.b_bookingID_Visual} --- Original and Scanned lines are already there!"
        )
        return
    elif original_lines.count() > 0:
        packed_status = Booking_lines.SCANNED_PACK
        lines = original_lines
    elif scanned_lines.count() > 0:
        packed_status = Booking_lines.ORIGINAL
        lines = scanned_lines

    for line in lines:
        # Aberdeen Paper - map only Carton items
        if booking.kf_client_id == "4ac9d3ee-2558-4475-bdbb-9d9405279e81":
            if not (
                is_carton(line.e_type_of_packaging)
                or is_pallet(line.e_type_of_packaging)
            ):
                continue

        line_datas = Booking_lines_data.objects.filter(
            fk_booking_lines_id=line.pk_booking_lines_id
        )
        line.pk = None
        line.pk_booking_lines_id = str(uuid.uuid4())
        line.packed_status = packed_status
        line.save()

        for line_data in line_datas:
            line_data.pk = None
            line_data.fk_booking_lines_id = line.pk_booking_lines_id
            line_data.packed_status = packed_status
            line_data.save()

    logger.info(
        f"@849 {LOG_ID} Booking: {booking.b_bookingID_Visual} --- Finished successfully! {len(lines)} Lines are duplicated."
    )
