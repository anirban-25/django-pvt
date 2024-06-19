import logging

from api.models import BOK_1_headers, BOK_2_lines, Log, FPRouting, DME_clients
from api.operations.email_senders import send_email_to_admins
from api.warehouses.constants import CARRIER_MAPPING

logger = logging.getLogger(__name__)


def get_address(bok_1):
    # Validations
    message = None

    if not bok_1.b_061_b_del_contact_full_name:
        message = "{bok_1.b_client_order_num} issue: 'b_061_b_del_contact_full_name' is missing"

    if not bok_1.b_055_b_del_address_street_1:
        message = "{bok_1.b_client_order_num} issue: 'b_055_b_del_address_street_1' is missing"

    if not bok_1.b_058_b_del_address_suburb:
        message = (
            "{bok_1.b_client_order_num} issue: 'b_058_b_del_address_suburb' is missing"
        )

    if not bok_1.b_057_b_del_address_state:
        message = (
            "{bok_1.b_client_order_num} issue: 'b_057_b_del_address_state' is missing"
        )

    if not bok_1.b_059_b_del_address_postalcode:
        message = "{bok_1.b_client_order_num} issue: 'b_059_b_del_address_postalcode' is missing"

    if message:
        raise Exception(message)

    return {
        "companyName": bok_1.b_054_b_del_company,
        "address1": bok_1.b_055_b_del_address_street_1,
        "address2": bok_1.b_056_b_del_address_street_2,
        "country": bok_1.b_060_b_del_address_country,
        "postalCode": bok_1.b_059_b_del_address_postalcode,
        "state": bok_1.b_057_b_del_address_state,
        "suburb": bok_1.b_058_b_del_address_suburb,
    }


def get_lines(bok_2s):
    from api.clients.operations.index import extract_product_code

    _lines = []

    for bok_2 in bok_2s:
        product_code = bok_2.l_003_item
        product_code = extract_product_code(product_code)

        _lines.append(
            {
                "lineID": bok_2.pk_lines_id,
                "width": bok_2.l_006_dim_width,
                "height": bok_2.l_007_dim_height,
                "length": bok_2.l_005_dim_length,
                "quantity": bok_2.l_002_qty,
                "volumn": bok_2.pk_lines_id,
                "weight": bok_2.l_009_weight_per_each,
                # "reference": bok_2.sscc,
                "dangerous": False,
                "productCode": product_code,
            }
        )

    return _lines


def build_push_payload(bok_1, bok_2s):
    client = DME_clients.objects.get(dme_account_num=bok_1.fk_client_id)
    deliveryInstructions = f"{bok_1.b_043_b_del_instructions_contact or ''} {bok_1.b_044_b_del_instructions_address or ''}"

    freight_provider = CARRIER_MAPPING[bok_1.quote.freight_provider.lower()]
    if "MCPHEE_" in bok_1.b_client_warehouse_code and freight_provider == "DMECHP":
        freight_provider = "DME-DMECHP"

    return {
        "bookingID": bok_1.pk,
        "orderNumber": bok_1.b_client_order_num,
        "warehouseName": bok_1.b_028_b_pu_company,
        "warehouseCode": bok_1.b_client_warehouse_code,
        "freightProvider": freight_provider,
        "clientName": client.company_name,
        "address": get_address(bok_1),
        "deliveryInstructions": deliveryInstructions,
        "specialInstructions": bok_1.b_016_b_pu_instructions_address or "",
        "phoneNumber": bok_1.b_064_b_del_phone_main,
        "emailAddress": bok_1.b_063_b_del_email,
        "bookingLines": get_lines(bok_2s),
        "customerCode": bok_1.b_500_b_client_cust_job_code or "",
    }
