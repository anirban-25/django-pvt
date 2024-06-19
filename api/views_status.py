import logging

from rest_framework.decorators import (
    api_view,
    permission_classes,
    action,
)
from rest_framework.response import Response
from rest_framework import authentication, permissions, viewsets
from rest_framework.permissions import (
    IsAuthenticated,
    AllowAny,
    IsAuthenticatedOrReadOnly,
)
from rest_framework.status import HTTP_400_BAD_REQUEST, HTTP_200_OK, HTTP_201_CREATED

from api.models import Bookings, FP_status_history
from api.serializers import FPStatusHistorySerializer

logger = logging.getLogger(__name__)


class ScansViewSet(viewsets.ModelViewSet):
    serializer_class = FPStatusHistorySerializer
    permission_classes = [AllowAny]

    def get_queryset(self):
        booking_id = self.request.GET["bookingId"]
        queryset = FP_status_history.objects.all()

        if booking_id:
            queryset = queryset.filter(booking_id=booking_id)

        return queryset.order_by("id")
