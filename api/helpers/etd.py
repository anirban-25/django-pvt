import logging

from api.helpers.number import is_float


logger = logging.getLogger(__name__)


def get_etd(etd_str):
    if not etd_str:
        raise Exception("etd_str is null")

    etd = 1
    unit = "Days"

    if etd_str == "Overnight":
        return etd, unit

    if is_float(etd_str):
        return float(etd_str), unit

    temp1 = etd_str.split(",")
    temp2, temp3 = [], []

    for item in temp1:
        temp2 += item.split("-")

    for item in temp2:
        temp3 += item.split(" ")

    for item in temp3:
        _item = item.strip()

        if is_float(_item) and float(_item) > etd:
            etd = int(_item) if float(_item).is_integer() else float(_item)

        if "hour" in _item.lower():
            unit = "Hours"

    return etd, unit
