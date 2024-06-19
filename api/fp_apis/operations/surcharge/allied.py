import math
from api.models import FP_onforwarding, FP_zones, FP_pricing_rules, Fp_freight_providers

# def cw(param):
#     if :
#         return {
#             'name': 'Cubic Weight',
#             'description': 'All Allied Overnight Express rates are charged on the greater of either the dead weight or the cubic weight of the consignment. ' +
#                 'The cubic conversion factor is 250 kilograms per cubic metre of space.',
#             'value': 60 * param['total_qty']
#         }
#     else:
#         return None


def get_base_kg_charge(param):
    try:
        fp_id = Fp_freight_providers.objects.get(
            fp_company_name=param["vx_freight_provider"]
        ).id
        pu_zone = FP_zones.objects.get(
            fk_fp=fp_id,
            state=param["pu_address_state"],
            postal_code=param["pu_address_postcode"],
            suburb=param["pu_address_suburb"],
        ).zone
        de_zone = FP_zones.objects.get(
            fk_fp=fp_id,
            state=param["de_to_address_state"],
            postal_code=param["de_to_address_postcode"],
            suburb=param["de_to_address_suburb"],
        ).zone

        rules = FP_pricing_rules.objects.filter(
            freight_provider_id=fp_id,
            service_type=param["vx_service_name"],
            pu_zone=pu_zone,
            de_zone=de_zone,
        )

        if not rules:
            raise Exception("No pricing rule")

        base_charge = rules.first().cost.basic_charge
        per_kg_charge = rules.first().cost.per_UOM_charge
    except Exception as e:
        base_charge = 0
        per_kg_charge = 0

    return base_charge, per_kg_charge


def tl(param):
    if "is_tail_lift" in param and param["is_tail_lift"] == True:
        return {
            "name": "Tail Lift [TL]",
            "description": "For deliveries requiring tail lifts",
            "value": 45.83,
        }
    else:
        return None


# def tm(param):
#     if param['is_tail_lift']:
#         return {
#             'name': '2 Person Deliveries [2M]',
#             'description': 'For deliveries requiring additional helpers',
#             'value': '40.22 * hours'
#         }
#     else:
#         return None

# def tm(param):
#     if param['is_tail_lift']:
#         return {
#             'name': 'Minimum Pick up Fee [MPFEE]',
#             'description': 'A minimum pick up fee is invoked if the total transport charges on freight despatched at any one time ' +
#                 'is less than the minimum pickup fee. If this occurs, the difference between the transport charges and the fee is charged.',
#             'value': 31.26
#         }
#     else:
#         return None

# def op(param):
#     if param['is_pallet'] and oversize
#         return {
#             'name': 'Oversize Pallets',
#             'description': 'Standard pallet sizes are measured at a maximum of 1.2m x 1.2m x 1.4m and weighed at a maximum of 500 kilograms. ' +
#                 'Pallets greater than will incur oversize pallet charges, in line with the number of pallet spaces occupied, charged in full ' +
#                 'pallets. An additional pallet charge will apply.',
#             'value': per_kg_charge * param['max_weight']
#         }
#     else:
#         return None


def hd0(param):
    if (
        param["de_to_address_type"].lower() == "residential"
        and param["max_weight"] < 22
    ):
        return {
            "name": "Home Deliveries [HD] - 22",
            "description": "For freight being delivered to residential addresses a surcharge per consignment under 22kgs (dead or cubic weight)",
            "value": 11.02 * 0.5,
        }
    else:
        return None


def hd1(param):
    if (
        param["de_to_address_type"].lower() == "residential"
        and param["max_weight"] > 22
        and param["max_weight"] <= 55
    ):
        return {
            "name": "Home Deliveries [HD] - 55",
            "description": "For freight being delivered to residential addresses a surcharge per consignment between 23 and 55 kgs (dead or cubic weight)",
            "value": 22.04 * 0.5,
        }
    else:
        return None


def hd2(param):
    if param["de_to_address_type"].lower() == "residential" and (
        (param["dead_weight"] > 55 and param["dead_weight"] <= 90)
        or (param["cubic_weight"] > 55 and param["cubic_weight"] <= 135)
    ) and not (param["dead_weight"] > 90 or param["cubic_weight"] > 135):
        return {
            "name": "Home Deliveries [HD] - 90",
            "description": "For freight being delivered to residential addresses a surcharge per consignment over 55kgs dead weight or over 90 cubic weight will apply",
            "value": 77.12 * 0.5,
        }
    else:
        return None


def hd3(param):
    if param["de_to_address_type"].lower() == "residential" and (
        param["dead_weight"] > 90 or param["cubic_weight"] > 135
    ):
        return {
            "name": "Home Deliveries [HD] - 136",
            "description": "For freight being delivered to residential addresses a surcharge per consignment over 90kgs dead weight or over 136 cubic weight will apply",
            "value": 165.22 * 0.5,
        }
    else:
        return None


# def ow(param):
#     base_charge, per_kg_charge = get_base_kg_charge(param)
#     return {
#         'name': 'Overweight',
#         'description': 'Base charge plus kilo charge',
#         'value': base_charge + per_kg_charge * param['max_weight']
#     }


def mc(param):
    base_charge, per_kg_charge = get_base_kg_charge(param)
    if param["is_pallet"] and per_kg_charge and param["max_weight"] < 350:
        return {
            "name": "Minimum Charge-Skids/ Pallets",
            "description": "The minimum charge for a skid is 175 kilograms, and for a pallet is 350 kilograms.  Please note that even if your "
            + "freight is not presented on a pallet or skid, these charges may be applied if items cannot be lifted by one person.",
            "value": per_kg_charge * (350 - param["max_weight"]),
        }
    else:
        return None


def lws(param):
    """
    Allied pricing api contains this surcharge.

    """

    length_surcharge, width_surcharge = None, None

    # Width surcharge
    if param["max_dimension"] >= 1.2 and param["max_dimension"] < 2.4:
        length_surcharge = {
            "name": "Lengths [LSC] 1.20-2.39 metre",
            "description": "Items that exceed lenghts in any direction will attract a surcharge",
            "value": 5.62,
        }
    elif param["max_dimension"] >= 2.4 and param["max_dimension"] < 3.6:
        length_surcharge = {
            "name": "Lengths [LSC] 2.40-3.59 metre",
            "description": "Items that exceed lenghts in any direction will attract a surcharge",
            "value": 12.41,
        }
    elif param["max_dimension"] >= 3.6 and param["max_dimension"] < 4.2:
        length_surcharge = {
            "name": "Lengths [LSC] 3.6-4.19 metre",
            "description": "Items that exceed lenghts in any direction will attract a surcharge",
            "value": 26.42,
        }
    elif param["max_dimension"] >= 4.2 and param["max_dimension"] < 4.8:
        length_surcharge = {
            "name": "Lengths [LSC] 4.2-4.79 metre",
            "description": "Items that exceed lenghts in any direction will attract a surcharge",
            "value": 92.15,
        }
    elif param["max_dimension"] >= 4.8 and param["max_dimension"] < 6:
        length_surcharge = {
            "name": "Lengths [LSC] 4.8-5.99 metre",
            "description": "Items that exceed lenghts in any direction will attract a surcharge",
            "value": 123.96,
        }
    elif param["max_dimension"] >= 6:
        length_surcharge = {
            "name": "Lengths [LSC] over 6 metre",
            "description": "Items that exceed lenghts in any direction will attract a surcharge",
            "value": 160.07,
        }

    if param["max_dimension"] > 1.1 and param["max_dimension"] <= 1.6:
        width_surcharge = {
            "name": "Width [WS] 1.10-1.60 metre",
            "description": "Items that exceed width will attract a surcharge",
            "value": 7.80,
        }
    elif param["max_dimension"] > 1.6 and param["max_dimension"] <= 2.4:
        width_surcharge = {
            "name": "Width [WS] 1.61-2.4 metre",
            "description": "Items that exceed width will attract a surcharge",
            "value": 10.92,
        }

    # Length surcharge
    if length_surcharge and width_surcharge:
        if length_surcharge["value"] > width_surcharge["value"]:
            return length_surcharge
        else:
            return width_surcharge
    elif length_surcharge or width_surcharge:
        if length_surcharge:
            return length_surcharge
        else:
            return width_surcharge
    else:
        return None


# def bbs(param):
#     if param['max_dimension'] >= 1.4:
#         return {
#             'name': 'Big Bulky Surcharge',
#             'description': 'Where freight travelling extends beyond a pallet space, in any direction, then a surcharge equivalent to double ' +
#                 'the chargeable weight (the greater of either the cubic or dead weight) of the item travelling is charged.',
#             'value': 0.1 * param['dead_weight']
#         }
#     else:
#         return None

# def pd(param):
#     if param['max_dimension'] >= 1.4 or param['max_weight'] > 500:
#         return {
#             'name': 'Pallet Deliveries',
#             'description': 'If items are loaded onto a pallet, and the pallet is to be delivered intact, a full pallet charges will be charged. ' +
#                 'A pallet charge will be made when it takes up a lift space, eg. nothing can be loaded on top of the pallet.',
#             'value': '0.12 unknown'
#         }
#     else:
#         return None


def ofpu(param):
    try:
        pu_onforwarding = FP_onforwarding.objects.get(
            fp_company_name="Allied",
            state=param["pu_address_state"],
            postcode=param["pu_address_postcode"],
            suburb=param["pu_address_suburb"],
        )
        return {
            "name": "Onforwarding(Pickup)",
            "description": "All our rates apply from pick up and to drop, where a delivery made to a nominated regional, country or remote location, "
            + "as outlined on our Onforwarding matrix, an onforwarding surcharge is applicable.  Please contact Allied Express for a copy of this matrix.",
            "value": pu_onforwarding.base_price
            + pu_onforwarding.price_per_kg * param["max_weight"],
        }
    except Exception as e:
        return None


def ofde(param):
    try:
        de_to_onforwarding = FP_onforwarding.objects.get(
            fp_company_name="Allied",
            state=param["de_to_address_state"],
            postcode=param["de_to_address_postcode"],
            suburb=param["de_to_address_suburb"],
        )
        return {
            "name": "Onforwarding(Delivery)",
            "description": "All our rates apply from pick up and to drop, where a delivery made to a nominated regional, country or remote location, "
            + "as outlined on our Onforwarding matrix, an onforwarding surcharge is applicable.  Please contact Allied Express for a copy of this matrix.",
            "value": de_to_onforwarding.base_price
            + de_to_onforwarding.price_per_kg * param["max_weight"],
        }
    except Exception as e:
        return None


def allied():
    return {
        "order": [
            # ow,
            ofpu,
            ofde,
            tl,
            hd0,
            hd1,
            hd2,
            hd3,
        ],
        "line": [
            # mc,
            lws
        ],
    }
