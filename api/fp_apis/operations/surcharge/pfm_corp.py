
from api.models import FP_zones, Fp_freight_providers


def is_regional(param):
    fp_id = Fp_freight_providers.objects.get(
            fp_company_name=param["vx_freight_provider"]
        ).id
    zone = FP_zones.objects.filter(
        fk_fp=fp_id,
        state=param["pu_address_state"],
        postal_code=param["pu_address_postcode"],
        suburb=param["pu_address_suburb"],
    ).first()

    if zone:
        pu_sender_code = zone.sender_code
    else:
        pu_sender_code = None  # Or set it to another default value
   
    zone = FP_zones.objects.filter(
        fk_fp=fp_id,
        state=param["de_to_address_state"],
        postal_code=param["de_to_address_postcode"],
        suburb=param["de_to_address_suburb"],
    ).first()

    if zone:
        de_sender_code = zone.sender_code
    else:
        de_sender_code = None  # Or set it to another default value

    if pu_sender_code == "REGIONAL" or de_sender_code == "REGIONAL":
        return True
    else:
        return False
    
def is_depot(param):
    valid_addresses = [
        {"state": "NSW", "postcode": "2164", "suburb": "Wetherill Park", "street1": "2/147 Newton Rd", "street2": "2/147 Newton Rd"},
        {"state": "NSW", "postcode": "2322", "suburb": "Beresfield", "street1": "1/2 Gamma Cl", "street2": "1/2 Gamma Cl"},
        {"state": "ACT", "postcode": "2609", "suburb": "Fyshwick", "street1": "120 Gladstone St", "street2": "120 Gladstone St"},
        {"state": "QLD", "postcode": "4117", "suburb": "Berrinba", "street1": "29 WayneGoss Dr", "street2": "51 WayneGoss Dr"},
        {"state": "QLD", "postcode": "4869", "suburb": "Edmonton", "street1": "3/57 Swallow Rd", "street2": "3/59 Swallow Rd"},
        {"state": "QLD", "postcode": "4818", "suburb": "Bohle", "street1": "4 Trade Crt", "street2": "4 Trade Crt"},
        {"state": "SA", "postcode": "5009", "suburb": "Beverley", "street1": "113 Ledger Rd", "street2": "113 Ledger Rd"},
        {"state": "WA", "postcode": "6155", "suburb": "Canning Vale", "street1": "32 Gauge Cct", "street2": "32 Gauge Cct"},
        {"state": "VIC", "postcode": "3175", "suburb": "Dandenong South", "street1": "1/81 Princes Hwy", "street2": "1/97 Princes Hwy"},
        {"state": "TAS", "postcode": "7249", "suburb": "Kings Meadows", "street1": "2/20 Merino St", "street2": "2/22 Merino St"},
        {"state": "NT", "postcode": "0820", "suburb": "Winnellie", "street1": "10 Menmuir St (Rear Shed)", "street2": "10 Menmuir St (Rear Shed)"}
    ]

    for address in valid_addresses:
        if (param["pu_address_state"].upper() == address["state"] and
            param["pu_address_postcode"] == address["postcode"] and
            param["pu_address_suburb"].upper() == address["suburb"].upper() and
            param["pu_address_street"].upper() >= address["street1"].upper() and
            param["pu_address_street"].upper() <= address["street2"].upper()):
            return True

    return False

def rd0(param):
    if is_regional(param) and param["max_weight"] <= 100:
        return {
            "name": "Regional Delivery - Category A",
            "description": "Regional Delivery/Collection Rates /Collection Rates Service Type / Category A Weight Break / 0 - 100kgs Per Consignment / $111.00",
            "value": 111,
        }

def rd1(param):
    if is_regional(param) and 100 < param["max_weight"] <= 250:
        return {
            "name": "Regional Delivery - Category B",
            "description": "Regional Delivery/Collection Rates /Collection Rates Service Type / Category B Weight Break / 101 - 250kgs Per Consignment / $148.00",
            "value": 148,
        }

def rd2(param):
    if is_regional(param) and 250 < param["max_weight"] <= 500:
        return {
            "name": "Regional Delivery - Category C",
            "description": "Regional Delivery/Collection Rates /Collection Rates Service Type / Category C Weight Break / 251 - 500kgs Per Consignment / $237.00",
            "value": 237,
        }

def rd3(param):
    if is_regional(param) and 500 < param["max_weight"]:
        return {
            "name": "Regional Delivery - Category D",
            "description": "Regional Delivery/Collection Rates /Collection Rates Service Type / Category D Weight Break / 501kgs Per Consignment / Category C Plus 0.22 per kg",
            "value": 237 + (param["max_weight"] - 500) * 0.22,
        }

def hp0(param):
    if not is_depot(param) and param["max_weight"] <= 100:
        return {
            "name": "Hub Pickup - Cat A",
            "description": "Per Consignment Collection from Hub if Unable to Delivery to PFM Depot",
            "value": 16.13,
        }

def hp1(param):
    if not is_depot(param) and 100 < param["max_weight"] <= 250:
        return {
            "name": "Hub Pickup - Cat B",
            "description": "Per Consignment Collection from Hub if Unable to Delivery to PFM Depot",
            "value": 21.82,
        }

def hp2(param):
    if not is_depot(param) and 250 < param["max_weight"] <= 500:
        return {
            "name": "Hub Pickup - Cat C",
            "description": "Per Consignment Collection from Hub if Unable to Delivery to PFM Depot",
            "value": 34.15,
        }

def hp3(param):
    if not is_depot(param) and 500 < param["max_weight"]:
        return {
            "name": "Hub Pickup - Cat D",
            "description": "Per Consignment Collection from Hub if Unable to Delivery to PFM Depot",
            "value": 34.15,
        }

def pfm_corp():
    return {
        "order": [
            rd0,
            rd1,
            rd2,
            rd3,
            hp0,
            hp1,
            hp2,
            hp3,
        ],
        "line": [],
    }
