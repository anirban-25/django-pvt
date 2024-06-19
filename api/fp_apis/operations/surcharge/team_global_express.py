def get_pallet_count(param):
    pallet_count = 0
    try:
        for line in param["lines_data"]:
            if line["is_pallet"]:
                pallet_count += line["quantity"]
    except Exception as e:
        pallet_count = 0

    return pallet_count


def asf(param):
    return {
        "name": "Account Service Fee",
        "description": "Charged to all invoice / statements.",
        "value": 29.95,
    }


# def atf(param):
#     if :
#         return {
#             "name": "Account Transfer Fee",
#             "description": "Applicable to all transfer of freight charges contrary to the original instructions of the sender.",
#             "value": 29.95,
#         }
#     else:
#         return None

# def ccf(param):
#     if :
#         return {
#             "name": "Cancelled – Connote Fee",
#             "description": "An administrative charge where a consignment is manifested and posted electronically to Team Global Express but where no freight is presented.",
#             "value": 2.70,
#         }
#     else:
#         return None


def dg(param):
    if param["has_dangerous_item"]:
        return {
            "name": "Dangerous Goods",
            "description": "For the additional labour, facility and legislative compliance costs involved with processing and moving goods classed as ‘Dangerous’ under the Australian Dangerous Code.",
            "value": 57.25 if param["vx_service_name"] == "IPEC" else 152.20,
        }
    else:
        return None


def ewp(param):
    if param["pu_address_state"] == "WA" and (
        param["de_to_address_state"] == "WA" or param["de_to_address_state"] == "NT"
    ):
        # "Applicable to all consignments that are collected in WA and either sent to WA or NT locations. Not applicable to items collected in WA and sent to other states and territories.
        #    This fee is charged as a flat rate plus a kg rate."	 $51.50 	"per consignment; plus"
        #    1kg to 1000kg	 $0.09 	per kg
        #    1001 kg to 3000kg	 $0.09 	per kg
        #    3001 kg to 8000kg	 $0.07 	per kg
        #    8001 kg to 99999kg	 $0.04 	per kg

        fee_rate = 0
        if param["max_weight"] >= 1 and param["max_weight"] <= 1000:
            fee_rate = 0.09
        elif param["max_weight"] > 1000 and param["max_weight"] <= 3000:
            fee_rate = 0.09
        elif param["max_weight"] > 3000 and param["max_weight"] <= 8000:
            fee_rate = 0.07
        elif param["max_weight"] > 8000:
            fee_rate = 0.04
        return {
            "name": "Ex WA Pickup Charge",
            "description": "Applicable to all consignments that are collected in WA and either sent to WA or NT locations.",
            "value": 51.50 + fee_rate * param["max_weight"],
        }
    else:
        return None


def hd(param):
    # I&S Oversize Manual Handling Fee:
    # I&S | OVERSIZE       - if carton is 20 < weight 63.50 per item

    lines = param["lines_data"]
    large_oversize_item_cnt = 0
    for line in lines:
        if 20 < line["max_weight"]:
            large_oversize_item_cnt += line["quantity"]

    if large_oversize_item_cnt:
        # Aberdeen Paper, Anchor Packaging, Ariston Wire
        if param["client_id"] in ["4ac9d3ee-2558-4475-bdbb-9d9405279e81", "49294ca3-2adb-4a6e-9c55-9b56c0361953" , "c8f0b7fc-7088-498b-bf3e-ec0fb8dc8851"] and param["de_no_of_assists"] < 2:
            return None
        return {
            "name": "Oversize Manual Handling Fee",
            "description": "Deliver to residential, office buildings and retail stores addresses will incur a charge",
            "value": 63.50 * large_oversize_item_cnt,
            "quantity": large_oversize_item_cnt,
        }


def ol(param):
    if param["max_dimension"] >= 3.7 and param["max_dimension"] < 6:
        return {
            "name": "Over-length Goods",
            "description": "Where the length of the consignment matches the following dimensions.",
            "value": 139.65,
        }
    elif param["max_dimension"] >= 6 and param["max_dimension"] < 7.3:
        return {
            "name": "Over-length Goods",
            "description": "Where the length of the consignment matches the following dimensions.",
            "value": 203.15,
        }
    elif param["max_dimension"] >= 7.3:
        return {
            "name": "Over-length Goods",
            "description": "Where the length of the consignment matches the following dimensions.",
            "value": 759.85,
        }
    else:
        return None


def oz(param):
    # IPEC Oversize Manual Handling Fee:
    # IPEC | OVERSIZE
    #   if carton is
    #       30<weight<35    OR
    #       1.2<maxDIM<1.8  OR
    #       0.8<width       OR
    #       0.6<height      OR
    #       AND cubic meter < 0.7m3
    #       Then oversize fee or 12.85 per item

    original_lines = param["original_lines_data"]
    oversize_item_cnt = 0
    for index, line in enumerate(original_lines):
        if (
            (1.2 < line["max_dimension"] and line["max_dimension"] < 1.8)
            or 0.8 < line["e_dimWidth"]
            or 0.6 < line["e_dimHeight"]
            or (30 < line["weight"] and line["weight"] < 35)
        ) and line["cubic"] < 0.7:
            # DEBUG Point
            # print(
            #     "Oversize Manual Handling Fee - ",
            #     index + 1,
            #     line["e_item"],
            #     line["max_dimension"],
            #     line["weight"],
            #     line["cubic"],
            #     line["e_qty"],
            # )
            oversize_item_cnt += line["e_qty"]

    if oversize_item_cnt:
        return {
            "name": "Oversize Manual Handling Fee",
            "description": "Deliver to residential, office buildings and retail stores addresses will incur a charge",
            "value": 13.75 * oversize_item_cnt,
            "quantity": oversize_item_cnt,
        }


def ozl(param):
    # IPEC Large Oversize Manual Handling Fee:
    # IPEC | LARGE OVERSIZE - if carton is 35<weight    | 1.8<maxDIM        | cubic meter > 0.7m3 then oversize fee or 53.50 per item

    original_lines = param["original_lines_data"]
    large_oversize_item_cnt = 0
    for line in original_lines:
        if (1.8 <= line["max_dimension"] or 35 <= line["weight"]) and 0.7 <= line[
            "cubic"
        ]:
            large_oversize_item_cnt += line["e_qty"]

    if large_oversize_item_cnt:
        return {
            "name": "Large Oversize Manual Handling Fee",
            "description": "Deliver to residential, office buildings and retail stores addresses will incur a charge",
            "value": 57.25 * large_oversize_item_cnt,
            "quantity": large_oversize_item_cnt,
        }


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


# def lp(param):
#     if ():
#         return {
#             "name": "Lost Pallets",
#             "description": "Lost or outstanding Chep/Loscam pallets.",
#             "value": "$50 per pallet",
#         }
#     else:
#         return None


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
    original_lines = param["original_lines_data"]
    has_big_item = False
    for line in original_lines:
        if line["weight"] >= 30:
            has_big_item = True

    # if param["is_tail_lift"] or has_big_item:
    if param["is_tail_lift"]:
        if param["vx_service_name"] == "IPEC":
            return {
                "name": "Tail Lift Requirement",
                "description": "When a consignment involving pallets or other heavy consignments requires the use of a tail lift or tilt tray truck.",
                "value": 83.00,
                "quantity": 1,
            }
        pallet_count = get_pallet_count(param)
        if pallet_count <= 2:
            return {
                "name": "Tail Lift Requirement",
                "description": "When a consignment involving pallets or other heavy consignments requires the use of a tail lift or tilt tray truck.",
                "value": 89.30,
                "quantity": 1,
            }
        else:
            return {
                "name": "Tail Lift Requirement",
                "description": "When a consignment involving pallets or other heavy consignments requires the use of a tail lift or tilt tray truck.",
                "value": 89.30 + 44.60 * (pallet_count - 2),
                "quantity": pallet_count,
            }


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


def team_global_express_ins():
    return {
        "order": [
            # asf,
            # atf,
            # ccf,
            dg,
            ewp,
            hd,
            # oz,
            # ozl,
            # et,
            # fup_fud,
            # ha,
            # hz,
            # lp,
            # rd,
            # rrl,
            # rsibf,
            # rp,
            # sw,
            # slpd,
            # sh,
            tgp_tgd,
            # tl,
            # wt,
            # wht
        ],
        "line": [
            ol,
            # op
        ],
    }


def team_global_express_ipec():
    return {
        "order": [
            # asf,
            # atf,
            # ccf,
            dg,
            # ewp,
            # hd,
            oz,
            ozl,
            # et,
            # fup_fud,
            # ha,
            # hz,
            # lp,
            # rd,
            # rrl,
            # rsibf,
            # rp,
            # sw,
            # slpd,
            # sh,
            tgp_tgd,
            # tl,
            # wt,
            # wht
        ],
        "line": [
            # oz,
            # op
        ],
    }
