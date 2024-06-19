import io
import time as t
import uuid
import json
import logging
import requests
import zipfile
from datetime import datetime, date, timedelta
from base64 import b64decode, b64encode

from django.conf import settings
from django.http import JsonResponse
from django.shortcuts import render, redirect
from django.db import transaction
from django.db.models import Q
from rest_framework import views, serializers, status
from rest_framework.response import Response
from rest_framework import authentication, permissions, viewsets
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import (
    IsAuthenticated,
    AllowAny,
    IsAuthenticatedOrReadOnly,
)
from rest_framework.status import HTTP_400_BAD_REQUEST, HTTP_200_OK, HTTP_201_CREATED
from rest_framework.decorators import (
    api_view,
    permission_classes,
    action,
)
from api.serializers_client import *
from api.serializers import (
    SimpleQuoteSerializer,
    SurchargeSerializer,
    FPStatusHistorySerializer,
)
from api.models import *
from api.common import (
    trace_error,
    constants as dme_constants,
    status_history,
    time as dme_time_lib,
)
from api.fp_apis.utils import (
    get_status_category_from_status,
    get_status_time_from_category,
)
from api.fp_apis.operations.surcharge.index import get_surcharges, gen_surcharges
from api.operations.pronto_xi.index import (
    send_info_back,
    update_note as update_pronto_note,
)
from api.operations.paperless import send_order_info
from api.operations.packing.bok import (
    reset_repack as bok_reset_repack,
    auto_repack as bok_auto_repack,
    manual_repack as bok_manual_repack,
)
from api.clients.plum import index as plum
from api.clients.tempo import index as tempo
from api.clients.tempo_big_w import index as tempo_big_w
from api.clients.bsd import index as bsd
from api.clients.jason_l import index as jason_l
from api.clients.biopak import index as biopak
from api.clients.aberdeen_paper import index as aberdeen_paper
from api.clients.anchor_packaging import index as anchor_packaging
from api.clients.jason_l.operations import (
    create_or_update_product as jasonL_create_or_update_product,
)
from api.clients.ariston_wire import index as ariston_wire
from api.clients.standard import index as standard
from api.clients.operations.index import get_client, get_warehouse, bok_quote
from api.clients.jason_l.constants import SERVICE_GROUP_CODES


logger = logging.getLogger(__name__)


class BOK_0_ViewSet(viewsets.ViewSet):
    permission_classes = (IsAuthenticatedOrReadOnly,)

    def list(self, request):
        bok_0_bookingkeys = BOK_0_BookingKeys.objects.all().order_by(
            "-z_createdTimeStamp"
        )[:50]
        serializer = BOK_0_Serializer(bok_0_bookingkeys, many=True)
        return Response(serializer.data)

    def create(self, request):
        serializer = BOK_0_Serializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=HTTP_201_CREATED)
        return Response(serializer.errors, status=HTTP_400_BAD_REQUEST)


class BOK_1_ViewSet(viewsets.ModelViewSet):
    queryset = BOK_1_headers.objects.all()
    serializer_class = BOK_1_Serializer
    permission_classes = (IsAuthenticatedOrReadOnly,)

    def list(self, request):
        bok_1_headers = BOK_1_headers.objects.all().order_by("-z_createdTimeStamp")[:50]
        serializer = BOK_1_Serializer(bok_1_headers, many=True)
        return Response(serializer.data)

    def create(self, request):
        """
        for BioPak
        """
        logger.info(f"@871 User: {request.user.username}")
        logger.info(f"@872 request payload - {request.data}")
        bok_1_header = request.data
        b_client_warehouse_code = bok_1_header["b_client_warehouse_code"]
        warehouse = Client_warehouses.objects.get(
            client_warehouse_code=b_client_warehouse_code
        )
        bok_1_header["fk_client_warehouse"] = warehouse.pk_id_client_warehouses
        bok_1_header["success"] = dme_constants.BOK_SUCCESS_2
        bok_1_header["client_booking_id"] = str(uuid.uuid4())
        serializer = BOK_1_Serializer(data=bok_1_header)

        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=HTTP_201_CREATED)
        else:
            logger.info(f"@841 BOK_1 POST - {serializer.errors}")
            return Response(serializer.errors, status=HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=["put"], permission_classes=[AllowAny])
    def update_freight_options(self, request, pk=None):
        """"""
        identifier = request.data.get("client_booking_id", None)
        logger.info(f"[UPDATE_FREIGHT_OPT]: {identifier}")

        if not identifier:
            return Response(
                {"message": "Wrong identifier."}, status=HTTP_400_BAD_REQUEST
            )

        try:
            bok_1 = BOK_1_headers.objects.get(client_booking_id=identifier)
            bok_1.b_027_b_pu_address_type = request.data.get("b_027_b_pu_address_type")
            bok_1.b_053_b_del_address_type = request.data.get(
                "b_053_b_del_address_type"
            )
            bok_1.b_019_b_pu_tail_lift = request.data.get("b_019_b_pu_tail_lift")
            bok_1.b_041_b_del_tail_lift = request.data.get("b_041_b_del_tail_lift")
            bok_1.b_072_b_pu_no_of_assists = request.data.get(
                "b_072_b_pu_no_of_assists", 0
            )
            bok_1.b_073_b_del_no_of_assists = request.data.get(
                "b_073_b_del_no_of_assists", 0
            )
            bok_1.b_078_b_pu_location = request.data.get("b_078_b_pu_location")
            bok_1.b_068_b_del_location = request.data.get("b_068_b_del_location")
            bok_1.b_074_b_pu_delivery_access = request.data.get(
                "b_074_b_pu_delivery_access"
            )
            bok_1.b_075_b_del_delivery_access = request.data.get(
                "b_075_b_del_delivery_access"
            )
            bok_1.b_079_b_pu_floor_number = request.data.get(
                "b_079_b_pu_floor_number", 0
            )
            bok_1.b_069_b_del_floor_number = request.data.get(
                "b_069_b_del_floor_number", 0
            )
            bok_1.b_080_b_pu_floor_access_by = request.data.get(
                "b_080_b_pu_floor_access_by"
            )
            bok_1.b_070_b_del_floor_access_by = request.data.get(
                "b_070_b_del_floor_access_by"
            )
            bok_1.b_076_b_pu_service = request.data.get("b_076_b_pu_service")
            bok_1.b_077_b_del_service = request.data.get("b_077_b_del_service")
            bok_1.b_081_b_pu_auto_pack = request.data.get("b_081_b_pu_auto_pack")
            # bok_1.b_091_send_quote_to_pronto = request.data.get(
            #     "b_091_send_quote_to_pronto", False
            # )

            bok_1.b_021_b_pu_avail_from_date = request.data.get(
                "b_021_b_pu_avail_from_date"
            )
            bok_1.b_022_b_pu_avail_from_time_hour = request.data.get(
                "b_022_b_pu_avail_from_time_hour"
            )
            bok_1.b_023_b_pu_avail_from_time_minute = request.data.get(
                "b_023_b_pu_avail_from_time_minute"
            )
            bok_1.b_024_b_pu_by_date = request.data.get("b_024_b_pu_by_date")
            bok_1.b_025_b_pu_by_time_hour = request.data.get("b_025_b_pu_by_time_hour")
            bok_1.b_026_b_pu_by_time_minute = request.data.get(
                "b_026_b_pu_by_time_minute"
            )
            bok_1.b_047_b_del_avail_from_date = request.data.get(
                "b_047_b_del_avail_from_date"
            )
            bok_1.b_048_b_del_avail_from_time_hour = request.data.get(
                "b_048_b_del_avail_from_time_hour"
            )
            bok_1.b_049_b_del_avail_from_time_minute = request.data.get(
                "b_049_b_del_avail_from_time_minute"
            )
            bok_1.b_050_b_del_by_date = request.data.get("b_050_b_del_by_date")
            bok_1.b_051_b_del_by_time_hour = request.data.get(
                "b_051_b_del_by_time_hour"
            )
            bok_1.b_052_b_del_by_time_minute = request.data.get(
                "b_052_b_del_by_time_minute"
            )
            bok_1.save()

            # Re-Gen Surcharges
            quotes = API_booking_quotes.objects.filter(
                fk_booking_id=bok_1.pk_header_id, is_used=False
            )
            bok_2s = BOK_2_lines.objects.filter(
                fk_header_id=bok_1.pk_header_id, is_deleted=False
            )
            fp_names = [quote.freight_provider for quote in quotes]
            fps = Fp_freight_providers.objects.filter(fp_company_name__in=fp_names)
            client = DME_clients.objects.get(dme_account_num=bok_1.fk_client_id)

            # Delete existing Surcharges
            Surcharge.objects.filter(quote__in=quotes).delete()

            for quote in quotes:
                _original_bok_2s = []
                _bok_2s = []
                for bok_2 in bok_2s:
                    if bok_2.b_093_packed_status == quote.packed_status:
                        _bok_2s.append(bok_2)
                for fp in fps:
                    if quote.freight_provider == fp.fp_company_name:
                        quote_fp = fp

                gen_surcharges(
                    bok_1,
                    _bok_2s,
                    bok_2s,
                    quote,
                    client,
                    quote_fp,
                    "bok_1",
                )

            res_json = {"success": True, "message": "Freigth options are updated."}
            return Response(res_json, status=HTTP_200_OK)
        except Exception as e:
            trace_error.print()
            logger.info(
                f"[UPDATE_FREIGHT_OPT] BOK Failure with identifier: {identifier}, reason: {str(e)}"
            )
            return Response({"success": False}, status=HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=["get"], permission_classes=[AllowAny])
    def get_boks_with_pricings(self, request):
        if settings.ENV == "local":
            t.sleep(2)

        client_booking_id = request.GET["identifier"]
        logger.info(
            f"#490 [get_boks_with_pricings] client_booking_id: {client_booking_id}"
        )

        if not client_booking_id:
            logger.info(f"#491 [get_boks_with_pricings] Error: Wrong identifier.")
            res_json = {"message": "Wrong identifier."}
            return Response(res_json, status=HTTP_400_BAD_REQUEST)

        try:
            bok_1 = BOK_1_headers.objects.get(client_booking_id=client_booking_id)
            bok_2s = BOK_2_lines.objects.filter(
                fk_header_id=bok_1.pk_header_id, is_deleted=False
            )
            bok_3s = BOK_3_lines_data.objects.filter(
                fk_header_id=bok_1.pk_header_id, is_deleted=False
            )
            quote_set = (
                API_booking_quotes.objects.prefetch_related("vehicle")
                .filter(
                    fk_booking_id=bok_1.pk_header_id,
                    is_used=False,
                )
                .exclude(client_mu_1_minimum_values__isnull=True)
            )
            client = DME_clients.objects.get(dme_account_num=bok_1.fk_client_id)

            result = BOK_1_Serializer(bok_1).data
            result["bok_2s"] = BOK_2_Serializer(bok_2s, many=True).data
            result["bok_3s"] = BOK_3_Serializer(bok_3s, many=True).data
            result["pricings"] = []
            best_quotes = quote_set

            if best_quotes:
                context = {"client_customer_mark_up": client.client_customer_mark_up}
                json_results = SimpleQuoteSerializer(
                    best_quotes, many=True, context=context
                ).data
                json_results = dme_time_lib.beautify_eta(
                    json_results, best_quotes, client
                )

                # Surcharge point
                for json_result in json_results:
                    quote = None

                    for _quote in best_quotes:
                        if _quote.pk == json_result["cost_id"]:
                            quote = _quote

                    context = {"client_mark_up_percent": client.client_mark_up_percent}
                    json_result["surcharges"] = SurchargeSerializer(
                        get_surcharges(quote), context=context, many=True
                    ).data

                result["pricings"] = json_results

            res_json = {"message": "Succesfully get bok and pricings.", "data": result}
            logger.info(f"#495 [get_boks_with_pricings] Success!")
            return Response(res_json, status=HTTP_200_OK)
        except Exception as e:
            logger.info(f"#499 [get_boks_with_pricings] Error: {e}")
            trace_error.print()
            return Response(
                {"message": "Couldn't find matching Booking."},
                status=HTTP_400_BAD_REQUEST,
            )

    @action(detail=False, methods=["patch"], permission_classes=[AllowAny])
    def book(self, request):
        if settings.ENV == "local":
            t.sleep(2)

        identifier = request.GET["identifier"]

        if not identifier:
            return Response(
                {"message": "Wrong identifier."}, status=HTTP_400_BAD_REQUEST
            )

        try:
            bok_1 = BOK_1_headers.objects.select_related("quote").get(
                client_booking_id=identifier
            )
            bok_2s = BOK_2_lines.objects.filter(fk_header_id=bok_1.pk_header_id)
            bok_3s = BOK_3_lines_data.objects.filter(fk_header_id=bok_1.pk_header_id)

            if bok_1.quote:
                bok_1.b_001_b_freight_provider = bok_1.quote.freight_provider
                bok_1.b_003_b_service_name = bok_1.quote.service_name
                bok_1.vx_serviceType_XXX = bok_1.quote.service_code
                bok_1.b_002_b_vehicle_type = (
                    bok_1.quote.vehicle.description if bok_1.quote.vehicle else None
                )
                send_order_info(bok_1)
                bok_1.save()

                for bok_2 in bok_2s:
                    bok_2.success = dme_constants.BOK_SUCCESS_4
                    bok_2.save()

                for bok_3 in bok_3s:
                    bok_3.success = dme_constants.BOK_SUCCESS_4
                    bok_3.save()

                bok_1.success = dme_constants.BOK_SUCCESS_4
                bok_1.save()

                logger.info(f"@843 [BOOK] BOK success with identifier: {identifier}")
                return Response({"success": True}, status=HTTP_200_OK)
            else:
                logger.error(f"@8430 [BOOK] BOK Failure with identifier: {identifier}")
                return Response(
                    {"success": False, "message": "Order doesn't have quote."},
                    status=HTTP_400_BAD_REQUEST,
                )
        except Exception as e:
            logger.error(f"@844 [BOOK] BOK Failure with identifier: {identifier}")
            logger.error(f"@845 [BOOK] BOK Failure: {str(e)}")
            return Response({"success": False}, status=HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=["delete"], permission_classes=[AllowAny])
    def cancel(self, request):
        if settings.ENV == "local":
            t.sleep(2)

        identifier = request.GET["identifier"]

        if not identifier:
            return Response(
                {"message": "Wrong identifier."}, status=HTTP_400_BAD_REQUEST
            )

        try:
            bok_1 = BOK_1_headers.objects.get(client_booking_id=identifier)
            BOK_2_lines.objects.filter(fk_header_id=bok_1.pk_header_id).delete()
            BOK_3_lines_data.objects.filter(fk_header_id=bok_1.pk_header_id).delete()
            bok_1.delete()
            logger.info(f"@840 [CANCEL] BOK success with identifier: {identifier}")
            return Response({"success": True}, status=HTTP_200_OK)
        except Exception as e:
            logger.info(
                f"@841 [CANCEL] BOK Failure with identifier: {identifier}, reason: {str(e)}"
            )
            return Response({"success": False}, status=HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=["get"], permission_classes=[AllowAny])
    def send_email(self, request):
        # Send `picking slip printed` email from DME itself

        LOG_ID = "[MANUAL PICKING SLIP EMAIL SENDER]"
        identifier = request.GET["identifier"]
        logger.info(f"@840 {LOG_ID} Identifier: {identifier}")

        if not identifier:
            message = f"Wrong identifier: {identifier}"
            logger.info(f"@841 {LOG_ID} message")
            return Response({"message": message}, status=HTTP_400_BAD_REQUEST)

        try:
            from api.operations.email_senders import send_picking_slip_printed_email

            bok_1 = BOK_1_headers.objects.get(client_booking_id=identifier)
            send_picking_slip_printed_email(
                bok_1.b_client_order_num,
                bok_1.b_092_booking_type,
                bok_1.b_053_b_del_address_type,
            )
            logger.info(f"@842 {LOG_ID} Success to send email: {identifier}")
            return Response({"success": True}, status=HTTP_200_OK)
        except Exception as e:
            trace_error.print()
            logger.info(
                f"@843 {LOG_ID} Failed to send email: {identifier}, reason: {str(e)}"
            )
            return Response({"success": False}, status=HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=["post"], permission_classes=[AllowAny])
    def select_pricing(self, request):
        try:
            cost_id = request.data["costId"]
            identifier = request.data["identifier"]
            isLocking = request.data["isLocking"]

            bok_1 = BOK_1_headers.objects.get(client_booking_id=identifier)
            quote = API_booking_quotes.objects.get(pk=cost_id)
            bok_1.b_001_b_freight_provider = quote.freight_provider
            bok_1.b_003_b_service_name = quote.service_name
            bok_1.vx_serviceType_XXX = quote.service_code
            bok_1.b_092_is_quote_locked = isLocking
            bok_1.quote = quote
            bok_1.save()

            # Send quote info back to Pronto
            # send_info_back(bok_1, bok_1.quote)

            # Update Pronto Note
            update_pronto_note(bok_1.quote, bok_1, [], "bok")

            fc_log = (
                FC_Log.objects.filter(client_booking_id=bok_1.client_booking_id)
                .order_by("z_createdTimeStamp")
                .last()
            )

            if fc_log:
                fc_log.new_quote = bok_1.quote
                fc_log.save()

            return Response({"success": True}, status=HTTP_200_OK)
        except:
            trace_error.print()
            return Response({"success": False}, status=HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=["post"], permission_classes=[AllowAny])
    def add_bok_line(self, request):
        """
        Used for "Jason L" only
        """
        LOG_ID = "[add_bok_line]"

        try:
            logger.info(f"{LOG_ID} {request.data}")
            line = request.data["line"]

            with transaction.atomic():
                if line.get("apply_to_product"):
                    jasonL_create_or_update_product(line)

                bok_2 = BOK_2_lines()
                bok_2.fk_header_id = line["fk_header_id"]
                bok_2.pk_booking_lines_id = str(uuid.uuid4())
                bok_2.l_001_type_of_packaging = line.get("l_001_type_of_packaging")
                bok_2.zbl_131_decimal_1 = line.get("zbl_131_decimal_1")
                bok_2.e_item_type = line.get("e_item_type")
                bok_2.l_002_qty = line.get("e_qty")
                bok_2.l_003_item = line.get("e_item")
                bok_2.l_004_dim_UOM = line.get("e_dimUOM")
                bok_2.l_005_dim_length = line.get("e_dimLength")
                bok_2.l_006_dim_width = line.get("e_dimWidth")
                bok_2.l_007_dim_height = line.get("e_dimHeight")
                bok_2.l_008_weight_UOM = line.get("e_weightUOM")
                bok_2.l_009_weight_per_each = line.get("e_weightPerEach")
                bok_2.v_client_pk_consigment_num = line.get("fk_header_id")
                bok_2.b_093_packed_status = line.get("b_093_packed_status")
                bok_2.save()

                API_booking_quotes.objects.filter(
                    fk_booking_id=line["fk_header_id"],
                    packed_status=bok_2.b_093_packed_status,
                ).update(is_used=True)

            return Response({"success": True}, status=HTTP_200_OK)
        except Exception as e:
            trace_error.print()
            logger.info(f"{LOG_ID} error: {str(e)}")
            return Response({"success": False}, status=HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=["put"], permission_classes=[AllowAny])
    def update_bok_line(self, request):
        """
        Used for "Jason L" only
        """
        LOG_ID = "[update_bok_line]"

        try:
            logger.info(f"{LOG_ID} {request.data}")
            line_id = request.data["line_id"]
            line = request.data["line"]

            bok_2 = BOK_2_lines.objects.get(pk=line_id)

            with transaction.atomic():
                if line.get("apply_to_product"):
                    jasonL_create_or_update_product(line)

                bok_2.l_001_type_of_packaging = line.get("l_001_type_of_packaging")
                bok_2.zbl_131_decimal_1 = line.get("zbl_131_decimal_1")
                bok_2.e_item_type = line.get("e_item_type")
                bok_2.l_002_qty = line.get("e_qty")
                bok_2.l_003_item = line.get("e_item")
                bok_2.l_004_dim_UOM = line.get("e_dimUOM")
                bok_2.l_005_dim_length = line.get("e_dimLength")
                bok_2.l_006_dim_width = line.get("e_dimWidth")
                bok_2.l_007_dim_height = line.get("e_dimHeight")
                bok_2.l_008_weight_UOM = line.get("e_weightUOM")
                bok_2.l_009_weight_per_each = line.get("e_weightPerEach")
                bok_2.save()

                API_booking_quotes.objects.filter(
                    fk_booking_id=bok_2.fk_header_id,
                    packed_status=bok_2.b_093_packed_status,
                ).update(is_used=True)

            return Response({"success": True}, status=HTTP_200_OK)
        except Exception as e:
            trace_error.print()
            logger.info(f"{LOG_ID} error: {str(e)}")
            return Response({"success": False}, status=HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=["delete"], permission_classes=[AllowAny])
    def delete_bok_line(self, request):
        """
        Used for "Jason L" only
        """
        LOG_ID = "[delete_bok_line]"

        try:
            logger.info(f"{LOG_ID} {request.data}")
            line_id = request.data["line_id"]
            bok_2 = BOK_2_lines.objects.get(pk=line_id)
            bok_2.delete()

            API_booking_quotes.objects.filter(
                fk_booking_id=bok_2.fk_header_id,
                packed_status=bok_2.b_093_packed_status,
            ).update(is_used=True)

            return Response({"success": True}, status=HTTP_200_OK)
        except Exception as e:
            trace_error.print()
            logger.info(f"{LOG_ID} error: {str(e)}")
            return Response({"success": False}, status=HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=["post"], permission_classes=[AllowAny])
    def repack(self, request, pk, format=None):
        LOG_ID = "[BOK REPACK LINES]"
        repack_status = request.data.get("repackStatus")
        pallet_id = request.data.get("palletId")
        bok_1 = self.get_object()
        client = DME_clients.objects.get(dme_account_num=bok_1.fk_client_id)
        logger.info(
            f"@200 {LOG_ID}, Bok pk: {pk}, Repack Status: {repack_status}, Client: {client}"
        )

        try:
            if repack_status and repack_status[0] == "-":
                bok_reset_repack(bok_1, repack_status[1:])
            elif "quote-" in repack_status:
                bok_quote(bok_1, repack_status[6:])
            elif repack_status == "auto":
                bok_auto_repack(bok_1, repack_status, pallet_id, client)
                bok_quote(bok_1, repack_status)
            else:
                bok_manual_repack(bok_1, repack_status)
                bok_quote(bok_1, repack_status)

            return JsonResponse({"success": True})
        except Exception as e:
            trace_error.print()
            logger.error(f"@204 {LOG_ID} Error: {str(e)}")
            return JsonResponse({"success": False}, status=HTTP_400_BAD_REQUEST)


class BOK_2_ViewSet(viewsets.ViewSet):
    permission_classes = (IsAuthenticatedOrReadOnly,)

    def list(self, request):
        bok_2_lines = BOK_2_lines.objects.all().order_by("-z_createdTimeStamp")[:50]
        serializer = BOK_2_Serializer(bok_2_lines, many=True)
        return Response(serializer.data)

    def create(self, request):
        logger.info(f"@873 User: {request.user.username}")
        logger.info(f"@874 request payload - {request.data}")
        bok_2_line = request.data
        bok_2_line["v_client_pk_consigment_num"] = bok_2_line["fk_header_id"]
        bok_2_line["b_093_packed_status"] = BOK_2_lines.ORIGINAL
        bok_2_line["success"] = dme_constants.BOK_SUCCESS_2
        serializer = BOK_2_Serializer(data=bok_2_line)

        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=HTTP_201_CREATED)
        else:
            logger.info(f"@842 BOK_2 POST - {serializer.errors}")
            return Response(serializer.errors, status=HTTP_400_BAD_REQUEST)


class BOK_3_ViewSet(viewsets.ViewSet):
    permission_classes = (IsAuthenticatedOrReadOnly,)

    def list(self, request):
        bok_3_lines_data = BOK_3_lines_data.objects.all().order_by(
            "-z_createdTimeStamp"
        )
        serializer = BOK_3_Serializer(bok_3_lines_data, many=True)
        return Response(serializer.data)


@api_view(["POST"])
@permission_classes((AllowAny,))
def quick_pricing(request):
    LOG_ID = "[QUICK PRICING]"
    user = request.user
    logger.info(f"{LOG_ID} Requester: {user.username}")
    logger.info(f"{LOG_ID} Payload: {request.data}")

    try:
        results = standard.quick_pricing(request.data)

        if results:
            logger.info(
                f"@819 {LOG_ID} Success! \nPayload: {request.data}\nResults: {results}"
            )
            return Response({"success": True, "results": results})
        else:
            message = "Pricing cannot be returned due to incorrect address information."
            logger.info(f"@827 {LOG_ID} {message}")
            res_json = {"success": False, "code": "invalid_request", "message": message}
            return Response(res_json, status=HTTP_400_BAD_REQUEST)
    except Exception as e:
        logger.info(f"@829 {LOG_ID} Exception: {str(e)}")
        trace_error.print()
        res_json = {"success": False, "message": str(e)}
        return Response(res_json, status=HTTP_400_BAD_REQUEST)


@api_view(["POST"])
def partial_pricing(request):
    LOG_ID = "[PARTIAL PRICING]"
    user = request.user
    logger.info(f"@810 {LOG_ID} Requester: {user.username}")
    logger.info(f"@811 {LOG_ID} Payload: {request.data}")

    if user.username == "spojit_user_01":
        dme_account_num = request.data.get("fk_client_id")
        client = get_client(user, dme_account_num)
    else:
        client = get_client(user)
        warehouse = get_warehouse(client)
        dme_account_num = client.dme_account_num

    try:
        if dme_account_num == "4ac9d3ee-2558-4475-bdbb-9d9405279e81":  # Aberdeen Paper
            warehouse = get_warehouse(client, "ABP_SUNSHINE")
            results = aberdeen_paper.partial_pricing(request.data, client, warehouse)
        elif dme_account_num == "461162D2-90C7-BF4E-A905-000000000004":  # Plum
            results = plum.partial_pricing(request.data, client, warehouse)
        elif dme_account_num == "1af6bcd2-6148-11eb-ae93-0242ac130002":  # Jason L
            results = jason_l.partial_pricing(request.data, client, warehouse)

        if results:
            logger.info(
                f"@819 {LOG_ID} Success! \nPayload: {request.data}\nResults: {results}"
            )
            return Response({"success": True, "results": results})
        else:
            message = "Pricing cannot be returned due to incorrect address information."
            logger.info(f"@827 {LOG_ID} {message}")
            res_json = {"success": False, "code": "invalid_request", "message": message}
            return Response(res_json, status=HTTP_400_BAD_REQUEST)
    except Exception as e:
        logger.info(f"@829 {LOG_ID} Exception: {str(e)}")
        trace_error.print()
        res_json = {"success": False, "message": str(e)}
        return Response(res_json, status=HTTP_400_BAD_REQUEST)


@api_view(["POST"])
def fetch_bsd_order(request):
    """
    called as `fetch-bsd-order`

    request when fetch a BSD Order from WooCommerce
    """
    LOG_ID = "[Fetch BSD Order]"
    user = request.user
    logger.info(f"@830 {LOG_ID} Requester: {user.username}")
    logger.info(f"@831 {LOG_ID} Payload: {request.data}")
    time1 = t.time()

    try:
        order_num = request.data["orderNumber"]
        result = bsd.fetch_order(order_num)
        # message = f"Successfully fetched. {order_num}"
        # logger.info(f"#838 {LOG_ID} {message}")
        time2 = t.time()
        logger.info(
            f"\n#838 {LOG_ID} Requester: {user.username}\nSpent time: {str(int(round(time2 - time1)))}s\n"
        )
        return JsonResponse(result, status=HTTP_200_OK)
    except Exception as e:
        logger.info(f"@839 {LOG_ID} Exception: {str(e)}")
        trace_error.print()
        time2 = t.time()
        logger.info(
            f"\n#838 {LOG_ID} Requester: {user.username}\nSpent time: {str(int(round(time2 - time1)))}s\n"
        )
        res_json = {
            "success": False,
            "message": str(e),
        }
        return Response(res_json, status=HTTP_400_BAD_REQUEST)


@api_view(["POST", "PUT"])
def push_boks(request):
    """
    PUSH api (bok_1, bok_2, bok_3)
    """
    LOG_ID = "[PUSH BOKS]"
    user = request.user
    logger.info(f"@800 {LOG_ID} Requester: {user.username}")
    logger.info(f"@801 {LOG_ID} Payload: {request.data}")
    time1 = t.time()

    if user.username == "spojit_user_01":
        dme_account_num = request.data["booking"]["fk_client_id"]
        client = get_client(user, dme_account_num)
    else:
        client = get_client(user)
        dme_account_num = client.dme_account_num

        bok_1 = request.data["booking"]
        if bok_1.get("zb_101_text_1") == "02_Microwave_Portal_Collections":
            dme_account_num = request.data["booking"]["fk_client_id"]
            client = get_client(user, dme_account_num)

    if not dme_account_num:
        msg = "Error: no account number."
        logger.info(f"@802 {LOG_ID} {msg}")
        res_json = {"success": False, "message": str(msg)}
        return Response(res_json, status=HTTP_400_BAD_REQUEST)

    try:
        if dme_account_num == "4ac9d3ee-2558-4475-bdbb-9d9405279e81":  # Aberdeen Paper
            result = aberdeen_paper.push_boks(
                payload=request.data,
                client=client,
                username=user.username,
                method=request.method,
            )
        elif dme_account_num == "461162D2-90C7-BF4E-A905-000000000004":  # Plum
            result = plum.push_boks(
                payload=request.data,
                client=client,
                username=user.username,
                method=request.method,
            )
        elif dme_account_num == "1af6bcd2-6148-11eb-ae93-0242ac130002":  # Jason L
            result = jason_l.push_boks(
                payload=request.data,
                client=client,
                username=user.username,
                method=request.method,
            )
        elif dme_account_num == "37C19636-C5F9-424D-AD17-05A056A8FBDB":  # Tempo
            result = tempo.push_boks(
                payload=request.data,
                client=client,
                username=user.username,
                method=request.method,
            )
        elif dme_account_num == "d69f550a-9327-4ff9-bc8f-242dfca00f7e":  # Tempo Big W
            result = tempo_big_w.push_boks(
                payload=request.data,
                client=client,
                username=user.username,
                method=request.method,
            )
        elif (
            dme_account_num == "9e72da0f-77c3-4355-a5ce-70611ffd0bc8"
        ):  # BSD - Bathroom Sales Direct
            result = bsd.push_boks(
                payload=request.data,
                client=client,
                username=user.username,
                method=request.method,
            )
        elif (
            dme_account_num == "49294ca3-2adb-4a6e-9c55-9b56c0361953"
        ):  # Anchor Packaging
            result = anchor_packaging.push_boks(
                payload=request.data,
                client=client,
                username=user.username,
                method=request.method,
            )
        elif dme_account_num == "7EAA4B16-484B-3944-902E-BC936BFEF535":  # Biopak
            result = biopak.push_boks(
                payload=request.data,
                client=client,
            )
        elif dme_account_num == "c8f0b7fc-7088-498b-bf3e-ec0fb8dc8851":  # Ariston Wire
            result = ariston_wire.push_boks(
                payload=request.data,
                client=client,
                username=user.username,
                method=request.method,
            )
        else:  # Standard Client
            result = standard.push_boks(request.data, client)

        logger.info(f"@828 {LOG_ID} Push BOKS success!, 201_created")
        time2 = t.time()
        logger.info(
            f"\n#838 {LOG_ID} Requester: {user.username}\nSpent time: {str(int(round(time2 - time1)))}s\n"
        )
        return JsonResponse(result, status=HTTP_201_CREATED)
    except Exception as e:
        logger.info(f"@829 {LOG_ID} Exception: {str(e)}")
        trace_error.print()
        res_json = {"success": False, "message": str(e)}
        return Response(res_json, status=HTTP_400_BAD_REQUEST)


@api_view(["POST"])
def scanned(request):
    """
    called as `get_label`

    request when item(s) is picked(scanned) at warehouse
    should response LABEL if payload is correct
    """
    LOG_ID = "[SCANNED]"
    user = request.user
    logger.info(f"@830 {LOG_ID} Requester: {user.username}")
    logger.info(f"@831 {LOG_ID} Payload: {request.data}")
    time1 = t.time()

    try:
        client = get_client(user)
        dme_account_num = client.dme_account_num

        if dme_account_num == "461162D2-90C7-BF4E-A905-000000000004":  # Plum
            result = plum.scanned(payload=request.data, client=client)
        elif dme_account_num == "1af6bcd2-6148-11eb-ae93-0242ac130002":  # Jason L
            result = jason_l.scanned(payload=request.data, client=client)

        message = f"Successfully scanned."
        logger.info(f"#838 {LOG_ID} {message}")
        time2 = t.time()
        logger.info(
            f"\n#838 {LOG_ID} Requester: {user.username}\nSpent time: {str(int(round(time2 - time1)))}s\n"
        )
        return JsonResponse(result, status=HTTP_200_OK)
    except Exception as e:
        logger.info(f"@839 {LOG_ID} Exception: {str(e)}")
        trace_error.print()
        time2 = t.time()
        logger.info(
            f"\n#838 {LOG_ID} Requester: {user.username}\nSpent time: {str(int(round(time2 - time1)))}s\n"
        )
        res_json = {
            "success": False,
            "message": str(e),
            "labelUrl": f"{settings.WEB_SITE_URL}/label/scan-failed?reason=unknown",
        }
        return Response(res_json, status=HTTP_400_BAD_REQUEST)


@api_view(["POST"])
def ready_boks(request):
    """
    When it is ready(picked all items) on Warehouse
    """
    LOG_ID = "[READY]"
    user = request.user
    logger.info(f"@840 {LOG_ID} Requester: {user.username}")
    logger.info(f"@841 {LOG_ID} Payload: {request.data}")

    try:
        client = get_client(user)
        dme_account_num = client.dme_account_num

        if dme_account_num == "461162D2-90C7-BF4E-A905-000000000004":  # Plum
            result = plum.ready_boks(payload=request.data, client=client)
        elif dme_account_num == "1af6bcd2-6148-11eb-ae93-0242ac130002":  # Jason L
            result = jason_l.ready_boks(payload=request.data, client=client)

        logger.info(f"#848 {LOG_ID} {result}")
        return Response({"success": True, "message": result})
    except Exception as e:
        logger.info(f"@849 {LOG_ID} Exception: {str(e)}")
        trace_error.print()
        res_json = {"success": False, "message": str(e)}
        return Response(res_json, status=HTTP_400_BAD_REQUEST)


@api_view(["GET"])
def reprint_label(request):
    """
    get label(already built)
    """
    LOG_ID = "[REPRINT]"
    user = request.user
    logger.info(f"@850 {LOG_ID} Requester: {user.username}")
    logger.info(f"@851 {LOG_ID} params: {request.GET}")

    try:
        client = get_client(user)
        dme_account_num = client.dme_account_num

        if dme_account_num == "461162D2-90C7-BF4E-A905-000000000004":  # Plum
            result = plum.reprint_label(params=request.GET, client=client)
        # elif dme_account_num == "1af6bcd2-6148-11eb-ae93-0242ac130002":  # Jason L
        #     result = jason_l.reprint_label(params=request.GET, client=client)
        elif dme_account_num == "7EAA4B16-484B-3944-902E-BC936BFEF535":  # BioPak
            result = biopak.reprint_label(params=request.GET, client=client)

        logger.info(f"#858 {LOG_ID} {json.dumps(result, indent=4)[:64]}")
        return Response(result)
    except Exception as e:
        logger.info(f"@859 {LOG_ID} Exception: {str(e)}")
        trace_error.print()
        res_json = {"success": False, "message": str(e)}
        return Response(res_json, status=HTTP_400_BAD_REQUEST)


@transaction.atomic
@api_view(["POST"])
def manifest_boks(request):
    """
    MANIFEST api
    """
    LOG_ID = "[MANIFEST]"
    user = request.user
    logger.info(f"@860 {LOG_ID} Requester: {user.username}")
    logger.info(f"@861 {LOG_ID} Payload: {request.data}")

    try:
        client = get_client(user)
        dme_account_num = client.dme_account_num

        if dme_account_num == "461162D2-90C7-BF4E-A905-000000000004":  # Plum
            result = plum.manifest(
                payload=request.data,
                client=client,
                username=user.username,
            )

        logger.info(f"#858 {LOG_ID} {result}")
        return Response(result)
    except Exception as e:
        logger.info(f"@859 {LOG_ID} Exception: {str(e)}")
        trace_error.print()
        res_json = {"success": False, "message": str(e)}
        return Response(res_json, status=HTTP_400_BAD_REQUEST)


@api_view(["GET"])
@permission_classes((AllowAny,))
def quote_count(request):
    """
    GET quote count
    """
    identifier = request.GET.get("identifier")
    bok_1 = BOK_1_headers.objects.filter(pk_auto_id=identifier).first()

    if not bok_1:
        return Response(
            {
                "code": "does_not_exist",
                "message": "Could not find BOK",
            },
            status=HTTP_400_BAD_REQUEST,
        )

    quotes = API_booking_quotes.objects.filter(
        fk_booking_id=bok_1.pk_header_id, is_used=False
    ).exclude(client_mu_1_minimum_values__isnull=True)

    if bok_1.zb_104_text_4 == "In Progress":
        quote_status = "in_progress"
    else:
        quote_status = "finished"

    return Response(
        {
            "code": "does_exist",
            "message": "",
            "result": {"quote_count": quotes.count(), "quote_status": quote_status},
        },
        status=HTTP_200_OK,
    )


@api_view(["GET"])
@permission_classes((AllowAny,))
def get_delivery_status(request):
    """
    GET request should have `identifier` param

    If length is over 32 - `b_client_booking_ref_num`
    """

    from api.fp_apis.utils import get_dme_status_from_fp_status

    identifier = request.GET.get("identifier")
    quote_data = {}
    last_milestone = "Delivered"

    # 1. Try to find from dme_bookings table
    booking = Bookings.objects.filter(
        Q(b_client_booking_ref_num=identifier) | Q(pk_booking_id=identifier)
    ).first()

    if booking:
        client = DME_clients.objects.get(dme_account_num=booking.kf_client_id)
        b_status = booking.b_status
        quote = booking.api_booking_quote

        # Category
        category = get_status_category_from_status(b_status)
        if not category:
            logger.info(
                f"#301 - unknown_status - identifier={identifier}, status={b_status}"
            )
            return Response(
                {
                    "code": "unknown_status",
                    "message": "Please contact DME support center. <bookings@deliver-me.com.au>",
                    "step": None,
                    "status": None,
                },
                status=HTTP_400_BAD_REQUEST,
            )

        status_histories = Dme_status_history.objects.filter(
            fk_booking_id=booking.pk_booking_id
        ).order_by("-z_createdTimeStamp")
        apls = Api_booking_confirmation_lines.objects.filter(
            fk_booking_id=booking.pk_booking_id
        ).exclude(api_artical_id__isnull=True)
        apls_json = []

        for apl in apls:
            apls_json.append(
                {
                    "id": apl.pk,
                    "service_provider": apl.service_provider,
                    "api_artical_id": apl.api_artical_id,
                    "api_consignment_id": apl.api_consignment_id,
                    "api_status": apl.api_status,
                    "fp_event_date": apl.fp_event_date,
                    "fp_event_time": apl.fp_event_time,
                }
            )

        last_updated = ""
        if status_histories and status_histories.first().event_time_stamp:
            last_updated = dme_time_lib.convert_to_AU_SYDNEY_tz(
                status_histories.first().event_time_stamp
            ).strftime("%d/%m/%Y %H:%M")

        booking_lines = Booking_lines.objects.filter(
            fk_booking_id=booking.pk_booking_id
        )

        booking_lines = booking_lines.exclude(
            zbl_102_text_2__in=SERVICE_GROUP_CODES
        ).only(
            "pk_lines_id",
            "e_type_of_packaging",
            "e_qty",
            "e_item",
            "e_item_type",
            "e_dimUOM",
            "e_dimLength",
            "e_dimWidth",
            "e_dimHeight",
            "e_Total_KG_weight",
        )

        original_lines = booking_lines.filter(packed_status=Booking_lines.ORIGINAL)
        original_lines = original_lines.order_by("pk_lines_id")
        packed_lines = booking_lines.filter(packed_status=Booking_lines.SCANNED_PACK)
        booking_lines = booking_lines.order_by("pk_lines_id")

        booking_dict = {
            "uid": booking.pk,
            "b_client_name": booking.b_client_name,
            "b_client_name_sub": booking.b_client_name_sub,
            "b_bookingID_Visual": booking.b_bookingID_Visual,
            "b_client_order_num": booking.b_client_order_num,
            "b_client_sales_inv_num": booking.b_client_sales_inv_num,
            "b_028_b_pu_company": booking.puCompany,
            "b_029_b_pu_address_street_1": booking.pu_Address_Street_1,
            "b_030_b_pu_address_street_2": booking.pu_Address_street_2,
            "b_032_b_pu_address_suburb": booking.pu_Address_Suburb,
            "b_031_b_pu_address_state": booking.pu_Address_State,
            "b_034_b_pu_address_country": booking.pu_Address_Country,
            "b_033_b_pu_address_postalcode": booking.pu_Address_PostalCode,
            "b_035_b_pu_contact_full_name": booking.pu_Contact_F_L_Name,
            "b_037_b_pu_email": booking.pu_Email,
            "b_038_b_pu_phone_main": booking.pu_Phone_Main,
            "b_054_b_del_company": booking.deToCompanyName,
            "b_055_b_del_address_street_1": booking.de_To_Address_Street_1,
            "b_056_b_del_address_street_2": booking.de_To_Address_Street_2,
            "b_058_b_del_address_suburb": booking.de_To_Address_Suburb,
            "b_057_b_del_address_state": booking.de_To_Address_State,
            "b_060_b_del_address_country": booking.de_To_Address_Country,
            "b_059_b_del_address_postalcode": booking.de_To_Address_PostalCode,
            "b_061_b_del_contact_full_name": booking.de_to_Contact_F_LName,
            "b_063_b_del_email": booking.de_Email,
            "b_064_b_del_phone_main": booking.de_to_Phone_Main,
            "b_000_3_consignment_number": booking.v_FPBookingNumber,
            "s_06_Latest_Delivery_Date_Time_Override": booking.s_06_Latest_Delivery_Date_Time_Override,
            "vx_freight_provider": booking.vx_freight_provider,
            "vx_serviceName": booking.vx_serviceName,
            "z_pod_signed_url": booking.z_pod_signed_url,
            "z_pod_url": booking.z_pod_url,
            "pusher": booking.x_booking_Created_With,
        }

        def serialize_lines(lines, need_product=False):
            _lines = []
            for line in lines:
                product = ""

                if need_product:
                    try:
                        product = Client_Products.objects.get(
                            child_model_number=line.e_item_type
                        ).description
                    except Exception as e:
                        logger.error(f"Client product doesn't exist: {e}")
                        pass

                _lines.append(
                    {
                        "e_type_of_packaging": line.e_type_of_packaging,
                        "e_qty": line.e_qty,
                        "e_item": line.e_item,
                        "e_item_type": line.e_item_type,
                        "e_dimUOM": line.e_dimUOM,
                        "e_dimLength": line.e_dimLength,
                        "e_dimWidth": line.e_dimWidth,
                        "e_dimHeight": line.e_dimHeight,
                        "e_Total_KG_weight": line.e_Total_KG_weight,
                        "product": product,
                    }
                )

            return _lines

        original_lines = serialize_lines(original_lines, True)
        packed_lines = serialize_lines(packed_lines, False)

        json_quote = None

        if quote:
            context = {"client_customer_mark_up": client.client_customer_mark_up}
            quote_data = SimpleQuoteSerializer(quote, context=context).data
            json_quote = dme_time_lib.beautify_eta([quote_data], [quote], client)[0]

        if b_status in [
            "In Transit",
            "Partially In Transit",
            "On-Forwarded",
            "Futile Delivery",
            "Delivery Delayed",
            "Delivery Rebooked",
            "Partially Delivered",
        ]:
            step = 1
        elif b_status in [
            "On Board for Delivery",
        ]:
            step = 2
        elif b_status in [
            "Collected by Customer",
            "Delivered",
            "Lost In Transit",
            "Damaged",
            "Returning",
            "Returned",
            "Closed",
            "Cancelled",
            "On Hold",
            "Cancel Requested",
        ]:
            step = 3
            last_milestone = b_status if b_status != "Collected" else "Delivered"
        else:
            step = 0
            b_status = "Processing"

        steps = [
            "Processing",
            "Booked",
            "Transit",
            "On Board for Delivery",
            "Complete",
        ]

        timestamps = []
        for index, item in enumerate(steps):
            if index == 0:
                timestamps.append(
                    dme_time_lib.convert_to_AU_SYDNEY_tz(
                        booking.z_CreatedTimestamp
                    ).strftime("%d/%m/%Y %H:%M")
                    if booking and booking.z_CreatedTimestamp
                    else ""
                )
            elif index >= step:
                timestamps.append("")
            else:
                if (
                    category == "Complete"
                    and not booking.b_status in ["Closed", "Cancelled"]
                    and index == 4
                ):
                    delivery_date = ""
                    if booking.s_21_Actual_Delivery_TimeStamp:
                        delivery_date = booking.s_21_Actual_Delivery_TimeStamp.strftime(
                            "%d/%m/%Y %H:%M"
                        )
                    elif booking.z_ModifiedTimestamp:
                        delivery_date = booking.z_ModifiedTimestamp.strftime(
                            "%d/%m/%Y %H:%M"
                        )
                    elif booking.b_dateBookedDate:
                        delivery_date = booking.b_dateBookedDate.strftime(
                            "%d/%m/%Y %H:%M"
                        )
                    elif booking.puPickUpAvailFrom_Date:
                        delivery_date = booking.puPickUpAvailFrom_Date.strftime(
                            "%d/%m/%Y %H:%M"
                        )
                    elif booking.z_CreatedTimestamp:
                        delivery_date = booking.z_CreatedTimestamp.strftime(
                            "%d/%m/%Y %H:%M"
                        )
                    else:
                        delivery_date = ""
                    timestamps.append(delivery_date)
                else:
                    status_time = get_status_time_from_category(
                        booking.pk_booking_id, item
                    )
                    timestamps.append(
                        status_time.strftime("%d/%m/%Y %H:%M") if status_time else None
                    )

        if step == 0:
            from api.utils import get_eta_de_by

            eta = get_eta_de_by(booking, booking.api_booking_quote)
            eta = eta.strftime("%d/%m/%Y %H:%M")
        else:
            from api.utils import get_eta_pu_by, get_eta_de_by

            s_06 = booking.get_s_06()

            if not s_06:
                booking.s_05_Latest_Pick_Up_Date_TimeSet = get_eta_pu_by(booking)
                booking.s_06_Latest_Delivery_Date_TimeSet = get_eta_de_by(
                    booking, booking.api_booking_quote
                )
                booking.save()
                s_06 = booking.s_06_Latest_Delivery_Date_TimeSet

            eta = s_06.strftime("%d/%m/%Y %H:%M")
        try:
            fp_status_histories = (
                FP_status_history.objects.values(
                    "id", "status", "desc", "event_timestamp"
                )
                .filter(booking_id=booking.id)
                .order_by("-id")
            )
            fp_status_histories = [
                {
                    **item,
                    "desc": get_dme_status_from_fp_status(
                        booking.vx_freight_provider, item["status"]
                    )
                    if (
                        not item["desc"]
                        or str(booking.b_bookingID_Visual) in item["desc"]
                    )
                    else item["desc"],
                }
                for item in fp_status_histories
            ]
        except Exception as e:
            logger.info(f"Get FP status history error: {str(e)}")
            fp_status_histories = []

        return Response(
            {
                "step": step,
                "status": b_status,
                "last_updated": last_updated,
                "quote": json_quote,
                "booking": booking_dict,
                "original_lines": original_lines,
                "packed_lines": packed_lines,
                "eta_date": eta,
                "last_milestone": last_milestone,
                "timestamps": timestamps,
                "logo_url": client.logo_url,
                "scans": fp_status_histories,
                "apls": apls_json,
            }
        )

    # 2. Try to find from Bok tables
    bok_1 = BOK_1_headers.objects.filter(
        Q(client_booking_id=identifier) | Q(pk_header_id=identifier)
    ).first()

    if not bok_1:
        return Response(
            {
                "code": "does_not_exist",
                "message": "Could not find Order!",
                "step": None,
                "status": None,
            },
            status=HTTP_400_BAD_REQUEST,
        )

    booking_lines = (
        BOK_2_lines.objects.filter(
            fk_header_id=bok_1.pk_header_id, is_deleted=True, e_item_type__isnull=False
        )
        .exclude(zbl_102_text_2__in=SERVICE_GROUP_CODES)
        .exclude(l_003_item__icontains="(Ignored")
    )

    status_history = Dme_status_history.objects.filter(
        fk_booking_id=bok_1.pk_header_id
    ).order_by("-z_createdTimeStamp")

    if status_history:
        last_updated = (
            dme_time_lib.convert_to_AU_SYDNEY_tz(
                status_history.first().event_time_stamp
            ).strftime("%d/%m/%Y %H:%M")
            if status_history.first().event_time_stamp
            else ""
        )
    else:
        last_updated = ""

    client = DME_clients.objects.get(dme_account_num=bok_1.fk_client_id)
    booking_dict = {
        "b_bookingID_Visual": None,
        "b_client_order_num": bok_1.b_client_order_num,
        "b_client_sales_inv_num": bok_1.b_client_sales_inv_num,
        "b_028_b_pu_company": bok_1.b_028_b_pu_company,
        "b_029_b_pu_address_street_1": bok_1.b_029_b_pu_address_street_1,
        "b_030_b_pu_address_street_2": bok_1.b_030_b_pu_address_street_2,
        "b_032_b_pu_address_suburb": bok_1.b_032_b_pu_address_suburb,
        "b_031_b_pu_address_state": bok_1.b_031_b_pu_address_state,
        "b_034_b_pu_address_country": bok_1.b_034_b_pu_address_country,
        "b_033_b_pu_address_postalcode": bok_1.b_033_b_pu_address_postalcode,
        "b_035_b_pu_contact_full_name": bok_1.b_035_b_pu_contact_full_name,
        "b_037_b_pu_email": bok_1.b_037_b_pu_email,
        "b_038_b_pu_phone_main": bok_1.b_038_b_pu_phone_main,
        "b_054_b_del_company": bok_1.b_054_b_del_company,
        "b_055_b_del_address_street_1": bok_1.b_055_b_del_address_street_1,
        "b_056_b_del_address_street_2": bok_1.b_056_b_del_address_street_2,
        "b_058_b_del_address_suburb": bok_1.b_058_b_del_address_suburb,
        "b_057_b_del_address_state": bok_1.b_057_b_del_address_state,
        "b_060_b_del_address_country": bok_1.b_060_b_del_address_country,
        "b_059_b_del_address_postalcode": bok_1.b_059_b_del_address_postalcode,
        "b_061_b_del_contact_full_name": bok_1.b_061_b_del_contact_full_name,
        "b_063_b_del_email": bok_1.b_063_b_del_email,
        "b_064_b_del_phone_main": bok_1.b_064_b_del_phone_main,
        "b_000_3_consignment_number": bok_1.b_000_3_consignment_number,
        "pusher": bok_1.x_booking_Created_With,
    }

    def line_to_dict(line):
        try:
            product = Client_Products.objects.get(
                child_model_number=line.e_item_type
            ).description
        except Exception as e:
            logger.error(f"Client product doesn't exist: {e}")
            product = ""

        return {
            "e_item_type": line.e_item_type,
            "l_003_item": line.e_item,
            "l_002_qty": line.e_qty,
            "product": product,
        }

    original_lines = map(line_to_dict, booking_lines)

    quote = bok_1.quote
    json_quote, eta = None, ""

    if quote:
        context = {"client_customer_mark_up": client.client_customer_mark_up}
        quote_data = SimpleQuoteSerializer(quote, context=context).data
        json_quote = dme_time_lib.beautify_eta([quote_data], [quote], client)[0]

        if json_quote and bok_1.b_021_b_pu_avail_from_date:
            eta = dme_time_lib.next_business_day(
                dme_time_lib.convert_to_AU_SYDNEY_tz(bok_1.b_021_b_pu_avail_from_date),
                int(json_quote["eta"].split()[0]),
            ).strftime("%d/%m/%Y %H:%M")

    try:
        logo_url = DME_clients.objects.get(company_name=booking.b_client_name).logo_url
    except Exception as e:
        logger.error(f"Logo url error: {str(e)}")
        logo_url = None

    status = "Processing"
    return Response(
        {
            "step": 1,
            "status": status,
            "last_updated": last_updated,
            "quote": json_quote,
            "booking": booking_dict,
            "eta_date": eta,
            "last_milestone": last_milestone,
            "timestamps": [
                dme_time_lib.convert_to_AU_SYDNEY_tz(bok_1.date_processed).strftime(
                    "%d/%m/%Y %H:%M:%S"
                )
                if bok_1 and bok_1.date_processed
                else "",
                "",
                "",
                "",
                "",
            ],
            "logo_url": client.logo_url,
            "scans": [],
            "original_lines": original_lines,
            "packed_lines": [],
            "apls": [],
        }
    )


@api_view(["POST"])
@permission_classes((AllowAny,))
def approve_booking(request):
    message = tempo.approve(request)
    return Response({"message": message})


@api_view(["GET"])
def find_a_booking(request):
    LOG_ID = "[FIND BOOKING]"
    client_pk = request.GET.get("clientPK")
    order_or_inv_num = request.GET.get("orderNumber")
    client = DME_clients.objects.get(pk=client_pk)

    logger.info(f"{LOG_ID} Client: {client}, Order/Invoice number: {order_or_inv_num}")

    # 1. Try to find from dme_bookings table
    booking = (
        Bookings.objects.filter(kf_client_id=client.dme_account_num)
        .filter(
            Q(b_client_order_num=order_or_inv_num)
            | Q(b_client_sales_inv_num=order_or_inv_num)
        )
        .first()
    )

    if booking:
        logger.info(f"{LOG_ID} Booking: {booking.b_bookingID_Visual}")
        return Response(
            {
                "status": True,
                "statusPageUrl": f"{settings.WEB_SITE_URL}/status/{booking.b_client_booking_ref_num}/",
                "pricePageUrl": f"{settings.WEB_SITE_URL}/price/{booking.b_client_booking_ref_num}/",
            }
        )

    # 2. Try to find from bok_1 table
    bok_1 = (
        BOK_1_headers.objects.filter(fk_client_id=client.dme_account_num)
        .filter(
            Q(b_client_order_num=order_or_inv_num)
            | Q(b_client_sales_inv_num=order_or_inv_num)
        )
        .first()
    )

    if bok_1:
        return Response(
            {
                "status": True,
                "statusPageUrl": f"{settings.WEB_SITE_URL}/status/{bok_1.client_booking_id}/"
                if bok_1.success in [1, 4]
                else "",
                "pricePageUrl": f"{settings.WEB_SITE_URL}/price/{bok_1.client_booking_id}/",
            }
        )

    logger.info(f"{LOG_ID} Order/Invoice({order_or_inv_num}) does not exist.")
    return Response(
        {
            "status": False,
            "statusPageUrl": "",
            "pricePageUrl": "",
            "message": f"Order/Invoice({order_or_inv_num}) does not exist.",
        }
    )
