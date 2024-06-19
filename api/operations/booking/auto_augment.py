from api.models import Client_Process_Mgr
from api.utils import sanitize_address


def auto_augment(booking, client_aa, cl_proc=None):
    """
    Auto Augment for a Booking

    @params
        * booking: Booking
        * client_aa: Client_Auto_Augment object
        * cl_proc: Client Process already created (used when update)
    """

    # update
    if cl_proc:
        if not booking.pu_Address_street_2:
            cl_proc.origin_pu_Address_Street_2 = booking.pu_Address_Street_1

            custRefNumVerbage = f"Ref: {str(booking.clientRefNumbers or '')} Returns"

            if len(custRefNumVerbage) >= 30:
                fixed_len = len("Ref:  Returns")
                cl_ref_nums = []
                clientRefNumbers_arr = booking.clientRefNumbers.split(", ")

                for cl_ref_num in clientRefNumbers_arr:
                    if len(clientRefNumbers_arr) - len(cl_ref_nums) > 0:
                        avail_len = 30 - fixed_len - len(cl_ref_num) - 1
                        avail_len -= len(
                            f"+{len(clientRefNumbers_arr) - len(cl_ref_nums)}"
                        )
                    else:
                        avail_len = 30 - fixed_len - len(cl_ref_num) - 1

                    if avail_len > len(",".join(cl_ref_nums)):
                        cl_ref_nums.append(cl_ref_num)

                if len(clientRefNumbers_arr) - len(cl_ref_nums) > 0:
                    custRefNumVerbage = f"Ref: {','.join(cl_ref_nums)} +{len(clientRefNumbers_arr) - len(cl_ref_nums)} Returns"
                else:
                    custRefNumVerbage = f"Ref: {','.join(cl_ref_nums)} Returns"

            cl_proc.origin_pu_Address_Street_1 = custRefNumVerbage
            cl_proc.origin_pu_pickup_instructions_address = (
                str(booking.pu_pickup_instructions_address or "")
                + " "
                + custRefNumVerbage
            )
            cl_proc.save()

        return cl_proc

    # create
    cl_proc = Client_Process_Mgr(fk_booking_id=booking.pk)
    cl_proc.process_name = f"Auto Augment {str(booking.b_bookingID_Visual)}"
    cl_proc.origin_puCompany = booking.puCompany

    if not booking.pu_Address_street_2:
        cl_proc.origin_pu_Address_Street_2 = booking.pu_Address_Street_1

        custRefNumVerbage = f"Ref: {str(booking.clientRefNumbers or '')} Returns"

        if len(custRefNumVerbage) >= 30:
            fixed_len = len("Ref:  Returns")
            cl_ref_nums = []
            clientRefNumbers_arr = booking.clientRefNumbers.split(", ")

            for cl_ref_num in clientRefNumbers_arr:
                if len(clientRefNumbers_arr) - len(cl_ref_nums) > 0:
                    avail_len = 30 - fixed_len - len(cl_ref_num) - 1
                    avail_len -= len(f"+{len(clientRefNumbers_arr) - len(cl_ref_nums)}")
                else:
                    avail_len = 30 - fixed_len - len(cl_ref_num) - 1

                if avail_len > len(",".join(cl_ref_nums)):
                    cl_ref_nums.append(cl_ref_num)

            if len(clientRefNumbers_arr) - len(cl_ref_nums) > 0:
                custRefNumVerbage = f"Ref: {','.join(cl_ref_nums)} +{len(clientRefNumbers_arr) - len(cl_ref_nums)} Returns"
            else:
                custRefNumVerbage = f"Ref: {','.join(cl_ref_nums)} Returns"

        cl_proc.origin_pu_Address_Street_1 = custRefNumVerbage
        cl_proc.origin_pu_pickup_instructions_address = (
            str(booking.pu_pickup_instructions_address or "") + " " + custRefNumVerbage
        )
        cl_proc.origin_de_Email = str(booking.de_Email or "").replace(";", ",")
        cl_proc.origin_de_Email_Group_Emails = str(
            booking.de_Email_Group_Emails or ""
        ).replace(";", ",")

    if client_aa.de_Email:
        cl_proc.origin_de_Email = client_aa.de_Email

    if client_aa.de_Email_Group_Emails:
        cl_proc.origin_de_Email_Group_Emails = client_aa.de_Email_Group_Emails

    if client_aa.de_To_Address_Street_1:
        cl_proc.origin_de_To_Address_Street_1 = client_aa.de_To_Address_Street_1

    if client_aa.de_To_Address_Street_1:
        cl_proc.origin_de_To_Address_Street_2 = client_aa.de_To_Address_Street_2

    if client_aa.company_hours_info:
        deToCompanyName = booking.deToCompanyName
        cl_proc.origin_deToCompanyName = (
            f"{deToCompanyName} ({client_aa.company_hours_info})"
        )

    cl_proc.origin_pu_Address_Street_1 = sanitize_address(
        cl_proc.origin_pu_Address_Street_1
    )
    cl_proc.origin_pu_Address_Street_2 = sanitize_address(
        cl_proc.origin_pu_Address_Street_2
    )
    cl_proc.origin_de_To_Address_Street_1 = sanitize_address(
        cl_proc.origin_de_To_Address_Street_1
    )
    cl_proc.origin_de_To_Address_Street_2 = sanitize_address(
        cl_proc.origin_de_To_Address_Street_2
    )
    cl_proc.origin_pu_pickup_instructions_address = sanitize_address(
        cl_proc.origin_pu_pickup_instructions_address
    )

    cl_proc.save()
    return cl_proc
