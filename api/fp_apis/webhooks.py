import json
import base64
import logging
from datetime import datetime

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

from api.common.thread import background
from api.fp_apis.constants import S3_URL
from api.models import Bookings, Dme_manifest_log

logger = logging.getLogger(__name__)


@background
def process_in_bg(request):
    LOG_ID = "[WEBHOOK ORDER SUMMARY]"

    data = request.data
    order_id = data.get("orderId")
    logger.info(f"{LOG_ID} orderId - {order_id}")
    bookings = Bookings.objects.filter(vx_fp_order_id=order_id).only(
        "id",
        "pk_booking_id",
        "vx_freight_provider",
        "vx_fp_order_id",
        "z_manifest_url",
        "manifest_timestamp",
    )

    if not bookings.exists():
        msg = f"No bookigs with order_id: {order_id}"
        logger.info(f"{LOG_ID} {msg}")
        return JsonResponse({"message": msg}, status=200)

    booking = bookings.first()
    _fp_name = booking.vx_freight_provider.lower()
    suffix = f"{str(booking.vx_fp_order_id)}_{str(datetime.now())}.pdf"
    file_name = f"manifest_{suffix}"
    full_path = f"{S3_URL}/pdfs/{_fp_name}_au/{file_name}"

    summary_data = base64.b64decode(data["pdfData"]["data"])
    # ONLY for BioPak + TGE + PE (Pallet Express service)
    # Download Pickup PDF file
    if "consignmentData" in data:
        pickup_file_name = f"pickup_{suffix}"
        pickup_full_path = f"{S3_URL}/pdfs/{_fp_name}_au/{pickup_file_name}"
        pickup_data = base64.b64decode(data["consignmentData"]["data"])
        with open(pickup_full_path, "wb") as f:
            f.write(pickup_data)
            f.close()

    with open(full_path, "wb") as f:
        f.write(summary_data)
        f.close()

    manifest_timestamp = datetime.now()
    booking_ids = []
    for booking in bookings:
        booking.z_manifest_url = f"{_fp_name}_au/{file_name}"
        booking.manifest_timestamp = manifest_timestamp
        booking_ids.append(str(booking.pk))
        booking.save()

    Dme_manifest_log.objects.create(
        fk_booking_id=booking.pk_booking_id,
        manifest_url=booking.z_manifest_url,
        manifest_number=str(booking.vx_fp_order_id),
        bookings_cnt=bookings.count(),
        is_one_booking=False,
        z_createdByAccount=request.user.username,
        booking_ids=",".join(booking_ids),
        freight_provider=booking.vx_freight_provider,
    )


@api_view(["POST"])
@authentication_classes([JSONWebTokenAuthentication])
def spojit_order_summary_webhook(request):
    """
    TGE orderSummary can take 5+ mins, so we used webhook solution.
    """
    process_in_bg(request)

    return JsonResponse({"message": "success"}, status=200)
