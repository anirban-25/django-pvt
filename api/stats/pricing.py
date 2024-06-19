from django.db.models import Count

from api.models import Bookings, API_booking_quotes


def _is_new_diff(diffs, pricing):
    for diff in diffs:
        if (
            diff["fp_name"] == pricing.freight_provider
            and diff["service_name"] == pricing.service_name
            and diff["account_code"] == pricing.account_code
        ):
            return False

    return True


def analyse_booking_quotes_table(bookingIds):
    results = []
    no_quotes_cnt = 0
    bookings = Bookings.objects.filter(id__in=bookingIds)
    pk_booking_ids = [booking.pk_booking_id for booking in bookings]
    api_booking_quotes = API_booking_quotes.objects.filter(
        fk_booking_id__in=pk_booking_ids
    )

    diffs = []
    for pricing in api_booking_quotes:
        if not diffs or _is_new_diff(diffs, pricing):
            diffs.append(
                {
                    "fp_name": pricing.freight_provider,
                    "service_name": pricing.service_name,
                    "account_code": pricing.account_code,
                }
            )

    for diff in diffs:
        pricing_group = []

        for pricing in api_booking_quotes:
            if (
                diff["fp_name"] == pricing.freight_provider
                and diff["service_name"] == pricing.service_name
                and diff["account_code"] == pricing.account_code
            ):
                pricing_group.append(pricing)

        min_price = max_price = None
        group_total = 0
        for pricing in pricing_group:
            if not min_price or pricing.client_mu_1_minimum_values < min_price:
                min_price = pricing.client_mu_1_minimum_values

            if not max_price or pricing.client_mu_1_minimum_values > max_price:
                max_price = pricing.client_mu_1_minimum_values

            group_total += pricing.client_mu_1_minimum_values

        results.append(
            {
                "fp_name": pricing_group[0].freight_provider,
                "service_name": pricing_group[0].service_name,
                "account_code": pricing_group[0].account_code,
                "count": len(pricing_group),
                "min_price": min_price,
                "avg_price": group_total / len(pricing_group),
                "max_price": max_price,
            }
        )

    max_quotes_cnt = 0
    for result in results:
        if max_quotes_cnt < result["count"]:
            max_quotes_cnt = result["count"]

    results.append(
        {
            "fp_name": "No-Pricing",
            "count": len(bookings) - max_quotes_cnt,
            "min_price": "0",
            "avg_price": "0",
            "max_price": "0",
        }
    )

    return results
