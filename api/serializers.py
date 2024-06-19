import re
import time
import pytz
import uuid
from datetime import datetime

from rest_framework import serializers

from api.models import (
    Bookings,
    Client_warehouses,
    DME_employees,
    Client_employees,
    Booking_lines,
    Booking_lines_data,
    Dme_status_history,
    DME_reports,
    API_booking_quotes,
    FP_Store_Booking_Log,
    DME_Email_Templates,
    Fp_freight_providers,
    FP_carriers,
    FP_zones,
    DME_Options,
    DME_Files,
    FP_vehicles,
    FP_availabilities,
    FP_costs,
    FP_pricing_rules,
    EmailLogs,
    BookingSets,
    Client_Products,
    Client_Ras,
    Utl_sql_queries,
    DME_Error,
    Client_Process_Mgr,
    DME_Augment_Address,
    DME_Roles,
    DME_clients,
    Pallet,
    Surcharge,
    Dme_utl_fp_statuses,
    FP_status_history,
    DMEBookingCSNote,
    BOK_1_headers,
)
from api import utils
from api.fp_apis.utils import _is_deliverable_price
from api.common import math as dme_math
from api.common.constants import BOOKING_FIELDS_4_ALLBOOKING_TABLE
from api.fp_apis.operations.surcharge.common import SURCHARGE_NAME_DESC
from api.fp_apis.operations.surcharge.index import (
    get_surcharges as get_surcharges_with_quote,
)
from api.fp_apis.constants import SPECIAL_FPS


class WarehouseSerializer(serializers.HyperlinkedModelSerializer):
    client_company_name = serializers.SerializerMethodField(read_only=True)

    def get_client_company_name(self, obj):
        return obj.fk_id_dme_client.company_name

    class Meta:
        model = Client_warehouses
        fields = (
            "pk_id_client_warehouses",
            "name",
            "client_warehouse_code",
            "client_company_name",
            "address1",
            "address2",
            "state",
            "suburb",
            "phone_main",
            "postal_code",
            "contact_name",
            "contact_email",
        )


class SimpleBookingSerializer(serializers.ModelSerializer):
    de_Deliver_By_Time = serializers.SerializerMethodField(read_only=True)
    remaining_time = serializers.SerializerMethodField(read_only=True)
    remaining_time_in_seconds = serializers.SerializerMethodField(read_only=True)
    cheapest_quote = serializers.SerializerMethodField(read_only=True)
    cost_dollar = serializers.SerializerMethodField(read_only=True)

    def get_de_Deliver_By_Time(self, obj):
        if not obj.de_Deliver_By_Minutes:
            minute = "00"
        else:
            minute = str(obj.de_Deliver_By_Minutes).zfill(2)

        if obj.de_Deliver_By_Hours != None:
            return f"{str(obj.de_Deliver_By_Hours).zfill(2)}:{minute}"

        return None

    def get_remaining_time(self, obj):
        if obj.s_06_Latest_Delivery_Date_TimeSet:
            utcnow = datetime.utcnow().replace(tzinfo=pytz.UTC)
            time_delta = obj.s_06_Latest_Delivery_Date_TimeSet - utcnow
            days = time_delta.days
            hours = int(time_delta.seconds / 60 / 60)
            mins = int(time_delta.seconds / 60 % 60)
            return f"{str(days).zfill(2)}:{str(hours).zfill(2)}:{str(mins).zfill(2)}"

        return None

    def get_remaining_time_in_seconds(self, obj):
        if obj.s_06_Latest_Delivery_Date_TimeSet:
            utcnow = datetime.utcnow().replace(tzinfo=pytz.UTC)
            time_delta = obj.s_06_Latest_Delivery_Date_TimeSet - utcnow
            days = time_delta.days
            return days * 24 * 3600 + time_delta.seconds

        return 0

    def get_cheapest_quote(self, obj):
        scanned_quotes_4_picked_bookings = self.context.get(
            "scanned_quotes_4_picked_bookings", []
        )
        lowest_quote = None
        booking_quotes = []

        for quote in scanned_quotes_4_picked_bookings:
            if quote.fk_booking_id == obj.pk_booking_id:
                booking_quotes.append(quote)

            if obj.api_booking_quote and obj.api_booking_quote == quote.id:
                lowest_quote = quote

        if not booking_quotes:
            return {}

        lowest_quote = lowest_quote or booking_quotes[0]
        for quote in booking_quotes:
            if (
                quote.client_mu_1_minimum_values
                < lowest_quote.client_mu_1_minimum_values
            ):
                lowest_quote = quote

        if (
            obj.api_booking_quote
            and lowest_quote
            and obj.api_booking_quote.id == lowest_quote.id
        ):
            return {}

        return {
            "fp": lowest_quote.freight_provider,
            "cost_dollar": round(lowest_quote.client_mu_1_minimum_values, 2),
            "account_code": lowest_quote.account_code,
        }

    def get_cost_dollar(self, obj):
        if obj.inv_sell_quoted_override:
            return round(obj.inv_sell_quoted_override, 2)
        elif obj.inv_booked_quoted:
            return round(obj.inv_booked_quoted, 2)
        elif obj.inv_sell_quoted:
            return round(obj.inv_sell_quoted, 2)
        elif obj.api_booking_quote:
            return round(obj.api_booking_quote.client_mu_1_minimum_values, 2)

    class Meta:
        model = Bookings
        read_only_fields = (
            # "clientRefNumbers",  # property
            # "gap_ras",  # property
            "de_Deliver_By_Time",
            "remaining_time",
            "remaining_time_in_seconds",
            "cheapest_quote",
            "cost_dollar",
        )
        fields = read_only_fields + tuple(BOOKING_FIELDS_4_ALLBOOKING_TABLE)


class BookingSerializer(serializers.ModelSerializer):
    eta_pu_by = serializers.SerializerMethodField(read_only=True)
    eta_de_by = serializers.SerializerMethodField(read_only=True)
    pricing_cost = serializers.SerializerMethodField(read_only=True)
    pricing_service_name = serializers.SerializerMethodField(read_only=True)
    pricing_account_code = serializers.SerializerMethodField(read_only=True)
    is_auto_augmented = serializers.SerializerMethodField(read_only=True)
    customer_cost = serializers.SerializerMethodField(read_only=True)
    quote_packed_status = serializers.SerializerMethodField(read_only=True)
    qtys_in_stock = serializers.SerializerMethodField(read_only=True)
    children = serializers.SerializerMethodField(read_only=True)
    cs_notes_cnt = serializers.SerializerMethodField(read_only=True)

    def get_eta_pu_by(self, obj):
        return utils.get_eta_pu_by(obj)

    def get_eta_de_by(self, obj):
        if obj.api_booking_quote:
            return utils.get_eta_de_by(obj, obj.api_booking_quote)

        return None

    def get_pricing_cost(self, obj):
        if obj.api_booking_quote:
            return obj.api_booking_quote.client_mu_1_minimum_values

        return None

    def get_pricing_service_name(self, obj):
        if obj.api_booking_quote:
            return obj.api_booking_quote.service_name

        return None

    def get_pricing_account_code(self, obj):
        if obj.api_booking_quote:
            return obj.api_booking_quote.account_code

        return None

    def get_is_auto_augmented(self, obj):
        cl_proc = Client_Process_Mgr.objects.filter(fk_booking_id=obj.pk).first()

        if cl_proc:
            return True

        return False

    def get_customer_cost(self, obj):
        client_customer_mark_up = self.context.get("client_customer_mark_up", None)

        if client_customer_mark_up:
            if obj.inv_sell_quoted_override:
                return round(
                    obj.inv_sell_quoted_override * (1 + client_customer_mark_up), 2
                )
            elif obj.inv_booked_quoted:
                return round(obj.inv_booked_quoted * (1 + client_customer_mark_up), 2)
            elif obj.inv_sell_quoted:
                return round(obj.inv_sell_quoted * (1 + client_customer_mark_up), 2)

        return None

    def get_quote_packed_status(self, obj):
        if obj.api_booking_quote:
            return obj.api_booking_quote.packed_status

        return ""

    def get_children(self, obj):
        _chidren = []

        child_bookings = Bookings.objects.filter(
            x_booking_Created_With__contains=f"Child of #{obj.b_bookingID_Visual}"
        ).only(
            "id",
            "b_bookingID_Visual",
            "pk_booking_id",
            "vx_freight_provider",
            "b_status",
        )

        if not child_bookings:
            return _chidren

        pk_booking_ids = [booking.pk_booking_id for booking in child_bookings]
        child_lines = Booking_lines.objects.filter(
            fk_booking_id__in=pk_booking_ids
        ).only("pk_lines_id", "e_item", "e_qty")

        for booking in child_bookings:
            child = {}
            _child_lines = []

            child["b_bookingID_Visual"] = booking.b_bookingID_Visual
            child["vx_freight_provider"] = booking.vx_freight_provider
            child["b_status"] = booking.b_status
            child["lines"] = []

            for line in child_lines:
                if booking.pk_booking_id == line.fk_booking_id:
                    _line = {"e_item": line.e_item, "e_qty": line.e_qty}
                    child["lines"].append(_line)

            _chidren.append(child)

        return _chidren

    def get_qtys_in_stock(self, obj):
        _qtys_in_stock = []

        if obj.x_booking_Created_With and "Child of #" in obj.x_booking_Created_With:
            return _qtys_in_stock

        child_bookings = Bookings.objects.filter(
            x_booking_Created_With__contains=f"Child of #{obj.b_bookingID_Visual}"
        ).only("id", "pk_booking_id", "vx_freight_provider")
        lines = (
            obj.lines()
            .filter(is_deleted=False, packed_status=Booking_lines.ORIGINAL)
            .only("pk_lines_id", "e_item", "e_qty")
        )

        if not child_bookings:
            for line in lines:
                _qtys_in_stock.append(
                    {
                        "pk_lines_id": line.pk,
                        "qty_in_stock": line.e_qty,
                        "qty_out_stock": 0,
                        "e_item": line.e_item,
                    }
                )
        else:
            pk_booking_ids = [booking.pk_booking_id for booking in child_bookings]
            child_lines = Booking_lines.objects.filter(
                fk_booking_id__in=pk_booking_ids
            ).only("pk_lines_id", "e_item", "e_qty")

            for line in lines:
                qty_in_stock = line.e_qty
                qty_out_stock = 0

                for _line in child_lines:
                    if line.e_item == _line.e_item:
                        qty_in_stock -= _line.e_qty
                        qty_out_stock += _line.e_qty

                _qtys_in_stock.append(
                    {
                        "pk_lines_id": line.pk,
                        "qty_in_stock": qty_in_stock,
                        "qty_out_stock": qty_out_stock,
                        "e_item": line.e_item,
                    }
                )

        return _qtys_in_stock

    def get_cs_notes_cnt(self, obj):
        return DMEBookingCSNote.objects.filter(booking_id=obj.pk).count()

    class Meta:
        model = Bookings
        read_only_fields = (
            "eta_pu_by",  # serializer method
            "eta_de_by",  # serializer method
            "pricing_cost",  # serializer method
            "pricing_account_code",  # serializer method
            "pricing_service_name",  # serializer method
            # "business_group",  # property
            # "client_item_references",  # property
            # "clientRefNumbers",  # property
            # "gap_ras",  # property
            "is_auto_augmented",  # Auto Augmented
            "customer_cost",  # Customer cost (Client: Plum)
            "quote_packed_status",
            "qtys_in_stock",  # Child booking related field
            "children",  # Child booking related field
            "cs_notes_cnt",
            "client_sales_total",  # JasonL client_sales_total
        )
        fields = read_only_fields + (
            "id",
            "pk_booking_id",
            "b_bookingID_Visual",
            "b_client_booking_ref_num",
            "puCompany",
            "pu_Address_Street_1",
            "pu_Address_street_2",
            "pu_Address_PostalCode",
            "pu_Address_Suburb",
            "pu_Address_Country",
            "pu_Contact_F_L_Name",
            "pu_Phone_Main",
            "pu_Email",
            "pu_email_Group_Name",
            "pu_email_Group",
            "pu_Comm_Booking_Communicate_Via",
            "de_To_Address_Street_1",
            "de_To_Address_Street_2",
            "de_To_Address_PostalCode",
            "de_To_Address_Suburb",
            "de_To_Address_Country",
            "de_to_Contact_F_LName",
            "de_to_Phone_Main",
            "de_Email",
            "de_Email_Group_Name",
            "de_Email_Group_Emails",
            "deToCompanyName",
            "de_To_Comm_Delivery_Communicate_Via",
            "v_FPBookingNumber",
            "vx_freight_provider",
            "z_label_url",
            "z_pod_url",
            "z_pod_signed_url",
            "pu_Address_State",
            "de_To_Address_State",
            "b_status",
            "b_dateBookedDate",
            "s_20_Actual_Pickup_TimeStamp",
            "s_21_Actual_Delivery_TimeStamp",
            "b_client_name",
            "fk_client_warehouse",
            "b_client_warehouse_code",
            "b_clientPU_Warehouse",
            "booking_Created_For",
            "booking_Created_For_Email",
            "b_booking_Category",
            "b_booking_Priority",
            "vx_fp_pu_eta_time",
            "vx_fp_del_eta_time",
            "b_clientReference_RA_Numbers",
            "de_to_Pick_Up_Instructions_Contact",
            "de_to_PickUp_Instructions_Address",
            "pu_pickup_instructions_address",
            "pu_PickUp_Instructions_Contact",
            "consignment_label_link",
            "s_02_Booking_Cutoff_Time",
            "z_CreatedTimestamp",
            "z_ModifiedTimestamp",
            "b_dateBookedDate",
            "total_lines_qty_override",
            "total_1_KG_weight_override",
            "total_Cubic_Meter_override",
            "z_lock_status",
            "tally_delivered",
            "dme_status_detail",
            "dme_status_action",
            "dme_status_linked_reference_from_fp",
            "puPickUpAvailFrom_Date",
            "pu_PickUp_Avail_Time_Hours",
            "pu_PickUp_Avail_Time_Minutes",
            "pu_PickUp_By_Date",
            "pu_PickUp_By_Time_Hours",
            "pu_PickUp_By_Time_Minutes",
            "de_Deliver_From_Date",
            "de_Deliver_From_Hours",
            "de_Deliver_From_Minutes",
            "de_Deliver_By_Date",
            "de_Deliver_By_Hours",
            "de_Deliver_By_Minutes",
            # "client_item_references",
            "v_service_Type",
            "vx_serviceName",
            "vx_account_code",
            "fk_fp_pickup_id",
            "v_vehicle_Type",
            "inv_billing_status",
            "inv_billing_status_note",
            "dme_client_notes",
            "b_client_sales_inv_num",
            "b_client_order_num",
            "b_client_name_sub",
            "inv_dme_invoice_no",
            "fp_invoice_no",
            "inv_cost_quoted",
            "inv_cost_actual",
            "inv_sell_quoted",
            "inv_sell_quoted_override",
            "inv_sell_actual",
            "x_manual_booked_flag",
            "b_fp_qty_delivered",
            "manifest_timestamp",
            "b_booking_project",
            "b_project_opened",
            "b_project_inventory_due",
            "b_project_wh_unpack",
            "b_project_dd_receive_date",
            "z_calculated_ETA",
            "b_project_due_date",
            "delivery_booking",
            "fp_store_event_date",
            "fp_store_event_time",
            "fp_store_event_desc",
            "fp_received_date_time",
            "b_given_to_transport_date_time",
            "x_ReadyStatus",
            "z_downloaded_shipping_label_timestamp",
            "api_booking_quote",
            "vx_futile_Booking_Notes",
            "s_05_Latest_Pick_Up_Date_TimeSet",
            "s_06_Latest_Delivery_Date_TimeSet",
            "s_06_Latest_Delivery_Date_Time_Override",
            "b_handling_Instructions",
            "b_status_API",
            "b_booking_Notes",
            "b_error_Capture",
            "kf_client_id",
            "z_locked_status_time",
            "x_booking_Created_With",
            "z_CreatedByAccount",
            "b_send_POD_eMail",
            "pu_Address_Type",
            "de_To_AddressType",
            "b_booking_tail_lift_pickup",
            "b_booking_tail_lift_deliver",
            "pu_no_of_assists",
            "de_no_of_assists",
            "pu_location",
            "de_to_location",
            "pu_access",
            "de_access",
            "pu_floor_number",
            "de_floor_number",
            "pu_floor_access_by",
            "de_to_floor_access_by",
            "pu_service",
            "de_service",
            "booking_type",
            "is_quote_locked",
            "inv_booked_quoted",
            "b_pallet_loscam_account",            
        )


class BookingLineSerializer(serializers.ModelSerializer):
    class Meta:
        model = Booking_lines
        fields = (
            "pk_lines_id",
            "fk_booking_id",
            "pk_booking_lines_id",
            "e_type_of_packaging",
            "e_item",
            "e_qty",
            "e_weightUOM",
            "e_weightPerEach",
            "e_dimUOM",
            "e_dimLength",
            "e_dimWidth",
            "e_dimHeight",
            "e_util_height",
            "e_util_cbm",
            "e_util_kg",
            "e_Total_KG_weight",
            "e_1_Total_dimCubicMeter",
            "total_2_cubic_mass_factor_calc",
            "e_qty_awaiting_inventory",
            "e_qty_collected",
            "e_qty_scanned_depot",
            "e_qty_delivered",
            "e_qty_adjusted_delivered",
            "e_qty_damaged",
            "e_qty_returned",
            "e_qty_shortages",
            "e_qty_scanned_fp",
            "picked_up_timestamp",
            "sscc",
            "packed_status",
            "e_bin_number",
            "warranty_value",
            "warranty_percent",
            "note",
            "b_pallet_loscam_account",
        )


class SimpleBookingLineSerializer(serializers.ModelSerializer):
    class Meta:
        model = Booking_lines
        fields = (
            "pk_lines_id",
            "fk_booking_id",
            "pk_booking_lines_id",
            "e_type_of_packaging",
            "e_item",
            "e_qty",
            "e_weightUOM",
            "e_weightPerEach",
            "e_dimUOM",
            "e_dimLength",
            "e_dimWidth",
            "e_dimHeight",
            "e_util_height",
            "e_util_cbm",
            "e_util_kg",
            "e_Total_KG_weight",
            "e_1_Total_dimCubicMeter",
            "total_2_cubic_mass_factor_calc",
            "sscc",
            "packed_status",
            "e_bin_number",
            "warranty_value",
            "warranty_percent",
            "note",
            "is_deleted",
            "b_pallet_loscam_account",
        )


class BookingLineDetailSerializer(serializers.ModelSerializer):
    class Meta:
        model = Booking_lines_data
        fields = (
            "pk_id_lines_data",
            "fk_booking_id",
            "fk_booking_lines_id",
            "modelNumber",
            "itemDescription",
            "quantity",
            "itemFaultDescription",
            "insuranceValueEach",
            "gap_ra",
            "clientRefNumber",
        )


class StatusHistorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Dme_status_history
        fields = "__all__"


class DmeReportsSerializer(serializers.ModelSerializer):
    username = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = DME_reports
        fields = "__all__"

    def get_username(self, obj):
        return obj.user.username


class FPStoreBookingLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = FP_Store_Booking_Log
        fields = "__all__"


class ApiBookingQuotesSerializer(serializers.ModelSerializer):
    eta_pu_by = serializers.SerializerMethodField(read_only=True)
    eta_de_by = serializers.SerializerMethodField(read_only=True)
    is_deliverable = serializers.SerializerMethodField(read_only=True)
    inv_cost_quoted = serializers.SerializerMethodField(read_only=True)
    surcharge_total = serializers.SerializerMethodField(read_only=True)
    surcharge_total_cl = serializers.SerializerMethodField(read_only=True)
    client_customer_mark_up = serializers.SerializerMethodField(read_only=True)
    surcharges = serializers.SerializerMethodField(read_only=True)
    cost_dollar = serializers.SerializerMethodField(read_only=True)
    fuel_levy_base_cl = serializers.SerializerMethodField(read_only=True)
    vehicle_name = serializers.SerializerMethodField(read_only=True)
    service_desc = serializers.SerializerMethodField()

    def get_service_desc(self, obj):
        if obj.freight_provider == "Customer Collect":
            return ""
        elif obj.service_name and "(Into Premises)" in obj.service_name:
            return obj.service_name

        booking = self.context.get("booking")
        if (booking.deToCompanyName.lower() in ["jl fitouts"]) or (
            obj.freight_provider
            in [
                "Deliver-ME",
                "WeFleet",
                "In House Fleet",
                "All Purpose Transport",
            ]
        ):
            return f"{obj.service_name or ''} (Into Premises)"
        else:
            return f"{obj.service_name or ''} (To Door, ground level)"

    def __init__(self, *args, **kwargs):
        # Don't pass the 'fields_to_exclude' arg up to the superclass
        fields_to_exclude = kwargs.pop("fields_to_exclude", None)

        # Instantiate the superclass normally
        super(ApiBookingQuotesSerializer, self).__init__(*args, **kwargs)

        if fields_to_exclude is not None:
            disallowed = set(fields_to_exclude)

            for field_name in disallowed:
                self.fields.pop(field_name)

    def get_eta_pu_by(self, obj):
        try:
            booking = self.context.get("booking")
            return utils.get_eta_pu_by(booking)
        except Exception as e:
            return None

    def get_eta_de_by(self, obj):
        try:
            booking = self.context.get("booking")
            return utils.get_eta_de_by(booking, obj)
        except Exception as e:
            return None

    def get_inv_cost_quoted(self, obj):
        try:
            booking = self.context.get("booking")
            return round(obj.fee * (1 + obj.mu_percentage_fuel_levy), 3)
        except Exception as e:
            return None

    def get_is_deliverable(self, obj):
        try:
            booking = self.context.get("booking")
            return _is_deliverable_price(obj, booking)
        except Exception as e:
            return None

    def get_surcharge_total(self, obj):
        return obj.x_price_surcharge if obj.x_price_surcharge else 0

    def get_surcharge_total_cl(self, obj):
        return (
            obj.x_price_surcharge * (1 + obj.client_mark_up_percent)
            if obj.x_price_surcharge
            else 0
        )

    def get_client_customer_mark_up(self, obj):
        client_customer_mark_up = self.context.get("client_customer_mark_up", 0)
        return client_customer_mark_up

    def get_surcharges(self, obj):
        booking = self.context.get("booking")
        surcharges = get_surcharges_with_quote(obj)
        context = {"client_mark_up_percent": obj.client_mark_up_percent}
        return SurchargeSerializer(surcharges, context=context, many=True).data

    def get_cost_dollar(self, obj):
        if obj.freight_provider in SPECIAL_FPS:
            return round(obj.client_mu_1_minimum_values or 0, 2)

        return round(obj.fee * (1 + obj.client_mark_up_percent), 2)

    def get_fuel_levy_base_cl(self, obj):
        return obj.fuel_levy_base * (1 + obj.client_mark_up_percent)

    def get_vehicle_name(self, obj):
        if obj.vehicle_id:
            return obj.vehicle.description
        return ""

    class Meta:
        model = API_booking_quotes
        fields = "__all__"


class SimpleQuoteSerializer(serializers.ModelSerializer):
    cost_id = serializers.SerializerMethodField(read_only=True)
    eta = serializers.SerializerMethodField(read_only=True)
    fp_name = serializers.SerializerMethodField(read_only=True)
    provider = serializers.SerializerMethodField(read_only=True)
    cost = serializers.SerializerMethodField(read_only=True)
    client_customer_mark_up = serializers.SerializerMethodField(read_only=True)
    surcharge_total = serializers.SerializerMethodField(read_only=True)
    surcharge_total_cl = serializers.SerializerMethodField(read_only=True)
    cost_dollar = serializers.SerializerMethodField(read_only=True)
    fuel_levy_base_cl = serializers.SerializerMethodField(read_only=True)
    vehicle_name = serializers.SerializerMethodField(read_only=True)
    service_desc = serializers.SerializerMethodField()

    def get_service_desc(self, obj):
        if obj.freight_provider == "Customer Collect":
            return ""
        elif obj.service_name and "(Into Premises)" in obj.service_name:
            return obj.service_name

        if obj.freight_provider in [
            "Deliver-ME",
            "WeFleet",
            "In House Fleet",
            "All Purpose Transport",
        ]:
            return f"{obj.service_name or ''} (Into Premises)"
        else:
            return f"{obj.service_name or ''} (To Door, ground level)"

    def get_cost_id(self, obj):
        return obj.pk

    def get_client_customer_mark_up(self, obj):
        client_customer_mark_up = self.context.get("client_customer_mark_up", 0)
        return client_customer_mark_up

    def get_cost(self, obj):
        cost = obj.client_mu_1_minimum_values or 0

        if obj.freight_provider in SPECIAL_FPS:
            return round(cost, 2)

        client_customer_mark_up = self.context.get("client_customer_mark_up", 0)
        if client_customer_mark_up:
            cost = cost * (1 + client_customer_mark_up)

            if obj.tax_value_1:
                cost += obj.tax_value_1

        return round(cost, 2)

    def get_surcharge_total(self, obj):
        return obj.x_price_surcharge if obj.x_price_surcharge else 0

    def get_surcharge_total_cl(self, obj):
        return (
            obj.x_price_surcharge * (1 + obj.client_mark_up_percent)
            if obj.x_price_surcharge
            else 0
        )

    def get_eta(self, obj):
        return obj.etd

    def get_fp_name(self, obj):
        return obj.freight_provider

    def get_provider(self, obj):
        return obj.provider

    def get_cost_dollar(self, obj):
        if obj.freight_provider in SPECIAL_FPS:
            return round(obj.client_mu_1_minimum_values or 0, 2)

        return round(obj.fee * (1 + obj.client_mark_up_percent), 2)

    def get_fuel_levy_base_cl(self, obj):
        return obj.fuel_levy_base * (1 + obj.client_mark_up_percent)

    def get_vehicle_name(self, obj):
        if obj.vehicle_id:
            return obj.vehicle.description
        return ""

    class Meta:
        model = API_booking_quotes
        fields = (
            "cost_id",
            "client_mu_1_minimum_values",
            "cost",
            "surcharge_total",
            "surcharge_total_cl",
            "client_customer_mark_up",
            "eta",
            "service_name",
            "service_desc",
            "fp_name",
            "provider",
            "cost_dollar",
            "fuel_levy_base_cl",
            "mu_percentage_fuel_levy",
            "vehicle_name",
            "packed_status",
        )


class Simple4ProntoQuoteSerializer(serializers.ModelSerializer):
    cost_id = serializers.SerializerMethodField(read_only=True)
    cost = serializers.SerializerMethodField(read_only=True)
    eta = serializers.SerializerMethodField(read_only=True)
    fp_name = serializers.SerializerMethodField(read_only=True)
    service_desc = serializers.SerializerMethodField()

    def get_service_desc(self, obj):
        if obj.freight_provider == "Customer Collect":
            return ""
        elif obj.service_name and "(Into Premises)" in obj.service_name:
            return obj.service_name

        bok_1 = BOK_1_headers.objects.get(pk_header_id=obj.fk_booking_id)
        if (bok_1.b_054_b_del_company.lower() in ["jl fitouts"]) or (
            obj.freight_provider
            in [
                "Deliver-ME",
                "WeFleet",
                "In House Fleet",
                "All Purpose Transport",
            ]
        ):
            return f"{obj.service_name or ''} (Into Premises)"
        else:
            return f"{obj.service_name or ''} (To Door, ground level)"

    def get_cost_id(self, obj):
        return obj.pk

    def get_cost(self, obj):
        cost = obj.client_mu_1_minimum_values
        client_customer_mark_up = self.context.get("client_customer_mark_up", 0)

        if client_customer_mark_up:
            cost = cost * (1 + client_customer_mark_up)

            if obj.tax_value_1:
                cost += obj.tax_value_1

        return round(cost, 2)

    def get_eta(self, obj):
        return obj.etd

    def get_fp_name(self, obj):
        return obj.freight_provider

    class Meta:
        model = API_booking_quotes
        fields = (
            "cost_id",
            "cost",
            "eta",
            "service_name",
            "service_desc",
            "fp_name",
        )


class EmailTemplatesSerializer(serializers.ModelSerializer):
    class Meta:
        model = DME_Email_Templates
        fields = "__all__"


class FpSerializer(serializers.ModelSerializer):
    rule_type_code = serializers.SerializerMethodField(read_only=True)

    def get_rule_type_code(self, fp):
        if fp.rule_type:
            return fp.rule_type.rule_type_code
        else:
            return None

    class Meta:
        model = Fp_freight_providers
        fields = (
            "id",
            "fp_company_name",
            "fp_address_country",
            "service_cutoff_time",
            "rule_type",
            "rule_type_code",
            "fp_markupfuel_levy_percent",
        )


class CarrierSerializer(serializers.ModelSerializer):
    class Meta:
        model = FP_carriers
        fields = "__all__"


class ZoneSerializer(serializers.ModelSerializer):
    class Meta:
        model = FP_zones
        fields = "__all__"


class OptionsSerializer(serializers.ModelSerializer):
    class Meta:
        model = DME_Options
        fields = (
            "id",
            "option_value",
            "option_name",
            "option_description",
            "elapsed_seconds",
            "is_running",
            "arg1",
            "arg2",
        )


class FilesSerializer(serializers.ModelSerializer):
    class Meta:
        model = DME_Files
        fields = "__all__"


class VehiclesSerializer(serializers.ModelSerializer):
    class Meta:
        model = FP_vehicles
        fields = "__all__"


class AvailabilitiesSerializer(serializers.ModelSerializer):
    class Meta:
        model = FP_availabilities
        fields = "__all__"


class FPCostsSerializer(serializers.ModelSerializer):
    class Meta:
        model = FP_costs
        fields = "__all__"


class PricingRulesSerializer(serializers.ModelSerializer):
    class Meta:
        model = FP_pricing_rules
        fields = "__all__"


class EmailLogsSerializer(serializers.ModelSerializer):
    class Meta:
        model = EmailLogs
        fields = "__all__"


class ClientEmployeesSerializer(serializers.ModelSerializer):
    role_name = serializers.CharField(source="role.role_code", required=False)
    client_name = serializers.CharField(
        source="fk_id_dme_client.company_name", required=False
    )
    warehouse_name = serializers.SerializerMethodField()

    class Meta:
        model = Client_employees
        exclude = ("status_time",)

    def get_warehouse_name(self, instance):
        if instance.warehouse_id:
            warehouse = Client_warehouses.objects.get(
                pk_id_client_warehouses=instance.warehouse_id
            )
            return warehouse.name

        return None


class SqlQueriesSerializer(serializers.ModelSerializer):
    sql_query = serializers.CharField()

    def validate_sql_query(self, value):
        """
        Only SELECT query is allowed to added
        """
        if re.search("select", value, flags=re.IGNORECASE):
            return value
        else:
            raise serializers.ValidationError("Only SELECT query is allowed!")

    class Meta:
        model = Utl_sql_queries
        fields = "__all__"


class ClientProductsSerializer(serializers.ModelSerializer):
    class Meta:
        model = Client_Products
        fields = "__all__"


class ClientRasSerializer(serializers.ModelSerializer):
    class Meta:
        model = Client_Ras
        fields = "__all__"


class ClientProcessSerializer(serializers.ModelSerializer):
    class Meta:
        model = Client_Process_Mgr
        fields = "__all__"


class BookingSetsSerializer(serializers.ModelSerializer):
    bookings_cnt = serializers.SerializerMethodField(read_only=True)

    def get_bookings_cnt(self, obj):
        if obj.booking_ids:
            return len(obj.booking_ids.split(", "))

        return 0

    class Meta:
        model = BookingSets
        fields = "__all__"


class ErrorSerializer(serializers.ModelSerializer):
    fp_name = serializers.SerializerMethodField(read_only=True)

    def get_fp_name(self, obj):
        return obj.freight_provider.fp_company_name

    class Meta:
        model = DME_Error
        fields = (
            "accountCode",
            "error_code",
            "error_description",
            "fp_name",
        )


class AugmentAddressSerializer(serializers.ModelSerializer):
    class Meta:
        model = DME_Augment_Address
        fields = "__all__"


class RoleSerializer(serializers.ModelSerializer):
    class Meta:
        model = DME_Roles
        fields = "__all__"


class ClientSerializer(serializers.ModelSerializer):
    phone = serializers.IntegerField(required=False)
    client_filter_date_field = serializers.CharField(required=False)
    current_freight_provider = serializers.CharField(allow_blank=True, required=False)
    logo_url = serializers.CharField(allow_blank=True, required=False)
    gap_percent = serializers.FloatField(required=False)
    augment_pu_by_time = serializers.TimeField(required=False)
    augment_pu_available_time = serializers.TimeField(required=False)
    status_email = serializers.CharField(allow_blank=True, required=False)
    status_phone = serializers.CharField(allow_blank=True, required=False)
    status_send_flag = serializers.BooleanField(required=False)

    class Meta:
        model = DME_clients
        fields = "__all__"

    def create(self, validated_data):
        validated_data["dme_account_num"] = str(uuid.uuid4())
        client = DME_clients(**validated_data)
        client.save()
        return client


class PalletSerializer(serializers.ModelSerializer):
    class Meta:
        model = Pallet
        fields = "__all__"


class SurchargeSerializer(serializers.ModelSerializer):
    description = serializers.SerializerMethodField(read_only=True)
    amount_cl = serializers.SerializerMethodField(read_only=True)

    def get_description(self, obj):
        try:
            return SURCHARGE_NAME_DESC[obj.fp.fp_company_name.upper()][obj.name]
        except:
            return ""

    def get_amount_cl(self, obj):
        client_mark_up_percent = self.context.get("client_mark_up_percent", 0)
        return obj.amount * (1 + client_mark_up_percent)

    class Meta:
        model = Surcharge
        fields = "__all__"


class FpStatusSerializer(serializers.ModelSerializer):
    class Meta:
        model = Dme_utl_fp_statuses
        fields = "__all__"


class FPStatusHistorySerializer(serializers.ModelSerializer):
    class Meta:
        model = FP_status_history
        fields = "__all__"


class DMEBookingCSNoteSerializer(serializers.ModelSerializer):
    class Meta:
        model = DMEBookingCSNote
        fields = "__all__"
