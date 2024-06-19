def is_in_postal_code_ranges(postal_code, ps_ranges):
    """
    Check if a PostalCode is in PostalCode ranges

    * postal_code: 2000
    * ps_ranges: ["1000-2000", "2500", "3000-4000"]
    """

    if not postal_code or not ps_ranges:
        return False

    for one_or_range in ps_ranges:
        if "-" in one_or_range:
            _from = one_or_range.split("-")[0]
            _to = one_or_range.split("-")[1]
            if int(_from) <= int(postal_code) <= int(_to):
                return True
        else:
            _one = one_or_range
            if int(postal_code) == int(_one):
                return True

    return False
