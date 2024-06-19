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
        "userId,connoteNo,connoteDate,customer,senderName,senderAddress1,senderAddress2,senderSuburb,senderPostcode,senderState,\
senderContact,senderPhone,pickupDate,pickupTime,receiverName,receiverAddress1,receiverAddress2,receiverSuburb,receiverPostcode,receiverState,\
receiverContact,receiverPhone,deliveryDate,deliveryTime,totalQuantity,totalPallets,totalWeight,totalVolume,senderReference,description,\
specialInstructions,notes,jobType,serviceType,priorityType,vehicleType,itemCode,scanCode,freightCode,itemReference,\
description,quantity,pallets,labels,totalWeight,totalVolume,length,width,height,weight,\
docAmount,senderCode,receiverCode,warehouseOrderType,freightline_serialNumber,freightline_wbDocket,senderAddress3,receiverAddress3, senderEmail,receiverEmail,\
noConnote"
    )

    # Write Each Line
    comma = ","
    newLine = "\n"
    for booking in bookings:
        _booking_lines = filter_booking_lines(booking, booking_lines)
        eachLineText = "DVM0001"

        if booking.b_bookingID_Visual is None:
            h0 = ""
        else:
            h0 = wrap_in_quote("DME" + str(booking.b_bookingID_Visual))

        if booking.puPickUpAvailFrom_Date is None:
            h1 = ""
        else:
            h1 = wrap_in_quote(str(booking.puPickUpAvailFrom_Date))

        h2 = "009790"

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

        if booking.pu_Contact_F_L_Name is None:
            h06 = ""
        else:
            h06 = wrap_in_quote(booking.pu_Contact_F_L_Name)

        if booking.pu_Phone_Main is None:
            h07 = ""
        else:
            h07 = str(booking.pu_Phone_Main)

        if booking.pu_PickUp_Avail_From_Date_DME is None:
            h08 = ""
        else:
            h08 = wrap_in_quote(booking.pu_PickUp_Avail_From_Date_DME)

        if booking.pu_PickUp_Avail_Time_Hours_DME is None:
            h09 = ""
        else:
            h09 = str(booking.pu_PickUp_Avail_Time_Hours_DME)

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

        if booking.de_to_Phone_Main is None:
            h17 = ""
        else:
            h17 = str(booking.de_to_Phone_Main)

        if booking.de_Deliver_From_Date is None:
            h18 = ""
        else:
            h18 = wrap_in_quote(booking.de_Deliver_From_Date)

        if booking.de_Deliver_From_Hours is None:
            h19 = ""
        else:
            h19 = str(booking.de_Deliver_From_Hours)

        h20 = ""
        h21 = ""
        h22 = ""
        h23 = ""

        if booking.b_client_sales_inv_num is None:
            h24 = ""
        else:
            h24 = wrap_in_quote(booking.b_client_sales_inv_num)

        if booking.b_client_order_num is None:
            h25 = ""
        else:
            h25 = wrap_in_quote(booking.b_client_order_num)

        h26 = ""
        if booking.de_to_PickUp_Instructions_Address:
            h26 = wrap_in_quote(booking.de_to_PickUp_Instructions_Address)
        if booking.de_to_Pick_Up_Instructions_Contact:
            h26 += " " + wrap_in_quote(booking.de_to_Pick_Up_Instructions_Contact)

        h27 = ""

        if booking.vx_serviceName is None:
            h28 = ""
        else:
            h28 = wrap_in_quote(booking.vx_serviceName)

        if booking.v_service_Type is None:
            h29 = ""
        else:
            h29 = wrap_in_quote(booking.v_service_Type)

        h50 = h25
        h51 = ""

        if booking.pu_pickup_instructions_address is None:
            h52 = ""
        else:
            h52 = wrap_in_quote(booking.pu_pickup_instructions_address)

        h53 = ""

        if booking.pu_Email is None:
            h54 = ""
        else:
            h54 = wrap_in_quote(booking.pu_Email)
        if booking.de_Email is None:
            h55 = ""
        else:
            h55 = wrap_in_quote(booking.de_Email)

        h56 = "N"

        h30 = ""
        h31 = ""
        if len(_booking_lines) > 0:
            for booking_line in _booking_lines:
                if booking.b_clientReference_RA_Numbers is None:
                    h32 = ""
                else:
                    h32 = str(booking.b_clientReference_RA_Numbers)

                h33 = ""
                if booking_line.e_type_of_packaging is None:
                    h34 = ""
                else:
                    h34 = wrap_in_quote(booking_line.e_type_of_packaging)
                if booking_line.client_item_reference is None:
                    h35 = ""
                else:
                    h35 = wrap_in_quote(booking_line.client_item_reference)
                if booking_line.e_item is None:
                    h36 = ""
                else:
                    h36 = wrap_in_quote(booking_line.e_item)
                if booking_line.e_qty is None:
                    h37 = ""
                else:
                    h37 = str(booking_line.e_qty)

                h38 = ""

                if booking_line.e_qty is None:
                    h39 = ""
                else:
                    h39 = str(booking_line.e_qty)

                # Calc totalWeight
                h40 = "0"
                if (
                    booking_line.e_weightUOM is not None
                    and booking_line.e_weightPerEach is not None
                    and booking_line.e_qty is not None
                ):
                    if (
                        booking_line.e_weightUOM.upper() == "GRAM"
                        or booking_line.e_weightUOM.upper() == "GRAMS"
                    ):
                        h40 = str(
                            booking_line.e_qty * booking_line.e_weightPerEach / 1000
                        )
                    elif (
                        booking_line.e_weightUOM.upper() == "KILOGRAM"
                        or booking_line.e_weightUOM.upper() == "KG"
                        or booking_line.e_weightUOM.upper() == "KGS"
                        or booking_line.e_weightUOM.upper() == "KILOGRAMS"
                    ):
                        h40 = str(booking_line.e_qty * booking_line.e_weightPerEach)
                    elif (
                        booking_line.e_weightUOM.upper() == "TON"
                        or booking_line.e_weightUOM.upper() == "TONS"
                    ):
                        h40 = str(
                            booking_line.e_qty * booking_line.e_weightPerEach * 1000
                        )
                    else:
                        h40 = str(booking_line.e_qty * booking_line.e_weightPerEach)

                # Calc totalVolume
                h41 = "0"
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
                        h41 = str(
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
                        h41 = str(
                            booking_line.e_qty
                            * booking_line.e_dimLength
                            * booking_line.e_dimWidth
                            * booking_line.e_dimHeight
                        )
                    elif (
                        booking_line.e_dimUOM.upper() == "MILIMETER"
                        or booking_line.e_dimUOM.upper() == "MM"
                    ):
                        h41 = str(
                            booking_line.e_qty
                            * booking_line.e_dimLength
                            * booking_line.e_dimWidth
                            * booking_line.e_dimHeight
                            / 1000000000
                        )
                    else:
                        h41 = str(
                            booking_line.e_qty
                            * booking_line.e_dimLength
                            * booking_line.e_dimWidth
                            * booking_line.e_dimHeight
                        )

                if booking_line.e_dimLength is None:
                    h42 = ""
                else:
                    h42 = str(booking_line.e_dimLength)
                if booking_line.e_dimWidth is None:
                    h43 = ""
                else:
                    h43 = str(booking_line.e_dimWidth)
                if booking_line.e_dimHeight is None:
                    h44 = ""
                else:
                    h44 = str(booking_line.e_dimHeight)
                if booking_line.e_weightPerEach is None:
                    h45 = ""
                else:
                    h45 = str(booking_line.e_weightPerEach)
                h46 = ""
                h47 = ""
                h48 = ""
                h49 = ""

                eachLineText += comma + h0 + comma + h1 + comma + h2
                eachLineText += (
                    comma
                    + h00
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
                )
                eachLineText += (
                    comma
                    + h40
                    + comma
                    + h41
                    + comma
                    + h42
                    + comma
                    + h43
                    + comma
                    + h44
                    + comma
                    + h45
                    + comma
                    + h46
                    + comma
                    + h47
                    + comma
                    + h48
                    + comma
                    + h49
                )
                eachLineText += (
                    comma
                    + h50
                    + comma
                    + h51
                    + comma
                    + h52
                    + comma
                    + h53
                    + comma
                    + h54
                    + comma
                    + h55
                    + comma
                    + h56
                )
                fileHandler.write(newLine + eachLineText)
                eachLineText = "DVM0001"
        else:
            h32 = ""
            h33 = ""
            h34 = ""
            h35 = ""
            h36 = ""
            h37 = ""
            h38 = ""
            h39 = ""
            h40 = ""
            h41 = ""
            h42 = ""
            h43 = ""
            h44 = ""
            h45 = ""
            h46 = ""
            h47 = ""
            h48 = ""
            h49 = ""

            eachLineText += comma + h0 + comma + h1 + comma + h2
            eachLineText += (
                comma
                + h00
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
            )
            eachLineText += (
                comma
                + h40
                + comma
                + h41
                + comma
                + h42
                + comma
                + h43
                + comma
                + h44
                + comma
                + h45
                + comma
                + h46
                + comma
                + h47
                + comma
                + h48
                + comma
                + h49
            )
            eachLineText += (
                comma
                + h50
                + comma
                + h51
                + comma
                + h52
                + comma
                + h53
                + comma
                + h54
                + comma
                + h55
                + comma
                + h56
            )
            fileHandler.write(newLine + eachLineText)
            eachLineText = "DVM0001"

    if has_error:
        for booking in bookings:
            booking.v_FPBookingNumber = None
            booking.vx_freight_provider_carrier = None
            booking.save()

    return has_error
