import logging

from django.conf import settings

from api.fp_apis.constants import FP_INFO
from api.models import Client_warehouses, Fp_freight_providers
from api.common.sscc import calc_checksum as calc_sscc_checksum

logger = logging.getLogger(__name__)

SPOJIT_API_URLS = {"book": "83eafd0c-d9e0-11ee-817e-16c1f0c61fa6"}


def is_valid_sscc(sscc):
    return sscc and sscc.startswith(f'000{FP_INFO["CAMERONS"]["ssccPrefix"]}')


def gen_sscc(booking, line, index):
    sscc = str(line.sscc) if line.sscc else ""
    sscc_list = sscc.split(",") if sscc else []

    if len(sscc_list) == line.e_qty:
        sscc = sscc_list[0]
        if sscc and not "NOSSCC" in str(sscc) and is_valid_sscc(sscc):
            return sscc

    # Newly build | Re-build
    sscc_list = []
    for i in range(line.e_qty):
        fp_info = Fp_freight_providers.objects.get(
            fp_company_name=booking.vx_freight_provider
        )
        fp_info.new_connot_index = fp_info.new_connot_index + 1
        fp_info.save()

        sscc_index = fp_info.new_connot_index
        prefix2 = FP_INFO["CAMERONS"]["ssccPrefix"]

        ai_1 = "00"
        extension_digit = "0"
        prefix3 = str(sscc_index).zfill(9)

        checksum = calc_sscc_checksum(ai_1, extension_digit, prefix2, prefix3)
        sscc = f"{ai_1}{extension_digit}{prefix2}{prefix3}{checksum}"
        sscc_list.append(sscc)

    line.sscc = ",".join(sscc_list)
    line.save()
    return sscc_list[0]
