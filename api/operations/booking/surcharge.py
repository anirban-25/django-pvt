import logging

from django.db.models import Q

from api.common.convert_price import interpolate_gaps, apply_markups
from api.models import Surcharge, API_booking_quotes, Fp_freight_providers, Client_FP
from api.common.booking_quote import set_booking_quote

logger = logging.getLogger(__name__)


def handle_manual_surcharge_change(booking, surcharge):
    """
    hanlder of manual surcharge change
    """

    LOG_ID = "[SURCHARGE CHANGE HANDLER]"
    logger.info(f"{LOG_ID} Running...")

    quotes = API_booking_quotes.objects.filter(fk_booking_id=booking.pk_booking_id)
    surcharges = Surcharge.objects.filter(Q(quote__in=quotes) | Q(booking=booking))

    # Get Client
    client = booking.get_client()

    # Get FPs
    fp_names = []
    for quote in quotes:
        if quote.freight_provider not in fp_names:
            fp_names.append(quote.freight_provider)
    fps = Fp_freight_providers.objects.filter(fp_company_name__in=fp_names)

    # Get Client_FPs
    client_fps = Client_FP.objects.prefetch_related("fp").filter(
        client=client, is_active=True
    )

    # Get manually entered surcharges total
    try:
        manual_surcharges_total = booking.get_manual_surcharges_total()
    except Exception as e:
        manual_surcharges_total = 0

    # Re-calculate `x_price_surcharge` of each Quote
    for quote in quotes:
        fp_surcharges_total = 0
        for surcharge in surcharges:
            if surcharge.quote == quote and not surcharge.line_id:
                fp_surcharges_total += surcharge.qty * surcharge.amount

        quote.x_price_surcharge = fp_surcharges_total + manual_surcharges_total
        quote.save()

    # Apply Markups (FP Markup and Client Markup)
    de_addr = {
        "state": booking.de_To_Address_State,
        "postal_code": booking.de_To_Address_PostalCode,
        "suburb": booking.de_To_Address_Suburb,
    }
    quotes = apply_markups(quotes, client, fps, client_fps, de_addr)

    # Update Booking's quote info
    for quote in quotes:
        if booking.api_booking_quote and booking.api_booking_quote == quote:
            set_booking_quote(booking, quote)

    logger.info(f"{LOG_ID} Finihsed")
