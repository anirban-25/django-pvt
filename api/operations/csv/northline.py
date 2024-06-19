from datetime import timedelta
from api.helpers.phone import compact_number

from api.utils import get_sydney_now_time
from api.fp_apis.utils import gen_consignment_num
from api.common.ratio import _get_dim_amount, _get_weight_amount
from api.fp_apis.utils import get_m3_to_kg_factor


def filter_booking_lines(booking, booking_lines):
    _booking_lines = []

    for booking_line in booking_lines:
        if booking.pk_booking_id == booking_line.fk_booking_id:
            _booking_lines.append(booking_line)

    return _booking_lines


def wrap_in_quote(string):
    return '"' + str(string).replace(",", "") + '"'


def build_csv(fileHandler, bookings, booking_lines):
    has_error = False

    # Write Header
    fileHandler.write(
        "ConnoteNumber,JobDate,CustID,CustRef,SendCompany,\
        SendState,SendSuburb,SendPostcode, SendAddress1,\
        SendAddress2,SendContact,SendPhone,TimeReady,TimeClose,\
        RecCompany,Recstate,RecSuburb,RecPostcode,RecAdd1,\
        RecAdd2,RecContact,SendPhone,SpecialInstructions,\
        RateCode,ItemDesc,DangerousIndicator,DangerUN,DangerClass,\
        DangerDesc,Weight,Cubic,Qty,Length,Width,\
        Height,ConfirmationEmail,SendTail,SendHand,RecTail,\
        RecHand,ResDel,ResPickup"
    )

    # Write Each Line
    comma = ","
    newLine = "\n"
    for booking in bookings:
        _booking_lines = filter_booking_lines(booking, booking_lines)
        eachLineText = ""

        connote_number = gen_consignment_num(
            booking.vx_freight_provider, booking.b_bookingID_Visual
        )
        h00 = wrap_in_quote(connote_number)

        if booking.puPickUpAvailFrom_Date is None:
            h01 = ""
        else:
            h01 = wrap_in_quote(str(booking.puPickUpAvailFrom_Date))

        h02 = wrap_in_quote("9DEL01")  # CustID

        if booking.clientRefNumbers is None:
            h03 = ""
        else:
            h03 = wrap_in_quote(booking.clientRefNumbers)

        if booking.puCompany is None:  # SendCompany
            h04 = ""
        else:
            h04 = wrap_in_quote(booking.puCompany)

        if booking.pu_Address_State is None:
            h05 = ""
        else:
            h05 = wrap_in_quote(booking.pu_Address_State)

        if booking.pu_Address_Suburb is None:
            h06 = ""
        else:
            h06 = wrap_in_quote(booking.pu_Address_Suburb)

        if booking.pu_Address_PostalCode is None:
            h07 = ""
        else:
            h07 = wrap_in_quote(booking.pu_Address_PostalCode)

        if booking.pu_Address_Street_1 is None:
            h08 = ""
        else:
            h08 = wrap_in_quote(booking.pu_Address_Street_1)

        if booking.pu_Address_street_2 is None:
            h09 = ""
        else:
            h09 = wrap_in_quote(booking.pu_Address_street_2)

        if booking.pu_Contact_F_L_Name is None:
            h10 = ""
        else:
            h10 = wrap_in_quote(booking.pu_Contact_F_L_Name)

        if booking.pu_Phone_Main is None:
            h11 = ""
        else:
            h11 = compact_number(booking.pu_Phone_Main, 10)

        time_ready_hours = "12"
        time_ready_minutes = "00"
        if booking.pu_PickUp_Avail_Time_Hours:
            time_ready_hours = str(booking.pu_PickUp_Avail_Time_Hours).zfill(2)
        if booking.pu_PickUp_Avail_Time_Minutes:
            time_ready_minutes = str(booking.pu_PickUp_Avail_Time_Minutes).zfill(2)

        # TimeReady
        h12 = f"{time_ready_hours}:{time_ready_minutes}"

        time_close_hours = "15"
        time_close_minutes = "00"
        if booking.pu_PickUp_By_Time_Hours:
            time_close_hours = str(booking.pu_PickUp_By_Time_Hours).zfill(2)
        if booking.pu_PickUp_By_Time_Minutes:
            time_close_minutes = str(booking.pu_PickUp_By_Time_Minutes).zfill(2)

        # TimeClose
        h13 = f"{time_close_hours}:{time_close_minutes}"

        if booking.deToCompanyName is None:
            h14 = ""
        else:
            h14 = wrap_in_quote(booking.deToCompanyName)

        if booking.de_To_Address_State is None:
            h15 = ""
        else:
            h15 = wrap_in_quote(booking.de_To_Address_State)

        if booking.de_To_Address_Suburb is None:
            h16 = ""
        else:
            h16 = wrap_in_quote(booking.de_To_Address_Suburb)

        if booking.de_To_Address_PostalCode is None:
            h17 = ""
        else:
            h17 = wrap_in_quote(booking.de_To_Address_PostalCode)

        if booking.de_To_Address_Street_1 is None:
            h18 = ""
        else:
            h18 = wrap_in_quote(booking.de_To_Address_Street_1)

        if booking.de_To_Address_Street_2 is None:
            h19 = ""
        else:
            h19 = wrap_in_quote(booking.de_To_Address_Street_2)

        if booking.de_to_Contact_F_LName is None:
            h20 = ""
        else:
            h20 = wrap_in_quote(booking.de_to_Contact_F_LName)

        if booking.de_to_Phone_Main is None:
            h21 = ""
        else:
            h21 = compact_number(booking.de_to_Phone_Main, 10)

        if booking.b_handling_Instructions is None:  # SpecialInstructions
            h22 = ""
        else:
            h22 = wrap_in_quote(booking.b_handling_Instructions)

        h23 = wrap_in_quote("KILO")  # RateCode

        if booking.de_Email is None:  # ConfirmationEmail
            h35 = ""
        else:
            h35 = wrap_in_quote(booking.de_Email)

        h36 = "Y" if booking.b_booking_tail_lift_pickup == True else "N"

        h37 = (
            "Y"
            if booking.pu_no_of_assists and int(booking.pu_no_of_assists) > 1
            else "N"
        )  # SendHand

        h38 = "Y" if booking.b_booking_tail_lift_deliver == True else "N"

        h39 = (
            "Y"
            if booking.de_no_of_assists and int(booking.de_no_of_assists) > 1
            else "N"
        )  # RecHand

        h40 = "Y" if booking.pu_Address_Type == "residential" else "N"

        h41 = "Y" if booking.de_To_AddressType == "residential" else "N"

        if len(_booking_lines) > 0:
            for booking_line in _booking_lines:
                if booking_line.e_item is None:
                    h24 = ""
                else:
                    h24 = wrap_in_quote(booking_line.e_item)

                h25 = "Y" if booking_line.e_dangerousGoods == True else "N"

                h26 = ""  # DangerUN

                h27 = ""  # DangerClass

                h28 = ""  # DangerDesc

                # Calc totalVolume
                h30 = "0"
                if (
                    booking_line.e_dimUOM is not None
                    and booking_line.e_dimLength is not None
                    and booking_line.e_dimWidth is not None
                    and booking_line.e_dimHeight is not None
                    and booking_line.e_qty is not None
                ):
                    if (
                        booking_line.e_dimUOM.upper() == "CM"
                        or booking_line.e_dimUOM.upper() == "CENTIMETER"
                    ):
                        h30 = str(
                            booking_line.e_qty
                            * booking_line.e_dimLength
                            * booking_line.e_dimWidth
                            * booking_line.e_dimHeight
                            / 1000000
                        )
                    elif (
                        booking_line.e_dimUOM.upper() == "METER"
                        or booking_line.e_dimUOM.upper() == "M"
                    ):
                        h30 = str(
                            booking_line.e_qty
                            * booking_line.e_dimLength
                            * booking_line.e_dimWidth
                            * booking_line.e_dimHeight
                        )
                    elif (
                        booking_line.e_dimUOM.upper() == "MILIMETER"
                        or booking_line.e_dimUOM.upper() == "MM"
                    ):
                        h30 = str(
                            booking_line.e_qty
                            * booking_line.e_dimLength
                            * booking_line.e_dimWidth
                            * booking_line.e_dimHeight
                            / 1000000000
                        )
                    else:
                        h30 = str(
                            booking_line.e_qty
                            * booking_line.e_dimLength
                            * booking_line.e_dimWidth
                            * booking_line.e_dimHeight
                        )

                # Calc totalWeight
                h29 = "0"
                if (
                    booking_line.e_weightUOM is not None
                    and booking_line.e_weightPerEach is not None
                    and booking_line.e_qty is not None
                ):
                    if (
                        booking_line.e_weightUOM.upper() == "GRAM"
                        or booking_line.e_weightUOM.upper() == "GRAMS"
                    ):
                        h29 = str(
                            booking_line.e_qty * booking_line.e_weightPerEach / 1000
                        )
                    elif (
                        booking_line.e_weightUOM.upper() == "KILOGRAM"
                        or booking_line.e_weightUOM.upper() == "KG"
                        or booking_line.e_weightUOM.upper() == "KGS"
                        or booking_line.e_weightUOM.upper() == "KILOGRAMS"
                    ):
                        h29 = str(booking_line.e_qty * booking_line.e_weightPerEach)
                    elif (
                        booking_line.e_weightUOM.upper() == "TON"
                        or booking_line.e_weightUOM.upper() == "TONS"
                    ):
                        h29 = str(
                            booking_line.e_qty * booking_line.e_weightPerEach * 1000
                        )
                    else:
                        h29 = str(booking_line.e_qty * booking_line.e_weightPerEach)

                # Commented on 2024-01-15
                # Nen said: Providers' systems are usually programmed to calculate the cubic weight based on the dimensions. And they will select automatically whichever is greater between cubic and dead
                # Compare cubicWeight and deadWeight
                # if float(h30) * get_m3_to_kg_factor("Northline") > float(h29):
                #     h29 = float(h30) * get_m3_to_kg_factor("Northline")
                #     h29 = str(h29)

                if booking_line.e_qty is None:
                    h31 = ""
                else:
                    h31 = str(booking_line.e_qty)

                if booking_line.e_dimLength is None:
                    h32 = ""
                else:  # Should be in `M`
                    h32 = str(
                        _get_dim_amount(booking_line.e_dimUOM)
                        * booking_line.e_dimLength
                    )

                if booking_line.e_dimWidth is None:
                    h33 = ""
                else:  # Should be in `M`
                    h33 = str(
                        _get_dim_amount(booking_line.e_dimUOM) * booking_line.e_dimWidth
                    )

                if booking_line.e_dimHeight is None:
                    h34 = ""
                else:  # Should be in `M`
                    h34 = str(
                        _get_dim_amount(booking_line.e_dimUOM)
                        * booking_line.e_dimHeight
                    )

                eachLineText += (
                    h00
                    + comma
                    + h01
                    + comma
                    + h02
                    + comma
                    + h03
                    + comma
                    + h04
                    + comma
                    + h05
                    + comma
                    + h06
                    + comma
                    + h07
                    + comma
                    + h08
                    + comma
                    + h09
                )
                eachLineText += (
                    comma
                    + h10
                    + comma
                    + h11
                    + comma
                    + h12
                    + comma
                    + h13
                    + comma
                    + h14
                    + comma
                    + h15
                    + comma
                    + h16
                    + comma
                    + h17
                    + comma
                    + h18
                    + comma
                    + h19
                )
                eachLineText += (
                    comma
                    + h20
                    + comma
                    + h21
                    + comma
                    + h22
                    + comma
                    + h23
                    + comma
                    + h24
                    + comma
                    + h25
                    + comma
                    + h26
                    + comma
                    + h27
                    + comma
                    + h28
                    + comma
                    + h29
                )
                eachLineText += (
                    comma
                    + h30
                    + comma
                    + h31
                    + comma
                    + h32
                    + comma
                    + h33
                    + comma
                    + h34
                    + comma
                    + h35
                    + comma
                    + h36
                    + comma
                    + h37
                    + comma
                    + h38
                    + comma
                    + h39
                    + comma
                    + h40
                    + comma
                    + h41
                )
                fileHandler.write(newLine + eachLineText)
                eachLineText = ""
        else:
            h24 = ""
            h25 = ""
            h26 = ""
            h27 = ""
            h28 = ""
            h29 = ""
            h30 = ""
            h31 = ""
            h32 = ""
            h33 = ""
            h34 = ""

            eachLineText += (
                h00
                + comma
                + h01
                + comma
                + h02
                + comma
                + h03
                + comma
                + h04
                + comma
                + h05
                + comma
                + h06
                + comma
                + h07
                + comma
                + h08
                + comma
                + h09
            )
            eachLineText += (
                comma
                + h10
                + comma
                + h11
                + comma
                + h12
                + comma
                + h13
                + comma
                + h14
                + comma
                + h15
                + comma
                + h16
                + comma
                + h17
                + comma
                + h18
                + comma
                + h19
            )
            eachLineText += (
                comma
                + h20
                + comma
                + h21
                + comma
                + h22
                + comma
                + h23
                + comma
                + h24
                + comma
                + h25
                + comma
                + h26
                + comma
                + h27
                + comma
                + h28
                + comma
                + h29
            )
            eachLineText += (
                comma
                + h30
                + comma
                + h31
                + comma
                + h32
                + comma
                + h33
                + comma
                + h34
                + comma
                + h35
                + comma
                + h36
                + comma
                + h37
                + comma
                + h38
                + comma
                + h39
                + comma
                + h40
                + comma
                + h41
            )
            fileHandler.write(newLine + eachLineText)
            eachLineText = ""

    if has_error:
        for booking in bookings:
            booking.v_FPBookingNumber = None
            booking.vx_freight_provider_carrier = None
            booking.save()

    return has_error
