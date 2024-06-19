import os
import logging

from django.conf import settings
from django.http import JsonResponse
from django.db.models import Q
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.exceptions import ValidationError
from rest_framework.authentication import TokenAuthentication
from rest_framework_jwt.authentication import JSONWebTokenAuthentication
from rest_framework.decorators import (
    api_view,
    authentication_classes,
    permission_classes,
)
from rest_framework import views, serializers, status
from rest_framework.permissions import IsAuthenticated

from api.serializers_client import *
from api.serializers import ApiBookingQuotesSerializer
from api.models import *
from api.operations import paperless
from api.fp_apis.constants import AVAILABLE_FPS_4_FC, BUILT_IN_PRICINGS
from api.fp_apis.operations.pricing import pricing as pricing_oper
from api.common.build_object import Struct

logger = logging.getLogger(__name__)


@api_view(["GET"])
@authentication_classes([JSONWebTokenAuthentication])
def get_booking_status_by_consignment(request):
    v_FPBookingNumber = request.GET.get("consignment", None)

    if not v_FPBookingNumber:
        return JsonResponse(
            {"status": "error", "error": "Consignment is null"}, status=400
        )
    else:
        try:
            booking = Bookings.objects.get(v_FPBookingNumber=v_FPBookingNumber)
            return JsonResponse(
                {
                    "status": "success",
                    "b_status": booking.b_status_API,
                    "z_lastStatusAPI_ProcessedTimeStamp": booking.z_lastStatusAPI_ProcessedTimeStamp,
                },
                status=200,
            )
        except Bookings.DoesNotExist:
            return JsonResponse(
                {"status": "error", "error": "No matching Booking"}, status=400
            )


# Paperless
@api_view(["POST"])
def send_order_to_paperless(request):
    logger.info(f"@680 Paperless request payload - {request.data}")
    b_client_sales_inv_num = request.data.get("b_client_sales_inv_num")

    if not b_client_sales_inv_num:
        message = "'b_client_sales_inv_num' is required"
        raise ValidationError({"code": "missing_param", "description": message})

    bok_1 = BOK_1_headers.objects.filter(
        b_client_sales_inv_num=b_client_sales_inv_num
    ).first()

    if not bok_1:
        message = "bok_1 does not exist with given b_client_sales_inv_num"
        raise ValidationError({"code": "not_found", "description": message})

    result = paperless.send_order_info(bok_1)

    if not result:
        return JsonResponse(
            {"success": True, "error": "Unknown erorr"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    return JsonResponse(
        {"success": True, "error": None, "message": result}, status=status.HTTP_200_OK
    )


@api_view(["GET"])
@authentication_classes([JSONWebTokenAuthentication])
def get_logs(request):
    username = request.user.username
    if username != "dme":
        return Response(
            {"success": False, "error": "Only admin can call"},
            status=status.HTTP_401_UNAUTHORIZED,
        )

    try:
        log_file = os.path.join(f"{settings.BASE_DIR}/logs", "debug.log")
        f = open(log_file, "r")
        lines = f.readlines()
        last_lines = lines[-300:]

        return Response(
            {"success": True, "logs": last_lines}, status=status.HTTP_200_OK
        )
    except Exception as e:
        return Response(
            {"success": False, "error": str(e)}, status=status.HTTP_400_BAD_REQUEST
        )


# Pricing-only
# @api_view(["POST"])
# def bulk_pricing(request):
#     bookings = request.data.get("bookings")
#     booking_lines = request.data.get("booking_lines")


def do_bulk_pricing(bookings, booking_lines):
    LOG_ID = "[BULK PRICING]"
    logger.info(f"{LOG_ID} bulk_pricing")
    result = []

    for index, booking in enumerate(bookings):
        if index % 10 == 0:
            logger.info(f"{LOG_ID} Bulk pricing: {index}/{len(bookings)}")

        lines = []
        for booking_line in booking_lines:
            if booking["pk_booking_id"] == booking_line["fk_booking_id"]:
                lines.append(booking_line)

        _, success, message, quote_set, client = pricing_oper(
            body={"booking": booking, "booking_lines": lines},
            booking_id=None,
            is_pricing_only=True,
            packed_statuses=[Booking_lines.ORIGINAL],
        )

        json_results = ApiBookingQuotesSerializer(
            quote_set,
            many=True,
            context={
                "booking": Struct(**booking),
                "client_customer_mark_up": 0,
            },
        ).data

        result.append({"booking": booking, "pricings": json_results})

    # if not result:
    #     return JsonResponse(
    #         {"success": True, "error": "Unknown erorr"},
    #         status=status.HTTP_400_BAD_REQUEST,
    #     )

    # return JsonResponse(
    #     {"success": True, "error": None, "result": result}, status=status.HTTP_200_OK
    # )
    return result
