from datetime import datetime


def _set_error(booking, error_msg):
    booking.b_error_Capture = str(error_msg)[:999]
    booking.z_ModifiedTimestamp = datetime.now()
    booking.save()


def pre_check_book(booking):
    _fp_name = booking.vx_freight_provider.lower()
    _b_client_name = booking.b_client_name.lower()
    error_msg = None

    if booking.b_status.lower() == "booked":
        error_msg = "Booking is already booked."

    if booking.pu_Address_State is None or not booking.pu_Address_State:
        error_msg = "State for pickup postal address is required."
        _set_error(booking, error_msg)

    if booking.pu_Address_Suburb is None or not booking.pu_Address_Suburb:
        error_msg = "Suburb name for pickup postal address is required."
        _set_error(booking, error_msg)

    if _fp_name == "hunter" and not booking.puPickUpAvailFrom_Date:
        error_msg = "PU Available From Date is required."
        _set_error(booking, error_msg)

    if _b_client_name == "biopak" and not booking.b_clientReference_RA_Numbers:
        error_msg = "'FFL-' number is missing."
        _set_error(booking, error_msg)

    return error_msg


def pre_check_rebook(booking):
    if booking.b_status.lower() == "ready for booking":
        error_msg = "Booking is not booked."
        return error_msg

    if booking.pu_Address_State is None or not booking.pu_Address_State:
        error_msg = "State for pickup postal address is required."
        _set_error(booking, error_msg)
        return error_msg

    if booking.pu_Address_Suburb is None or not booking.pu_Address_Suburb:
        error_msg = "Suburb name for pickup postal address is required."
        _set_error(booking, error_msg)
        return error_msg

    if (
        booking.vx_freight_provider.lower() == "hunter"
        and not booking.puPickUpAvailFrom_Date
    ):
        error_msg = "PU Available From Date is required."
        _set_error(booking, error_msg)
        return error_msg


def pre_check_label(booking):
    if booking.vx_freight_provider.lower() == "tnt":
        from api.helpers.phone import compact_number

        # Phone Number
        booking.pu_Phone_Main = compact_number(booking.pu_Phone_Main)
        booking.de_to_Phone_Main = compact_number(booking.de_to_Phone_Main)

        # PU Address
        booking.pu_Address_Street_1 = (booking.pu_Address_Street_1 or "").strip()[:30]
        booking.pu_Address_street_2 = (booking.pu_Address_street_2 or "").strip()[:30]
        if not booking.pu_Address_Street_1 and not booking.pu_Address_street_2:
            error_msg = "PU address doesn't exist"
            _set_error(booking, error_msg)
            return booking, error_msg
        elif booking.pu_Address_street_2 and not booking.pu_Address_Street_1:
            booking.pu_Address_Street_1 = booking.pu_Address_street_2
            booking.pu_Address_street_2 = None

        # DE Address
        booking.de_To_Address_Street_1 = booking.de_To_Address_Street_1 or ""
        booking.de_To_Address_Street_1 = booking.de_To_Address_Street_1.strip()[:30]
        booking.de_To_Address_Street_2 = booking.de_To_Address_Street_2 or ""
        booking.de_To_Address_Street_2 = booking.de_To_Address_Street_2.strip()[:30]
        if not booking.de_To_Address_Street_1 and not booking.de_To_Address_Street_2:
            error_msg = "PU address doesn't exist"
            _set_error(booking, error_msg)
            return booking, error_msg
        elif booking.de_To_Address_Street_2 and not booking.de_To_Address_Street_1:
            booking.de_To_Address_Street_1 = booking.de_To_Address_Street_2
            booking.de_To_Address_Street_2 = None

        # PU Company
        booking.puCompany = (booking.puCompany or "").strip()[:30]
        if not booking.puCompany:
            error_msg = "PU address is required"
            _set_error(booking, error_msg)
            return booking, error_msg

        # DE Company
        booking.deToCompanyName = (booking.deToCompanyName or "").strip()[:30]
        if not booking.deToCompanyName:
            error_msg = "DE address is required"
            _set_error(booking, error_msg)
            return booking, error_msg

        # PU Contact
        booking.pu_Contact_F_L_Name = (booking.pu_Contact_F_L_Name or "").strip()[:20]
        if not booking.pu_Contact_F_L_Name:
            error_msg = "PU contact name is required"
            _set_error(booking, error_msg)
            return booking, error_msg

        # DE Contact
        booking.de_to_Contact_F_LName = booking.de_to_Contact_F_LName or ""
        booking.de_to_Contact_F_LName = booking.de_to_Contact_F_LName.strip()[:20]
        if not booking.de_to_Contact_F_LName:
            error_msg = "DE contact name is required"
            _set_error(booking, error_msg)
            return booking, error_msg

        booking.save()

    return booking, None
