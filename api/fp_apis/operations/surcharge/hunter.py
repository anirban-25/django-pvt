from cgi import parse_multipart


def el0(param):
    if param["max_dimension"] >= 1.5 and param["max_dimension"] < 2.5:
        return {
            "name": "Excess Lengths: 1.5m up to/not incl. 2.5m",
            "description": "",
            "value": 10,
        }
    else:
        return None


def el1(param):
    if param["max_dimension"] >= 2.5 and param["max_dimension"] < 4:
        return {
            "name": "Excess Lengths: 2.5m up to/not incl. 4.0m",
            "description": "",
            "value": 50,
        }
    else:
        return None


# dummy value for below two
def el2(param):
    if param["max_dimension"] >= 4:
        return {
            "name": "Excess Lengths: 4m up to/not incl. 6.0m",
            "description": "",
            "value": 200,
        }
    else:
        return None

def pu_residential_charge(param):
    address_type = param["pu_address_type"].lower()
    max_item_weight = param["max_item_weight"]
    if address_type == "residential":
        if max_item_weight >= 35 and max_item_weight < 50:
            return {
                "name": "Bulk Pickup from Residential Address - Average dead or cubic weight per item 35-49kg",
                "description": "",
                "value": 10,
            }
        elif max_item_weight >=50 and max_item_weight < 75:
            return {
                "name": "Bulk Pickup from Residential Address - Average dead or cubic weight per item 50-74kg",
                "description": "",
                "value": 20,
            }
        elif max_item_weight >= 75 and max_item_weight < 100:
            return {
                "name": "Bulk Pickup from Residential Address - Average dead or cubic weight per item 75-99kg",
                "description": "",
                "value": 30,
            }
        elif max_item_weight >= 100:
            return {
                "name": "Bulk Pickup from Residential Address - Average dead or cubic weight per item 100kg or greater",
                "description": "",
                "value": 50,
            }
        else:
            return None
    else:
        return None

def de_residential_charge(param):
    address_type = param["de_to_address_type"].lower()
    max_item_weight = param["max_item_weight"]
    if address_type == "residential":
        if max_item_weight >= 35 and max_item_weight < 50:
            return {
                "name": "Bulk Delivery to Residential Address - Average dead or cubic weight per item 35-49kg",
                "description": "",
                "value": 10,
            }
        elif max_item_weight >=50 and max_item_weight < 75:
            return {
                "name": "Bulk Delivery to Residential Address - Average dead or cubic weight per item 50-74kg",
                "description": "",
                "value": 20,
            }
        elif max_item_weight >= 75 and max_item_weight < 100:
            return {
                "name": "Bulk Delivery to Residential Address - Average dead or cubic weight per item 75-99kg",
                "description": "",
                "value": 30,
            }
        elif max_item_weight >= 100:
            return {
                "name": "Bulk Delivery to Residential Address - Average dead or cubic weight per item 100kg or greater",
                "description": "",
                "value": 50,
            }
        else:
            return None
    else:
        return None


def ptl(param):
    if param["pu_tail_lift"] and int(param["pu_tail_lift"]) != 0:
        return {
            "name": "Tail-Lift Truck8(pickup)",
            "description": "",
            "value": 60,
        }
    else:
        return None


def dtl(param):
    if param["de_tail_lift"] and int(param["de_tail_lift"]) != 0:
        return {
            "name": "Tail-Lift Truck8(delivery)",
            "description": "",
            "value": 60,
        }
    else:
        return None


def hunter():
    return {
        "order": [ pu_residential_charge, de_residential_charge, ptl, dtl, el0, el1, el2 ],
        "line": [],
    }
