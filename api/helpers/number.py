def is_float(string):
    try:
        float(string)
    except ValueError:
        return False
    return True
