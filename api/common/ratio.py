def _get_dim_amount(dim_uom):
    uom = dim_uom.lower()

    if uom in ["km", "kms", "kilometer", "kilometers"]:
        return 1000
    elif uom in ["m", "ms", "meter", "meters"]:
        return 1
    elif uom in ["cm", "cms", "centimeter", "centimeters"]:
        return 0.01
    elif uom in ["mm", "mms", "millimeter", "millimeters"]:
        return 0.001


def _get_weight_amount(weight_uom):
    uom = weight_uom.lower()

    if uom in ["t", "ts", "ton", "tons"]:
        return 1000
    elif uom in ["kg", "kgs", "kilogram", "kilograms"]:
        return 1
    elif uom in ["g", "gs", "gram", "grams"]:
        return 0.001


def get_ratio(uom1, uom2, type):
    if type == "dim":
        return _get_dim_amount(uom1.lower()) / _get_dim_amount(uom2.lower())
    elif type == "weight":
        return _get_weight_amount(uom1.lower()) / _get_weight_amount(uom2.lower())


def _m3_to_kg(booking_lines, m3_to_kg_factor):
    total_kgs = 0

    for item in booking_lines:
        dim_UOM = _get_dim_amount(item.e_dimUOM)
        length = dim_UOM * item.e_dimLength
        width = dim_UOM * item.e_dimWidth
        height = dim_UOM * item.e_dimHeight
        total_kgs += length * width * height * item.e_qty * m3_to_kg_factor

    return total_kgs
