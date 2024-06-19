from datetime import timedelta

from api.utils import get_sydney_now_time
from api.common.ratio import _get_dim_amount, _get_weight_amount


def filter_booking_lines(booking, booking_lines):
    _booking_lines = []

    for booking_line in booking_lines:
        if booking.pk_booking_id == booking_line.fk_booking_id:
            _booking_lines.append(booking_line)

    return _booking_lines


def wrap_in_quote(string):
    return '"' + str(string) + '"'


def build_csv(fileHandler, bookings, booking_lines):
    has_error = False

    # Write Header
    fileHandler.write(
        "pickupName,pickupAddress,pickupAddress2,pickupSuburb,pickupPostcode,pickupState,pickupContact,pickupPhone,pickupDate,pickupTime,\
        dropName,dropAddress1,dropAddress2,dropSuburb,dropPostcode,dropState,dropContact,dropPhone,senderReference,reference1,\
        specialInstructions,description,quantity,pallets,clientName,totalWeight,totalVolume,length,width,height,\
        weight,goodsType,rateType,vehicleType,deliveryTime,deliverTimeTo,warehouse_code"
    )

    # Write Each Line
    comma = ","
    newLine = "\n"
    for booking in bookings:
        _booking_lines = filter_booking_lines(booking, booking_lines)
        eachLineText = ""

        if booking.puCompany is None:
            h00 = ""
        else:
            h00 = wrap_in_quote(booking.puCompany)

        if booking.pu_Address_Street_1 is None:
            h01 = ""
        else:
            h01 = wrap_in_quote(booking.pu_Address_Street_1)

        if booking.pu_Address_street_2 is None:
            h02 = ""
        else:
            h02 = wrap_in_quote(booking.pu_Address_street_2)

        if booking.pu_Address_Suburb is None:
            h03 = ""
        else:
            h03 = wrap_in_quote(booking.pu_Address_Suburb)

        if booking.pu_Address_PostalCode is None:
            h04 = ""
        else:
            h04 = wrap_in_quote(booking.pu_Address_PostalCode)

        if booking.pu_Address_State is None:
            h05 = ""
        else:
            h05 = wrap_in_quote(booking.pu_Address_State)

        # h06 = ""
        # if (
        #     booking.pu_pickup_instructions_address
        #     or booking.pu_PickUp_Instructions_Contact
        # ):
        #     h06 = wrap_in_quote(
        #         booking.pu_pickup_instructions_address
        #         or "" + booking.pu_PickUp_Instructions_Contact
        #         or ""
        #     )
        h06 = f"Collecting Order No. #{str(booking.b_client_order_num)}"

        if booking.pu_Phone_Main is None:
            h07 = ""
        else:
            h07 = str(booking.pu_Phone_Main)

        if booking.pu_PickUp_Avail_From_Date_DME is None:
            h08 = ""
        else:
            h08 = wrap_in_quote(
                booking.pu_PickUp_Avail_From_Date_DME.strftime("%d/%m/%Y")
            )

        if booking.pu_PickUp_Avail_Time_Hours_DME is None:
            h09 = ""
        else:
            h09 = f"{booking.pu_PickUp_Avail_Time_Hours_DME}:00"

        if booking.deToCompanyName is None:
            h10 = ""
        else:
            h10 = wrap_in_quote(booking.deToCompanyName)

        if booking.de_To_Address_Street_1 is None:
            h11 = ""
        else:
            h11 = wrap_in_quote(booking.de_To_Address_Street_1)

        if booking.de_To_Address_Street_2 is None:
            h12 = ""
        else:
            h12 = wrap_in_quote(booking.de_To_Address_Street_2)

        if booking.de_To_Address_Suburb is None:
            h13 = ""
        else:
            h13 = wrap_in_quote(booking.de_To_Address_Suburb)

        if booking.de_To_Address_PostalCode is None:
            h14 = ""
        else:
            h14 = wrap_in_quote(booking.de_To_Address_PostalCode)

        if booking.de_To_Address_State is None:
            h15 = ""
        else:
            h15 = wrap_in_quote(booking.de_To_Address_State)

        if booking.de_to_Contact_F_LName is None:
            h16 = ""
        else:
            h16 = wrap_in_quote(booking.de_to_Contact_F_LName)

        if booking.de_to_Phone_Main is None:  # dropPhone
            h17 = ""
        else:
            h17 = str(booking.de_to_Phone_Main)

        if booking.b_client_order_num is None:  # senderReference
            h18 = ""
        else:
            h18 = f"D_jasonl_{str(booking.b_client_order_num)}"

        if booking.b_bookingID_Visual is None:  # reference1
            h19 = ""
        else:
            h19 = f"DME{booking.b_bookingID_Visual}"

        h20 = ""

        if booking.b_client_name is None:
            h24 = ""
        else:
            h24 = str(booking.b_client_name)

        if booking.v_service_Type is None:
            h32 = ""
        else:
            h32 = str(booking.v_service_Type)

        if booking.v_vehicle_Type is None:
            h33 = ""
        else:
            h33 = str(booking.v_vehicle_Type)

        sydney_time = get_sydney_now_time(return_type="datetime")

        h34 = sydney_time.strftime("%H:%M")

        # if booking.vx_serviceName == "Standard":
        #     h35 = "4"
        # elif booking.vx_serviceName == "VIP":
        #     h35 = "3"
        # elif booking.vx_serviceName == "Priority":
        #     h35 = "2"

        h35 = (sydney_time + timedelta(hours=4)).strftime("%H:%M")

        if booking.b_client_warehouse_code is None:
            h36 = ""
            has_error = "No warehouse"
        else:
            h36 = str(booking.b_client_warehouse_code)

        if len(_booking_lines) > 0:
            for booking_line in _booking_lines:

                if booking_line.e_item is None:
                    h21 = ""
                else:
                    h21 = str(booking_line.e_item)

                if booking_line.e_qty is None:
                    h22 = ""
                else:
                    h22 = str(booking_line.e_qty)

                h23 = ""

                # Calc totalWeight
                h25 = "0"
                if (
                    booking_line.e_weightUOM is not None
                    and booking_line.e_weightPerEach is not None
                    and booking_line.e_qty is not None
                ):
                    if (
                        booking_line.e_weightUOM.upper() == "GRAM"
                        or booking_line.e_weightUOM.upper() == "GRAMS"
                    ):
                        h25 = str(
                            booking_line.e_qty * booking_line.e_weightPerEach / 1000
                        )
                    elif (
                        booking_line.e_weightUOM.upper() == "KILOGRAM"
                        or booking_line.e_weightUOM.upper() == "KG"
                        or booking_line.e_weightUOM.upper() == "KGS"
                        or booking_line.e_weightUOM.upper() == "KILOGRAMS"
                    ):
                        h25 = str(booking_line.e_qty * booking_line.e_weightPerEach)
                    elif (
                        booking_line.e_weightUOM.upper() == "TON"
                        or booking_line.e_weightUOM.upper() == "TONS"
                    ):
                        h25 = str(
                            booking_line.e_qty * booking_line.e_weightPerEach * 1000
                        )
                    else:
                        h25 = str(booking_line.e_qty * booking_line.e_weightPerEach)

                # Calc totalVolume
                h26 = "0"
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
                        h26 = str(
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
                        h26 = str(
                            booking_line.e_qty
                            * booking_line.e_dimLength
                            * booking_line.e_dimWidth
                            * booking_line.e_dimHeight
                        )
                    elif (
                        booking_line.e_dimUOM.upper() == "MILIMETER"
                        or booking_line.e_dimUOM.upper() == "MM"
                    ):
                        h26 = str(
                            booking_line.e_qty
                            * booking_line.e_dimLength
                            * booking_line.e_dimWidth
                            * booking_line.e_dimHeight
                            / 1000000000
                        )
                    else:
                        h26 = str(
                            booking_line.e_qty
                            * booking_line.e_dimLength
                            * booking_line.e_dimWidth
                            * booking_line.e_dimHeight
                        )

                if booking_line.e_dimLength is None:
                    h27 = ""
                else:  # Should be in `CM`
                    h27 = str(
                        _get_dim_amount(booking_line.e_dimUOM)
                        * booking_line.e_dimLength
                        * 100
                    )

                if booking_line.e_dimWidth is None:
                    h28 = ""
                else:  # Should be in `CM`
                    h28 = str(
                        _get_dim_amount(booking_line.e_dimUOM)
                        * booking_line.e_dimWidth
                        * 100
                    )

                if booking_line.e_dimHeight is None:
                    h29 = ""
                else:  # Should be in `CM`
                    h29 = str(
                        _get_dim_amount(booking_line.e_dimUOM)
                        * booking_line.e_dimHeight
                        * 100
                    )

                if booking_line.e_weightPerEach is None:
                    h30 = ""
                else:
                    h30 = str(
                        _get_weight_amount(booking_line.e_weightUOM)
                        * booking_line.e_weightPerEach
                    )

                if booking_line.e_type_of_packaging is None:
                    h31 = ""
                else:
                    h31 = str(booking_line.e_type_of_packaging)

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
                )
                fileHandler.write(newLine + eachLineText)
                eachLineText = ""
        else:
            h19 = ""
            h20 = ""
            h21 = ""
            h22 = ""
            h23 = ""
            h24 = ""
            h25 = ""
            h26 = ""
            h27 = ""
            h28 = ""
            h29 = ""
            h30 = ""
            h31 = ""

            eachLineText += comma + h00 + comma + h01 + comma + h02
            eachLineText += (
                +h00
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
            )
            fileHandler.write(newLine + eachLineText)
            eachLineText = ""

    if has_error:
        for booking in bookings:
            booking.v_FPBookingNumber = None
            booking.vx_freight_provider_carrier = None
            booking.save()

    return has_error
