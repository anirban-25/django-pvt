import math
import logging
from datetime import datetime, date

from rest_framework.exceptions import ValidationError
from django.conf import settings

from api.models import *
from api.common import time as dme_time_lib
from api.common import trace_error
from api.common.time import TIME_DIFFERENCE
from api.helpers.cubic import get_cubic_meter, getM3ToKgFactor
from api.helpers.line import is_carton, is_pallet
from api.helpers.phone import compact_number
from api.fp_apis.utils import _convert_UOM, gen_consignment_num
from api.fp_apis.constants import FP_CREDENTIALS, FP_CREDENTIALS, FP_UOM
from api.fps.tnt import get_service_code as get_tnt_service_code
from api.fps.team_global_express import gen_sscc as gen_sscc_tge
from api.fps.camerons import gen_sscc as gen_sscc_camerons
from api.common.time import convert_to_AU_SYDNEY_tz

logger = logging.getLogger(__name__)  # Payload Builder


def get_account_detail(booking, fp_name):
    _fp_name = fp_name.lower()
    _b_client_name = booking.b_client_name.lower()
    account_code = None
    account_detail = None

    if _fp_name not in FP_CREDENTIALS:
        booking.b_errorCapture = f"Not supported FP"
        booking.save()
        raise ValidationError(booking.b_errorCapture)

    if booking.api_booking_quote:
        account_code = booking.api_booking_quote.account_code
    elif booking.vx_account_code:
        account_code = booking.vx_account_code

    if account_code:
        for client_name in FP_CREDENTIALS[_fp_name].keys():
            for key in FP_CREDENTIALS[_fp_name][client_name].keys():
                detail = FP_CREDENTIALS[_fp_name][client_name][key]

                if detail["accountCode"] == account_code:
                    account_detail = detail

    # Startrack
    if _fp_name in ["startrack"]:
        for client_name in FP_CREDENTIALS[_fp_name].keys():
            for key in FP_CREDENTIALS[_fp_name][client_name].keys():
                if key == booking.b_client_warehouse_code:
                    account_detail = FP_CREDENTIALS[_fp_name][client_name][key]
                    return account_detail

    # Allied
    if _fp_name in ["allied"]:
        if settings.ENV != "prod":
            account_detail = FP_CREDENTIALS["allied"]["test"]["test_bed_1"]
        elif booking.b_client_name == "Bathroom Sales Direct":
            account_detail = FP_CREDENTIALS["allied"]["bathroom sales direct"]["live_0"]
        else:
            account_detail = FP_CREDENTIALS["allied"]["dme"]["live_0"]

    # Camerons
    if _fp_name in ["camerons"]:
        account_detail = FP_CREDENTIALS["camerons"]["dme"]["live_0"]

    # DXT
    if _fp_name in ["dxt"]:
        account_detail = FP_CREDENTIALS["dxt"]["dme"]["live_0"]

    # TGE
    if _fp_name == "team global express":
        from api.fps.team_global_express import (
            get_account_detail as get_tge_account_detail,
        )

        account_detail = get_tge_account_detail(booking)

    # DF
    if _fp_name == "direct freight":
        from api.fps.direct_freight import (
            get_account_detail as get_df_account_detail,
        )

        account_detail = get_df_account_detail(booking)

    # MRL Sampson
    if _fp_name == "mrl sampson":
        from api.fps.mrl_sampson import (
            get_account_detail as get_mrl_sampson_account_detail,
        )

        account_detail = get_mrl_sampson_account_detail(booking)

    if not account_detail:
        booking.b_errorCapture = f"Couldn't find Account Detail"
        booking.save()
        raise ValidationError(booking.b_errorCapture)
    else:
        return account_detail


def get_service_provider(fp_name, upper=True, fp_obj=None):
    try:
        _fp_name = fp_name.lower()
        fp = fp_obj

        if not fp:
            fp = Fp_freight_providers.objects.get(fp_company_name__iexact=fp_name)

        if _fp_name == "startrack":
            return "ST" if upper else fp.fp_company_name
        elif _fp_name == "hunter":
            return "HUNTER_V2"
        else:
            return fp_name.upper() if upper else fp.fp_company_name
    except Fp_freight_providers.DoesNotExist:
        logger.error("#810 - Not supported FP!")
        return None


def get_service_name(fp_name, service_code):
    if fp_name in ["startrack", "auspost"]:
        if service_code == "EXP":
            return "EXPRESS"
        elif service_code == "PRM":
            return "PREMIUM"
        elif service_code == "FPP":
            return "1,3 & 5KG FIXED PRICE PREMIUM"
        else:
            return None


def _set_error(booking, error_msg):
    booking.b_error_Capture = str(error_msg)[:999]
    booking.save()


def get_pu_from(booking, fp_name):
    if fp_name == "hunter":
        _pu_from = (
            booking.puPickUpAvailFrom_Date.strftime("%Y-%m-%d")
            if not isinstance(booking.puPickUpAvailFrom_Date, str)
            else booking.puPickUpAvailFrom_Date
        )
        hour = booking.pu_PickUp_Avail_Time_Hours
        minute = booking.pu_PickUp_Avail_Time_Minutes
        _pu_from += f"T{str(hour).zfill(2)}" if hour else "T00"
        _pu_from += f":{str(minute).zfill(2)}" if minute else ":00"
        _pu_from += f"+{TIME_DIFFERENCE}:00"
    elif fp_name == "tnt":
        _pu_from = (
            booking.puPickUpAvailFrom_Date.strftime("%Y-%m-%d")
            if not isinstance(booking.puPickUpAvailFrom_Date, str)
            else booking.puPickUpAvailFrom_Date
        )
        hour = booking.pu_PickUp_Avail_Time_Hours
        minute = booking.pu_PickUp_Avail_Time_Minutes
        _pu_from += f"T{str(hour).zfill(2)}" if hour else "T00"
        _pu_from += f":{str(minute).zfill(2)}:00" if minute else ":00:00"
        _pu_from += f"+{TIME_DIFFERENCE}:00"
    return _pu_from


def get_pu_to(booking, fp_name):
    _pu_to = ""
    hour = booking.pu_PickUp_By_Time_Hours
    minute = booking.pu_PickUp_By_Time_Minutes

    if hour or minute:
        _pu_to += f"{str(hour).zfill(2)}" if hour else "00"
        _pu_to += f":{str(minute).zfill(2)}" if minute else ":00"
        _pu_to += f"+{TIME_DIFFERENCE}:00"
        return _pu_to


def get_de_from(booking, fp_name):
    if booking.de_Deliver_From_Date:
        _de_from = booking.de_Deliver_From_Date.strftime("%Y-%m-%d")
        hour = booking.de_Deliver_From_Hours
        minute = booking.de_Deliver_From_Minutes
        _de_from += f"T{str(hour).zfill(2)}" if hour else "T00"
        _de_from += f":{str(minute).zfill(2)}" if minute else ":00"
        _de_from += f"+{TIME_DIFFERENCE}:00"
        return _de_from


def get_de_to(booking, fp_name):
    _de_to = ""
    hour = booking.de_Deliver_By_Hours
    minute = booking.de_Deliver_By_Minutes

    if hour or minute:
        _de_to += f"{str(hour).zfill(2)}" if hour else "00"
        _de_to += f":{str(minute).zfill(2)}" if minute else ":00"
        _de_to += f"+{TIME_DIFFERENCE}:00"
        return _de_to


def get_tracking_payload(bookingOrBookings, fp_name, bulk_mode=False):
    try:
        payload = {}
        consignmentDetails = []
        payload["serviceProvider"] = get_service_provider(fp_name)

        if bulk_mode:
            bookings = bookingOrBookings
            payload["spAccountDetails"] = get_account_detail(bookings[0], fp_name)

            for booking in bookings:
                consignmentDetails.append(
                    {
                        "consignmentNumber": booking.v_FPBookingNumber,
                        "connote": booking.jobNumber,
                    }
                )

            payload["consignmentDetails"] = consignmentDetails
        elif fp_name.lower() == "team global express":
            booking = bookingOrBookings
            payload["spAccountDetails"] = get_account_detail(booking, fp_name)
            payload["consignmentNumber"] = booking.v_FPBookingNumber
            payload["de_to_address_postcode"] = booking.de_To_Address_PostalCode
        else:
            booking = bookingOrBookings
            payload["spAccountDetails"] = get_account_detail(booking, fp_name)
            consignmentDetails.append(
                {
                    "consignmentNumber": booking.v_FPBookingNumber,
                    "connote": booking.jobNumber,
                    "de_to_address_postcode": booking.de_To_Address_PostalCode,
                }
            )
            payload["consignmentDetails"] = consignmentDetails

        return payload
    except Exception as e:
        trace_error.print()
        logger.error(f"#400 - Error while build payload: {e}")
        return None


def get_book_payload(booking, fp_name):
    payload = {}
    payload["spAccountDetails"] = get_account_detail(booking, fp_name)
    payload["serviceProvider"] = get_service_provider(fp_name)
    payload["readyDate"] = str(booking.puPickUpAvailFrom_Date or date.today())

    # JasonL
    if booking.kf_client_id == "1af6bcd2-6148-11eb-ae93-0242ac130002":
        # # TNT -> book with DME's TNT
        # if fp_name == "tnt":
        #     payload["spAccountDetails"] = {
        #         "accountCode": "30021385",
        #         "accountKey": "30021385",
        #         "accountState": "DELME",
        #         "accountPassword": "Deliver123",
        #         "accountUsername": "CIT00000000000098839",
        #     }
        if fp_name == "team global express":
            if date.today().weekday() == 5:
                payload["readyDate"] = str(date.today() + timedelta(days=2))
            elif date.today().weekday() == 6:
                payload["readyDate"] = str(date.today() + timedelta(days=1))
            else:
                payload["readyDate"] = str(date.today())

    payload["referenceNumber"] = booking.b_clientReference_RA_Numbers or ""

    client_process = None
    if hasattr(booking, "id"):
        client_process = (
            Client_Process_Mgr.objects.select_related()
            .filter(fk_booking_id=booking.id)
            .first()
        )

    if client_process:
        puCompany = client_process.origin_puCompany
        pu_Address_Street_1 = client_process.origin_pu_Address_Street_1
        pu_Address_street_2 = client_process.origin_pu_Address_Street_2
        pu_pickup_instructions_address = (
            client_process.origin_pu_pickup_instructions_address
        )
        deToCompanyName = client_process.origin_deToCompanyName
        de_Email = client_process.origin_de_Email
        # de_Email_Group_Emails = client_process.origin_de_Email_Group_Emails
        de_To_Address_Street_1 = client_process.origin_de_To_Address_Street_1
        de_To_Address_Street_2 = client_process.origin_de_To_Address_Street_2
    else:
        puCompany = booking.puCompany
        pu_Address_Street_1 = booking.pu_Address_Street_1
        pu_Address_street_2 = booking.pu_Address_street_2
        pu_pickup_instructions_address = booking.pu_pickup_instructions_address
        deToCompanyName = booking.deToCompanyName
        de_Email = booking.de_Email
        # de_Email_Group_Emails = booking.de_Email_Group_Emails
        de_To_Address_Street_1 = booking.de_To_Address_Street_1
        de_To_Address_Street_2 = booking.de_To_Address_Street_2

    payload["serviceType"] = booking.vx_serviceName or "R"
    payload["bookedBy"] = "DME"
    payload["pickupAddress"] = {
        "companyName": (puCompany or "")[:30],
        "contact": (booking.pu_Contact_F_L_Name or " ")[:19],
        "emailAddress": booking.pu_Email or "pu@email.com",
        "instruction": "",
        "contactPhoneAreaCode": "0",
        "phoneNumber": compact_number(booking.pu_Phone_Main) or "0283111500",
    }

    payload["pickupAddress"]["instruction"] = " "
    if pu_pickup_instructions_address:
        payload["pickupAddress"]["instruction"] = f"{pu_pickup_instructions_address}"
    if booking.pu_PickUp_Instructions_Contact:
        payload["pickupAddress"][
            "instruction"
        ] += f" {booking.pu_PickUp_Instructions_Contact}"

    payload["pickupAddress"]["postalAddress"] = {
        "address1": pu_Address_Street_1 or "",
        "address2": pu_Address_street_2 or "_",
        "country": booking.pu_Address_Country or "",
        "postCode": booking.pu_Address_PostalCode or "",
        "state": booking.pu_Address_State or "",
        "suburb": booking.pu_Address_Suburb or "",
        "sortCode": booking.pu_Address_PostalCode or "",
    }
    payload["dropAddress"] = {
        "companyName": (deToCompanyName or "")[:30],
        "contact": (booking.de_to_Contact_F_LName or " ")[:19],
        "emailAddress": de_Email or "de@email.com",
        "instruction": "",
        "contactPhoneAreaCode": "0",
        "phoneNumber": compact_number(booking.de_to_Phone_Main) or "0283111500",
    }

    payload["dropAddress"]["instruction"] = " "
    if booking.de_to_PickUp_Instructions_Address:
        payload["dropAddress"][
            "instruction"
        ] = f"{booking.de_to_PickUp_Instructions_Address}"
    if booking.de_to_Pick_Up_Instructions_Contact:
        payload["dropAddress"][
            "instruction"
        ] += f" {booking.de_to_Pick_Up_Instructions_Contact}"

    de_To_Address_Street_1 = (de_To_Address_Street_1 or "").strip()
    de_street_1 = de_To_Address_Street_1 or de_To_Address_Street_2 or "_"
    de_street_2 = de_To_Address_Street_2 or "_"

    if not de_street_1 and not de_street_2:
        message = f"DE street info is required. BookingId: {booking.b_bookingID_Visual}"
        logger.error(message)
        raise Exception(message)

    payload["dropAddress"]["postalAddress"] = {
        "address1": de_street_1,
        "address2": de_street_2 if de_street_1 != de_street_2 else "_",
        "country": booking.de_To_Address_Country or "",
        "postCode": booking.de_To_Address_PostalCode or "",
        "state": booking.de_To_Address_State or "",
        "suburb": booking.de_To_Address_Suburb or "",
        "sortCode": booking.de_To_Address_PostalCode or "",
    }

    booking_lines = Booking_lines.objects.filter(
        fk_booking_id=booking.pk_booking_id, is_deleted=False
    ).order_by("pk_lines_id")
    scanned_lines = booking_lines.filter(packed_status=Booking_lines.SCANNED_PACK)

    if scanned_lines:
        booking_lines = scanned_lines
    elif booking.api_booking_quote:
        packed_status = booking.api_booking_quote.packed_status
        booking_lines = booking_lines.filter(packed_status=packed_status)
    else:
        booking_lines = booking_lines.filter(packed_status=Booking_lines.ORIGINAL)

    items = []
    totalWeight = 0
    maxHeight = 0
    maxWidth = 0
    maxLength = 0

    if fp_name == "startrack" and booking.b_client_warehouse_code in [
        "BIO - RIC",
        "BIO - HAZ",
        "BIO - EAS",
        "BIO - TRU",
    ]:
        consignment_id = gen_consignment_num("startrack", None, None, booking)

    booking_lines_data = Booking_lines_data.objects.filter(
        fk_booking_id=booking.pk_booking_id
    )

    sequence = 0
    gaps, clientRefNumbers = [], []
    for line in booking_lines:
        for line_data in booking_lines_data:
            if line_data.gap_ra:
                gaps.append(line_data.gap_ra)
            if line_data.clientRefNumber:
                clientRefNumbers.append(line_data.clientRefNumber)

        width = _convert_UOM(line.e_dimWidth, line.e_dimUOM, "dim", fp_name)
        height = _convert_UOM(line.e_dimHeight, line.e_dimUOM, "dim", fp_name)
        length = _convert_UOM(line.e_dimLength, line.e_dimUOM, "dim", fp_name)
        weight = _convert_UOM(line.e_weightPerEach, line.e_weightUOM, "weight", fp_name)

        for i in range(line.e_qty):
            volume = round(width * height * length / 1000000, 5)
            item = {
                "dangerous": 0,
                "width": width or 0,
                "height": height or 0,
                "length": length or 0,
                "quantity": 1,
                "volume": max(volume, 0.01),
                "weight": weight or 0,
                "reference": line.sscc if line.e_qty == 1 and line.sscc else "",
                "description": line.e_item,
            }

            _is_pallet = is_pallet(line.e_type_of_packaging)
            if fp_name == "startrack":
                item["itemId"] = "EXP"
                item["packagingType"] = "PLT" if _is_pallet else "CTN"

                if booking.b_client_warehouse_code in [
                    "BIO - RIC",
                    "BIO - HAZ",
                    "BIO - EAS",
                    "BIO - TRU",
                ]:
                    sequence_no = str(sequence + 1).zfill(5)
                    article_id = f"{consignment_id}{item['itemId']}{sequence_no}"
                    barcode_id = article_id
                    item["trackingDetails"] = {
                        "consignment_id": consignment_id,
                        "article_id": article_id,
                        "barcode_id": barcode_id,
                    }
            elif fp_name == "auspost":
                item["itemId"] = "7E55"  # PARCEL POST + SIGNATURE
            elif fp_name == "hunter":
                item["packagingType"] = "PLT" if _is_pallet else "CTN"
            elif fp_name == "tnt":
                item["packagingType"] = "D"
            elif fp_name == "team global express":
                if booking.b_client_name != "BioPak":
                    item["length"] = math.ceil(item["length"])
                    item["width"] = math.ceil(item["width"])
                    item["height"] = math.ceil(item["height"])
                    item["weight"] = math.ceil(item["weight"])

                item["reference1"] = ",".join(gaps)[-13:]
                item["reference2"] = ",".join(clientRefNumbers)[-13:]
                item["sscc"] = gen_sscc_tge(booking, line, i)

                # Tempo Big W | Tempo Pty Ltd
                if booking.kf_client_id in [
                    "d69f550a-9327-4ff9-bc8f-242dfca00f7e",
                    "37C19636-C5F9-424D-AD17-05A056A8FBDB",
                ]:
                    for line_data in booking_lines_data:
                        if line_data.fk_booking_lines_id == line.pk_booking_lines_id:
                            item["reference1"] = (line_data.clientRefNumber)[:13]
                            item["reference2"] = (line_data.gap_ra or "")[:13]
                            break

                if item["reference2"] and not item["reference1"]:
                    item["reference1"] = item["reference2"]
                    item["reference2"] = "_"
            elif fp_name == "direct freight":
                item["PackageDescription"] = (
                    "PLAIN PALLET" if _is_pallet else "Carton of Goods"
                )
                item["IsAuthorityToLeave"] = booking.opt_authority_to_leave
            elif fp_name == "camerons":
                item["packagingType"] = "PALLET" if _is_pallet else "CARTON"
                item["sscc"] = gen_sscc_camerons(booking, line, i)
            elif fp_name == "dhl":
                item["packagingType"] = "PLT" if _is_pallet else "CTN"
                fp_carrier = FP_carriers.objects.get(carrier="DHLPFM")
                consignmentNoteNumber = gen_consignment_num(
                    "dhl", booking.b_bookingID_Visual
                )

                labelCode = str(fp_carrier.label_start_value + fp_carrier.current_value)
                fp_carrier.current_value = fp_carrier.current_value + 1
                fp_carrier.save()

                # Create api_bcls
                Api_booking_confirmation_lines(
                    fk_booking_id=booking.pk_booking_id,
                    fk_booking_line_id=line.pk_lines_id,
                    api_item_id=labelCode,
                    service_provider=booking.vx_freight_provider,
                    label_code=labelCode,
                    client_item_reference=line.client_item_reference,
                ).save()
                item["packageCode"] = labelCode

            sequence += 1
            items.append(item)

            if line.e_weightPerEach:
                totalWeight += weight
            if maxHeight < height:
                maxHeight = height
            if maxWidth < width:
                maxWidth = width
            if maxLength < length:
                maxLength = length

    payload["items"] = items
    pu_inst = payload["pickupAddress"]["instruction"]
    de_inst = payload["dropAddress"]["instruction"]

    # Detail for each FP
    if fp_name == "allied":
        payload["serviceType"] = "R"
        payload["docketNumber"] = gen_consignment_num(
            "allied", booking.b_bookingID_Visual
        )
        payload["instructions"] = ""
        if pu_inst:
            payload["instructions"] = f"{pu_inst}"
        if de_inst and de_inst != " ":
            payload["instructions"] += f" {de_inst}"

    if fp_name == "hunter":
        if booking.vx_serviceName == "Road Freight":
            payload["serviceType"] = "RF"
        elif booking.vx_serviceName == "Air Freight":
            payload["serviceType"] = "AF"
        elif booking.vx_serviceName == "Re-Delivery":
            payload["serviceType"] = "RDL"
        elif booking.vx_serviceName == "Same Day Air Freight":
            payload["serviceType"] = "SDX"

        if booking.b_client_order_num:
            payload["reference1"] = booking.b_client_order_num
        elif booking.clientRefNumbers:
            payload["reference1"] = booking.clientRefNumbers
        elif booking.b_client_sales_inv_num:
            payload["reference1"] = booking.b_client_sales_inv_num
        else:
            payload["reference1"] = "reference1"

        # V2 fields
        payload["SenderReference"] = booking.clientRefNumbers
        payload["ReceiverReference"] = booking.gap_ras
        payload["ConsignmentSenderIsResidential"] = (
            "y" if booking.pu_Address_Type == "residential" else "n"
        )
        payload["ConsignmentReceiverIsResidential"] = (
            "y" if booking.de_To_AddressType == "residential" else "n"
        )
        payload["SpecialInstructions"] = booking.b_handling_Instructions or ""

        payload["consignmentNoteNumber"] = gen_consignment_num(
            "hunter", booking.b_bookingID_Visual, booking.kf_client_id
        )
        payload["ConsignmentPickupBookingTime"] = get_pu_from(booking, fp_name)
        payload["ConsignmentPickupBookingTimeTo"] = get_pu_to(booking, fp_name) or ""
        payload["ConsignmentBookingDateTime"] = get_de_from(booking, fp_name) or ""
        payload["ConsignmentBookingDateTimeTo"] = get_de_to(booking, fp_name) or ""

        # Plum
        if booking.kf_client_id == "461162D2-90C7-BF4E-A905-000000000004":
            payload["reference2"] = gen_consignment_num(
                "hunter", booking.b_bookingID_Visual, booking.kf_client_id
            )

        payload["connoteFormat"] = "Thermal"  # For `Thermal` type printers
    elif fp_name == "tnt":  # TNT
        payload["pickupAddressCopy"] = payload["pickupAddress"]
        payload["itemCount"] = len(items)
        payload["totalWeight"] = totalWeight
        payload["maxHeight"] = int(maxHeight)
        payload["maxWidth"] = int(maxWidth)
        payload["maxLength"] = int(maxLength)
        payload["packagingCode"] = "CT"
        payload["collectionDateTime"] = get_pu_from(booking, fp_name)

        if booking.pu_PickUp_By_Time_Hours:
            payload["collectionCloseTime"] = str(booking.pu_PickUp_By_Time_Hours).zfill(
                2
            )

            if booking.pu_PickUp_By_Time_Minutes:
                payload["collectionCloseTime"] += str(
                    booking.pu_PickUp_By_Time_Minutes
                ).zfill(2)
            else:
                payload["collectionCloseTime"] += "00"
        else:
            payload["collectionCloseTime"] = "1500"

        if booking.api_booking_quote:
            payload["serviceCode"] = get_tnt_service_code(
                booking.api_booking_quote.service_name
            )

        payload["collectionInstructions"] = " "
        if pu_inst:
            payload["collectionInstructions"] = f"{pu_inst}"
        if de_inst:
            payload["collectionInstructions"] += f" {de_inst}"

        payload["consignmentNoteNumber"] = gen_consignment_num(
            "tnt", booking.b_bookingID_Visual
        )

        if booking.kf_client_id == "1af6bcd2-6148-11eb-ae93-0242ac130002":  # Jason L
            payload["customerReference"] = booking.b_client_sales_inv_num or ""
        elif booking.kf_client_id == "49294ca3-2adb-4a6e-9c55-9b56c0361953":  # AP
            payload["customerReference"] = booking.b_client_sales_inv_num or ""
        else:
            payload["customerReference"] = booking.clientRefNumbers

        payload["isDangerousGoods"] = False

        # JasonL
        if booking.kf_client_id == "1af6bcd2-6148-11eb-ae93-0242ac130002":
            payload["payer"] = "Sender"
            payload["receiver_Account"] = ""
        else:
            payload["payer"] = "Receiver"
            payload["receiver_Account"] = "30021385"
    elif fp_name == "capital":  # Capital
        payload["serviceType"] = "EC"
    elif fp_name == "camerons":  # Camerons
        payload["consignmentNumber"] = gen_consignment_num(
            "camerons", booking.b_bookingID_Visual
        )
        pu_from = booking.puPickUpAvailFrom_Date or date.today()

        if (
            booking.pu_Address_State.upper() == "WA"
            or booking.de_To_Address_State.upper() == "WA"
        ):
            de_from = pu_from + timedelta(days=7)
        else:
            de_from = pu_from + timedelta(days=3)

        pu_from = convert_to_AU_SYDNEY_tz(pu_from)
        pu_from_str = pu_from.strftime("%Y-%m-%d") + " 09:00+10:00"
        de_from = convert_to_AU_SYDNEY_tz(de_from)
        de_from_str = de_from.strftime("%Y-%m-%d") + " 13:00+10:00"
        payload["pickupFromTime"] = pu_from_str
        payload["deliveryFromTime"] = de_from_str

        if booking.b_client_order_num:
            payload["reference1"] = booking.b_client_order_num
        elif booking.clientRefNumbers:
            payload["reference1"] = booking.clientRefNumbers
        elif booking.b_client_sales_inv_num:
            payload["reference1"] = booking.b_client_sales_inv_num
        else:
            payload["reference1"] = "reference1"
    elif fp_name == "dhl":  # DHL
        if booking.kf_client_id == "461162D2-90C7-BF4E-A905-000000000002":
            payload["clientType"] = "aldi"
            payload["consignmentNoteNumber"] = gen_consignment_num(
                "dhl", booking.b_bookingID_Visual
            )
            payload["orderNumber"] = booking.pk_booking_id
            booking.b_client_sales_inv_num = booking.pk_booking_id
            booking.save()
            utl_state = Utl_states.objects.get(state_code=booking.pu_Address_State)

            if not utl_state.sender_code:
                error_msg = "Not supported PU state"
                _set_error(error_msg)
                raise Exception(error_msg)
        else:
            payload["clientType"] = "***"
    elif fp_name == "sendle":  # Sendle
        if payload["pickupAddress"]["instruction"] == " ":
            payload["pickupAddress"]["instruction"] = "_"

        if payload["dropAddress"]["instruction"] == " ":
            payload["dropAddress"]["instruction"] = "_"
    elif fp_name == "direct freight":  # Direct Freight
        payload["ConsignmentId"] = booking.b_bookingID_Visual
    elif fp_name == "team global express":
        payload["IsAuthorityToLeave"] = booking.opt_authority_to_leave
        payload["pickupEntity"] = payload["pickupAddress"]
        payload["dropEntity"] = payload["dropAddress"]
        payload["pickupEntity"]["address"] = payload["pickupEntity"]["postalAddress"]
        payload["dropEntity"]["address"] = payload["dropEntity"]["postalAddress"]
        pu_phone = payload["dropAddress"]["phoneNumber"]
        de_phone = payload["dropAddress"]["phoneNumber"]

        # Address Type
        pu_address_type = (booking.pu_Address_Type or "Business").title()
        payload["pickupEntity"]["address"]["addressType"] = pu_address_type
        payload["pickupEntity"]["address"]["country"] = "AU"
        de_To_AddressType = (booking.de_To_AddressType or "Business").title()
        payload["dropEntity"]["address"]["addressType"] = de_To_AddressType
        payload["dropEntity"]["address"]["country"] = "AU"

        del payload["pickupAddress"]
        del payload["dropAddress"]
        del payload["pickupEntity"]["postalAddress"]
        del payload["dropEntity"]["postalAddress"]

        payload["consignmentNumber"] = gen_consignment_num(
            fp_name,
            booking.b_bookingID_Visual,
            booking.kf_client_id,
            booking,
        )
        payload["specialInstructions"] = f"Pickup: {pu_phone}, Delivery: {de_phone}"

        # Tempo Big W
        if booking.kf_client_id == "d69f550a-9327-4ff9-bc8f-242dfca00f7e":
            referenceNumber = payload["referenceNumber"] or ""
            payload["referenceNumber"] = referenceNumber.split(", ")[0]

    return payload


# def get_spojit_book_payload(booking, fp_name):
#     payload = {}
#     payload["id"] = booking.id
#     payload["serviceProvider"] = get_service_provider(fp_name)
#     payload["readyDate"] = str(booking.puPickUpAvailFrom_Date or date.today())

#     payload["clientRefNumbers"] = booking.clientRefNumbers or ""
#     payload["referenceNumber"] = booking.b_client_order_num or ""
#     payload["consignmentNumber"] = booking.v_FPBookingNumber or ""
#     payload["deliveryDate"] = str(booking.s_06_Latest_Delivery_Date_TimeSet) or ""


#     payload["SenderReference"] = booking.clientRefNumbers
#     payload["ReceiverReference"] = booking.gap_ras

#     payload["SenderTail"] = "Y" if booking.b_booking_tail_lift_pickup == True else "N"

#     payload["SenderHand"] = (
#         "Y"
#         if booking.pu_no_of_assists and int(booking.pu_no_of_assists) > 1
#         else "N"
#     )  # SendHand

#     payload["ReceiverTail"] = "Y" if booking.b_booking_tail_lift_deliver == True else "N"

#     payload["ReceiverHand"] = (
#         "Y"
#         if booking.de_no_of_assists and int(booking.de_no_of_assists) > 1
#         else "N"
#     )  # RecHand

#     payload["SenderResidential"] = "Y" if booking.pu_Address_Type == "residential" else "N"

#     payload["ReceiverResidential"]  = "Y" if booking.de_To_AddressType == "residential" else "N"

#     payload["SpecialInstructions"] = booking.b_handling_Instructions or ""

#     time_ready_hours = "12"
#     time_ready_minutes = "00"
#     if booking.pu_PickUp_Avail_Time_Hours:
#         time_ready_hours = str(booking.pu_PickUp_Avail_Time_Hours).zfill(2)
#     if booking.pu_PickUp_Avail_Time_Minutes:
#         time_ready_minutes = str(booking.pu_PickUp_Avail_Time_Minutes).zfill(2)

#     # TimeReady
#     time_ready_hours = "12"
#     time_ready_minutes = "00"
#     if booking.pu_PickUp_Avail_Time_Hours:
#         time_ready_hours = str(booking.pu_PickUp_Avail_Time_Hours).zfill(2)
#     if booking.pu_PickUp_Avail_Time_Minutes:
#         time_ready_minutes = str(booking.pu_PickUp_Avail_Time_Minutes).zfill(2)
#     payload["TimeReady"] = f"{time_ready_hours}:{time_ready_minutes}"

#     # TimeClose
#     time_close_hours = "15"
#     time_close_minutes = "00"
#     if booking.pu_PickUp_By_Time_Hours:
#         time_close_hours = str(booking.pu_PickUp_By_Time_Hours).zfill(2)
#     if booking.pu_PickUp_By_Time_Minutes:
#         time_close_minutes = str(booking.pu_PickUp_By_Time_Minutes).zfill(2)

#     payload["TimeClose"] = f"{time_close_hours}:{time_close_minutes}"

#     # DeliveryTimeClose
#     time_close_hours = "15"
#     time_close_minutes = "00"
#     if booking.de_Deliver_By_Hours:
#         time_close_hours = str(booking.de_Deliver_By_Hours).zfill(2)
#     if booking.de_Deliver_By_Minutes:
#         time_close_minutes = str(booking.de_Deliver_By_Minutes).zfill(2)

#     payload["DeliveryTimeClose"] = f"{time_close_hours}:{time_close_minutes}"

#     client_process = None
#     if hasattr(booking, "id"):
#         client_process = (
#             Client_Process_Mgr.objects.select_related()
#             .filter(fk_booking_id=booking.id)
#             .first()
#         )

#     if client_process:
#         puCompany = client_process.origin_puCompany
#         pu_Address_Street_1 = client_process.origin_pu_Address_Street_1
#         pu_Address_street_2 = client_process.origin_pu_Address_Street_2
#         pu_pickup_instructions_address = (
#             client_process.origin_pu_pickup_instructions_address
#         )
#         deToCompanyName = client_process.origin_deToCompanyName
#         de_Email = client_process.origin_de_Email
#         # de_Email_Group_Emails = client_process.origin_de_Email_Group_Emails
#         de_To_Address_Street_1 = client_process.origin_de_To_Address_Street_1
#         de_To_Address_Street_2 = client_process.origin_de_To_Address_Street_2
#     else:
#         puCompany = booking.puCompany
#         pu_Address_Street_1 = booking.pu_Address_Street_1
#         pu_Address_street_2 = booking.pu_Address_street_2
#         pu_pickup_instructions_address = booking.pu_pickup_instructions_address
#         deToCompanyName = booking.deToCompanyName
#         de_Email = booking.de_Email
#         # de_Email_Group_Emails = booking.de_Email_Group_Emails
#         de_To_Address_Street_1 = booking.de_To_Address_Street_1
#         de_To_Address_Street_2 = booking.de_To_Address_Street_2

#     payload["serviceType"] = booking.vx_serviceName or "R"
#     payload["bookedBy"] = "DME"
#     payload["pickupAddress"] = {
#         "companyName": puCompany or "",
#         "contact": (booking.pu_Contact_F_L_Name or " ")[:19],
#         "emailAddress": booking.pu_Email or "pu@email.com",
#         "instruction": "",
#         "contactPhoneAreaCode": "0",
#         "phoneNumber": compact_number(booking.pu_Phone_Main) or "0283111500",
#     }

#     payload["pickupAddress"]["instruction"] = " "
#     if pu_pickup_instructions_address:
#         payload["pickupAddress"]["instruction"] = f"{pu_pickup_instructions_address}"
#     if booking.pu_PickUp_Instructions_Contact:
#         payload["pickupAddress"][
#             "instruction"
#         ] += f" {booking.pu_PickUp_Instructions_Contact}"

#     payload["pickupAddress"]["postalAddress"] = {
#         "address1": pu_Address_Street_1 or "",
#         "address2": pu_Address_street_2 or "_",
#         "country": booking.pu_Address_Country or "",
#         "postCode": booking.pu_Address_PostalCode or "",
#         "state": booking.pu_Address_State or "",
#         "suburb": booking.pu_Address_Suburb or "",
#         "sortCode": booking.pu_Address_PostalCode or "",
#     }
#     payload["dropAddress"] = {
#         "companyName": deToCompanyName or "",
#         "contact": (booking.de_to_Contact_F_LName or " ")[:19],
#         "emailAddress": de_Email or "de@email.com",
#         "instruction": "",
#         "contactPhoneAreaCode": "0",
#         "phoneNumber": compact_number(booking.de_to_Phone_Main) or "0283111500",
#     }

#     payload["dropAddress"]["instruction"] = " "
#     if booking.de_to_PickUp_Instructions_Address:
#         payload["dropAddress"][
#             "instruction"
#         ] = f"{booking.de_to_PickUp_Instructions_Address}"
#     if booking.de_to_Pick_Up_Instructions_Contact:
#         payload["dropAddress"][
#             "instruction"
#         ] += f" {booking.de_to_Pick_Up_Instructions_Contact}"

#     de_To_Address_Street_1 = (de_To_Address_Street_1 or "").strip()
#     de_street_1 = de_To_Address_Street_1 or de_To_Address_Street_2 or ""
#     de_street_2 = de_To_Address_Street_2 or ""

#     payload["dropAddress"]["postalAddress"] = {
#         "address1": de_street_1,
#         "address2": de_street_2 if de_street_1 != de_street_2 else "_",
#         "country": booking.de_To_Address_Country or "",
#         "postCode": booking.de_To_Address_PostalCode or "",
#         "state": booking.de_To_Address_State or "",
#         "suburb": booking.de_To_Address_Suburb or "",
#         "sortCode": booking.de_To_Address_PostalCode or "",
#     }

#     booking_lines = Booking_lines.objects.filter(
#         fk_booking_id=booking.pk_booking_id, is_deleted=False
#     ).order_by("pk_lines_id")
#     scanned_lines = booking_lines.filter(packed_status=Booking_lines.SCANNED_PACK)

#     if scanned_lines:
#         booking_lines = scanned_lines
#     elif booking.api_booking_quote:
#         packed_status = booking.api_booking_quote.packed_status
#         booking_lines = booking_lines.filter(packed_status=packed_status)
#     else:
#         booking_lines = booking_lines.filter(packed_status=Booking_lines.ORIGINAL)

#     items = []
#     totalWeight = 0
#     maxHeight = 0
#     maxWidth = 0
#     maxLength = 0

#     booking_lines_data = Booking_lines_data.objects.filter(
#         fk_booking_id=booking.pk_booking_id
#     )

#     sequence = 0
#     payload["dangerousGoods"] = "N"

#     for line in booking_lines:
#         gaps = []
#         clientRefNumbers = []
#         for line_data in booking_lines_data:
#             if line_data.gap_ra:
#                 gaps.append(line_data.gap_ra)
#             if line_data.clientRefNumber:
#                 clientRefNumbers.append(line_data.clientRefNumber)

#         width = _convert_UOM(line.e_dimWidth, line.e_dimUOM, "dim", fp_name)
#         height = _convert_UOM(line.e_dimHeight, line.e_dimUOM, "dim", fp_name)
#         length = _convert_UOM(line.e_dimLength, line.e_dimUOM, "dim", fp_name)
#         weight = _convert_UOM(line.e_weightPerEach, line.e_weightUOM, "weight", fp_name)

#         if line.e_dangerousGoods == True:
#             payload["dangerousGoods"] = "Y"

#         for i in range(line.e_qty):
#             volume = round(width * height * length / 1000000, 5)
#             item = {
#                 "dangerous": "Y" if line.e_dangerousGoods == True else "N",
#                 "width": width or 0,
#                 "height": height or 0,
#                 "length": length or 0,
#                 "quantity": 1,
#                 "volume": max(volume, 0.01),
#                 "weight": weight or 0,
#                 "reference": line.sscc if line.e_qty == 1 and line.sscc else "",
#                 "description": line.e_item,
#                 "type": line.e_type_of_packaging,
#                 "barcode": f"{booking.v_FPBookingNumber}{i + 1}",
#             }

#             sequence += 1
#             items.append(item)

#             if line.e_weightPerEach:
#                 totalWeight += weight
#             if maxHeight < height:
#                 maxHeight = height
#             if maxWidth < width:
#                 maxWidth = width
#             if maxLength < length:
#                 maxLength = length

#     payload["items"] = items

#     return payload


def get_cancel_book_payload(booking, fp_name):
    try:
        payload = {}
        payload["spAccountDetails"] = get_account_detail(booking, fp_name)
        payload["serviceProvider"] = get_service_provider(fp_name)
        payload["consignmentNumbers"] = [booking.fk_fp_pickup_id]

        return payload
    except Exception as e:
        logger.error(f"#402 - Error while build payload: {e}")
        return None


def get_getlabel_payload(booking, fp_name):
    payload = {}
    payload["spAccountDetails"] = get_account_detail(booking, fp_name)
    payload["serviceProvider"] = get_service_provider(fp_name)

    # # JasonL + TNT -> book with DME's TNT
    # if booking.kf_client_id == "1af6bcd2-6148-11eb-ae93-0242ac130002":
    #     if fp_name.upper() == "tnt":
    #         payload["spAccountDetails"] = {
    #             "accountCode": "30021385",
    #             "accountKey": "30021385",
    #             "accountState": "DELME",
    #             "accountPassword": "Deliver123",
    #             "accountUsername": "CIT00000000000098839",
    #         }

    client_process = None
    if hasattr(booking, "id"):
        client_process = (
            Client_Process_Mgr.objects.select_related()
            .filter(fk_booking_id=booking.id)
            .first()
        )

    if client_process:
        puCompany = client_process.origin_puCompany
        pu_Address_Street_1 = client_process.origin_pu_Address_Street_1
        pu_Address_street_2 = client_process.origin_pu_Address_Street_2
        pu_pickup_instructions_address = (
            client_process.origin_pu_pickup_instructions_address
        )
        deToCompanyName = client_process.origin_deToCompanyName
        de_Email = client_process.origin_de_Email
        # de_Email_Group_Emails = client_process.origin_de_Email_Group_Emails
        de_To_Address_Street_1 = client_process.origin_de_To_Address_Street_1
        de_To_Address_Street_2 = client_process.origin_de_To_Address_Street_2
    else:
        puCompany = booking.puCompany
        pu_Address_Street_1 = booking.pu_Address_Street_1
        pu_Address_street_2 = booking.pu_Address_street_2
        pu_pickup_instructions_address = booking.pu_pickup_instructions_address
        deToCompanyName = booking.deToCompanyName
        de_Email = booking.de_Email
        # de_Email_Group_Emails = booking.de_Email_Group_Emails
        de_To_Address_Street_1 = booking.de_To_Address_Street_1
        de_To_Address_Street_2 = booking.de_To_Address_Street_2

    payload["pickupAddress"] = {
        "companyName": (puCompany or "")[:30],
        "contact": (booking.pu_Contact_F_L_Name or " ")[:19],
        "emailAddress": booking.pu_Email or "pu@email.com",
        "instruction": "",
        "contactPhoneAreaCode": "0",
        "phoneNumber": booking.pu_Phone_Main or "0283111500",
    }

    payload["pickupAddress"]["instruction"] = " "
    if pu_pickup_instructions_address:
        payload["pickupAddress"]["instruction"] = f"{pu_pickup_instructions_address}"
    if booking.pu_PickUp_Instructions_Contact:
        payload["pickupAddress"][
            "instruction"
        ] += f" {booking.pu_PickUp_Instructions_Contact}"

    payload["pickupAddress"]["postalAddress"] = {
        "address1": (pu_Address_Street_1 or "")[:29],
        "address2": pu_Address_street_2 or "",
        "country": booking.pu_Address_Country or "",
        "postCode": booking.pu_Address_PostalCode or "",
        "state": booking.pu_Address_State or "",
        "suburb": booking.pu_Address_Suburb or "",
        "sortCode": booking.pu_Address_PostalCode or "",
    }
    payload["dropAddress"] = {
        "companyName": (deToCompanyName or "")[:30],
        "contact": (booking.de_to_Contact_F_LName or " ")[:19],
        "emailAddress": de_Email or "de@email.com",
        "instruction": "",
        "contactPhoneAreaCode": "0",
        "phoneNumber": booking.de_to_Phone_Main or "",
    }

    payload["dropAddress"]["instruction"] = " "
    if booking.de_to_PickUp_Instructions_Address:
        payload["dropAddress"][
            "instruction"
        ] = f"{booking.de_to_PickUp_Instructions_Address}"
    if booking.de_to_Pick_Up_Instructions_Contact:
        payload["dropAddress"][
            "instruction"
        ] += f" {booking.de_to_Pick_Up_Instructions_Contact}"

    de_To_Address_Street_1 = (de_To_Address_Street_1 or "").strip()
    de_street_1 = de_To_Address_Street_1 or de_To_Address_Street_2 or ""
    de_street_2 = de_To_Address_Street_2 or ""

    if not de_street_1 and not de_street_2:
        message = f"DE street info is required. BookingId: {booking.b_bookingID_Visual}"
        logger.error(message)
        raise Exception(message)

    if de_street_1 == de_street_2:
        de_street_2 = ""

    payload["dropAddress"]["postalAddress"] = {
        "address1": de_street_1[:29],
        "address2": de_street_2 if de_street_1 != de_street_2 else "_",
        "country": booking.de_To_Address_Country or "",
        "postCode": booking.de_To_Address_PostalCode or "",
        "state": booking.de_To_Address_State or "",
        "suburb": booking.de_To_Address_Suburb or "",
        "sortCode": booking.de_To_Address_PostalCode or "",
    }

    booking_lines = Booking_lines.objects.filter(
        fk_booking_id=booking.pk_booking_id, is_deleted=False
    )

    if booking.api_booking_quote:
        packed_status = booking.api_booking_quote.packed_status
        booking_lines = booking_lines.filter(packed_status=packed_status)
    else:
        scanned_lines = booking_lines.filter(packed_status=Booking_lines.SCANNED_PACK)
        booking_lines = scanned_lines if scanned_lines else booking_linesc

    items = []
    for line in booking_lines:
        booking_lines_data = Booking_lines_data.objects.filter(
            fk_booking_lines_id=line.pk_booking_lines_id
        )

        descriptions = []
        gaps = []
        for line_data in booking_lines_data:
            if line_data.itemDescription:
                descriptions.append(line_data.itemDescription[:19])

            if line_data.gap_ra:
                gaps.append(line_data.gap_ra)

        width = _convert_UOM(line.e_dimWidth, line.e_dimUOM, "dim", fp_name.lower())
        height = _convert_UOM(line.e_dimHeight, line.e_dimUOM, "dim", fp_name.lower())
        length = _convert_UOM(line.e_dimLength, line.e_dimUOM, "dim", fp_name.lower())
        weight = _convert_UOM(
            line.e_weightPerEach, line.e_weightUOM, "weight", fp_name.lower()
        )

        for i in range(line.e_qty):
            volume = round(width * height * length / 1000000, 5)

            item = {
                "dangerous": 0,
                "itemId": "EXP",
                "width": 0 or width,
                "height": 0 or height,
                "length": 0 or length,
                "quantity": 1,
                "volume": max(volume, 0.01),
                "weight": 0 or weight,
                "description": ", ".join(descriptions)[:20] if descriptions else "_",
                "gapRa": ", ".join(gaps)[:15],
                # "lineCustomerReference": line.sscc or "",
            }

            items.append(item)

            if fp_name == "startrack":
                item["itemId"] = "EXP"
                item["packagingType"] = (
                    "PLT" if is_pallet(line.e_type_of_packaging) else "CTN"
                )
            elif fp_name == "auspost":
                item["itemId"] = "7E55"  # PARCEL POST + SIGNATURE
            elif fp_name == "hunter":
                item["packagingType"] = (
                    "PLT" if is_pallet(line.e_type_of_packaging) else "CTN"
                )
            elif fp_name == "tnt":
                item["packagingType"] = "D"
            elif fp_name == "dhl":
                item["packagingType"] = (
                    "PLT" if is_pallet(line.e_type_of_packaging) else "CTN"
                )

    payload["items"] = items

    # Detail for each FP
    if fp_name.lower() == "tnt":
        payload["consignmentNumber"] = gen_consignment_num(
            "tnt", booking.b_bookingID_Visual
        )

        # Get `serviceCode` from `serviceName`
        payload["ServiceCode"] = get_tnt_service_code(
            booking.api_booking_quote.service_name
        )
        payload["labelType"] = "A"
        payload["consignmentDate"] = datetime.today().strftime("%d%m%Y")
        payload["collectionInstructions"] = ""

        if payload["pickupAddress"]["instruction"]:
            payload[
                "collectionInstructions"
            ] = f"{payload['pickupAddress']['instruction']}"
        if (
            payload["dropAddress"]["instruction"]
            and payload["dropAddress"]["instruction"] != " "
        ):
            payload[
                "collectionInstructions"
            ] += f" {payload['dropAddress']['instruction']}"

        payload["CustomerConsignmentRef"] = booking.b_client_order_num or ""
    elif fp_name.lower() == "sendle":
        payload["consignmentNumber"] = booking.fk_fp_pickup_id

        if payload["pickupAddress"]["instruction"] == " ":
            payload["pickupAddress"]["instruction"] = "_"

        if payload["dropAddress"]["instruction"] == " ":
            payload["dropAddress"]["instruction"] = "_"

    return payload


def get_create_label_payload(booking, fp_name):
    try:
        payload = {}
        payload["spAccountDetails"] = get_account_detail(booking, fp_name)
        payload["serviceProvider"] = get_service_provider(fp_name)
        payload["consignmentNumber"] = booking.fk_fp_pickup_id

        confirmation_items = Api_booking_confirmation_lines.objects.filter(
            fk_booking_id=booking.pk_booking_id
        )

        items = []
        for item in confirmation_items:
            temp_item = {"itemId": item.api_item_id, "packagingType": "CTN"}
            items.append(temp_item)
        payload["items"] = items

        if fp_name == "startrack":
            layout = "A4-1pp"
        elif fp_name == "auspost":
            layout = "A4-4pp"

        if fp_name in ["startrack", "auspost"]:
            payload["type"] = "PRINT"
            payload["labelType"] = "PRINT"
            payload["pageFormat"] = [
                {
                    "branded": "_CMK0E6mwiMAAAFoYvcg7Ha9",
                    "branded": False,
                    "layout": layout,
                    "leftOffset": 0,
                    "topOffset": 0,
                    "typeOfPost": "Express Post",
                }
            ]

        return payload
    except Exception as e:
        logger.error(f"#403 - Error while build payload: {e}")
        return None


def get_create_order_payload(bookings, fp_name):
    try:
        _fp_name = fp_name.lower()
        payload = {}
        booking = bookings.first()
        payload["spAccountDetails"] = get_account_detail(booking, _fp_name)
        payload["serviceProvider"] = get_service_provider(fp_name)

        if _fp_name in ["startrack", "auspost"]:
            payload["paymentMethods"] = "CHARGE_TO_ACCOUNT"
            payload["referenceNumber"] = "refer1"

            consignmentNumbers = []
            for booking in bookings:
                consignmentNumbers.append(booking.fk_fp_pickup_id)
            payload["consignmentNumbers"] = consignmentNumbers
        elif _fp_name in ["team global express"]:
            consignmentNumbers = []
            _bookings = []
            for booking in bookings:
                consignmentNumbers.append(booking.v_FPBookingNumber)
                _bookings.append(get_book_payload(booking, fp_name))
            payload["consignmentNumbers"] = consignmentNumbers
            payload["bookings"] = _bookings

            # Call Truck if client is not BioPak or JasonL, Aberdeen
            if not booking.kf_client_id in [
                "1af6bcd2-6148-11eb-ae93-0242ac130002",
                "7EAA4B16-484B-3944-902E-BC936BFEF535",
                "4ac9d3ee-2558-4475-bdbb-9d9405279e81",
            ]:
                payload["needTruck"] = True
            else:
                payload["needTruck"] = False

        return payload
    except Exception as e:
        trace_error.print()
        logger.error(f"#404 - Error while build payload(CREATE ORDER): {e}")
        return None


def get_get_order_summary_payload(bookings, fp_name):
    try:
        payload = {}
        payload["spAccountDetails"] = get_account_detail(bookings[0], fp_name)
        payload["serviceProvider"] = get_service_provider(fp_name)
        payload["orderId"] = bookings[0].vx_fp_order_id

        _fp_name = fp_name.lower()
        if _fp_name in ["team global express"]:
            consignmentNumbers = []
            _bookings = []
            for booking in bookings:
                consignmentNumbers.append(booking.v_FPBookingNumber)
                _bookings.append(get_book_payload(booking, fp_name))
            payload["consignmentNumbers"] = consignmentNumbers
            payload["bookings"] = _bookings

        return payload
    except Exception as e:
        logger.error(f"#405 - Error while build payload: {e}")
        return None


def get_get_accounts_payload(fp_name):
    try:
        payload = {}

        for client_name in FP_CREDENTIALS[fp_name].keys():
            for key in FP_CREDENTIALS[fp_name][client_name].keys():
                detail = FP_CREDENTIALS[fp_name][client_name][key]
                payload["spAccountDetails"] = detail

        payload["serviceProvider"] = get_service_provider(fp_name)

        return payload
    except Exception as e:
        logger.error(f"#405 - Error while build payload: {e}")
        return None


def get_pod_payload(booking, fp_name):
    try:
        payload = {}

        payload["spAccountDetails"] = get_account_detail(booking, fp_name)
        payload["serviceProvider"] = get_service_provider(fp_name)

        if fp_name.lower() == "hunter":
            payload["consignmentDetails"] = {"consignmentNumber": booking.jobNumber}
            payload["jobDate"] = booking.jobDate
        else:
            payload["consignmentDetails"] = {
                "consignmentNumber": booking.v_FPBookingNumber
            }

        return payload
    except Exception as e:
        logger.error(f"#400 - Error while build payload: {e}")
        return None


def get_reprint_payload(booking, fp_name):
    try:
        payload = {}
        payload["spAccountDetails"] = get_account_detail(booking, fp_name)
        payload["serviceProvider"] = get_service_provider(fp_name)
        payload["consignmentNumber"] = gen_consignment_num(
            "tnt", booking.b_bookingID_Visual
        )
        payload["labelType"] = "A"
        return payload
    except Exception as e:
        logger.error(f"#400 - Error while build payload: {e}")
        return None


def get_pricing_payload(
    booking,
    fp_name,
    fp,
    account_detail,
    booking_lines,
    service_code=None,
):
    payload = {}

    if hasattr(booking, "client_warehouse_code"):
        client_warehouse_code = booking.client_warehouse_code
    else:
        client_warehouse_code = booking.fk_client_warehouse.client_warehouse_code

    payload["spAccountDetails"] = account_detail
    payload["serviceProvider"] = get_service_provider(
        fp_name=fp_name, upper=True, fp_obj=fp
    )

    # Check puPickUpAvailFrom_Date
    pu_avail_from = booking.puPickUpAvailFrom_Date

    try:
        if not pu_avail_from or pu_avail_from < date.today():
            booking.b_error_Capture = "Please note that date and time you've entered is either a non working day or after hours. This will limit your options of providers available for your collection"
            booking.save()
    except TypeError as e:  # Pricing-only
        pass

    payload["readyDate"] = "" or str(pu_avail_from)[:10]
    payload["referenceNumber"] = "" or booking.b_clientReference_RA_Numbers

    puCompany = booking.puCompany
    pu_Address_Street_1 = booking.pu_Address_Street_1
    pu_Address_street_2 = booking.pu_Address_street_2
    # pu_pickup_instructions_address = booking.pu_pickup_instructions_address
    deToCompanyName = booking.deToCompanyName
    de_Email = booking.de_Email
    # de_Email_Group_Emails = booking.de_Email_Group_Emails
    de_To_Address_Street_1 = booking.de_To_Address_Street_1
    de_To_Address_Street_2 = booking.de_To_Address_Street_2

    payload["pickupAddress"] = {
        "companyName": (puCompany or "")[:30],
        "contact": (booking.pu_Contact_F_L_Name or " ")[:19],
        "emailAddress": booking.pu_Email or "pu@email.com",
        "instruction": "",
        "phoneNumber": booking.pu_Phone_Main or "0283111500",
    }

    payload["pickupAddress"]["postalAddress"] = {
        "address1": pu_Address_Street_1 or "NO ADDRESS",
        "address2": "" or pu_Address_street_2,
        "country": "" or booking.pu_Address_Country,
        "postCode": "" or booking.pu_Address_PostalCode,
        "state": "" or booking.pu_Address_State,
        "suburb": "" or booking.pu_Address_Suburb,
        "sortCode": "" or booking.pu_Address_PostalCode,
    }
    payload["dropAddress"] = {
        "companyName": (deToCompanyName or "")[:30],
        "contact": (booking.de_to_Contact_F_LName or " ")[:19],
        "emailAddress": de_Email or "de@email.com",
        "instruction": "",
        "phoneNumber": booking.de_to_Phone_Main or "0283111500",
    }

    payload["dropAddress"]["postalAddress"] = {
        "address1": de_To_Address_Street_1 or "NO ADDRESS",
        "address2": "" or de_To_Address_Street_2,
        "country": "" or booking.de_To_Address_Country,
        "postCode": "" or booking.de_To_Address_PostalCode,
        "state": "" or booking.de_To_Address_State,
        "suburb": "" or booking.de_To_Address_Suburb,
        "sortCode": "" or booking.de_To_Address_PostalCode,
    }

    items = []
    for line in booking_lines:
        width = _convert_UOM(line.e_dimWidth, line.e_dimUOM, "dim", fp_name)
        height = _convert_UOM(line.e_dimHeight, line.e_dimUOM, "dim", fp_name)
        length = _convert_UOM(line.e_dimLength, line.e_dimUOM, "dim", fp_name)
        weight = _convert_UOM(line.e_weightPerEach, line.e_weightUOM, "weight", fp_name)

        # Sendle size limitation: 120cm
        if fp_name == "sendle" and (width > 120 or height > 120 or length > 120):
            return None

        for i in range(line.e_qty):
            volume = round(width * height * length / 1000000, 5)
            item = {
                "dangerous": 0,
                "width": 0 or width,
                "height": 0 or height,
                "length": 0 or length,
                "quantity": 1,
                "volume": max(volume, 0.01),
                "weight": 0 or weight,
                "description": line.e_item,
            }

            if fp_name == "startrack":
                item["itemId"] = "EXP"
                item["packagingType"] = (
                    "PLT" if is_pallet(line.e_type_of_packaging) else "CTN"
                )
            elif fp_name == "auspost":
                item["itemId"] = service_code  # PARCEL POST + SIGNATURE
            elif fp_name == "hunter":
                item["packagingType"] = (
                    "PLT" if is_pallet(line.e_type_of_packaging) else "CTN"
                )
            elif fp_name == "tnt":
                item["packagingType"] = "D"
            elif fp_name == "dhl":
                item["packagingType"] = (
                    "PLT" if is_pallet(line.e_type_of_packaging) else "CTN"
                )

            items.append(item)

    payload["items"] = items

    # Detail for each FP
    if fp_name == "startrack":
        payload["serviceType"] = "R"
    elif fp_name == "hunter":
        payload["serviceType"] = "RF"
        payload["ConsignmentSenderIsResidential"] = (
            "y" if booking.pu_Address_Type == "residential" else "n"
        )
        payload["ConsignmentReceiverIsResidential"] = (
            "y" if booking.de_To_AddressType == "residential" else "n"
        )
    elif fp_name == "capital":
        payload["serviceType"] = "EC"
    elif fp_name == "allied":
        payload["serviceType"] = "R"
    elif fp_name == "mrl sampson":
        payload["IsAuthorityToLeave"] = booking.opt_authority_to_leave
        payload["pickupEntity"] = payload["pickupAddress"]
        payload["dropEntity"] = payload["dropAddress"]
        payload["pickupEntity"]["address"] = payload["pickupEntity"]["postalAddress"]
        payload["dropEntity"]["address"] = payload["dropEntity"]["postalAddress"]
        pu_phone = payload["dropAddress"]["phoneNumber"]
        de_phone = payload["dropAddress"]["phoneNumber"]

        # Address Type
        pu_address_type = (booking.pu_Address_Type or "Business").title()
        payload["pickupEntity"]["address"]["addressType"] = pu_address_type
        payload["pickupEntity"]["address"]["country"] = "AU"
        de_To_AddressType = (booking.de_To_AddressType or "Business").title()
        payload["dropEntity"]["address"]["addressType"] = de_To_AddressType
        payload["dropEntity"]["address"]["country"] = "AU"

        del payload["pickupAddress"]
        del payload["dropAddress"]
        del payload["pickupEntity"]["postalAddress"]
        del payload["dropEntity"]["postalAddress"]

    return payload


def get_etd_payload(booking, fp_name):
    payload = {}

    if hasattr(booking, "client_warehouse_code"):
        client_warehouse_code = booking.client_warehouse_code
    else:
        client_warehouse_code = booking.fk_client_warehouse.client_warehouse_code

    payload["spAccountDetails"] = {
        "accountCode": "00956684",  # Original
        "accountKey": "4a7a2e7d-d301-409b-848b-2e787fab17c9",
        "accountPassword": "xab801a41e663b5cb889",
    }
    payload["serviceProvider"] = get_service_provider(fp_name)
    payload["readyDate"] = "" or str(booking.puPickUpAvailFrom_Date)[:10]

    client_process = None
    if hasattr(booking, "id"):
        client_process = (
            Client_Process_Mgr.objects.select_related()
            .filter(fk_booking_id=booking.id)
            .first()
        )

    if client_process:
        puCompany = client_process.origin_puCompany
        pu_Address_Street_1 = client_process.origin_pu_Address_Street_1
        pu_Address_street_2 = client_process.origin_pu_Address_Street_2
        deToCompanyName = client_process.origin_deToCompanyName
        de_Email = client_process.origin_de_Email
        de_To_Address_Street_1 = client_process.origin_de_To_Address_Street_1
        de_To_Address_Street_2 = client_process.origin_de_To_Address_Street_2
    else:
        puCompany = booking.puCompany
        pu_Address_Street_1 = booking.pu_Address_Street_1
        pu_Address_street_2 = booking.pu_Address_street_2
        deToCompanyName = booking.deToCompanyName
        de_Email = booking.de_Email
        de_To_Address_Street_1 = booking.de_To_Address_Street_1
        de_To_Address_Street_2 = booking.de_To_Address_Street_2

    payload["pickupAddress"] = {
        "companyName": (puCompany or "")[:30],
        "contact": (booking.pu_Contact_F_L_Name or " ")[:19],
        "emailAddress": booking.pu_Email or "pu@email.com",
        "instruction": "",
        "phoneNumber": booking.pu_Phone_Main or "0283111500",
    }

    payload["pickupAddress"]["postalAddress"] = {
        "address1": "" or pu_Address_Street_1,
        "address2": "" or pu_Address_street_2,
        "country": "" or booking.pu_Address_Country,
        "postCode": "" or booking.pu_Address_PostalCode,
        "state": "" or booking.pu_Address_State,
        "suburb": "" or booking.pu_Address_Suburb,
        "sortCode": "" or booking.pu_Address_PostalCode,
    }
    payload["dropAddress"] = {
        "companyName": (deToCompanyName or "")[:30],
        "contact": (booking.de_to_Contact_F_LName or " ")[:19],
        "emailAddress": de_Email or "de@email.com",
        "instruction": "",
        "phoneNumber": "" or booking.de_to_Phone_Main,
    }

    payload["dropAddress"]["postalAddress"] = {
        "address1": "" or de_To_Address_Street_1,
        "address2": "" or de_To_Address_Street_2,
        "country": "" or booking.de_To_Address_Country,
        "postCode": "" or booking.de_To_Address_PostalCode,
        "state": "" or booking.de_To_Address_State,
        "suburb": "" or booking.de_To_Address_Suburb,
        "sortCode": "" or booking.de_To_Address_PostalCode,
    }

    # Detail for each FP
    if fp_name == "startrack":
        # etd = FP_Service_ETDs.objects.get(
        #     fp_delivery_time_description="PARCEL POST + SIGNATURE"
        # )
        # payload["product_ids"] = [etd.fp_delivery_service_code]
        payload["product_ids"] = "EXP"

    return payload


def get_call_truck_payload(bookings, fp_name, clientname):
    payload = {}

    if fp_name.lower() == "direct freight":
        first_booking = bookings[0]
        payload["spAccountDetails"] = get_account_detail(first_booking, fp_name)
        payload["serviceProvider"] = get_service_provider(fp_name)
        payload["AuthorisedContactName"] = first_booking.b_client_name
        payload["AuthorisedContactPhone"] = ""  # TODO
        payload["ReadyTime"] = "1pm"
        payload["CloseTime"] = "5pm"
        payload["PickupInstructions"] = "Pickup from Reception"

        # Get lines to load
        pk_booking_ids = []
        for booking in bookings:
            pk_booking_ids.append(booking.pk_booking_id)
        booking_lines = Booking_lines.objects.filter(
            fk_booking_id__in=pk_booking_ids, is_deleted=False
        )
        for booking in bookings:
            lines = []
            quote = booking.api_booking_quote
            for booking_line in booking_lines:
                if quote:
                    if booking_line.packed_status == quote.packed_status:
                        lines.append(booking_line)
                else:
                    if booking_line.packed_status == "original":
                        lines.append(booking_line)

        # Extract params from lines
        total_kgs, total_cubic, total_cartons, total_pallets = 0, 0, 0, 0
        max_carton_length, max_carton_width, max_carton_height = 0, 0, 0
        max_pallet_length, max_pallet_width, max_pallet_height = 0, 0, 0
        for line in lines:
            weight_each = _convert_UOM(
                line.e_weightPerEach, line.e_weightUOM, "weight", fp_name
            )
            total_kgs += weight_each * line.e_qty
            total_cubic += get_cubic_meter(
                line.e_dimLength,
                line.e_dimWidth,
                line.e_dimHeight,
                line.e_dimUOM,
                line.e_qty,
            )

            length = _convert_UOM(line.e_dimLength, line.e_dimUOM, "dim", fp_name)
            width = _convert_UOM(line.e_dimWidth, line.e_dimUOM, "dim", fp_name)
            height = _convert_UOM(line.e_dimHeight, line.e_dimUOM, "dim", fp_name)
            if is_carton(line.e_type_of_packaging):
                total_cartons += line.e_qty
                if length > max_carton_length:
                    max_carton_length = length
                if width > max_carton_width:
                    max_carton_width = width
                if height > max_carton_height:
                    max_carton_height = height
            else:
                total_pallets += line.e_qty
                if length > max_pallet_length:
                    max_pallet_length = length
                if width > max_pallet_width:
                    max_pallet_width = width
                if height > max_pallet_height:
                    max_pallet_height = height

        payload["EstimatedTotalKgs"] = int(total_kgs)
        payload["EstimatedTotalCubic"] = round(total_cubic, 3)
        payload["EstimatedTotalCartons"] = int(total_cartons)
        payload["LargestCartonsLength"] = int(max_carton_length)
        payload["LargestCartonsWidth"] = int(max_carton_width)
        payload["LargestCartonsHeight"] = int(max_carton_height)
        payload["EstimatedTotalPallets"] = int(total_pallets)
        payload["LargestPalletsLength"] = int(max_pallet_length)
        payload["LargestPalletsWidth"] = int(max_pallet_width)
        payload["LargestPalletsHeight"] = int(max_pallet_height)

    return payload
