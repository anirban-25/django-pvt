import logging
import json

from django.http import JsonResponse
from rest_framework_jwt.authentication import JSONWebTokenAuthentication
from rest_framework.decorators import (
    api_view,
    authentication_classes,
    permission_classes,
)
from rest_framework.permissions import (
    IsAuthenticated,
    AllowAny,
    IsAuthenticatedOrReadOnly,
)
from api.common.constants import EIGHT_EIGHT_API_KEY

from api.models import Bookings, DME_Voice_Calls, FP_status_history
from api.common import common_times as dme_time_lib, status_history
from api.fp_apis.operations.tracking import create_fp_status_history
from api.fp_apis.utils import (
    get_dme_status_from_fp_status,
    get_status_category_from_status,
)
from api.clients.biopak.index import update_biopak
from datetime import date
import requests

logger = logging.getLogger(__name__)


@api_view(["POST"])
@permission_classes((AllowAny,))
def st_tracking_webhook(request):
    LOG_ID = "[ST TRACK WEBHOOK]"
    logger.info(f"{LOG_ID} Payload: {request.data}")

    try:
        consignment_num = request.data["{www.startrack.com.au/events}Consignment"]
        status = request.data["{www.startrack.com.au/events}EventStatus"]
        event_at = request.data["{www.startrack.com.au/events}EventDateTime"]
        signature_name = request.data["{www.startrack.com.au/events}SignatureName"]
        signature_img = request.data["{www.startrack.com.au/events}SignatureImage"]

        bookings = Bookings.objects.filter(
            vx_freight_provider="Startrack", v_FPBookingNumber=consignment_num
        )

        # If Booking does exist
        if not bookings.exists():
            logger.info(f"{LOG_ID} Does not exist: {consignment_num}")
            return JsonResponse({}, status=200)

        booking = Bookings.first()
        fp_status_histories = FP_status_history.objects.filter(
            booking=booking
        ).order_by("id")

        # If event is duplicated
        if fp_status_histories.exists():
            last_fp_status = FP_status_history.last()
            if last_fp_status.status == status:
                logger.info(
                    f"{LOG_ID} Same with previous event. FP status: {consignment_num}"
                )
                return JsonResponse({}, status=200)

        fp = Fp_freight_providers.objects.get(fp_company_name="Startrack")
        fp_status_history_data = {
            "b_status_API": status,
            "status_desc": "",
            "event_time": event_at,
        }
        create_fp_status_history(booking, fp, fp_status_history_data)
        dme_status = get_dme_status_from_fp_status(fp.fp_company_name, status, booking)
        status_history.create(booking, dme_status, LOG_ID)

        # if booking.b_client_name == "BioPak":
        #     update_biopak(booking, fp, status, event_at)

        return JsonResponse({}, status=200)
    except Exception as e:
        logger.error(f"{LOG_ID} Error: {str(e)}")
        return JsonResponse(
            {"errorCode": "failure", "errorMessage": str(e)}, status=400
        )
    
@api_view(["POST"])
@permission_classes((AllowAny,))
def voice_call_webhook(request):
    LOG_ID = "[VOICE CALL WEBHOOK]"
    logger.info(f"{LOG_ID} Payload: {request.data}")


    try:
        if request.data["eventType"] != "CALL_ACTION":
            return JsonResponse({}, status=200)
        
        booking_id = DME_Voice_Calls.objects.filter(uid=request.data["payload"]["sessionId"]).values_list('booking', flat=True).first()        
        logger.info(f"{LOG_ID} BookingID: {booking_id}")

        dtmf = request.data["payload"]["dtmf"]
        # clientActionId = "initalCall"
        # if "clientActionId" in request.data["payload"]:
        #     clientActionId = request.data["payload"]["clientActionId"]

        booking = Bookings.objects.get(pk=booking_id)

        payload = {
            "callflow": [
                {
                    "action": "say",
                    "params": {
                        "text": f"You have chosen to end this call with out a response. Thank you. Have a good day.",
                        "voiceProfile": "en-US-BenjaminRUS",
                        "repetition": 1,
                        "speed": 1,
                    },
                },
                {
                    "action": "hangup",
                }
            ],
        }

        if dtmf == "4":
            payload = {
                "clientActionId": "nextCall",
                "callflow": [              
                    {
                        "action": "sayAndCapture",
                        "params": {
                            "promptMessage": f"Hi {booking.de_to_Contact_F_LName}, this is an automated message with information about the delivery of your {booking.b_client_name} order with Sales Order {booking.b_client_order_num} \
                            is not showing as delivered as of {date.today()} 5pm. \
                            Please note we are contacting the Freight Provider {booking.vx_freight_provider} to follow up for you. \
                            This providers standard response time is 24 working hours. \
                            Press 1 if you did not receive the order. \
                            Press 2 if you received the complete order.  \
                            Press 3 if you received the partial order.",
                            "language": "en",
                            "voiceProfile": "en-US-BenjaminRUS",
                            "repetition": 1,
                            "speed": 0.8,
                            "minDigits": 1,
                            "maxDigits": 1,
                            "digitTimeout": 10000,
                            "overallTimeout": 10000,
                            "completeOnHash": False,
                            "noOfTries": 1,
                            "failureMessage": "Invalid input, please try again",
                        },
                    },
                ],
            }
        elif dtmf == "2":
            payload = {
                "callflow": [
                    {
                        "clientActionId": "customerCall",
                        "action": "sayAndCapture",
                        "params": {
                            "promptMessage": "Thank you for your response, if you would still like to speak with a Customer Service person please press 0 and you will be tranferred",
                            "language": "en",
                            "voiceProfile": "en-US-BenjaminRUS",
                            "repetition": 1,
                            "speed": 0.8,
                            "minDigits": 1,
                            "maxDigits": 1,
                            "digitTimeout": 10000,
                            "overallTimeout": 10000,
                            "completeOnHash": False,
                            "noOfTries": 1,
                            "failureMessage": "Invalid input, please try again",
                        },
                    },
                ],
            }
            booking.b_status = "Delivered"
            booking.save()
        elif dtmf == "3":
            payload = {
                "callflow": [
                    {
                        "clientActionId": "customerCall",
                        "action": "sayAndCapture",
                        "params": {
                            "promptMessage": "Thank you for your response, if you would still like to speak with a Customer Service person please press 0 and you will be tranferred",
                            "language": "en",
                            "voiceProfile": "en-US-BenjaminRUS",
                            "repetition": 1,
                            "speed": 0.8,
                            "minDigits": 1,
                            "maxDigits": 1,
                            "digitTimeout": 10000,
                            "overallTimeout": 10000,
                            "completeOnHash": False,
                            "noOfTries": 1,
                            "failureMessage": "Invalid input, please try again",
                        },
                    },
                ],
            }
            booking.b_status = "Partially Delivered"
            booking.save()
        elif dtmf == "1":
            payload = {
                "callflow": [
                    {
                        "clientActionId": "customerCall",
                        "action": "sayAndCapture",
                        "params": {
                            "promptMessage": "Thank you for your response, if you would still like to speak with a Customer Service person please press 0 and you will be tranferred",
                            "language": "en",
                            "voiceProfile": "en-US-BenjaminRUS",
                            "repetition": 1,
                            "speed": 0.8,
                            "minDigits": 1,
                            "maxDigits": 1,
                            "digitTimeout": 10000,
                            "overallTimeout": 10000,
                            "completeOnHash": False,
                            "noOfTries": 1,
                            "failureMessage": "Invalid input, please try again",
                        },
                    },
                ],
            }
        elif dtmf == "0":
            payload = {
                "callflow": [
                    {
                        "action": "makeCall",
                        "params": {
                            "source": "+61283111500", # Default number
                            "destination": "+61283574600", # CS Number
                        },
                    },
                ],
            }

        logger.info(f"{LOG_ID} Request Payload: {payload}")
        return JsonResponse(payload)
    except Exception as e:
        logger.error(f"{LOG_ID} Error: {str(e)}")
        return JsonResponse(
            {"errorCode": "failure", "errorMessage": str(e)}, status=400
        )
