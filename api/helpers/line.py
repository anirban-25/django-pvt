from api.common.constants import PALLETS, SKIDS, CARTONS


def is_pallet(packaging_type):
    if not packaging_type:
        return False

    return packaging_type.upper() in PALLETS or packaging_type.upper() in SKIDS


def is_skid(packaging_type):
    if not packaging_type:
        return False

    return packaging_type.upper() in SKIDS


def is_carton(packaging_type):
    if not packaging_type:
        return False

    return packaging_type.upper() in CARTONS
