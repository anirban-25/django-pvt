import logging

logger = logging.getLogger(__name__)

# Get `serviceCode` from `serviceName`
def get_service_code(service_name):
    service_code = None

    if service_name in ["Overnight 09:00", "09:00 Express"]:
        service_code = "712"
    elif service_name in ["Overnight 10:00", "10:00 Express"]:
        service_code = "X10"
    elif service_name in ["Overnight 12:00", "12:00 Express"]:
        service_code = "X12"
    elif service_name == "Overnight Express":
        service_code = "75"
    elif service_name == "Road Express":
        service_code = "76"
    elif service_name == "Technology Express - Sensitive Express":
        service_code = "717"
    elif service_name == "Fashion Express – Carton":
        service_code = "718"
    elif service_name == "Sameday Domestic":
        service_code = "701"
    elif "satchel" in service_name.lower():
        service_code = "73"
    else:
        error_msg = (
            f"@118 Error: TNT({service_name}) - there is no service code matched."
        )
        logger.info(error_msg)

    return service_code
