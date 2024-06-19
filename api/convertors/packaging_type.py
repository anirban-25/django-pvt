def get_package_type(original_type):
    if not original_type:
        return "Carton"

    _original_type = original_type.lower()
    if "ctn" in _original_type or "carton" in _original_type:
        return "Carton"
    elif "packet" in _original_type:
        return "Packet"
    elif "pkg" in _original_type or "package" in _original_type:
        return "Package"
    elif (
        "plt" in _original_type or "pal" in _original_type or "pallet" in _original_type
    ):
        return "Pallet"
    elif "roll" in _original_type:
        return "Roll"
    else:
        return original_type
