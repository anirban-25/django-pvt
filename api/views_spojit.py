import logging
import requests, json
from datetime import datetime, date, timedelta

from django.conf import settings
from django.http import JsonResponse
from django.shortcuts import redirect
from rest_framework.permissions import AllowAny
from rest_framework.decorators import (
    api_view,
    authentication_classes,
    permission_classes,
)
from rest_framework.authentication import TokenAuthentication
from rest_framework_jwt.authentication import JSONWebTokenAuthentication
from api.fp_apis.operations.book import built_in_book
from api.models import Bookings
from api.operations.email_senders import send_email_to_admins

from api.warehouses import index as warehouse
from api.common import trace_error

logger = logging.getLogger(__name__)


@api_view(["POST"])
@authentication_classes([JSONWebTokenAuthentication])
def spojit_push_webhook(request):
    LOG_ID = "[WEBHOOK SPOJIT PUSH]"
    logger.info(f"{LOG_ID} Payload: {request.data}")

    try:
        res_json = warehouse.push_webhook(request.data)
        return JsonResponse({}, status=200)
    except Exception as e:
        logger.error(f"{LOG_ID} Error: {str(e)}")
        return JsonResponse(
            {"errorCode": "failure", "errorMessage": str(e)}, status=400
        )

@api_view(["POST"])
@authentication_classes([JSONWebTokenAuthentication])
def spojit_push_webhook_fp(request):
    LOG_ID = "[WEBHOOK SPOJIT PUSH FOR FP]"
    logger.info(f"{LOG_ID} Payload: {request.data}")

    try:
        
        logger.info(f"{LOG_ID} Webhook data: {request.data}")

        data = request.data

        if data["code"] == "success":
            booking_id = data.get("booking_id")
            booker = data.get("booker")

            if not booking_id:
                message = f"{LOG_ID} Webhook data is invalid. Data: {data}"
                logger.error(message)
                send_email_to_admins("Invalid webhook data", message)

            try:
                from api.common import status_history
                from django.db import transaction
                
                booking = Bookings.objects.get(pk=booking_id)
                booking.b_dateBookedDate = datetime.now()
                booking.b_error_Capture = None

                logger.info(f"{LOG_ID} step1: {booking_id}")

                status_history.create(booking, "Booked", booker)

                logger.info(f"{LOG_ID} step2: {booker}")

                with transaction.atomic():
                    booking.save()

                logger.info(f"{LOG_ID} step3: booked successfully")
            except:
                message = f"{LOG_ID} Book does not exist. Data: {data}"
                logger.error(message)
                send_email_to_admins("No Book", message)

        return JsonResponse({}, status=200)
    except Exception as e:
        logger.error(f"{LOG_ID} Error: {str(e)}")
        return JsonResponse(
            {"errorCode": "failure", "errorMessage": str(e)}, status=400
        )

@api_view(["POST"])
@authentication_classes([JSONWebTokenAuthentication])
def spojit_scan(request):
    LOG_ID = "[SPOJIT SCAN]"
    logger.info(f"{LOG_ID} Payload: {request.data}")

    try:
        res_json = warehouse.scanned(request.data)
        return JsonResponse(res_json, status=200)
    except Exception as e:
        trace_error.print()
        logger.error(f"{LOG_ID} Error: {str(e)}")
        return JsonResponse(
            {"errorCode": "failure", "errorMessage": str(e)}, status=400
        )


@api_view(["GET"])
@authentication_classes([JSONWebTokenAuthentication])
def spojit_reprint_label(request):
    LOG_ID = "[SPOJIT REPRINT LABEL]"
    logger.info(f"{LOG_ID} Payload: {request.GET}")

    try:
        res_json = warehouse.reprint_label(request.GET)
        return JsonResponse(res_json, status=200)
    except Exception as e:
        logger.error(f"{LOG_ID} Error: {str(e)}")
        return JsonResponse(
            {"errorCode": "failure", "errorMessage": str(e)}, status=400
        )


@api_view(["POST"])
@authentication_classes([JSONWebTokenAuthentication])
def spojit_ready(request):
    LOG_ID = "[SPOJIT READY]"
    logger.info(f"{LOG_ID} Payload: {request.POST}")

    try:
        res_json = warehouse.ready(request.data)
        return JsonResponse(res_json, status=200)
    except Exception as e:
        logger.error(f"{LOG_ID} Error: {str(e)}")
        return JsonResponse(
            {"errorCode": "failure", "errorMessage": str(e)}, status=400
        )


@api_view(["POST"])
@authentication_classes([JSONWebTokenAuthentication])
def spojit_manifest(request):
    LOG_ID = "[SPOJIT MANIFEST]"
    logger.info(f"{LOG_ID} Payload: {request.POST}")

    try:
        res_json = warehouse.manifest(request.data)
        return JsonResponse(res_json, status=200)
    except Exception as e:
        logger.error(f"{LOG_ID} Error: {str(e)}")
        return JsonResponse(
            {"errorCode": "failure", "errorMessage": str(e)}, status=400
        )
