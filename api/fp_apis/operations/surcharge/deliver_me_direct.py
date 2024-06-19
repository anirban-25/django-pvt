import logging


logger = logging.getLogger(__name__)


def hd(param):
    if param["de_to_address_type"] == "residential":
        logger.info(f'[SURCHARGE] Deliver-Me Direct: hd {param["pu_address_type"]}, {param["de_to_address_type"]}')
        return {
            "name": "Home Delivery/Residential",
            "description": "Pickups and/or deliveries to private addresses. Hand load/unload, tailgate and waiting time fees may also apply where applicable.",
            "value": 50,
        }
    else:
        return None


def tgp_tgd(param):
    if param["is_tail_lift"]:
        logger.info(f'[SURCHARGE] Deliver-Me Direct: tgp_tgd {param["is_tail_lift"]}')
        return {
            "name": "Tailgate",
            "description": "Pickups and/or deliveries requiring the use of a Tailgate vehicle.",
            "value": 50,
        }
    else:
        return None


def deliver_me_direct():
    return {
        "order": [
            hd,
            tgp_tgd,
        ],
        "line": [
        ],
    }
