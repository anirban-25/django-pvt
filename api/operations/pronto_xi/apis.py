import logging
import xml.etree.ElementTree as ET

from django.conf import settings

from api.models import BOK_1_headers, BOK_2_lines, Log, DME_clients
from api.outputs.soap import send_soap_request
from api.outputs.email import send_email
from api.fp_apis.operations.surcharge.index import get_surcharges_total
from api.clients.jason_l.constants import (
    ITEM_CODES_TO_BE_IGNORED as JASONL_ITEM_CODES_TO_BE_IGNORED,
)
from api.clients.jason_l.operations import get_address as jasonl_get_address

logger = logging.getLogger(__name__)
IS_TESTING = False

# Constants
PORT = "8443"
USERNAME = "delme"
PASSWORD = "Dme1234!$*"
CUSTOMER_CODE = "3QD3D5X"

if settings.ENV in ["local", "dev"]:
    API_URL = f"https://jasonl-bi.prontohosted.com.au:{PORT}/pronto/rest/U01_avenue"
else:
    API_URL = f"https://jasonl-bi.prontohosted.com.au:{PORT}/pronto/rest/L01_avenue"


def parse_token_xml(response):
    xml_str = response.content.decode("utf-8")
    root = ET.fromstring(xml_str)
    token_ns = "token"

    return {"token": root.find(token_ns).text}


def get_token():
    logger.info("@630 [PRONTO TOKEN] Start")
    url = f"{API_URL}/login"
    headers = {
        "X-Pronto-Username": USERNAME,
        "X-Pronto-Password": PASSWORD,
    }

    response = send_soap_request(url, "", headers)
    # logger.info(
    #     f"@631 [PRONTO TOKEN] response status_code: {response.status_code}, content: {response.content}"
    # )

    if response.status_code != 200:
        logger.error(f"@632 [PRONTO TOKEN] Failed")
        return False

    token = parse_token_xml(response)["token"]
    logger.info(f"@631 [PRONTO TOKEN] Finish - {token}")
    return token


def parse_product_group_code(response):
    xml_str = response.content.decode("utf-8")
    # xml_str = '<?xml version="1.0" encoding="UTF-8"?><InvGetItemsResponse xmlns="http://www.pronto.net/inv/1.0.0"><APIResponseStatus><Code>OK</Code></APIResponseStatus><Items><Item><GroupCode>FR01</GroupCode><ItemCode>S068</ItemCode><ItemDescription>JL Shipping</ItemDescription><UOMCode>EACH</UOMCode></Item></Items></InvGetItemsResponse>'
    root = ET.fromstring(xml_str)
    Items = root.find("{http://www.pronto.net/inv/1.0.0}Items")

    if not len(Items):
        return ""

    Item = Items[0]
    GroupCode = Item.find("{http://www.pronto.net/inv/1.0.0}GroupCode").text

    return GroupCode


def get_product_group_code(ItemCode, token=None):
    logger.info(f"@640 [PRONTO GET ITEM INFO] Start! ItemCode: {ItemCode}")

    if not token:
        token = get_token()

    url = f"{API_URL}/api/InvGetItems"
    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "X-Pronto-Token": token,
    }
    body = f'<InvGetItemsRequest \
                xmlns="http://www.pronto.net/inv/1.0.0"> \
                <Parameters> \
                    <ItemCode>{ItemCode}</ItemCode> \
                </Parameters> \
                <OrderBy /> \
                <RequestFields> \
                    <Items> \
                        <Item> \
                            <GroupCode /> \
                            <ItemCode /> \
                            <ItemDescription /> \
                            <UOMCode /> \
                        </Item> \
                    </Items> \
                </RequestFields> \
            </InvGetItemsRequest>'

    response = send_soap_request(url, body, headers)
    logger.info(
        f"@631 [PRONTO GET ITEM INFO] response status_code: {response.status_code}, content: {response.content}"
    )

    if response.status_code != 200:
        logger.error(f"@632 [PRONTO GET ITEM INFO] Failed")
        return False

    GroupCode = parse_product_group_code(response)
    logger.info(
        f"@649 [PRONTO GET ITEM INFO] Finished! ItemCode: {ItemCode}, GroupCode: {GroupCode}"
    )

    return GroupCode


def parse_order_xml(response, order_num, token):
    LOG_ID = "[PRONTO PARSE ORDER XML]"

    # Test Usage #
    if IS_TESTING:
        xml_str = '<?xml version="1.0" encoding="UTF-8"?>\n<SalesOrderGetSalesOrdersResponse xmlns="http://www.pronto.net/so/1.0.0"><APIResponseStatus><Code>OK</Code></APIResponseStatus><SalesOrders><SalesOrder><Address1>Level 9</Address1><Address2>16 O Connel St</Address2><Address3></Address3><Address4>Sydney</Address4><Address5>NSW</Address5><Address6></Address6><AddressName>2 Discover Recruitment Pty Ltd</AddressName><AddressPostcode>2000</AddressPostcode><CustomerEmail>jodyc@2discover.com.au</CustomerEmail><DeliveryDate>2021-06-22</DeliveryDate><Packages>35</Packages><SOOrderNo>1034326</SOOrderNo><SalesOrderLines><SalesOrderLine><ItemCode>8931</ItemCode><OrderedQty>2.0000</OrderedQty><ProductGroupCode></ProductGroupCode><SequenceNo>7.00</SequenceNo><TypeCode>SN</TypeCode><UOMCode>PAIR</UOMCode></SalesOrderLine><SalesOrderLine><ItemCode>8963</ItemCode><OrderedQty>8.0000</OrderedQty><ProductGroupCode></ProductGroupCode><SequenceNo>8.00</SequenceNo><TypeCode>SN</TypeCode><UOMCode>EACH</UOMCode></SalesOrderLine><SalesOrderLine><ItemCode>8934</ItemCode><OrderedQty>16.0000</OrderedQty><ProductGroupCode></ProductGroupCode><SequenceNo>9.00</SequenceNo><TypeCode>SN</TypeCode><UOMCode>EACH</UOMCode></SalesOrderLine><SalesOrderLine><ItemCode>HC124M</ItemCode><OrderedQty>8.0000</OrderedQty><ProductGroupCode></ProductGroupCode><SequenceNo>10.00</SequenceNo><TypeCode>SN</TypeCode><UOMCode>EACH</UOMCode></SalesOrderLine><SalesOrderLine><ItemCode>S068</ItemCode><OrderedQty>1.0000</OrderedQty><ProductGroupCode></ProductGroupCode><SequenceNo>11.00</SequenceNo><TypeCode>SN</TypeCode><UOMCode>EACH</UOMCode></SalesOrderLine><SalesOrderLine><ItemCode>AAA001</ItemCode><OrderedQty>5.0000</OrderedQty><ProductGroupCode></ProductGroupCode><SequenceNo>12.00</SequenceNo><TypeCode>SN</TypeCode><UOMCode>EACH</UOMCode></SalesOrderLine></SalesOrderLines><WarehouseCode>BOT</WarehouseCode></SalesOrder></SalesOrders></SalesOrderGetSalesOrdersResponse>\n'
    else:
        xml_str = response.content.decode("utf-8")
    ##############

    root = ET.fromstring(xml_str)
    SalesOrders = root.find("{http://www.pronto.net/so/1.0.0}SalesOrders")

    if not len(SalesOrders):
        return {}

    SalesOrder = SalesOrders[0]
    # order_num = SalesOrder.find("{http://www.pronto.net/so/1.0.0}SOOrderNo").text

    # Test Usage #
    if IS_TESTING:
        address = {
            "error": "Postal Code and Suburb mismatch",
            "phone": "0490001222",
            "email": "aaa@email.com",
            "street_1": "690 Ann Street",
            "suburb": "DEE WHY",
            "state": "NSW",
            "postal_code": "2099",
        }
    else:
        # get address by using `Talend` .sh script
        address = jasonl_get_address(order_num)
    ##############

    b_021 = SalesOrder.find("{http://www.pronto.net/so/1.0.0}DeliveryDate").text
    b_055 = address["street_1"]
    b_056 = address["street_2"]
    b_057 = address["state"]
    b_058 = address["suburb"]
    b_059 = address["postal_code"] or " "
    b_060 = "Australia"
    b_061 = SalesOrder.find("{http://www.pronto.net/so/1.0.0}AddressName").text
    b_063 = address["email"]
    b_064 = address["phone"]
    b_066 = "Phone"  # Not provided
    b_067 = 0  # Not provided
    b_068 = "Drop at Door / Warehouse Dock"  # Not provided
    b_069 = 1  # Not provided
    b_070 = "Escalator"  # Not provided
    b_071 = 1  # Not provided
    warehouse_code = SalesOrder.find(
        "{http://www.pronto.net/so/1.0.0}WarehouseCode"
    ).text

    order = {
        "b_client_order_num": order_num,
        "b_021_b_pu_avail_from_date": b_021,
        "b_055_b_del_address_street_1": b_055,
        "b_056_b_del_address_street_2": b_056,
        "b_057_b_del_address_state": b_057,
        "b_058_b_del_address_suburb": b_058,
        "b_059_b_del_address_postalcode": b_059,
        "b_060_b_del_address_country": b_060,
        "b_061_b_del_contact_full_name": b_061,
        "b_063_b_del_email": b_063,
        "b_064_b_del_phone_main": b_064,
        "b_066_b_del_communicate_via": b_066,
        "b_067_assembly_required": b_067,
        "b_068_b_del_location": b_068,
        "b_069_b_del_floor_number": b_069,
        "b_070_b_del_floor_access_by": b_070,
        "b_071_b_del_sufficient_space": b_071,
        "warehouse_code": warehouse_code,
        "zb_105_text_5": address["error"],
    }

    lines = []
    SalesOrderLines = SalesOrder.find("{http://www.pronto.net/so/1.0.0}SalesOrderLines")
    ignored_items = []

    for SalesOrderLine in SalesOrderLines:
        ItemCode = SalesOrderLine.find("{http://www.pronto.net/so/1.0.0}ItemCode").text
        OrderedQty = SalesOrderLine.find("{http://www.pronto.net/so/1.0.0}OrderedQty")
        SequenceNo = SalesOrderLine.find("{http://www.pronto.net/so/1.0.0}SequenceNo")
        UOMCode = SalesOrderLine.find("{http://www.pronto.net/so/1.0.0}UOMCode")

        if ItemCode and ItemCode.upper() in JASONL_ITEM_CODES_TO_BE_IGNORED:
            ignored_items.append(ItemCode)
            message = f"@6410 {LOG_ID} IGNORED (LISTED ITEM) --- itemCode: {ItemCode}"
            logger.info(message)
            continue

        ProductGroupCode = get_product_group_code(ItemCode, token)
        if not ProductGroupCode:
            ignored_items.append(ItemCode)
            message = f"@6410 {LOG_ID} IGNORED (MISSING ITEM) --- itemCode: {ItemCode}"
            logger.info(message)
            # continue

        line = {
            "model_number": ItemCode,
            "qty": int(float(OrderedQty.text)),
            "sequence": int(float(SequenceNo.text)),
            "UOMCode": UOMCode.text,
            "ProductGroupCode": ProductGroupCode,
        }
        lines.append(line)

    if ignored_items:
        order["b_010_b_notes"] = ", ".join(ignored_items)

    return order, lines


def get_order(order_num):
    logger.info(f"@640 [PRONTO GET ORDER] Start! Order: {order_num}")

    # - Split `order_num` and `suffix` -
    _order_num, suffix = order_num, ""
    iters = _order_num.split("-")

    if len(iters) > 1:
        _order_num, suffix = iters[0], iters[1]

    message = f"@641 [PRONTO GET ORDER] OrderNum: {_order_num}, Suffix: {suffix}"
    logger.info(message)
    # ---

    token = get_token()

    # Test usage #
    if IS_TESTING:
        order, lines = parse_order_xml(None, token)
        return order, lines
    ##############

    url = f"{API_URL}/api/SalesOrderGetSalesOrders"
    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "X-Pronto-Token": token,
    }
    body = f'<?xml version="1.0" encoding="UTF-8" standalone="no"?> \
                <SalesOrderGetSalesOrdersRequest> \
                    <Parameters> \
                        <SOOrderNo>{_order_num}</SOOrderNo> \
                        <SOBOSuffix>{suffix}</SOBOSuffix> \
                    </Parameters> \
                    <RequestFields> \
                        <SalesOrders> \
                            <SalesOrder> \
                                <SOOrderNo/> \
                                <AddressName/> \
                                <DeliveryDate/> \
                                <Packages/> \
                                <WarehouseCode/> \
                                <CustomerEmail /> \
                                <Address1/> \
                                <Address2/> \
                                <Address3/> \
                                <Address4/> \
                                <Address5/> \
                                <Address6/> \
                                <AddressPostcode/> \
                                <SalesOrderLines> \
                                    <RequestFields> \
                                        <SalesOrderLines> \
                                            <SalesOrderLine> \
                                                <ItemCode /> \
                                                <OrderedQty /> \
                                                <SequenceNo /> \
                                                <UOMCode /> \
                                                <TypeCode /> \
                                                <ProductGroupCode /> \
                                            </SalesOrderLine> \
                                        </SalesOrderLines> \
                                    </RequestFields> \
                                </SalesOrderLines> \
                            </SalesOrder> \
                        </SalesOrders> \
                    </RequestFields> \
                </SalesOrderGetSalesOrdersRequest>'

    response = send_soap_request(url, body, headers)
    logger.info(
        f"@631 [PRONTO GET ORDER] response status_code: {response.status_code}, content: {response.content}"
    )

    if response.status_code != 200:
        logger.error(f"@632 [PRONTO GET ORDER] Failed")
        return None, None

    order, lines = parse_order_xml(response, order_num, token)
    logger.info(f"@649 [PRONTO GET ORDER] Finish \norder: {order}\nlines: {lines}")

    return order, lines


def send_info_back_to_pronto(bok_1, quote):
    LOG_ID = "[PRONTO SEND ORDER BACK]"

    if not bok_1.b_091_send_quote_to_pronto:
        logger.info(
            f"@650 {LOG_ID} Flag is OFF! Do not need to send. bok_1 ID: {bok_1.pk}"
        )
        return True

    logger.info(f"@650 {LOG_ID} Start! bok_1 ID: {bok_1.pk}")

    # Query data
    client = DME_clients.objects.get(dme_account_num=bok_1.fk_client_id)
    bok_2s = BOK_2_lines.objects.filter(
        fk_header_id=bok_1.pk_header_id, is_deleted=False
    )
    service_bok_2s = BOK_2_lines.objects.filter(
        fk_header_id=bok_1.pk_header_id, is_deleted=True, zbl_102_text_2="FR01"
    )

    if not service_bok_2s:
        logger.info(f"@651 {LOG_ID} No service(FR01) bok_2 found")
        return None

    bok_2 = service_bok_2s.first()

    # Calc `ordered_qty` & `item_price`
    client = DME_clients.objects.get(dme_account_num=bok_1.fk_client_id)
    tax_value_1 = bok_1.quote.tax_value_1 or 0
    ordered_qty = 1
    surcharge_total = get_surcharges_total(bok_1.quote)
    item_price = "{0:.2f}".format(
        (bok_1.quote.client_mu_1_minimum_values + surcharge_total)
        * (client.client_customer_mark_up + 1)
    )

    logger.info(
        f"@652 {LOG_ID} Info to back - ordered_qty: {ordered_qty}, item_price: {item_price}"
    )

    # Get token
    token = get_token()

    # Update LineQty
    url = f"{API_URL}/api/SalesOrderPostLineQtyOverride"
    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "X-Pronto-Token": token,
    }
    body = f'<SalesOrderPostLineQtyOverrideRequest xmlns="http://www.pronto.net/so/1.0.0"> \
                <SalesOrderLines> \
                    <SalesOrderLine SOOrderNo="{bok_1.b_client_order_num}" SOBOSuffix=" " SequenceNo="{bok_2.zbl_131_decimal_1}"> \
                        <OrderedQty>1</OrderedQty> \
                    </SalesOrderLine> \
                </SalesOrderLines> \
            </SalesOrderPostLineQtyOverrideRequest>'

    response = send_soap_request(url, body, headers)
    logger.info(
        f"@653 {LOG_ID} SalesOrderPostLineQtyOverride response status_code: {response.status_code}"
    )

    if response.status_code != 200:
        logger.info(
            f"@654 {LOG_ID} SalesOrderPostLinePriceOverride response content: {response.content}"
        )

    # Update LinePrice
    url = f"{API_URL}/api/SalesOrderPostLinePriceOverride"
    body = f'<SalesOrderPostLinePriceOverrideRequest xmlns="http://www.pronto.net/so/1.0.0"> \
                <SalesOrderLines> \
                    <SalesOrderLine SOOrderNo="{bok_1.b_client_order_num}" SOBOSuffix=" " SequenceNo="{bok_2.zbl_131_decimal_1}"> \
                        <ItemPrice>{item_price}</ItemPrice> \
                        <PriceOverrideFlag>Y</PriceOverrideFlag> \
                        <PriceRule>D</PriceRule> \
                    </SalesOrderLine> \
                </SalesOrderLines> \
            </SalesOrderPostLinePriceOverrideRequest>'

    response = send_soap_request(url, body, headers)
    logger.info(
        f"@655 {LOG_ID} SalesOrderPostLinePriceOverride response status_code: {response.status_code}"
    )

    if response.status_code != 200:
        logger.info(
            f"@656 {LOG_ID} SalesOrderPostLinePriceOverride response content: {response.content}"
        )

    logger.info(f"@659 {LOG_ID} Finish! bok_1 ID: {bok_1.pk}")
    return True


def update_pronto_note(order_num, note):
    LOG_ID = "[PRONTO UPDATE NOTE]"
    logger.info(f"@660 {LOG_ID} Start! OrderNum: {order_num}, Note: {note}")

    # - Split `order_num` and `suffix` -
    _order_num, suffix = order_num, ""
    iters = _order_num.split("-")

    if len(iters) > 1:
        _order_num, suffix = iters[0], iters[1]
        message = f"@6400 [PRONTO UPDATE NOTE] OrderNum: {_order_num}, Suffix: {suffix}"
        logger.info(message)
    # ---

    token = get_token()

    if not token:
        message = f"@6401 [PRONTO UPDATE NOTE] Failed to get token"
        return

    url = f"{API_URL}/api/SalesOrderPostOrderNotes"
    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "X-Pronto-Token": token,
    }
    body = f'<SalesOrderPostOrderNotesRequest xmlns="http://www.pronto.net/so/1.0.0"> \
                <SalesOrders> \
                    <SalesOrder SOOrderNo="{_order_num}" SOBOSuffix="{suffix}"> \
                        <Notes>{note}</Notes> \
                    </SalesOrder> \
                </SalesOrders> \
            </SalesOrderPostOrderNotesRequest>'

    # logger.info(f"@661 {LOG_ID} request body: {body}")
    response = send_soap_request(url, body, headers)
    logger.info(
        f"@662 {LOG_ID} response status_code: {response.status_code}, content: {response.content}"
    )

    logger.info(f"@669 {LOG_ID} Finish! OrderNum: {order_num}")
    return True
