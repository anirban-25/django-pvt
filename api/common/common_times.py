import pytz
import math
import logging
import holidays
from datetime import date, timedelta, datetime


from api.models import Fp_freight_providers

logger = logging.getLogger(__name__)
SYDNEY_TZ = pytz.timezone("Australia/Sydney")
UTC_TZ = pytz.timezone("UTC")
TIME_DIFFERENCE = 10  # Difference between UTC and AU(Sydney) time


def get_sydney_now_time(return_type="char"):
    sydney_tz = pytz.timezone("Australia/Sydney")
    sydney_now = sydney_tz.localize(datetime.utcnow())
    sydney_now = sydney_now + timedelta(hours=TIME_DIFFERENCE)

    if return_type == "char":
        return sydney_now.strftime("%Y-%m-%d %H:%M:%S")
    elif return_type == "ISO":
        return sydney_now.strftime("%Y-%m-%dT%H:%M:%S")
    elif return_type == "datetime":
        return sydney_now


def convert_to_AU_SYDNEY_tz(time, type="datetime"):
    delta = timedelta(hours=TIME_DIFFERENCE)

    if not time:
        return None

    if type == "datetime":
        try:
            sydney_time = SYDNEY_TZ.localize(time)
            sydney_time = sydney_time + delta
        except:
            sydney_time = time + delta
    else:
        sydney_time = (datetime.combine(date(2, 1, 1), time) + delta).time()

    return sydney_time


def convert_to_UTC_tz(time, type="datetime"):
    delta = timedelta(hours=TIME_DIFFERENCE)

    if not time:
        return None

    if type == "datetime":
        try:
            sydney_time = UTC_TZ.localize(time)
            sydney_time = sydney_time - delta
        except:
            sydney_time = time - delta
    else:
        sydney_time = (datetime.combine(date(2, 1, 1), time) - delta).time()

    return sydney_time


def beautify_eta(json_results, quotes, client):
    """
    beautify eta as Days,
    i.e:
        3.51 -> 4 Days
        3.00 -> 3 Days
    """
    _results = []

    for index, result in enumerate(json_results):
        try:
            delta = float(result["eta"]) - round(float(result["eta"]))

            if delta != 0:
                readable_eta = f"{math.ceil(float(result['eta']))} days"
            else:
                readable_eta = f"{math.round(float(result['eta']))} days"

            result["eta"] = float(result["eta"]) * 24
        except Exception as e:
            try:
                from api.fp_apis.utils import get_etd_in_hour

                etd_in_hour = get_etd_in_hour(quotes[index]) / 24
                result["eta"] = etd_in_hour * 24
                readable_eta = f"{math.ceil(etd_in_hour)} days"
            except Exception as e:
                logger.info(f"@880 [beautify_eta] error: {str(e)}")
                readable_eta = f'{str(result["eta"])} days'

        try:
            result["eta_in_hour"] = round(float(result["eta"]), 2)
            result["eta"] = readable_eta

            if client and client.company_name == "Plum Products Australia Ltd":
                result["eta_in_hour"] = result["eta_in_hour"] + 24 * 3
                result["eta"] = f"{int(result['eta'].split(' ')[0]) + 3} days"

            _results.append(result)
        except:
            logger.info(f"@881 [beautify_eta] error: {result['eta']}")
            pass

    return _results


def next_business_day(
    start_day, business_days, fp_name=None, time=datetime.now().time()
):
    if not start_day:
        return None

    AU_HOLIDAYS = holidays.AU()
    ONE_DAY = timedelta(days=1)
    _next_day = start_day
    fp = None

    if fp_name:
        fps = Fp_freight_providers.objects.only("service_cutoff_time")
        fp = fps.get(fp_company_name__iexact=fp_name)

    if fp and fp.service_cutoff_time:
        service_cutoff_time = fp.service_cutoff_time
    else:
        service_cutoff_time = datetime.strptime("13:00", "%H:%M").time()

    if service_cutoff_time < time:
        _next_day += ONE_DAY

    for i in range(0, int(business_days)):
        _next_day += ONE_DAY

        while _next_day.weekday() in [5, 6] or _next_day in AU_HOLIDAYS:
            _next_day += ONE_DAY

    return _next_day
