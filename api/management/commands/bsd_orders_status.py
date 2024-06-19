import subprocess

from django.core.management.base import BaseCommand
from django.conf import settings

from api.models import Bookings
import sys, time
import os
import uuid
from datetime import datetime, timedelta
import pymysql, pymysql.cursors
import shutil
import json
import requests
import traceback

# from env import DB_HOST, DB_USER, DB_PASS, DB_PORT, DB_NAME, API_URL
# from _options_lib import get_option, set_option
# from _email_lib import send_email

from woocommerce import API

wcapi = API(
    url="https://bathroomsalesdirect.com.au/",  # Your store URL
    consumer_key="ck_b805f1858e763af3f27e5638f80e06f924ac94b1",  # Your consumer key
    consumer_secret="cs_8b52746e7285a2cbaee34046be2e5eadb09884f2",  # Your consumer secret
    wp_api=True,  # Enable the WP REST API integration
    version="wc/v3",  # WooCommerce WP REST API version
    query_string_auth=True,
)


class Command(BaseCommand):
    def handle(self, *args, **options):
        print("----- Get completed BSD orders from Woocommerce -----")
        orderList = get_orders_from_woocommerce(
            datetime.now() - timedelta(days=50), datetime.now(), "completed"
        )
        print("----- Completed BSD order count: %d -----" % len(orderList))
        order_id_list = []
        for order in orderList:
            order_id_list.append(order["id"])

        bookings = (
            Bookings.objects.filter(
                b_client_name="Bathroom Sales Direct",
                b_client_order_num__in=order_id_list,
            )
            .filter(
                b_status__in=[
                    "Parent Booking",
                    "Entered",
                    "Imported / Integrated",
                    "To Quote",
                    "Quoted",
                    "Picking",
                ]
            )
            .only(
                "id",
                "b_status",
                "b_status_category",
                "b_client_order_num",
            )
        )
        bookings.update(
            b_status="Closed",
            b_status_category="Complete",
            b_booking_Notes="Inactive, auto closed",
        )
        print(f"Closed count: {len(bookings)} are closed!")
        print(f"Closed bookings: {bookings}")
        print("---- Finished auto close BSD booking -------")


def get_orders_from_woocommerce(from_date, to_date, status):
    print(f"params - from_date: {from_date}, to_date: {to_date}, status: {status}")

    try:
        order_list = []
        index = 0
        per_page = 40
        while True:
            index += 1
            url = build_req_url(from_date, to_date, status, index, per_page)
            print(f"url - {url}")
            res = wcapi.get(url).json()
            print(f"count - {len(res)}")
            order_list += res
            if len(res) < per_page:
                break

        if (
            "code" in order_list
            and order_list["code"] == "woocommerce_rest_cannot_view"
        ):
            print(f"Message from WooCommerce: {order_list['message']}")
            return []

        return order_list
    except Exception as e:
        print(f"Get orders error: {e}")
        return []


def build_req_url(from_date, to_date, status, index, per_page):
    url = f"orders?"
    url += f"per_page={per_page}"
    url += f"&status={status}"
    url += "&orderby=id"
    url += "&order=desc"
    url += f"&page={index}"

    if from_date:
        url += f"&after={from_date}"

    if to_date:
        url += f"&before={to_date}"
    return url
