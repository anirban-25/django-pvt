import logging
from datetime import datetime, date

from api.models import (
    Client_employees,
    Client_warehouses,
    Utl_suburbs,
    DME_clients,
    FC_Log,
    BOK_1_headers,
    BOK_2_lines,
    FPRouting,
)
from api.helpers.string import similarity
from api.fp_apis.utils import (
    select_best_options,
    auto_select_pricing_4_bok,
    gen_consignment_num,
)
from api.serializers import SimpleQuoteSerializer
from api.operations.email_senders import send_email_to_admins
from api.common import trace_error, time as dme_time_lib

logger = logging.getLogger(__name__)


def get_client(user, kf_client_id=None):
    """
    get client
    """
    LOG_ID = "[GET CLIENT]"

    try:
        if kf_client_id:
            client = DME_clients.objects.get(dme_account_num=kf_client_id)
        else:
            client_employee = Client_employees.objects.get(fk_id_user_id=user.pk)
            client = client_employee.fk_id_dme_client

        logger.info(f"{LOG_ID} Client: {client.company_name}")
        return client
    except Exception as e:
        logger.info(f"{LOG_ID} client_employee does not exist, {str(e)}")
        message = "Permission denied."
        raise Exception(message)


def get_warehouse(client, code=None):
    """
    get Client's Warehouse
    """
    LOG_ID = "[GET WHSE]"
    logger.info(f"{LOG_ID} client: {client}, code: {code}")

    try:
        if code:  # JasonL with code
            warehouse = Client_warehouses.objects.get(client_warehouse_code=code)
        elif client.company_name == "Jason L":  # JasonL without code
            warehouse = Client_warehouses.objects.get(
                client_warehouse_code="JASON_L_BOT"
            )
        else:
            warehouse = Client_warehouses.objects.get(fk_id_dme_client=client)

        logger.info(f"{LOG_ID} Warehouse: {warehouse}")
        return warehouse
    except Exception as e:
        logger.info(f"{LOG_ID} Client doesn't have Warehouse(s): {client}")
        message = "Issues with warehouse assignment."
        raise Exception(message)


def get_suburb_state(postal_code, clue=""):
    """
    get `suburb` and `state` from postal_code

    postal_code: PostalCode
    clue: String which may contains Suburb and State
    """
    LOG_ID = "[GET SUBURB & STATE]"
    logger.info(f"{LOG_ID} postal_code: {postal_code}, clue: {clue}")

    if not postal_code:
        message = "Delivery postal code is required."
        logger.info(f"{LOG_ID} {message}")
        raise Exception(message)

    addresses = Utl_suburbs.objects.filter(postal_code=postal_code)

    if not addresses.exists():
        message = "Suburb and or postal code mismatch please check info and try again."
        logger.info(f"{LOG_ID} {message}")
        raise Exception(message)

    selected_address = None
    if clue:
        for address in addresses:
            for clue_iter in clue.split(", "):
                _clue_iter = clue_iter.lower()
                _clue_iter = _clue_iter.strip()

                if address.suburb.lower() == _clue_iter:
                    selected_address = address

    if not selected_address and not clue:
        selected_address = addresses[0]
    elif not selected_address and clue:
        return None, None

    return selected_address.state, selected_address.suburb


def get_similar_suburb(clues):
    """
    get similar(>0.8) suburb from clues
    """
    LOG_ID = "[GET SIMILAR SUBURB]"
    logger.info(f"{LOG_ID} clues: {clues}")
    addresses = Utl_suburbs.objects.all().only("suburb")

    for address in addresses:
        for clue_iter in clues:
            _clue_iter = clue_iter.lower()
            _clue_iter = _clue_iter.strip()

            if similarity(address.suburb.lower(), _clue_iter) > 0.8:
                return clue_iter


def is_postalcode_in_state(state, postal_code):
    """
    check if postal_code is in state
    """
    LOG_ID = "[CHECK STATE HAS POSTAL]"
    logger.info(f"{LOG_ID} state: {state}, postal_code: {postal_code}")

    addresses = Utl_suburbs.objects.filter(state=state, postal_code=postal_code)

    return addresses.exists()


def is_suburb_in_postalcode(postal_code, suburb):
    """
    check if suburb is in postal_code
    """
    LOG_ID = "[CHECK POSTAL HAS SUBURB]"
    logger.info(f"{LOG_ID} postal_code: {postal_code}, suburb: {suburb}")

    addresses = Utl_suburbs.objects.filter(postal_code=postal_code, suburb=suburb)

    return addresses.exists()


def bok_quote(bok_1, packed_status):
    from api.fp_apis.operations.pricing import pricing as pricing_oper
    from api.clients.jason_l.operations import get_total_sales

    LOG_ID = "[BOK QUOTE]"

    # Get Boks
    bok_2s = bok_1.bok_2s().filter(
        is_deleted=False, b_093_packed_status=packed_status or "original"
    )
    client = DME_clients.objects.get(dme_account_num=bok_1.fk_client_id)

    # Get next business day
    next_biz_day = dme_time_lib.next_business_day(date.today(), 1)

    # Get Pricings
    booking = {
        "pk_booking_id": bok_1.pk_header_id,
        "puPickUpAvailFrom_Date": next_biz_day,
        "b_clientReference_RA_Numbers": "",
        "puCompany": bok_1.b_028_b_pu_company,
        "pu_Contact_F_L_Name": bok_1.b_035_b_pu_contact_full_name,
        "pu_Email": bok_1.b_037_b_pu_email,
        "pu_Phone_Main": bok_1.b_038_b_pu_phone_main,
        "pu_Address_Street_1": bok_1.b_029_b_pu_address_street_1,
        "pu_Address_street_2": bok_1.b_030_b_pu_address_street_2,
        "pu_Address_Country": bok_1.b_034_b_pu_address_country,
        "pu_Address_PostalCode": bok_1.b_033_b_pu_address_postalcode,
        "pu_Address_State": bok_1.b_031_b_pu_address_state,
        "pu_Address_Suburb": bok_1.b_032_b_pu_address_suburb,
        "pu_Address_Type": bok_1.b_027_b_pu_address_type,
        "deToCompanyName": bok_1.b_054_b_del_company,
        "de_to_Contact_F_LName": bok_1.b_061_b_del_contact_full_name,
        "de_Email": bok_1.b_063_b_del_email,
        "de_to_Phone_Main": bok_1.b_064_b_del_phone_main,
        "de_To_Address_Street_1": bok_1.b_055_b_del_address_street_1,
        "de_To_Address_Street_2": bok_1.b_056_b_del_address_street_2,
        "de_To_Address_Country": bok_1.b_060_b_del_address_country,
        "de_To_Address_PostalCode": bok_1.b_059_b_del_address_postalcode,
        "de_To_Address_State": bok_1.b_057_b_del_address_state,
        "de_To_Address_Suburb": bok_1.b_058_b_del_address_suburb,
        "de_To_AddressType": bok_1.b_053_b_del_address_type,
        "b_booking_tail_lift_pickup": bok_1.b_019_b_pu_tail_lift,
        "b_booking_tail_lift_deliver": bok_1.b_041_b_del_tail_lift,
        "client_warehouse_code": bok_1.b_client_warehouse_code,
        "kf_client_id": bok_1.fk_client_id,
        "pu_no_of_assists": bok_1.b_072_b_pu_no_of_assists,
        "de_no_of_assists": bok_1.b_073_b_del_no_of_assists,
        "b_client_name": client.company_name,
        "b_booking_project": None,
    }

    booking_lines = []
    for _bok_2 in bok_2s:
        bok_2_line = {
            # "fk_booking_id": _bok_2.fk_header_id,
            "pk_lines_id": _bok_2.pk,
            "e_type_of_packaging": _bok_2.l_001_type_of_packaging,
            "e_qty": int(_bok_2.l_002_qty),
            "e_item": _bok_2.l_003_item,
            "e_dimUOM": _bok_2.l_004_dim_UOM,
            "e_dimLength": _bok_2.l_005_dim_length,
            "e_dimWidth": _bok_2.l_006_dim_width,
            "e_dimHeight": _bok_2.l_007_dim_height,
            "e_weightUOM": _bok_2.l_008_weight_UOM,
            "e_weightPerEach": _bok_2.l_009_weight_per_each,
            "packed_status": _bok_2.b_093_packed_status,
        }
        booking_lines.append(bok_2_line)

    fc_log, _ = FC_Log.objects.get_or_create(
        client_booking_id=bok_1.client_booking_id,
        old_quote__isnull=True,
        new_quote__isnull=True,
    )
    fc_log.old_quote = bok_1.quote
    body = {"booking": booking, "booking_lines": booking_lines}
    packed_statuses = [packed_status or "original"]

    # JasonL - update sales total
    if bok_1.fk_client_id == "1af6bcd2-6148-11eb-ae93-0242ac130002":
        bok_1.b_094_client_sales_total = get_total_sales(bok_1.b_client_order_num)
        bok_1.save()

    _, success, message, quotes, client = pricing_oper(
        body=body,
        booking_id=None,
        is_pricing_only=True,
        packed_statuses=packed_statuses,
    )
    logger.info(
        f"#519 {LOG_ID} Pricing result: success: {success}, message: {message}, results cnt: {len(quotes)}"
    )
    json_results = []

    if quotes and bok_1.b_092_is_quote_locked:
        _quotes = []
        for quote in quotes:
            if (
                quote.freight_provider.lower() == bok_1.b_001_b_freight_provider.lower()
                and quote.packed_status == "scanned"
            ):
                if quote.service_name:
                    if quote.service_name.lower() == bok_1.b_003_b_service_name.lower():
                        _quotes.append(quote)
                else:
                    _quotes.append(quote)
        quotes = _quotes

    # Select best quotes(fastest, lowest)
    if quotes:
        bok_1_obj = bok_1
        best_quotes = select_best_options(pricings=quotes, client=client)
        logger.info(f"#520 {LOG_ID} Selected Best Pricings: {best_quotes}")

        best_quote = best_quotes[0]
        bok_1_obj.b_003_b_service_name = best_quote.service_name
        bok_1_obj.b_001_b_freight_provider = best_quote.freight_provider
        bok_1_obj.quote = best_quote
        bok_1_obj.save()
        fc_log.new_quote = best_quotes[0]
        fc_log.save()
    else:
        message = f"#521 {LOG_ID} No Pricing results to select - BOK_1 pk_header_id: {bok_1.pk_header_id}\nOrder Number: {bok_1.b_client_order_num}"
        logger.error(message)

        if bok_1.b_client_order_num:
            send_email_to_admins("No FC result", message)

    # Response
    if quotes:
        logger.info(f"@8888 {LOG_ID} success: True, 201_created")
    else:
        message = "Pricing cannot be returned due to incorrect address information."
        logger.info(f"@8889 {LOG_ID} {message}")


def check_port_code(de_suburb, de_postcode, de_state):
    logger.info("Checking port_code...")

    # head_port and port_code
    fp_routings = FPRouting.objects.filter(
        freight_provider=13,
        dest_suburb__iexact=de_suburb,
        dest_postcode=de_postcode,
        dest_state__iexact=de_state,
    )
    head_port = fp_routings[0].gateway if fp_routings and fp_routings[0].gateway else ""
    port_code = fp_routings[0].onfwd if fp_routings and fp_routings[0].onfwd else ""

    if not head_port or not port_code:
        message = f"Invalid address: Suburb: {de_suburb}, Postal Code: {de_postcode}, State: {de_state}"
        logger.error(f"{message}")
        raise Exception(message)

    logger.info("`port_code` is fine")


def extract_product_code(e_item):
    if e_item and "ZERO Dims -" in e_item:
        return e_item[: e_item.index("ZERO Dims -") - 2]
    else:
        return e_item or ""


def get_next_version_order_num(order_num):
    if not order_num:
        return ""

    _iters = order_num.split("-")
    if len(_iters) == 1:
        return f"{order_num}-1"
    elif len(_iters) == 2:
        return f"{_iters[0]}-{int(_iters[1]) + 1}"
    else:
        return order_num
