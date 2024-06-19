def get_cubic_meter(length, width, height, uom="METER", qty=1):
    value = 0
    _dimUOM = uom.upper()

    if _dimUOM in ["MM", "MILIMETER"]:
        value = qty * length * width * height / 1000000000
    elif _dimUOM in ["CM", "CENTIMETER"]:
        value = qty * length * width * height / 1000000
    elif _dimUOM in ["M", "METER"]:
        value = qty * length * width * height

    return value

def get_rounded_cubic_meter(length, width, height, uom="METER", qty=1):
    import math

    value = 0
    _dimUOM = uom.upper()

    if _dimUOM in ["MM", "MILIMETER"]:
        value = qty * math.ceil(length / 10) * math.ceil(width / 10) * math.ceil(height / 10) / 1000000
    elif _dimUOM in ["CM", "CENTIMETER"]:
        value = qty * math.ceil(length) * math.ceil(width) * math.ceil(height) / 1000000
    elif _dimUOM in ["M", "METER"]:
        value = qty * math.ceil(length * 100) * math.ceil(width * 100) * math.ceil(height * 100) / 1000000

    return value

def getM3ToKgFactor(freight_provider, length, width, height, weight, dimUOM, weightUOM):
    if freight_provider:
        if freight_provider.lower() == "hunter":
            _length = length * getDimRatio(dimUOM)
            _width = width * getDimRatio(dimUOM)
            _height = height * getDimRatio(dimUOM)
            _weight = weight * getWeightRatio(weightUOM)

            if _length > 1.2 and _width > 1.2:
                return 333
            if _height > 1.8:
                return 333
            if (_length > 1.2 or _width > 1.2) and _weight > 59:
                return 333
        elif freight_provider and freight_provider.lower() == "northline":
            return 333
    return 250


def getDimRatio(dimUOM):
    _dimUOM = dimUOM.upper()

    if _dimUOM == "CM" or _dimUOM == "CENTIMETER":
        return 0.01
    elif _dimUOM == "METER" or _dimUOM == "M":
        return 1
    elif _dimUOM == "MILIMETER" or _dimUOM == "MM":
        return 0.001
    else:
        return 1


def getWeightRatio(weightUOM):
    _weightUOM = weightUOM.upper()

    if _weightUOM == "T" or _weightUOM == "TON":
        return 1000
    elif _weightUOM == "KG" or _weightUOM == "KILOGRAM":
        return 1
    elif _weightUOM == "G" or _weightUOM == "GRAM":
        return 0.001
    else:
        return 1
