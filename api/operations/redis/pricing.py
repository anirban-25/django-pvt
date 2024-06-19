from django.core.cache import cache


"""
Save pricing result to the Redis cache

pricing_result: {
    'account_code': 'DME',
    'api_results_id': 'self-pricing-074549',
    'fk_booking_id': '24066786-d415-11ed-a48d-acde48001122',
    'fk_client_id': 'Anchor Packaging Pty Ltd',
    'freight_provider': 'DXT',
    'fee': 0.0,
    'etd': '2',
    'tax_value_1': 0,
    'service_name': 'Road Service',
    'service_code': None,
    'vehicle': None,
    'packed_status': 'original'
}
"""


def save_2_redis(pricing_id, pricing_result, booking, client, fp, start_index=0):
    REDIS_TIMEOUT = 300
    packed_status = pricing_result["packed_status"]

    for index in range(start_index, 32):
        prefix = f"{pricing_id}:{fp.pk}:{packed_status}:{index}"
        if not cache.get({prefix}):
            cache.set(prefix, "1")
            break

    cache.set(
        f"{prefix}:account_code",
        pricing_result["account_code"],
        timeout=REDIS_TIMEOUT,
    )
    cache.set(
        f"{prefix}:api_results_id",
        pricing_result["api_results_id"],
        timeout=REDIS_TIMEOUT,
    )
    cache.set(
        f"{prefix}:fk_booking_id",
        pricing_result["fk_booking_id"],
        timeout=REDIS_TIMEOUT,
    )
    cache.set(
        f"{prefix}:fk_client_id",
        pricing_result["fk_client_id"],
        timeout=REDIS_TIMEOUT,
    )
    cache.set(
        f"{prefix}:fee",
        pricing_result["fee"],
        timeout=REDIS_TIMEOUT,
    )
    cache.set(
        f"{prefix}:etd",
        pricing_result["etd"],
        timeout=REDIS_TIMEOUT,
    )
    cache.set(
        f"{prefix}:tax_value_1",
        pricing_result.get("tax_value_1", 0),
        timeout=REDIS_TIMEOUT,
    )
    cache.set(
        f"{prefix}:service_name",
        pricing_result["service_name"],
        timeout=REDIS_TIMEOUT,
    )
    cache.set(
        f"{prefix}:service_code",
        pricing_result.get("service_code", ""),
        timeout=REDIS_TIMEOUT,
    )
    cache.set(
        f"{prefix}:vehicle",
        pricing_result.get("vehicle"),
        timeout=REDIS_TIMEOUT,
    )
    cache.set(
        f"{prefix}:packed_status",
        pricing_result["packed_status"],
        timeout=REDIS_TIMEOUT,
    )
    cache.set(
        f"{prefix}:mu_percentage_fuel_levy",
        pricing_result.get("mu_percentage_fuel_levy", 0),
        timeout=REDIS_TIMEOUT,
    )
    cache.set(
        f"{prefix}:client_mu_1_minimum_values",
        pricing_result.get("client_mu_1_minimum_values", 0),
        timeout=REDIS_TIMEOUT,
    )
    cache.set(
        f"{prefix}:is_from_api",
        pricing_result.get("is_from_api", False),
        timeout=REDIS_TIMEOUT,
    )


def read_from_redis(pricing_id, fp, packed_status, index):
    prefix = f"{pricing_id}:{fp.pk}:{packed_status}:{index}"
    data = {
        "account_code": cache.get(f"{prefix}:account_code"),
        "api_results_id": cache.get(f"{prefix}:api_results_id"),
        "fk_booking_id": cache.get(f"{prefix}:fk_booking_id"),
        "fk_client_id": cache.get(f"{prefix}:fk_client_id"),
        "fee": cache.get(f"{prefix}:fee"),
        "etd": cache.get(f"{prefix}:etd"),
        "client_mu_1_minimum_values": cache.get(f"{prefix}:client_mu_1_minimum_values"),
        "tax_value_1": cache.get(f"{prefix}:tax_value_1"),
        "mu_percentage_fuel_levy": cache.get(f"{prefix}:mu_percentage_fuel_levy"),
        "service_name": cache.get(f"{prefix}:service_name"),
        "service_code": cache.get(f"{prefix}:service_code"),
        "vehicle": cache.get(f"{prefix}:vehicle"),
        "packed_status": cache.get(f"{prefix}:packed_status"),
        "freight_provider": fp.fp_company_name,
        "is_from_api": cache.get(f"{prefix}:is_from_api"),
    }
    return data
