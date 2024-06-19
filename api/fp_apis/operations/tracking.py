import logging
from datetime import datetime

from django.conf import settings

from api.models import *
from api.common import status_history
from api.common.time import convert_to_UTC_tz
from api.fp_apis.utils import (
    get_dme_status_from_fp_status,
    get_status_category_from_status,
)
from api.operations.email_senders import send_email_missing_status

logger = logging.getLogger(__name__)


def _extract(fp_name, consignmentStatus):
    item_ref = None

    if fp_name.lower() == "startrack":
        b_status_API = consignmentStatus["status"]
        event_time = None
        status_desc = ""
    elif fp_name.lower() in ["tnt"]:
        b_status_API = consignmentStatus["status"][0]
        status_desc = consignmentStatus["statusDescription"][0]
        event_time = consignmentStatus["statusDate"][0]
        event_time = datetime.strptime(event_time, "%d/%m/%Y")
        event_time = str(convert_to_UTC_tz(event_time))
    elif fp_name.lower() in ["hunter", "sendle", "allied"]:
        b_status_API = consignmentStatus["status"]
        status_desc = consignmentStatus.get("statusDescription")
        event_time = consignmentStatus["statusUpdate"]
        # is_UTC = len(event_time) == 19

        if event_time:
            if len(event_time) > 18:
                event_time = datetime.strptime(event_time[:19], "%Y-%m-%dT%H:%M:%S")
            else:
                event_time = datetime.strptime(event_time[:16], "%Y-%m-%d %H:%M")

        event_time = str(convert_to_UTC_tz(event_time))
    elif fp_name.lower() in ["team global express"]:
        b_status_API = consignmentStatus["description"]
        status_desc = consignmentStatus["type"]
        event_time = consignmentStatus["eventAt"]
        event_time = datetime.strptime(event_time[:19], "%Y-%m-%dT%H:%M:%S")
        event_time = str(convert_to_UTC_tz(event_time))
        location = consignmentStatus["location"]
        item_ref = consignmentStatus["itemReference"]
        status_desc = f"{status_desc}-{item_ref}"
    elif fp_name.lower() in ["direct freight"]:
        b_status_API = consignmentStatus["status"]

        if "Delivered" in b_status_API:
            b_status_API = "Delivered"

        status_desc = consignmentStatus["statusDescription"]
        event_time = consignmentStatus["statusUpdate"]
        event_time = datetime.strptime(event_time, "%Y-%m-%dT%H:%M:%S")
        event_time = str(convert_to_UTC_tz(event_time))
        location = consignmentStatus["location"]
    else:
        event_time = None

    return b_status_API, status_desc, event_time, item_ref


def _extract_bulk(fp_name, consignmentStatuses):
    _result = []
    _consignmentStatuses = consignmentStatuses

    if fp_name.lower() in ["allied", "direct freight"]:
        # Sort by timestamp
        _consignmentStatuses = sorted(
            consignmentStatuses, key=lambda x: x["statusUpdate"]
        )
    # elif fp_name.lower() in ["startrack", "st"]:
    #     # Reverse sort order
    #     _consignmentStatuses = consignmentStatuses.reverse()

    for consignmentStatus in _consignmentStatuses:
        b_status_API = None
        status_desc = None
        event_time = None
        location = None
        item_ref = None

        if fp_name.lower() in ["startrack", "st"]:
            b_status_API = consignmentStatus["status"]
            event_time = None
            status_desc = ""

            if "statusDate" in consignmentStatus:
                event_time = consignmentStatus["statusDate"]
                event_time = datetime.strptime(event_time[:19], "%Y-%m-%dT%H:%M:%S")
                event_time = str(convert_to_UTC_tz(event_time))
        elif fp_name.lower() in ["tnt"]:
            b_status_API = consignmentStatus["status"][0]
            status_desc = consignmentStatus["statusDescription"][0]
            event_time = consignmentStatus["statusDate"][0]
            event_time = datetime.strptime(event_time, "%d/%m/%Y")
            event_time = str(convert_to_UTC_tz(event_time))
        elif fp_name.lower() in ["hunter", "sendle", "allied"]:
            b_status_API = consignmentStatus["status"]
            status_desc = consignmentStatus.get("statusDescription")
            event_time = consignmentStatus["statusUpdate"]
            # is_UTC = len(event_time) == 19

            if event_time:
                if len(event_time) > 18:
                    event_time = datetime.strptime(event_time[:19], "%Y-%m-%dT%H:%M:%S")
                else:
                    event_time = datetime.strptime(event_time[:16], "%Y-%m-%d %H:%M")

            event_time = str(convert_to_UTC_tz(event_time))
        elif fp_name.lower() in ["team global express"]:
            b_status_API = consignmentStatus["description"]
            status_desc = consignmentStatus["type"]
            event_time = consignmentStatus["eventAt"]
            event_time = datetime.strptime(event_time[:19], "%Y-%m-%dT%H:%M:%S")
            event_time = str(convert_to_UTC_tz(event_time))
            location = consignmentStatus["location"]
            item_ref = consignmentStatus["itemReference"]
            status_desc = f"{status_desc}-{item_ref}"
        elif fp_name.lower() in ["direct freight"]:
            b_status_API = consignmentStatus["status"]

            if "Delivered" in b_status_API:
                b_status_API = "Delivered"

            status_desc = consignmentStatus["statusDescription"]
            event_time = consignmentStatus["statusUpdate"]
            event_time = datetime.strptime(event_time, "%Y-%m-%dT%H:%M:%S")
            event_time = str(convert_to_UTC_tz(event_time))
            location = consignmentStatus["location"]
        else:
            event_time = None

        _result.append(
            {
                "b_status_API": b_status_API,
                "status_desc": status_desc,
                "event_time": event_time,
                "location": location,
                "item_ref": item_ref,
            }
        )

    return _result


def _get_actual_timestamp(fp_name, consignmentStatuses, type):
    if fp_name in ["tnt", "hunter", "sendle", "allied", "team global express"]:
        try:
            for consignmentStatus in consignmentStatuses:
                b_status_API, status_desc, event_time, item_ref = _extract(
                    fp_name, consignmentStatus
                )

                b_status = get_dme_status_from_fp_status(fp_name, b_status_API)
                status_category = get_status_category_from_status(b_status)

                if status_category == "Transit" and type == "pickup":
                    return event_time
                elif status_category == "Complete" and type == "delivery":
                    return event_time
        except Exception as e:
            logger.error(f"#480 Error: _get_actual_timestamp(), {str(e)}")
            return None

    return None


def update_booking_with_tracking_result(request, booking, fp_name, consignmentStatuses):
    if booking.z_lock_status:
        msg = f"#380 [TRACKING] Locked Booking: {booking.b_bookingID_Visual}({fp_name})"
        logger.info(msg)
        return True

    if not consignmentStatuses:
        msg = f"#381 [TRACKING] No statuses: {booking.b_bookingID_Visual}({fp_name})"
        logger.info(msg)
        return False

    # TGE
    _consignmentStatuses = consignmentStatuses
    if fp_name.lower() == "team global express":
        _consignmentStatuses_0 = consignmentStatuses

        # Check Partially Delivered
        has_delivered_status = False
        delivered_status_cnt = 0
        last_consignmentStatus = _consignmentStatuses_0[len(_consignmentStatuses_0) - 1]

        for _consignmentStatus in _consignmentStatuses_0:
            if _consignmentStatus["description"] in ["COLLCTD", "DELVERD", "Delivered"]:
                has_delivered_status = True
                delivered_status_cnt += 1

        if has_delivered_status:
            lines_count = (
                booking.lines()
                .filter(is_deleted=False, packed_status="scanned")
                .count()
            )
            if delivered_status_cnt < lines_count:
                logger.info(
                    f"#382 [TRACKING] TGE Partially Delivered BookingId: {booking.b_bookingID_Visual}"
                )
                _consignmentStatuses.append(
                    {
                        "type": last_consignmentStatus["type"],
                        "eventAt": last_consignmentStatus["eventAt"],
                        "description": "Partially Delivered",
                        "itemReference": last_consignmentStatus["itemReference"],
                        "location": last_consignmentStatus["location"],
                    }
                )

    # DF (Direct Freight)
    if fp_name.lower() == "direct freight":
        # Sort by timestamp
        _consignmentStatuses = sorted(
            consignmentStatuses, key=lambda x: x["statusUpdate"]
        )

    # Allied
    # _consignmentStatuses = consignmentStatuses
    if fp_name.lower() == "allied":
        _consignmentStatuses_0 = consignmentStatuses

        # Sort by timestamp
        _consignmentStatuses_0 = sorted(
            consignmentStatuses, key=lambda x: x["statusUpdate"]
        )

        # Check Partially Delivered
        has_delivered_status = False
        delivered_status_cnt = 0
        last_consignmentStatus = _consignmentStatuses_0[len(_consignmentStatuses_0) - 1]

        for _consignmentStatus in _consignmentStatuses_0:
            if _consignmentStatus["status"] in ["DEL", "ATL", "PODIN"]:
                has_delivered_status = True
                delivered_status_cnt += 1

        # Take out status after `DEL`
        if has_delivered_status:
            _consignmentStatuses = []

            for index, _consignmentStatus in enumerate(_consignmentStatuses_0):
                _consignmentStatuses.append(_consignmentStatus)

                if _consignmentStatus["status"] in ["DEL", "ATL", "PODIN"]:
                    break
        else:
            _consignmentStatuses = _consignmentStatuses_0

        if has_delivered_status:
            if booking.api_booking_quote:
                lines = booking.lines().filter(
                    is_deleted=False,
                    packed_status=booking.api_booking_quote.packed_status,
                )
            else:
                lines = booking.lines().filter(
                    is_deleted=False, packed_status=Booking_lines.ORIGINAL
                )

            if delivered_status_cnt < lines.count():
                logger.info(
                    f"#382 [TRACKING] Allied Partially Delivered BookingId: {booking.b_bookingID_Visual}, statuses: {_consignmentStatuses}"
                )
                _consignmentStatuses.append(
                    {
                        "status": "PARTDEL",
                        "statusDescription": "Partially Delivered",
                        "statusUpdate": last_consignmentStatus["statusUpdate"],
                    }
                )

    # Get actual_pickup_timestamp
    if not booking.s_20_Actual_Pickup_TimeStamp:
        result = _get_actual_timestamp(fp_name.lower(), _consignmentStatuses, "pickup")

        if result:
            booking.s_20_Actual_Pickup_TimeStamp = result

    # Get actual_delivery_timestamp
    if not booking.s_21_Actual_Delivery_TimeStamp:
        result = _get_actual_timestamp(
            fp_name.lower(), _consignmentStatuses, "delivery"
        )

        if result:
            booking.s_21_Actual_Delivery_TimeStamp = result
            booking.delivery_booking = result[:10]

    # Update booking's latest status
    if fp_name.lower() in ["startrack", "st"]:
        last_consignmentStatus = _consignmentStatuses[0]
    else:
        last_consignmentStatus = _consignmentStatuses[len(_consignmentStatuses) - 1]

    b_status_API, status_desc, event_time, item_ref = _extract(
        fp_name.lower(), last_consignmentStatus
    )
    booking.b_status_API = b_status_API
    new_status = get_dme_status_from_fp_status(fp_name, b_status_API, booking)

    if not new_status:  # Missing status mapping rule
        booking.b_errorCapture = f"New FP status: {b_status_API}"
        send_email_missing_status(booking, fp_name, b_status_API)

    status_history.create(booking, new_status, request.user.username, event_time)
    # booking.b_status = status_from_fp
    # booking.b_booking_Notes = status_desc
    booking.save()

    # msg = f"#389 [TRACKING] Success: {booking.b_bookingID_Visual}({fp_name})"
    # logger.info(msg)
    return True


def create_fp_status_history(booking, fp, data):
    _fp_status_history = FP_status_history()
    _fp_status_history.booking = booking
    _fp_status_history.fp = fp
    _fp_status_history.status = data["b_status_API"]
    _fp_status_history.desc = data["status_desc"]
    _fp_status_history.event_timestamp = data["event_time"]
    _fp_status_history.location = data.get("location")
    _fp_status_history.is_active = True
    _fp_status_history.save()

    return _fp_status_history


def populate_fp_status_history(booking, consignmentStatuses):
    LOG_ID = "#321 [POPULATE FP STATUS HISTORY]"
    fp_name = booking.vx_freight_provider

    if not consignmentStatuses:
        msg = f"#321 {LOG_ID} No statuses: {booking.b_bookingID_Visual}({fp_name})"
        logger.info(msg)
        return False

    fp_status_histories = FP_status_history.objects.filter(
        booking=booking, is_active=True
    ).order_by("-event_timestamp")
    new_fp_status_histories = _extract_bulk(fp_name, consignmentStatuses)
    fp = booking.get_fp()

    # Initial Tracking
    if fp_status_histories.count() == 0:
        msg = f"#322 {LOG_ID} Initial Tracking: {booking.b_bookingID_Visual}({fp_name})"
        logger.info(msg)

        for new_data in new_fp_status_histories:
            create_fp_status_history(booking, fp, new_data)

        return True

    # Periodic Tracking
    if len(new_fp_status_histories) < fp_status_histories.count():
        msg = f"#325 {LOG_ID} RARE CASE HAPPENED! --- Booking: {booking.b_bookingID_Visual}({fp_name})"
        logger.info(msg)

        # Soft delete existing FP statuses
        fp_status_histories.update(is_active=False)

        # Create new ones
        for new_data in new_fp_status_histories:
            create_fp_status_history(booking, fp, new_data)

        return True
    else:
        news = []

        # Existing descriptions
        existing_desc_list = []
        for fp_status_history in fp_status_histories:
            existing_desc_list.append(fp_status_history.desc)

        for _new in new_fp_status_histories:
            has_already = False

            for fp_status_history in fp_status_histories:
                # Compare status and event_time
                if (
                    _new["b_status_API"] == fp_status_history.status
                    and fp_status_history.event_timestamp
                    and _new["event_time"][:19]
                    == fp_status_history.event_timestamp.strftime("%Y-%m-%d %H:%M:%S")
                ):
                    has_already = True

                if (
                    not fp_status_history.event_timestamp
                    and fp_status_history.status == _new["b_status_API"]
                ):
                    has_already = True

                if not _new["status_desc"] in existing_desc_list:
                    has_already = False
                    break

            if not has_already:
                news.append(_new)

        if not news:
            msg = f"#323 {LOG_ID} No new status from FP --- Booking: {booking.b_bookingID_Visual}({fp_name})"
            # logger.info(msg)
            return False

        for new in news:
            msg = f"#324 {LOG_ID} New status from FP --- Booking: {booking.b_bookingID_Visual}({fp_name}), FP Status: {new['b_status_API']} ({new['status_desc']})"
            logger.info(msg)

            create_fp_status_history(booking, fp, new)

            # Do not create new dme_status_history when same `status` but different `event_time`
            if (
                not new["b_status_API"] == "Delivered"
                and new["b_status_API"] == fp_status_histories[0].status
            ):
                logger.info(f"{LOG_ID} Same status with different even_time")
                return False

        return True


def populate_items_status(booking, itemStatusList):
    bcls = Api_booking_confirmation_lines.objects.filter(
        fk_booking_id=booking.pk_booking_id
    )

    for itemStatus in itemStatusList:
        does_bcl_exist = False

        if booking.vx_freight_provider.lower() in ["startrack"]:
            if not "status" in itemStatus:
                continue

            if "events" in itemStatus:
                event_timestamp = itemStatus["events"][0]["date"]
                event_timestamp = datetime.strptime(
                    event_timestamp[:19], "%Y-%m-%dT%H:%M:%S"
                )

            for bcl in bcls:
                if bcl.api_artical_id == itemStatus["articleId"]:
                    does_bcl_exist = True

                    if bcl.api_status != itemStatus["status"]:
                        bcl.api_status = itemStatus["status"]
                        bcl.fp_event_date = event_timestamp.date()
                        bcl.fp_event_time = event_timestamp.time()
                        bcl.save()

            if not does_bcl_exist:
                Api_booking_confirmation_lines(
                    fk_booking_id=booking.pk_booking_id,
                    api_artical_id=itemStatus["articleId"],
                    api_status=itemStatus["status"],
                    service_provider=booking.vx_freight_provider,
                    api_consignment_id=booking.v_FPBookingNumber,
                    fp_event_date=event_timestamp.date(),
                    fp_event_time=event_timestamp.time(),
                ).save()
        elif booking.vx_freight_provider.lower() in ["team global express"]:
            if not "description" in itemStatus:
                continue

            status = itemStatus["description"]
            event_timestamp = itemStatus["eventAt"]
            event_timestamp = datetime.strptime(
                event_timestamp[:19], "%Y-%m-%dT%H:%M:%S"
            )
            item_ref = itemStatus["itemReference"]
            # location = itemStatus["location"]
            # description = itemStatus["type"]

            for bcl in bcls:
                if bcl.label_code == item_ref:
                    does_bcl_exist = True

                    if bcl.api_status != status:
                        bcl.api_status = status
                        bcl.fp_event_date = event_timestamp.date()
                        bcl.fp_event_time = event_timestamp.time()
                        bcl.save()

            if not does_bcl_exist:
                Api_booking_confirmation_lines(
                    fk_booking_id=booking.pk_booking_id,
                    label_code=item_ref,
                    api_status=status,
                    service_provider=booking.vx_freight_provider,
                    api_consignment_id=booking.v_FPBookingNumber,
                    fp_event_date=event_timestamp.date(),
                    fp_event_time=event_timestamp.time(),
                ).save()
