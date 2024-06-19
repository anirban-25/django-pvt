import logging

from django.conf import settings
from django.db import transaction
from api.fp_apis.constants import FP_INFO

from api.models import Client_warehouses, SHIP_SSCC_Ranges
from api.clients.biopak.constants import (
    FP_INFO as BIOPAK_INFO,
    SPOJIT_TOKEN as BIOPAK_SPOJIT_TOKEN,
)
from api.clients.tempo_big_w.constants import FP_INFO as BIGW_INFO
from api.clients.jason_l.constants import (
    FP_INFO as JASONL_INFO,
    SPOJIT_TOKEN as JASONL_SPOJIT_TOKEN,
)
from api.clients.bsd.constants import FP_INFO as BSD_INFO
from api.clients.plum.constants import FP_INFO as PLUM_INFO
from api.clients.anchor_packaging.constants import FP_INFO as AP_INFO
from api.clients.aberdeen_paper.constants import FP_INFO as ABP_INFO
from api.clients.tempo.constants import FP_INFO as TEMPO_INFO
from api.clients.reworx.constants import FP_INFO as REWORX_INFO
from api.common.sscc import calc_checksum as calc_sscc_checksum
from api.helpers.line import is_pallet

logger = logging.getLogger(__name__)


CARRIER_MAPPING = {
    "Intermodal and Specialised": "E",
    "Courier": "A",
    "IPEC": "B",
    "Priority (Aus)": "C",
    "Priority (NZ)": "C",
    "Priority (Aus)/International Services": "D",
    "Priority (NZ)/International Services": "D",
    "Shipping": "S",
    "Tasmania": "H",
}

SERICE_MAPPING = {
    "IPEC": {
        "Local": "002",
        "IPEC Priority": "003",
        "Road": "004",
        "Fashion": "005",
        "Consumer Delivery": "006",
        "Sensitive": "007",
        "Direct": "008",
    },
    # More
}


def get_client_fp_info(client_id):
    # Jason L
    if client_id == "1af6bcd2-6148-11eb-ae93-0242ac130002":
        return JASONL_INFO["TGE"]
    # BSD (Bathroom Sales Direct)
    elif client_id == "9e72da0f-77c3-4355-a5ce-70611ffd0bc8":
        return BSD_INFO["TGE"]
    # Plum (Plum Products Australia Ltd)
    elif client_id == "461162D2-90C7-BF4E-A905-000000000004":
        return PLUM_INFO["TGE"]
    # BigW (Tempo Big W)
    elif client_id == "d69f550a-9327-4ff9-bc8f-242dfca00f7e":
        return BIGW_INFO["TGE"]
    # Anchor Packaging
    elif client_id == "49294ca3-2adb-4a6e-9c55-9b56c0361953":
        return AP_INFO["TGE"]
    # Aberdeen Paper
    elif client_id == "4ac9d3ee-2558-4475-bdbb-9d9405279e81":
        return ABP_INFO["TGE"]
    # Tempo Pty Ltd
    elif client_id == "37C19636-C5F9-424D-AD17-05A056A8FBDB":
        return TEMPO_INFO["TGE"]
    # Reworx
    elif client_id == "feb8c98f-3156-4241-8413-86c7af99bf4e":
        return REWORX_INFO["TGE"]
    else:
        logger.error("Client is not supported by TGE.")


def get_account_detail(booking):
    account_detail = {}

    # BioPak
    if booking.kf_client_id == "7EAA4B16-484B-3944-902E-BC936BFEF535":
        return {"provider": "spojit"}
    # Non-BioPak
    else:
        service_code = get_service_code(booking)
        account_detail = {
            "message_sender": "DELIVERME",
            "my_toll_identity": "89a5d249-e248-4dcf-a296-778cf4fd4791",
            "my_toll_token": "eyJhbGciOiJSUzUxMiJ9.eyJ1c2VySWQiOiI4OWE1ZDI0OS1lMjQ4LTRkY2YtYTI5Ni03NzhjZjRmZDQ3OTEiLCJUJlQiOnRydWUsImdlbmVyYXRlRGF0ZSI6IjE2OTM3OTU4MDUzNTQiLCJjdXN0b21OYW1lIjoiMDQtMDktMjNfTXlUZWFtR0VUb2tlbiIsImNlcnRpZmljYXRlTmFtZSI6ImxvY2FsaGNsIiwiQyZDIjp0cnVlLCJ1bmlxdWVJZCI6IjhlNmMyMmE3YjU3NzA0ZjNhMWFlYjRhMDRjZmI5ZmMxYzI1N2I0NWU4ZGMxMzMzMjc5NmI2ZmQ0Nzk2ZTg5YmIiLCJleHAiOjE3NTY5NTQyMDV9.R3G22s152c_aoXZ9upFQnVvsqxUjx7Ur3XKcTzzVO5Ssnfm3WC1EMZbiohP_QWMQeFB1qDFiiCppy9cwmSI_avyA8oMogMXS_xxmI-SgyGziMLvJ9CVddtd6d2vJI9k0YTyHHHorvcZk1PloHxgxGS3hqDZYhswcKMF_EVv8pWf7dcyy4PnGECOlBDPgXpmvy_opKoMG_RbM7MBOjKBbywEShcQfh_NnM0dBa-0xwYafbX8cbKM0VjiulHzK-nKCveqyVfzTnhNooZ03aDFvmOSNltfzgrVhkLTtnzYsO96Sq02QxAYWxBqXnucLfAuI3MIQLzk47GH6EGXLxZX6fQ",
            "username": "stephenm@deliver-me.com.au",
            "password": "UL7JVk683%",
            "call_id": "DELIVERME",
            "source_system_code": "",
            "account_number": "",
        }

        # UAT (Sandbox)
        if settings.ENV != "prod":
            account_detail["password"] = "8b1@HZ3eB1"
            account_detail["my_toll_identity"] = "a9d4dc41-cb37-421f-a478-13dd2da954d5"
            account_detail[
                "my_toll_token"
            ] = "eyJhbGciOiJSUzUxMiJ9.eyJ1c2VySWQiOiJhOWQ0ZGM0MS1jYjM3LTQyMWYtYTQ3OC0xM2RkMmRhOTU0ZDUiLCJUJlQiOnRydWUsImdlbmVyYXRlRGF0ZSI6MTY5MjY3NDkwNTY2NCwiY3VzdG9tTmFtZSI6IjIyLTA4LTIzX015VGVhbUdFVG9rZW4iLCJjZXJ0aWZpY2F0ZU5hbWUiOiJsb2NhbGhjbCIsIkMmQyI6dHJ1ZSwidW5pcXVlSWQiOiIzMTBhODkwZmYwNzU3YTVkNTZhZGIzZTY1Y2IyMTE2MGU2ZmNkMWY3OTMxZDQwMTczNDNkZDgzYzQ5NWFmMGI2IiwiZXhwIjoxNzU1ODMzMzA1fQ.r-Z-TYjlt6svNn4kuZBrFbYLxGcUTgWta6A2vR8fkOB31x3yRnBfg2n3pEeuBGTf6Llo4tPeNkXb-oMNOgbeIDp51bIzCv-ahQmwAsD4GHMj3KTFsevk352Y5U5bau82LBpXgbRjzuHXtQnD7oraw5kka5zAp94AHOmT49KT_454reBMODUjsxq-sov7-821YOHiBSzlccq0SWvl5QgpY9hn_r3jOwy6lyvzSsKCCPUXzSRx4ADyUqwnBCxa6grmyEorw3mq7yfRJ38Ujrt6G_vGz4ilLw1hP9usPhSYoqDF7a6EhiDcGJkBCXtru7ZuRByysAhD7sLjLq5S7NemoQ"

        fp_info = get_client_fp_info(booking.kf_client_id)
        service_info = fp_info[service_code]
        account_detail["account_number"] = service_info["account_number"]

        if service_code == "ins":
            account_detail["source_system_code"] = "DELIVERME"
        else:
            account_detail["source_system_code"] = service_info["source_system_code"]

    return account_detail


def get_base_url(booking):
    # BioPak
    if booking.kf_client_id == "7EAA4B16-484B-3944-902E-BC936BFEF535":
        base_url = BIOPAK_INFO["TGE"]["spojit_url"]
    else:  # Non BioPak
        base_url = JASONL_INFO["TGE"]["spojit_url"]

    return base_url

def get_tge_ins_order_url(booking):
    # BioPak
    if booking.kf_client_id == "7EAA4B16-484B-3944-902E-BC936BFEF535":
        base_url = BIOPAK_INFO["TGE"]["spojit_url"]
    else:  # Non BioPak
        base_url = JASONL_INFO["TGE"]["ins"]["spojit_order_url"]

    return base_url

def get_tge_ins_summary_url(booking):
    # BioPak
    if booking.kf_client_id == "7EAA4B16-484B-3944-902E-BC936BFEF535":
        base_url = BIOPAK_INFO["TGE"]["spojit_url"]
    else:  # Non BioPak
        base_url = JASONL_INFO["TGE"]["ins"]["spojit_summary_url"]

    return base_url

def get_headers(booking):
    # BioPak
    if booking.kf_client_id == "7EAA4B16-484B-3944-902E-BC936BFEF535":
        headers = {
            "content-type": "application/json",
            "Authorization": BIOPAK_SPOJIT_TOKEN,
        }
    else:  # Non BioPak
        headers = {
            "content-type": "application/json",
            "Authorization": JASONL_SPOJIT_TOKEN,
        }

    return headers


def get_service_code(booking, lines=None):
    """
    Get TGE Service Code for a BioPak Booking
    """
    booking_lines = None

    if lines:
        booking_lines = lines
    else:
        booking_lines = booking.lines().filter(is_deleted=False)

    original_lines = []
    scanned_lines = []
    for line in booking_lines:
        if line.packed_status == "original":
            original_lines.append(line)
        elif line.packed_status == "scanned":
            scanned_lines.append(line)
    booking_lines = scanned_lines or original_lines

    if not booking_lines:
        return None

    if is_pallet(booking_lines[0].e_type_of_packaging):
        return "ins"
    else:
        return "ipec"


def is_valid_sscc(sscc):
    return sscc and sscc.startswith(FP_INFO["TGE"]["ssccPrefix"])


def gen_sscc(booking, line, index):
    sscc = str(line.sscc) if line.sscc else ""
    sscc_list = sscc.split(",") if sscc else []

    if len(sscc_list) == line.e_qty:
        sscc = sscc_list[index]
        if sscc and not "NOSSCC" in str(sscc) and is_valid_sscc(sscc):
            return sscc

    service_code = get_service_code(booking)

    # Newly build | Re-build
    sscc_list = []
    for i in range(line.e_qty):
        # BioPak
        if booking.kf_client_id == "7EAA4B16-484B-3944-902E-BC936BFEF535":
            if service_code == "ipec":
                warehouse = Client_warehouses.objects.get(
                    client_warehouse_code=booking.b_client_warehouse_code
                )
                warehouse.tge_ipec_sscc_index += 1
                warehouse.save()
                sscc_index = warehouse.tge_ipec_sscc_index
                prefix2 = BIOPAK_INFO["TGE"]["ipec"]["ssccPrefix"][
                    booking.b_client_warehouse_code
                ]
            elif service_code == "ins":
                # BioPak + TGE + I&S uses only one prefix and ranges for all warehouses
                warehouse = Client_warehouses.objects.get(
                    client_warehouse_code="BIO - CAV"
                )
                warehouse.tge_pe_sscc_index += 1
                warehouse.save()
                sscc_index = warehouse.tge_pe_sscc_index
                prefix2 = BIOPAK_INFO["TGE"]["ins"]["ssccPrefix"][
                    booking.b_client_warehouse_code
                ]

            ai_1 = "00"
            extension_digit = "0"
            prefix3 = str(sscc_index).zfill(9)
        # Non-BioPak
        else:
            with transaction.atomic():
                fp_info = get_client_fp_info(booking.kf_client_id)
                service_info = fp_info[service_code]
                account_number = service_info["account_number"]
                source_system_code = service_info["source_system_code"]
                ssr = SHIP_SSCC_Ranges.objects.select_for_update().get(
                    service_type=service_code,
                    account_number=account_number,
                    source_system_code=source_system_code,
                )

                ssr.sscc_current += 1
                ssr.save()
                sscc_index = ssr.sscc_current + int(ssr.sscc_start)
                prefix2 = ssr.prefix_2

                ai_1 = "00"
                extension_digit = "0"
                prefix3 = str(sscc_index).zfill(9)

        checksum = calc_sscc_checksum(ai_1, extension_digit, prefix2, prefix3)
        sscc = f"{ai_1}{extension_digit}{prefix2}{prefix3}{checksum}"
        sscc_list.append(sscc)

    line.sscc = ",".join(sscc_list)
    line.save()
    return sscc_list[index]


def calc_connote_checksum(number):
    """
    1.  Starting with the first number on the RIGHT, add all the alternate numbers.
    2.  Multiply the result of step 1 by three (3).
    3.  Starting with the second number on the RIGHT, add all the alternate numbers.
    4.  Add the results of steps two (2) and three (3).
    5.  The number needed to bring the total of step four (4) to the next multiple of ten (10) becomes the Check Digit. If the result of step four (4) is an exact multiple of ten (10), then the Check Digit is 0.

    Example: Consignment number = 443028030
    1.  Add     0 + 0 + 2 + 3 + 4   = 9
    2.  Multiply by three (3) 9 x 3     = 27
    3.  Add     3 + 8 + 0 + 4       = 15
    4.  Add     27 + 15         = 42
    5.  50 – 42             = 8
    The check digit is 8
    """
    value = f"{number}"

    if not value or len(value) != 9:
        logger.error(f"Connote length invalid. Value: {value}")
        return None

    sum1 = 0
    for index, _iter in enumerate(value):
        if index % 2 == 0:
            sum1 += int(_iter)

    sum2 = 0
    for index, _iter in enumerate(value):
        if index % 2 == 1:
            sum2 += int(_iter)

    sum3 = sum1 * 3 + sum2
    checksum = 10 - (sum3 % 10)
    checksum = 0 if checksum == 10 else checksum
    return checksum


def is_valid_connote(v_FPBookingNumber, service_code):
    if service_code == "ipec" and v_FPBookingNumber.startswith(
        FP_INFO["TGE"]["ipec"]["consignmentPrefix"]
    ):
        return True
    if service_code == "ins" and v_FPBookingNumber.startswith(
        FP_INFO["TGE"]["ins"]["consignmentPrefix"]
    ):
        return True
    return False


def gen_consignment(booking):
    service_code = get_service_code(booking)

    if booking.v_FPBookingNumber and is_valid_connote(
        booking.v_FPBookingNumber, service_code
    ):
        return booking.v_FPBookingNumber

    # BioPak
    if booking.kf_client_id == "7EAA4B16-484B-3944-902E-BC936BFEF535":
        if service_code == "ipec":
            warehouse = Client_warehouses.objects.get(
                client_warehouse_code=booking.b_client_warehouse_code
            )
            warehouse.tge_ipec_connote_index += 1
            warehouse.save()
            connote_number = warehouse.tge_ipec_connote_index
            prefix = BIOPAK_INFO["TGE"]["ipec"]["consignmentPrefix"][
                booking.b_client_warehouse_code
            ]
            sequence = str(connote_number).zfill(7)
        elif service_code == "ins":
            # BioPak + TGE + I&S uses only one prefix and ranges for all warehouses
            warehouse = Client_warehouses.objects.get(client_warehouse_code="BIO - CAV")
            warehouse.tge_pe_connote_index += 1
            warehouse.save()
            connote_number = warehouse.tge_pe_connote_index
            prefix = BIOPAK_INFO["TGE"]["ins"]["consignmentPrefix"][
                booking.b_client_warehouse_code
            ]  # Will be empty string for `I&S`
            checksum = calc_connote_checksum(connote_number)
            sequence = f"{connote_number}{checksum}"
    # Non-BioPak
    else:
        fp_info = get_client_fp_info(booking.kf_client_id)
        service_info = fp_info[service_code]
        account_number = service_info["account_number"]
        source_system_code = service_info["source_system_code"]
        ssr = SHIP_SSCC_Ranges.objects.get(
            service_type=service_code,
            account_number=account_number,
            source_system_code=source_system_code,
        )

        ssr.ship_current += 1
        ssr.save()
        sscc_index = ssr.ship_current + int(ssr.ship_start)
        prefix = ssr.prefix_1 or ""

        if service_code == "ipec":
            sequence = str(sscc_index).zfill(7)
        elif service_code == "ins":
            checksum = calc_connote_checksum(sscc_index)
            sequence = f"{sscc_index}{checksum}"

    booking.v_FPBookingNumber = f"{prefix}{sequence}"
    booking.save()
    return booking.v_FPBookingNumber
