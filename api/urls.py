from django.conf.urls import url, include
from rest_framework.routers import DefaultRouter
from rest_framework_jwt.views import obtain_jwt_token, verify_jwt_token

from .views import *
from .views_status import *
from .views_client import *
from .views_cron import *
from .views_external_apis import *
from .views_spojit import *
from .views_webhook import *
from .fp_apis import apis as fp_apis
from .file_operations.uploads import get_upload_status
from .fp_apis.webhooks import *

router = DefaultRouter()
router.register(r"users", UserViewSet, basename="user")
router.register(r"bookings", BookingsViewSet, basename="bookings")
router.register(r"booking", BookingViewSet, basename="booking")
router.register(r"bookinglines", BookingLinesViewSet, basename="bookinglines")
router.register(
    r"bookinglinedetails", BookingLineDetailsViewSet, basename="bookinglinedetails"
)
router.register(r"packagetype", PackageTypesViewSet, basename="packagetype")
router.register(r"bookingstatus", BookingStatusViewSet, basename="bookingstatus")
router.register(r"statushistory", StatusHistoryViewSet, basename="statushistory")
router.register(r"fp", FPViewSet, basename="fp")
router.register(r"emailtemplates", EmailTemplatesViewSet, basename="emailtemplates")
router.register(r"options", OptionsViewSet, basename="options")
router.register(r"status", StatusViewSet, basename="status")
router.register(r"api_bcl", ApiBCLViewSet, basename="api_bcl")
router.register(r"reports", DmeReportsViewSet, basename="reports")
router.register(r"pricing", ApiBookingQuotesViewSet, basename="pricing")
router.register(r"surcharge", SurchargeViewSet, basename="surcharge")
router.register(r"sqlqueries", SqlQueriesViewSet, basename="sqlqueries")
router.register(r"vehicles", VehiclesViewSet, basename="vehicles")
router.register(r"pallet", PalletViewSet, basename="pallet")
router.register(r"availabilities", AvailabilitiesViewSet, basename="availabilities")
router.register(r"fp-cost", FPCostsViewSet, basename="fp_cost")
router.register(r"pricing_rules", PricingRulesViewSet, basename="pricing_rules")

router.register(
    r"fp-store-booking-log", FPStoreBookingLog, basename="fp-store-booking-log"
)
router.register(r"bok_0_bookingskeys", BOK_0_ViewSet, basename="bok0")
router.register(r"bok_1_headers", BOK_1_ViewSet, basename="bok1")
router.register(r"bok_2_lines", BOK_2_ViewSet, basename="bok2")
router.register(r"bok_3_lines_data", BOK_3_ViewSet, basename="bok3")
router.register(r"files", FilesViewSet, basename="files")
router.register(r"bookingsets", BookingSetsViewSet, basename="bookingsets")
router.register(r"clientemployee", ClientEmployeesViewSet, basename="clientemployee")
router.register(r"clientproducts", ClientProductsViewSet, basename="client_products")
router.register(r"clientras", ClientRasViewSet, basename="client_ras")
router.register(r"charts", ChartsViewSet, basename="charts")
router.register(r"errors", ErrorViewSet, basename="error")
router.register(r"clientprocess", ClientProcessViewSet, basename="clientprocess_mgr")
router.register(
    r"augmentaddress", AugmentAddressViewSet, basename="augmentaddress_rules"
)
router.register(r"clients", ClientViewSet, basename="clients")
router.register(r"roles", RoleViewSet, basename="roles")
router.register(r"scans", ScansViewSet, basename="scans")
router.register(r"fp_statuses", FpStatusesViewSet, basename="fp_statuses")
router.register(r"cs_notes", DMEBookingCSNoteViewSet, basename="cs_notes")


urlpatterns = router.urls

urlpatterns += [
    # Status
    url(r"^status/", getStatus),
    # Auth
    url(r"^api-token-auth/", obtain_jwt_token),
    url(r"^api-token-verify/", verify_jwt_token),
    url(
        r"^password_reset/",
        include("django_rest_passwordreset.urls", namespace="password_reset"),
    ),
    # Mapping
    url(r"^map-bok-to-booking/", mapBokToBooking),
    url(r"^warehouses/", WarehouseViewSet.as_view({"get": "list"})),
    # File Uploads
    url(r"^attachments/", getAttachmentsHistory),
    url(r"^upload/", FileUploadView.as_view()),
    url(r"^upload/status/", get_upload_status),
    # File Downloads
    url(r"^download/", download),
    # File Delete
    url(r"^delete-file/", delete_file),
    # File Update
    url(r"^set-attachment/", set_attachment),
    # File View(eml, msg files)
    url(r"^get-attachment/", getAttachmentContent),
    # Build & download
    url(r"^get-csv/", get_csv),  # build & download CSV
    url(r"^get-xml/", get_xml),  # build & download XML
    url(r"^get-pdf/", get_pdf),  # build & download PDF
    url(r"^get-manifest/", get_manifest),  # build & download Manifest
    url(r"^build-label/", build_label),  # build Label
    url(r"^build-label-bulk/", build_label_bulk),  # build Label (bulk)
    # APIs for Warehouse(Paperless)
    url(r"^boks/get_label/", scanned),
    url(r"^boks/ready/", ready_boks),
    url(r"^reprint_label/", reprint_label),
    url(r"^manifest/", manifest_boks),
    # BOK apis
    url(r"^bok/quote-count/", quote_count),
    url(r"^boks/", push_boks),
    url(r"^price/partial/", partial_pricing),
    # External apis
    url(r"^external/paperless/send_order_to_paperless/", send_order_to_paperless),
    # Freight Provider apis
    url(r"^fp-api/(?P<fp_name>[^/]+)/bulk-tracking/", fp_apis.bulk_tracking),
    url(r"^fp-api/(?P<fp_name>[^/]+)/tracking/", fp_apis.tracking),
    url(r"^fp-api/(?P<fp_name>[^/]+)/reprint/", fp_apis.reprint),
    url(r"^fp-api/(?P<fp_name>[^/]+)/rebook/", fp_apis.rebook),
    url(r"^fp-api/(?P<fp_name>[^/]+)/book/", fp_apis.book),
    url(r"^fp-api/(?P<fp_name>[^/]+)/pod/", fp_apis.pod),
    url(r"^fp-api/(?P<fp_name>[^/]+)/get-label/", fp_apis.get_label),
    url(r"^fp-api/(?P<fp_name>[^/]+)/edit-book/", fp_apis.edit_book),
    url(r"^fp-api/(?P<fp_name>[^/]+)/cancel-book/", fp_apis.cancel_book),
    url(r"^fp-api/(?P<fp_name>[^/]+)/create-order/", fp_apis.create_order),
    url(r"^fp-api/(?P<fp_name>[^/]+)/get-order-summary/", fp_apis.get_order_summary),
    url(r"^fp-api/(?P<fp_name>[^/]+)/update-service-code/", fp_apis.update_servce_code),
    url(r"^fp-api/(?P<fp_name>[^/]+)/get-booking-info/", fp_apis.get_booking_info),
    url(r"^fp-api/pricing/", fp_apis.pricing),
    # External apis
    url(r"^get_booking_status_by_consignment/", get_booking_status_by_consignment),
    # SPOJIT apis
    url(r"^spojit/whse/scan/", spojit_scan),
    url(r"^spojit/whse/reprint_label/", spojit_reprint_label),
    url(r"^spojit/whse/ready/", spojit_ready),
    url(r"^spojit/whse/manifest/", spojit_manifest),
    # Webhooks
    url(r"^webhook/spojit/whse/push/", spojit_push_webhook),
    url(r"^webhook/spojit/fp/push/", spojit_push_webhook_fp),
    url(r"^webhook/spojit/order-summary/", spojit_order_summary_webhook),
    url(r"^webhook/spojit/(?P<fp_name>[^/]+)/book/", fp_apis.book_webhook),
    url(r"^webhook/startrack/tracking/", st_tracking_webhook),
    url(r"^webhook/voice-call/", voice_call_webhook),
    # PricingOnly
    url(r"^get-quick-pricing/", quick_pricing),
    # url(r"^bulk_pricing/", bulk_pricing),
    # Client apis
    url(r"^get_delivery_status/", get_delivery_status),
    url(r"^find-a-booking/", find_a_booking),
    url(r"^approve-booking/", approve_booking),
    # Logs for debugging
    url(r"^logs/", get_logs),
    # Cron requests
    url(r"^aberdeen-paper/create-set/", aberdeenPaperSet),
    url(r"^aberdeen-paper/gen-label/", aberdeenPaperGenLabel),
    # BSD (Bathroom Sales Direct)
    url(r"^fetch-bsd-order/", fetch_bsd_order),
]
