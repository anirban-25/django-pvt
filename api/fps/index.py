from api.models import Client_FP


def get_fp_fl(fp, client, state, postal_code, suburb, quote, client_fp=None):
    """
    Plum & Hunter

    Fuel Levy to Western Australia (Zone 22-26): 45%
    Fuel Levy to Other Regions: 24%
    """
    if (
        fp.fp_company_name.lower() == "hunter"
        and client.dme_account_num == "461162D2-90C7-BF4E-A905-000000000004"
    ):
        if state.upper() == "WA":
            return 0.45
        else:
            return 0.24

    """
    TGE IPEC | TGE Pallet
    """
    if fp.fp_company_name.lower() == "team global express":
        if quote.service_name == "IPEC":
            return 0.1040
        else:
            return 0.1656

    _client_fp = client_fp
    if not client_fp:
        try:
            _client_fp = Client_FP.objects.get(client=client, fp=fp)
        except Exception as e:
            return fp.fp_markupfuel_levy_percent

    return _client_fp.fuel_levy or fp.fp_markupfuel_levy_percent
