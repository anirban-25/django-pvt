import logging
import math
import traceback

from api.common.ratio import _get_dim_amount, _get_weight_amount
from api.helpers.cubic import get_cubic_meter
from api.common.constants import PALLETS, SKIDS

logger = logging.getLogger(__name__)

QUOTE_LIST = [
    {
        "from_zone": "SYD",
        "to_zone": "MELD",
        "from_suburb": "SMITHFIELD",
        "to_suburb": "DERRIMUT",
        "from_state": "NSW",
        "to_state": "VIC",
        "basic_price": 12.50,
        "per_price": 0.1145,
        "minimum_price": 65,
        "cubic": 333,
        "rebate": 2.5,
        "etd": "2 days",
    },
    {
        "from_zone": "SYD",
        "to_zone": "MEL",
        "from_suburb": "SMITHFIELD",
        "to_suburb": "MELBOURNE METRO",
        "from_state": "NSW",
        "to_state": "VIC",
        "basic_price": 12.50,
        "per_price": 0.1150,
        "minimum_price": 150,
        "cubic": 333,
        "rebate": 2.5,
        "etd": "2 days",
    },
    {
        "from_zone": "SYD",
        "to_zone": "BNED",
        "from_suburb": "SMITHFIELD",
        "to_suburb": "ARCHERFIELD",
        "from_state": "NSW",
        "to_state": "QLD",
        "basic_price": 12.50,
        "per_price": 0.2150,
        "minimum_price": 65,
        "cubic": 333,
        "rebate": 2.5,
        "etd": "2 days",
    },
    {
        "from_zone": "SYD",
        "to_zone": "BNE",
        "from_suburb": "SMITHFIELD",
        "to_suburb": "BRISBANE METRO",
        "from_state": "NSW",
        "to_state": "QLD",
        "basic_price": 12.50,
        "per_price": 0.2550,
        "minimum_price": 150,
        "cubic": 333,
        "rebate": 2.5,
        "etd": "2 days",
    },
    {
        "from_zone": "MEL",
        "to_zone": "SYD",
        "from_suburb": "DERRIMUT",
        "to_suburb": "SMITHFIELD",
        "from_state": "VIC",
        "to_state": "NSW",
        "basic_price": 12.50,
        "per_price": 0.2150,
        "minimum_price": 70,
        "cubic": 333,
        "rebate": 2.5,
        "etd": "2 days",
    },
    {
        "from_zone": "SYD",
        "to_zone": "ADLD",
        "from_suburb": "SMITHFIELD",
        "to_suburb": "Green Fields",
        "from_state": "NSW",
        "to_state": "SA",
        "basic_price": 12.50,
        "per_price": 0.3250,
        "minimum_price": 90,
        "cubic": 333,
        "rebate": 2.5,
        "etd": "3 days",
    },
    {
        "from_zone": "SYD",
        "to_zone": "ADL",
        "from_suburb": "SMITHFIELD",
        "to_suburb": "ADELAIDE METRO",
        "from_state": "NSW",
        "to_state": "SA",
        "basic_price": 12.50,
        "per_price": 0.3750,
        "minimum_price": 150,
        "cubic": 333,
        "rebate": 2.5,
        "etd": "3 days",
    },
    {
        "from_zone": "SYD",
        "to_zone": "PERD",
        "from_suburb": "SMITHFIELD",
        "to_suburb": "Welshpool",
        "from_state": "NSW",
        "to_state": "WA",
        "basic_price": 12.50,
        "per_price": 0.8550,
        "minimum_price": 180,
        "cubic": 333,
        "rebate": 2.5,
        "etd": "7 days",
    },
    {
        "from_zone": "SYD",
        "to_zone": "PER",
        "from_suburb": "SMITHFIELD",
        "to_suburb": "PERTH METRO",
        "from_state": "NSW",
        "to_state": "WA",
        "basic_price": 12.50,
        "per_price": 0.8950,
        "minimum_price": 250,
        "cubic": 333,
        "rebate": 2.5,
        "etd": "7 days",
    },
]


def can_use(booking):
    for quote in QUOTE_LIST:
        if (
            quote["from_suburb"].lower() == booking.pu_Address_Suburb.lower()
            and quote["from_state"].lower() == booking.pu_Address_State.lower()
            and quote["to_state"].lower() == booking.de_To_Address_State.lower()
            and (
                quote["to_suburb"].lower() == booking.de_To_Address_Suburb.lower()
                or (
                    quote["to_suburb"] == "MELBOURNE METRO"
                    and (
                        (
                            int(booking.de_To_Address_PostalCode) >= 3000
                            and int(booking.de_To_Address_PostalCode) <= 3207
                        )
                        or (
                            int(booking.de_To_Address_PostalCode) >= 8000
                            and int(booking.de_To_Address_PostalCode) <= 8499
                        )
                    )
                )
                or (
                    quote["to_suburb"] == "BRISBANE METRO"
                    and (
                        (
                            int(booking.de_To_Address_PostalCode) >= 4000
                            and int(booking.de_To_Address_PostalCode) <= 4207
                        )
                        or (
                            int(booking.de_To_Address_PostalCode) >= 9000
                            and int(booking.de_To_Address_PostalCode) <= 9499
                        )
                    )
                )
                or (
                    quote["to_suburb"] == "ADELAIDE METRO"
                    and (
                        (
                            int(booking.de_To_Address_PostalCode) >= 5000
                            and int(booking.de_To_Address_PostalCode) <= 5199
                        )
                        or (
                            int(booking.de_To_Address_PostalCode) >= 5900
                            and int(booking.de_To_Address_PostalCode) <= 5999
                        )
                    )
                )
                or (
                    quote["to_suburb"] == "PERTH METRO"
                    and (
                        (
                            int(booking.de_To_Address_PostalCode) >= 6000
                            and int(booking.de_To_Address_PostalCode) <= 6199
                        )
                        or (
                            int(booking.de_To_Address_PostalCode) >= 6800
                            and int(booking.de_To_Address_PostalCode) <= 6999
                        )
                    )
                )
            )
        ):
            return quote
    return False


def get_value_by_formula(booking, booking_lines):
    net_price = 0
    quote = can_use(booking)
    total_qty = 0
    dead_weight, cubic_weight = 0, 0
    m3_to_kg_factor = quote["cubic"]

    for item in booking_lines:
        dead_weight += (
            item.e_weightPerEach * _get_weight_amount(item.e_weightUOM) * item.e_qty
        )
        cubic_weight += (
            get_cubic_meter(
                item.e_dimLength,
                item.e_dimWidth,
                item.e_dimHeight,
                item.e_dimUOM,
                item.e_qty,
            )
            * m3_to_kg_factor
        )
        total_qty += item.e_qty

    net_price = quote["basic_price"] or 0
    chargable_weight = dead_weight if dead_weight > cubic_weight else cubic_weight
    net_price += float(quote["per_price"] or 0) * math.ceil(chargable_weight)

    return net_price if net_price > quote['minimum_price'] else quote['minimum_price']


def get_etd_by_formula(booking):
    quote = can_use(booking)
    
    return quote['etd']
