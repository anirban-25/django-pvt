import logging

from api.models import DME_clients, Fp_freight_providers
from api.fp_apis.constants import FP_CREDENTIALS, SPECIAL_FPS
from api.fps.index import get_fp_fl


logger = logging.getLogger(__name__)


def _is_used_client_credential(fp_name, client_name, account_code):
    """
    Check if used client's credential
    """

    credentials = FP_CREDENTIALS.get(fp_name.lower())

    if not credentials:
        return False

    for _client_name in credentials:
        client_credentials = credentials[_client_name]

        for client_key in client_credentials:
            if (
                client_credentials[client_key]["accountCode"] == account_code
                and _client_name == client_name.lower()
            ):
                return True

    return False


def _apply_mu(quote, fp, client, client_fp, de_addr):
    """
    Convert FP price to DME price

    params:
        * quote: api_booking_quote object
    """
    logger.info(f"[FP $ -> DME $] Start quote: {quote}")

    # FP MU(Fuel Levy)
    fp_mu = get_fp_fl(
        fp,
        client,
        de_addr["state"],
        de_addr["postal_code"],
        de_addr["suburb"],
        quote,
        client_fp,
    )

    # DME will consider tax on `invoicing` stage
    # tax = quote.tax_value_1 if quote.tax_value_1 else 0

    # Deactivated 2021-06-14: Need to be considered again
    # if quote.client_mu_1_minimum_values:
    #     fuel_levy_base = quote.client_mu_1_minimum_values * fp_mu
    # else:
    #     fuel_levy_base = quote.fee * fp_mu

    surcharge = quote.x_price_surcharge if quote.x_price_surcharge else 0

    if fp.fp_company_name in ["Hunter", "Allied", "Northline", "Camerons"]:
        fuel_levy_base = (quote.fee + surcharge) * fp_mu
    else:
        fuel_levy_base = quote.fee * fp_mu

    cost = quote.fee + surcharge + fuel_levy_base

    # Client MU
    # Apply FP MU for Quotes with DME credentials
    if _is_used_client_credential(
        quote.freight_provider, quote.fk_client_id.lower(), quote.account_code
    ):
        client_mu = 0
    else:
        client_mu = client.client_mark_up_percent

        if fp.id in [83, 84, 85, 86, 87, 105]:
            client_mu = 0
        elif fp.id in [115]: # Deliver-Me Direct: Markup fee 25%
            client_mu = 0.25
        elif fp.id in [2] and client.dme_account_num == '9e72da0f-77c3-4355-a5ce-70611ffd0bc8':
            # Allied for BSD - Bathroom Sales Direct: Markup fee 1%
            client_mu = 0.01

    client_min_markup_startingcostvalue = client.client_min_markup_startingcostvalue
    client_min = client.client_min_markup_value

    if cost > float(client_min_markup_startingcostvalue):
        quoted_dollar = cost * (1 + client_mu)
    else:
        cost_mu = cost * client_mu

        if cost_mu > client_min:
            quoted_dollar = cost + cost_mu
        else:
            quoted_dollar = cost + client_min

    logger.info(
        f"[FP $ -> DME $] Finish quoted $: {quoted_dollar} FP_MU: {fp_mu}, Client_MU: {client_mu}"
    )
    return quoted_dollar, fuel_levy_base, client_mu


def apply_markups(quotes, client, fps, client_fps, de_addr, booking=None):
    logger.info(f"[APPLY MU] Start")

    if not quotes:
        logger.info(f"[APPLY MU] No Quotes!")
        return quotes

    logger.info(f"[APPLY MU] Booking.fk_booking_id: {quotes[0].fk_booking_id}")

    for quote in quotes:
        if quote.freight_provider in SPECIAL_FPS:  # skip Special FPs
            continue

        fp = None
        _client_fp = None

        for _fp in fps:
            if quote.freight_provider.lower() == _fp.fp_company_name.lower():
                fp = _fp

        for client_fp in client_fps:
            if client_fp.fp == fp:
                _client_fp = client_fp
                break

        client_mu_1_minimum_values, fuel_levy_base, client_mu = _apply_mu(
            quote, fp, client, _client_fp, de_addr
        )

        if not (quote.fee == 0 and quote.x_price_surcharge == 0):
            quote.client_mu_1_minimum_values = client_mu_1_minimum_values

        # BSD + Allied (no Client FP, just add 3 USD) --
        # if (
        #     booking
        #     and booking.kf_client_id == "9e72da0f-77c3-4355-a5ce-70611ffd0bc8"
        #     and quote.freight_provider == "Allied"
        # ):
        #     quote.fuel_levy_base = fuel_levy_base
        #     quote.client_mark_up_percent = 0
        #     quote.client_mu_1_minimum_values = quote.fee + 3
        #     continue

        quote.mu_percentage_fuel_levy = get_fp_fl(
            fp,
            client,
            de_addr["state"],
            de_addr["postal_code"],
            de_addr["suburb"],
            quote,
            client_fp,
        )
        quote.fuel_levy_base = fuel_levy_base
        quote.client_mark_up_percent = client_mu

    logger.info(f"[APPLY MU] Finished")
    return quotes


def _get_lowest_client_pricing(quotes):
    """
    Get lowest pricing which used client's credential
    """

    _lowest_pricing = None

    for quote in quotes:
        fp_name = quote.freight_provider.lower()
        client_name = quote.fk_client_id.lower()
        account_code = quote.account_code

        if _is_used_client_credential(fp_name, client_name, account_code):
            if not _lowest_pricing:
                _lowest_pricing = quote
            elif _lowest_pricing.fee > quote.fee:
                _lowest_pricing = quote

    return _lowest_pricing


def interpolate_gaps(quotes, client):
    """
    Interpolate DME pricings if has gap with lowest client pricing

    params:
        * quotes: api_booking_quote objects array
    """
    logger.info(f"[$ INTERPOLATE] Start")

    if not client:
        # Do not interpolate gaps when doing "Pricing-Only"
        logger.info(f"[$ INTERPOLATE] Pricing only!")
        return quotes

    if not quotes:
        logger.info(f"[$ INTERPOLATE] No Quotes!")
        return quotes

    logger.info(f"[$ INTERPOLATE] Booking.fk_booking_id: {quotes[0].fk_booking_id}")
    fp_name = quotes[0].freight_provider.lower()
    client_name = quotes[0].fk_client_id.lower()

    # Do not interpolate if gap_percent is not set
    # (gap_percent is set only clients which has its FP credentials)
    if not client.gap_percent:
        logger.info(f"[$ INTERPOLATE] No gap_percent! client: {client_name.upper()}")
        return quotes

    lowest_pricing = _get_lowest_client_pricing(quotes)

    if not lowest_pricing:
        return quotes

    logger.info(
        f"[$ INTERPOLATE] Lowest Clinet quote: {lowest_pricing.pk}({lowest_pricing.fee})"
    )
    for quote in quotes:
        if quote.freight_provider in SPECIAL_FPS:  # skip Special FPs
            continue

        fp_name = quote.freight_provider.lower()
        client_name = quote.fk_client_id.lower()
        account_code = quote.account_code

        # Interpolate gaps for DME pricings only
        gap = lowest_pricing.fee - quote.fee

        # DME will consider tax on `invoicing` stage
        # if lowest_pricing.tax_value_1:
        #     gap += float(lowest_pricing.tax_value_1)

        if (
            not _is_used_client_credential(fp_name, client_name, account_code)
            and gap > 0
        ):
            log_msg = (
                f"[$ INTERPOLATE] process! Quote: {quote.pk}({quote.fee}), Gap: {gap}"
            )
            # logger.info(log_msg)
            quote.fee += gap * client.gap_percent

    logger.info(f"[$ INTERPOLATE] Finished")
    return quotes
