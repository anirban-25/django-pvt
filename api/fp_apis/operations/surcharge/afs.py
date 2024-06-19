# def asf(param):
#     if :
#         return {
#             "name": "Account Service Fee",
#             "description": "Charged by account per trading week",
#             "value": 7,
#         }
#     else:
#         return None


# def al(param):
#     if :
#         return {
#             "name": "Additional Labour",
#             "description": "Any pickup and/or delivery requiring an extra person",
#             "value": 80 * hour,
#         }
#     else:
#         return None


def dg(param):
    if param["has_dangerous_item"]:
        return {
            "name": "Dangerous Goods",
            "description": "Dangerous Goods consignments incurr a 25% surcharge ontop of the freight rate + $15 Basic Charge",
            "value": param["quote_obj"].fee * 0.25 + 15,
        }
    else:
        return None


# def et(param):
#     if :
#         return {
#             "name": "Express Transit",
#             "description": "The fee applies where Pickup and/or delivery to a time window where the transit is 1 or more days inside the published general transit schedule. All requests are required to be approved with a Sales Representative prior to booking.",
#             "value": "40% sucharge, min surcharge fee $90",
#         }
#     else:
#         return None


# def fup_fud(param):
#     if :
#         if (regid vehicle):
#             return {
#                 "name": "Futile Delivery/Pickup",
#                 "description": "Where a vehicle is dispatched, and the goods are unable to be either picked up or delivered",
#                 "value": 40,
#             }
#         elif(semi-trailer/b-double vehicles):
#             return {
#                 "name": "Futile Delivery/Pickup",
#                 "description": "Where a vehicle is dispatched, and the goods are unable to be either picked up or delivered",
#                 "value": 120,
#             }
#         else:
#             return None
#     else:
#         return None


# def ha(param):
#     if () and ():
#         return {
#             "name": "Hand Load/Unload",
#             "description": "Goods with a maximum item weight of 25 kilograms which require hand loading or offloading. Multiple consignments booked on the same job will have the time calculated on the total job. Charges will be calculated in 15-minute increments from time of arrival onsite.",
#             "value": "$35 per 15 mins",
#         }
#     else:
#         return None


# def hz(param):
#     if ():
#         return {
#             "name": "Hazardous Goods Transport",
#             "description": "Goods transported as Hazardous or Waste product, declarable under the Environmental Protection Act.",
#             "value": 120,
#         }
#     else:
#         return None


def hd(param):
    if (
        param["pu_address_type"].lower() == "residential"
        or param["de_to_address_type"] == "residential"
    ):
        return {
            "name": "Home Delivery/Residential",
            "description": "Pickups and/or deliveries to private addresses. Hand load/unload, tailgate and waiting time fees may also apply where applicable.",
            "value":  9.50 ,
        }
    else:
        return None


# def lp(param):
#     if ():
#         return {
#             "name": "Lost Pallets",
#             "description": "Lost or outstanding Chep/Loscam pallets.",
#             "value": "$50 per pallet",
#         }
#     else:
#         return None


def ol(param):
    if param["max_dimension"] > 3 and param["max_dimension"] <= 6:
        return {
            "name": "Over-length Goods",
            "description": "Where the length of the consignment matches the following dimensions.",
            "value": 105,
        }
    elif param["max_dimension"] > 6 and param["max_dimension"] <= 9:
        return {
            "name": "Over-length Goods",
            "description": "Where the length of the consignment matches the following dimensions.",
            "value": 315,
        }
    elif param["max_dimension"] > 9:
        return {
            "name": "Over-length Goods",
            "description": "Where the length of the consignment matches the following dimensions.",
            "value": 1000,
        }
    else:
        return None


# def op(param):
#     if ():
#         return {
#             "name": "Oversize Pallets/Un-Packed Goods",
#             "description": "Oversized and/or unpacked goods that have been accepted by Northline will be charged by the equivalent pallet space/s area taken up on the load. Measurements will be taken to the trailer height and width and not the product height and width.",
#             "value": "POA",
#         }
#     else:
#         return None


# def rd(param):
#     if ():
#         return {
#             "name": "Redirection Fee/Incorrect Address",
#             "description": "It is the responsibility of the Customer to provide the correct pickup and delivery address. Where an incorrect address is supplied a re-direction fee will be applicable to have the consignment re-delivered. This applies when redirected whilst in transit or when futile delivery has occurred, and the redelivery is to a new destination.",
#             "value": "POA",
#         }
#     else:
#         return None


# def rrl(param):
#     if ():
#         return {
#             "name": "Regionals and Remote Locations",
#             "description": "Regional pricing is to the nominated township area and immediate surrounds only (it does not refer to the area governed i.e. shire or city of). Whilst every effort is made to provide accurate pricing, on occasion Northline may be charged “extra” by our Agents for locations outside of this area or for difficult to access sites. When this occurs, Northline reserves the right to charge an additional fee or the Receiver may be given the option of collecting the freight from the Agent’s depot.",
#             "value": "POA",
#         }
#     else:
#         return None


# def rsibf(param):
#     if ():
#         return {
#             "name": "Remote Sites, Islands, Barge or Ferry Services",
#             "description": "Goods to these sites may incur additional charges. Please discuss these with a Sales Representative prior to booking.",
#             "value": "POA",
#         }
#     else:
#         return None


# def rp(param):
#     if ():
#         return {
#             "name": "Reporting: Non-Standard",
#             "description": "Where Northline are required to provide non-standard or tailored performance reports, a format will be agreed on before the customer will be charged for this service.",
#             "value": "$45 per hour",
#         }
#     else:
#         return None


# def sw(param):
#     if () and ():
#         return {
#             "name": "Short Term Holding/Warehousing",
#             "description": "The development of any non-standard or tailored reports at the request of a Customer. Goods which have been negotiated to be held or where the delivery cannot be performed within 4 days.",
#             "value": "$7 per pallet per day",
#         }
#     elif () and ():
#         return {
#             "name": "Short Term Holding/Warehousing",
#             "description": "The development of any non-standard or tailored reports at the request of a Customer. Goods which have been negotiated to be held or where the delivery cannot be performed within 4 days.",
#             "value": "POA",
#         }
#     else:
#         return None


# def slpd(param):
#     if ():
#         return {
#             "name": "Specialized Lifting or Pickup/Delivery",
#             "description": "Rates do not include specialised vehicle requirements such as Hiabs or Crane vehicles. The cost for the use of these specialised vehicles will be priced on application.",
#             "value": "POA",
#         }
#     else:
#         return None


# def sh(param):
#     if ():
#         return {
#             "name": "Storage and Handling",
#             "description": "Specific to Warehousing Customers. Goods will be stored and warehoused in a manner that is safe, proper and fit for purpose. Goods to be despatched will be assembled in a manner that ensures no damage occurs to the goods during transport. Documentation will also be sent with the despatched orders. Northline’s warehousing services will include the following activities: -Receiving into store as per agreed timeframes -Order picking, processing and despatching as per agreed timeframes -Confirming orders directly from WMS and checking prior to despatch -All orders are generated with industry serial shipping container code and address labels -Unloading all imported or domestic goods -Storing all goods whilst ensuring FIFO or FEFO, as directed by customer -Completing Cycle counts/stocktakes as required by customer -Ensuring efficient WMS interface with controls in place for systems/figures integrity",
#             "value": "POA",
#         }
#     else:
#         return None


def tgp_tgd(param):
    if param["is_tail_lift"]:
        return {
            "name": "Tailgate",
            "description": "Pickups and/or deliveries requiring the use of a Tailgate vehicle.",
            "value": 52,
        }
    else:
        return None


# def tl(param):
#     if ():
#         return {
#             "name": "Top Load Only",
#             "description": "Freight designated as “top load only” may attract a charge equivalent to the full pallet height of the trailer.",
#             "value": "",
#         }
#     else:
#         return None


# def wt(param):
#     if ():
#         if () and ():
#             return {
#                 "name": "Waiting Time",
#                 "description": "Charge applies where allocated loading and/or unloading time is exceeded and will be calculated in 15-minute increments.",
#                 "value": "$25 per 15 mins",
#             }
#         elif () and ():
#             return {
#                 "name": "Waiting Time",
#                 "description": "Charge applies where allocated loading and/or unloading time is exceeded and will be calculated in 15-minute increments.",
#                 "value": "$30 per 15 mins",
#             }
#         else:
#             return None
#     else:
#         return None


# def wht(param):
#     if ():
#         return {
#             "name": "Wharf Terminal",
#             "description": "Timeslot booking fees and infrastructure fees charged by wharf terminal providers for containers picked up or dropped off at the wharf will be passed onto the Customer.",
#             "value": "POA",
#         }
#     else:
#         return None


def afs():
    return {
        "order": [
            # asf,
            # al,
            # dg,
            # et,
            # fup_fud,
            # ha,
            # hz,
            hd,
            # lp,
            # rd,
            # rrl,
            # rsibf,
            # rp,
            # sw,
            # slpd,
            # sh,
            # tgp_tgd,
            # tl,
            # wt,
            # wht
        ],
        "line": [
            # ol,
            # op
        ],
    }
