import base64
import re
import os
import io
from collections import OrderedDict
import pytz
import json
import uuid
import time as t
import math
import logging
import operator
import requests
import tempfile
import zipfile
import random
from base64 import b64encode
from wsgiref.util import FileWrapper
from datetime import datetime, date, timedelta
from time import gmtime, strftime
from ast import literal_eval
from functools import reduce
from pydash import _
from django_rest_passwordreset.signals import (
    reset_password_token_created,
    post_password_reset,
    pre_password_reset,
)

from django.shortcuts import render
from django.core import serializers, files
from django.http import HttpResponse, JsonResponse, QueryDict
from django.db.models import Q, Case, When, Count, F, Sum
from django.db import connection
from django.utils import timezone
from django.conf import settings
from django.utils.datastructures import MultiValueDictKeyError
from django.core.mail import EmailMultiAlternatives
from django.dispatch import receiver
from django.template.loader import render_to_string
from django.urls import reverse

from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework import viewsets, views, status, authentication, permissions
from rest_framework.permissions import (
    IsAuthenticated,
    AllowAny,
    IsAuthenticatedOrReadOnly,
)
from rest_framework_jwt.authentication import JSONWebTokenAuthentication
from rest_framework.decorators import (
    api_view,
    authentication_classes,
    permission_classes,
    action,
)
from rest_framework.parsers import MultiPartParser
from rest_framework.exceptions import ValidationError
from api.clients.bsd.operations import send_email_booked
from api.fp_apis.operations.surcharge.index import get_surcharges

from api.helpers.string import toAlphaNumeric
from api.serializers import *
from api.models import *
from api.base.viewsets import *
from api.utils import (
    build_pdf,
    build_xls_and_send,
    make_3digit,
    get_sydney_now_time,
    calc_collect_after_status_change,
    tables_in_query,
    get_clientname_with_request,
)
from api.operations.manifests.index import build_manifest
from api.operations.csv.index import build_csv, dme_log_csv
from api.operations.email_senders import send_booking_status_email
from api.clients.ariston_wire.operations import (
    send_email_close_bidding,
    send_email_confirmed,
)
from api.operations.labels.index import build_label as build_label_oper
from api.operations.booking.auto_augment import auto_augment as auto_augment_oper
from api.operations.booking.cancel import cancel_book as cancel_book_oper
from api.fp_apis.utils import (
    get_dme_status_from_fp_status,
    get_status_category_from_status,
    gen_consignment_num,
)
from api.fp_apis.constants import SPECIAL_FPS
from api.fp_apis.operations.tracking import create_fp_status_history
from api.fp_apis.operations.call_truck import call_truck as call_truck_oper
from api.outputs.email import send_email
from api.common import status_history
from api.common.time import (
    UTC_TZ,
    convert_to_UTC_tz,
    convert_to_AU_SYDNEY_tz,
    TIME_DIFFERENCE,
    beautify_eta,
)
from api.common.postal_code import get_postal_codes
from api.common.booking_quote import set_booking_quote
from api.common.constants import (
    BOOKING_FIELDS_4_ALLBOOKING_TABLE,
    ROLLS,
    PACKETS,
    CARTONS,
    PALLETS,
)
from api.common.time import timedelta_2_hours
from api.stats.pricing import analyse_booking_quotes_table
from api.file_operations import (
    uploads as upload_lib,
    delete as delete_lib,
    downloads as download_libs,
)
from api.file_operations.operations import doesFileExist
from api.helpers.cubic import get_cubic_meter
from api.helpers.filter import filter_bookings_by_columns
from api.convertors.pdf import pdf_merge, rotate_pdf, pdf_to_zpl
from api.operations.packing.booking import (
    reset_repack as booking_reset_repack,
    auto_repack as booking_auto_repack,
    manual_repack as booking_manual_repack,
    duplicate_line_linedata,
)
from api.operations.reports.quote import build_quote_report
from api.operations.booking.parent_child import get_run_out_bookings
from api.operations.booking.refs import (
    get_connoteOrReference,
    get_gapRas,
    get_clientRefNumbers,
    get_lines_in_bulk,
    get_surcharges_in_bulk,
    get_status_histories_in_bulk,
)
from api.operations.genesis.index import update_shared_booking
from api.operations.email_senders import send_email_to_admins
from api.fps.index import get_fp_fl
from api.fps.direct_freight import build_book_xml as build_df_book_xml
from email import message_from_string  # For parsing .eml files
from extract_msg import Message
from api.helpers.line import is_carton, is_pallet
from api.convertors import pdf

if settings.ENV == "local":
    S3_URL = "./static"
elif settings.ENV == "dev":
    S3_URL = "/opt/s3_public"
elif settings.ENV == "prod":
    S3_URL = "/opt/s3_public"

logger = logging.getLogger(__name__)


@receiver(reset_password_token_created)
def password_reset_token_created(
    sender, instance, reset_password_token, *args, **kwargs
):
    context = {
        "current_user": reset_password_token.user,
        "username": reset_password_token.user.username,
        "email": reset_password_token.user.email,
        "reset_password_url": f"{settings.WEB_SITE_URL}/reset-password?token="
        + reset_password_token.key,
    }

    try:
        filepath = settings.EMAIL_ROOT + "/user_reset_password.html"
    except MultiValueDictKeyError:
        logger.info("Error #101: Either the file is missing or not readable")

    email_html_message = render_to_string(
        settings.EMAIL_ROOT + "/user_reset_password.html", context
    )

    subject = f"Reset Your Password"
    mime_type = "html"

    try:
        send_email(
            [context["email"]],
            [],
            ["goldj@deliver-me.com.au"],
            subject,
            email_html_message,
            None,
            mime_type,
        )
    except Exception as e:
        logger.info(f"Error #102: {e}")


class UserViewSet(viewsets.ViewSet):
    @action(detail=True, methods=["get"])
    def get(self, request, pk, format=None):
        return_data = []
        try:
            resultObjects = []
            resultObject = User.objects.get(pk=pk)

            return_data.append(
                {
                    "id": resultObject.id,
                    "first_name": resultObject.first_name,
                    "last_name": resultObject.last_name,
                    "username": resultObject.username,
                    "email": resultObject.email,
                    "last_login": resultObject.last_login,
                    "is_staff": resultObject.is_staff,
                    "is_active": resultObject.is_active,
                }
            )
            return JsonResponse({"results": return_data})
        except Exception as e:
            # print("@Exception", e)
            return JsonResponse({"results": ""})

    @action(detail=False, methods=["post"])
    def add(self, request, pk=None):
        return_data = []

        try:
            resultObjects = []
            resultObjects = User.objects.create(
                fk_idEmailParent=request.data["fk_idEmailParent"],
                emailName=request.data["emailName"],
                emailBody=request.data["emailBody"],
                sectionName=request.data["sectionName"],
                emailBodyRepeatEven=request.data["emailBodyRepeatEven"],
                emailBodyRepeatOdd=request.data["emailBodyRepeatOdd"],
                whenAttachmentUnavailable=request.data["whenAttachmentUnavailable"],
            )

            return JsonResponse({"results": resultObjects})
        except Exception as e:
            # print('@Exception', e)
            return JsonResponse({"results": ""})

    @action(detail=True, methods=["put"])
    def edit(self, request, pk, format=None):
        user = User.objects.get(pk=pk)

        try:
            User.objects.filter(pk=pk).update(is_active=request.data["is_active"])
            dme_employee = DME_employees.objects.filter(fk_id_user=user.id).first()
            client_employee = Client_employees.objects.filter(
                fk_id_user=user.id
            ).first()

            if dme_employee is not None:
                dme_employee.status_time = str(datetime.now())
                dme_employee.save()

            if client_employee is not None:
                client_employee.status_time = str(datetime.now())
                client_employee.save()

            return JsonResponse({"results": request.data})
            # if serializer.is_valid():
            # try:
            # serializer.save()
            # return Response(serializer.data)
            # except Exception as e:
            # print('%s (%s)' % (e.message, type(e)))
            # return Response({"results": e.message})
            # return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            # print('Exception: ', e)
            return JsonResponse({"results": str(e)})
            # return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=["delete"])
    def delete(self, request, pk, format=None):
        user = User.objects.get(pk=pk)

        try:
            # user.delete()
            return JsonResponse({"results": fp_freight_providers})
        except Exception as e:
            # print('@Exception', e)
            return JsonResponse({"results": ""})

    @action(detail=False, methods=["post"])
    def username(self, request, format=None):
        user_id = self.request.user.id
        dme_employee = DME_employees.objects.filter(fk_id_user=user_id).first()
        if dme_employee is not None:
            return JsonResponse(
                {
                    "username": request.user.username,
                    "clientname": "dme",
                }
            )
        else:
            client_employee = Client_employees.objects.filter(
                fk_id_user=user_id
            ).first()
            client = DME_clients.objects.get(
                pk_id_dme_client=client_employee.fk_id_dme_client_id
            )
            return JsonResponse(
                {
                    "username": request.user.username,
                    "clientname": client.company_name,
                    "clientId": client.dme_account_num,
                    "clientPK": client.pk_id_dme_client,
                }
            )

    @action(detail=False, methods=["get"])
    def get_clients(self, request, format=None):
        user_id = self.request.user.id
        dme_employee = DME_employees.objects.filter(fk_id_user=user_id).first()

        if dme_employee is not None:
            user_type = "DME"
            dme_clients = DME_clients.objects.all().order_by("company_name")
        else:
            user_type = "CLIENT"
            client_employee = Client_employees.objects.filter(
                fk_id_user=user_id
            ).first()
            client_employee_role = client_employee.get_role()
            dme_clients = DME_clients.objects.filter(
                pk_id_dme_client=int(client_employee.fk_id_dme_client_id)
            ).order_by("company_name")

        if not dme_clients.exists():
            return JsonResponse({"dme_clients": []})
        else:
            return_data = []
            if user_type == "DME":
                return_data = [
                    {
                        "pk_id_dme_client": 0,
                        "company_name": "dme",
                        "dme_account_num": "dme_account_num",
                        "current_freight_provider": "*",
                        "client_filter_date_field": "0",
                        "client_mark_up_percent": "0",
                        "client_min_markup_startingcostvalue": "0",
                        "client_min_markup_value": "0",
                        "augment_pu_by_time": "0",
                        "augment_pu_available_time": "0",
                        "num_client_products": 0,
                    }
                ]

            for client in dme_clients:
                num_client_products = len(
                    Client_Products.objects.filter(
                        fk_id_dme_client=client.pk_id_dme_client
                    )
                )
                return_data.append(
                    {
                        "pk_id_dme_client": client.pk_id_dme_client,
                        "company_name": client.company_name,
                        "dme_account_num": client.dme_account_num,
                        "current_freight_provider": client.current_freight_provider,
                        "client_filter_date_field": client.client_filter_date_field,
                        "client_mark_up_percent": client.client_mark_up_percent,
                        "client_min_markup_startingcostvalue": client.client_min_markup_startingcostvalue,
                        "client_min_markup_value": client.client_min_markup_value,
                        "augment_pu_by_time": client.augment_pu_by_time,
                        "augment_pu_available_time": client.augment_pu_available_time,
                        "num_client_products": num_client_products,
                    }
                )

            return JsonResponse({"dme_clients": return_data})

    @action(detail=False, methods=["get"])
    def get_user_date_filter_field(self, request, pk=None):
        user_id = self.request.user.id
        dme_employee = DME_employees.objects.filter(fk_id_user=user_id).first()

        if dme_employee is not None:
            return JsonResponse({"user_date_filter_field": "z_CreatedTimestamp"})
        else:
            client_employee = Client_employees.objects.filter(
                fk_id_user=user_id
            ).first()
            client = DME_clients.objects.get(
                pk_id_dme_client=client_employee.fk_id_dme_client_id
            )
            return JsonResponse(
                {"user_date_filter_field": client.client_filter_date_field}
            )

    @action(detail=False, methods=["get"])
    def get_all(self, request, pk=None):
        return_data = []
        client_pk = self.request.query_params.get("clientPK", None)

        if client_pk is not None:
            filter_data = Client_employees.objects.filter(
                fk_id_dme_client_id=int(client_pk)
            )

            filter_arr = []
            for data in filter_data:
                filter_arr.append(data.fk_id_user_id)

        try:
            resultObjects = []
            if len(filter_arr) == 0:
                resultObjects = User.objects.all().order_by("username")
            else:
                resultObjects = User.objects.filter(pk__in=filter_arr).order_by(
                    "username"
                )
            for resultObject in resultObjects:
                dme_employee = DME_employees.objects.filter(
                    fk_id_user=resultObject.id
                ).first()
                client_employee = Client_employees.objects.filter(
                    fk_id_user=resultObject.id
                ).first()

                if dme_employee is not None:
                    status_time = dme_employee.status_time

                if client_employee is not None:
                    status_time = client_employee.status_time

                return_data.append(
                    {
                        "id": resultObject.id,
                        "first_name": resultObject.first_name,
                        "last_name": resultObject.last_name,
                        "username": resultObject.username,
                        "email": resultObject.email,
                        "last_login": resultObject.last_login,
                        "is_staff": resultObject.is_staff,
                        "is_active": resultObject.is_active,
                        "status_time": status_time,
                    }
                )
            return JsonResponse({"results": return_data})
        except Exception as e:
            # print('@Exception', e)
            logger.info(f"Error #502: {e}")
            return JsonResponse({"results": ""})

    @action(detail=False, methods=["get"])
    def get_created_for_infos(self, request, pk=None):
        user_id = int(self.request.user.id)
        dme_employee = DME_employees.objects.filter(fk_id_user=user_id)

        if dme_employee:
            client_employees = Client_employees.objects.filter(
                email__isnull=False
            ).order_by("name_first")
            company_name = "dme"
        else:
            client_employee = Client_employees.objects.filter(
                fk_id_user=user_id
            ).first()
            client = DME_clients.objects.filter(
                pk_id_dme_client=int(client_employee.fk_id_dme_client_id)
            ).first()
            client_employees = (
                Client_employees.objects.filter(
                    fk_id_dme_client_id=client.pk_id_dme_client, email__isnull=False
                )
                .prefetch_related("fk_id_dme_client")
                .order_by("name_first")
            )
            company_name = client_employee.fk_id_dme_client.company_name

        results = []
        for client_employee in client_employees:
            result = {
                "id": client_employee.pk_id_client_emp,
                "name_first": client_employee.name_first,
                "name_last": client_employee.name_last,
                "email": client_employee.email,
                "company_name": client_employee.fk_id_dme_client.company_name,
            }
            results.append(result)

        return JsonResponse({"success": True, "results": results})


class BookingsViewSet(viewsets.ViewSet):
    serializer_class = BookingSerializer

    @action(detail=False, methods=["get"])
    def get_bookings(self, request, format=None):
        user_id = int(self.request.user.id)
        dme_employee = DME_employees.objects.filter(fk_id_user=user_id)

        # Initialize values:
        errors_to_correct = 0
        missing_labels = 0
        to_manifest = 0
        to_process = 0
        closed = 0
        unprinted_labels = 0
        client = None
        client_employee_role = None

        if dme_employee.exists():
            user_type = "DME"
        else:
            user_type = "CLIENT"
            client_employee = Client_employees.objects.filter(
                fk_id_user=user_id
            ).first()
            client_employee_role = client_employee.get_role()
            client = DME_clients.objects.filter(
                pk_id_dme_client=int(client_employee.fk_id_dme_client_id)
            ).first()

        start_date = self.request.query_params.get("startDate", None)

        if start_date == "*":
            search_type = "ALL"
        else:
            search_type = "FILTER"
            end_date = self.request.query_params.get("endDate", None)

        if search_type == "FILTER":
            first_date = datetime.strptime(start_date, "%Y-%m-%d")
            last_date = datetime.strptime(end_date, "%Y-%m-%d")
            last_date = last_date.replace(hour=23, minute=59, second=59)

        warehouse_id = self.request.query_params.get("warehouseId", None)
        fp_id = self.request.query_params.get("fpId", None)
        sort_field = self.request.query_params.get("sortField", None)
        column_filters = self.request.query_params.get("columnFilters", None)
        column_filters = json.loads(column_filters or "{}")
        active_tab_index = self.request.query_params.get("activeTabInd", None)
        active_tab_index = json.loads(active_tab_index or "{}")
        simple_search_keyword = self.request.query_params.get(
            "simpleSearchKeyword", None
        )
        download_option = self.request.query_params.get("downloadOption", None)
        client_pk = self.request.query_params.get("clientPK", None)
        page_item_cnt = self.request.query_params.get("pageItemCnt", 10)
        page_ind = self.request.query_params.get("pageInd", 0)
        dme_status = self.request.query_params.get("dmeStatus", None)
        multi_find_field = self.request.query_params.get("multiFindField", None)
        multi_find_values = self.request.query_params.get("multiFindValues", "")
        project_name = self.request.query_params.get("projectName", None)
        booking_ids = self.request.query_params.get("bookingIds", None)

        if multi_find_values:
            multi_find_values = multi_find_values.split(", ")

        if booking_ids:
            booking_ids = booking_ids.split(", ")

        # item_count_per_page = self.request.query_params.get('itemCountPerPage', 10)

        # if user_type == 'CLIENT':
        #     print('@01 - Client filter: ', client.dme_account_num)
        # else:
        #     print('@01 - DME user')

        # if start_date == '*':
        #     print('@02 - Date filter: ', start_date)
        # else:
        #     print('@02 - Date filter: ', start_date, end_date, first_date, last_date)

        # print('@03 - Warehouse ID filter: ', warehouse_id)
        # print('@04 - Sort field: ', sort_field)

        # if user_type == 'CLIENT':
        #     print('@05 - Company name: ', client.company_name)
        # else:
        #     print('@05 - Company name: DME')

        # print('@06 - active_tab_index: ', active_tab_index)
        # print('@07 - Simple search keyword: ', simple_search_keyword)
        # print('@08 - Download Option: ', download_option)
        # print('@09 - Client PK: ', client_pk)
        # print("@010 - MultiFind Field: ", multi_find_field)
        # print("@011 - MultiFind Values: ", multi_find_values)

        # DME & Client filter
        if user_type == "DME":
            queryset = Bookings.objects.all()
        else:
            if client_employee_role == "company":
                queryset = Bookings.objects.filter(kf_client_id=client.dme_account_num)
            elif (
                client_employee_role == "employee"
                and client_employee.name_first == "Teddybed"
            ):
                queryset = Bookings.objects.filter(
                    kf_client_id=client.dme_account_num,
                    b_client_name_sub="Teddybed Australia Pty Ltd",
                )
            elif client_employee_role == "warehouse":
                employee_warehouse_id = client_employee.warehouse_id
                queryset = Bookings.objects.filter(
                    kf_client_id=client.dme_account_num,
                    fk_client_warehouse_id=employee_warehouse_id,
                )

        # active_tab_index filter: 0 -> all
        if active_tab_index == 1:  # Erros to Correct
            queryset = queryset.exclude(b_error_Capture__isnull=True).exclude(
                b_error_Capture__exact=""
            )
        if active_tab_index == 2:  # Missing labels
            queryset = queryset.filter(Q(z_label_url__isnull=True) | Q(z_label_url=""))
        elif active_tab_index == 3:  # To manifest
            # BioPak
            if (
                client
                and client.dme_account_num == "7EAA4B16-484B-3944-902E-BC936BFEF535"
            ):
                queryset = queryset.filter(b_status="Booked")
                queryset = queryset.filter(
                    Q(z_manifest_url__isnull=True) | Q(z_manifest_url="")
                )
                queryset = queryset.filter(
                    Q(vx_fp_order_id__isnull=True) | Q(vx_fp_order_id="")
                )
            else:
                queryset = queryset.filter(
                    b_status__in=["Picked", "Ready for Despatch", "Ready for Booking"]
                )
        elif active_tab_index == 40:  # Booked
            queryset = queryset.filter(
                b_status__in=["Booked", "Futile Pickup", "Pickup Rebooked"]
            )
        elif active_tab_index == 41:  # Cancel Requested
            queryset = queryset.filter(b_status="Cancel Requested")
        elif active_tab_index == 42:  # In Progress
            queryset = queryset.filter(
                b_status__in=[
                    "In Transit",
                    "Partially In Transit",
                    "On-Forwarded",
                    "On Board for delivery",
                    "Futile Delivery",
                    "Partially Delivered",
                    "Delivery Delayed",
                    "Delivery Rebooked",
                ]
            )
        elif active_tab_index == 43:  # On Hold
            queryset = queryset.filter(b_status="On Hold")
        elif active_tab_index == 5:  # Closed
            queryset = queryset.filter(b_status__in=["Closed", "Cancelled"])
        elif active_tab_index == 51:  # Closed with issue
            queryset = queryset.filter(b_status__in=["Lost in Transit", "Damaged"])
        elif active_tab_index == 6:  # 'Delivery Management' - exclude BioPak
            queryset = queryset.exclude(b_client_name="BioPak")
        elif active_tab_index == 8:  # 'Pre-Processing'
            queryset = queryset.filter(
                b_status__in=[
                    "To Quote",
                    "Quoted",
                    "Entered",
                    "Imported / Integrated",
                ]
            )
        elif active_tab_index == 81:  # 'Processing'
            queryset = queryset.filter(b_status="Picking")
        elif active_tab_index == 9:  # 'Unprinted Labels'
            queryset = queryset.filter(
                z_label_url__isnull=False,
                z_downloaded_shipping_label_timestamp__isnull=True,
            )
        elif active_tab_index == 90:  # 'Returning'
            queryset = queryset.filter(b_status="Returning")
        elif active_tab_index == 91:  # 'Returned'
            queryset = queryset.filter(b_status="Returned")
        elif active_tab_index == 10:  # More tab
            queryset = queryset.filter(b_status=dme_status)
        elif active_tab_index == 11:
            queryset = queryset.filter(b_status="Parent Booking")
            run_out_bookings = get_run_out_bookings(queryset)
            queryset = queryset.exclude(pk__in=run_out_bookings)
        elif active_tab_index in [12, 109]:  # Delivered
            queryset = queryset.filter(
                b_status__in=["Delivered", "Collected by Customer"]
            )
        elif active_tab_index == 61:  # Out of Set
            # Find bookings out of a Set
            bookingSets = BookingSets.objects.all()
            booking_ids_in_sets = []
            for _set in bookingSets:
                booking_ids_in_sets += _set.booking_ids.split(", ")
            queryset = queryset.exclude(pk__in=booking_ids_in_sets)
        elif active_tab_index == 100:  # Entered
            _100_statuses = ["Imported / Integrated", "Entered", "To Quote"]
            queryset = queryset.filter(b_status__in=_100_statuses)
        elif active_tab_index == 101:  # Picking
            _101_statuses = ["Picking"]
            queryset = queryset.filter(b_status__in=_101_statuses)
        elif active_tab_index == 102:  # Packed
            _102_statuses = ["Picked"]
            queryset = queryset.filter(b_status__in=_102_statuses)
        elif active_tab_index == 103:  # Booked
            _103_statuses = ["Booked"]
            queryset = queryset.filter(b_status__in=_103_statuses)
        elif active_tab_index == 104:  # Late From Whs
            _104_statuses = [
                "Picking",
                "Picked",
                "Ready for Booking",
                "Ready for Despatch",
                "Booked",
                "Futile Pickup",
                "Pickup Rebooked",
            ]
            queryset = queryset.filter(b_status__in=_104_statuses)
            queryset = queryset.exclude(b_client_name="BioPak")
        elif active_tab_index == 105:  # In Transit
            _105_statuses = [
                "In Transit",
                "Partially In Transit",
                "Partially Delivered",
                "On Board for Delivery",
            ]
            queryset = queryset.filter(b_status__in=_105_statuses)
        elif active_tab_index == 108:  # Late Delivery
            tab_statuses = [
                "In Transit",
                "Partially In Transit",
                "On-Forwarded",
                "On Board for Delivery",
                "Futile Delivery",
                "Delivery Rebooked",
                "Partially Delivered",
            ]
            queryset = queryset.filter(b_status__in=tab_statuses)
            queryset = queryset.exclude(b_client_name="BioPak")
        elif active_tab_index == 110:  # Exceptions
            tab_statuses = [
                "Lost In Transit",
                "Damaged",
                "Returning",
            ]
            queryset = queryset.filter(b_status__in=tab_statuses)

        # Filter `late` bookings
        if active_tab_index == 104:  # Late From Whs
            filtered_pks = []
            t_queryset = queryset.only(
                "id", "pk_booking_id", "b_status", "z_CreatedTimestamp"
            )
            if search_type == "FILTER":
                t_queryset = t_queryset.filter(
                    z_CreatedTimestamp__range=(
                        convert_to_UTC_tz(first_date),
                        convert_to_UTC_tz(last_date),
                    )
                )
            histories = get_status_histories_in_bulk(t_queryset)
            for booking in t_queryset:
                b_history = None
                for history in histories:
                    if booking.pk_booking_id == history.fk_booking_id:
                        if booking.b_status == history.status_last:
                            b_history = history
                            break
                event_at = None
                if b_history:
                    event_at = (
                        b_history.event_time_stamp or b_history.z_createdTimestamp
                    )
                if not b_history and booking.b_status == "Picking":
                    event_at = booking.z_CreatedTimestamp

                if event_at:
                    t_delta = UTC_TZ.localize(datetime.now()) - event_at
                    hours = timedelta_2_hours(t_delta)
                    if hours > 24:
                        filtered_pks.append(booking.id)
            queryset = queryset.filter(pk__in=filtered_pks)
        elif active_tab_index == 108:  # Late Delivery
            filtered_pks = []
            t_queryset = queryset
            if search_type == "FILTER":
                t_queryset = t_queryset.filter(
                    z_CreatedTimestamp__range=(
                        convert_to_UTC_tz(first_date),
                        convert_to_UTC_tz(last_date),
                    )
                )
            for booking in t_queryset:
                s_06 = booking.get_s_06()
                if s_06 and s_06 < UTC_TZ.localize(datetime.now()):
                    filtered_pks.append(booking.id)
            queryset = queryset.filter(pk__in=filtered_pks)

        queryset = queryset.select_related("api_booking_quote")
        # If booking_ids is not None
        if booking_ids:
            queryset = queryset.filter(pk__in=booking_ids)

            # Column fitler
            queryset = filter_bookings_by_columns(
                queryset, column_filters, active_tab_index
            )
        else:
            # Client filter
            if client_pk is not "0":
                client = DME_clients.objects.get(pk_id_dme_client=int(client_pk))
                queryset = queryset.filter(kf_client_id=client.dme_account_num)

            if (
                "new" in download_option
                or "check_pod" in download_option
                or "flagged" in download_option
            ):
                # New POD filter
                if download_option == "new_pod":
                    queryset = queryset.filter(
                        z_downloaded_pod_timestamp__isnull=True
                    ).exclude(Q(z_pod_url__isnull=True) | Q(z_pod_url__exact=""))

                # New POD_SOG filter
                if download_option == "new_pod_sog":
                    queryset = queryset.filter(
                        z_downloaded_pod_sog_timestamp__isnull=True
                    ).exclude(
                        Q(z_pod_signed_url__isnull=True) | Q(z_pod_signed_url__exact="")
                    )

                # New Lable filter
                if download_option == "new_label":
                    queryset = queryset.filter(
                        z_downloaded_shipping_label_timestamp__isnull=True
                    ).exclude(Q(z_label_url__isnull=True) | Q(z_label_url__exact=""))

                # New Connote filter
                if download_option == "new_connote":
                    queryset = queryset.filter(
                        z_downloaded_connote_timestamp__isnull=True
                    ).exclude(
                        Q(z_connote_url__isnull=True) | Q(z_connote_url__exact="")
                    )

                # Check POD
                if download_option == "check_pod":
                    queryset = (
                        queryset.exclude(b_status__icontains="delivered")
                        .exclude(
                            (Q(z_pod_url__isnull=True) | Q(z_pod_url__exact="")),
                            (
                                Q(z_pod_signed_url__isnull=True)
                                | Q(z_pod_signed_url__exact="")
                            ),
                        )
                        .order_by("-check_pod")
                    )

                # Flagged
                if download_option == "flagged":
                    queryset = queryset.filter(b_is_flagged_add_on_services=True)

                if column_filters:
                    queryset = filter_bookings_by_columns(
                        queryset, column_filters, active_tab_index
                    )

            else:
                if search_type == "FILTER":
                    # Date filter
                    if user_type == "DME":
                        queryset = queryset.filter(
                            z_CreatedTimestamp__range=(
                                convert_to_UTC_tz(first_date),
                                convert_to_UTC_tz(last_date),
                            )
                        )
                    else:
                        if client.company_name == "BioPak":
                            queryset = queryset.filter(
                                puPickUpAvailFrom_Date__range=(first_date, last_date)
                            )
                        else:
                            queryset = queryset.filter(
                                z_CreatedTimestamp__range=(
                                    convert_to_UTC_tz(first_date),
                                    convert_to_UTC_tz(last_date),
                                )
                            )

                # Warehouse filter
                if int(warehouse_id) is not 0:
                    queryset = queryset.filter(fk_client_warehouse=int(warehouse_id))

                # Warehouse filter
                if int(fp_id) is not 0:
                    fp = Fp_freight_providers.objects.get(pk=fp_id)
                    queryset = queryset.filter(
                        vx_freight_provider__iexact=fp.fp_company_name
                    )

                # Mulitple search | Simple search | Project Name Search
                if project_name:
                    queryset = queryset.filter(b_booking_project=project_name)
                elif (
                    multi_find_field
                    and multi_find_values
                    and len(multi_find_values) > 0
                ):
                    if multi_find_field == "postal_code_pair":
                        queryset = queryset.filter(
                            de_To_Address_PostalCode__gte=multi_find_values[0],
                            de_To_Address_PostalCode__lte=multi_find_values[1],
                        )
                    elif multi_find_field == "postal_code_type":
                        postal_code_ranges = get_postal_codes(name=multi_find_values[0])
                        or_filters = Q()
                        or_filters.connector = Q.OR

                        for one_or_range in postal_code_ranges:
                            if "-" in one_or_range:
                                _from = one_or_range.split("-")[0]
                                _to = one_or_range.split("-")[1]
                                or_filters.add(
                                    Q(de_To_Address_PostalCode__gte=_from)
                                    & Q(de_To_Address_PostalCode__lte=_to),
                                    Q.OR,
                                )
                            else:
                                _one = one_or_range
                                or_filters.add(Q(de_To_Address_PostalCode=_one), Q.OR)

                        queryset = queryset.filter(or_filters)
                    else:
                        preserved = Case(
                            *[
                                When(
                                    **{
                                        f"{multi_find_field}": multi_find_value,
                                        "then": pos,
                                    }
                                )
                                for pos, multi_find_value in enumerate(
                                    multi_find_values
                                )
                            ]
                        )
                        filter_kwargs = {f"{multi_find_field}__in": multi_find_values}

                        if not multi_find_field in [
                            "gap_ra",
                            "clientRefNumber",
                            "connote_or_reference",
                        ]:
                            queryset = queryset.filter(**filter_kwargs).order_by(
                                preserved
                            )
                        elif multi_find_field == "connote_or_reference":
                            surchage_datas = Surcharge.objects.filter(
                                **filter_kwargs
                            ).order_by(preserved)

                            booking_ids = []
                            for surcharge_data in surchage_datas:
                                if surcharge_data.booking:
                                    booking_ids.append(surcharge_data.booking.id)

                            preserved = Case(
                                *[
                                    When(pk=pk, then=pos)
                                    for pos, pk in enumerate(booking_ids)
                                ]
                            )
                            queryset = queryset.filter(pk__in=booking_ids).order_by(
                                preserved
                            )
                        else:
                            line_datas = Booking_lines_data.objects.filter(
                                **filter_kwargs
                            ).order_by(preserved)

                            booking_ids = []
                            for line_data in line_datas:
                                if line_data.booking():
                                    booking_ids.append(line_data.booking().id)

                            preserved = Case(
                                *[
                                    When(pk=pk, then=pos)
                                    for pos, pk in enumerate(booking_ids)
                                ]
                            )
                            queryset = queryset.filter(pk__in=booking_ids).order_by(
                                preserved
                            )
                elif simple_search_keyword and len(simple_search_keyword) > 0:
                    if (
                        not "&" in simple_search_keyword
                        and not "|" in simple_search_keyword
                    ):
                        queryset = queryset.filter(
                            Q(b_bookingID_Visual__icontains=simple_search_keyword)
                            | Q(puPickUpAvailFrom_Date__icontains=simple_search_keyword)
                            | Q(puCompany__icontains=simple_search_keyword)
                            | Q(pu_Address_Suburb__icontains=simple_search_keyword)
                            | Q(pu_Address_State__icontains=simple_search_keyword)
                            | Q(pu_Address_PostalCode__icontains=simple_search_keyword)
                            | Q(
                                pu_Comm_Booking_Communicate_Via__icontains=simple_search_keyword
                            )
                            | Q(deToCompanyName__icontains=simple_search_keyword)
                            | Q(de_To_Address_Suburb__icontains=simple_search_keyword)
                            | Q(de_To_Address_State__icontains=simple_search_keyword)
                            | Q(
                                de_To_Address_PostalCode__icontains=simple_search_keyword
                            )
                            | Q(
                                de_To_Comm_Delivery_Communicate_Via=simple_search_keyword
                            )
                            | Q(
                                b_clientReference_RA_Numbers__icontains=simple_search_keyword
                            )
                            | Q(vx_freight_provider__icontains=simple_search_keyword)
                            | Q(vx_serviceName__icontains=simple_search_keyword)
                            | Q(v_FPBookingNumber__icontains=simple_search_keyword)
                            | Q(b_status__icontains=simple_search_keyword)
                            | Q(b_status_API__icontains=simple_search_keyword)
                            | Q(b_booking_Category__icontains=simple_search_keyword)
                            | Q(b_status_category__icontains=simple_search_keyword)
                            | Q(
                                s_05_Latest_Pick_Up_Date_TimeSet__icontains=simple_search_keyword
                            )
                            | Q(
                                s_06_Latest_Delivery_Date_TimeSet__icontains=simple_search_keyword
                            )
                            | Q(
                                s_20_Actual_Pickup_TimeStamp__icontains=simple_search_keyword
                            )
                            | Q(
                                s_21_Actual_Delivery_TimeStamp__icontains=simple_search_keyword
                            )
                            | Q(b_client_sales_inv_num__icontains=simple_search_keyword)
                            | Q(pu_Contact_F_L_Name__icontains=simple_search_keyword)
                            | Q(
                                de_to_PickUp_Instructions_Address__icontains=simple_search_keyword
                            )
                            | Q(b_client_name__icontains=simple_search_keyword)
                            | Q(b_client_name_sub__icontains=simple_search_keyword)
                            | Q(b_client_order_num__icontains=simple_search_keyword)
                        )
                    else:
                        if "&" in simple_search_keyword:
                            search_keywords = simple_search_keyword.split("&")

                            for search_keyword in search_keywords:
                                search_keyword = search_keyword.replace(" ", "").lower()

                                if len(search_keyword) > 0:
                                    queryset = queryset.filter(
                                        de_to_PickUp_Instructions_Address__icontains=search_keyword
                                    )
                        elif "|" in simple_search_keyword:
                            search_keywords = simple_search_keyword.split("|")

                            for index, search_keyword in enumerate(search_keywords):
                                search_keywords[index] = search_keyword.replace(
                                    " ", ""
                                ).lower()

                            list_of_Q = [
                                Q(
                                    **{
                                        "de_to_PickUp_Instructions_Address__icontains": val
                                    }
                                )
                                for val in search_keywords
                            ]
                            queryset = queryset.filter(reduce(operator.or_, list_of_Q))
                # Column fitler
                queryset = filter_bookings_by_columns(
                    queryset, column_filters, active_tab_index
                )

        # Sort
        if download_option != "check_pod" and (
            len(multi_find_values) == 0
            or (len(multi_find_values) > 0 and sort_field not in ["id", "-id"])
        ):
            if sort_field is None:
                queryset = queryset.order_by("id")
            else:
                if sort_field == "z_pod_url":
                    queryset = queryset.order_by(sort_field, "z_pod_signed_url")
                else:
                    queryset = queryset.order_by(sort_field)

        # Assign to bookings value!
        bookings = queryset.only(*BOOKING_FIELDS_4_ALLBOOKING_TABLE)

        filtered_booking_ids = []
        filtered_booking_visual_ids = []
        filtered_consignments = []
        filtered_order_nums = []
        for booking in queryset:
            filtered_booking_ids.append(booking.id)
            filtered_booking_visual_ids.append(booking.b_bookingID_Visual)
            filtered_consignments.append(booking.v_FPBookingNumber)
            filtered_order_nums.append(booking.b_client_order_num)

        # Count
        bookings_cnt = len(filtered_booking_ids)

        # Pagination
        page_cnt = (
            int(bookings_cnt / int(page_item_cnt))
            if bookings_cnt % int(page_item_cnt) == 0
            else int(bookings_cnt / int(page_item_cnt)) + 1
        )
        queryset = queryset[
            int(page_item_cnt)
            * int(page_ind) : int(page_item_cnt)
            * (int(page_ind) + 1)
        ]

        if active_tab_index == 8:
            picked_booking_pk_booking_ids = []

            for booking in queryset:
                if booking.b_status == "Picked" or booking.b_dateBookedDate:
                    picked_booking_pk_booking_ids.append(booking.pk_booking_id)

            scanned_quotes_4_picked_bookings = API_booking_quotes.objects.filter(
                fk_booking_id__in=picked_booking_pk_booking_ids,
                packed_status=Booking_lines.SCANNED_PACK,
                is_used=False,
            ).only(
                "id",
                "fk_booking_id",
                "freight_provider",
                "account_code",
                "client_mu_1_minimum_values",
            )

            context = {
                "scanned_quotes_4_picked_bookings": scanned_quotes_4_picked_bookings
            }
            bookings = SimpleBookingSerializer(
                queryset, many=True, context=context
            ).data
        else:
            bookings = SimpleBookingSerializer(queryset, many=True).data

        # Sort on `remaining time` on 'Delivery Management' tab
        if active_tab_index == 6:
            bookings = sorted(bookings, key=lambda k: k["remaining_time_in_seconds"])

        # clientRefNumber & gapRa
        results = []
        if multi_find_field == "gap_ra":
            line_datas = get_gapRas(bookings)
            for booking in bookings:
                booking_gap_ras = []
                for line_data in line_datas:
                    if booking["pk_booking_id"] == line_data.fk_booking_id:
                        booking_gap_ras.append(line_data.gap_ra)

                gapRas = ("gapRas", ", ".join(booking_gap_ras))
                items = list(booking.items())
                items.append(gapRas)
                booking = OrderedDict(items)
                results.append(booking)
        elif multi_find_field == "clientRefNumber":
            line_datas = get_clientRefNumbers(bookings)
            for booking in bookings:
                booking_clientRefNumbers = []
                for line_data in line_datas:
                    if booking["pk_booking_id"] == line_data.fk_booking_id:
                        booking_clientRefNumbers.append(line_data.clientRefNumber)

                clientRefNumbers = (
                    "clientRefNumbers",
                    ", ".join(booking_clientRefNumbers),
                )
                items = list(booking.items())
                items.append(clientRefNumbers)
                booking = OrderedDict(items)
                results.append(booking)
        elif multi_find_field == "connote_or_reference":
            surcharge_datas = get_connoteOrReference(bookings)
            for booking in bookings:
                booking_connote_or_reference = []
                for surcharge_data in surcharge_datas:
                    if booking["id"] == surcharge_data.booking_id:
                        booking_connote_or_reference.append(
                            surcharge_data.connote_or_reference
                        )

                connoteOrReference = (
                    "connoteOrReference",
                    ", ".join(booking_connote_or_reference),
                )
                items = list(booking.items())
                items.append(connoteOrReference)
                booking = OrderedDict(items)
                results.append(booking)
        else:
            results = bookings

        # lines info
        _results = []
        lines = get_lines_in_bulk(bookings)
        for result in results:
            # if has 'scanned' then extract lines info from `scanned`
            # else extract from `original`
            original_lines_count = 0
            original_total_kgs = 0
            original_total_cbm = 0  # Cubic Meter

            scanned_lines_count = 0
            scanned_total_kgs = 0
            scanned_total_cbm = 0  # Cubic Meter

            has_rolls_or_packets = False

            for line in lines:
                if result["pk_booking_id"] == line.fk_booking_id:
                    if not (line.e_type_of_packaging or "").upper() in (
                        CARTONS + PALLETS
                    ):
                        has_rolls_or_packets = True
                    if line.packed_status == "scanned":
                        scanned_lines_count += line.e_qty or 0
                        scanned_total_kgs += line.e_Total_KG_weight or 0
                        scanned_total_cbm += line.e_1_Total_dimCubicMeter or 0
                    else:
                        original_lines_count += line.e_qty or 0
                        original_total_kgs += line.e_Total_KG_weight or 0
                        original_total_cbm += line.e_1_Total_dimCubicMeter or 0

            original_total_kgs = round(original_total_kgs, 1)
            original_total_cbm = round(original_total_cbm, 1)
            scanned_total_kgs = round(scanned_total_kgs, 1)
            scanned_total_cbm = round(scanned_total_cbm, 1)
            _lines_count = ("lines_count", scanned_lines_count or original_lines_count)
            _total_kgs = ("total_kgs", scanned_total_kgs or original_total_kgs)
            _total_cbm = ("total_cbm", scanned_total_cbm or original_total_cbm)
            _has_rolls_or_packets = ("has_rolls_or_packets", has_rolls_or_packets)
            items = list(result.items())
            items.append(_lines_count)
            items.append(_total_kgs)
            items.append(_total_cbm)
            items.append(_has_rolls_or_packets)
            result = OrderedDict(items)
            _results.append(result)
        results = _results

        # surcharge count
        _results = []
        surcharges = get_surcharges_in_bulk(bookings)
        for result in results:
            booking_surcharges = []
            for surcharge in surcharges:
                if result["id"] == surcharge.booking_id:
                    booking_surcharges.append(surcharge)
            surcharge_cnt = ("surcharge_cnt", len(booking_surcharges))
            items = list(result.items())
            items.append(surcharge_cnt)
            result = OrderedDict(items)
            _results.append(result)
        results = _results

        return JsonResponse(
            {
                "bookings": results,
                "filtered_booking_ids": filtered_booking_ids,
                "filtered_booking_visual_ids": filtered_booking_visual_ids,
                "filtered_consignments": filtered_consignments,
                "filtered_order_nums": filtered_order_nums,
                "count": bookings_cnt,
                "page_cnt": page_cnt,
                "page_ind": page_ind,
                "page_item_cnt": page_item_cnt,
            }
        )

    @action(detail=True, methods=["put"])
    def update_booking(self, request, pk, format=None):
        booking = Bookings.objects.get(pk=pk)
        lowest_pricing = None

        # Check if `booking_type` changes
        if (
            booking.b_client_name == "Jason L"
            and booking.booking_type != request.data.get("booking_type")
        ):
            if request.data.get("booking_type") == Bookings.DMEP:
                request.data["inv_cost_quoted"] = 0
                request.data["inv_sell_quoted"] = 0
            elif (
                request.data.get("booking_type") == Bookings.DMEA
                and booking.api_booking_quote
            ):
                lowest_pricing = (
                    API_booking_quotes.objects.filter(
                        fk_booking_id=booking.pk_booking_id,
                        packed_status=booking.api_booking_quote.packed_status,
                    )
                    .order_by("client_mu_1_minimum_values")
                    .first()
                )

        # Check if Ariston Wire's booking
        if (
            booking.b_client_name == "Ariston Wire"
            and booking.api_booking_quote != request.data.get("api_booking_quote")
            and not booking.b_dateBookedDate
        ):
            selected_pricing = API_booking_quotes.objects.get(
                pk=request.data.get("api_booking_quote")
            )
            lowest_pricing = selected_pricing
            dme_tokens = DME_Tokens.objects.filter(booking_id=booking.id)
            bok_lines = BOK_2_lines.objects.filter(fk_header_id=booking.pk_booking_id)
            for dme_token in dme_tokens:
                send_email_close_bidding(
                    booking, bok_lines, dme_token, selected_pricing
                )

        serializer = BookingSerializer(booking, data=request.data)
        try:
            if serializer.is_valid():
                serializer.save()

                if lowest_pricing:
                    set_booking_quote(booking, lowest_pricing)

                return Response(serializer.data)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            logger.error(f"update_booking Error: {str(e)}")
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=["put"])
    def change_bookings_status(self, request, format=None):
        LOG_ID = "[CHANGE STATUS IN BULK]"
        status = request.data["status"]
        optional_value = request.data["optionalValue"]
        booking_ids = request.data["bookingIds"]

        try:
            if "flag_add_on_services" in status:
                for booking_id in booking_ids:
                    booking = Bookings.objects.get(pk=booking_id)
                    booking.b_is_flagged_add_on_services = (
                        1 if status == "flag_add_on_services" else 0
                    )
                    booking.save()
                return JsonResponse({"status": "success"})
            else:
                for booking_id in booking_ids:
                    booking = Bookings.objects.get(pk=booking_id)
                    delivery_kpi_days = int(booking.delivery_kpi_days or 14)

                    if status == "In Transit":
                        booking.z_calculated_ETA = (
                            datetime.strptime(optional_value[:16], "%Y-%m-%d %H:%M")
                            + timedelta(days=delivery_kpi_days)
                        ).date()
                        booking.b_given_to_transport_date_time = datetime.strptime(
                            optional_value[:16], "%Y-%m-%d %H:%M"
                        )

                    status_history.create(
                        booking, status, request.user.username, optional_value[:19]
                    )
                    calc_collect_after_status_change(booking.pk_booking_id, status)
                    booking.save()
                return JsonResponse({"status": "success"})
        except Exception as e:
            logger.error(f"{LOG_ID} Error: {str(e)}")
            return Response({"status": "error"})

    @action(detail=False, methods=["post"])
    def get_xls(self, request, format=None):
        user_id = int(self.request.user.id)
        dme_employee = DME_employees.objects.filter(fk_id_user=user_id).first()

        if dme_employee is not None:
            user_type = "DME"
        else:
            user_type = "CLIENT"
            client_employee = Client_employees.objects.filter(
                fk_id_user=user_id
            ).first()
            client_employee_role = client_employee.get_role()
            client = DME_clients.objects.filter(
                pk_id_dme_client=int(client_employee.fk_id_dme_client_id)
            ).first()

        vx_freight_provider = request.data["vx_freight_provider"]
        pk_id_dme_client = request.data["pk_id_dme_client"]
        report_type = request.data["report_type"]
        email_addr = request.data["emailAddr"]
        show_field_name = request.data["showFieldName"]
        use_selected = request.data["useSelected"]
        first_date = None
        last_date = None

        if use_selected:
            booking_ids = request.data["selectedBookingIds"]
        else:
            start_date = request.data["startDate"]
            end_date = request.data["endDate"]
            first_date = datetime.strptime(start_date, "%Y-%m-%d")
            last_date = datetime.strptime(end_date, "%Y-%m-%d")
            last_date = last_date.replace(hour=23, minute=59, second=59)

        # DME & Client filter
        if user_type == "DME":
            queryset = Bookings.objects.all()
        else:
            if client_employee_role == "company":
                queryset = Bookings.objects.filter(kf_client_id=client.dme_account_num)
            elif (
                client_employee_role == "employee"
                and client_employee.name_first == "Teddybed"
            ):
                queryset = Bookings.objects.filter(
                    kf_client_id=client.dme_account_num,
                    b_client_name_sub="Teddybed Australia Pty Ltd",
                )
            elif client_employee_role == "warehouse":
                employee_warehouse_id = client_employee.warehouse_id
                queryset = Bookings.objects.filter(
                    kf_client_id=client.dme_account_num,
                    fk_client_warehouse_id=employee_warehouse_id,
                )

        if use_selected:
            queryset = queryset.filter(pk__in=booking_ids)
        else:
            if report_type == "pending_bookings":
                queryset = queryset.filter(
                    z_CreatedTimestamp__range=(
                        convert_to_UTC_tz(first_date),
                        convert_to_UTC_tz(last_date),
                    ),
                    b_status__in=[
                        "Ready for booking",
                        "Picking",
                    ]
                )
            elif report_type == "booked_bookings":
                queryset = queryset.filter(
                    b_dateBookedDate__range=(
                        convert_to_UTC_tz(first_date),
                        convert_to_UTC_tz(last_date),
                    )
                )
            elif report_type == "real_time_bookings":
                queryset = queryset.filter(
                    b_dateBookedDate__range=(
                        convert_to_UTC_tz(first_date),
                        convert_to_UTC_tz(last_date),
                    )
                )
            elif report_type == "picked_up_bookings":
                queryset = queryset.filter(
                    s_20_Actual_Pickup_TimeStamp__range=(
                        convert_to_UTC_tz(first_date),
                        convert_to_UTC_tz(last_date),
                    )
                )
            elif report_type == "box":
                queryset = queryset.filter(
                    b_dateBookedDate__range=(
                        convert_to_UTC_tz(first_date),
                        convert_to_UTC_tz(last_date),
                    ),
                    puCompany__icontains="Tempo Aus Whs",
                    pu_Address_Suburb__iexact="FRENCHS FOREST",
                )
            elif report_type == "futile":
                queryset = queryset.filter(
                    b_dateBookedDate__range=(
                        convert_to_UTC_tz(first_date),
                        convert_to_UTC_tz(last_date),
                    )
                )
            elif report_type == "bookings_delivered":
                queryset = queryset.filter(
                    s_21_Actual_Delivery_TimeStamp__range=(
                        convert_to_UTC_tz(first_date),
                        convert_to_UTC_tz(last_date),
                    ),
                    b_status__iexact="delivered",
                )
            elif report_type in ["bookings_sent", "booking_lines_sent"]:
                queryset = queryset.filter(
                    b_dateBookedDate__range=(
                        convert_to_UTC_tz(first_date),
                        convert_to_UTC_tz(last_date),
                    ),
                    b_dateBookedDate__isnull=False,
                )
            elif report_type in ["delivery"]:
                queryset = queryset.filter(
                    b_dateBookedDate__range=(
                        convert_to_UTC_tz(first_date),
                        convert_to_UTC_tz(last_date),
                    ),
                    b_dateBookedDate__isnull=False,
                )
            elif report_type in ["cost_report_dme_only"]:
                queryset = queryset.exclude(b_client_name="BioPak").filter(
                    z_CreatedTimestamp__range=(
                        convert_to_UTC_tz(first_date),
                        convert_to_UTC_tz(last_date),
                    )
                )
            else:
                # Date filter
                if user_type == "DME":
                    queryset = queryset.filter(
                        z_CreatedTimestamp__range=(
                            convert_to_UTC_tz(first_date),
                            convert_to_UTC_tz(last_date),
                        )
                    )
                else:
                    if client.company_name == "BioPak":
                        queryset = queryset.filter(
                            puPickUpAvailFrom_Date__range=(first_date, last_date)
                        )
                    else:
                        queryset = queryset.filter(
                            z_CreatedTimestamp__range=(
                                convert_to_UTC_tz(first_date),
                                convert_to_UTC_tz(last_date),
                            )
                        )

            # Freight Provider filter
            if vx_freight_provider != "All":
                queryset = queryset.filter(vx_freight_provider=vx_freight_provider)

            # Client filter
            if pk_id_dme_client != "All" and pk_id_dme_client != 0:
                client = DME_clients.objects.get(pk_id_dme_client=pk_id_dme_client)
                queryset = queryset.filter(kf_client_id=client.dme_account_num)

        # Optimized to speed up building XLS
        queryset.only(
            "id",
            "pk_booking_id",
            "b_dateBookedDate",
            "pu_Address_State",
            "puCompany",
            "deToCompanyName",
            "de_To_Address_Suburb",
            "de_To_Address_State",
            "de_To_Address_PostalCode",
            "b_client_sales_inv_num",
            "b_client_order_num",
            "v_FPBookingNumber",
            "b_status",
            "b_status_category",
            "dme_status_detail",
            "dme_status_action",
            "s_05_LatestPickUpDateTimeFinal",
            "s_06_Latest_Delivery_Date_TimeSet",
            "s_20_Actual_Pickup_TimeStamp",
            "s_21_ActualDeliveryTimeStamp",
            "z_pod_url",
            "z_pod_signed_url",
            "delivery_kpi_days",
            "de_Deliver_By_Date",
            "vx_freight_provider",
            "pu_Address_Suburb",
            "b_bookingID_Visual",
            "b_client_name",
            "b_client_name_sub",
            "fp_invoice_no",
            "inv_cost_quoted",
            "inv_cost_actual",
            "inv_sell_quoted",
            "inv_sell_quoted_override",
            "inv_booked_quoted",
            "inv_sell_actual",
            "dme_status_linked_reference_from_fp",
            "inv_billing_status",
            "inv_billing_status_note",
            "b_booking_Category",
            # "clientRefNumbers",
            # "gap_ras",
            "s_05_LatestPickUpDateTimeFinal",
            "b_booking_Notes",
            "dme_client_notes",
            "z_CreatedTimestamp",
            "de_to_Pick_Up_Instructions_Contact",
            "de_to_PickUp_Instructions_Address",
            "de_To_AddressType",
            "b_client_warehouse_code",
        )

        build_xls_and_send(
            queryset,
            email_addr,
            report_type,
            str(self.request.user),
            first_date,
            last_date,
            show_field_name,
            get_clientname_with_request(request),
        )
        return JsonResponse({"status": "started generate xml"})

    @action(detail=False, methods=["post"])
    def calc_collected(self, request, format=None):
        booking_ids = request.data["bookingIds"]
        type = request.data["type"]

        try:
            for id in booking_ids:
                booking = Bookings.objects.get(id=int(id))
                booking_lines = Booking_lines.objects.filter(
                    fk_booking_id=booking.pk_booking_id
                )

                for booking_line in booking_lines:
                    if type == "Calc":
                        if not booking_line.e_qty:
                            booking_line.e_qty = 0
                        if not booking_line.e_qty_awaiting_inventory:
                            booking_line.e_qty_awaiting_inventory = 0

                        booking_line.e_qty_collected = int(booking_line.e_qty) - int(
                            booking_line.e_qty_awaiting_inventory
                        )
                        booking_line.save()
                    elif type == "Clear":
                        booking_line.e_qty_collected = 0
                        booking_line.save()
            return JsonResponse(
                {"success": "All bookings e_qty_collected has been calculated"}
            )
        except Exception as e:
            # print('Exception: ', e)
            return JsonResponse({"error": "Got error, please contact support center"})

    @action(detail=False, methods=["get"])
    def get_bookings_4_manifest(self, request, format=None):
        user_id = int(self.request.user.id)
        dme_employee = DME_employees.objects.filter(fk_id_user=user_id).first()

        if dme_employee is not None:
            user_type = "DME"
        else:
            user_type = "CLIENT"
            client_employee = Client_employees.objects.filter(
                fk_id_user=user_id
            ).first()
            client_employee_role = client_employee.get_role()
            client = DME_clients.objects.filter(
                pk_id_dme_client=int(client_employee.fk_id_dme_client_id)
            ).first()

        puPickUpAvailFrom_Date = request.GET["puPickUpAvailFrom_Date"]
        vx_freight_provider = request.GET["vx_freight_provider"]
        if vx_freight_provider == "Tas":
            vx_freight_provider = "TASFR"

        # DME & Client filter
        if user_type == "DME":
            queryset = Bookings.objects.all()
        else:
            if client_employee_role == "company":
                queryset = Bookings.objects.filter(kf_client_id=client.dme_account_num)
            elif (
                client_employee_role == "employee"
                and client_employee.name_first == "Teddybed"
            ):
                queryset = Bookings.objects.filter(
                    kf_client_id=client.dme_account_num,
                    b_client_name_sub="Teddybed Australia Pty Ltd",
                )
            elif client_employee_role == "warehouse":
                employee_warehouse_id = client_employee.warehouse_id
                queryset = Bookings.objects.filter(
                    kf_client_id=client.dme_account_num,
                    fk_client_warehouse_id=employee_warehouse_id,
                )

        queryset = queryset.filter(puPickUpAvailFrom_Date=puPickUpAvailFrom_Date)
        queryset = queryset.filter(vx_freight_provider=vx_freight_provider)
        queryset = queryset.filter(b_status__icontains="Ready for XML")

        # Active Tab content count
        errors_to_correct = 0
        missing_labels = 0
        to_manifest = 0
        to_process = 0
        closed = 0

        for booking in queryset:
            if booking.b_error_Capture is not None and len(booking.b_error_Capture) > 0:
                errors_to_correct += 1
            if booking.z_label_url is None or len(booking.z_label_url) == 0:
                missing_labels += 1
            if booking.b_status == "Booked":
                to_manifest += 1
            if booking.b_status == "Ready to booking":
                to_process += 1
            if booking.b_status == "Closed":
                closed += 1

        # Sort
        queryset = queryset.order_by("-id")

        # Count
        bookings_cnt = queryset.count()
        bookings = queryset

        return JsonResponse(
            {
                "bookings": BookingSerializer(bookings, many=True).data,
                "count": bookings_cnt,
                "errors_to_correct": errors_to_correct,
                "to_manifest": to_manifest,
                "missing_labels": missing_labels,
                "to_process": to_process,
                "closed": closed,
            }
        )

    @action(detail=False, methods=["post"])
    def bulk_booking_update(self, request, format=None):
        LOG_ID = "[BULK BOOKING UPDATE]"
        booking_ids = request.data["bookingIds"]
        field_name = request.data["fieldName"]
        field_content = request.data["fieldContent"]

        if field_content == "":
            field_content = None

        if (
            request.user.username == "anchor_packaging_afs"
            and field_name != "vx_freight_provider"
        ):
            msg = f"Error: You have no permission to update this field!"
            logger(f"{LOG_ID} {request.user.username} {msg}")
            return JsonResponse({"message": msg}, status=400)

        try:
            for booking_id in booking_ids:
                if field_name == "fp_scan":
                    field_content["booking"] = booking_id
                    fp_status_history = FPStatusHistorySerializer(data=field_content)

                    if fp_status_history.is_valid():
                        fp_status_history.save()
                    else:
                        return JsonResponse(
                            {
                                "message": f"Error: {fp_status_history.errors}, Please contact support center!"
                            },
                            status=400,
                        )
                elif field_name == "additional_surcharge":
                    field_content["booking"] = booking_id
                    surcharge = SurchargeSerializer(data=field_content)

                    if surcharge.is_valid():
                        result = surcharge.save()

                        if (
                            "Will be automatically generated"
                            in field_content["connote_or_reference"]
                        ):
                            booking = Bookings.objects.get(id=booking_id)
                            result.connote_or_reference = (
                                f"auto-{str(result.fp_id).zfill(4)}-"
                            )
                            result.connote_or_reference += (
                                f"DME{booking.b_bookingID_Visual}"
                            )
                            result.save()
                    else:
                        return JsonResponse(
                            {
                                "message": f"Error: {surcharge.errors}, Please contact support center!"
                            },
                            status=400,
                        )
                else:
                    booking = Bookings.objects.get(id=booking_id)
                    setattr(booking, field_name, field_content)

                    if not booking.delivery_kpi_days:
                        delivery_kpi_days = 14
                    else:
                        delivery_kpi_days = int(booking.delivery_kpi_days)

                    if field_name == "b_project_due_date" and field_content:
                        if not booking.delivery_booking:
                            booking.de_Deliver_From_Date = field_content
                            booking.de_Deliver_By_Date = field_content
                    elif field_name == "delivery_booking" and field_content:
                        booking.de_Deliver_From_Date = field_content
                        booking.de_Deliver_By_Date = field_content
                    elif (
                        field_name == "fp_received_date_time"
                        and field_content
                        and not booking.b_given_to_transport_date_time
                    ):
                        booking.z_calculated_ETA = datetime.strptime(
                            field_content, "%Y-%m-%d"
                        ) + timedelta(days=delivery_kpi_days)
                    elif (
                        field_name == "b_given_to_transport_date_time" and field_content
                    ):
                        booking.z_calculated_ETA = datetime.strptime(
                            field_content, "%Y-%m-%d %H:%M:%S"
                        ) + timedelta(days=delivery_kpi_days)
                    elif field_name == "vx_freight_provider" and field_content:
                        logger.info(f"Rebuild label required")
                        booking.z_downloaded_shipping_label_timestamp = None

                        if booking.z_label_url:
                            booking.z_label_url = (
                                "[REBUILD_REQUIRED]" + booking.z_label_url
                            )
                        else:
                            booking.z_label_url = "[REBUILD_REQUIRED]"

                        # JasonL and 3 special FP
                        if booking.b_client_name == "Jason L":
                            if field_content in SPECIAL_FPS:
                                booking.booking_type = "DMEM"
                                booking.is_quote_locked = True

                    booking.save()
            return JsonResponse(
                {"message": "Bookings are updated successfully"}, status=200
            )
        except Exception as e:
            # print("Exception: ", e)
            return JsonResponse(
                {"message": f"Error: {e}, Please contact support center!"}, status=400
            )

    @action(detail=False, methods=["get"])
    def get_status_info(self, request, format=None):
        user_id = int(self.request.user.id)
        dme_employee = DME_employees.objects.filter(fk_id_user=user_id).first()

        if dme_employee is not None:
            user_type = "DME"
        else:
            user_type = "CLIENT"
            client_employee = Client_employees.objects.filter(
                fk_id_user=user_id
            ).first()
            client_employee_role = client_employee.get_role()
            client = DME_clients.objects.filter(
                pk_id_dme_client=int(client_employee.fk_id_dme_client_id)
            ).first()

        start_date = self.request.query_params.get("startDate", None)
        end_date = self.request.query_params.get("endDate", None)
        first_date = datetime.strptime(start_date, "%Y-%m-%d")
        last_date = datetime.strptime(end_date, "%Y-%m-%d") + timedelta(days=1)
        client_pk = self.request.query_params.get("clientPK", None)

        # DME & Client filter
        if user_type == "DME":
            queryset = Bookings.objects.all()
        else:
            if client_employee_role == "company":
                queryset = Bookings.objects.filter(kf_client_id=client.dme_account_num)
            elif (
                client_employee_role == "employee"
                and client_employee.name_first == "Teddybed"
            ):
                queryset = Bookings.objects.filter(
                    kf_client_id=client.dme_account_num,
                    b_client_name_sub="Teddybed Australia Pty Ltd",
                )
            elif client_employee_role == "warehouse":
                employee_warehouse_id = client_employee.warehouse_id
                queryset = Bookings.objects.filter(
                    kf_client_id=client.dme_account_num,
                    fk_client_warehouse_id=employee_warehouse_id,
                )

        # Client filter
        if client_pk is not "0":
            client = DME_clients.objects.get(pk_id_dme_client=int(client_pk))
            queryset = queryset.filter(kf_client_id=client.dme_account_num)

        # Date filter
        if user_type == "DME":
            queryset = queryset.filter(
                z_CreatedTimestamp__range=(
                    convert_to_UTC_tz(first_date),
                    convert_to_UTC_tz(last_date),
                )
            )
        else:
            if client.company_name == "BioPak":
                queryset = queryset.filter(
                    puPickUpAvailFrom_Date__range=(first_date, last_date)
                )
            else:
                queryset = queryset.filter(
                    z_CreatedTimestamp__range=(
                        convert_to_UTC_tz(first_date),
                        convert_to_UTC_tz(last_date),
                    )
                )

        # Get all statuses
        dme_statuses = Utl_dme_status.objects.all().order_by("dme_delivery_status")

        ret_data = []
        for dme_status in dme_statuses:
            ret_data.append(
                {
                    "dme_delivery_status": dme_status.dme_delivery_status,
                    "dme_status_label": dme_status.dme_status_label
                    if dme_status.dme_status_label is not None
                    else dme_status.dme_delivery_status,
                    "count": queryset.filter(
                        b_status=dme_status.dme_delivery_status
                    ).count(),
                }
            )

        return JsonResponse({"results": ret_data})

    @action(detail=False, methods=["get"])
    def get_manifest_report(self, request, format=None):
        clientname = get_clientname_with_request(self.request)
        page_index = int(request.GET["index"])

        if not clientname in ["Jason L", "Bathroom Sales Direct", "BioPak", "dme"]:
            return JsonResponse(
                {"message": "You have no permission to see this information"},
                status=400,
            )

        sydney_now = get_sydney_now_time("datetime")
        last_date = datetime.now() - timedelta(days=20 * page_index)
        first_date = (sydney_now - timedelta(days=20 * (page_index + 1))).date()
        manifest_logs = (
            Dme_manifest_log.objects.filter(
                z_createdTimeStamp__range=(first_date, last_date)
            )
            .order_by("-z_createdTimeStamp")
            .only("id", "manifest_url")
        )

        manifest_ids = []
        booking_ids_in_str = []
        booking_ids = []
        for manifest_log in manifest_logs:
            manifest_ids.append(manifest_log.pk)
            booking_ids_in_str += (manifest_log.booking_ids or "").split(",")
        for booking_id in booking_ids_in_str:
            if booking_id:
                booking_ids.append(booking_id)

        bookings_with_manifest = Bookings.objects.prefetch_related(
            "fk_client_warehouse"
        ).filter(pk__in=booking_ids)

        # Client filter
        if clientname != "dme":
            bookings_with_manifest = bookings_with_manifest.filter(
                b_client_name=clientname
            )

        results = []
        report_fps = []
        client_ids = []
        index = 0
        for manifest_log in manifest_logs:
            result = {"freight_providers": [], "vehicles": [], "cnt_4_each_fp": {}}
            daily_count = 0
            first_booking = None
            b_bookingID_Visuals = []

            for booking in bookings_with_manifest:
                if booking.z_manifest_url == manifest_log.manifest_url:
                    first_booking = booking
                    daily_count += 1
                    b_bookingID_Visuals.append(booking.b_bookingID_Visual)

                    if not booking.vx_freight_provider in result["cnt_4_each_fp"]:
                        result["cnt_4_each_fp"][booking.vx_freight_provider] = 1
                    else:
                        result["cnt_4_each_fp"][booking.vx_freight_provider] += 1

                    if not booking.vx_freight_provider in result["freight_providers"]:
                        result["freight_providers"].append(booking.vx_freight_provider)
                        result["vehicles"].append(
                            booking.b_booking_project
                            if booking.vx_freight_provider == "Deliver-ME"
                            else f"{booking.vx_freight_provider} Vehicle"
                        )

            if not first_booking:
                msg = f"Can not find first booking: {manifest_log}, {manifest_log.manifest_url}"
                logger.error(msg)
                continue

            result["manifest_id"] = manifest_ids[index]
            result["count"] = daily_count
            result["z_manifest_url"] = first_booking.z_manifest_url
            result["warehouse_name"] = first_booking.fk_client_warehouse.name
            result["manifest_date"] = manifest_log.z_createdTimeStamp
            result["b_bookingID_Visuals"] = b_bookingID_Visuals
            result["kf_client_id"] = first_booking.kf_client_id
            results.append(result)

            if first_booking.vx_freight_provider not in report_fps:
                report_fps.append(first_booking.vx_freight_provider)

            if first_booking.kf_client_id not in client_ids:
                client_ids.append(first_booking.kf_client_id)

            index += 1

        clients = DME_clients.objects.filter(dme_account_num__in=client_ids).only(
            "company_name", "dme_account_num"
        )
        report_clients = []
        for client in clients:
            report_client = {}
            report_client["company_name"] = client.company_name
            report_client["dme_account_num"] = client.dme_account_num
            report_clients.append(report_client)
        return JsonResponse(
            {
                "results": results,
                "report_fps": report_fps,
                "report_clients": report_clients,
            }
        )

    @action(detail=False, methods=["get"])
    def get_project_names(self, request, format=None):
        user_id = int(self.request.user.id)
        dme_employee = DME_employees.objects.filter(fk_id_user=user_id).first()

        if dme_employee is not None:
            user_type = "DME"
        else:
            user_type = "CLIENT"
            client_employee = Client_employees.objects.filter(
                fk_id_user=user_id
            ).first()
            client_employee_role = client_employee.get_role()
            client = DME_clients.objects.filter(
                pk_id_dme_client=int(client_employee.fk_id_dme_client_id)
            ).first()

        # DME & Client filter
        if user_type == "DME":
            queryset = Bookings.objects.all()
        else:
            if client_employee_role == "company":
                queryset = Bookings.objects.filter(kf_client_id=client.dme_account_num)
            elif (
                client_employee_role == "employee"
                and client_employee.name_first == "Teddybed"
            ):
                queryset = Bookings.objects.filter(
                    kf_client_id=client.dme_account_num,
                    b_client_name_sub="Teddybed Australia Pty Ltd",
                )
            elif client_employee_role == "warehouse":
                employee_warehouse_id = client_employee.warehouse_id
                queryset = Bookings.objects.filter(
                    kf_client_id=client.dme_account_num,
                    fk_client_warehouse_id=employee_warehouse_id,
                )

        results = (
            queryset.exclude(
                Q(b_booking_project__isnull=True) | Q(b_booking_project__exact="")
            )
            .values_list("b_booking_project", flat=True)
            .distinct()
        )

        return JsonResponse({"results": list(results)})

    @action(detail=False, methods=["get"])
    def send_email(self, request, format=None):
        user_id = int(self.request.user.id)
        template_name = self.request.query_params.get("templateName", None)
        booking_id = self.request.query_params.get("bookingId", None)
        send_booking_status_email(booking_id, template_name, self.request.user.username)
        return JsonResponse({"message": "success"}, status=200)

    @action(detail=False, methods=["post"])
    def pricing_analysis(self, request, format=None):
        bookingIds = request.data["bookingIds"]
        results = analyse_booking_quotes_table(bookingIds)
        return JsonResponse({"message": "success", "results": results}, status=200)

    @action(detail=False, methods=["post"])
    def get_bookings_summary(self, request, format=None):
        bookingIds = request.data["bookingIds"]
        bookings = Bookings.objects.filter(pk__in=bookingIds)
        bookings = bookings.only(
            "pk_booking_id",
            "b_bookingID_Visual",
            "vx_freight_provider",
            "b_client_order_num",
        )

        pk_booking_ids = []
        for booking in bookings:
            pk_booking_ids.append(booking.pk_booking_id)

        booking_lines = Booking_lines.objects.filter(
            fk_booking_id__in=pk_booking_ids,
            packed_status__in=[Booking_lines.ORIGINAL, Booking_lines.SCANNED_PACK],
            is_deleted=False,
        ).only(
            "fk_booking_id",
            "e_qty",
            "e_dimUOM",
            "e_dimLength",
            "e_dimHeight",
            "e_dimWidth",
            "e_Total_KG_weight",
            "e_weightPerEach",
            "packed_status",
        )

        total_qty, total_kgs, total_cbm = 0, 0, 0
        fps = {}
        stats = {}

        for booking in bookings:
            if not booking.vx_freight_provider in fps:
                fps[booking.vx_freight_provider] = {
                    "orderCnt": 0,
                    "totalQty": 0,
                    "totalKgs": 0,
                    "totalCubicMeter": 0,
                }

            fps[booking.vx_freight_provider]["orderCnt"] += 1

            original_lines, scanned_lines = [], []
            for line in booking_lines:
                if booking.pk_booking_id == line.fk_booking_id:
                    if line.packed_status == Booking_lines.ORIGINAL:
                        original_lines.append(line)
                    else:
                        scanned_lines.append(line)

            stats[booking.b_bookingID_Visual] = {
                "b_client_order_num": booking.b_client_order_num,
                "original_lines_count": len(original_lines),
                "scanned_lines_count": len(scanned_lines),
            }

            for line in scanned_lines or original_lines or []:
                total_qty += line.e_qty
                total_kgs += line.e_Total_KG_weight or 0
                total_cbm += line.e_1_Total_dimCubicMeter or 0

                fps[booking.vx_freight_provider]["totalQty"] += line.e_qty
                fps[booking.vx_freight_provider]["totalKgs"] += line.e_qty * (
                    line.e_weightPerEach or 0
                )
                fps[booking.vx_freight_provider]["totalCubicMeter"] += (
                    line.e_1_Total_dimCubicMeter or 0
                )

        result = {}
        result["fps"] = fps
        result["total_qty"] = total_qty
        result["total_kgs"] = total_kgs
        result["total_cbm"] = total_cbm
        result["stats"] = stats
        return JsonResponse(result, status=200)


class BookingViewSet(viewsets.ViewSet):
    serializer_class = BookingSerializer

    @action(detail=False, methods=["get"])
    def get_booking(self, request, format=None):
        uid = request.GET["id"]
        filterName = request.GET["filter"]
        user_id = request.user.id

        try:
            dme_employee = DME_employees.objects.filter(fk_id_user=user_id).first()
            client_customer_mark_up = None

            if dme_employee is not None:
                user_type = "DME"
            else:
                user_type = "CLIENT"

            if user_type == "DME":
                queryset = Bookings.objects.all()
            else:
                client_employee = Client_employees.objects.filter(
                    fk_id_user=user_id
                ).first()

                if client_employee is None:
                    return JsonResponse({"booking": {}, "nextid": 0, "previd": 0})

                client_employee_role = client_employee.get_role()
                client = DME_clients.objects.get(
                    pk_id_dme_client=client_employee.fk_id_dme_client_id
                )

                if client is None:
                    return JsonResponse({"booking": {}, "nextid": 0, "previd": 0})

                client_customer_mark_up = client.client_customer_mark_up

                if client_employee_role == "company":
                    queryset = Bookings.objects.filter(
                        kf_client_id=client.dme_account_num
                    )
                elif (
                    client_employee_role == "employee"
                    and client_employee.name_first == "Teddybed"
                ):
                    queryset = Bookings.objects.filter(
                        kf_client_id=client.dme_account_num,
                        b_client_name_sub="Teddybed Australia Pty Ltd",
                    )
                elif client_employee_role == "warehouse":
                    employee_warehouse_id = client_employee.warehouse_id
                    queryset = Bookings.objects.filter(
                        kf_client_id=client.dme_account_num,
                        fk_client_warehouse_id=employee_warehouse_id,
                    )

            if filterName == "null":
                booking = queryset.last()
            elif filterName == "dme":
                booking = queryset.get(b_bookingID_Visual=uid)
            elif filterName == "con":
                booking = queryset.filter(v_FPBookingNumber=uid).first()
            elif filterName == "id" and uid and uid != "null":
                booking = queryset.get(id=uid)
            else:
                return JsonResponse({"booking": {}, "nextid": 0, "previd": 0})

            if booking is not None:
                nextBooking = queryset.filter(id__gt=booking.id).order_by("id").first()
                prevBooking = queryset.filter(id__lt=booking.id).order_by("-id").first()
                nextBookingId = 0
                prevBookingId = 0

                if nextBooking is not None:
                    nextBookingId = nextBooking.id
                if prevBooking is not None:
                    prevBookingId = prevBooking.id

                # Get count for `Shipment Packages / Goods`
                booking_lines = Booking_lines.objects.filter(
                    fk_booking_id=booking.pk_booking_id
                )

                e_qty_total = 0
                for booking_line in booking_lines:
                    e_qty_total += booking_line.e_qty or 0

                client_customer_mark_up = 0
                if not client_customer_mark_up and booking.kf_client_id:
                    try:
                        client = DME_clients.objects.get(
                            dme_account_num=booking.kf_client_id
                        )
                        client_customer_mark_up = client.client_customer_mark_up
                    except:
                        pass

                # Get count for 'Attachments'
                cnt_attachments = Dme_attachments.objects.filter(
                    fk_id_dme_booking=booking.pk_booking_id
                ).count()

                # Get count for `additional surcharges`
                cnt_additional_surcharges = Surcharge.objects.filter(
                    booking=booking, is_manually_entered=True
                ).count()

                context = {"client_customer_mark_up": client_customer_mark_up}

                return JsonResponse(
                    {
                        "booking": BookingSerializer(booking, context=context).data,
                        "nextid": nextBookingId,
                        "previd": prevBookingId,
                        "e_qty_total": e_qty_total,
                        "cnt_attachments": cnt_attachments,
                        "cnt_additional_surcharges": cnt_additional_surcharges,
                    }
                )
            return JsonResponse(
                {
                    "booking": {},
                    "nextid": 0,
                    "previd": 0,
                    "e_qty_total": 0,
                    "cnt_attachments": 0,
                    "cnt_additional_surcharges": 0,
                }
            )
        except Exception as e:
            trace_error.print()
            logger.info(f"#104 - Get booking exception: {str(e)}")
            return JsonResponse(
                {
                    "booking": {},
                    "nextid": 0,
                    "previd": 0,
                    "e_qty_total": 0,
                    "cnt_attachments": 0,
                    "cnt_additional_surcharges": 0,
                }
            )

    @action(detail=False, methods=["get"], permission_classes=[AllowAny])
    def get_booking_for_bidding(self, request):
        LOG_ID = "[get_booking_for_bidding]"
        token = request.GET["identifier"]
        logger.info(f"{LOG_ID} token: {token}")

        if not token or len(token.split("_")) != 2:
            logger.info(f"{LOG_ID} Error: Wrong identifier.")
            res_json = {"message": "Wrong identifier."}
            return Response(res_json, status=status.HTTP_400_BAD_REQUEST)

        dme_token = DME_Tokens.objects.get(token=token)
        if not dme_token:
            logger.info(f"{LOG_ID} Error: Wrong identifier.")
            res_json = {"message": "Wrong identifier."}
            return Response(res_json, status=status.HTTP_400_BAD_REQUEST)

        try:
            booking_id = token.split("_")[1]
            booking = Bookings.objects.get(pk=booking_id)
            booking_lines = Booking_lines.objects.filter(
                fk_booking_id=booking.pk_booking_id, is_deleted=False
            )
            booking_lines_data = Booking_lines_data.objects.filter(
                fk_booking_id=booking.pk_booking_id
            )

            result = BookingSerializer(booking).data
            result["booking_lines"] = BookingLineSerializer(
                booking_lines, many=True
            ).data
            result["booking_lines_data"] = BookingLineDetailSerializer(
                booking_lines_data, many=True
            ).data

            quote_set = API_booking_quotes.objects.filter(
                pk=dme_token.api_booking_quote_id
            )
            client = DME_clients.objects.get(dme_account_num=booking.kf_client_id)
            if quote_set:
                context = {"client_customer_mark_up": client.client_customer_mark_up}
                json_results = SimpleQuoteSerializer(
                    quote_set, many=True, context=context
                ).data
                json_results = beautify_eta(json_results, quote_set, client)

                # Surcharge point
                for json_result in json_results:
                    quote = None

                    for _quote in quote_set:
                        if _quote.pk == json_result["cost_id"]:
                            quote = _quote

                    context = {"client_mark_up_percent": client.client_mark_up_percent}
                    json_result["surcharges"] = SurchargeSerializer(
                        get_surcharges(quote), context=context, many=True
                    ).data

                result["pricings"] = json_results

            res_json = {
                "message": "",
                "data": result,
            }
            logger.info(f"#{LOG_ID} Success!")
            return Response(res_json, status=status.HTTP_200_OK)
        except Exception as e:
            logger.info(f"#{LOG_ID} Error: {e}")
            trace_error.print()
            return Response(
                {"message": "Couldn't find matching Booking."},
                status=status.HTTP_400_BAD_REQUEST,
            )

    @action(detail=False, methods=["post"], permission_classes=[AllowAny])
    def get_booking_for_confirm(self, request):
        LOG_ID = "[get_booking_for_confirm]"
        token = request.data["identifer"]
        logger.info(f"{LOG_ID} token: {token}")

        if not token or len(token.split("_")) != 2:
            logger.info(f"{LOG_ID} Error: Wrong identifier.")
            res_json = {"message": "Wrong identifier."}
            return Response(res_json, status=status.HTTP_400_BAD_REQUEST)

        dme_token = DME_Tokens.objects.get(token=token)
        if not dme_token:
            logger.info(f"{LOG_ID} Error: Wrong identifier.")
            res_json = {"message": "Wrong identifier."}
            return Response(res_json, status=status.HTTP_400_BAD_REQUEST)

        try:
            booking_id = token.split("_")[1]
            booking = Bookings.objects.get(pk=booking_id)
            booking_lines = Booking_lines.objects.filter(
                fk_booking_id=booking.pk_booking_id, is_deleted=False
            )
            booking_lines_data = Booking_lines_data.objects.filter(
                fk_booking_id=booking.pk_booking_id
            )
            quote_set = API_booking_quotes.objects.filter(
                pk=dme_token.api_booking_quote_id
            )
            client = DME_clients.objects.get(dme_account_num=booking.kf_client_id)

            original_lines, scanned_lines = [], []
            for line in booking_lines:
                if line.packed_status == "original":
                    original_lines.append(line)
                if line.packed_status == "scanned":
                    scanned_lines.append(line)
            lines = scanned_lines or original_lines

            result = BookingSerializer(booking).data
            result["booking_lines"] = BookingLineSerializer(lines, many=True).data
            result["booking_lines_data"] = BookingLineDetailSerializer(
                booking_lines_data, many=True
            ).data

            if quote_set:
                context = {"client_customer_mark_up": client.client_customer_mark_up}
                json_results = SimpleQuoteSerializer(
                    quote_set, many=True, context=context
                ).data
                json_results = beautify_eta(json_results, quote_set, client)

                # Surcharge point
                for json_result in json_results:
                    quote = None

                    for _quote in quote_set:
                        if _quote.pk == json_result["cost_id"]:
                            quote = _quote

                    context = {"client_mark_up_percent": client.client_mark_up_percent}
                    json_result["surcharges"] = SurchargeSerializer(
                        get_surcharges(quote), context=context, many=True
                    ).data

                result["pricings"] = json_results

            res_json = {
                "message": "Succesfully confirmed!",
                "data": result,
            }
            send_email_confirmed(booking, lines, dme_token, booking.api_booking_quote)
            if booking.vx_freight_provider != dme_token.vx_freight_provider:
                res_json["message"] = "Booking selected other FP!"
            elif booking.vx_freight_provider == dme_token.vx_freight_provider:
                if booking.b_dateBookedDate:
                    message = f'Already confirmed by "{booking.vx_freight_provider}"'
                    res_json["message"] = message
                else:
                    status_history.create(
                        booking, "Booked", dme_token.vx_freight_provider
                    )
                    send_email_confirmed(
                        booking, lines, dme_token, booking.api_booking_quote
                    )

            logger.info(f"#{LOG_ID} Success!")
            return Response(res_json, status=status.HTTP_200_OK)
        except Exception as e:
            logger.info(f"#{LOG_ID} Error: {e}")
            trace_error.print()
            return Response(
                {"message": "Couldn't find matching Booking."},
                status=status.HTTP_400_BAD_REQUEST,
            )

    @action(detail=False, methods=["get"])
    def get_status(self, request, format=None):
        pk_booking_id = request.GET["pk_header_id"]
        user_id = request.user.id

        try:
            dme_employee = DME_employees.objects.filter(fk_id_user=user_id).first()

            if dme_employee is not None:
                user_type = "DME"
            else:
                user_type = "CLIENT"

            if user_type == "CLIENT":
                client_employee = Client_employees.objects.filter(
                    fk_id_user=user_id
                ).first()
                client = DME_clients.objects.get(
                    pk_id_dme_client=client_employee.fk_id_dme_client_id
                )

                if client is None:
                    return JsonResponse({"booking": {}, "nextid": 0, "previd": 0})

            try:
                booking = Bookings.objects.filter(pk_booking_id=pk_booking_id).values(
                    "b_status",
                    "v_FPBookingNumber",
                    "vx_account_code",
                    "kf_client_id",
                )

                if (
                    user_type == "CLIENT"
                    and booking.kf_client_id != client.dme_account_num
                ):
                    return JsonResponse(
                        {
                            "success": False,
                            "message": "You don't have permission to get status of this booking.",
                            "pk_header_id": pk_booking_id,
                        }
                    )

                if booking.vx_account_code:
                    quote = booking.api_booking_quote

                if booking.vx_account_code and booking.b_status == "Ready for Booking":
                    return JsonResponse(
                        {
                            "success": True,
                            "message": "Pricing is selected but not booked yet",
                            "pk_header_id": pk_booking_id,
                            "status": booking.b_status,
                            "price": {
                                "fee": quote.client_mu_1_minimum_values,
                                "tax": qutoe.mu_percentage_fuel_levy,
                            },
                        }
                    )
                elif (
                    not booking.vx_account_code
                    and booking.b_status == "Ready for Booking"
                ):
                    return JsonResponse(
                        {
                            "success": True,
                            "message": "Pricing is not selected.",
                            "pk_header_id": pk_booking_id,
                            "status": booking.b_status,
                            "price": None,
                        }
                    )
                elif booking.vx_account_code and booking.b_status == "Booked":
                    return JsonResponse(
                        {
                            "success": True,
                            "message": "Booking is booked.",
                            "pk_header_id": pk_booking_id,
                            "status": booking.b_status,
                            "price": {
                                "fee": quote.client_mu_1_minimum_values,
                                "tax": qutoe.mu_percentage_fuel_levy,
                            },
                            "connote": booking.v_FPBookingNumber,
                        }
                    )
                elif booking.vx_account_code and booking.b_status == "Closed":
                    return JsonResponse(
                        {
                            "success": True,
                            "message": "Booking is cancelled.",
                            "pk_header_id": pk_booking_id,
                            "status": booking.b_status,
                            "price": {
                                "fee": quote.client_mu_1_minimum_values,
                                "tax": qutoe.mu_percentage_fuel_levy,
                            },
                            "connote": booking.v_FPBookingNumber,
                        }
                    )
            except Bookings.DoesNotExist:
                return JsonResponse(
                    {
                        "success": False,
                        "message": "Booking is not exist with provided pk_header_id.",
                        "pk_header_id": pk_booking_id,
                    }
                )
        except Exception as e:
            return JsonResponse(
                {"success": False, "message": str(e), "pk_header_id": pk_booking_id}
            )

    @action(detail=False, methods=["post"])
    def create_booking(self, request, format=None):
        bookingData = request.data
        bookingData["b_bookingID_Visual"] = Bookings.get_new_booking_visual_id()
        bookingData["pk_booking_id"] = str(uuid.uuid1())
        bookingData["b_client_booking_ref_num"] = bookingData["pk_booking_id"]
        serializer = BookingSerializer(data=request.data)

        if serializer.is_valid():
            booking = serializer.save()
            serializer.data["id"] = booking.pk
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=["post"])
    def duplicate_booking(self, request, pk=None, format=None):
        LOG_ID = "[DUP BOOKING]"
        user_id = request.user.id
        booking = Bookings.objects.get(pk=pk)
        payload = request.data
        logger.info(
            f"{LOG_ID} Booking: {pk}({booking.b_bookingID_Visual}), Payload: {payload}"
        )
        dup_line_and_linedetail = payload.get("dupLineAndLineDetail")
        switch_info = payload.get("switchInfo")
        is_4_child = payload.get("is4Child")
        qtys_4_children = payload.get("qtys4Children")

        if switch_info:
            newBooking = {
                "puCompany": booking.deToCompanyName,
                "pu_Address_Street_1": booking.de_To_Address_Street_1,
                "pu_Address_street_2": booking.de_To_Address_Street_2,
                "pu_Address_State": booking.de_To_Address_State,
                "pu_Address_PostalCode": booking.de_To_Address_PostalCode,
                "pu_Address_Suburb": booking.de_To_Address_Suburb,
                "pu_Address_Country": booking.de_To_Address_Country,
                "pu_Contact_F_L_Name": booking.de_to_Contact_F_LName,
                "pu_Phone_Main": booking.de_to_Phone_Main,
                "pu_Email": booking.de_Email,
                "deToCompanyName": booking.puCompany,
                "de_To_Address_Street_1": booking.pu_Address_Street_1,
                "de_To_Address_Street_2": booking.pu_Address_street_2,
                "de_To_Address_State": booking.pu_Address_State,
                "de_To_Address_PostalCode": booking.pu_Address_PostalCode,
                "de_To_Address_Suburb": booking.pu_Address_Suburb,
                "de_To_Address_Country": booking.pu_Address_Country,
                "de_to_Contact_F_LName": booking.pu_Contact_F_L_Name,
                "de_to_Phone_Main": booking.pu_Phone_Main,
                "de_Email": booking.pu_Email,
                "pu_email_Group_Name": booking.de_Email_Group_Name,
                "pu_email_Group": booking.de_Email_Group_Emails,
                "de_Email_Group_Name": booking.pu_email_Group_Name,
                "de_Email_Group_Emails": booking.pu_email_Group,
                "pu_Address_Type": booking.de_To_AddressType,
                "de_To_AddressType": booking.pu_Address_Type,
                "pu_no_of_assists": booking.pu_no_of_assists,
                "de_no_of_assists": booking.de_no_of_assists,
                "pu_location": booking.pu_location,
                "de_to_location": booking.de_to_location,
                "pu_access": booking.pu_access,
                "de_access": booking.de_access,
                "pu_floor_number": booking.pu_floor_number,
                "de_floor_number": booking.de_floor_number,
                "pu_floor_access_by": booking.pu_floor_access_by,
                "de_to_floor_access_by": booking.de_to_floor_access_by,
                "pu_service": booking.pu_service,
                "de_service": booking.de_service,
            }
        else:
            newBooking = {
                "puCompany": booking.puCompany,
                "pu_Address_Street_1": booking.pu_Address_Street_1,
                "pu_Address_street_2": booking.pu_Address_street_2,
                "pu_Address_PostalCode": booking.pu_Address_PostalCode,
                "pu_Address_Suburb": booking.pu_Address_Suburb,
                "pu_Address_Country": booking.pu_Address_Country,
                "pu_Contact_F_L_Name": booking.pu_Contact_F_L_Name,
                "pu_Phone_Main": booking.pu_Phone_Main,
                "pu_Email": booking.pu_Email,
                "pu_Address_State": booking.pu_Address_State,
                "deToCompanyName": booking.deToCompanyName,
                "de_To_Address_Street_1": booking.de_To_Address_Street_1,
                "de_To_Address_Street_2": booking.de_To_Address_Street_2,
                "de_To_Address_PostalCode": booking.de_To_Address_PostalCode,
                "de_To_Address_Suburb": booking.de_To_Address_Suburb,
                "de_To_Address_Country": booking.de_To_Address_Country,
                "de_to_Contact_F_LName": booking.de_to_Contact_F_LName,
                "de_to_Phone_Main": booking.de_to_Phone_Main,
                "de_Email": booking.de_Email,
                "de_To_Address_State": booking.de_To_Address_State,
                "pu_email_Group_Name": booking.pu_email_Group_Name,
                "pu_email_Group": booking.pu_email_Group,
                "de_Email_Group_Name": booking.de_Email_Group_Name,
                "de_Email_Group_Emails": booking.de_Email_Group_Emails,
                "pu_Address_Type": booking.pu_Address_Type,
                "de_To_AddressType": booking.de_To_AddressType,
                "pu_no_of_assists": booking.de_no_of_assists,
                "de_no_of_assists": booking.pu_no_of_assists,
                "pu_location": booking.de_to_location,
                "de_to_location": booking.pu_location,
                "pu_access": booking.de_access,
                "de_access": booking.pu_access,
                "pu_floor_number": booking.de_floor_number,
                "de_floor_number": booking.pu_floor_number,
                "pu_floor_access_by": booking.de_to_floor_access_by,
                "de_to_floor_access_by": booking.pu_floor_access_by,
                "pu_service": booking.de_service,
                "de_service": booking.pu_service,
            }

        newBooking["b_bookingID_Visual"] = Bookings.get_new_booking_visual_id()
        newBooking["fk_client_warehouse"] = booking.fk_client_warehouse_id
        newBooking["b_client_warehouse_code"] = booking.b_client_warehouse_code
        newBooking["b_clientPU_Warehouse"] = booking.b_clientPU_Warehouse
        newBooking["b_client_name"] = booking.b_client_name
        newBooking["pk_booking_id"] = str(uuid.uuid1())
        # newBooking["z_lock_status"] = booking.z_lock_status
        newBooking["b_status"] = "Ready for booking"
        newBooking["vx_freight_provider"] = booking.vx_freight_provider
        newBooking["kf_client_id"] = booking.kf_client_id
        newBooking[
            "b_clientReference_RA_Numbers"
        ] = booking.b_clientReference_RA_Numbers
        newBooking["vx_serviceName"] = booking.vx_serviceName
        newBooking["z_CreatedByAccount"] = request.user.username
        newBooking["booking_type"] = booking.booking_type
        newBooking["b_client_booking_ref_num"] = newBooking["pk_booking_id"]

        if is_4_child:
            newBooking[
                "x_booking_Created_With"
            ] = f"Child of #{booking.b_bookingID_Visual}"
        else:
            newBooking[
                "x_booking_Created_With"
            ] = f"Duped from #{booking.b_bookingID_Visual}"

        if dup_line_and_linedetail or is_4_child:
            booking_lines = Booking_lines.objects.filter(
                fk_booking_id=booking.pk_booking_id
            )

            for booking_line in booking_lines:
                if qtys_4_children:
                    if (
                        str(booking_line.pk) in qtys_4_children
                        and qtys_4_children[str(booking_line.pk)]
                        and qtys_4_children[str(booking_line.pk)] > 0
                    ):
                        booking_line.e_qty = qtys_4_children[str(booking_line.pk)]
                    else:
                        continue

                booking_line.pk_lines_id = None
                booking_line.fk_booking_id = newBooking["pk_booking_id"]
                booking_line.e_qty_delivered = 0
                booking_line.e_qty_adjusted_delivered = 0
                booking_line.z_createdTimeStamp = datetime.now()
                booking_line.z_modifiedTimeStamp = None
                booking_line.picked_up_timestamp = None
                booking_line.sscc = None
                new_pk_booking_lines_id = str(uuid.uuid1())

                if booking_line.pk_booking_lines_id:
                    booking_line_details = Booking_lines_data.objects.filter(
                        fk_booking_lines_id=booking_line.pk_booking_lines_id
                    )

                    for booking_line_detail in booking_line_details:
                        booking_line_detail.pk_id_lines_data = None
                        booking_line_detail.fk_booking_id = newBooking["pk_booking_id"]
                        booking_line_detail.fk_booking_lines_id = (
                            new_pk_booking_lines_id
                        )
                        booking_line_detail.z_createdTimeStamp = datetime.now()
                        booking_line_detail.z_modifiedTimeStamp = None
                        booking_line_detail.save()

                booking_line.pk_booking_lines_id = new_pk_booking_lines_id
                booking_line.save()

        serializer = BookingSerializer(data=newBooking)
        if serializer.is_valid():
            serializer.save()

            if is_4_child:
                status_history.create(
                    booking, "Parent Booking", request.user.username, datetime.now()
                )

            logger.info(
                f"{LOG_ID} Successfully duplicated! Original: {pk}({booking.b_bookingID_Visual}) -> New: {serializer.data['id']}({serializer.data['b_bookingID_Visual']})"
            )
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=["post"])
    def tick_manual_book(self, request, format=None):
        body = literal_eval(request.body.decode("utf8"))
        id = body["id"]
        user_id = request.user.id
        dme_employees = DME_employees.objects.filter(fk_id_user=user_id)

        if not dme_employees.exists():
            user_type = "CLIENT"
            return Response(status=status.HTTP_403_FORBIDDEN)

        booking = Bookings.objects.get(id=id)

        if booking.b_dateBookedDate:
            return Response(status=status.HTTP_400_BAD_REQUEST)
        else:
            booking.x_manual_booked_flag = not booking.x_manual_booked_flag
            booking.api_booking_quote_id = None  # clear relation with Quote
            booking.save()
            serializer = BookingSerializer(booking)

            return Response(serializer.data, status=status.HTTP_200_OK)

    @action(detail=False, methods=["post"])
    def manual_book(self, request, format=None):
        LOG_ID = "[MANUAL BOOK]"
        body = literal_eval(request.body.decode("utf8"))
        id = body["id"]
        user_id = request.user.id
        dme_employees = DME_employees.objects.filter(fk_id_user=user_id)

        if not dme_employees.exists():
            user_type = "CLIENT"
            return Response(status=status.HTTP_403_FORBIDDEN)

        booking = Bookings.objects.get(id=id)

        if not booking.x_manual_booked_flag:
            return Response(status=status.HTTP_400_BAD_REQUEST)
        else:
            duplicate_line_linedata(booking)
            status_history.create(booking, "Booked", request.user.username)
            booking.b_dateBookedDate = datetime.now()
            booking.save()
            serializer = BookingSerializer(booking)

            logger.info(f"@880 {LOG_ID} Booking: {booking.b_bookingID_Visual}")

            if booking.b_client_name == "Bathroom Sales Direct":
                booking_lines = Booking_lines.objects.filter(
                    fk_booking_id=booking.pk_booking_id, is_deleted=False, packed_status="scanned"
                )
                send_email_booked(booking, booking_lines)
            return Response(serializer.data, status=status.HTTP_200_OK)

    @action(detail=True, methods=["post"])
    def cancel_book(self, request, pk, format=None):
        LOG_ID = "[CANCEL BOOK]"
        try:
            booking = Bookings.objects.get(pk=pk)
            cancel_book_oper(booking, request.user)
            return Response(
                {"success": True, "message": "Successfully Cancelled"},
                status=status.HTTP_200_OK,
            )
        except Exception as e:
            trace_error.print()
            logger.info(f"{LOG_ID} Error: {str(e)}")
            return Response({"success": False}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=["post"])
    def update_augment(self, request, format=None):
        Client_Process_Mgr.objects.filter(id=request.data["id"]).update(
            origin_puCompany=request.data["origin_puCompany"],
            origin_pu_Address_Street_1=request.data["origin_pu_Address_Street_1"],
            origin_pu_Address_Street_2=request.data["origin_pu_Address_Street_2"],
            origin_deToCompanyName=request.data["origin_deToCompanyName"],
            origin_pu_pickup_instructions_address=request.data[
                "origin_pu_pickup_instructions_address"
            ],
            origin_de_Email_Group_Emails=request.data["origin_de_Email_Group_Emails"],
        )
        return JsonResponse({"message": "Updated client successfully."})

    @action(detail=False, methods=["post"])
    def auto_augment(self, request, format=None):
        body = literal_eval(request.body.decode("utf8"))
        bookingId = body["bookingId"]
        booking = Bookings.objects.get(pk=bookingId)

        # Do now allow create new client_progress_mgr when already exist for this Booking.
        client_process = Client_Process_Mgr.objects.filter(
            fk_booking_id=bookingId
        ).first()

        if client_process:
            return JsonResponse(
                {"message": "Already Augmented!", "success": False},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Apply only "Salvage Expense" category
        if booking.b_booking_Category != "Salvage Expense":
            return JsonResponse(
                {
                    "message": "Booking Category is not Salvage Expense",
                    "success": False,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Get client_auto_augment
        dme_client = DME_clients.objects.filter(
            dme_account_num=booking.kf_client_id
        ).first()
        client_auto_augment = Client_Auto_Augment.objects.filter(
            fk_id_dme_client_id=dme_client.pk_id_dme_client,
            de_to_companyName__iexact=booking.deToCompanyName.strip(),
        ).first()

        if not client_auto_augment:
            return JsonResponse(
                {
                    "message": "This Client is not set up for auto augment",
                    "success": False,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            auto_augment_oper(booking, client_auto_augment)
            return Response({"success": True})
        except Exception as e:
            logger.error(f"@207 Auto Augment - {str(e)}")
            return JsonResponse(
                {"success": False, "message": str(e)},
                status=status.HTTP_400_BAD_REQUEST,
            )

    @action(detail=False, methods=["post"])
    def set_pu_date_augment(self, request, format=None):
        body = literal_eval(request.body.decode("utf8"))
        bookingId = body["bookingId"]
        booking = Bookings.objects.get(pk=bookingId)

        try:
            tempo_client = DME_clients.objects.get(company_name="Tempo Pty Ltd")
            sydney_now = get_sydney_now_time("datetime")

            if booking.x_ReadyStatus == "Available From":
                weekno = sydney_now.weekday()

                if weekno > 4:
                    booking.puPickUpAvailFrom_Date = (
                        sydney_now + timedelta(days=6 - weekno)
                    ).date()
                    booking.pu_PickUp_By_Date = (
                        sydney_now + timedelta(days=6 - weekno)
                    ).date()
                else:
                    booking.puPickUpAvailFrom_Date = (
                        sydney_now + timedelta(days=1)
                    ).date()
                    booking.pu_PickUp_By_Date = (sydney_now + timedelta(days=1)).date()

                booking.pu_PickUp_Avail_Time_Hours = (
                    tempo_client.augment_pu_available_time.strftime("%H")
                )
                booking.pu_PickUp_Avail_Time_Minutes = (
                    tempo_client.augment_pu_available_time.strftime("%M")
                )

                booking.pu_PickUp_By_Time_Hours = (
                    tempo_client.augment_pu_by_time.strftime("%H")
                )
                booking.pu_PickUp_By_Time_Minutes = (
                    tempo_client.augment_pu_by_time.strftime("%M")
                )
            elif booking.x_ReadyStatus == "Available Now":
                booking.puPickUpAvailFrom_Date = sydney_now.date()
                booking.pu_PickUp_By_Date = sydney_now.date()

                booking.pu_PickUp_Avail_Time_Hours = sydney_now.strftime("%H")
                booking.pu_PickUp_Avail_Time_Minutes = 0
                booking.pu_PickUp_By_Time_Hours = (
                    tempo_client.augment_pu_by_time.strftime("%H")
                )
                booking.pu_PickUp_By_Time_Minutes = (
                    tempo_client.augment_pu_by_time.strftime("%M")
                )
            else:
                booking.puPickUpAvailFrom_Date = sydney_now.date()
                booking.pu_PickUp_By_Date = sydney_now.date()

                booking.pu_PickUp_Avail_Time_Hours = (
                    tempo_client.augment_pu_available_time.strftime("%H")
                )
                booking.pu_PickUp_Avail_Time_Minutes = (
                    tempo_client.augment_pu_available_time.strftime("%M")
                )
                booking.pu_PickUp_By_Time_Hours = (
                    tempo_client.augment_pu_by_time.strftime("%H")
                )
                booking.pu_PickUp_By_Time_Minutes = (
                    tempo_client.augment_pu_by_time.strftime("%M")
                )

            booking.save()
            serializer = BookingSerializer(booking)
            return Response(serializer.data)

        except Exception as e:
            # print(str(e))
            return JsonResponse(
                {"type": "Failure", "message": str(e)},
                status=status.HTTP_400_BAD_REQUEST,
            )

    @action(detail=False, methods=["post"])
    def revert_augment(self, request, format=None):
        body = literal_eval(request.body.decode("utf8"))
        bookingId = body["bookingId"]
        booking = Bookings.objects.get(pk=bookingId)

        try:
            client_process = Client_Process_Mgr.objects.filter(
                fk_booking_id=bookingId
            ).first()
            if client_process is not None:
                booking.puCompany = client_process.origin_puCompany
                booking.pu_Address_Street_1 = client_process.origin_pu_Address_Street_1
                booking.pu_Address_street_2 = client_process.origin_pu_Address_Street_2
                booking.pu_pickup_instructions_address = (
                    client_process.origin_pu_pickup_instructions_address
                )
                booking.deToCompanyName = client_process.origin_deToCompanyName
                booking.de_Email = client_process.origin_de_Email
                booking.de_Email_Group_Emails = (
                    client_process.origin_de_Email_Group_Emails
                )
                booking.de_To_Address_Street_1 = (
                    client_process.origin_de_To_Address_Street_1
                )
                booking.de_To_Address_Street_2 = (
                    client_process.origin_de_To_Address_Street_2
                )

                client_process.delete()
                booking.save()
                serializer = BookingSerializer(booking)
                return Response(serializer.data)
            else:
                return JsonResponse(
                    {"message": "This booking is not Augmented", "type": "Failure"},
                    status=status.HTTP_400_BAD_REQUEST,
                )
        except Exception as e:
            return Response(
                {"type": "Failure", "message": "Exception occurred"},
                status=status.HTTP_400_BAD_REQUEST,
            )

    @action(detail=False, methods=["get"])
    def get_email_logs(self, request, format=None):
        booking_id = request.GET["bookingId"]

        if not booking_id:
            return JsonResponse(
                {"success": False, "message": "Booking id is required."}
            )

        email_logs = EmailLogs.objects.filter(booking_id=int(booking_id)).order_by(
            "-z_createdTimeStamp"
        )
        return JsonResponse(
            {
                "success": True,
                "results": EmailLogsSerializer(email_logs, many=True).data,
            }
        )

    @action(detail=False, methods=["get"], permission_classes=[AllowAny])
    def get_labels(self, request):
        LOG_ID = "[LABELS]"
        b_client_booking_ref_num = request.GET.get("b_client_booking_ref_num", None)
        message = f"#100 {LOG_ID}: b_client_booking_ref_num: {b_client_booking_ref_num}"
        logger.info(message)

        label_type = request.GET.get("label_type", None)
        suffix = "" if label_type == "label" else f"_{label_type}"

        if not b_client_booking_ref_num:
            message = "Wrong identifier."
            logger.info(f"#101 {LOG_ID} {message}")
            raise ValidationError({"message": message})

        booking = (
            Bookings.objects.filter(b_client_booking_ref_num=b_client_booking_ref_num)
            .only(
                "id",
                "pk_booking_id",
                "b_bookingID_Visual",
                "b_client_name",
                "b_client_order_num",
                "b_client_sales_inv_num",
                "v_FPBookingNumber",
                "vx_freight_provider",
                "z_label_url",
                "pu_Address_State",
                "x_manual_booked_flag",
                "api_booking_quote",
                "b_dateBookedDate",
                "client_sales_total",
                "is_quote_locked",
            )
            .order_by("id")
            .last()
        )

        if not booking:
            message = "Order does not exist!"
            logger.info(f"#102 {LOG_ID} {message}")
            raise ValidationError({"message": message})

        quotes = API_booking_quotes.objects.filter(
            fk_booking_id=booking.pk_booking_id, is_used=False
        ).only("id", "freight_provider", "account_code", "client_mu_1_minimum_values")
        logger.info(f"#103 {LOG_ID} BookingId: {booking.b_bookingID_Visual}")
        file_path = (
            f"{settings.STATIC_PUBLIC}/pdfs/{booking.vx_freight_provider.lower()}_au"
        )

        lines = booking.lines().only(
            "pk_lines_id",
            "pk_booking_lines_id",
            "sscc",
            "e_item",
            "e_item_type",
            "e_qty",
            "e_type_of_packaging",
        )
        line_datas = booking.line_datas().only(
            "pk_id_lines_data", "quantity", "itemDescription", "clientRefNumber"
        )

        original_lines, scanned_lines = [], []
        for line in lines:
            if line.packed_status == "original":
                original_lines.append(line)
            elif line.packed_status == "scanned":
                scanned_lines.append(line)
        lines = scanned_lines or original_lines

        sscc_arr = []
        result_with_sscc = {}

        for line in lines:
            if line.sscc and not line.sscc in sscc_arr:
                sscc_arr.append(line.sscc)

        for sscc in sscc_arr:
            result_with_sscc[str(sscc)] = []
            original_line = None
            selected_line_data = None
            label_url = None
            is_available = False

            # Auto populated lines
            for line_data in line_datas:
                if line_data.clientRefNumber != sscc:
                    continue

                for line in lines:
                    if (
                        not line.sscc
                        and line.e_item_type == line_data.modelNumber
                        and line.zbl_131_decimal_1 == line_data.itemSerialNumbers
                    ):
                        original_line = line
                        selected_line_data = line_data
                        break

                if original_line:
                    # For TNT orders, DME builds label for each SSCC
                    file_name1 = (
                        booking.pu_Address_State
                        + "_"
                        + str(booking.b_bookingID_Visual)
                        + "_"
                        + str(sscc)
                        + suffix
                        + ".pdf"
                    )
                    # Some FPs could have serveral SSCC(s) in sscc field
                    file_name2 = (
                        booking.pu_Address_State
                        + "_"
                        + str(booking.b_bookingID_Visual)
                        + "_"
                        + str(original_line.pk_lines_id)
                        + suffix
                        + ".pdf"
                    )

                    if doesFileExist(file_path, file_name1):
                        is_available = doesFileExist(file_path, file_name1)
                        file_name = file_name1
                    elif doesFileExist(file_path, file_name2):
                        is_available = doesFileExist(file_path, file_name2)
                        file_name = file_name2

                    label_url = f"{booking.vx_freight_provider.lower()}_au/{file_name}"

                    try:
                        with open(f"{file_path}/{file_name}", "rb") as file:
                            pdf_data = str(b64encode(file.read()))[2:-1]
                    except:
                        pdf_data = ""

                    result_with_sscc[str(sscc)].append(
                        {
                            "pk_lines_id": original_line.pk_lines_id,
                            "sscc": sscc,
                            "e_item": original_line.e_item,
                            "e_item_type": original_line.e_item_type,
                            "e_qty": selected_line_data.quantity
                            if selected_line_data
                            else original_line.e_qty,
                            "e_type_of_packaging": original_line.e_type_of_packaging,
                            "is_available": is_available,
                            "url": label_url,
                            "pdf": pdf_data,
                        }
                    )

            # Manually populated lines
            if not original_line:
                for line in lines:
                    if line.sscc == sscc:
                        original_line = line
                        break

                # For TNT orders, DME builds label for each SSCC
                file_name1 = (
                    booking.pu_Address_State
                    + "_"
                    + str(booking.b_bookingID_Visual)
                    + "_"
                    + str(sscc)
                    + suffix
                    + ".pdf"
                )
                # Some FPs could have serveral SSCC(s) in sscc field
                file_name2 = (
                    booking.pu_Address_State
                    + "_"
                    + str(booking.b_bookingID_Visual)
                    + "_"
                    + str(original_line.pk_lines_id)
                    + suffix
                    + ".pdf"
                )

                if doesFileExist(file_path, file_name1):
                    is_available = doesFileExist(file_path, file_name1)
                    file_name = file_name1
                elif doesFileExist(file_path, file_name2):
                    is_available = doesFileExist(file_path, file_name2)
                    file_name = file_name2
                else:
                    message = f"{label_type.capitalize()} does not exist!"
                    logger.info(
                        f"#102 {LOG_ID} {message}\nPath #1:{file_path}, {file_name1}\nPath #2: {file_path}, {file_name2}"
                    )
                    # raise ValidationError({"message": message})
                    continue

                is_available = doesFileExist(file_path, file_name)
                label_url = f"{booking.vx_freight_provider.lower()}_au/{file_name}"

                try:
                    with open(f"{file_path}/{file_name}", "rb") as file:
                        pdf_data = str(b64encode(file.read()))[2:-1]
                except:
                    pdf_data = ""

                result_with_sscc[str(sscc)].append(
                    {
                        "pk_lines_id": original_line.pk_lines_id,
                        "sscc": sscc,
                        "e_item": original_line.e_item,
                        "e_item_type": original_line.e_item_type,
                        "e_qty": selected_line_data.quantity
                        if selected_line_data
                        else original_line.e_qty,
                        "e_type_of_packaging": original_line.e_type_of_packaging,
                        "is_available": is_available,
                        "url": label_url,
                        "pdf": pdf_data,
                    }
                )

        # Full PDF
        full_label_name = ""
        try:
            pdf_data = None
            file_name = f"DME{booking.b_bookingID_Visual}{suffix}.pdf"

            try:
                with open(f"{file_path}/{file_name}", "rb") as file:
                    pdf_data = str(b64encode(file.read()))[2:-1]
            except:
                pdf_data = ""

            full_label_name = f"{booking.vx_freight_provider.lower()}_au/{file_name}"
        except:
            full_label_name = ""
            pass

        # Cheapest quote
        quote_json = {}
        scanned_quotes = []
        cheapest_quote = None

        for quote in quotes:
            if quote.packed_status == Booking_lines.SCANNED_PACK:
                scanned_quotes.append(quote)

        if scanned_quotes:
            cheapest_quote = booking.api_booking_quote or scanned_quotes[0]
            original_quote = None
            scanned_quote = None

            for quote in quotes:
                if (
                    quote.packed_status == Booking_lines.ORIGINAL
                    and quote.client_mu_1_minimum_values == booking.inv_sell_quoted
                ):
                    original_quote = quote

                if (
                    quote.packed_status == Booking_lines.SCANNED_PACK
                    and quote.client_mu_1_minimum_values == booking.inv_booked_quoted
                ):
                    scanned_quote = quote

            for quote in scanned_quotes:
                if (
                    quote.client_mu_1_minimum_values
                    < cheapest_quote.client_mu_1_minimum_values
                ):
                    cheapest_quote = quote

            if (
                booking.api_booking_quote
                and cheapest_quote != booking.api_booking_quote
            ):
                quote_json = {
                    "cheapest": {
                        "id": cheapest_quote.pk,
                        "fp": cheapest_quote.freight_provider,
                        "cost_dollar": cheapest_quote.client_mu_1_minimum_values,
                        "savings": booking.api_booking_quote.client_mu_1_minimum_values
                        - cheapest_quote.client_mu_1_minimum_values,
                    }
                }

                if original_quote:
                    quote_json["original"] = {
                        "fp": original_quote.freight_provider,
                        "cost_dollar": original_quote.client_mu_1_minimum_values,
                    }

                if scanned_quote:
                    quote_json["scanned"] = {
                        "fp": scanned_quote.freight_provider,
                        "cost_dollar": scanned_quote.client_mu_1_minimum_values,
                    }

        result = {
            "id": booking.pk,
            "pk_booking_id": booking.pk_booking_id,
            "b_bookingID_Visual": booking.b_bookingID_Visual,
            "b_client_name": booking.b_client_name,
            "b_client_order_num": booking.b_client_order_num,
            "b_client_sales_inv_num": booking.b_client_sales_inv_num,
            "v_FPBookingNumber": booking.v_FPBookingNumber,
            "vx_freight_provider": booking.vx_freight_provider,
            "x_manual_booked_flag": booking.x_manual_booked_flag,
            "api_booking_quote_id": booking.api_booking_quote_id,
            "b_dateBookedDate": booking.b_dateBookedDate,
            "client_sales_total": booking.client_sales_total,
            "no_of_sscc": len(result_with_sscc),
            "url": booking.z_label_url,
            "pdf": pdf_data,
            "full_label_name": full_label_name,
            "sscc_obj": result_with_sscc,
            "quotes_cnt": quotes.count(),
            "quote": quote_json,
        }

        return JsonResponse({"success": True, "result": result})

    @action(detail=False, methods=["get"], permission_classes=[AllowAny])
    def get_labels_bookings(self, request):
        LOG_ID = "[LABELS]"
        bookingSet = BookingSets.objects.get(pk=request.GET.get("id"))
        message = f"#100 {LOG_ID}: ids: {bookingSet.booking_ids}"
        logger.info(message)
        sort_by = request.GET.get("sort_by")
        is_shipping_label = request.GET.get("is_shipping_label")
        label_type = request.GET.get("label_type", None)

        if not bookingSet:
            message = "Wrong identifier."
            logger.info(f"#101 {LOG_ID} {message}")
            raise ValidationError({"message": message})
        if (
            sort_by != "product_name"
            and sort_by != "bin_number"
            and sort_by != "group"
            and sort_by != "order_number"
        ):
            message = "Wrong Sort_by."
            logger.info(f"#101 {LOG_ID} {message}")
            raise ValidationError({"message": message})

        basePath = f"{settings.STATIC_PUBLIC}/pdfs"
        bookingSetFilepath = f"bookingSets/{bookingSet.id}"

        for fp_name in ["Direct Freight", "Team Global Express"]:
            if not os.path.exists(f"{basePath}/{bookingSetFilepath}/items_{sort_by}_{fp_name}"):
                os.makedirs(f"{basePath}/{bookingSetFilepath}/items_{sort_by}_{fp_name}")

        bookings = (
            Bookings.objects.filter(id__in=bookingSet.booking_ids.split(","))
            .only(
                "id",
                "pk_booking_id",
                "b_bookingID_Visual",
                "b_client_name",
                "b_client_order_num",
                "b_client_sales_inv_num",
                "v_FPBookingNumber",
                "vx_freight_provider",
                "z_label_url",
                "pu_Address_State",
                "x_manual_booked_flag",
                "api_booking_quote",
                "b_dateBookedDate",
                "client_sales_total",
                "is_quote_locked",
                "kf_client_id",
            )
            .order_by("vx_freight_provider", "id")
        )

        results = []
        resultsBookingSet = {"name": bookingSet.name, "items": {"Direct Freight": {}, "Team Global Express": {}}}
        itemsUrls = {"Direct Freight": {}, "Team Global Express": {}}
        if sort_by == "group":
            resultsBookingSet = {
                "name": bookingSet.name,
                "items": {"Direct Freight": {"CARTON": {}, "NONE": {}}, "Team Global Express": {"CARTON": {}, "NONE": {}}},
            }
            itemsUrls = {"Direct Freight": {"CARTON": {}, "NONE": {}}, "Team Global Express": {"CARTON": {}, "NONE": {}}}

        pk_booking_ids = []

        for booking in bookings:
            pk_booking_ids.append(booking.pk_booking_id)

        quotes = API_booking_quotes.objects.filter(
            fk_booking_id__in=pk_booking_ids, is_used=False
        ).only("id", "freight_provider", "account_code", "client_mu_1_minimum_values")

        lines_list = Booking_lines.objects.filter(
            fk_booking_id__in=pk_booking_ids
        ).only(
            "pk_lines_id",
            "pk_booking_lines_id",
            "sscc",
            "e_item",
            "e_item_type",
            "e_bin_number",
            "e_qty",
            "e_dimUOM",
            "e_weightUOM",
            "e_weightPerEach",
            "e_dimLength",
            "e_dimWidth",
            "e_dimHeight",
            "e_type_of_packaging",
        )
        line_datas_list = Booking_lines_data.objects.filter(
            fk_booking_id__in=pk_booking_ids
        ).only("pk_id_lines_data", "quantity", "itemDescription", "clientRefNumber")

        for booking in bookings:
            fp_name = booking.vx_freight_provider
            if not booking:
                message = "Order does not exist!"
                logger.info(f"#102 {LOG_ID} {message}")
                raise ValidationError({"message": message})

            quotes_cnt = 0
            for quote in quotes:
                if quote.fk_booking_id == booking.pk_booking_id:
                    quotes_cnt += 1

            logger.info(f"#103 {LOG_ID} BookingId: {booking.b_bookingID_Visual}")
            file_path = f"{basePath}/{booking.vx_freight_provider.lower()}_au"

            # Aberdeen Paper
            if (
                booking.kf_client_id == "4ac9d3ee-2558-4475-bdbb-9d9405279e81"
                and is_shipping_label == "0"
            ):
                file_path = f"{basePath}/carton_au"

            lines = []
            for line in lines_list:
                if line.fk_booking_id == booking.pk_booking_id:
                    lines.append(line)

            line_datas = []
            for line_data in line_datas_list:
                if line_data.fk_booking_id == booking.pk_booking_id:
                    line_datas.append(line_data)

            sscc_arr = []
            result_with_sscc = {}

            for line in lines:
                if line.sscc and not line.sscc in sscc_arr:
                    sscc_arr.append(line.sscc)

            for sscc in sscc_arr:
                result_with_sscc[str(sscc)] = []
                original_line = None
                selected_line_data = None
                label_url = None
                is_available = False

                # Auto populated lines
                for line_data in line_datas:
                    if line_data.clientRefNumber != sscc:
                        continue

                    for line in lines:
                        if (
                            not line.sscc
                            and line.e_item_type == line_data.modelNumber
                            and line.zbl_131_decimal_1 == line_data.itemSerialNumbers
                        ):
                            original_line = line
                            selected_line_data = line_data
                            break

                    if original_line:
                        # For TNT orders, DME builds label for each SSCC
                        file_name1 = (
                            booking.pu_Address_State
                            + "_"
                            + str(booking.b_bookingID_Visual)
                            + "_"
                            + str(sscc)
                            + ("_consignment" if label_type == "consignment" else "")
                            + ".pdf"
                        )
                        # Some FPs could have serveral SSCC(s) in sscc field
                        file_name2 = (
                            booking.pu_Address_State
                            + "_"
                            + str(booking.b_bookingID_Visual)
                            + "_"
                            + str(original_line.pk_lines_id)
                            + ("_consignment" if label_type == "consignment" else "")
                            + ".pdf"
                        )

                        if doesFileExist(file_path, file_name1):
                            is_available = doesFileExist(file_path, file_name1)
                            file_name = file_name1
                        elif doesFileExist(file_path, file_name2):
                            is_available = doesFileExist(file_path, file_name2)
                            file_name = file_name2
                        else:
                            continue

                        label_url = (
                            f"{booking.vx_freight_provider.lower()}_au/{file_name}"
                        )

                        # Aberdeen Paper
                        if (
                            booking.kf_client_id
                            == "4ac9d3ee-2558-4475-bdbb-9d9405279e81"
                            and is_shipping_label == "0"
                        ):
                            label_url = f"carton_au/{file_name}"

                        # try:
                        #     with open(f"{file_path}/{file_name}", "rb") as file:
                        #         pdf_data = str(b64encode(file.read()))[2:-1]
                        # except:
                        #     pdf_data = ""

                        result_with_sscc[str(sscc)].append(
                            {
                                "pk_lines_id": original_line.pk_lines_id,
                                "sscc": sscc,
                                "e_item": original_line.e_item,
                                "e_item_type": original_line.e_item_type,
                                "e_bin_number": original_line.e_bin_number,
                                "e_dimUOM": original_line.e_dimUOM,
                                "e_weightUOM": original_line.e_weightUOM,
                                "e_weightPerEach": original_line.e_weightPerEach,
                                "e_dimLength": original_line.e_dimLength,
                                "e_dimWidth": original_line.e_dimWidth,
                                "e_dimHeight": original_line.e_dimHeight,
                                "e_qty": selected_line_data.quantity
                                if selected_line_data
                                else original_line.e_qty,
                                "e_type_of_packaging": original_line.e_type_of_packaging,
                                "is_available": is_available,
                                "url": label_url,
                                # "pdf": pdf_data,
                            }
                        )

                # Manually populated lines
                if not original_line:
                    for line in lines:
                        if line.sscc == sscc:
                            original_line = line
                            break

                    # For TNT orders, DME builds label for each SSCC
                    file_name1 = (
                        booking.pu_Address_State
                        + "_"
                        + str(booking.b_bookingID_Visual)
                        + "_"
                        + str(sscc)
                        + ("_consignment" if label_type == "consignment" else "")
                        + ".pdf"
                    )
                    # Some FPs could have serveral SSCC(s) in sscc field
                    file_name2 = (
                        booking.pu_Address_State
                        + "_"
                        + str(booking.b_bookingID_Visual)
                        + "_"
                        + str(original_line.pk_lines_id)
                        + ("_consignment" if label_type == "consignment" else "")
                        + ".pdf"
                    )

                    if doesFileExist(file_path, file_name1):
                        is_available = doesFileExist(file_path, file_name1)
                        file_name = file_name1
                    elif doesFileExist(file_path, file_name2):
                        is_available = doesFileExist(file_path, file_name2)
                        file_name = file_name2
                    else:
                        continue

                    label_url = f"{booking.vx_freight_provider.lower()}_au/{file_name}"

                    # Aberdeen Paper
                    if (
                        booking.kf_client_id == "4ac9d3ee-2558-4475-bdbb-9d9405279e81"
                        and is_shipping_label == "0"
                    ):
                        label_url = f"carton_au/{file_name}"

                    # try:
                    #     with open(f"{file_path}/{file_name}", "rb") as file:
                    #         pdf_data = str(b64encode(file.read()))[2:-1]
                    # except:
                    #     pdf_data = ""

                    item_url = f"{file_path}/{file_name}"

                    # Aberdeen Paper & TGE I&S label
                    if (
                        booking.kf_client_id == "4ac9d3ee-2558-4475-bdbb-9d9405279e81"
                        and booking.vx_freight_provider.lower() == "team global express"
                        and is_pallet(lines[0].e_type_of_packaging)
                    ):
                        item_url = pdf.rotate_and_shrink_pdf(item_url)

                    result_with_sscc[str(sscc)].append(
                        {
                            "pk_lines_id": original_line.pk_lines_id,
                            "sscc": sscc,
                            "e_item": original_line.e_item,
                            "e_item_type": original_line.e_item_type,
                            "e_bin_number": original_line.e_bin_number,
                            "e_dimUOM": original_line.e_dimUOM,
                            "e_weightUOM": original_line.e_weightUOM,
                            "e_weightPerEach": original_line.e_weightPerEach,
                            "e_dimLength": original_line.e_dimLength,
                            "e_dimWidth": original_line.e_dimWidth,
                            "e_dimHeight": original_line.e_dimHeight,
                            "e_qty": selected_line_data.quantity
                            if selected_line_data
                            else original_line.e_qty,
                            "e_type_of_packaging": original_line.e_type_of_packaging,
                            "is_available": is_available,
                            "url": label_url,
                            # "pdf": pdf_data,
                        }
                    )
                if is_available:
                    if sort_by == "product_name":
                        if line.e_item not in resultsBookingSet["items"][fp_name]:
                            resultsBookingSet["items"][fp_name][line.e_item] = {
                                "url": f"{bookingSetFilepath}/items_{sort_by}_{fp_name}/{line.e_item.replace('/', '_')}.pdf"
                            }
                        if line.e_item not in itemsUrls[fp_name]:
                            itemsUrls[fp_name][line.e_item] = [item_url]
                        else:
                            itemsUrls[fp_name][line.e_item].append(item_url)
                    elif sort_by == "bin_number":
                        if line.e_bin_number:
                            if line.e_bin_number not in resultsBookingSet["items"][fp_name]:
                                resultsBookingSet["items"][fp_name][line.e_bin_number] = {
                                    "url": f"{bookingSetFilepath}/items_{sort_by}_{fp_name}/{line.e_bin_number.replace('/', '_')}.pdf"
                                }
                            if line.e_bin_number not in itemsUrls[fp_name]:
                                itemsUrls[fp_name][line.e_bin_number] = [item_url]
                            else:
                                itemsUrls[fp_name][line.e_bin_number].append(item_url)
                    elif sort_by == "group":
                        if line.e_bin_number:
                            carton_type = (
                                "CARTON"
                                if is_carton(line.e_type_of_packaging)
                                else "NONE"
                            )
                            if (
                                line.e_bin_number
                                not in resultsBookingSet["items"][fp_name][carton_type]
                            ):
                                resultsBookingSet["items"][fp_name][carton_type][
                                    line.e_bin_number
                                ] = {
                                    "url": f"{bookingSetFilepath}/items_{sort_by}_{fp_name}/{carton_type}_{line.e_bin_number.replace('/', '_')}.pdf"
                                }
                            if line.e_bin_number not in itemsUrls[fp_name][carton_type]:
                                itemsUrls[fp_name][carton_type][line.e_bin_number] = [item_url]
                            else:
                                itemsUrls[fp_name][carton_type][line.e_bin_number].append(item_url)
                    else:
                        if booking.b_client_order_num:
                            if (
                                booking.b_client_order_num
                                not in resultsBookingSet["items"][fp_name]
                            ):
                                resultsBookingSet["items"][fp_name][
                                    booking.b_client_order_num
                                ] = {
                                    "url": f"{bookingSetFilepath}/items_{sort_by}_{fp_name}/{booking.b_client_order_num.replace('/', '_')}.pdf"
                                }
                            if booking.b_client_order_num not in itemsUrls[fp_name]:
                                itemsUrls[fp_name][booking.b_client_order_num] = [item_url]
                            else:
                                itemsUrls[fp_name][booking.b_client_order_num].append(item_url)

            # Full order PDF
            # full_label_name = ""
            # try:
            #     file_name = f"DME{booking.b_bookingID_Visual}.pdf"
            #     pdf_data = None

            #     try:
            #         with open(f"{file_path}/{file_name}", "rb") as file:
            #             pdf_data = str(b64encode(file.read()))[2:-1]
            #     except:
            #         pdf_data = ""

            #     full_label_name = (
            #         f"{booking.vx_freight_provider.lower()}_au/{file_name}"
            #     )
            # except:
            #     full_label_name = ""
            #     pass

            # Full order PDF

            file_name = f"DME{booking.b_bookingID_Visual}{'_consignment' if label_type == 'consignment' else ''}.pdf"

            full_label_name = f"{booking.vx_freight_provider.lower()}_au/{file_name}"

            result = {
                "id": booking.pk,
                "pk_booking_id": booking.pk_booking_id,
                "b_bookingID_Visual": booking.b_bookingID_Visual,
                "b_client_name": booking.b_client_name,
                "b_client_order_num": booking.b_client_order_num,
                "b_client_sales_inv_num": booking.b_client_sales_inv_num,
                "v_FPBookingNumber": booking.v_FPBookingNumber,
                "vx_freight_provider": booking.vx_freight_provider,
                "x_manual_booked_flag": booking.x_manual_booked_flag,
                "api_booking_quote_id": booking.api_booking_quote_id,
                "b_dateBookedDate": booking.b_dateBookedDate,
                "client_sales_total": booking.client_sales_total,
                "no_of_sscc": len(result_with_sscc),
                "url": booking.z_label_url,
                # "pdf": pdf_data,
                "full_label_name": full_label_name,
                "sscc_obj": result_with_sscc,
                "quotes_cnt": quotes_cnt,
            }
            results.append(result)

        resultsBookingSet["url"] = f"{bookingSetFilepath}/all_{sort_by}.pdf"
        bookingSetUrls = []
        for fp_name in ["Direct Freight", "Team Global Express"]:
            if sort_by == "group":
                for item in sorted(resultsBookingSet["items"][fp_name]["CARTON"]):
                    if len(itemsUrls[fp_name]["CARTON"][item]) == 1:
                        resultsBookingSet["items"][fp_name]["CARTON"][item]["url"] = itemsUrls[fp_name][
                            "CARTON"
                        ][item][0].replace(f"{basePath}/", "")
                    else:
                        pdf_merge(
                            itemsUrls[fp_name]["CARTON"][item],
                            f"{basePath}/{resultsBookingSet['items'][fp_name]['CARTON'][item]['url']}",
                        )
                    bookingSetUrls.append(
                        f"{basePath}/{resultsBookingSet['items'][fp_name]['CARTON'][item]['url']}"
                    )
                for item in sorted(resultsBookingSet["items"][fp_name]["NONE"]):
                    if len(itemsUrls[fp_name]["NONE"][item]) == 1:
                        resultsBookingSet["items"][fp_name]["NONE"][item]["url"] = itemsUrls[fp_name]["NONE"][
                            item
                        ][0].replace(f"{basePath}/", "")
                    else:
                        pdf_merge(
                            itemsUrls[fp_name]["NONE"][item],
                            f"{basePath}/{resultsBookingSet['items'][fp_name]['NONE'][item]['url']}",
                        )
                    bookingSetUrls.append(
                        f"{basePath}/{resultsBookingSet['items'][fp_name]['NONE'][item]['url']}"
                    )
            else:
                for item in sorted(resultsBookingSet["items"][fp_name]):
                    if len(itemsUrls[fp_name][item]) == 1:
                        resultsBookingSet["items"][fp_name][item]["url"] = itemsUrls[fp_name][item][
                            0
                        ].replace(f"{basePath}/", "")
                    else:
                        pdf_merge(
                            itemsUrls[fp_name][item],
                            f"{basePath}/{resultsBookingSet['items'][fp_name][item]['url']}",
                        )
                    bookingSetUrls.append(
                        f"{basePath}/{resultsBookingSet['items'][fp_name][item]['url']}"
                    )
            # try:
            #     resultsBookingSet["items"][item]["pdf"] = None

            #     try:
            #         with open(
            #             f"{basePath}/{resultsBookingSet['items'][item]['url']}", "rb"
            #         ) as file:
            #             resultsBookingSet["items"][item]["pdf"] = str(
            #                 b64encode(file.read())
            #             )[2:-1]
            #     except:
            #         resultsBookingSet["items"][item]["pdf"] = ""
            # except:
            #     pass
        if len(bookingSetUrls) == 1:
            resultsBookingSet["url"] = bookingSetUrls[0].replace(f"{basePath}/", "")
        else:
            pdf_merge(bookingSetUrls, f"{basePath}/{resultsBookingSet['url']}")

        # Full PDF
        # try:
        #     resultsBookingSet["pdf"] = None

        #     try:
        #         with open(f"{basePath}/{resultsBookingSet['url']}", "rb") as file:
        #             resultsBookingSet["pdf"] = str(b64encode(file.read()))[2:-1]
        #     except:
        #         resultsBookingSet["pdf"] = ""
        # except:
        #     pass
        return JsonResponse(
            {
                "success": True,
                "result": {"bookings": results, "bookingSet": resultsBookingSet},
            }
        )

    @action(detail=True, methods=["post"])
    def repack(self, request, pk, format=None):
        LOG_ID = "[REPACK LINES]"
        body = literal_eval(request.body.decode("utf8"))
        repack_status = body["repackStatus"]
        # logger.info(f"@200 {LOG_ID}, BookingPk: {pk}, Repack Status: {repack_status}")

        try:
            booking = Bookings.objects.get(pk=pk)

            if repack_status and repack_status[0] == "-":
                booking_reset_repack(booking, repack_status[1:])
            elif repack_status == "auto":
                booking_auto_repack(booking, repack_status)
            else:
                booking_manual_repack(booking, repack_status)

            return JsonResponse({"success": True})
        except Exception as e:
            trace_error.print()
            logger.error(f"@204 {LOG_ID} Error: {str(e)}")
            return JsonResponse({"success": False}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=["get"], permission_classes=[AllowAny])
    def get_status_page_url(self, request):
        LOG_ID = "[get_status_page_url]"
        v_FPBookingNumber = request.GET.get("v_FPBookingNumber", None)
        logger.info(f"{LOG_ID} v_FPBookingNumber: {v_FPBookingNumber}")

        if v_FPBookingNumber:
            bookings = Bookings.objects.filter(
                v_FPBookingNumber__iexact=v_FPBookingNumber
            )

            if bookings:
                booking = bookings.first()

                if not booking.b_client_booking_ref_num:
                    booking.b_client_booking_ref_num = (
                        f"{booking.b_bookingID_Visual}_{booking.pk_booking_id}"
                    )
                    booking.save()

                status_page_url = f"{settings.WEB_SITE_URL}/status/{booking.b_client_booking_ref_num}/"
                return JsonResponse({"success": True, "statusPageUrl": status_page_url})

        logger.error(f"{LOG_ID} Failed to find status page url")
        return JsonResponse({"success": False}, status=status.HTTP_400_BAD_REQUEST)


class BookingLinesViewSet(viewsets.ViewSet):
    serializer_class = BookingLineSerializer

    @action(detail=False, methods=["get"])
    def get_booking_lines(self, request, format=None):
        pk_booking_id = request.GET["pk_booking_id"]
        booking_lines = Booking_lines.objects.filter(is_deleted=False)

        if pk_booking_id != "undefined":
            booking_lines = booking_lines.filter(fk_booking_id=pk_booking_id)

        result = BookingLineSerializer(booking_lines, many=True).data

        for booking_line in result:
            booking_line["is_scanned"] = False

        return JsonResponse({"booking_lines": result})

    @action(detail=False, methods=["get"])
    def get_lines_bulk(self, request, format=None):
        if settings.ENV == "local":
            t.sleep(1)

        booking_ids = request.GET["booking_ids"].split(",")
        bookings = Bookings.objects.filter(id__in=booking_ids).only(
            "id",
            "b_bookingID_Visual",
            "pk_booking_id",
            "b_client_name",
            "b_client_order_num",
        )
        pk_booking_ids = [booking.pk_booking_id for booking in bookings]
        lines = Booking_lines.objects.filter(fk_booking_id__in=pk_booking_ids)

        lines_json = SimpleBookingLineSerializer(lines, many=True).data
        for line in lines_json:
            for booking in bookings:
                if line["fk_booking_id"] == booking.pk_booking_id:
                    line["b_bookingID_Visual"] = booking.b_bookingID_Visual
                    line["b_client_order_num"] = booking.b_client_order_num
                    line["deToCompanyName"] = booking.deToCompanyName

        return JsonResponse({"results": lines_json})

    @action(detail=False, methods=["post"])
    def edit_lines_bulk(self, request, format=None):
        LOG_ID = "[EDIT LINES BULK]"
        if settings.ENV == "local":
            t.sleep(1)

        lines_json = request.data["bookingLines"]
        order_nums = []
        pk_lines_ids = []
        for line_json in lines_json:
            order_nums.append(line_json["b_client_order_num"])
            pk_lines_ids.append(line_json["pk_lines_id"])

        bookings = Bookings.objects.filter(b_client_order_num__in=order_nums).only(
            "id", "pk_booking_id", "b_bookingID_Visual", "b_client_order_num"
        )
        lines = Booking_lines.objects.filter(pk_lines_id__in=pk_lines_ids)

        new_lines = []
        for line_json in lines_json:
            if "isNew" in line_json:
                for booking in bookings:
                    if line_json["b_client_order_num"] == booking.b_client_order_num:
                        line_json["fk_booking_id"] = booking.pk_booking_id

                try:
                    del line_json["isNew"]
                    del line_json["isUpdated"]
                    del line_json["b_bookingID_Visual"]
                    del line_json["b_client_order_num"]
                except Exception as e:
                    pass

                line_json["pk_lines_id"] = None
                line_json["pk_booking_lines_id"] = str(uuid.uuid4())
                serializer = SimpleBookingLineSerializer(data=line_json)
                if serializer.is_valid():
                    new_line = serializer.save()
                    new_lines.append(new_line)
                    logger.info(f"{LOG_ID} Created: {new_line.pk_lines_id}")
                else:
                    logger.info(
                        f"{LOG_ID} Create failture\nData: {line_json}\nErrors: {serializer.errors}"
                    )
            elif "isUpdated" in line_json:
                current_line = None
                for line in lines:
                    if line.pk_lines_id == line_json["pk_lines_id"]:
                        current_line = line

                try:
                    del line_json["isUpdated"]
                    del line_json["b_bookingID_Visual"]
                    del line_json["b_client_order_num"]
                except Exception as e:
                    pass

                serializer = SimpleBookingLineSerializer(current_line, data=line_json)
                if serializer.is_valid():
                    updated_line = serializer.save()
                    new_lines.append(updated_line)
                    logger.info(f"{LOG_ID} Updated: {updated_line.pk_lines_id}")
                else:
                    logger.info(
                        f"{LOG_ID} Update failture\nData: {line_json}\nErrors: {serializer.errors}"
                    )
            else:
                current_line = None
                for line in lines:
                    if line.pk_lines_id == line_json["pk_lines_id"]:
                        current_line = line
                        new_lines.append(current_line)

        new_lines_json = SimpleBookingLineSerializer(new_lines, many=True).data
        for line in new_lines_json:
            for booking in bookings:
                if line["fk_booking_id"] == booking.pk_booking_id:
                    line["b_bookingID_Visual"] = booking.b_bookingID_Visual
                    line["b_client_order_num"] = booking.b_client_order_num

        return JsonResponse({"results": new_lines_json})

    @action(detail=False, methods=["get"])
    def get_count(self, request, format=None):
        booking_ids = request.GET["bookingIds"].split(",")
        bookings = Bookings.objects.filter(id__in=booking_ids)

        count = 0
        for booking in bookings:
            booking_lines = Booking_lines.objects.filter(
                fk_booking_id=booking.pk_booking_id
            )

            for booking_line in booking_lines:
                count = count + booking_line.e_qty

        return JsonResponse({"count": count})

    @action(detail=False, methods=["post"])
    def create_booking_line(self, request, format=None):
        request.data["pk_booking_lines_id"] = str(uuid.uuid1())
        serializer = BookingLineSerializer(data=request.data)

        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=["post"])
    def duplicate_booking_line(self, request, format=None):
        booking_line = Booking_lines.objects.get(pk=request.data["pk_lines_id"])
        newbooking_line = {
            "fk_booking_id": booking_line.fk_booking_id,
            "pk_booking_lines_id": str(uuid.uuid1()),
            "e_type_of_packaging": booking_line.e_type_of_packaging,
            "e_item": booking_line.e_item,
            "e_qty": booking_line.e_qty,
            "e_weightUOM": booking_line.e_weightUOM,
            "e_weightPerEach": booking_line.e_weightPerEach,
            "e_dimUOM": booking_line.e_dimUOM,
            "e_dimLength": booking_line.e_dimLength,
            "e_dimWidth": booking_line.e_dimWidth,
            "e_dimHeight": booking_line.e_dimHeight,
            "e_Total_KG_weight": booking_line.e_Total_KG_weight,
            "e_1_Total_dimCubicMeter": booking_line.e_1_Total_dimCubicMeter,
            "total_2_cubic_mass_factor_calc": booking_line.total_2_cubic_mass_factor_calc,
            "z_createdTimeStamp": datetime.now(),
            "z_modifiedTimeStamp": None,
            "packed_status": booking_line.packed_status,
        }
        serializer = BookingLineSerializer(data=newbooking_line)

        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=["put"])
    def update_booking_line(self, request, pk, format=None):
        booking_line = Booking_lines.objects.get(pk=pk)
        serializer = BookingLineSerializer(booking_line, data=request.data)

        try:
            if serializer.is_valid():
                serializer.save()
                return Response(serializer.data)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            trace_error.print()
            logger.error("Exception: ", e)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=["delete"])
    def delete_booking_line(self, request, pk, format=None):
        booking_line = Booking_lines.objects.get(pk=pk)

        try:
            # Delete related line_data
            line_datas = Booking_lines_data.objects.filter(
                fk_booking_lines_id=booking_line.pk_booking_lines_id
            )

            if line_datas.exists():
                line_datas.delete()

            booking_line.is_deleted = True
            booking_line.save()
            return JsonResponse({}, status=status.HTTP_204_NO_CONTENT)
        except Exception as e:
            trace_error.print()
            logger.error(f"#330 - booking line delete: {str(e)}")
            return JsonResponse({"error": "Can not delete BookingLine"})

    @action(detail=False, methods=["delete"])
    def delete_booking_lines(self, request, format=None):
        ids = request.data["lineIds"]
        booking_lines = Booking_lines.objects.filter(pk__in=ids)

        try:
            pk_booking_lines_ids = []
            for line in booking_lines:
                pk_booking_lines_ids.append(line.pk_booking_lines_id)

            # Delete related line_data
            Booking_lines_data.objects.filter(
                fk_booking_lines_id__in=pk_booking_lines_ids
            ).delete()

            booking_lines.update(is_deleted=True)
            return JsonResponse({}, status=status.HTTP_204_NO_CONTENT)
        except Exception as e:
            trace_error.print()
            logger.error(f"#330 - lines delete: {str(e)}")
            return JsonResponse({"error": "Can not delete BookingLines"})

    @action(detail=False, methods=["post"])
    def calc_collected(self, request, format=None):
        ids = request.data["ids"]
        type = request.data["type"]

        try:
            for id in ids:
                booking_line = Booking_lines.objects.get(pk_lines_id=id)

                if type == "Calc":
                    if not booking_line.e_qty:
                        booking_line.e_qty = 0
                    if not booking_line.e_qty_awaiting_inventory:
                        booking_line.e_qty_awaiting_inventory = 0

                    booking_line.e_qty_collected = int(booking_line.e_qty) - int(
                        booking_line.e_qty_awaiting_inventory
                    )
                    booking_line.save()
                elif type == "Clear":
                    booking_line.e_qty_collected = 0
                    booking_line.save()
            return JsonResponse(
                {"success": "All bookings e_qty_collected has been calculated"}
            )
        except Exception as e:
            # print("Exception: ", e)
            return JsonResponse({"error": "Got error, please contact support center"})


class BookingLineDetailsViewSet(viewsets.ViewSet):
    serializer_class = BookingLineDetailSerializer

    @action(detail=False, methods=["get"])
    def get_booking_line_details(self, request, format=None):
        pk_booking_id = request.GET["pk_booking_id"]
        booking_line_details = Booking_lines_data.objects.all()

        if pk_booking_id != "undefined":
            booking_line_details = Booking_lines_data.objects.filter(
                fk_booking_id=pk_booking_id
            )

        return JsonResponse(
            {
                "booking_line_details": BookingLineDetailSerializer(
                    booking_line_details, many=True
                ).data
            }
        )

    @action(detail=False, methods=["post"])
    def create_booking_line_detail(self, request, format=None):
        serializer = BookingLineDetailSerializer(data=request.data)

        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=["post"])
    def duplicate_booking_line_detail(self, request, format=None):
        booking_line_detail = Booking_lines_data.objects.get(
            pk=request.data["pk_id_lines_data"]
        )
        newbooking_line_detail = {
            "fk_booking_id": booking_line_detail.fk_booking_id,
            "modelNumber": booking_line_detail.modelNumber,
            "itemDescription": booking_line_detail.itemDescription,
            "quantity": booking_line_detail.quantity,
            "itemFaultDescription": booking_line_detail.itemFaultDescription,
            "insuranceValueEach": booking_line_detail.insuranceValueEach,
            "gap_ra": booking_line_detail.gap_ra,
            "clientRefNumber": booking_line_detail.clientRefNumber,
            "fk_booking_lines_id": booking_line_detail.fk_booking_lines_id,
            "z_createdTimeStamp": datetime.now(),
            "z_modifiedTimeStamp": None,
        }
        serializer = BookingLineDetailSerializer(data=newbooking_line_detail)

        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=["put"])
    def update_booking_line_detail(self, request, pk, format=None):
        booking_line_detail = Booking_lines_data.objects.get(pk=pk)
        serializer = BookingLineDetailSerializer(booking_line_detail, data=request.data)

        try:
            if serializer.is_valid():
                serializer.save()
                return Response(serializer.data)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            # print('Exception: ', e)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=["delete"])
    def delete_booking_line_detail(self, request, pk, format=None):
        booking_line_detail = Booking_lines_data.objects.get(pk=pk)
        serializer = BookingLineDetailSerializer(booking_line_detail)

        try:
            booking_line_detail.delete()
            return JsonResponse({"Deleted BookingLineDetail ": serializer.data})
        except Exception as e:
            trace_error.print()
            logger.error(f"#331 - booking lines data delete: {str(e)}")
            return JsonResponse({"error": "Can not delete BookingLineDetail"})

    @action(detail=False, methods=["post"])
    def bulk_move(self, request):
        """
        bulk move LineData(s) to other Line
        """

        LOG_ID = "[BULK MOVE LINE DATA]"
        line_id = request.data["lineId"]
        line_detail_ids = request.data["lineDetailIds"]
        moved_line_detail_ids = []
        logger.info(f"{LOG_ID} Request payload: {request.data}")

        try:
            line = Booking_lines.objects.get(pk=line_id)
            line_details = Booking_lines_data.objects.filter(
                pk__in=line_detail_ids
            ).only("pk", "fk_booking_lines_id")

            for line_detail in line_details:
                line_detail.fk_booking_lines_id = line.pk_booking_lines_id
                line_detail.save()
                moved_line_detail_ids.append(line_detail.pk)

            logger.info(f"{LOG_ID} Success. Moved Id(s):{moved_line_detail_ids}")
            return JsonResponse(
                {
                    "message": "LineDetails are successfully moved",
                    "result": moved_line_detail_ids,
                }
            )
        except Exception as e:
            trace_error.print()
            logger.error(f"{LOG_ID} Error: str{e}")
            return JsonResponse(
                {"error": "Can not move BookingLineDetails"},
                status=status.HTTP_400_BAD_REQUEST,
            )


class WarehouseViewSet(viewsets.ModelViewSet):
    serializer_class = WarehouseSerializer

    def get_queryset(self):
        user_id = int(self.request.user.id)
        dme_employee = DME_employees.objects.filter(fk_id_user=user_id).first()

        if dme_employee is not None:
            user_type = "DME"
        else:
            user_type = "CLIENT"

        if user_type == "DME":
            clientWarehouseObject_list = Client_warehouses.objects.all().order_by(
                "client_warehouse_code"
            )
            queryset = clientWarehouseObject_list
            return queryset
        else:
            client_employee = Client_employees.objects.filter(
                fk_id_user=user_id
            ).first()
            client_employee_role = client_employee.get_role()

            if client_employee_role == "company":
                clientWarehouseObject_list = Client_warehouses.objects.filter(
                    Q(fk_id_dme_client_id=int(client_employee.fk_id_dme_client_id))
                    | Q(fk_id_dme_client_id=100)
                ).order_by("client_warehouse_code")
                queryset = clientWarehouseObject_list
                return queryset
            elif (
                client_employee_role == "employee"
                and client_employee.name_first == "Teddybed"
            ):
                return Client_warehouses.objects.filter(
                    fk_id_dme_client_id=client_employee.fk_id_dme_client_id
                )
            elif client_employee_role == "warehouse":
                employee_warehouse_id = client_employee.warehouse_id
                employee_warehouse = Client_warehouses.objects.get(
                    pk_id_client_warehouses=employee_warehouse_id
                )
                queryset = [employee_warehouse]
                return queryset


class PackageTypesViewSet(viewsets.ModelViewSet):
    @action(detail=False, methods=["get"], permission_classes=[AllowAny])
    def get_packagetypes(self, request, pk=None):
        packageTypes = Dme_package_types.objects.all().order_by("id")

        return_datas = []
        for packageType in packageTypes:
            return_data = {
                "id": packageType.id,
                "dmePackageTypeCode": packageType.dmePackageTypeCode,
                "dmePackageCategory": packageType.dmePackageCategory,
                "dmePackageTypeDesc": packageType.dmePackageTypeDesc,
            }
            return_datas.append(return_data)
        return JsonResponse({"packageTypes": return_datas})


class BookingStatusViewSet(viewsets.ViewSet):
    @action(detail=False, methods=["get"])
    def get_all_booking_status(self, request, pk=None):
        user_id = request.user.id
        dme_employee = DME_employees.objects.filter(fk_id_user=user_id).first()

        if dme_employee is not None:
            user_type = "DME"
        else:
            user_type = "CLIENT"

        if user_type == "DME":
            all_booking_status = Utl_dme_status.objects.all().order_by("sort_order")
        else:
            all_booking_status = Utl_dme_status.objects.filter(
                z_show_client_option=1
            ).order_by("sort_order")

        return_datas = []
        if not all_booking_status.exists():
            return JsonResponse({"all_booking_status": []})
        else:
            for booking_status in all_booking_status:
                return_data = {
                    "id": booking_status.id,
                    "dme_delivery_status": booking_status.dme_delivery_status,
                    "sort_order": booking_status.sort_order,
                }
                return_datas.append(return_data)
            return JsonResponse({"all_booking_status": return_datas})


class StatusHistoryViewSet(viewsets.ViewSet):
    @action(detail=False, methods=["get"])
    def get_all(self, request, pk=None):
        pk_booking_id = self.request.GET.get("pk_booking_id")
        queryset = Dme_status_history.objects.filter(
            fk_booking_id=pk_booking_id
        ).order_by("-id")

        return JsonResponse(
            {"results": StatusHistorySerializer(queryset, many=True).data}
        )

    @action(detail=False, methods=["post"])
    def save_status_history(self, request, pk=None):
        LOG_ID = "STATUS_HISTORY_CREATE"
        try:
            bookings = Bookings.objects.filter(
                pk_booking_id=request.data["fk_booking_id"]
            ).order_by("id")

            if bookings.count() > 1:
                error_msg = f'{LOG_ID} Duplicated {request.data["fk_booking_id"]}'
                logger.error(error_msg)
                send_email_to_admins(
                    "Duplicated pk_booking_id", request.data["fk_booking_id"]
                )
                booking = bookings.last()
            else:
                booking = bookings.first()
            
            fp_name = booking.vx_freight_provider.lower()
            if fp_name == "century" and "pod" in request.data:
                logger.info(f"{LOG_ID} Payload: {request.data.get('fp_status_description')}")
            else:
                logger.info(f"{LOG_ID} Payload: {request.data}")

            status_last = request.data.get("status_last")
            event_time_stamp = request.data.get("event_time_stamp")

            dme_notes = request.data.get("dme_notes")
            is_from_script = request.data.get("is_from_script")

            if is_from_script:
                event_time_stamp = datetime.strptime(event_time_stamp, "%Y-%m-%d %H:%M:%S.%f")
                event_time_stamp = timezone.make_aware(event_time_stamp, timezone.get_current_timezone())
                fp = booking.get_fp()
                b_status_API = request.data.get("fp_status")
                data = {
                    "b_status_API": b_status_API,
                    "status_desc": request.data.get("fp_status_description"),
                    "event_time": event_time_stamp,
                }
                create_fp_status_history(booking, fp, data)
                status_last = get_dme_status_from_fp_status(
                    fp.fp_company_name, b_status_API, booking
                )

                if not status_last:
                    error_msg = f"{LOG_ID} New FP status! Booking: {booking}, FP: {fp}, b_status_API: {b_status_API}"
                    logger.error(error_msg)
                    send_email_to_admins("New FP status", error_msg)
                    return Response(
                        {"success": False}, status=status.HTTP_400_BAD_REQUEST
                    )

            status_history.create(
                booking,
                status_last,
                request.user.username,
                event_time_stamp,
                dme_notes,
            )

            # ######################################## #
            #    Disabled because it was for `Cope`    #
            # ######################################## #
            # if request.data["status_last"] == "In Transit":
            #     calc_collect_after_status_change(
            #         request.data["fk_booking_id"], request.data["status_last"]
            #     )
            # elif request.data["status_last"] == "Delivered":
            #     booking.z_api_issue_update_flag_500 = 0
            #     booking.delivery_booking = str(datetime.now())
            #     booking.save()

            # status_category = get_status_category_from_status(
            #     request.data["status_last"]
            # )

            # if status_category == "Transit":
            #     booking.s_20_Actual_Pickup_TimeStamp = request.data[
            #         "event_time_stamp"
            #     ]

            #     if booking.s_20_Actual_Pickup_TimeStamp:
            #         z_calculated_ETA = datetime.strptime(
            #             booking.s_20_Actual_Pickup_TimeStamp[:10], "%Y-%m-%d"
            #         ) + timedelta(days=booking.delivery_kpi_days)
            #     else:
            #         z_calculated_ETA = datetime.now() + timedelta(
            #             days=booking.delivery_kpi_days
            #         )

            #     if not booking.b_given_to_transport_date_time:
            #         booking.b_given_to_transport_date_time = datetime.now()

            #     booking.z_calculated_ETA = datetime.strftime(
            #         z_calculated_ETA, "%Y-%m-%d"
            #     )
            # elif status_category == "Complete":
            #     booking.s_21_Actual_Delivery_TimeStamp = request.data[
            #         "event_time_stamp"
            #     ]
            #     booking.delivery_booking = request.data["event_time_stamp"][:10]
            #     booking.z_api_issue_update_flag_500 = 0

            # booking.b_status = request.data["status_last"]
            # booking.save()
            # serializer.save()

            if fp_name == "century" and "pod" in request.data:
                file_name = f"POD_{booking.pu_Address_State}_{toAlphaNumeric(booking.b_client_sales_inv_num)}_{str(datetime.now().strftime('%Y%m%d_%H%M%S'))}"

                file_name += ".jpeg"
                full_path = f"{S3_URL}/imgs/{fp_name}_au/{file_name}"

                logger.info(f"{LOG_ID} Pod saving: {fp_name}_au/{file_name} - {request.data['pod']}")

                f = open(full_path, "wb")
                f.write(base64.b64decode(request.data["pod"]))
                f.close()

                booking.z_pod_url = f"{fp_name}_au/{file_name}"
                booking.b_error_Capture = None
                booking.save()

            return Response({"success": True})
        except Exception as e:
            trace_error.print()
            logger.error(f"@902 - save_status_history Error: {str(e)}")
            return Response({"success": False}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=["put"])
    def update_status_history(self, request, pk, format=None):
        status_history = Dme_status_history.objects.get(pk=pk)
        booking = Bookings.objects.get(pk_booking_id=request.data["fk_booking_id"])
        serializer = StatusHistorySerializer(status_history, data=request.data)

        try:
            if serializer.is_valid():
                status_category = get_status_category_from_status(
                    request.data["status_last"]
                )

                if status_category == "Transit":
                    calc_collect_after_status_change(
                        request.data["fk_booking_id"], request.data["status_last"]
                    )

                    booking.s_20_Actual_Pickup_TimeStamp = request.data[
                        "event_time_stamp"
                    ]

                    if booking.s_20_Actual_Pickup_TimeStamp:
                        z_calculated_ETA = datetime.strptime(
                            booking.s_20_Actual_Pickup_TimeStamp[:10], "%Y-%m-%d"
                        ) + timedelta(days=booking.delivery_kpi_days)
                    else:
                        z_calculated_ETA = datetime.now() + timedelta(
                            days=booking.delivery_kpi_days
                        )

                    if not booking.b_given_to_transport_date_time:
                        booking.b_given_to_transport_date_time = (
                            booking.s_20_Actual_Pickup_TimeStamp
                        )

                    booking.z_calculated_ETA = datetime.strftime(
                        z_calculated_ETA, "%Y-%m-%d"
                    )
                elif status_category == "Complete":
                    booking.s_21_Actual_Delivery_TimeStamp = request.data[
                        "event_time_stamp"
                    ]
                    booking.delivery_booking = request.data["event_time_stamp"][:10]

                # When update last statusHistory of a booking
                if (
                    status_history.is_last_status_of_booking(booking)
                    and status_history.status_last != request.data["status_last"]
                ):
                    booking.b_status = request.data["status_last"]

                booking.save()
                serializer.save()
                return Response(serializer.data)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            # print("Exception: ", e)
            logger.info(f"Exception: {e}")
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    # Code for only [TNT REBOOK]
    @action(detail=False, methods=["post"])
    def create_with_pu_dates(self, request, pk=None):
        booking_id = request.data["bookingId"]
        booking = Bookings.objects.get(id=int(booking_id))

        if booking and booking.fk_fp_pickup_id:
            dme_status_history = Dme_status_history.objects.create(
                fk_booking_id=booking.pk_booking_id
            )

            pu_avail_date_str = booking.puPickUpAvailFrom_Date.strftime("%Y-%m-%d")
            pu_avail_time_str = f"{str(booking.pu_PickUp_Avail_Time_Hours).zfill(2)}-{str(booking.pu_PickUp_Avail_Time_Minutes).zfill(2)}-00"

            pu_by_date_str = booking.pu_PickUp_By_Date.strftime("%Y-%m-%d")
            pu_by_time_str = f"{str(booking.pu_PickUp_By_Time_Hours).zfill(2)}-{str(booking.pu_PickUp_By_Time_Minutes).zfill(2)}-00"

            dme_status_history.notes = (
                f"Rebooked PU Info - Current PU ID: {booking.fk_fp_pickup_id} "
                + f"Pickup From: ({pu_avail_date_str} {pu_avail_time_str}) "
                + f"Pickup By: ({pu_by_date_str} {pu_by_time_str})"
            )
            dme_status_history.save()

            status_histories = Dme_status_history.objects.filter(
                fk_booking_id=booking.pk_booking_id
            )

            return JsonResponse(
                {
                    "success": True,
                    "result": StatusHistorySerializer(dme_status_history).data,
                }
            )

        return JsonResponse({"success": False})


class FPViewSet(viewsets.ViewSet):
    serializer_class = FpSerializer

    @action(detail=False, methods=["get"])
    def get_all(self, request, pk=None):
        resultObjects = Fp_freight_providers.objects.all().order_by("fp_company_name")

        return JsonResponse(
            {"success": True, "results": FpSerializer(resultObjects, many=True).data}
        )

    @action(detail=True, methods=["get"])
    def get(self, request, pk, format=None):
        return_data = []
        try:
            resultObjects = []
            resultObjects = Fp_freight_providers.objects.get(pk=pk)
            if not resultObjects.fp_inactive_date:
                return_data.append(
                    {
                        "id": resultObjects.id,
                        "fp_company_name": resultObjects.fp_company_name,
                        "fp_address_country": resultObjects.fp_address_country,
                    }
                )
            return JsonResponse({"results": return_data})
        except Exception as e:
            # print('@Exception', e)
            return JsonResponse({"results": ""})

    @action(detail=False, methods=["post"])
    def add(self, request, pk=None):
        try:
            resultObject = Fp_freight_providers.objects.get_or_create(
                fp_company_name=request.data["fp_company_name"],
                fp_address_country=request.data["fp_address_country"],
            )

            return JsonResponse(
                {
                    "result": FpSerializer(resultObject[0]).data,
                    "isCreated": resultObject[1],
                }
            )
        except Exception as e:
            # print("@Exception", e)
            return JsonResponse({"results": None})

    @action(detail=True, methods=["put"])
    def edit(self, request, pk, format=None):
        fp_freight_providers = Fp_freight_providers.objects.get(pk=pk)
        serializer = FpSerializer(fp_freight_providers, data=request.data)

        try:
            if serializer.is_valid():
                serializer.save()
                return Response(serializer.data)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            # print('Exception: ', e)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=["delete"])
    def delete(self, request, pk, format=None):
        fp_freight_providers = Fp_freight_providers.objects.get(pk=pk)

        try:
            fp_freight_providers.delete()
            return JsonResponse({"results": fp_freight_providers})
        except Exception as e:
            # print('@Exception', e)
            return JsonResponse({"results": ""})

    @action(detail=False, methods=["post"])
    def set_fuel_levy_percent(self, request, pk=None):
        try:
            for fp in request.data:
                Fp_freight_providers.objects.filter(id=fp["id"]).update(
                    fp_markupfuel_levy_percent=0 if not fp["value"] else fp["value"]
                )

            return JsonResponse({"success": True})
        except Exception as e:
            # print("@Exception", e)
            return JsonResponse({"success": False})

    @action(detail=False, methods=["get"])
    def get_carriers(self, request, pk=None):
        fp_id = request.GET["fp_id"]
        return_data = []
        try:
            resultObjects = []
            resultObjects = FP_carriers.objects.filter(fk_fp=fp_id)

            for resultObject in resultObjects:
                return_data.append(
                    {
                        "id": resultObject.id,
                        "fk_fp": resultObject.fk_fp,
                        "carrier": resultObject.carrier,
                        "connote_start_value": resultObject.connote_start_value,
                        "connote_end_value": resultObject.connote_end_value,
                        "current_value": resultObject.current_value,
                        "label_end_value": resultObject.label_end_value,
                        "label_start_value": resultObject.label_start_value,
                    }
                )
            return JsonResponse({"results": return_data})
        except Exception as e:
            # print('@Exception', e)
            return JsonResponse({"results": ""})

    @action(detail=False, methods=["post"])
    def add_carrier(self, request, pk=None):
        return_data = []

        try:
            resultObjects = []
            resultObjects = FP_carriers.objects.create(
                fk_fp=request.data["fk_fp"],
                carrier=request.data["carrier"],
                connote_start_value=request.data["connote_start_value"],
                connote_end_value=request.data["connote_end_value"],
                current_value=request.data["current_value"],
                label_start_value=request.data["label_start_value"],
                label_end_value=request.data["label_end_value"],
            )

            return JsonResponse({"results": resultObjects})
        except Exception as e:
            # print('@Exception', e)
            return JsonResponse({"results": ""})

    @action(detail=True, methods=["put"])
    def edit_carrier(self, request, pk, format=None):
        fp_carrier = FP_carriers.objects.get(pk=pk)
        serializer = CarrierSerializer(fp_carrier, data=request.data)

        try:
            if serializer.is_valid():
                serializer.save()
                return Response(serializer.data)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            # print('Exception: ', e)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=["delete"])
    def delete_carrier(self, request, pk, format=None):
        fp_carrier = FP_carriers.objects.get(id=pk)

        try:
            fp_carrier.delete()
            return JsonResponse({"results": fp_carrier})
        except Exception as e:
            # print('@Exception', e)
            return JsonResponse({"results": ""})

    @action(detail=False, methods=["get"])
    def get_zones(self, request, pk=None):
        fp_id = self.request.GET["fp_id"]
        page_item_cnt = self.request.query_params.get("pageItemCnt", 10)
        page_ind = self.request.query_params.get("pageInd", 0)
        return_data = []
        try:
            resultObjects = []
            resultObjects = FP_zones.objects.filter(fk_fp=fp_id)
            # Count
            zones_cnt = resultObjects.count()

            # Pagination
            page_cnt = (
                int(zones_cnt / int(page_item_cnt))
                if zones_cnt % int(page_item_cnt) == 0
                else int(zones_cnt / int(page_item_cnt)) + 1
            )
            resultObjects = resultObjects[
                int(page_item_cnt)
                * int(page_ind) : int(page_item_cnt)
                * (int(page_ind) + 1)
            ]
            for resultObject in resultObjects:
                return_data.append(
                    {
                        "id": resultObject.id,
                        "fk_fp": resultObject.fk_fp,
                        "suburb": resultObject.suburb,
                        "state": resultObject.state,
                        "postal_code": resultObject.postal_code,
                        "zone": resultObject.zone,
                        "carrier": resultObject.carrier,
                        "service": resultObject.service,
                        "sender_code": resultObject.sender_code,
                    }
                )
            return JsonResponse(
                {
                    "results": return_data,
                    "page_cnt": page_cnt,
                    "page_ind": page_ind,
                    "page_item_cnt": page_item_cnt,
                }
            )
        except Exception as e:
            # print('@Exception', e)
            return JsonResponse({"results": ""})

    @action(detail=False, methods=["post"])
    def add_zone(self, request, pk=None):
        return_data = []

        try:
            resultObjects = []
            resultObjects = FP_zones.objects.create(
                fk_fp=request.data["fk_fp"],
                suburb=request.data["suburb"],
                state=request.data["state"],
                postal_code=request.data["postal_code"],
                zone=request.data["zone"],
                carrier=request.data["carrier"],
                service=request.data["service"],
                sender_code=request.data["sender_code"],
            )

            return JsonResponse({"results": resultObjects})
        except Exception as e:
            # print('@Exception', e)
            return JsonResponse({"results": ""})

    @action(detail=True, methods=["put"])
    def edit_zone(self, request, pk, format=None):
        fp_zone = FP_zones.objects.get(pk=pk)
        serializer = ZoneSerializer(fp_zone, data=request.data)

        try:
            if serializer.is_valid():
                serializer.save()
                return Response(serializer.data)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            # print('Exception: ', e)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=["delete"])
    def delete_zone(self, request, pk, format=None):
        fp_zone = FP_zones.objects.get(pk=pk)

        try:
            fp_zone.delete()
            return JsonResponse({"results": fp_zone})
        except Exception as e:
            # print('@Exception', e)
            return JsonResponse({"results": ""})


class EmailTemplatesViewSet(viewsets.ViewSet):
    serializer_class = EmailTemplatesSerializer

    @action(detail=False, methods=["get"])
    def get_all(self, request, pk=None):
        return_data = []

        try:
            resultObjects = []
            resultObjects = DME_Email_Templates.objects.all()
            for resultObject in resultObjects:
                return_data.append(
                    {
                        "id": resultObject.id,
                        "fk_idEmailParent": resultObject.fk_idEmailParent,
                        "emailName": resultObject.emailName,
                        "emailBody": resultObject.emailBody,
                        "sectionName": resultObject.sectionName,
                        "emailBodyRepeatEven": resultObject.emailBodyRepeatEven,
                        "emailBodyRepeatOdd": resultObject.emailBodyRepeatOdd,
                        "whenAttachmentUnavailable": resultObject.whenAttachmentUnavailable,
                        "z_createdByAccount": resultObject.z_createdByAccount,
                        "z_createdTimeStamp": resultObject.z_createdTimeStamp,
                    }
                )
            return JsonResponse({"results": return_data})
        except Exception as e:
            # print('@Exception', e)
            return JsonResponse({"results": ""})

    @action(detail=True, methods=["get"])
    def get(self, request, pk, format=None):
        return_data = []
        try:
            resultObjects = []
            resultObject = DME_Email_Templates.objects.get(pk=pk)

            return_data.append(
                {
                    "id": resultObject.id,
                    "fk_idEmailParent": resultObject.fk_idEmailParent,
                    "emailName": resultObject.emailName,
                    "emailBody": resultObject.emailBody,
                    "sectionName": resultObject.sectionName,
                    "emailBodyRepeatEven": resultObject.emailBodyRepeatEven,
                    "emailBodyRepeatOdd": resultObject.emailBodyRepeatOdd,
                    "whenAttachmentUnavailable": resultObject.whenAttachmentUnavailable,
                    "z_createdByAccount": resultObject.z_createdByAccount,
                    "z_createdTimeStamp": resultObject.z_createdTimeStamp,
                }
            )
            return JsonResponse({"results": return_data})
        except Exception as e:
            # print("@Exception", e)
            return JsonResponse({"results": ""})

    @action(detail=False, methods=["post"])
    def add(self, request, pk=None):
        return_data = []

        try:
            resultObjects = []
            resultObjects = DME_Email_Templates.objects.create(
                fk_idEmailParent=request.data["fk_idEmailParent"],
                emailName=request.data["emailName"],
                emailBody=request.data["emailBody"],
                sectionName=request.data["sectionName"],
                emailBodyRepeatEven=request.data["emailBodyRepeatEven"],
                emailBodyRepeatOdd=request.data["emailBodyRepeatOdd"],
                whenAttachmentUnavailable=request.data["whenAttachmentUnavailable"],
            )

            return JsonResponse({"results": resultObjects})
        except Exception as e:
            # print('@Exception', e)
            return JsonResponse({"results": ""})

    @action(detail=True, methods=["put"])
    def edit(self, request, pk, format=None):
        email_template = DME_Email_Templates.objects.get(pk=pk)
        # return JsonResponse({"results": (email_template.emailBody)})
        # serializer = EmailTemplatesSerializer(email_template, data=request.data)

        try:
            DME_Email_Templates.objects.filter(pk=pk).update(
                emailBody=request.data["emailBody"]
            )
            return JsonResponse({"results": request.data})
            # if serializer.is_valid():
            # try:
            # serializer.save()
            # return Response(serializer.data)
            # except Exception as e:
            # print('%s (%s)' % (e.message, type(e)))
            # return Response({"results": e.message})
            # return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            # print('Exception: ', e)
            return JsonResponse({"results": str(e)})
            # return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=["delete"])
    def delete(self, request, pk, format=None):
        email_template = DME_Email_Templates.objects.get(pk=pk)

        try:
            email_template.delete()
            return JsonResponse({"results": fp_freight_providers})
        except Exception as e:
            # print('@Exception', e)
            return JsonResponse({"results": ""})


class OptionsViewSet(viewsets.ViewSet):
    serializer_class = OptionsSerializer

    def list(self, request, pk=None):
        try:
            queryset = DME_Options.objects.filter(show_in_admin=True)
            serializer = OptionsSerializer(queryset, many=True)
            return JsonResponse({"results": serializer.data}, status=status.HTTP_200_OK)
        except Exception as e:
            return JsonResponse({"error": str(e)})

    def partial_update(self, request, pk, format=None):
        dme_options = DME_Options.objects.get(pk=pk)
        serializer = OptionsSerializer(dme_options, data=request.data)

        try:
            if serializer.is_valid():
                serializer.save()
                return Response(serializer.data)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class StatusViewSet(viewsets.ViewSet):
    @action(detail=False, methods=["get"])
    def get_status_actions(self, request, pk=None):
        return_data = []

        try:
            resultObjects = []
            resultObjects = Utl_dme_status_actions.objects.all()
            for resultObject in resultObjects:
                return_data.append(
                    {
                        "id": resultObject.id,
                        "dme_status_action": resultObject.dme_status_action,
                    }
                )
            return JsonResponse({"results": return_data})
        except Exception as e:
            # print('@Exception', e)
            return JsonResponse({"results": ""})

    @action(detail=False, methods=["post"])
    def create_status_action(self, request, pk=None):
        try:
            utl_dme_status_action = Utl_dme_status_actions(
                dme_status_action=request.data["newStatusAction"]
            )
            utl_dme_status_action.save()
            return JsonResponse({"success": "Created new status action"})
        except Exception as e:
            # print('@Exception', e)
            return JsonResponse({"error": "Can not create new status action"})

    @action(detail=False, methods=["get"])
    def get_status_details(self, request, pk=None):
        return_data = []

        try:
            resultObjects = []
            resultObjects = Utl_dme_status_details.objects.all()
            for resultObject in resultObjects:
                return_data.append(
                    {
                        "id": resultObject.id,
                        "dme_status_detail": resultObject.dme_status_detail,
                    }
                )
            return JsonResponse({"results": return_data})
        except Exception as e:
            # print('@Exception', e)
            return JsonResponse({"results": ""})

    @action(detail=False, methods=["post"])
    def create_status_detail(self, request, pk=None):
        try:
            utl_dme_status_action = Utl_dme_status_details(
                dme_status_detail=request.data["newStatusDetail"]
            )
            utl_dme_status_action.save()
            return JsonResponse({"success": "Created new status detail"})
        except Exception as e:
            # print('@Exception', e)
            return JsonResponse({"error": "Can not create new status action"})


class ApiBCLViewSet(viewsets.ViewSet):
    @action(detail=False, methods=["get"])
    def get_api_bcls(self, request, pk=None):
        booking_id = request.GET["bookingId"]
        booking = Bookings.objects.get(id=int(booking_id))
        return_data = []

        try:
            resultObjects = []
            resultObjects = Api_booking_confirmation_lines.objects.filter(
                fk_booking_id=booking.pk_booking_id
            )
            for resultObject in resultObjects:
                return_data.append(
                    {
                        "id": resultObject.id,
                        "fk_booking_id": resultObject.fk_booking_id,
                        "fk_booking_line_id": resultObject.fk_booking_line_id,
                        "label_code": resultObject.label_code
                        or resultObject.api_artical_id,
                        "client_item_reference": resultObject.client_item_reference,
                        "fp_event_date": resultObject.fp_event_date,
                        "fp_event_time": resultObject.fp_event_time,
                        "api_status": resultObject.api_status,
                    }
                )
            return JsonResponse({"results": return_data})
        except Exception as e:
            # print('@Exception', e)
            return JsonResponse({"results": ""})


class DmeReportsViewSet(viewsets.ViewSet):
    def list(self, request):
        queryset = DME_reports.objects.all()
        serializer = DmeReportsSerializer(queryset, many=True)
        return Response(serializer.data)


class FPStoreBookingLog(viewsets.ViewSet):
    # def list(self, request):
    #     queryset = FP_Store_Booking_Log.objects.all()
    #     serializer = FPStoreBookingLogSerializer(queryset, many=True)
    #     return Response(serializer.data)

    @action(detail=False, methods=["get"])
    def get_store_booking_logs(self, request, pk=None):
        v_FPBookingNumber = request.GET["v_FPBookingNumber"]
        queryset = FP_Store_Booking_Log.objects.filter(
            v_FPBookingNumber=v_FPBookingNumber
        ).order_by("-id")
        serializer = FPStoreBookingLogSerializer(queryset, many=True)
        return Response(serializer.data)


class ApiBookingQuotesViewSet(viewsets.ViewSet):
    def get_permissions(self):
        if self.action == "add" or self.action == "edit":
            permission_classes = [
                IsAuthenticated
            ]  # Set permission class for list action
        elif self.action == "addBid" or self.action == "editBid":
            permission_classes = [AllowAny]  # Set permission class for list action
        else:
            permission_classes = (
                []
            )  # Set any custom permission classes for other actions

        return [permission() for permission in permission_classes]

    @action(detail=False, methods=["get"])
    def get_pricings(self, request):
        dme_employee = DME_employees.objects.filter(fk_id_user=request.user.id)

        if dme_employee:
            user_type = "DME"
            fields_to_exclude = []
        else:
            user_type = "CLIENT"
            fields_to_exclude = ["client_mark_up_percent"]

        booking_id = request.GET["booking_id"]
        booking = Bookings.objects.get(pk=booking_id)
        queryset = (
            API_booking_quotes.objects.select_related("vehicle")
            .filter(fk_booking_id=booking.pk_booking_id, is_used=False)
            .exclude(service_name="Air Freight")
            .order_by("client_mu_1_minimum_values")
        )

        # When DmeInvoice is set (Deactivated at: 2024-03-04)
        # if booking.inv_dme_invoice_no and booking.api_booking_quote:
        #     queryset = queryset.filter(pk=booking.api_booking_quote.pk)

        client = booking.get_client()
        context = {
            "booking": booking,
            "client_customer_mark_up": client.client_customer_mark_up if client else 0,
        }

        serializer = ApiBookingQuotesSerializer(
            queryset,
            many=True,
            fields_to_exclude=fields_to_exclude,
            context=context,
        )

        res = list(serializer.data)

        # When DmeInvoice and Quote $* is set (Deactivated at: 2024-03-04)
        # if (
        #     res
        #     and booking.inv_dme_invoice_no
        #     and (booking.inv_sell_quoted_override or booking.inv_sell_quoted)
        # ):
        #     res = list(serializer.data)[0]
        #     res["freight_provider"] = booking.vx_freight_provider

        #     quoted_amount = (
        #         booking.inv_booked_quoted
        #         or booking.inv_sell_quoted_override
        #         or booking.inv_sell_quoted
        #     )

        #     res["client_mu_1_minimum_values"] = quoted_amount
        #     quote = booking.api_booking_quote
        #     surcharge_total = quote.x_price_surcharge if quote.x_price_surcharge else 0
        #     without_surcharge = res["client_mu_1_minimum_values"] - surcharge_total
        #     fp = Fp_freight_providers.objects.get(
        #         fp_company_name__iexact=booking.vx_freight_provider
        #     )
        #     res["fuel_levy_base_cl"] = without_surcharge * get_fp_fl(
        #         fp,
        #         client,
        #         booking.de_To_Address_State,
        #         booking.de_To_Address_PostalCode,
        #         booking.de_To_Address_Suburb,
        #         quote,
        #     )
        #     res["cost_dollar"] = without_surcharge - res["fuel_levy_base_cl"]
        #     res = [res]

        return Response(res)

    @action(detail=False, methods=["post"])
    def add(self, request, pk=None):
        LOG_ID = "[CREATE CUSTOM FP QUOTE]"
        pk_auto_id = request.data.get("pk_auto_id")
        fk_booking_id = request.data.get("fk_booking_id")
        fk_client_id = request.data.get("fk_client_id")
        try:
            if pk_auto_id:  # from pricing page, else from booking page
                #  Try to find from bok_1 table
                bok_1 = BOK_1_headers.objects.get(pk_auto_id=pk_auto_id)
                if bok_1:
                    fk_booking_id = bok_1.pk_header_id
                    fk_client_id = bok_1.fk_client_id
                else:
                    return Response(
                        {
                            "success": False,
                            "message": f"BOK_1_headers({pk_auto_id}) does not exist.",
                        },
                        status=status.HTTP_400_BAD_REQUEST,
                    )

            api_booking_quotes = API_booking_quotes(
                api_results_id=f"custom-result-{str(random.randrange(0, 100000)).zfill(6)}",
                fk_booking_id=fk_booking_id,
                fk_client_id=fk_client_id,
                provider="Customer",
                freight_provider=request.data.get("freight_provider"),
                service_name=request.data.get("service_name"),
                fee=request.data.get("fee"),
                etd=request.data.get("etd"),
                packed_status=request.data.get("packed_status"),
                fuel_levy_base=float(request.data.get("fee"))
                * float(request.data.get("mu_percentage_fuel_levy")),
                mu_percentage_fuel_levy=request.data.get("mu_percentage_fuel_levy"),
                client_mu_1_minimum_values=request.data.get(
                    "client_mu_1_minimum_values"
                ),
            )
            api_booking_quotes.save()
            logger.info(f"{LOG_ID} Success! \nPayload: {request.data}")
            return Response(
                {
                    "success": True,
                    "message": "Custom FP quote is created successfully",
                }
            )
        except Exception as e:
            # print("Exception: ", e)
            trace_error.print()
            res_json = {"success": False, "message": str(e)}
            return Response(res_json, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=["put"])
    def edit(self, request, pk=None):
        LOG_ID = "[UPDATE CUSTOM FP QUOTE]"
        quote_id = request.data.get("quote_id")

        try:
            API_booking_quotes.objects.filter(pk=quote_id).update(
                freight_provider=request.data.get("freight_provider"),
                service_name=request.data.get("service_name"),
                fee=request.data.get("fee"),
                etd=request.data.get("etd"),
                packed_status=request.data.get("packed_status"),
                fuel_levy_base=float(request.data.get("fee"))
                * float(request.data.get("mu_percentage_fuel_levy")),
                mu_percentage_fuel_levy=request.data.get("mu_percentage_fuel_levy"),
                client_mu_1_minimum_values=request.data.get(
                    "client_mu_1_minimum_values"
                ),
            )
            logger.info(f"{LOG_ID} Success! \nPayload: {request.data}")
            return Response(
                {"success": True, "message": "Custom FP quote is updated successfully"}
            )
        except Exception as e:
            # print("Exception: ", e)
            trace_error.print()
            res_json = {"success": False, "message": str(e)}
            return Response(res_json, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=["delete"])
    def delete(self, request, pk, format=None):
        custom_quote = API_booking_quotes.objects.get(pk=pk)

        try:
            custom_quote.delete()
            return JsonResponse({"results": custom_quote})
        except Exception as e:
            # print('@Exception', e)
            return JsonResponse({"results": ""})

    @action(detail=False, methods=["post"])
    def addBid(self, request):
        LOG_ID = "[CREATE CUSTOM BID FP QUOTE]"
        token = request.data.get("token")
        try:
            if token:  # from pricing page, else from booking page
                #  Try to find from bok_1 table
                dme_token = DME_Tokens.objects.get(token=token)
                if dme_token:
                    booking = Bookings.objects.get(pk=dme_token.booking_id)
                    fk_booking_id = booking.pk_booking_id
                    fk_client_id = booking.b_client_name

                    api_booking_quotes = API_booking_quotes(
                        api_results_id=f"custom-result-{str(random.randrange(0, 100000)).zfill(6)}",
                        fk_booking_id=fk_booking_id,
                        fk_client_id=fk_client_id,
                        provider="Customer",
                        freight_provider=dme_token.vx_freight_provider,
                        service_name=request.data.get("service_name"),
                        fee=request.data.get("fee"),
                        etd=request.data.get("etd"),
                        packed_status=request.data.get("packed_status"),
                        fuel_levy_base=float(request.data.get("fee"))
                        * float(request.data.get("mu_percentage_fuel_levy")),
                        mu_percentage_fuel_levy=request.data.get(
                            "mu_percentage_fuel_levy"
                        ),
                        client_mu_1_minimum_values=request.data.get(
                            "client_mu_1_minimum_values"
                        ),
                        notes=request.data.get("notes"),
                        pickup_timestamp=request.data.get("pickup_timestamp"),
                        delivery_timestamp=request.data.get("delivery_timestamp"),
                    )
                    api_booking_quotes.save()

                    dme_token.api_booking_quote_id = api_booking_quotes.id
                    dme_token.save()

                    logger.info(f"{LOG_ID} Success! \nPayload: {request.data}")
                    return Response(
                        {
                            "success": True,
                            "message": "Custom FP quote is created successfully",
                        }
                    )
            return Response(
                {
                    "success": False,
                    "message": f"Token is invalid.",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        except Exception as e:
            # print("Exception: ", e)
            trace_error.print()
            res_json = {"success": False, "message": str(e)}
            return Response(res_json, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=["put"])
    def editBid(self, request):
        LOG_ID = "[UPDATE CUSTOM BID FP QUOTE]"
        quote_id = request.data.get("quote_id")
        token = request.data.get("token")
        try:
            if token:  # from pricing page, else from booking page
                #  Try to find from bok_1 table
                dme_token = DME_Tokens.objects.get(token=token)
                if dme_token:

                    API_booking_quotes.objects.filter(pk=quote_id).update(
                        freight_provider=request.data.get("freight_provider"),
                        service_name=request.data.get("service_name"),
                        fee=request.data.get("fee"),
                        etd=request.data.get("etd"),
                        packed_status=request.data.get("packed_status"),
                        fuel_levy_base=float(request.data.get("fee"))
                        * float(request.data.get("mu_percentage_fuel_levy")),
                        mu_percentage_fuel_levy=request.data.get(
                            "mu_percentage_fuel_levy"
                        ),
                        client_mu_1_minimum_values=request.data.get(
                            "client_mu_1_minimum_values"
                        ),
                        notes=request.data.get("notes"),
                        pickup_timestamp=request.data.get("pickup_timestamp"),
                        delivery_timestamp=request.data.get("delivery_timestamp"),
                    )

                    logger.info(f"{LOG_ID} Success! \nPayload: {request.data}")
                    return Response(
                        {
                            "success": True,
                            "message": "Custom FP quote is created successfully",
                        }
                    )
            return Response(
                {
                    "success": False,
                    "message": f"Token is invalid.",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        except Exception as e:
            # print("Exception: ", e)
            trace_error.print()
            res_json = {"success": False, "message": str(e)}
            return Response(res_json, status=status.HTTP_400_BAD_REQUEST)


@api_view(["POST"])
@permission_classes((IsAuthenticated,))
def download(request):
    LOG_ID = "[DOWNLOAD]"
    body = literal_eval(request.body.decode("utf8"))
    download_option = body["downloadOption"]
    file_paths = []
    prefixes = []
    logger.info(f"{LOG_ID} Option: {download_option}")

    if download_option not in ["logs", "dme_logs", "quote-report"]:
        if download_option in ["pricing-only", "pricing-rule", "xls import"]:
            file_name = body["fileName"]
        elif download_option == "manifest":
            z_manifest_url = body["z_manifest_url"]
        elif download_option == "zpl":
            pass
        elif download_option == "attachment":
            attachmentIds = body["ids"]
            attachments = Dme_attachments.objects.filter(pk_id_attachment=attachmentIds)
        else:
            bookingIds = body["ids"]
            bookings = Bookings.objects.filter(id__in=bookingIds).order_by("id")

    if download_option == "pricing-only":
        src_file_path = f"./static/uploaded/pricing_only/achieve/{file_name}"
        file_paths.append(src_file_path)
        file_name_without_ext = file_name.split(".")[0]
        result_file_record = DME_Files.objects.filter(
            file_name__icontains=file_name_without_ext, file_type="pricing-result"
        )

        if result_file_record:
            file_paths.append(result_file_record.first().file_path)
    elif download_option == "pricing-rule":
        src_file_path = f"./static/uploaded/pricing_rule/achieve/{file_name}"
        file_paths.append(src_file_path)
    elif download_option == "xls import":
        file_name_without_ext = file_name.split(".")[0]
        result_file_record = DME_Files.objects.filter(
            file_name__icontains=file_name_without_ext, file_type="xls import"
        )

        if result_file_record:
            file_paths.append(result_file_record.first().file_path)
    elif download_option == "manifest":
        file_paths.append(f"{settings.STATIC_PUBLIC}/pdfs/{z_manifest_url}")

        # ONLY for BioPak + TGE + PE (Pallet Express service)
        # Download Pickup PDF file as well
        pickup_file_name = z_manifest_url.replace("manifest_", "pickup_")
        pickup_file_path = f"{settings.STATIC_PUBLIC}/pdfs"
        if doesFileExist(pickup_file_path, pickup_file_name):
            file_paths.append(f"{pickup_file_path}/{pickup_file_name}")
    elif download_option == "label":
        for booking in bookings:
            if booking.z_label_url and len(booking.z_label_url) > 0:
                if "http" in booking.z_label_url:
                    fp_name = f"{booking.vx_freight_provider.lower()}_au"
                    label_url = f"{fp_name}/DME{booking.b_bookingID_Visual}.pdf"
                else:
                    label_url = booking.z_label_url

                if booking.b_client_name == "Tempo Big W":
                    prefixes.append(booking.b_bookingID_Visual)

                file_paths.append(f"{settings.STATIC_PUBLIC}/pdfs/{label_url}")
                booking.z_downloaded_shipping_label_timestamp = str(datetime.now())
                booking.save()
    elif download_option == "attachment":
        for attachment in attachments:
            if attachment.fileName and len(attachment.fileName) > 0:
                file_paths.append(f"{attachment.fileName}")
    elif download_option == "merged_label":
        label_urls = []
        label_numbers = []
        for booking in bookings:
            if booking.z_label_url and len(booking.z_label_url) > 0:
                if "http" in booking.z_label_url:
                    fp_name = f"{booking.vx_freight_provider.lower()}_au"
                    label_url = f"{fp_name}/DME{booking.b_bookingID_Visual}.pdf"
                else:
                    label_url = booking.z_label_url
                logger.info(booking.b_clientReference_RA_Numbers)
                label_numbers.append(
                    booking.b_clientReference_RA_Numbers
                    if booking.b_clientReference_RA_Numbers
                    else booking.v_FPBookingNumber
                )
                label_urls.append(f"{settings.STATIC_PUBLIC}/pdfs/{label_url}")
        file_path = f"{settings.STATIC_PUBLIC}/pdfs"
        if len(label_numbers) > 0:
            entire_label_url = f"{file_path}/{label_numbers[0]}_{label_numbers[-1]}.pdf"
            pdf_merge(label_urls, entire_label_url)
            file_paths.append(entire_label_url)
    elif download_option == "pod":
        for booking in bookings:
            if booking.z_pod_url is not None and len(booking.z_pod_url) > 0:
                file_paths.append(f"{settings.STATIC_PUBLIC}/imgs/{booking.z_pod_url}")
                booking.z_downloaded_pod_timestamp = timezone.now()
                booking.save()
    elif download_option == "pod_sog":
        for booking in bookings:
            if booking.z_pod_signed_url and len(booking.z_pod_signed_url) > 0:
                file_paths.append(
                    f"{settings.STATIC_PUBLIC}/imgs/{booking.z_pod_signed_url}"
                )
                booking.z_downloaded_pod_sog_timestamp = timezone.now()
                booking.save()
    elif download_option == "new_pod":
        for booking in bookings:
            if booking.z_downloaded_pod_timestamp is None:
                if booking.z_pod_url and len(booking.z_pod_url) > 0:
                    file_paths.append(
                        f"{settings.STATIC_PUBLIC}/imgs/{booking.z_pod_url}"
                    )
                    booking.z_downloaded_pod_timestamp = timezone.now()
                    booking.save()
    elif download_option == "new_pod_sog":
        for booking in bookings:
            if booking.z_downloaded_pod_sog_timestamp is None:
                if booking.z_pod_signed_url and len(booking.z_pod_signed_url) > 0:
                    file_paths.append(
                        f"{settings.STATIC_PUBLIC}/imgs/{booking.z_pod_signed_url}"
                    )
                    booking.z_downloaded_pod_sog_timestamp = timezone.now()
                    booking.save()
    elif download_option == "connote":
        for booking in bookings:
            if booking.z_connote_url and len(booking.z_connote_url) is not 0:
                file_paths.append(
                    f"{settings.STATIC_PRIVATE}/connotes/" + booking.z_connote_url
                )
                booking.z_downloaded_connote_timestamp = timezone.now()
                booking.save()
    elif download_option == "new_connote":
        for booking in bookings:
            if booking.z_downloaded_pod_timestamp is None:
                if booking.z_connote_url and len(booking.z_connote_url) > 0:
                    file_paths.append(
                        f"{settings.STATIC_PRIVATE}/connotes/" + booking.z_connote_url
                    )
                    booking.z_downloaded_connote_timestamp = timezone.now()
                    booking.save()
    elif download_option == "label_and_connote":
        for booking in bookings:
            if booking.z_connote_url and len(booking.z_connote_url) > 0:
                file_paths.append(
                    f"{settings.STATIC_PRIVATE}/connotes/" + booking.z_connote_url
                )
                booking.z_downloaded_connote_timestamp = timezone.now()
                booking.save()
            if booking.z_label_url and len(booking.z_label_url) > 0:
                if "http" in booking.z_label_url:
                    fp_name = f"{booking.vx_freight_provider.lower()}_au"
                    label_url = f"{fp_name}/DME{booking.b_bookingID_Visual}.pdf"
                else:
                    label_url = booking.z_label_url

                file_paths.append(f"{settings.STATIC_PUBLIC}/pdfs/{label_url}")
                booking.z_downloaded_shipping_label_timestamp = timezone.now()
                booking.save()
    elif download_option == "zpl":
        pdf_url = body.get("url")
        booking_id = body.get("id")

        if booking_id:
            booking = Bookings.objects.get(pk=booking_id)
            # Plum ZPL printer requries portrait label
            if booking.vx_freight_provider.lower() in ["hunter", "tnt"]:
                label_url = rotate_pdf(label_url)

        label_url = f"{settings.STATIC_PUBLIC}/pdfs/{pdf_url}"

        # Convert label into ZPL format
        logger.info(f"{LOG_ID} - converting LABEL({label_url}) into ZPL format...")
        result = pdf_to_zpl(label_url, label_url[:-4] + ".zpl")

        zpl_url = label_url[:-4] + ".zpl"
        file_paths.append(zpl_url)
    elif download_option == "logs":
        mode = body["mode"]

        if mode == 0:
            file_paths.append(os.path.join(f"{settings.BASE_DIR}/logs", "debug.log"))
        else:
            count = 10 if mode == 1 else 50

            for i in range(count):
                if i == 0:
                    path = f"{settings.BASE_DIR}/logs/debug.log"
                else:
                    path = f"{settings.BASE_DIR}/logs/debug.log.{i}"

                if os.path.exists(path):
                    file_paths.append(path)

    elif download_option == "dme_logs":
        log_date = body["log_date"]
        has_error = dme_log_csv(log_date)

        if has_error:
            return JsonResponse(
                {"status": False, "message": "Failed to create CSV"}, status=400
            )
        file_paths = [f"{settings.STATIC_PUBLIC}/csvs/dme_logs/dme_log__{log_date}.csv"]

    elif download_option == "quote-report":
        kf_client_ids = body.get("kfClientIds")
        start_date = body.get("startDate")
        end_date = body.get("endDate")
        file_paths = [build_quote_report(kf_client_ids, start_date, end_date)]

    response = download_libs.download_from_disk(download_option, file_paths, prefixes)
    return response


@api_view(["DELETE"])
@permission_classes((IsAuthenticated,))
def delete_file(request):
    body = literal_eval(request.body.decode("utf8"))
    file_option = body["deleteFileOption"]

    if file_option in ["label", "pod"]:
        try:
            booking_id = body["bookingId"]
            booking = Bookings.objects.get(id=booking_id)
        except Bookings.DoesNotExist as e:
            return JsonResponse(
                {"message": "Booking does not exist", "status": "failure"}, status=400
            )

        if file_option == "label":
            file_name = f"{booking.z_label_url}"
            file_path = f"{settings.STATIC_PUBLIC}/pdfs/{file_name}"
            booking.z_label_url = None
            booking.z_downloaded_shipping_label_timestamp = None
        elif file_option == "pod":
            file_name = f"{booking.z_pod_url}"
            file_path = f"{settings.STATIC_PUBLIC}/imgs/"
            booking.z_pod_url = None
            booking.z_downloaded_pod_timestamp = None

        booking.save()
        delete_lib.delete(file_path)
    elif file_option == "attachment":
        try:
            attachmentId = body["attachmentId"]
            attachment = Dme_attachments.objects.get(pk_id_attachment=attachmentId)
        except Dme_attachments.DoesNotExist as e:
            return JsonResponse(
                {"message": "Attachments does not exist", "status": "failure"},
                status=400,
            )
        file_name = f"{attachment.fileName}"
        attachment.delete()
        delete_lib.delete(attachment.fileName)
    elif file_option == "pricing-only":
        file_name = body["fileName"]
        delete_lib.delete(f"./static/uploaded/pricing_only/indata/{file_name}")
        delete_lib.delete(f"./static/uploaded/pricing_only/inprogress/{file_name}")
        delete_lib.delete(f"./static/uploaded/pricing_only/achieve/{file_name}")
        file_name_without_ext = file_name.split(".")[0]
        result_file_record = DME_Files.objects.filter(
            file_name__icontains=file_name_without_ext, file_type="pricing-result"
        )

        if result_file_record:
            delete_lib.delete(result_file_record.first().file_path)

        DME_Files.objects.filter(file_name__icontains=file_name_without_ext).delete()
    elif file_option == "pricing-rule":
        file_name = body["fileName"]
        delete_lib.delete(f"./static/uploaded/pricing_rule/indata/{file_name}")
        delete_lib.delete(f"./static/uploaded/pricing_rule/inprogress/{file_name}")
        delete_lib.delete(f"./static/uploaded/pricing_rule/achieve/{file_name}")
        file_name_without_ext = file_name.split(".")[0]
        DME_Files.objects.filter(file_name__icontains=file_name_without_ext).delete()

    return JsonResponse(
        {
            "filename": file_name,
            "status": "success",
            "message": "Deleted successfully!",
        },
        status=200,
    )


@api_view(["POST"])
@permission_classes((IsAuthenticated,))
@authentication_classes([JSONWebTokenAuthentication])
def get_csv(request):
    body = literal_eval(request.body.decode("utf8"))
    booking_ids = body["bookingIds"]
    vx_freight_provider = body.get("vx_freight_provider", None)
    file_paths = []
    label_names = []

    if not booking_ids:
        return JsonResponse(
            {"success": False, "filename": "", "status": "No bookings to build CSV."},
            status=400,
        )

    bookings = Bookings.objects.filter(pk__in=booking_ids)

    if bookings and not vx_freight_provider:
        vx_freight_provider = bookings.first().vx_freight_provider.lower()

    has_error = build_csv(booking_ids)

    if has_error:
        return JsonResponse(
            {"status": False, "message": "Failed to create CSV"}, status=400
        )
    else:
        for booking in bookings:
            if vx_freight_provider == "cope":
                ############################################################################################
                # This is a comment this is what I did and why to make this happen 05/09/2019 pete walbolt #
                ############################################################################################
                booking.b_dateBookedDate = get_sydney_now_time()
                status_history.create(booking, "Booked", request.user.username)
                booking.v_FPBookingNumber = "DME" + str(booking.b_bookingID_Visual)
                booking.save()

                booking_lines = Booking_lines.objects.filter(
                    fk_booking_id=booking.pk_booking_id
                )
                index = 1

                for booking_line in booking_lines:
                    for i in range(int(booking_line.e_qty)):
                        api_booking_confirmation_line = Api_booking_confirmation_lines(
                            fk_booking_id=booking.pk_booking_id,
                            fk_booking_line_id=booking_line.pk_lines_id,
                            api_item_id=str("COPDME")
                            + str(booking.b_bookingID_Visual)
                            + make_3digit(index),
                            service_provider=booking.vx_freight_provider,
                            label_code=str("COPDME")
                            + str(booking.b_bookingID_Visual)
                            + make_3digit(index),
                            client_item_reference=booking_line.client_item_reference,
                        )
                        api_booking_confirmation_line.save()
                        index = index + 1
            else:  # vx_freight_provider in ["dhl", "state transport", "century"]:
                booking.b_dateBookedDate = get_sydney_now_time(return_type="datetime")
                booking.v_FPBookingNumber = "DME" + str(booking.b_bookingID_Visual)
                status_history.create(booking, "Booked", request.user.username)
                booking.save()

                if booking.b_client_name == "Bathroom Sales Direct":
                    booking_lines = Booking_lines.objects.filter(
                        fk_booking_id=booking.pk_booking_id, is_deleted=False, packed_status="scanned"
                    )
                    send_email_booked(booking, booking_lines)

        return JsonResponse(
            {"success": True, "message": "Created CSV successfully"}, status=200
        )


@api_view(["POST"])
@permission_classes((IsAuthenticated,))
@authentication_classes([JSONWebTokenAuthentication])
def get_xml(request):
    body = literal_eval(request.body.decode("utf8"))
    booking_ids = body["bookingIds"]
    vx_freight_provider = body["vx_freight_provider"]

    if len(booking_ids) == 0:
        return JsonResponse({"success": True, "status": "No bookings to build XML"})

    try:
        booking = Bookings.objects.get(pk=booking_ids[0])

        if vx_freight_provider == "direct freight":
            success = build_df_book_xml(booking)
        # else:
        #     booked_list = build_xml(booking_ids, vx_freight_provider, 1)

        booking.b_dateBookedDate = datetime.now()
        status_history.create(booking, "Booked", request.user.username)
        booking.b_error_Capture = None
        booking.save()

        if booking.b_client_name == "Bathroom Sales Direct":
            booking_lines = Booking_lines.objects.filter(
                fk_booking_id=booking.pk_booking_id, is_deleted=False, packed_status="scanned"
            )
            send_email_booked(booking, booking_lines)

        return JsonResponse({"success": "success"})
    except Exception as e:
        trace_error.print()
        return JsonResponse({"error": str(e)})


@api_view(["POST"])
@permission_classes((IsAuthenticated,))
@authentication_classes([JSONWebTokenAuthentication])
def get_manifest(request):
    LOG_ID = "[GET_MANIFEST]"
    body = literal_eval(request.body.decode("utf8"))
    booking_ids = body["bookingIds"]
    vx_freight_provider = body["vx_freight_provider"]
    username = body["username"]
    clientname = get_clientname_with_request(request)
    need_truck = body.get("needTruck") or False
    is_from_fm = body.get("isFromFM") or False
    timestamp = body.get("timestamp") or None

    bookings = (
        Bookings.objects.filter(pk__in=booking_ids)
        .filter(Q(z_manifest_url__isnull=True) | Q(z_manifest_url__exact=""))
        .only("id", "vx_freight_provider")
    )
    fps = {}

    for booking in bookings:
        if not booking.vx_freight_provider in fps:
            fps[booking.vx_freight_provider] = []

        fps[booking.vx_freight_provider].append(booking.id)

    try:
        file_paths = []

        for fp in fps:
            if vx_freight_provider.upper() == "DIRECT FREIGHT" and need_truck:
                # Call 'Direct Freight' truck (once per day)
                success = call_truck_oper(
                    bookings, vx_freight_provider.lower(), clientname
                )

                if not success:
                    return JsonResponse(
                        {
                            "success": False,
                            "message": "Call Truck operation got failed.",
                        }
                    )

            bookings, filename = build_manifest(
                fps[fp], username, need_truck, timestamp
            )

            z_manifest_url = f"{vx_freight_provider.lower()}_au/{filename}"
            file_path = f"{settings.STATIC_PUBLIC}/pdfs/{z_manifest_url}"
            file_paths.append(file_path)

            for booking in bookings:
                # Jason L & BSD: Create new statusHistory
                if (
                    "bsd" in request.user.username
                    or "jason" in request.user.username
                    or "anchor_packaging" in request.user.username
                    or "aberdeen_paper_01" in request.user.username
                    or clientname == "dme"
                ) and not booking.b_dateBookedDate:
                    if booking.vx_freight_provider in SPECIAL_FPS:
                        booking.b_dateBookedDate = timestamp or datetime.now()
                        booking.v_FPBookingNumber = gen_consignment_num(
                            booking.vx_freight_provider, booking.b_bookingID_Visual
                        )
                        status_history.create(booking, "Booked", username)

                        # Update status to `In Transit` for DME linehaul
                        if booking.vx_freight_provider == "Deliver-ME":
                            status_history.create(booking, "In Transit", username)
                    else:
                        status_history.create(booking, "Ready for Despatch", username)

                booking.z_manifest_url = z_manifest_url
                booking.manifest_timestamp = timestamp or datetime.now()
                booking.save()
        if is_from_fm:
            return JsonResponse(
                {
                    "success": True,
                    "message": "Manifest is built successfully.",
                    "manifest_url": file_paths[0].replace(
                        settings.STATIC_PUBLIC, settings.S3_URL
                    ),
                }
            )
        else:
            zip_subdir = "manifest_files"
            zip_filename = "%s.zip" % zip_subdir

            s = io.BytesIO()
            zf = zipfile.ZipFile(s, "w")
            for index, file_path in enumerate(file_paths):
                if os.path.isfile(file_path):
                    file_name = file_path.split("/")[-1]
                    file_name = file_name.split("\\")[-1]
                    zf.write(file_path, f"manifest_files/{file_name}")
            zf.close()

            response = HttpResponse(s.getvalue(), "application/x-zip-compressed")
            response["Content-Disposition"] = "attachment; filename=%s" % zip_filename
            return response
    except Exception as e:
        trace_error.print()
        logger.error(f"get_mainifest error: {str(e)}")
        return JsonResponse(
            {"success": False, "message": "Please contact support center."}
        )


@api_view(["POST"])
@permission_classes((IsAuthenticated,))
@authentication_classes([JSONWebTokenAuthentication])
def get_pdf(request):
    body = literal_eval(request.body.decode("utf8"))
    booking_ids = body["bookingIds"]
    vx_freight_provider = body["vx_freight_provider"]

    try:
        results_cnt = build_pdf(booking_ids, vx_freight_provider)

        if results_cnt > 0:
            return JsonResponse({"success": "success"})
        else:
            return JsonResponse({"error": "No one has been generated"})
    except Exception as e:
        # print('get_pdf error: ', e)
        return JsonResponse({"error": "error"})


@api_view(["POST"])
@permission_classes((IsAuthenticated,))
@authentication_classes([JSONWebTokenAuthentication])
def build_label(request):
    LOG_ID = "[DME LABEL BUILD]"

    body = literal_eval(request.body.decode("utf8"))
    booking_id = body["booking_id"]
    line_ids = body.get("line_ids")
    logger.info(f"{LOG_ID} Booking pk: {booking_id}, Line Ids: {line_ids}")
    booking = Bookings.objects.get(pk=booking_id)
    lines = booking.lines().filter(is_deleted=False)

    if line_ids:
        lines = lines.filter(pk__in=line_ids)

    # Reset all Api_booking_confirmation_lines
    Api_booking_confirmation_lines.objects.filter(
        fk_booking_id=booking.pk_booking_id
    ).delete()

    for line in lines:
        if line.sscc and "NOSSCC_" in line.sscc:
            line.sscc = None
            line.save()

    scanned_lines = []
    for line in lines:
        if line.packed_status == "scanned":
            scanned_lines.append(line)

    original_lines = []
    for line in lines:
        if line.packed_status == "original":
            original_lines.append(line)

    if booking.api_booking_quote:
        selected_lines = []

        for line in lines:
            if (
                line_ids
                or line.packed_status == booking.api_booking_quote.packed_status
            ):
                selected_lines.append(line)

        lines = selected_lines
    else:
        if scanned_lines:
            lines = scanned_lines
        else:
            lines = original_lines

    # Populate SSCC if doesn't exist
    for line in lines:
        if not line.sscc:
            line.sscc = f"NOSSCC_{booking.b_bookingID_Visual}_{line.pk}"
            line.save()

    label_urls = []
    sscc_list = []
    sscc_lines = {}
    total_qty = 0
    for line in lines:
        if line.sscc not in sscc_list:
            sscc_list.append(line.sscc)
            total_qty += line.e_qty
            _lines = []

            for line1 in lines:
                if line1.sscc == line.sscc:
                    _lines.append(line1)

            sscc_lines[line.sscc] = _lines
    logger.info(
        f"{LOG_ID} \nsscc_list: {sscc_list}\nsscc_lines: {sscc_lines}\nTotal QTY: {total_qty}"
    )

    if not booking.puPickUpAvailFrom_Date:
        booking.puPickUpAvailFrom_Date = convert_to_AU_SYDNEY_tz(datetime.now()).date()

    file_path = (
        f"{settings.STATIC_PUBLIC}/pdfs/{booking.vx_freight_provider.lower()}_au"
    )

    try:
        # Build label with SSCC - one sscc should have one page label
        label_data = build_label_oper(
            booking=booking,
            file_path=file_path,
            total_qty=total_qty,
            sscc_list=sscc_list,
            sscc_lines=sscc_lines,
            need_zpl=False,
        )

        message = f"#379 {LOG_ID} - Successfully build label. Booking Id: {booking.b_bookingID_Visual}"
        logger.info(message)

        if label_data["urls"]:
            if line_ids:
                suffix = (
                    len(line_ids)
                    if len(line_ids) > 10
                    else "_".join([str(line_id) for line_id in line_ids])
                )
                label_url = f"DME{booking.b_bookingID_Visual}_{suffix}.pdf"
                entire_label_url = f"{file_path}/{label_url}"
                pdf_merge(label_data["urls"], entire_label_url)
                return JsonResponse(
                    {
                        "success": "success",
                        "message": "Label is successfully built!",
                        "labelUrl": f"{booking.vx_freight_provider.lower()}_au/{label_url}",
                        "lineIds": line_ids,
                    }
                )

            entire_label_url = f"{file_path}/DME{booking.b_bookingID_Visual}.pdf"
            pdf_merge(label_data["urls"], entire_label_url)

        # Build merged consignment pdf for Northline and Camerons
        if booking.vx_freight_provider.lower() in ["northline", "camerons"]:
            entire_label_url = (
                f"{file_path}/DME{booking.b_bookingID_Visual}_consignment.pdf"
            )
            label_data["urls"] = [
                os.path.splitext(url)[0] + "_consignment" + os.path.splitext(url)[1]
                for url in label_data["urls"]
            ]
            pdf_merge(label_data["urls"], entire_label_url)

        if not booking.b_client_booking_ref_num:
            booking.b_client_booking_ref_num = (
                f"{booking.b_bookingID_Visual}_{str(uuid.uuid4())}"
            )

        booking.z_label_url = f"{settings.WEB_SITE_URL}/label/{booking.b_client_booking_ref_num or booking.pk_booking_id}/"

        # Jason L
        if not booking.b_dateBookedDate and booking.b_status != "Picked":
            status_history.create(booking, "Picked", request.user.username)

        # Set consignment number
        booking.v_FPBookingNumber = gen_consignment_num(
            booking.vx_freight_provider,
            booking.b_bookingID_Visual,
            booking.kf_client_id,
            booking,
        )
        booking.b_error_Capture = ""
        booking.save()

        # BioPak: update with json
        # if (
        #     booking.b_client_name.lower() == "biopak"
        #     and booking.b_client_warehouse_code in ["BIO - RIC"]
        # ):
        #     from api.fp_apis.update_by_json import update_biopak_with_booked_booking

        #     update_biopak_with_booked_booking(booking.pk, "label")
    except Exception as e:
        trace_error.print()
        logger.error(f"{LOG_ID} Error: {str(e)}")
        booking.b_error_Capture = str(e)
        booking.save()
        return JsonResponse(
            {"success": "failure", "message": f"Label operation get failed!\n{str(e)}"}
        )

    return JsonResponse(
        {
            "success": "success",
            "message": "Label is successfully built!",
            "labelUrl": booking.z_label_url,
            "lineIds": line_ids,
        }
    )


@api_view(["POST"])
@permission_classes((IsAuthenticated,))
@authentication_classes([JSONWebTokenAuthentication])
def build_label_bulk(request):
    LOG_ID = "[DME LABEL BULK]"

    body = literal_eval(request.body.decode("utf8"))
    line_ids = body.get("line_ids")
    logger.info(f"{LOG_ID} Booking Line Ids: {line_ids}")
    booking_lines = Booking_lines.objects.filter(is_deleted=False)

    if not line_ids:
        return JsonResponse(
            {
                "success": "failure",
                "message": f"Label operation get failed! `line_ids` are required.",
            }
        )
    if line_ids:
        booking_lines = booking_lines.filter(pk__in=line_ids)

    pk_booking_ids = []
    for line in booking_lines:
        pk_booking_ids.append(line.fk_booking_id)
    # Reset all Api_booking_confirmation_lines
    Api_booking_confirmation_lines.objects.filter(
        fk_booking_id__in=pk_booking_ids
    ).delete()
    bookings = Bookings.objects.filter(pk_booking_id__in=pk_booking_ids)

    label_urls = []
    for booking in bookings:
        lines = []
        for line in booking_lines:
            if booking.pk_booking_id == line.fk_booking_id:
                lines.append(line)

        if not lines:
            continue

        for line in lines:
            if line.sscc and "NOSSCC_" in line.sscc:
                line.sscc = None
                line.save()

        scanned_lines = []
        for line in lines:
            if line.packed_status == "scanned":
                scanned_lines.append(line)

        original_lines = []
        for line in lines:
            if line.packed_status == "original":
                original_lines.append(line)

        if booking.api_booking_quote:
            selected_lines = []

            for line in lines:
                if (
                    line_ids
                    or line.packed_status == booking.api_booking_quote.packed_status
                ):
                    selected_lines.append(line)

            lines = selected_lines
        else:
            lines = scanned_lines or original_lines

        # Populate SSCC if doesn't exist
        for line in lines:
            if not line.sscc:
                line.sscc = f"NOSSCC_{booking.b_bookingID_Visual}_{line.pk}"
                line.save()

        sscc_list = []
        sscc_lines = {}
        total_qty = 0
        for line in lines:
            if line.sscc not in sscc_list:
                sscc_list.append(line.sscc)
                total_qty += line.e_qty
                _lines = []

                for line1 in lines:
                    if line1.sscc == line.sscc:
                        _lines.append(line1)

                sscc_lines[line.sscc] = _lines
        logger.info(
            f"{LOG_ID} \nsscc_list: {sscc_list}\nsscc_lines: {sscc_lines}\nTotal QTY: {total_qty}"
        )

        if not booking.puPickUpAvailFrom_Date:
            booking.puPickUpAvailFrom_Date = convert_to_AU_SYDNEY_tz(
                datetime.now()
            ).date()

        file_path = (
            f"{settings.STATIC_PUBLIC}/pdfs/{booking.vx_freight_provider.lower()}_au"
        )

        # Build label with SSCC - one sscc should have one page label
        label_data = build_label_oper(
            booking=booking,
            file_path=file_path,
            total_qty=total_qty,
            sscc_list=sscc_list,
            sscc_lines=sscc_lines,
            need_zpl=False,
        )

        message = f"#379 {LOG_ID} - Successfully build label. Booking Id: {booking.b_bookingID_Visual}"
        logger.info(message)

        if label_data["urls"]:
            label_urls += label_data["urls"]

    file_path = f"{settings.STATIC_PUBLIC}/pdfs/lines_bulk"
    suffix = (
        len(line_ids)
        if len(line_ids) > 10
        else "_".join([str(line_id) for line_id in line_ids])
    )
    label_url = f"lines_bulk_label_{suffix}.pdf"
    entire_label_url = f"{file_path}/{label_url}"
    pdf_merge(label_urls, entire_label_url)
    return JsonResponse(
        {
            "success": "success",
            "message": "Label is successfully built!",
            "labelUrl": f"lines_bulk/{label_url}",
            "lineIds": line_ids,
        }
    )


@api_view(["GET"])
@permission_classes((IsAuthenticated,))
@authentication_classes([JSONWebTokenAuthentication])
def getAttachmentsHistory(request):
    fk_booking_id = request.GET.get("fk_booking_id")
    return_data = []

    try:
        resultObjects = []
        resultObjects = Dme_attachments.objects.filter(fk_id_dme_booking=fk_booking_id)
        for resultObject in resultObjects:
            # print('@bookingID', resultObject.fk_id_dme_booking.id)
            return_data.append(
                {
                    "pk_id_attachment": resultObject.pk_id_attachment,
                    "fk_id_dme_client": resultObject.fk_id_dme_client.pk_id_dme_client,
                    "desc": resultObject.desc,
                    "fileName": resultObject.fileName,
                    "linkurl": resultObject.linkurl,
                    "upload_Date": resultObject.upload_Date,
                    "is_hidden": resultObject.is_hidden,
                }
            )
        return JsonResponse({"history": return_data})
    except Exception as e:
        # print('@Exception', e)
        return JsonResponse({"history": ""})


@api_view(["GET"])
def getAttachmentContent(request):
    file_path = request.GET.get("file_path")
    try:
        response = requests.get(file_path)
        if response.status_code == 200:
            content = response.content
            if file_path.endswith(".eml"):
                # Parse .eml file content
                eml_message = message_from_string(content.decode())
                parsed_data = {
                    "subject": eml_message["subject"],
                    "body": eml_message.get_payload(),
                }
            elif file_path.endswith(".msg"):
                msg = Message(content)
                parsed_data = {"subject": msg.subject, "body": msg.body}

            else:
                parsed_data = {"message": "Unsupported file format."}
            return JsonResponse(parsed_data)
        else:
            return JsonResponse(
                {"error": "File not found at the provided URL."}, status=404
            )
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)


@api_view(["PUT"])
@permission_classes((IsAuthenticated,))
@authentication_classes([JSONWebTokenAuthentication])
def set_attachment(request):
    try:
        attachment = Dme_attachments.objects.filter(pk=request.data["pk"])
        if "is_hidden" in request.data:
            attachment.update(is_hidden=request.data["is_hidden"])
        elif "description" in request.data:
            attachment.update(desc=request.data["description"])
        return JsonResponse({"results": request.data})
    except Exception as e:
        # print('@Exception', e)
        return JsonResponse({"results": str(e)})


class SqlQueriesViewSet(viewsets.ViewSet):
    serializer_class = SqlQueriesSerializer
    queryset = Utl_sql_queries.objects.all()

    def list(self, request, pk=None):
        queryset = Utl_sql_queries.objects.all()
        serializer = SqlQueriesSerializer(queryset, many=True)
        return JsonResponse(
            {
                "results": serializer.data,
            },
            status=status.HTTP_200_OK,
        )

    @action(detail=True, methods=["get"])
    def get(self, request, pk, format=None):
        return_data = []
        try:
            resultObject = Utl_sql_queries.objects.get(id=pk)
            return JsonResponse({"result": SqlQueriesSerializer(resultObject).data})
        except Exception as e:
            # print("@Exception", e)
            return JsonResponse({"message": e}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=["post"])
    def add(self, request, pk=None):
        serializer = SqlQueriesSerializer(data=request.data)

        try:
            if serializer.is_valid():
                serializer.save()
                return Response(serializer.data, status=status.HTTP_201_CREATED)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            # print("Exception: ", e)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=["put"])
    def edit(self, request, pk, format=None):
        data = Utl_sql_queries.objects.get(pk=pk)
        serializer = SqlQueriesSerializer(data, data=request.data)

        try:
            if serializer.is_valid():
                serializer.save()
                return Response(serializer.data, status=status.HTTP_200_OK)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            # print("Exception: ", e)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=["delete"])
    def delete(self, request, pk=None):
        result = Utl_sql_queries.objects.get(pk=pk)
        result.delete()
        return Response(SqlQueriesSerializer(result).data)

    @action(detail=False, methods=["post"])
    def execute(self, request, pk=None):
        return_data = []
        query_tables = tables_in_query(request.data["sql_query"])
        serializer = SqlQueriesSerializer(data=request.data)

        if serializer.is_valid():
            with connection.cursor() as cursor:
                try:
                    cursor.execute(request.data["sql_query"])
                    columns = cursor.description
                    row = cursor.fetchall()
                    cursor.execute(
                        "SHOW KEYS FROM "
                        + query_tables[0]
                        + " WHERE Key_name = 'PRIMARY'"
                    )
                    row1 = cursor.fetchone()
                    result = []

                    for value in row:
                        tmp = {}

                        for index, column in enumerate(value):
                            tmp[columns[index][0]] = column
                        result.append(tmp)

                    return JsonResponse({"results": result, "tables": row1})
                except Exception as e:
                    # print("@Exception", e)
                    return JsonResponse({"message": str(e)}, status=400)
        else:
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=["post"])
    def update_query(self, request, pk=None):
        return_data = []
        if re.search("update", request.data["sql_query"], flags=re.IGNORECASE):
            with connection.cursor() as cursor:
                try:
                    cursor.execute(request.data["sql_query"])
                    columns = cursor.description
                    row = cursor.fetchall()
                    result = []
                    for value in row:
                        tmp = {}
                        for index, column in enumerate(value):
                            tmp[columns[index][0]] = column
                        result.append(tmp)
                    return JsonResponse({"results": result})
                except Exception as e:
                    # print('@Exception', e)
                    return JsonResponse({"error": str(e)})
        else:
            return JsonResponse({"error": "Sorry only UPDATE statement allowed"})


class FileUploadView(views.APIView):
    parser_classes = (MultiPartParser,)

    def post(self, request, format=None):
        user_id = request.user.id
        username = request.user.username
        file = request.FILES["file"]
        upload_option = request.POST.get("uploadOption", None)
        client_id = request.POST.get("clientId", None)
        result = None

        if upload_option == "import":
            uploader = request.POST["uploader"]
            file_name = upload_lib.upload_import_file(user_id, file, uploader)
            result = file_name
        elif upload_option in ["pod", "label", "attachment"]:
            booking_id = request.POST.get("bookingId", None)
            file_name = upload_lib.upload_attachment_file(
                user_id, file, booking_id, upload_option
            )
            result = file_name
        elif upload_option == "pricing-only":
            file_name = upload_lib.upload_pricing_only_file(
                user_id, username, file, upload_option
            )
            result = file_name
        elif upload_option == "pricing-rule":
            rule_type = request.POST.get("ruleType", None)
            file_name = upload_lib.upload_pricing_rule_file(
                user_id, username, file, upload_option, rule_type
            )
            result = file_name
        elif upload_option == "client-products":
            import_results = upload_lib.upload_client_products_file(
                user_id, username, client_id, file
            )
            result = import_results

        return Response(result)


@permission_classes([IsAuthenticatedOrReadOnly])
class FilesViewSet(viewsets.ModelViewSet):
    def list(self, request):
        file_type = request.GET["fileType"]
        dme_files = DME_Files.objects.filter(file_type=file_type)
        dme_files = dme_files.order_by("-z_createdTimeStamp")[:50]
        json_results = FilesSerializer(dme_files, many=True).data
        pk_booking_ids = []

        for json_data in json_results:
            if json_data["note"]:
                pk_booking_ids += json_data["note"].split(", ")

        bookings = Bookings.objects.filter(pk_booking_id__in=pk_booking_ids)

        for index, json_data in enumerate(json_results):
            b_bookingID_Visuals = []
            booking_ids = []

            for booking in bookings:
                if booking.pk_booking_id in json_data["note"]:
                    b_bookingID_Visuals.append(str(booking.b_bookingID_Visual))
                    booking_ids.append(str(booking.pk))

            json_results[index]["b_bookingID_Visual"] = ", ".join(b_bookingID_Visuals)
            json_results[index]["booking_id"] = ", ".join(booking_ids)

        return Response(json_results)

    def create(self, request):
        serializer = FilesSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class VehiclesViewSet(viewsets.ViewSet):
    serializer_class = VehiclesSerializer

    def list(self, request, pk=None):
        queryset = FP_vehicles.objects.all()
        serializer = VehiclesSerializer(queryset, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=["post"])
    def add(self, request, pk=None):
        try:
            request.data.pop("id", None)
            resultObject = FP_vehicles.objects.get_or_create(**request.data)

            return JsonResponse(
                {
                    "result": VehiclesSerializer(resultObject[0]).data,
                    "isCreated": resultObject[1],
                },
                status=200,
            )
        except Exception as e:
            trace_error.print()
            logger.error(f"Vehicle Add error: {str(e)}")
            return JsonResponse({"result": None}, status=400)


class AvailabilitiesViewSet(viewsets.ViewSet):
    serializer_class = AvailabilitiesSerializer

    def list(self, request, pk=None):
        queryset = FP_availabilities.objects.all()
        serializer = AvailabilitiesSerializer(queryset, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=["post"])
    def add(self, request, pk=None):
        try:
            request.data.pop("id", None)
            logger.info(f"Availability Create payload: {request.data}")
            resultObject = FP_availabilities.objects.get_or_create(**request.data)

            return JsonResponse(
                {
                    "result": AvailabilitiesSerializer(resultObject[0]).data,
                    "isCreated": resultObject[1],
                },
                status=200,
            )
        except Exception as e:
            logger.error(f"Availabilities Add error: {str(e)}")
            return JsonResponse({"result": None}, status=400)


class FPCostsViewSet(viewsets.ModelViewSet):
    queryset = FP_costs.objects.all()
    serializer_class = FPCostsSerializer

    @action(detail=False, methods=["post"])
    def add(self, request, pk=None):
        try:
            request.data.pop("id", None)
            resultObject = FP_costs.objects.get_or_create(**request.data)

            return JsonResponse(
                {
                    "result": FPCostsSerializer(resultObject[0]).data,
                    "isCreated": resultObject[1],
                },
                status=200,
            )
        except Exception as e:
            logger.error(f"[FP_COST ADD] {str(e)}")
            return JsonResponse({"result": None}, status=400)


class PricingRulesViewSet(viewsets.ViewSet):
    serializer_class = PricingRulesSerializer

    def list(self, request, pk=None):
        queryset = FP_pricing_rules.objects.all()
        serializer = PricingRulesSerializer(queryset, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=["post"])
    def add(self, request, pk=None):
        try:
            request.data.pop("id", None)
            resultObject = FP_pricing_rules.objects.get_or_create(**request.data)

            return JsonResponse(
                {
                    "result": PricingRulesSerializer(resultObject[0]).data,
                    "isCreated": resultObject[1],
                },
                status=200,
            )
        except Exception as e:
            logger.error(f"[FP_RULE ADD] {str(e)}, payload: {request.data}")
            return JsonResponse({"result": None}, status=400)


class BookingSetsViewSet(viewsets.ModelViewSet):
    queryset = BookingSets.objects.all()
    serializer_class = BookingSetsSerializer

    def list(self, request, pk=None):
        # TODO: should implement pagination here as well
        MAX_SETS_COUNT = 25
        queryset = BookingSets.objects.all()

        if get_clientname_with_request(request) != "dme":
            queryset = queryset.filter(
                z_createdByAccount=get_clientname_with_request(request)
            )

        queryset = queryset.order_by("-id")[:MAX_SETS_COUNT]
        serializer = BookingSetsSerializer(queryset, many=True)
        booking_ids = []
        for bookingset in serializer.data:
            booking_ids += bookingset["booking_ids"].split(", ")
        booking_ids = [int(booking_id) for booking_id in booking_ids if booking_id != '']
        filtered_bookings = Bookings.objects.filter(
            Q(pk__in=booking_ids) & (Q(z_label_url="") | Q(z_label_url__isnull=True))
        ).values_list("id", flat=True)
        filtered_booking_ids = list(filtered_bookings)
        bookingsets = []
        for bookingset in serializer.data:
            missing_labels_cnt = sum(
                1
                for booking_id in bookingset["booking_ids"].split(", ")
                if booking_id != '' and int(booking_id) in filtered_booking_ids
            )
            bookingset["missing_labels_cnt"] = missing_labels_cnt
            bookingsets.append(bookingset)
        return Response(bookingsets)

    def create(self, request, pk=None):
        bookingIds = []

        for bookingId in request.data["bookingIds"]:
            bookingIds.append(str(bookingId))

        request.data["booking_ids"] = ", ".join(bookingIds)
        request.data["status"] = "Created"
        request.data["z_createdByAccount"] = get_clientname_with_request(request)
        request.data["z_createdTimeStamp"] = str(datetime.now())

        # prevent empty string
        if not request.data["line_haul_date"]:
            request.data["line_haul_date"] = None

        serializer = BookingSetsSerializer(data=request.data)

        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class ClientEmployeesViewSet(viewsets.ModelViewSet):
    serializer_class = ClientEmployeesSerializer

    def get_queryset(self):
        user_id = int(self.request.user.id)
        dme_employee = DME_employees.objects.filter(fk_id_user=user_id).first()

        if dme_employee:
            client_employees = Client_employees.objects.filter(email__isnull=False)
        else:
            client_employee = Client_employees.objects.filter(
                fk_id_user=user_id
            ).first()
            client = DME_clients.objects.filter(
                pk_id_dme_client=int(client_employee.fk_id_dme_client_id)
            ).first()
            client_employees = Client_employees.objects.filter(
                fk_id_dme_client_id=client.pk_id_dme_client, email__isnull=False
            )

        return client_employees.order_by("name_first")


class ClientProductsViewSet(viewsets.ModelViewSet):
    serializer_class = ClientProductsSerializer
    queryset = Client_Products.objects.all()

    def get_client_id(self):
        user_id = int(self.request.user.id)
        dme_employee = DME_employees.objects.filter(fk_id_user=user_id).first()

        if dme_employee:
            client = self.request.query_params.get("clientId")
        else:
            client_employee = Client_employees.objects.filter(
                fk_id_user=user_id
            ).first()
            client = DME_clients.objects.filter(
                pk_id_dme_client=int(client_employee.fk_id_dme_client_id)
            ).first()

        return client

    def list(self, request, *args, **kwargs):
        client = self.get_client_id()
        client_products = Client_Products.objects.filter(
            fk_id_dme_client=client
        ).order_by("id")
        serializer = ClientProductsSerializer(client_products, many=True)

        return Response(serializer.data)

    def destroy(self, request, *args, **kwargs):
        id = self.kwargs["pk"]
        try:
            Client_Products.objects.filter(id=id).delete()
        except Exception as e:
            return Response({"msg": f"{e}"}, status=status.HTTP_400_BAD_REQUEST)

        return Response({id})


class ClientRasViewSet(viewsets.ModelViewSet):
    serializer_class = ClientRasSerializer
    queryset = Client_Ras.objects.all()


class ErrorViewSet(viewsets.ModelViewSet):
    serializer_class = ErrorSerializer
    queryset = DME_Error.objects.all()

    def list(self, request, pk=None):
        pk_booking_id = request.GET["pk_booking_id"]

        if pk_booking_id:
            queryset = DME_Error.objects.filter(fk_booking_id=pk_booking_id)
        else:
            queryset = DME_Error.objects.all()

        serializer = ErrorSerializer(queryset, many=True)
        return Response(serializer.data)


class ClientProcessViewSet(viewsets.ModelViewSet):
    serializer_class = ClientProcessSerializer

    def get_queryset(self):
        booking_id = self.request.GET["bookingId"]

        if booking_id:
            queryset = Client_Process_Mgr.objects.filter(fk_booking_id=booking_id)
        else:
            queryset = Client_Process_Mgr.objects.all()

        return queryset.order_by("id")


class AugmentAddressViewSet(viewsets.ModelViewSet):
    serializer_class = AugmentAddressSerializer
    queryset = DME_Augment_Address.objects.all()


class ClientViewSet(viewsets.ModelViewSet):
    serializer_class = ClientSerializer
    queryset = DME_clients.objects.all()


class RoleViewSet(viewsets.ModelViewSet):
    serializer_class = RoleSerializer
    queryset = DME_Roles.objects.all()


@permission_classes((IsAuthenticated,))
class SurchargeViewSet(viewsets.ModelViewSet):
    serializer_class = SurchargeSerializer

    def get_queryset(self):
        booking_id = self.request.GET.get("bookingId")
        queryset = Surcharge.objects.all()

        if booking_id:
            queryset = queryset.filter(booking_id=booking_id)

        return queryset.order_by("id")

    def update(self, request, pk=None):
        surcharge = Surcharge.objects.get(pk=pk)
        bulk_update = request.data.get("bulk_update")

        if bulk_update:
            surcharges = Surcharge.objects.filter(
                name=surcharge.name,
                fp_id=surcharge.fp_id,
                booked_date__gte=(surcharge.booked_date - timedelta(seconds=3)),
                booked_date__lte=(surcharge.booked_date + timedelta(seconds=3)),
            )

            try:
                for surcharge in surcharges:
                    data = {}
                    if request.data.get("update_visible_field"):
                        data["visible"] = request.data.get("visible")
                    if request.data.get("update_fp_field"):
                        data["fp"] = request.data.get("fp")
                    if request.data.get("update_service_name_field"):
                        data["name"] = request.data.get("name")
                    if request.data.get("update_connote_or_reference_field"):
                        data["connote_or_reference"] = request.data.get(
                            "connote_or_reference"
                        )
                    if request.data.get("update_booked_date_field"):
                        data["booked_date"] = request.data.get("booked_date")
                    if request.data.get("update_estimated_pickup_date_field"):
                        data["estimated_pu_date"] = request.data.get(
                            "estimated_pu_date"
                        )
                    if request.data.get("update_estimated_delivery_date_field"):
                        data["estimated_de_date"] = request.data.get(
                            "estimated_de_date"
                        )
                    if request.data.get("update_actual_pickup_date_field"):
                        data["actual_pu_date"] = request.data.get("actual_pu_date")
                    if request.data.get("update_actual_delivery_date_field"):
                        data["actual_de_date"] = request.data.get("actual_de_date")
                    if request.data.get("update_amount_field"):
                        data["amount"] = request.data.get("amount")
                    if request.data.get("update_quantity_field"):
                        data["qty"] = request.data.get("qty")

                    serializer = SurchargeSerializer(surcharge, data=data)
                    if serializer.is_valid():
                        serializer.save()
                    else:
                        error = f"Update Surcharges Error: {serializer.errors}"
                        logger.info(error)
                        raise Exception(error)
                return Response(
                    {"success": True, "is_bulk_update": True}, status=status.HTTP_200_OK
                )
            except Exception as e:
                return Response(
                    {f"message": str(e)}, status=status.HTTP_400_BAD_REQUEST
                )
        else:
            serializer = SurchargeSerializer(surcharge, data=request.data)

            if serializer.is_valid():
                serializer.save()
                return Response(serializer.data, status=status.HTTP_200_OK)
            else:
                logger.info(f"Update Surcharge Error: {str(serializer.errors)}")
                return Response(serializer.data, status=status.HTTP_400_BAD_REQUEST)

    def destroy(self, request, pk=None):
        surcharge = Surcharge.objects.get(pk=pk)
        type = request.data.get("type")

        if type == "single-delete":
            try:
                surcharge.delete()
                return Response(status=status.HTTP_200_OK)
            except Exception as e:
                logger.info(f"Delete Fp Status Error: {str(e)}")
                return Response(status=status.HTTP_400_BAD_REQUEST)
        else:
            surcharges = Surcharge.objects.filter(
                name=surcharge.name,
                fp_id=surcharge.fp_id,
                booked_date__gte=(surcharge.booked_date - timedelta(seconds=3)),
                booked_date__lte=(surcharge.booked_date + timedelta(seconds=3)),
            )

            for _iter in surcharges:
                _iter.delete()

            return Response(status=status.HTTP_200_OK)


@permission_classes((IsAuthenticated,))
class ChartsViewSet(viewsets.ViewSet):
    @action(detail=False, methods=["get"])
    def get_num_bookings_per_fp(self, request):
        try:
            startDate = request.GET.get("startDate")
            endDate = request.GET.get("endDate")

            result = (
                Bookings.objects.filter(
                    Q(b_status="Delivered")
                    & Q(b_dateBookedDate__range=[startDate, endDate])
                )
                .extra(select={"freight_provider": "vx_freight_provider"})
                .values("freight_provider")
                .annotate(deliveries=Count("vx_freight_provider"))
                .order_by("deliveries")
            )

            late_result = (
                Bookings.objects.filter(
                    Q(b_status="Delivered")
                    & Q(b_dateBookedDate__range=[startDate, endDate])
                    & Q(
                        s_21_Actual_Delivery_TimeStamp__gt=F(
                            "s_06_Latest_Delivery_Date_TimeSet"
                        )
                    )
                )
                .extra(select={"freight_provider": "vx_freight_provider"})
                .values("freight_provider")
                .annotate(late_deliveries=Count("vx_freight_provider"))
                .order_by("late_deliveries")
            )

            ontime_result = (
                Bookings.objects.filter(
                    Q(b_status="Delivered")
                    & Q(b_dateBookedDate__range=[startDate, endDate])
                    & Q(
                        s_21_Actual_Delivery_TimeStamp__lte=F(
                            "s_06_Latest_Delivery_Date_TimeSet"
                        )
                    )
                )
                .extra(select={"freight_provider": "vx_freight_provider"})
                .values("freight_provider")
                .annotate(ontime_deliveries=Count("vx_freight_provider"))
                .order_by("ontime_deliveries")
            )

            num_reports = list(result)
            num_late_reports = list(late_result)
            num_ontime_reports = list(ontime_result)

            for report in num_reports:
                for late_report in num_late_reports:
                    if report["freight_provider"] == late_report["freight_provider"]:
                        report["late_deliveries"] = late_report["late_deliveries"]
                        report["late_deliveries_percentage"] = math.ceil(
                            late_report["late_deliveries"] / report["deliveries"] * 100
                        )

                for ontime_report in num_ontime_reports:
                    if report["freight_provider"] == ontime_report["freight_provider"]:
                        report["ontime_deliveries"] = ontime_report["ontime_deliveries"]
                        report["ontime_deliveries_percentage"] = math.ceil(
                            ontime_report["ontime_deliveries"]
                            / report["deliveries"]
                            * 100
                        )

            return JsonResponse({"results": num_reports})
        except Exception as e:
            # print(f"Error #102: {e}")
            return JsonResponse({"results": [], "success": False, "message": str(e)})

    @action(detail=False, methods=["get"])
    def get_num_bookings_per_status(self, request):
        try:
            startDate = request.GET.get("startDate")
            endDate = request.GET.get("endDate")
            category_result = (
                Bookings.objects.filter(Q(b_dateBookedDate__range=[startDate, endDate]))
                .extra(select={"status": "b_status"})
                .values("status")
                .annotate(value=Count("b_status"))
                .order_by("value")
            )

            categories = []
            category_reports = list(category_result)

            for category_report in category_reports:
                if (
                    category_report["status"] is not None
                    and category_report["status"] != ""
                ):
                    utl_dme_status = Utl_dme_status.objects.filter(
                        dme_delivery_status=category_report["status"]
                    ).first()

                    if utl_dme_status:
                        category_report["status"] = (
                            utl_dme_status.dme_delivery_status_category
                            + "("
                            + category_report["status"]
                            + ")"
                        )
                        categories.append(category_report)

            return JsonResponse({"results": categories})
        except Exception as e:
            # print(f"Error #102: {e}")
            return JsonResponse({"results": [], "success": False, "message": str(e)})

    @action(detail=False, methods=["get"])
    def get_num_bookings_per_client(self, request):
        try:
            startDate = request.GET.get("startDate")
            endDate = request.GET.get("endDate")

            result = (
                Bookings.objects.filter(Q(b_dateBookedDate__range=[startDate, endDate]))
                .extra(select={"client_name": "b_client_name"})
                .values("client_name")
                .annotate(deliveries=Count("b_client_name"))
                .order_by("deliveries")
            )

            late_result = (
                Bookings.objects.filter(
                    Q(b_dateBookedDate__range=[startDate, endDate])
                    & Q(
                        s_21_Actual_Delivery_TimeStamp__gt=F(
                            "s_06_Latest_Delivery_Date_TimeSet"
                        )
                    )
                )
                .extra(select={"client_name": "b_client_name"})
                .values("client_name")
                .annotate(late_deliveries=Count("b_client_name"))
                .order_by("late_deliveries")
            )

            ontime_result = (
                Bookings.objects.filter(
                    Q(b_dateBookedDate__range=[startDate, endDate])
                    & Q(
                        s_21_Actual_Delivery_TimeStamp__lte=F(
                            "s_06_Latest_Delivery_Date_TimeSet"
                        )
                    )
                )
                .extra(select={"client_name": "b_client_name"})
                .values("client_name")
                .annotate(ontime_deliveries=Count("b_client_name"))
                .order_by("ontime_deliveries")
            )

            inv_sell_quoted_result = (
                Bookings.objects.filter(Q(b_dateBookedDate__range=[startDate, endDate]))
                .extra(select={"client_name": "b_client_name"})
                .values("client_name")
                .annotate(inv_sell_quoted=Sum("inv_sell_quoted"))
                .order_by("inv_sell_quoted")
            )

            inv_sell_quoted_override_result = (
                Bookings.objects.filter(Q(b_dateBookedDate__range=[startDate, endDate]))
                .extra(select={"client_name": "b_client_name"})
                .values("client_name")
                .annotate(inv_sell_quoted_override=Sum("inv_sell_quoted_override"))
                .order_by("inv_sell_quoted_override")
            )

            inv_cost_quoted_result = (
                Bookings.objects.filter(Q(b_dateBookedDate__range=[startDate, endDate]))
                .extra(select={"client_name": "b_client_name"})
                .values("client_name")
                .annotate(inv_cost_quoted=Sum("inv_cost_quoted"))
                .order_by("inv_cost_quoted")
            )

            deliveries_reports = list(result)
            inv_sell_quoted_reports = list(inv_sell_quoted_result)
            inv_sell_quoted_override_reports = list(inv_sell_quoted_override_result)
            inv_cost_quoted_reports = list(inv_cost_quoted_result)
            late_reports = list(late_result)
            ontime_reports = list(ontime_result)

            for report in deliveries_reports:
                for late_report in late_reports:
                    if report["client_name"] == late_report["client_name"]:
                        report["late_deliveries"] = late_report["late_deliveries"]

                for ontime_report in ontime_reports:
                    if report["client_name"] == ontime_report["client_name"]:
                        report["ontime_deliveries"] = ontime_report["ontime_deliveries"]

                for inv_sell_quoted_report in inv_sell_quoted_reports:
                    if report["client_name"] == inv_sell_quoted_report["client_name"]:
                        report["inv_sell_quoted"] = (
                            0
                            if not inv_sell_quoted_report["inv_sell_quoted"]
                            else round(
                                float(inv_sell_quoted_report["inv_sell_quoted"]), 2
                            )
                        )

                for inv_sell_quoted_override_report in inv_sell_quoted_override_reports:
                    if (
                        report["client_name"]
                        == inv_sell_quoted_override_report["client_name"]
                    ):
                        report["inv_sell_quoted_override"] = (
                            0
                            if not inv_sell_quoted_override_report[
                                "inv_sell_quoted_override"
                            ]
                            else round(
                                float(
                                    inv_sell_quoted_override_report[
                                        "inv_sell_quoted_override"
                                    ]
                                ),
                                2,
                            )
                        )

                for inv_cost_quoted_report in inv_cost_quoted_reports:
                    if report["client_name"] == inv_cost_quoted_report["client_name"]:
                        report["inv_cost_quoted"] = (
                            0
                            if not inv_cost_quoted_report["inv_cost_quoted"]
                            else round(
                                float(inv_cost_quoted_report["inv_cost_quoted"]), 2
                            )
                        )

            return JsonResponse({"results": deliveries_reports})
        except Exception as e:
            # print(f"Error #102: {e}")
            return JsonResponse({"results": [], "success": False, "message": str(e)})

    @action(detail=False, methods=["get"])
    def get_num_ready_bookings_per_fp(self, request):
        try:
            result = (
                Bookings.objects.filter(b_status="Ready for booking")
                .values("vx_freight_provider")
                .annotate(vx_freight_provider_count=Count("vx_freight_provider"))
                .order_by("vx_freight_provider_count")
            )
            return JsonResponse({"results": list(result)})
        except Exception as e:
            # print(f"Error #102: {e}")
            return JsonResponse({"results": [], "success": False, "message": str(e)})

    @action(detail=False, methods=["get"])
    def get_num_booked_bookings_per_fp(self, request):
        try:
            result = (
                Bookings.objects.filter(b_status="Booked")
                .values("vx_freight_provider")
                .annotate(vx_freight_provider_count=Count("vx_freight_provider"))
                .order_by("vx_freight_provider_count")
            )
            return JsonResponse({"results": list(result)})
        except Exception as e:
            # print(f"Error #102: {e}")
            return JsonResponse({"results": [], "success": False, "message": str(e)})

    @action(detail=False, methods=["get"])
    def get_num_rebooked_bookings_per_fp(self, request):
        try:
            result = (
                Bookings.objects.filter(b_status="Pickup Rebooked")
                .values("vx_freight_provider")
                .annotate(vx_freight_provider_count=Count("vx_freight_provider"))
                .order_by("vx_freight_provider_count")
            )
            return JsonResponse({"results": list(result)})
        except Exception as e:
            # print(f"Error #102: {e}")
            return JsonResponse({"results": [], "success": False, "message": str(e)})

    @action(detail=False, methods=["get"])
    def get_num_closed_bookings_per_fp(self, request):
        try:
            result = (
                Bookings.objects.filter(b_status="Closed")
                .values("vx_freight_provider")
                .annotate(vx_freight_provider_count=Count("vx_freight_provider"))
                .order_by("vx_freight_provider_count")
            )
            return JsonResponse({"results": list(result)})
        except Exception as e:
            # print(f"Error #102: {e}")
            return JsonResponse({"results": [], "success": False, "message": str(e)})

    @action(detail=False, methods=["get"])
    def get_num_month_bookings(self, request):
        try:
            result = (
                Bookings.objects.filter(b_status="Delivered")
                .extra(select={"month": "EXTRACT(month FROM b_dateBookedDate)"})
                .values("month")
                .annotate(count_items=Count("b_dateBookedDate"))
            )

            return JsonResponse({"results": list(result)})
        except Exception as e:
            # print(f"Error #102: {e}")
            return JsonResponse({"results": [], "success": False, "message": str(e)})

    @action(detail=False, methods=["get"])
    def get_num_year_bookings(self, request):
        try:
            result = (
                Bookings.objects.filter(b_status="Delivered")
                .extra(select={"year": "EXTRACT(year FROM b_dateBookedDate)"})
                .values("year")
                .annotate(count_items=Count("b_dateBookedDate"))
            )

            return JsonResponse({"results": list(result)})
        except Exception as e:
            # print(f"Error #102: {e}")
            return JsonResponse({"results": [], "success": False, "message": str(e)})

    @action(detail=False, methods=["get"])
    def get_num_active_bookings_per_client(self, request):
        try:
            result = (
                Bookings.objects.filter(
                    b_client_name__in=[
                        "Tempo Pty Ltd",
                        "Reworx",
                        "Plum Products Australia Ltd",
                        "Cinnamon Creations",
                        "Jason L",
                        "Bathroom Sales Direct",
                    ],
                    b_dateBookedDate__isnull=False,
                )
                .exclude(
                    b_status__in=[
                        "Closed",
                        "Cancelled",
                        "Ready for booking",
                        "Delivered",
                        "To Quote",
                        "Picking",
                        "Picked",
                        "On Hold",
                    ]
                )
                .extra(select={"b_client": "b_client_name"})
                .values("b_client")
                .annotate(inprogress=Count("b_client_name"))
                .order_by("inprogress")
            )
            num_reports = list(result)
            return JsonResponse({"results": num_reports})
        except Exception as e:
            # print(f"Error #102: {e}")
            return JsonResponse({"results": [], "success": False, "message": str(e)})


class PalletViewSet(NoUpdateMixin, NoDestroyMixin, viewsets.ModelViewSet):
    queryset = Pallet.objects.all()
    serializer_class = PalletSerializer
    permission_classes = (AllowAny,)


class FpStatusesViewSet(viewsets.ViewSet):
    serializer_class = FpStatusSerializer
    permission_classes = [permissions.IsAuthenticated]

    @action(detail=False, methods=["get"])
    @authentication_classes([JSONWebTokenAuthentication])
    def get_fp_statuses(self, request, pk=None):
        try:
            fp_name = request.GET.get("fp_name")
            queryset = Dme_utl_fp_statuses.objects.filter(fp_name=fp_name)
            serializer = FpStatusSerializer(queryset, many=True)
            return Response(serializer.data)
        except Exception as e:
            logger.info(f"Get Fp Statuses Error: {str(e)}")

    def create(self, request):
        serializer = FpStatusSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        else:
            logger.info(f"Create Fp Status Error: {str(e)}")
            return Response(serializer.data, status=status.HTTP_400_BAD_REQUEST)

    def update(self, request, pk=None):
        fp_status = Dme_utl_fp_statuses.objects.get(pk=pk)
        serializer = FpStatusSerializer(fp_status, data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_200_OK)
        else:
            logger.info(f"Create Fp Status Error: {str(e)}")
            return Response(serializer.data, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, pk=None):
        fp_status = Dme_utl_fp_statuses.objects.get(pk=pk)
        try:
            fp_status.delete()
            return Response(status=status.HTTP_200_OK)
        except Exception as e:
            logger.info(f"Delete Fp Status Error: {str(e)}")
            return Response(status=status.HTTP_400_BAD_REQUEST)


class DMEBookingCSNoteViewSet(viewsets.ModelViewSet):
    queryset = DMEBookingCSNote.objects.all().order_by("z_createdTimeStamp")
    serializer_class = DMEBookingCSNoteSerializer

    def list(self, request):
        booking_id = request.GET.get("bookingId")

        if booking_id:
            queryset = DMEBookingCSNote.objects.filter(booking_id=booking_id)
        else:
            queryset = DMEBookingCSNote.objects.all()

        serializer = DMEBookingCSNoteSerializer(queryset, many=True)
        return Response(serializer.data)

    def create(self, request):
        dme_employee = DME_employees.objects.get(fk_id_user_id=request.user.pk)
        request.data[
            "z_createdByAccount"
        ] = f"{dme_employee.name_first} {dme_employee.name_last}"
        serializer = DMEBookingCSNoteSerializer(data=request.data)
        if serializer.is_valid():
            cs_note = serializer.save()
            update_shared_booking(cs_note.booking, "cs-note")
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        else:
            logger.info(f"Create CS Note Error: {str(serializer.errors)}")
            return Response(serializer.data, status=status.HTTP_400_BAD_REQUEST)

    def destroy(self, request, pk=None):
        try:
            cs_note = DMEBookingCSNote.objects.get(pk=pk)
            serializer = DMEBookingCSNoteSerializer(cs_note)
            res_json = serializer.data
            cs_note.delete()
            return Response(res_json, status=status.HTTP_200_OK)
        except Exception as e:
            logger.info(f"Delete Fp Status Error: {str(e)}")
            return Response(status=status.HTTP_400_BAD_REQUEST)


@api_view(["GET"])
@permission_classes((AllowAny,))
def getStatus(request):
    return Response(status=status.HTTP_200_OK)
