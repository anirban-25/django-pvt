import json
import logging
import xml.etree.ElementTree as ET

from django.conf import settings

from api.outputs.soap import send_soap_request
from api.outputs.email import send_email
from api.models import BOK_1_headers, BOK_2_lines, Log, FPRouting
from api.operations.email_senders import send_email_to_admins

logger = logging.getLogger(__name__)


def build_xml_with_booking(booking, lines):
    # Validations
    message = None

    if not booking.b_client_order_num:
        message = "'b_client_order_num' is missing"

    if not booking.de_to_Contact_F_LName:
        message = (
            "{booking.b_client_order_num} issue: 'de_to_Contact_F_LName' is missing"
        )

    if not booking.de_To_Address_Street_1:
        message = (
            "{booking.b_client_order_num} issue: 'de_To_Address_Street_1' is missing"
        )

    if not booking.de_To_Address_Suburb:
        message = (
            "{booking.b_client_order_num} issue: 'de_To_Address_Suburb' is missing"
        )

    if not booking.de_To_Address_State:
        message = "{booking.b_client_order_num} issue: 'de_To_Address_State' is missing"

    if not booking.api_booking_quote:
        message = "{booking.b_client_order_num} issue: no quotes"

    if not booking.de_To_Address_PostalCode:
        message = (
            "{booking.b_client_order_num} issue: 'de_To_Address_PostalCode' is missing"
        )

    if message:
        raise Exception(message)

    # Constants
    dme_account_num = "50365"
    customer_order_number = "y"
    order_type_code = "QI"
    customer_country = "AU"
    order_priority = "11"
    warehouse_code = "01"
    geographic_code = ""
    reference_number = ""
    send_status = "x"

    # Init result var
    _xml = ET.Element(
        "soapenv:Envelope",
        {
            "xmlns:soapenv": "http://schemas.xmlsoap.org/soap/envelope/",
            "xmlns:sal": "http://www.paperless-warehousing.com/ACR/SalesOrderToWMS",
        },
    )

    # Add XML Header
    ET.SubElement(_xml, "soapenv:Header")

    # Build XML Body
    Body = ET.SubElement(_xml, "soapenv:Body")
    SalesOrderToWMS = ET.SubElement(Body, "sal:SalesOrderToWMS")

    # Build Header
    Header = ET.SubElement(SalesOrderToWMS, "Header")

    if not booking.b_client_order_num:
        raise Exception({"message": "Order number is null."})

    OrderNumber = ET.SubElement(Header, "OrderNumber")
    OrderNumber.text = f"{dme_account_num}{booking.b_client_order_num}"

    NumberOfDetails = ET.SubElement(Header, "NumberOfDetails")
    NumberOfDetails.text = str(lines.count())

    HostOrderNumber = ET.SubElement(Header, "HostOrderNumber")
    HostOrderNumber.text = f"{dme_account_num}{booking.pk}"

    CustomerNumber = ET.SubElement(Header, "CustomerNumber")
    CustomerNumber.text = f"{dme_account_num}{booking.b_client_order_num}"

    CustomerName = ET.SubElement(Header, "CustomerName")
    CustomerName.text = booking.de_to_Contact_F_LName or ""

    CustomerOrderNumber = ET.SubElement(Header, "CustomerOrderNumber")
    CustomerOrderNumber.text = customer_order_number

    OrderTypeCode = ET.SubElement(Header, "OrderTypeCode")
    OrderTypeCode.text = order_type_code

    CustomerStreet1 = ET.SubElement(Header, "CustomerStreet1")
    CustomerStreet1.text = booking.de_To_Address_Street_1 or ""

    CustomerStreet2 = ET.SubElement(Header, "CustomerStreet2")
    CustomerStreet2.text = booking.de_To_Address_Street_2 or ""

    CustomerStreet3 = ET.SubElement(Header, "CustomerStreet3")
    CustomerStreet3.text = ""

    CustomerSuburb = ET.SubElement(Header, "CustomerSuburb")
    CustomerSuburb.text = booking.de_To_Address_Suburb

    CustomerState = ET.SubElement(Header, "CustomerState")
    CustomerState.text = booking.de_To_Address_State

    CustomerPostCode = ET.SubElement(Header, "CustomerPostCode")
    CustomerPostCode.text = booking.de_To_Address_PostalCode

    CustomerCountry = ET.SubElement(Header, "CustomerCountry")
    CustomerCountry.text = customer_country

    OrderPriority = ET.SubElement(Header, "OrderPriority")
    OrderPriority.text = order_priority

    DeliveryInstructions = ET.SubElement(Header, "DeliveryInstructions")
    DeliveryInstructions.text = f"{booking.de_to_Pick_Up_Instructions_Contact or ''} {booking.de_to_PickUp_Instructions_Address or ''}"

    WarehouseCode = ET.SubElement(Header, "WarehouseCode")
    WarehouseCode.text = warehouse_code

    GeographicCode = ET.SubElement(Header, "GeographicCode")
    GeographicCode.text = geographic_code

    SpecialInstructions = ET.SubElement(Header, "SpecialInstructions")
    SpecialInstructions.text = booking.pu_pickup_instructions_address or ""

    Carrier = ET.SubElement(Header, "Carrier")
    _fp_name = booking.api_booking_quote.freight_provider.lower()

    if not booking.api_booking_quote:
        Carrier.text = ""
    elif _fp_name == "tnt":
        Carrier.text = "D_CHP"
    elif _fp_name == "hunter":
        Carrier.text = "D_CHP"
    elif _fp_name == "camerons":
        Carrier.text = "D_CHP"
    elif _fp_name == "allied":
        Carrier.text = "D_CHP"
    elif _fp_name == "team global express":
        Carrier.text = "D_TGE"
    elif _fp_name == "sendle":
        Carrier.text = "D_CHP"
    elif (
        _fp_name == "auspost" and booking.api_booking_quote.account_code == "2006871123"
    ):
        Carrier.text = "D_CHP"

    ReferenceNumber = ET.SubElement(Header, "ReferenceNumber")
    ReferenceNumber.text = reference_number

    # DespatchDate = ET.SubElement(Header, "DespatchDate")
    # DespatchDate.text = ""

    SendStatus = ET.SubElement(Header, "SendStatus")
    SendStatus.text = send_status

    ContactPhoneNumber1 = ET.SubElement(Header, "ContactPhoneNumber1")
    ContactPhoneNumber1.text = booking.de_to_Phone_Main

    CustomerEmailAddress = ET.SubElement(Header, "CustomerEmailAddress")
    CustomerEmailAddress.text = booking.de_Email

    if len(lines) == 0:
        message = f"{booking.b_client_order_num} issue: 0 lines"
        raise Exception(message)

    # Build Detail(s)
    for index, line in enumerate(lines):
        Detail = ET.SubElement(SalesOrderToWMS, "Detail")

        DetailSequenceNum = ET.SubElement(Detail, "DetailSequenceNum")
        DetailSequenceNum.text = str(index + 1)

        HostLineNumber = ET.SubElement(Detail, "HostLineNumber")
        HostLineNumber.text = str(line.pk)

        ProductCode = ET.SubElement(Detail, "ProductCode")
        ProductCode.text = f"{dme_account_num}{line.e_item_type}"

        QuantityOrdered = ET.SubElement(Detail, "QuantityOrdered")
        QuantityOrdered.text = str(line.e_qty)

    # ET.dump(_xml)  # Only used for debugging
    result = ET.tostring(_xml)
    return result


def build_xml_with_bok(bok_1, bok_2s):
    # Validations
    message = None

    if not bok_1.b_client_order_num:
        message = "'b_client_order_num' is missing"

    if not bok_1.b_061_b_del_contact_full_name:
        message = "{bok_1.b_client_order_num} issue: 'b_061_b_del_contact_full_name' is missing"

    if not bok_1.b_055_b_del_address_street_1:
        message = "{bok_1.b_client_order_num} issue: 'b_055_b_del_address_street_1' is missing"

    if not bok_1.b_058_b_del_address_suburb:
        message = (
            "{bok_1.b_client_order_num} issue: 'b_058_b_del_address_suburb' is missing"
        )

    if not bok_1.b_057_b_del_address_state:
        message = (
            "{bok_1.b_client_order_num} issue: 'b_057_b_del_address_state' is missing"
        )

    if not bok_1.quote:
        message = "{bok_1.b_client_order_num} issue: no quotes"

    if not bok_1.b_059_b_del_address_postalcode:
        message = "{bok_1.b_client_order_num} issue: 'b_059_b_del_address_postalcode' is missing"

    if message:
        raise Exception(message)

    # Constants
    dme_account_num = "50365"
    customer_order_number = "y"
    order_type_code = "QI"
    customer_country = "AU"
    order_priority = "11"
    warehouse_code = "01"
    geographic_code = ""
    reference_number = ""
    send_status = "x"

    # Init result var
    _xml = ET.Element(
        "soapenv:Envelope",
        {
            "xmlns:soapenv": "http://schemas.xmlsoap.org/soap/envelope/",
            "xmlns:sal": "http://www.paperless-warehousing.com/ACR/SalesOrderToWMS",
        },
    )

    # Add XML Header
    ET.SubElement(_xml, "soapenv:Header")

    # Build XML Body
    Body = ET.SubElement(_xml, "soapenv:Body")
    SalesOrderToWMS = ET.SubElement(Body, "sal:SalesOrderToWMS")

    # Build Header
    Header = ET.SubElement(SalesOrderToWMS, "Header")

    if not bok_1.b_client_order_num:
        raise Exception({"message": "Order number is null."})

    OrderNumber = ET.SubElement(Header, "OrderNumber")
    OrderNumber.text = f"{dme_account_num}{bok_1.b_client_order_num}"

    NumberOfDetails = ET.SubElement(Header, "NumberOfDetails")
    NumberOfDetails.text = str(bok_2s.count())

    HostOrderNumber = ET.SubElement(Header, "HostOrderNumber")
    HostOrderNumber.text = f"{dme_account_num}{bok_1.pk}"

    CustomerNumber = ET.SubElement(Header, "CustomerNumber")
    CustomerNumber.text = f"{dme_account_num}{bok_1.b_client_order_num}"

    CustomerName = ET.SubElement(Header, "CustomerName")
    CustomerName.text = bok_1.b_061_b_del_contact_full_name or ""

    CustomerOrderNumber = ET.SubElement(Header, "CustomerOrderNumber")
    CustomerOrderNumber.text = customer_order_number

    OrderTypeCode = ET.SubElement(Header, "OrderTypeCode")
    OrderTypeCode.text = order_type_code

    CustomerStreet1 = ET.SubElement(Header, "CustomerStreet1")
    CustomerStreet1.text = bok_1.b_055_b_del_address_street_1 or ""

    CustomerStreet2 = ET.SubElement(Header, "CustomerStreet2")
    CustomerStreet2.text = bok_1.b_056_b_del_address_street_2 or ""

    CustomerStreet3 = ET.SubElement(Header, "CustomerStreet3")
    CustomerStreet3.text = ""

    CustomerSuburb = ET.SubElement(Header, "CustomerSuburb")
    CustomerSuburb.text = bok_1.b_058_b_del_address_suburb

    CustomerState = ET.SubElement(Header, "CustomerState")
    CustomerState.text = bok_1.b_057_b_del_address_state

    CustomerPostCode = ET.SubElement(Header, "CustomerPostCode")
    CustomerPostCode.text = bok_1.b_059_b_del_address_postalcode

    CustomerCountry = ET.SubElement(Header, "CustomerCountry")
    CustomerCountry.text = customer_country

    OrderPriority = ET.SubElement(Header, "OrderPriority")
    OrderPriority.text = order_priority

    DeliveryInstructions = ET.SubElement(Header, "DeliveryInstructions")
    DeliveryInstructions.text = f"{bok_1.b_043_b_del_instructions_contact or ''} {bok_1.b_044_b_del_instructions_address or ''}"

    # DeliveryDate = ET.SubElement(Header, "DeliveryDate")
    # DeliveryDate.text = str(bok_1.b_050_b_del_by_date)

    WarehouseCode = ET.SubElement(Header, "WarehouseCode")
    WarehouseCode.text = warehouse_code

    GeographicCode = ET.SubElement(Header, "GeographicCode")
    GeographicCode.text = geographic_code

    SpecialInstructions = ET.SubElement(Header, "SpecialInstructions")
    SpecialInstructions.text = bok_1.b_016_b_pu_instructions_address or ""

    Carrier = ET.SubElement(Header, "Carrier")
    _fp_name = bok_1.quote.freight_provider.lower()

    if not bok_1.quote:
        Carrier.text = ""
    elif _fp_name == "tnt":
        Carrier.text = "D_CHP"
    elif _fp_name == "hunter":
        Carrier.text = "D_CHP"
    elif _fp_name == "camerons":
        Carrier.text = "D_CHP"
    elif _fp_name == "allied":
        Carrier.text = "D_CHP"
    elif _fp_name == "team global express":
        Carrier.text = "D_TGE"
    elif _fp_name == "sendle":
        Carrier.text = "D_CHP"
    elif _fp_name == "auspost" and bok_1.quote.account_code == "2006871123":
        Carrier.text = "D_CHP"

    ReferenceNumber = ET.SubElement(Header, "ReferenceNumber")
    ReferenceNumber.text = reference_number

    # DespatchDate = ET.SubElement(Header, "DespatchDate")
    # DespatchDate.text = ""

    SendStatus = ET.SubElement(Header, "SendStatus")
    SendStatus.text = send_status

    ContactPhoneNumber1 = ET.SubElement(Header, "ContactPhoneNumber1")
    ContactPhoneNumber1.text = bok_1.b_064_b_del_phone_main

    CustomerEmailAddress = ET.SubElement(Header, "CustomerEmailAddress")
    CustomerEmailAddress.text = bok_1.b_063_b_del_email

    if len(bok_2s) == 0:
        message = f"{bok_1.b_client_order_num} issue: 0 lines"
        raise Exception(message)

    # Build Detail(s)
    for index, bok_2 in enumerate(bok_2s):
        Detail = ET.SubElement(SalesOrderToWMS, "Detail")

        DetailSequenceNum = ET.SubElement(Detail, "DetailSequenceNum")
        DetailSequenceNum.text = str(index + 1)

        HostLineNumber = ET.SubElement(Detail, "HostLineNumber")
        HostLineNumber.text = str(bok_2.pk_lines_id)

        ProductCode = ET.SubElement(Detail, "ProductCode")
        ProductCode.text = f"{dme_account_num}{bok_2.e_item_type}"

        QuantityOrdered = ET.SubElement(Detail, "QuantityOrdered")
        QuantityOrdered.text = str(bok_2.l_002_qty)

    # ET.dump(_xml)  # Only used for debugging
    result = ET.tostring(_xml)
    return result


def parse_xml(is_success_xml, xml_str):
    xml_str = xml_str.decode("utf-8")
    root = ET.fromstring(xml_str)
    Body_ns = "{http://schemas.xmlsoap.org/soap/envelope/}Body"
    Body = root.find(Body_ns)
    json_res = {}

    if is_success_xml:
        if settings.ENV == "prod":
            SalesOrderToWMSAck_ns = "{http://www.paperless-warehousing.com/ACR/SalesOrderToWMS}SalesOrderToWMSAck"
        else:
            SalesOrderToWMSAck_ns = "{http://www.paperless-warehousing.com/TEST/SalesOrderToWMS}SalesOrderToWMSAck"

        SalesOrderToWMSAck = Body.find(SalesOrderToWMSAck_ns)

        if SalesOrderToWMSAck:
            json_res["DocNbr"] = SalesOrderToWMSAck.find("DocNbr").text
            json_res["WhsCode"] = SalesOrderToWMSAck.find("WhsCode").text
            json_res["Version"] = SalesOrderToWMSAck.find("Version").text
            json_res["DateRcvd"] = SalesOrderToWMSAck.find("DateRcvd").text
            json_res["TimeRcvd"] = SalesOrderToWMSAck.find("TimeRcvd").text
            json_res["MessageType"] = SalesOrderToWMSAck.find("MessageType").text
            json_res["MessageStatus"] = SalesOrderToWMSAck.find("MessageStatus").text

            if json_res["MessageStatus"] != "OK":
                ErrorDetails = SalesOrderToWMSAck.find("ErrorDetails")
                json_res["ErrorDetails"] = {
                    "Type": ErrorDetails.find("Type").text,
                    "Description": ErrorDetails.find("Description").text,
                    "Code": ErrorDetails.find("Code").text,
                    "Area": ErrorDetails.find("Area").text,
                    "Source": ErrorDetails.find("Source").text,
                    "User": ErrorDetails.find("User").text,
                }
    else:
        Fault_ns = "{http://schemas.xmlsoap.org/soap/envelope/}Fault"
        Fault = Body.find(Fault_ns)
        json_res["faultcode"] = Fault.find("faultcode").text
        json_res["faultstring"] = Fault.find("faultcode").text
        json_res["detail"] = Fault.find("detail/WSDL_VALIDATION_FAILED").text

    return json_res


def _check_port_code(bok_1):
    logger.info("[PAPERLESS] Checking port_code...")
    de_suburb = bok_1.b_032_b_pu_address_suburb
    de_postcode = bok_1.b_033_b_pu_address_postalcode
    de_state = bok_1.b_031_b_pu_address_state

    # head_port and port_code
    fp_routings = FPRouting.objects.filter(
        freight_provider=13,
        dest_suburb__iexact=de_suburb,
        dest_postcode=de_postcode,
        dest_state__iexact=de_state,
    )
    head_port = fp_routings[0].gateway if fp_routings and fp_routings[0].gateway else ""
    port_code = fp_routings[0].onfwd if fp_routings and fp_routings[0].onfwd else ""

    if not head_port or not port_code:
        message = f"No port_code.\n\n"
        message += f"Order Num: {bok_1.b_client_order_num}\n"
        message += f"State: {de_state}\nPostal Code: {de_postcode}\nSuburb: {de_suburb}"
        logger.error(f"[PAPERLESS] {message}")
        send_email_to_admins("Failed to send order to ACR due to port_code", message)
        raise Exception(message)

    logger.info("[PAPERLESS] `port_code` is fine")


def send_order_info(bok_1):
    LOG_ID = "[PAPERLESS]"

    if settings.ENV == "local":
        logger.info(
            f"{LOG_ID} 'Send Order to ACR' is skipped on LOCAL - {bok_1.b_client_order_num}"
        )
        return True

    # Turn on/off this feature - `send order to ACR`
    # if settings.ENV == "prod":
    #     logger.info(
    #         f"{LOG_ID} 'Send Order to ACR' is temporaily disabled - {bok_1.b_client_order_num}"
    #     )
    #     return True

    _check_port_code(bok_1)

    try:
        headers = {
            "content-type": "text/xml",
            "soapaction": "http://www.paperless-warehousing.com/ACR/SalesOrderToWMS",
        }

        if settings.ENV == "prod":
            port = "32380"
        else:
            port = "33380"

        url = f"http://automation.acrsupplypartners.com.au:{port}/SalesOrderToWMS"
        bok_2s = BOK_2_lines.objects.filter(
            fk_header_id=bok_1.pk_header_id, b_093_packed_status=BOK_2_lines.ORIGINAL
        )
        log = Log(fk_booking_id=bok_1.pk_header_id, request_type="PAPERLESS_ORDER")
        log.save()

        try:
            # logger.info(f"@9000 {LOG_ID} url - {url}")
            body = build_xml_with_bok(bok_1, bok_2s)
            logger.info(f"@9000 {LOG_ID} payload body - {body}")
        except Exception as e:
            error = f"@901 {LOG_ID} error on payload builder.\n\nError: {str(e)}\nBok_1: {str(bok_1.pk)}\nOrder Number: {bok_1.b_client_order_num}"
            logger.error(error)
            raise Exception(error)

        log.request_payload = body.decode("utf-8")
        log.save()
        response = send_soap_request(url, body, headers)
        logger.info(
            f"@9001 - {LOG_ID} response status_code: {response.status_code}, content: {response.content}"
        )
        log.request_status = response.status_code
        log.response = response.content.decode("utf-8")
        log.save()

        try:
            json_res = parse_xml(response.status_code == 200, response.content)
        except Exception as e:
            error = f"@902 {LOG_ID} error on parseing response.\n\nError: {str(e)}\nBok_1: {str(bok_1.pk)}\nOrderNum: {bok_1.b_client_order_num}\n\n"
            error += f"Request info:\n    url: {url}\n    headers: {json.dumps(headers, indent=4)}\n    body: {body}\n\n"
            error += f"Response info:\n    status_code: {response.status_code}\n    content: {response.content}"
            logger.error(error)
            raise Exception(error)

        if response.status_code > 400 or "ErrorDetails" in json_res:
            error = f"@903 {LOG_ID} response error.\n\nBok_1: {str(bok_1.pk)}\n\n"
            error += f"Request info:\n    url: {url}\n    headers: {json.dumps(headers, indent=4)}\n    body: {body}\n\n"
            error += f"Response info:\n    status_code: {response.status_code}\n    content: {response.content}\n\n"
            error += f"Parsed json: {json.dumps(json_res, indent=4)}"
            logger.error(error)
            raise Exception(error)

        log.response = json.dumps(json_res, indent=4)
        log.save()
        logger.info(f"@9009 - {LOG_ID}\nresult: {json.dumps(json_res, indent=4)}")
        return json_res
    except Exception as e:
        if bok_1.b_client_order_num:
            to_emails = [settings.ADMIN_EMAIL_02]
            subject = "Error on Paperless workflow"

            if settings.ENV == "prod":
                to_emails.append(settings.SUPPORT_CENTER_EMAIL)
                # to_emails.append("randerson@plumproducts.com")  # Plum agent
                # to_emails.append("aussales@plumproducts.com")  # Plum agent

            send_email(
                send_to=to_emails,
                send_cc=[],
                send_bcc=["goldj@deliver-me.com.au"],
                subject=subject,
                text=str(e),
            )
            logger.error(f"@905 {LOG_ID} Sent email notification!")

        return None
