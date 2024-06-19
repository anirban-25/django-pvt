import logging

from api.common.thread import background
from api.models import Fp_freight_providers, API_booking_quotes

logger = logging.getLogger(__name__)


@background
def after_select_quote_bg(booking, quote):
    from api.operations.booking.label import update_label_4_booking

    # Consider label
    update_label_4_booking(booking, quote)


def set_booking_quote(booking, quote=None):
    LOG_ID = "[SET QUOTE]"
    logger.info(f"{LOG_ID}, BookingID: {booking.b_bookingID_Visual}, Quote: {quote}")

    if not quote:
        booking.api_booking_quote = None
        # booking.vx_freight_provider = None
        booking.vx_account_code = None
        booking.vx_serviceName = None
        booking.inv_cost_quoted = None
        booking.inv_sell_quoted = None
        booking.inv_booked_quoted = None
        booking.s_02_Booking_Cutoff_Time = None
        booking.v_vehicle_Type = None
        booking.packed_status = None
    else:
        booking.api_booking_quote = quote
        booking.packed_status = quote.packed_status
        booking.vx_freight_provider = quote.freight_provider
        booking.vx_account_code = quote.account_code
        booking.vx_serviceName = quote.service_name

        if not quote.fee:
            booking.inv_cost_quoted = 0
        else:
            surcharge = quote.x_price_surcharge or 0
            fp_mu = quote.mu_percentage_fuel_levy

            if quote.freight_provider in ["Hunter", "Allied", "Northline", "Camerons"]:
                fuel_levy_base = (quote.fee + surcharge) * fp_mu
            else:
                fuel_levy_base = quote.fee * fp_mu

            booking.inv_cost_quoted = quote.fee + surcharge + fuel_levy_base

        if quote.packed_status == API_booking_quotes.SCANNED_PACK:
            booking.inv_booked_quoted = quote.client_mu_1_minimum_values
        else:
            booking.inv_sell_quoted = quote.client_mu_1_minimum_values

        booking.v_vehicle_Type = quote.vehicle.description if quote.vehicle else None

        fp = Fp_freight_providers.objects.get(
            fp_company_name__iexact=quote.freight_provider
        )

        if fp and fp.service_cutoff_time:
            booking.s_02_Booking_Cutoff_Time = fp.service_cutoff_time
        else:
            booking.s_02_Booking_Cutoff_Time = "12:00:00"

    # Background function
    after_select_quote_bg(booking, quote)

    booking.save()
    return booking
