import math


def ceil(number, digits) -> float:
    return math.ceil((10.0 ** digits) * number) / (10.0 ** digits)
