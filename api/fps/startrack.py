from api.fp_apis.constants import FP_CREDENTIALS


def gen_consignment(booking):
    if booking.v_FPBookingNumber:
        return booking.v_FPBookingNumber

    warehouse = booking.fk_client_warehouse
    warehouse.connote_number += 1
    warehouse.save()

    if warehouse.client_warehouse_code == "BIO - RIC":
        prefix = "56R"
        return f"{prefix}Z2{str(warehouse.connote_number).zfill(7)}"
    elif warehouse.client_warehouse_code == "BIO - HAZ":
        prefix = "9XA"
        return f"{prefix}Z5{str(warehouse.connote_number).zfill(7)}"
    elif warehouse.client_warehouse_code == "BIO - FDM":
        prefix = "BBB"
        return f"{prefix}Z1{str(warehouse.connote_number).zfill(7)}"
    elif warehouse.client_warehouse_code == "BIO - EAS":
        prefix = "L7O"
        return f"{prefix}Z5{str(warehouse.connote_number).zfill(7)}"
    elif warehouse.client_warehouse_code == "BIO - TRU":
        prefix = "A0O"
        return f"{prefix}Z9{str(warehouse.connote_number).zfill(7)}"
    else:
        return ""


def get_account_code(booking):
    accounts = FP_CREDENTIALS["startrack"]["dme"]

    for key in accounts:
        account = accounts[key]

        if not account.get("suburb"):
            continue

        state = account["state"]
        postal_code = account["postcode"]
        suburb = account["suburb"]

        if (
            booking.pu_Address_State
            and booking.pu_Address_State.upper() == state
            and booking.pu_Address_PostalCode == postal_code
            and booking.pu_Address_Suburb
            and booking.pu_Address_Suburb.upper() == suburb
        ):
            return account["accountCode"]

    return None
