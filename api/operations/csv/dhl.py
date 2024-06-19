from api.models import Fp_freight_providers, FP_carriers, FP_zones


def filter_booking_lines(booking, booking_lines):
    _booking_lines = []

    for booking_line in booking_lines:
        if not booking.pk_booking_id == booking_line.fk_booking_id:
            _booking_lines.append(booking_line)

    return _booking_lines


def wrap_in_quote(string):
    return '"' + str(string) + '"'


def build_csv(fileHandler, bookings, booking_lines):
    has_error = False

    # Write Header
    fileHandler.write(
        "unique_identifier, ref1, ref2(sinv), receiver_name, receiver_address1, receiver_address2, receiver_address3, receiver_address4, receiver_locality, receiver_state, \
receiver_postcode, weight, length, width, height, receiver_contact, receiver_phone_no, receiver_email, pack_unit_code, pack_unit_description, \
items, special_instructions, consignment_prefix, consignment_number, transporter_code, service_code, sender_code, sender_warehouse_code, freight_payer, freight_label_number, \
barcode\n"
    )

    # Write Each Line
    comma = ","
    newLine = "\n"
    fp_info = Fp_freight_providers.objects.get(fp_company_name="DHL")
    fp_carriers = FP_carriers.objects.filter(fk_fp=fp_info.id)
    fp_carriers_old_vals = []

    for fp_carrier in fp_carriers:
        fp_carriers_old_vals.append(fp_carrier.current_value)

    for booking in bookings:
        _booking_lines = filter_booking_lines(booking, booking_lines)

        if not booking.b_client_order_num:
            h00 = ""
        else:
            h00 = str(booking.b_client_order_num)

        if not booking.b_clientReference_RA_Numbers:
            h02 = ""
        else:
            h02 = str(booking.b_clientReference_RA_Numbers)

        if not booking.b_client_sales_inv_num:
            h03 = ""
        else:
            h03 = str(booking.b_client_sales_inv_num)

        if not booking.deToCompanyName:
            h04 = ""
        else:
            h04 = str(booking.deToCompanyName)

        if not booking.de_To_Address_Street_1:
            h05 = ""
        else:
            h05 = str(booking.de_To_Address_Street_1)

        if not booking.de_To_Address_Street_2:
            h06 = ""
        else:
            h06 = str(booking.de_To_Address_Street_2)

        h07 = ""
        h08 = ""

        if not booking.de_To_Address_Suburb:
            h09 = ""
        else:
            h09 = str(booking.de_To_Address_Suburb)

        if not booking.de_To_Address_State:
            h10 = ""
        else:
            h10 = str(booking.de_To_Address_State)

        if not booking.de_To_Address_PostalCode:
            h11 = ""
        else:
            h11 = str(booking.de_To_Address_PostalCode)

        if not booking.de_to_Contact_F_LName:
            h16 = ""
        else:
            h16 = str(booking.de_to_Contact_F_LName)

        if not booking.de_to_Phone_Main:
            h17 = ""
        else:
            h17 = str(booking.de_to_Phone_Main)

        if not booking.de_Email:
            h18 = ""
        else:
            h18 = str(booking.de_Email)

        if not booking.de_to_PickUp_Instructions_Address:
            h22 = ""
        else:
            h22 = wrap_in_quote(
                booking.de_to_PickUp_Instructions_Address.replace(";", " ")
            )

        if (
            booking.de_To_Address_Suburb
            and booking.de_To_Address_State
            and booking.de_To_Address_PostalCode
        ):
            fp_zone = FP_zones.objects.filter(
                fk_fp=fp_info.id,
                state=booking.de_To_Address_State,
                suburb=booking.de_To_Address_Suburb,
                postal_code=booking.de_To_Address_PostalCode,
            ).first()

        if fp_zone is None:
            has_error = True
            booking.b_error_Capture = "DE address and FP_zones are not matching."
            booking.save()
        else:
            h23 = "DMS" if fp_zone.carrier == "DHLSFS" else "DMB"

            h25 = fp_zone.carrier
            h26 = fp_zone.service
            h27 = fp_zone.sender_code
            h28 = "OWNSITE"  # HARDCODED - "sender_warehouse_code"
            h29 = "S"

            for booking_line in booking_lines:
                eachLineText = ""
                h12 = ""
                if booking_line.e_weightUOM and booking_line.e_weightPerEach:
                    if (
                        booking_line.e_weightUOM.upper() == "GRAM"
                        or booking_line.e_weightUOM.upper() == "GRAMS"
                    ):
                        h12 = str(
                            booking_line.e_qty * booking_line.e_weightPerEach / 1000
                        )
                    elif (
                        booking_line.e_weightUOM.upper() == "TON"
                        or booking_line.e_weightUOM.upper() == "TONS"
                    ):
                        h12 = str(
                            booking_line.e_qty * booking_line.e_weightPerEach * 1000
                        )
                    else:
                        h12 = str(booking_line.e_qty * booking_line.e_weightPerEach)

                if booking_line.e_dimLength:
                    h13 = ""
                else:
                    h13 = str(booking_line.e_dimLength)

                if booking_line.e_dimWidth:
                    h14 = ""
                else:
                    h14 = str(booking_line.e_dimWidth)

                if booking_line.e_dimHeight:
                    h15 = ""
                else:
                    h15 = str(booking_line.e_dimHeight)

                # if booking_line.e_pallet_type:
                #     h19 = ""
                # else:
                #     h19 = str(booking_line.e_pallet_type"))

                # if booking_line.e_type_of_packaging:
                #     h20 = ""
                # else:
                #     h20 = str(booking_line.e_type_of_packaging"))

                h19 = "PAL"  # Hardcoded
                h20 = "Pallet"  # Hardcoded

                if booking_line.e_qty:
                    h21 = ""
                else:
                    h21 = str(booking_line.e_qty)

                h24 = ""
                h30 = ""
                fp_carrier = None

                try:
                    fp_carrier = fp_carriers.get(carrier=fp_zone.carrier)
                    h24 = h23 + str(
                        fp_carrier.connote_start_value + fp_carrier.current_value
                    )
                    h30 = (
                        h23
                        + "L00"
                        + str(fp_carrier.label_start_value + fp_carrier.current_value)
                    )

                    # Update booking while build CSV for DHL
                    booking.v_FPBookingNumber = h24
                    booking.vx_freight_provider_carrier = fp_zone.carrier
                    booking.b_error_Capture = None
                    booking.save()

                    if not has_error:
                        fp_carrier.current_value += 1
                        fp_carrier.save()
                except FP_carriers.DoesNotExist:
                    has_error = True

                    # Update booking with FP bug
                    error_msg = "FP_carrier is not matching. Please check FP_zones."
                    booking.b_error_Capture = error_msg
                    booking.save()

                h31 = h24 + h30 + booking.de_To_Address_PostalCode

                eachLineText += (
                    h00
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
                eachLineText += comma + h30 + comma + h31

                fileHandler.write(eachLineText + newLine)

    if has_error:
        for booking in bookings:
            booking.v_FPBookingNumber = None
            booking.vx_freight_provider_carrier = None
            booking.save()

        for index, fp_carrier in enumerate(fp_carriers):
            fp_carrier.current_value = fp_carriers_old_vals[index]
            fp_carrier.save()

    return has_error
