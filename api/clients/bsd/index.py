import uuid
import logging
from datetime import datetime, date, timedelta
from woocommerce import API

from django.db import transaction

from api.models import Client_warehouses, BOK_2_lines, Booking_lines, Bookings
from api.serializers import SimpleQuoteSerializer
from api.serializers_client import *
from api.common import time as dme_time_lib, constants as dme_constants
from api.operations import product_operations as product_oper
from api.operations.booking_line import index as line_oper
from api.clients.operations.index import get_suburb_state
from api.common.time import next_business_day
from api.clients.bsd.constants import *

logger = logging.getLogger(__name__)


def push_boks(payload, client, username, method):
    """
    PUSH api (bok_1, bok_2, bok_3)
    """
    LOG_ID = "[PB Standard]"  # PB - PUSH BOKS
    bok_1 = payload["booking"]
    bok_1["pk_header_id"] = str(uuid.uuid4())
    bok_2s = payload["booking_lines"]

    with transaction.atomic():
        # Save bok_1
        bok_1["fk_client_id"] = client.dme_account_num
        bok_1["x_booking_Created_With"] = "DME PUSH API"
        bok_1["success"] = dme_constants.BOK_SUCCESS_5

        # PU avail from
        bok_1["b_021_b_pu_avail_from_date"] = None
        bok_1["b_022_b_pu_avail_from_time_hour"] = 0
        bok_1["b_023_b_pu_avail_from_time_minute"] = 0
        # if not bok_1.get("b_021_b_pu_avail_from_date"):
        #     now_time = datetime.now()
        #     start_date = (
        #         now_time - timedelta(days=1) if now_time.time().hour < 12 else now_time
        #     )
        #     bok_1["b_021_b_pu_avail_from_date"] = next_business_day(start_date, 3)

        # Warehouse
        bok_1["client_booking_id"] = bok_1["pk_header_id"]
        bok_1["fk_client_warehouse"] = 220
        bok_1["b_clientPU_Warehouse"] = "Bathroom Sales Direct"
        bok_1["b_client_warehouse_code"] = "BSD_MERRYLANDS"
        bok_1["booking_Created_For_Email"] = "info@bathroomsalesdirect.com.au"

        if not bok_1.get("b_054_b_del_company"):
            bok_1["b_054_b_del_company"] = bok_1["b_061_b_del_contact_full_name"]

        bok_1["b_057_b_del_address_state"] = bok_1["b_057_b_del_address_state"].upper()
        bok_1["b_031_b_pu_address_state"] = bok_1["b_031_b_pu_address_state"].upper()
        bok_1["b_027_b_pu_address_type"] = "business"
        bok_1["b_053_b_del_address_type"] = "residential"

        # Shipping Method (local_pickup, ...)
        b_010_b_notes = bok_1["shipping_method"]
        if bok_1["shipping_method"] == "local_pickup":
            bok_1["b_001_b_freight_provider"] = "Customer Collect"
        elif bok_1["shipping_method"] == "free_shipping":
            bok_1["b_093_b_promo_code"] = "Flash Sale Bulk"

        bok_1_serializer = BOK_1_Serializer(data=bok_1)
        if not bok_1_serializer.is_valid():
            message = f"Serialiser Error - {bok_1_serializer.errors}"
            logger.info(f"@8811 {LOG_ID} {message}")
            raise Exception(message)

        # Save bok_2s
        for index, bok_2 in enumerate(bok_2s):
            _bok_2 = bok_2["booking_line"]
            _bok_2["fk_header_id"] = bok_1["pk_header_id"]
            _bok_2["v_client_pk_consigment_num"] = bok_1["pk_header_id"]
            _bok_2["pk_booking_lines_id"] = str(uuid.uuid1())
            _bok_2["success"] = bok_1["success"]
            _bok_2["is_deleted"] = 0
            _bok_2["b_093_packed_status"] = BOK_2_lines.ORIGINAL
            l_001 = _bok_2.get("l_001_type_of_packaging") or "Carton"
            _bok_2["l_001_type_of_packaging"] = l_001

            _bok_2 = line_oper.handle_zero(_bok_2)
            bok_2_serializer = BOK_2_Serializer(data=_bok_2)
            if bok_2_serializer.is_valid():
                bok_2_serializer.save()
            else:
                message = f"Serialiser Error - {bok_2_serializer.errors}"
                logger.info(f"@8821 {LOG_ID} {message}")
                raise Exception(message)

            # Save bok_3s
            if not "booking_lines_data" in bok_2:
                continue

            bok_3s = bok_2["booking_lines_data"]
            for bok_3 in bok_3s:
                bok_3["fk_header_id"] = bok_1["pk_header_id"]
                bok_3["fk_booking_lines_id"] = _bok_2["pk_booking_lines_id"]
                bok_3["v_client_pk_consigment_num"] = bok_1["pk_header_id"]
                bok_3["success"] = bok_1["success"]

                bok_3_serializer = BOK_3_Serializer(data=bok_3)
                if bok_3_serializer.is_valid():
                    bok_3_serializer.save()
                else:
                    message = f"Serialiser Error - {bok_3_serializer.errors}"
                    logger.info(f"@8831 {LOG_ID} {message}")
                    raise Exception(message)

        bok_1_obj = bok_1_serializer.save()

    res_json = {"success": True, "message": "Push success!"}
    return res_json


def get_order_from_woocommerce(wcapi, order_num):
    LOG_ID = "[WC Order]"
    logger.info(f"params - OrderId: {order_num}")

    try:
        url = f"orders/{order_num}"
        logger.info(f"url - {url}")
        order = wcapi.get(url).json()
        return order
    except Exception as e:
        logger.info(f"Get orders error: {e}")
        return []


def get_product_from_woocommerce(wcapi, product_id):
    LOG_ID = "[WC Product]"
    try:
        product = wcapi.get(f"products/{product_id}").json()
        return product
    except Exception as e:
        logger.info(f"Get product error: {e}")
        return None


def fetch_order(order_num):
    LOG_ID = "[Fetch Order]"

    # Try to find existing order
    bookings = Bookings.objects.filter(
        kf_client_id="9e72da0f-77c3-4355-a5ce-70611ffd0bc8",
        b_client_order_num=order_num,
    ).only("id", "b_bookingID_Visual", "b_client_order_num")

    if bookings:
        logger.info(
            f"{LOG_ID} Already exist! BookingId: {bookings.last().b_bookingID_Visual}, Order Number: {order_num}"
        )
        message = (
            f"Order already exist! Booking Id: {bookings.last().b_bookingID_Visual}"
        )
        raise Exception(message)

    # Initiate WC api
    wcapi = API(
        url=WC_URL,  # Your store URL
        consumer_key=WC_CONSUMER_KEY,  # Your consumer key
        consumer_secret=WC_CONSUMER_SECRET,  # Your consumer secret
        wp_api=True,  # Enable the WP REST API integration
        version=WC_VERSION,  # WooCommerce WP REST API version
        query_string_auth=True,
    )
    order = get_order_from_woocommerce(wcapi, order_num)

    if not "id" in order:
        logger.info(
            f"{LOG_ID} Failed to get order! Order Number: {order_num}, Message: {order['message']}"
        )
        raise Exception(order["message"])

    # Save on Bookings
    pk_booking_id = str(uuid.uuid4())
    booking_lines = []
    for line in order["line_items"]:
        logger.info(f"{LOG_ID} productId: {line['product_id']}")
        product = get_product_from_woocommerce(wcapi, line["product_id"])

        if not product:
            logger.info(f"{LOG_ID} Not Found! productId: {line['product_id']}")
            continue

        e_dimLength = float(product["dimensions"]["length"])
        e_dimWidth = float(product["dimensions"]["width"])
        e_dimHeight = float(product["dimensions"]["height"])
        total_cubic_meter = int(line["quantity"]) * (
            e_dimLength * e_dimWidth * e_dimHeight / 1000000
        )
        total_cubic_mass = total_cubic_meter * 250
        total_weight = float(product["weight"]) * int(line["quantity"])
        Booking_lines.objects.create(
            fk_booking_id=pk_booking_id,
            e_weightUOM="kg",
            e_weightPerEach=product["weight"],
            e_1_Total_dimCubicMeter=round(total_cubic_meter, 3),
            total_2_cubic_mass_factor_calc=round(total_cubic_mass, 3),
            e_Total_KG_weight=round(total_weight, 3),
            e_item=product["name"],
            e_qty=line["quantity"],
            e_type_of_packaging="Carton",
            e_dimUOM="cm",
            e_dimLength=e_dimLength,
            e_dimWidth=e_dimWidth,
            e_dimHeight=e_dimHeight,
            client_item_reference=line["product_id"],
            pk_booking_lines_id=str(uuid.uuid4()),
            is_deleted=0,
            packed_status="original",
        )

    shipping = order["shipping"]
    billing = order["billing"]
    booking = Bookings.objects.create(
        pk_booking_id=pk_booking_id,
        b_bookingID_Visual=0,
        booking_Created_For="Bathroom Sales Direct",
        booking_Created_For_Email="info@bathroomsalesdirect.com.au",
        x_ReadyStatus="Available From",
        b_booking_tail_lift_pickup=0,
        b_booking_no_operator_pickup=0,
        puPickUpAvailFrom_Date=order["date_modified"][:10],
        pu_PickUp_Avail_Time_Hours=8,
        pu_PickUp_Avail_Time_Minutes=0,
        puCompany="Bathroom Sales Direct",
        pu_Address_Type="business",
        pu_Address_Street_1="81 Warren Road",
        pu_Address_street_2="",
        pu_Address_State="NSW",
        pu_Address_Suburb="Smithfield",
        pu_Address_PostalCode="2164",
        pu_Address_Country="Australia",
        pu_Contact_F_L_Name="Bathroom Sales",
        pu_Email="info@bathroomsalesdirect.com.au",
        pu_Phone_Main="0296816914",
        pu_Comm_Booking_Communicate_Via="Email",
        b_booking_tail_lift_deliver=0,
        b_bookingNoOperatorDeliver=0,
        de_to_Pick_Up_Instructions_Contact="",
        de_to_PickUp_Instructions_Address="",
        # de_Deliver_From_Date=header.b_047_b_del_avail_from_date,
        # de_Deliver_From_Hours=header.b_048_b_del_avail_from_time_hour,
        # de_Deliver_From_Minutes=header.b_049_b_del_avail_from_time_minute,
        # de_Deliver_By_Date=header.b_050_b_del_by_date,
        # de_Deliver_By_Hours=header.b_051_b_del_by_time_hour,
        # de_Deliver_By_Minutes=header.b_052_b_del_by_time_minute,
        de_To_AddressType="business",
        deToCompanyName=f'{shipping["first_name"]} {shipping["last_name"]}',
        de_To_Address_Street_1=shipping["address_1"],
        de_To_Address_Street_2=shipping["address_2"],
        de_To_Address_State=shipping["state"],
        de_To_Address_Suburb=shipping["city"],
        de_To_Address_PostalCode=shipping["postcode"],
        de_To_Address_Country="Australia",
        de_to_Contact_F_LName=f'{shipping["first_name"]} {shipping["last_name"]}',
        de_to_Phone_Main=shipping["phone"] or billing["phone"],
        de_To_Comm_Delivery_Communicate_Via="Email",
        de_Email=billing["email"],
        fk_client_warehouse_id=226,
        b_client_warehouse_code="BSD_SMITHFIELD",
        kf_client_id="9e72da0f-77c3-4355-a5ce-70611ffd0bc8",
        b_status="To Quote",
        b_client_order_num=order_num,
        b_client_name="Bathroom Sales Direct",
        b_error_Capture="",
    )
    booking.b_bookingID_Visual = booking.pk + 15000
    logger.info(
        f"{LOG_ID} {booking.b_bookingID_Visual} is mapped! --- {booking.pk_booking_id}"
    )
    booking.save()

    res_json = {
        "success": True,
        "message": "Push success!",
        "booking_id": booking.b_bookingID_Visual,
        "order_number": order_num,
    }
    return res_json
