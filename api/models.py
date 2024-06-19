import pytz
import logging
import math
from datetime import datetime, date, timedelta, time

from django.utils import timezone
from django.conf import settings
from django.db import models, transaction
from django.db.models import Max
from django.db.models.signals import pre_save, post_save, post_delete
from django.utils.translation import gettext as _
from django.contrib.auth.models import BaseUserManager
from django.contrib.auth.models import User
from django.dispatch import receiver
from api.helpers.cubic import get_cubic_meter, getM3ToKgFactor
from api.common import trace_error, constants as dme_constants
from api.common.async_ops import quote_in_bg


if settings.ENV == "local":
    S3_URL = "./static"
elif settings.ENV == "dev":
    S3_URL = "/opt/s3_public"
elif settings.ENV == "prod":
    S3_URL = "/opt/s3_public"

logger = logging.getLogger(__name__)


class UserPermissions(models.Model):
    id = models.AutoField(primary_key=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, default=1
    )
    can_create_comm = models.BooleanField(blank=True, null=True, default=False)

    class Meta:
        db_table = "user_permissions"


class DME_Roles(models.Model):
    id = models.AutoField(primary_key=True)
    role_code = models.CharField(
        verbose_name=_("Role Code"), max_length=32, blank=False
    )
    description = models.CharField(
        verbose_name=_("Role Description"), max_length=255, blank=False
    )

    class Meta:
        db_table = "dme_roles"

    def __str__(self):
        return self.role_code


class DME_clients(models.Model):
    pk_id_dme_client = models.AutoField(primary_key=True)
    company_name = models.CharField(
        verbose_name=_("Company Name"), max_length=128, null=False
    )
    dme_account_num = models.CharField(
        verbose_name=_("dme account num"), max_length=64, default=None, null=False
    )
    phone = models.IntegerField(verbose_name=_("phone number"))
    client_filter_date_field = models.CharField(
        verbose_name=_("Client Filter Date Field"),
        max_length=64,
        blank=False,
        null=False,
        default="z_CreatedTimestamp",
    )
    current_freight_provider = models.CharField(
        verbose_name=_("Related FP"), max_length=30, null=True, default="*"
    )
    logo_url = models.CharField(
        verbose_name=_("Logo Url"), max_length=200, null=True, default=None
    )
    client_mark_up_percent = models.FloatField(default=0, null=True)
    client_min_markup_startingcostvalue = models.FloatField(default=0, null=True)
    client_min_markup_value = models.FloatField(default=0, null=True)
    augment_pu_by_time = models.TimeField(null=True, default=None)
    augment_pu_available_time = models.TimeField(null=True, default=None)
    client_customer_mark_up = models.FloatField(default=0, null=True)
    gap_percent = models.FloatField(default=0, null=True)
    status_email = models.CharField(max_length=64, default=None, null=True, blank=True)
    status_phone = models.CharField(max_length=16, default=None, null=True, blank=True)
    status_send_flag = models.BooleanField(default=False, null=True, blank=True)

    class Meta:
        db_table = "dme_clients"

    def __str__(self):
        return self.company_name


class DME_employees(models.Model):
    pk_id_dme_emp = models.AutoField(primary_key=True)
    fk_id_user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    name_last = models.CharField(
        verbose_name=_("last name"), max_length=30, blank=False
    )
    name_first = models.CharField(
        verbose_name=_("first name"), max_length=30, blank=False
    )
    role = models.ForeignKey(DME_Roles, on_delete=models.CASCADE, default=1)
    warehouse_id = models.IntegerField(
        verbose_name=_("Warehouse ID"), default=1, blank=False, null=True
    )
    status_time = models.DateTimeField(
        verbose_name=_("Status Time"), default=timezone.now, blank=True
    )

    class Meta:
        db_table = "dme_employees"


class Client_warehouses(models.Model):
    pk_id_client_warehouses = models.AutoField(primary_key=True)
    fk_id_dme_client = models.ForeignKey(DME_clients, on_delete=models.CASCADE)
    name = models.CharField(
        max_length=64,
        blank=False,
        null=True,
        default=None,
    )
    address1 = models.CharField(
        max_length=64,
        blank=False,
        null=True,
        default=None,
    )
    address2 = models.CharField(
        max_length=64,
        blank=False,
        null=True,
        default=None,
    )
    state = models.CharField(
        max_length=64,
        blank=False,
        null=True,
        default=None,
    )
    suburb = models.CharField(
        max_length=32,
        blank=False,
        null=True,
        default=None,
    )
    phone_main = models.CharField(
        max_length=16,
        blank=False,
        null=True,
        default=None,
    )
    postal_code = models.CharField(
        max_length=64,
        null=True,
        default=None,
    )
    contact_name = models.CharField(
        max_length=128,
        null=True,
        default=None,
    )
    contact_email = models.CharField(
        max_length=64,
        null=True,
        default=None,
    )
    hours = models.CharField(
        max_length=64,
        blank=False,
        null=True,
        default=None,
    )
    business_type = models.CharField(
        verbose_name=_("warehouse type"), max_length=64, blank=True, null=True
    )
    client_warehouse_code = models.CharField(
        verbose_name=_("warehouse code"), max_length=100, blank=True, null=True
    )
    success_type = models.IntegerField(default=0)
    use_dme_label = models.BooleanField(default=False)
    instructions_linehual = models.CharField(
        max_length=255,
        blank=False,
        null=True,
        default=None,
    )
    main_warehouse = models.BooleanField(default=False)
    connote_number = models.IntegerField(default=0)
    tge_ipec_connote_index = models.IntegerField(default=0)
    tge_ipec_sscc_index = models.IntegerField(default=0)
    tge_pe_connote_index = models.IntegerField(default=0)
    tge_pe_sscc_index = models.IntegerField(default=0)

    class Meta:
        db_table = "dme_client_warehouses"

    def __str__(self):
        return self.name


class Client_employees(models.Model):
    pk_id_client_emp = models.AutoField(primary_key=True)
    fk_id_user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, blank=True, null=True
    )
    fk_id_dme_client = models.ForeignKey(
        DME_clients, on_delete=models.CASCADE, blank=True, null=True
    )
    role = models.ForeignKey(DME_Roles, on_delete=models.CASCADE, blank=True, null=True)
    name_last = models.CharField(
        verbose_name=_("last name"), max_length=30, blank=True, null=True
    )
    name_first = models.CharField(
        verbose_name=_("first name"), max_length=30, blank=True, null=True
    )
    email = models.EmailField(
        verbose_name=_("email address"), max_length=64, unique=True, null=True
    )
    phone = models.CharField(max_length=16, blank=True, null=True, default=None)
    warehouse_id = models.IntegerField(
        verbose_name=_("Warehouse ID"), default=1, blank=True, null=True
    )
    clientEmployeeSalutation = models.CharField(max_length=20, blank=True, null=True)
    client_emp_name_frst = models.CharField(max_length=50, blank=True, null=True)
    client_emp_name_surname = models.CharField(max_length=50, blank=True, null=True)
    clientEmployeeEmail = models.CharField(max_length=50, blank=True, null=True)
    clien_emp_job_title = models.CharField(max_length=50, blank=True, null=True)
    client_emp_phone_fax = models.CharField(max_length=50, blank=True, null=True)
    client_emp_phone_main = models.CharField(max_length=50, blank=True, null=True)
    client_emp_phone_mobile = models.CharField(max_length=50, blank=True, null=True)
    client_emp_address_1 = models.CharField(max_length=200, blank=True, null=True)
    client_emp_address_2 = models.CharField(max_length=200, blank=True, null=True)
    client_emp_address_state = models.CharField(max_length=50, blank=True, null=True)
    client_emp_address_suburb = models.CharField(max_length=50, blank=True, null=True)
    client_emp_address_postal_code = models.CharField(
        max_length=50, blank=True, null=True
    )
    client_emp_address_country = models.CharField(max_length=50, blank=True, null=True)
    clientEmployeeSpecialInstruc = models.TextField(
        max_length=500, blank=True, null=True
    )
    clientEmployeeCommLateBookings = models.CharField(
        max_length=50, blank=True, null=True
    )
    z_createdByAccount = models.CharField(
        verbose_name=_("Created By Account"), max_length=25, blank=True, null=True
    )
    z_createdTimeStamp = models.DateTimeField(
        verbose_name=_("Created Timestamp"),
        null=True,
        blank=True,
        auto_now_add=True,
    )
    z_modifiedByAccount = models.CharField(
        verbose_name=_("Modified By Account"), max_length=25, blank=True, null=True
    )
    z_modifiedTimeStamp = models.DateTimeField(
        verbose_name=_("Modified Timestamp"),
        null=True,
        blank=True,
        auto_now=True,
    )
    status_time = models.DateTimeField(
        verbose_name=_("Status Time"), default=timezone.now, blank=True
    )

    class Meta:
        db_table = "dme_client_employees"

    def get_role(self):
        role = DME_Roles.objects.get(id=self.role_id)
        return role.role_code


class Dme_manifest_log(models.Model):
    id = models.AutoField(primary_key=True)
    fk_booking_id = models.CharField(
        verbose_name=_("FK Booking Id"), max_length=64, blank=True, null=True
    )
    booking_ids = models.TextField(default=None, null=True)
    freight_provider = models.CharField(
        max_length=64, default=None, blank=True, null=True
    )
    manifest_number = models.CharField(max_length=32, blank=True, null=True)
    manifest_url = models.CharField(max_length=200, blank=True, null=True)
    is_one_booking = models.BooleanField(blank=True, null=True, default=False)
    bookings_cnt = models.IntegerField(default=0, blank=True, null=True)
    # Used for manifests bookings to book on TNT
    need_truck = models.BooleanField(default=False, blank=True, null=True)
    note = models.BooleanField(default=None, blank=True, null=True)
    z_createdByAccount = models.CharField(
        verbose_name=_("Created by account"), max_length=64, blank=True, null=True
    )
    z_createdTimeStamp = models.DateTimeField(
        verbose_name=_("Created Timestamp"),
        null=True,
        blank=True,
        auto_now_add=True,
    )
    z_modifiedByAccount = models.CharField(
        verbose_name=_("Modified by account"), max_length=64, blank=True, null=True
    )
    z_modifiedTimeStamp = models.DateTimeField(
        verbose_name=_("Modified Timestamp"),
        null=True,
        blank=True,
        auto_now=True,
    )

    class Meta:
        db_table = "dme_manifest_log"


class RuleTypes(models.Model):
    id = models.AutoField(primary_key=True)
    rule_type_code = models.CharField(
        max_length=16,
        blank=True,
        null=True,
        default=None,
    )
    calc_type = models.CharField(
        max_length=128,
        blank=True,
        null=True,
        default=None,
    )
    charge_rule = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        default=None,
    )
    z_createdByAccount = models.CharField(
        verbose_name=_("Created by account"), max_length=64, blank=True, null=True
    )
    z_createdTimeStamp = models.DateTimeField(
        verbose_name=_("Created Timestamp"),
        null=True,
        blank=True,
        auto_now_add=True,
    )
    z_modifiedByAccount = models.CharField(
        verbose_name=_("Modified by account"), max_length=64, blank=True, null=True
    )
    z_modifiedTimeStamp = models.DateTimeField(
        verbose_name=_("Modified Timestamp"),
        null=True,
        blank=True,
        auto_now=True,
    )

    class Meta:
        db_table = "rule_types"


class Fp_freight_providers(models.Model):
    id = models.AutoField(primary_key=True)
    fp_company_name = models.CharField(max_length=64, blank=True, null=True)
    fp_address_country = models.CharField(max_length=32, blank=True, null=True)
    fp_inactive_date = models.DateField(blank=True, null=True)
    fp_manifest_cnt = models.IntegerField(default=1, blank=True, null=True)
    new_connot_index = models.IntegerField(default=1, blank=True, null=True)
    fp_markupfuel_levy_percent = models.FloatField(default=0, blank=True, null=True)
    prices_count = models.IntegerField(default=1, blank=True, null=True)
    service_cutoff_time = models.TimeField(default=None, blank=True, null=True)
    rule_type = models.ForeignKey(RuleTypes, on_delete=models.CASCADE, null=True)
    hex_color_code = models.CharField(max_length=6, blank=True, null=True)
    category = models.CharField(max_length=64, blank=True, null=True, default=None)
    last_vehicle_number = models.IntegerField(default=0, blank=True, null=True)
    last_atl_number = models.IntegerField(default=0, blank=True, null=True)
    z_createdByAccount = models.CharField(
        verbose_name=_("Created by account"), max_length=64, blank=True, null=True
    )
    z_createdTimeStamp = models.DateTimeField(
        verbose_name=_("Created Timestamp"),
        null=True,
        blank=True,
        auto_now_add=True,
    )
    z_modifiedByAccount = models.CharField(
        verbose_name=_("Modified by account"), max_length=64, blank=True, null=True
    )
    z_modifiedTimeStamp = models.DateTimeField(
        verbose_name=_("Modified Timestamp"),
        null=True,
        blank=True,
        auto_now=True,
    )

    class Meta:
        db_table = "fp_freight_providers"

    def __str__(self):
        return self.fp_company_name


class FP_vehicles(models.Model):
    id = models.AutoField(primary_key=True)
    freight_provider = models.ForeignKey(Fp_freight_providers, on_delete=models.CASCADE)
    description = models.CharField(
        max_length=64,
        blank=True,
        null=True,
        default=None,
    )
    dim_UOM = models.CharField(
        max_length=16,
        blank=True,
        null=True,
        default=None,
    )
    max_length = models.FloatField(default=0, null=True, blank=True)
    max_width = models.FloatField(default=0, null=True, blank=True)
    max_height = models.FloatField(default=0, null=True, blank=True)
    mass_UOM = models.CharField(
        max_length=16,
        blank=True,
        null=True,
        default=None,
    )
    max_mass = models.IntegerField(default=0, null=True, blank=True)
    max_cbm = models.FloatField(default=None, null=True)  # Cubic Meter
    pallets = models.IntegerField(default=0, null=True, blank=True)
    pallet_UOM = models.CharField(
        max_length=16,
        blank=True,
        null=True,
        default=None,
    )
    max_pallet_length = models.FloatField(default=0, null=True, blank=True)
    max_pallet_width = models.FloatField(default=0, null=True, blank=True)
    max_pallet_height = models.FloatField(default=0, null=True, blank=True)
    base_charge = models.IntegerField(default=0, null=True, blank=True)
    min_charge = models.IntegerField(default=0, null=True, blank=True)
    limited_state = models.CharField(
        max_length=16,
        blank=True,
        null=True,
        default=None,
    )
    category = models.CharField(max_length=16, null=True, default=None)

    class Meta:
        db_table = "fp_vehicles"


class DME_Service_Codes(models.Model):
    id = models.AutoField(primary_key=True)
    service_code = models.CharField(max_length=32, blank=True, null=True, default=None)
    service_name = models.CharField(max_length=32, blank=True, null=True, default=None)
    description = models.CharField(max_length=128, blank=True, null=True, default=None)
    z_createdByAccount = models.CharField(
        verbose_name=_("Created by account"), max_length=64, blank=True, null=True
    )
    z_createdTimeStamp = models.DateTimeField(
        verbose_name=_("Created Timestamp"),
        null=True,
        blank=True,
        auto_now_add=True,
    )
    z_modifiedByAccount = models.CharField(
        verbose_name=_("Modified by account"), max_length=64, blank=True, null=True
    )
    z_modifiedTimeStamp = models.DateTimeField(
        verbose_name=_("Modified Timestamp"),
        null=True,
        blank=True,
        auto_now=True,
    )

    class Meta:
        db_table = "dme_service_codes"


class FP_Service_ETDs(models.Model):
    id = models.AutoField(primary_key=True)
    freight_provider = models.ForeignKey(Fp_freight_providers, on_delete=models.CASCADE)
    dme_service_code = models.ForeignKey(DME_Service_Codes, on_delete=models.CASCADE)
    fp_delivery_service_code = models.CharField(
        max_length=64, blank=True, null=True, default=None
    )
    fp_delivery_time_description = models.TextField(
        max_length=512, blank=True, null=True, default=None
    )
    fp_service_time_uom = models.CharField(
        max_length=16, blank=True, null=True, default=None
    )
    fp_03_delivery_hours = models.FloatField(blank=True, null=True, default=None)
    service_cutoff_time = models.TimeField(default=None, blank=True, null=True)
    z_createdByAccount = models.CharField(
        verbose_name=_("Created by account"), max_length=64, blank=True, null=True
    )
    z_createdTimeStamp = models.DateTimeField(
        verbose_name=_("Created Timestamp"),
        null=True,
        blank=True,
        auto_now_add=True,
    )
    z_modifiedByAccount = models.CharField(
        verbose_name=_("Modified by account"), max_length=64, blank=True, null=True
    )
    z_modifiedTimeStamp = models.DateTimeField(
        verbose_name=_("Modified Timestamp"),
        null=True,
        blank=True,
        auto_now=True,
    )

    class Meta:
        db_table = "fp_service_etds"


class API_booking_quotes(models.Model):
    ORIGINAL = "original"
    AUTO_PACK = "auto"
    MANUAL_PACK = "manual"
    SCANNED_PACK = "scanned"
    PACKED_STATUS_CHOICES = (
        (ORIGINAL, "original"),
        (AUTO_PACK, "auto"),
        (MANUAL_PACK, "manual"),
        (SCANNED_PACK, "scanned"),
    )

    id = models.AutoField(primary_key=True)
    api_results_id = models.CharField(
        verbose_name=_("Result ID"), blank=True, null=True, max_length=128
    )
    fk_booking_id = models.CharField(
        verbose_name=_("Booking ID"), max_length=64, blank=True, null=True
    )
    fk_client_id = models.CharField(
        verbose_name=_("Client ID"), max_length=64, blank=True, null=True
    )
    freight_provider = models.CharField(
        verbose_name=_("Freight Provider ID"), max_length=64, blank=True, null=True
    )
    account_code = models.CharField(
        verbose_name=_("Account Code"), max_length=32, blank=True, null=True
    )
    provider = models.CharField(
        verbose_name=_("Provider"), max_length=64, blank=True, null=True
    )
    service_code = models.CharField(
        verbose_name=_("Service Code"), max_length=32, blank=True, null=True
    )
    service_name = models.CharField(
        verbose_name=_("Service Name"), max_length=64, blank=True, null=True
    )
    fee = models.FloatField(verbose_name=_("Fee"), blank=True, null=True)
    etd = models.CharField(verbose_name=_("ETD"), max_length=64, blank=True, null=True)
    tax_id_1 = models.CharField(
        verbose_name=_("Tax ID 1"), max_length=10, blank=True, null=True
    )
    tax_value_1 = models.FloatField(
        verbose_name=_("Tax Value 1"), blank=True, null=True
    )
    tax_id_2 = models.CharField(
        verbose_name=_("Tax ID 2"), max_length=10, blank=True, null=True
    )
    tax_value_2 = models.FloatField(
        verbose_name=_("Tax Value 2"), blank=True, null=True
    )
    tax_id_3 = models.CharField(
        verbose_name=_("Tax ID 3"), max_length=10, blank=True, null=True
    )
    tax_value_3 = models.FloatField(
        verbose_name=_("Tax Value 3"), blank=True, null=True
    )
    tax_id_5 = models.CharField(
        verbose_name=_("Tax ID 5"), max_length=10, blank=True, null=True
    )
    tax_value_5 = models.FloatField(
        verbose_name=_("Tax Value 5"), blank=True, null=True
    )
    lowest_quote_flag = models.BooleanField(blank=True, null=True, default=None)
    b_client_markup2_percentage = models.FloatField(
        verbose_name=_("Client Markup2 Percent"), blank=True, null=True
    )
    fp_01_pu_possible = models.CharField(
        verbose_name=_("PU possible"), max_length=64, blank=True, null=True
    )
    fp_02_del_possible = models.CharField(
        verbose_name=_("DEL possible"), max_length=64, blank=True, null=True
    )
    fp_03_del_possible_price = models.CharField(
        verbose_name=_("DEL possible price"), max_length=64, blank=True, null=True
    )
    booking_cut_off = models.DateTimeField(
        verbose_name=_("Booking cut off"), default=timezone.now, blank=True, null=True
    )
    collection_cut_off = models.DateTimeField(
        verbose_name=_("Collection cut off"),
        default=timezone.now,
        blank=True,
        null=True,
    )
    mu_percentage_fuel_levy = models.FloatField(
        verbose_name=_("Mu Percentage Fuel Levy"), blank=True, null=True
    )
    fuel_levy_base = models.FloatField(blank=True, null=True, default=0)
    client_mark_up_percent = models.FloatField(blank=True, null=True, default=0)
    client_mu_1_minimum_values = models.FloatField(
        verbose_name=_("Client MU 1 Minimum Value"), blank=True, null=True
    )  # fee * (1 + mu_percentage_fuel_levy)
    x_price_per_UOM = models.IntegerField(
        verbose_name=_("Price per UOM"), blank=True, null=True
    )
    fp_latest_promised_pu = models.DateTimeField(
        verbose_name=_("Lastest Promised PU"),
        default=timezone.now,
        blank=True,
        null=True,
    )
    fp_latest_promised_del = models.DateTimeField(
        verbose_name=_("Lastest Timestamp DEL"),
        default=timezone.now,
        blank=True,
        null=True,
    )
    x_for_dme_price_ToxbyPricePerUOM = models.IntegerField(
        verbose_name=_("For DME Price ToxByPricePerUOM"), blank=True, null=True
    )
    x_for_dem_price_base_price = models.IntegerField(
        verbose_name=_("For DEM Price Base Price"), blank=True, null=True
    )
    x_fk_pricin_id = models.IntegerField(
        verbose_name=_("Pricin ID"), blank=True, null=True
    )
    x_price_surcharge = models.FloatField(
        verbose_name=_("Price Surcharge"), blank=True, null=True
    )  # Total of surcharges
    x_minumum_charge = models.IntegerField(
        verbose_name=_("Minimum Charge"), blank=True, null=True
    )
    z_fp_delivery_hours = models.IntegerField(
        verbose_name=_("Delivery Hours"), blank=True, null=True
    )
    z_03_selected_lowest_priced_FC_that_passed = models.FloatField(
        verbose_name=_("Selected Lowest Priced FC That Passed"), blank=True, null=True
    )
    zc_dme_service_translation_nocalc = models.CharField(
        verbose_name=_("DME service translation no calc"),
        max_length=64,
        blank=True,
        null=True,
    )
    z_selected_manual_auto = models.CharField(
        verbose_name=_("Selected Manual Auto"), max_length=64, blank=True, null=True
    )
    z_selected_timestamp = models.DateTimeField(
        verbose_name=_("Selected Timestamp"), default=timezone.now
    )
    is_used = models.BooleanField(default=False)
    is_from_api = models.BooleanField(default=False)
    vehicle = models.ForeignKey(
        FP_vehicles, on_delete=models.CASCADE, null=True, default=None
    )
    packed_status = models.CharField(
        max_length=16, default=None, null=True, choices=PACKED_STATUS_CHOICES
    )
    notes = models.CharField(max_length=255, default=None, null=True)
    pickup_timestamp = models.DateTimeField(null=True, blank=True)
    delivery_timestamp = models.DateTimeField(null=True, blank=True)
    z_createdByAccount = models.CharField(
        verbose_name=_("Created by account"), max_length=64, blank=True, null=True
    )
    z_createdTimeStamp = models.DateTimeField(
        verbose_name=_("Created Timestamp"),
        null=True,
        blank=True,
        auto_now_add=True,
    )
    z_modifiedByAccount = models.CharField(
        verbose_name=_("Modified by account"), max_length=64, blank=True, null=True
    )
    z_modifiedTimeStamp = models.DateTimeField(
        verbose_name=_("Modified Timestamp"),
        null=True,
        blank=True,
        auto_now=True,
    )

    class Meta:
        db_table = "api_booking_quotes"

    def __str__(self):
        return f"Quote: {self.id}, {self.freight_provider}"


class Bookings(models.Model):
    PDWD = "Pickup at Door / Warehouse Dock"
    DDWD = "Drop at Door / Warehouse Dock"
    DDW = "Drop in Door / Warehouse"
    ROC = "Room of Choice"
    LOCATION_CHOICES = (
        (PDWD, "Pickup at Door / Warehouse Dock"),
        (DDWD, "Drop at Door / Warehouse Dock"),
        (DDW, "Drop in Door / Warehouse"),
        (ROC, "Room of Choice"),
    )

    NONE = "NONE"
    ELEVATOR = "Elevator"
    ESCALATOR = "Escalator"
    STAIRS = "Stairs"
    FLOOR_ACCESS_BY_CHOICES = (
        (NONE, "NONE"),
        (ELEVATOR, "Elevator"),
        (ESCALATOR, "Escalator"),
        (STAIRS, "Stairs"),
    )

    DMEM = "DMEM"  # Manual
    DMEA = "DMEA"  # Auto
    DMEP = "DMEP"  # Pickup
    BOOKING_TYPE_CHOICES = ((DMEM, "DMEM"), (DMEA, "DMEA"), (DMEP, "DMEP"))

    ORIGINAL = "original"
    AUTO_PACK = "auto"
    MANUAL_PACK = "manual"
    SCANNED_PACK = "scanned"
    PACKED_STATUS_CHOICES = (
        (ORIGINAL, "original"),
        (AUTO_PACK, "auto"),
        (MANUAL_PACK, "manual"),
        (SCANNED_PACK, "scanned"),
    )

    id = models.AutoField(primary_key=True)
    b_bookingID_Visual = models.IntegerField(
        verbose_name=_("BookingID Visual"), blank=True, null=True, default=0
    )
    b_dateBookedDate = models.DateTimeField(
        verbose_name=_("Booked Date"), blank=True, null=True, default=None
    )
    puPickUpAvailFrom_Date = models.DateField(
        verbose_name=_("PickUp Available From"), blank=True, null=True, default=None
    )
    b_clientReference_RA_Numbers = models.CharField(
        verbose_name=_("Client Reference Ra Numbers"),
        max_length=1000,
        blank=True,
        null=True,
        default=None,
    )
    b_status = models.CharField(
        verbose_name=_("Status"), max_length=40, blank=True, null=True, default=None
    )
    b_status_category = models.CharField(
        max_length=32, blank=True, null=True, default=None
    )
    vx_freight_provider = models.CharField(
        verbose_name=_("Freight Provider"),
        max_length=100,
        blank=True,
        null=True,
        default=None,
    )
    vx_serviceName = models.CharField(
        verbose_name=_("Service Name"),
        max_length=50,
        blank=True,
        null=True,
        default=None,
    )
    v_FPBookingNumber = models.CharField(
        verbose_name=_("FP Booking Number"),
        max_length=40,
        blank=True,
        null=True,
        default=None,
    )
    puCompany = models.CharField(
        verbose_name=_("Company"), max_length=128, blank=True, null=True, default=None
    )
    deToCompanyName = models.CharField(
        verbose_name=_("Company Name"),
        max_length=128,
        blank=True,
        null=True,
        default=None,
    )
    consignment_label_link = models.CharField(
        verbose_name=_("Consignment"),
        max_length=250,
        blank=True,
        null=True,
        default=None,
    )
    error_details = models.CharField(
        verbose_name=_("Error Detail"),
        max_length=250,
        blank=True,
        null=True,
        default=None,
    )
    fk_client_warehouse = models.ForeignKey(
        Client_warehouses, on_delete=models.CASCADE, default="1"
    )
    b_clientPU_Warehouse = models.CharField(
        verbose_name=_("warehouse"), max_length=64, blank=True, null=True, default=None
    )
    is_printed = models.BooleanField(
        verbose_name=_("Is printed"), default=False, blank=True, null=True
    )
    shipping_label_base64 = models.CharField(
        verbose_name=_("Based64 Label"),
        max_length=255,
        blank=True,
        null=True,
        default=None,
    )
    kf_client_id = models.CharField(
        verbose_name=_("KF Client ID"),
        max_length=64,
        blank=True,
        null=True,
        default=None,
    )
    b_client_name = models.CharField(
        verbose_name=_("Client Name"),
        max_length=36,
        blank=True,
        null=True,
        default=None,
    )
    pk_booking_id = models.CharField(
        verbose_name=_("Booking ID"), max_length=64, blank=True, null=True, default=None
    )
    zb_002_client_booking_key = models.CharField(
        verbose_name=_("Client Booking Key"),
        max_length=64,
        blank=True,
        null=True,
        default=None,
    )
    fk_fp_pickup_id = models.CharField(
        verbose_name=_("KF FP pickup id"),
        max_length=64,
        blank=True,
        null=True,
        default=None,
    )
    pu_pickup_instructions_address = models.TextField(
        verbose_name=_("Pickup instrunctions address"),
        max_length=512,
        blank=True,
        null=True,
        default=None,
    )
    kf_staff_id = models.CharField(
        verbose_name=_("Staff ID"), max_length=64, blank=True, null=True, default=None
    )
    kf_clientCustomerID_PU = models.CharField(
        verbose_name=_("Custom ID Pick Up"),
        max_length=64,
        blank=True,
        null=True,
        default=None,
    )
    kf_clientCustomerID_DE = models.CharField(
        verbose_name=_("Custom ID Deliver"),
        max_length=64,
        blank=True,
        null=True,
        default=None,
    )
    kf_Add_ID_PU = models.CharField(
        verbose_name=_("Add ID Pick Up"),
        max_length=64,
        blank=True,
        null=True,
        default=None,
    )
    kf_Add_ID_DE = models.CharField(
        verbose_name=_("Add ID Deliver"),
        max_length=64,
        blank=True,
        null=True,
        default=None,
    )
    kf_FP_ID = models.CharField(
        verbose_name=_("FP ID"), max_length=64, blank=True, null=True, default=None
    )
    kf_booking_Created_For_ID = models.CharField(
        verbose_name=_("Booking Created For ID"),
        max_length=64,
        blank=True,
        null=True,
        default=None,
    )
    kf_email_Template = models.CharField(
        verbose_name=_("Email Template"),
        max_length=64,
        blank=True,
        null=True,
        default=None,
    )
    inv_dme_invoice_no = models.CharField(
        verbose_name=_("Invoice Num Booking"),
        max_length=64,
        blank=True,
        null=True,
        default=None,
    )
    kf_booking_quote_import_id = models.CharField(
        verbose_name=_("Booking Quote Import ID"),
        max_length=64,
        blank=True,
        null=True,
        default=None,
    )
    kf_order_id = models.CharField(
        verbose_name=_("Order ID"), max_length=64, blank=True, null=True, default=None
    )
    x_Data_Entered_Via = models.CharField(
        verbose_name=_("Data Entered Via"),
        max_length=64,
        blank=True,
        null=True,
        default=None,
    )
    b_booking_Priority = models.CharField(
        verbose_name=_("Booking Priority"),
        max_length=32,
        blank=True,
        null=True,
        default=None,
    )
    z_API_Issue = models.IntegerField(
        verbose_name=_("Api Issue"), blank=True, null=True, default=0
    )
    z_api_issue_update_flag_500 = models.BooleanField(
        verbose_name=_("API Issue Update Flag 500"),
        default=False,
        blank=True,
        null=True,
    )
    pu_Address_Type = models.CharField(
        verbose_name=_("PU Address Type"),
        max_length=25,
        blank=True,
        null=True,
        default=None,
    )
    pu_Address_Street_1 = models.CharField(
        verbose_name=_("PU Address Street 1"),
        max_length=80,
        blank=True,
        null=True,
        default=None,
    )
    pu_Address_street_2 = models.CharField(
        verbose_name=_("PU Address Street 2"),
        max_length=40,
        blank=True,
        null=True,
        default=None,
    )
    pu_Address_State = models.CharField(
        verbose_name=_("PU Address State"),
        max_length=25,
        blank=True,
        null=True,
        default=None,
    )
    pu_Address_City = models.CharField(
        verbose_name=_("PU Address City"),
        max_length=50,
        blank=True,
        null=True,
        default=None,
    )
    pu_Address_Suburb = models.CharField(
        verbose_name=_("PU Address Suburb"),
        max_length=50,
        blank=True,
        null=True,
        default=None,
    )
    pu_Address_PostalCode = models.CharField(
        verbose_name=_("PU Address Postal Code"),
        max_length=25,
        blank=True,
        null=True,
        default=None,
    )
    pu_Address_Country = models.CharField(
        verbose_name=_("PU Address Country"),
        max_length=50,
        blank=True,
        null=True,
        default=None,
    )
    pu_Contact_F_L_Name = models.CharField(
        verbose_name=_("PU Contact Name"),
        max_length=25,
        blank=True,
        null=True,
        default=None,
    )
    pu_Phone_Main = models.CharField(
        verbose_name=_("PU Phone Main"),
        max_length=25,
        blank=True,
        null=True,
        default=None,
    )
    pu_Phone_Mobile = models.CharField(
        verbose_name=_("PU Phone Mobile"),
        max_length=25,
        blank=True,
        null=True,
        default=None,
    )
    pu_Email = models.CharField(
        verbose_name=_("PU Email"), max_length=64, blank=True, null=True, default=None
    )
    pu_email_Group_Name = models.CharField(
        verbose_name=_("PU Email Group Name"),
        max_length=25,
        blank=True,
        null=True,
        default=None,
    )
    pu_email_Group = models.TextField(
        verbose_name=_("PU Email Group"),
        max_length=512,
        blank=True,
        null=True,
        default=None,
    )
    pu_Comm_Booking_Communicate_Via = models.CharField(
        verbose_name=_("PU Booking Communicate Via"),
        max_length=25,
        blank=True,
        null=True,
        default=None,
    )
    pu_Contact_FName = models.CharField(
        verbose_name=_("PU Contact First Name"),
        max_length=25,
        blank=True,
        null=True,
        default=None,
    )
    pu_PickUp_Instructions_Contact = models.TextField(
        verbose_name=_("PU Instructions Contact"),
        max_length=512,
        blank=True,
        null=True,
        default=None,
    )
    pu_WareHouse_Number = models.CharField(
        verbose_name=_("PU Warehouse Number"),
        max_length=10,
        blank=True,
        null=True,
        default=None,
    )
    pu_WareHouse_Bay = models.CharField(
        verbose_name=_("PU Warehouse Bay"),
        max_length=10,
        blank=True,
        null=True,
        default=None,
    )
    pu_Contact_Lname = models.CharField(
        verbose_name=_("PU Contact Last Name"),
        max_length=25,
        blank=True,
        null=True,
        default=None,
    )
    de_Email = models.CharField(
        verbose_name=_("DE Email"), max_length=64, blank=True, null=True, default=None
    )
    de_To_AddressType = models.CharField(
        verbose_name=_("DE Address Type"),
        max_length=20,
        blank=True,
        null=True,
        default=None,
    )
    de_To_Address_Street_1 = models.CharField(
        verbose_name=_("DE Address Street 1"),
        max_length=40,
        blank=True,
        null=True,
        default=None,
    )
    de_To_Address_Street_2 = models.CharField(
        verbose_name=_("DE Address Street 2"),
        max_length=40,
        blank=True,
        null=True,
        default=None,
    )
    de_To_Address_State = models.CharField(
        verbose_name=_("DE Address State"),
        max_length=20,
        blank=True,
        null=True,
        default=None,
    )
    de_To_Address_City = models.CharField(
        verbose_name=_("DE Address City"),
        max_length=40,
        blank=True,
        null=True,
        default=None,
    )
    de_To_Address_Suburb = models.CharField(
        verbose_name=_("DE Address Suburb"),
        max_length=50,
        blank=True,
        null=True,
        default=None,
    )
    de_To_Address_PostalCode = models.CharField(
        verbose_name=_("DE Address Postal Code"),
        max_length=30,
        blank=True,
        null=True,
        default=None,
    )
    de_To_Address_Country = models.CharField(
        verbose_name=_("DE Address Country"),
        max_length=12,
        blank=True,
        null=True,
        default=None,
    )
    de_to_Contact_F_LName = models.CharField(
        verbose_name=_("DE Contact Name"),
        max_length=50,
        blank=True,
        null=True,
        default=None,
    )
    de_to_Contact_FName = models.CharField(
        verbose_name=_("DE Contact First Name"),
        max_length=25,
        blank=True,
        null=True,
        default=None,
    )
    de_to_Contact_Lname = models.CharField(
        verbose_name=_("DE Contact Last Name"),
        max_length=25,
        blank=True,
        null=True,
        default=None,
    )
    de_To_Comm_Delivery_Communicate_Via = models.CharField(
        verbose_name=_("DE Communicate Via"),
        max_length=40,
        blank=True,
        null=True,
        default=None,
    )
    de_to_Pick_Up_Instructions_Contact = models.TextField(
        verbose_name=_("DE Instructions Contact"),
        max_length=512,
        blank=True,
        null=True,
        default=None,
    )
    de_to_PickUp_Instructions_Address = models.TextField(
        verbose_name=_("DE Instructions Address"),
        max_length=512,
        blank=True,
        null=True,
        default=None,
    )
    de_to_WareHouse_Number = models.CharField(
        verbose_name=_("DE Warehouse Number"),
        max_length=30,
        blank=True,
        null=True,
        default=None,
    )
    de_to_WareHouse_Bay = models.CharField(
        verbose_name=_("DE Warehouse Bay"),
        max_length=25,
        blank=True,
        null=True,
        default=None,
    )
    de_to_Phone_Mobile = models.CharField(
        verbose_name=_("DE Phone Mobile"),
        max_length=25,
        blank=True,
        null=True,
        default=None,
    )
    de_to_Phone_Main = models.CharField(
        verbose_name=_("DE Phone Main"),
        max_length=30,
        blank=True,
        null=True,
        default=None,
    )
    de_to_addressed_Saved = models.IntegerField(
        verbose_name=_("DE Addressed Saved"), blank=True, default=0, null=True
    )
    de_Contact = models.CharField(
        verbose_name=_("DE Contact"), max_length=50, blank=True, null=True, default=None
    )
    pu_PickUp_By_Date = models.DateField(
        verbose_name=_("PickUp By Date"), blank=True, null=True, default=None
    )
    pu_addressed_Saved = models.IntegerField(
        verbose_name=_("PU Addressed Saved"), blank=True, null=True, default=0
    )
    b_date_booked_by_dme = models.DateField(
        verbose_name=_("Date Booked By DME"), blank=True, null=True, default=None
    )
    b_booking_Notes = models.TextField(
        verbose_name=_("Booking Notes"),
        max_length=400,
        blank=True,
        null=True,
        default=None,
    )
    s_02_Booking_Cutoff_Time = models.TimeField(
        verbose_name=_("Booking Cutoff Time"), blank=True, null=True, default=None
    )
    s_05_Latest_PickUp_Date_Time_Override = models.DateTimeField(
        verbose_name=_("Latest PU DateTime Override"),
        blank=True,
        null=True,
        default=None,
    )
    s_05_Latest_Pick_Up_Date_TimeSet = models.DateTimeField(
        verbose_name=_("Latest PU DateTime Set"), blank=True, null=True, default=None
    )
    s_06_Latest_Delivery_Date_Time_Override = models.DateTimeField(
        verbose_name=_("Latest DE DateTime Override"),
        blank=True,
        null=True,
        default=None,
    )
    s_06_Latest_Delivery_Date_TimeSet = models.DateTimeField(
        verbose_name=_("Latest DE DateTime Set"), blank=True, null=True, default=None
    )
    s_07_PickUp_Progress = models.CharField(
        verbose_name=_("PU Progress"),
        max_length=30,
        blank=True,
        null=True,
        default=None,
    )
    s_08_Delivery_Progress = models.CharField(
        verbose_name=_("DE Progress"),
        max_length=30,
        blank=True,
        null=True,
        default=None,
    )
    s_20_Actual_Pickup_TimeStamp = models.DateTimeField(
        verbose_name=_("Actual PU TimeStamp"), blank=True, null=True, default=None
    )
    s_21_Actual_Delivery_TimeStamp = models.DateTimeField(
        verbose_name=_("Actual DE TimeStamp"), blank=True, null=True, default=None
    )
    b_handling_Instructions = models.TextField(
        verbose_name=_("Handling Instructions"),
        max_length=120,
        blank=True,
        null=True,
        default=None,
    )
    v_price_Booking = models.FloatField(
        verbose_name=_("Price Booking"), default=0, blank=True, null=True
    )
    v_service_Type_2 = models.CharField(
        verbose_name=_("Service Type 2"),
        max_length=30,
        blank=True,
        null=True,
        default=None,
    )
    b_status_API = models.CharField(
        verbose_name=_("Status API"),
        max_length=255,
        blank=True,
        null=True,
        default=None,
    )
    v_vehicle_Type = models.CharField(
        verbose_name=_("Vehicle Type"),
        max_length=64,
        blank=True,
        null=True,
        default=None,
    )
    v_customer_code = models.CharField(
        verbose_name=_("Customer Code"),
        max_length=20,
        blank=True,
        null=True,
        default=None,
    )
    b_promo_code = models.CharField(
        verbose_name=_("Promotion Code"),
        max_length=32,
        blank=True,
        null=True,
        default=None,
    )
    v_service_Type_ID = models.CharField(
        verbose_name=_("Service Type ID"),
        max_length=64,
        blank=True,
        null=True,
        default=None,
    )
    v_service_Type = models.CharField(
        verbose_name=_("Service Type"),
        max_length=25,
        blank=True,
        null=True,
        default=None,
    )
    v_serviceCode_DME = models.CharField(
        verbose_name=_("Service Code DME"),
        max_length=10,
        blank=True,
        null=True,
        default=None,
    )
    v_serviceTime_End = models.TimeField(
        verbose_name=_("Service Time End"), blank=True, null=True, default=None
    )
    v_serviceTime_Start = models.TimeField(
        verbose_name=_("Service Time Start"), blank=True, null=True, default=None
    )
    v_serviceDelivery_Days = models.IntegerField(
        verbose_name=_("Service DE Days"), blank=True, default=0, null=True
    )
    v_service_Delivery_Hours = models.IntegerField(
        verbose_name=_("Service DE Hours"), blank=True, default=0, null=True
    )
    v_service_DeliveryHours_TO_PU = models.IntegerField(
        verbose_name=_("Service DE Hours To PU"), blank=True, default=0, null=True
    )
    x_booking_Created_With = models.CharField(
        verbose_name=_("Booking Created With"),
        max_length=32,
        blank=True,
        null=True,
        default=None,
    )
    x_manual_booked_flag = models.BooleanField(default=False, blank=True, null=True)
    de_Email_Group_Emails = models.TextField(
        verbose_name=_("DE Email Group Emails"),
        max_length=512,
        blank=True,
        null=True,
        default=None,
    )
    de_Email_Group_Name = models.CharField(
        verbose_name=_("DE Email Group Name"),
        max_length=30,
        blank=True,
        null=True,
        default=None,
    )
    de_Options = models.CharField(
        verbose_name=_("DE Options"), max_length=30, blank=True, null=True, default=None
    )
    total_lines_qty_override = models.FloatField(
        verbose_name=_("Total Lines Qty Override"), blank=True, default=0, null=True
    )
    total_1_KG_weight_override = models.FloatField(
        verbose_name=_("Total 1Kg Weight Override"), default=0, blank=True, null=True
    )
    total_Cubic_Meter_override = models.FloatField(
        verbose_name=_("Total Cubic Meter Override"), default=0, blank=True, null=True
    )
    booked_for_comm_communicate_via = models.CharField(
        verbose_name=_("Booked Communicate Via"),
        max_length=120,
        blank=True,
        null=True,
        default=None,
    )
    booking_Created_For = models.CharField(
        verbose_name=_("Booking Created For"),
        max_length=64,
        blank=True,
        null=True,
        default=None,
    )
    b_order_created = models.CharField(
        verbose_name=_("Order Created"),
        max_length=45,
        blank=True,
        null=True,
        default=None,
    )
    b_error_Capture = models.TextField(
        verbose_name=_("Error Capture"),
        max_length=1000,
        blank=True,
        null=True,
        default=None,
    )
    b_error_code = models.CharField(
        verbose_name=_("Error Code"), max_length=20, blank=True, null=True, default=None
    )
    b_booking_Category = models.CharField(
        verbose_name=_("Booking Categroy"),
        max_length=64,
        blank=True,
        null=True,
        default=None,
    )
    pu_PickUp_By_Time_Hours = models.IntegerField(
        verbose_name=_("PU By Time Hours"), blank=True, default=0, null=True
    )
    pu_PickUp_By_Time_Minutes = models.IntegerField(
        verbose_name=_("PU By Time Minutes"), blank=True, default=0, null=True
    )
    pu_PickUp_Avail_Time_Hours = models.IntegerField(
        verbose_name=_("PU Available Time Hours"), blank=True, default=0, null=True
    )
    pu_PickUp_Avail_Time_Minutes = models.IntegerField(
        verbose_name=_("PU Available Time Minutes"), blank=True, default=0, null=True
    )
    pu_PickUp_Avail_From_Date_DME = models.DateField(
        verbose_name=_("PU Available From Date DME"),
        blank=True,
        null=True,
        default=None,
    )
    pu_PickUp_Avail_Time_Hours_DME = models.IntegerField(
        verbose_name=_("PU Available Time Hours DME"), blank=True, default=0, null=True
    )
    pu_PickUp_Avail_Time_Minutes_DME = models.IntegerField(
        verbose_name=_("PU Available Time Minutes DME"),
        blank=True,
        default=0,
        null=True,
    )
    pu_PickUp_By_Date_DME = models.DateField(
        verbose_name=_("PU By Date DME"), blank=True, null=True, default=None
    )
    pu_PickUp_By_Time_Hours_DME = models.IntegerField(
        verbose_name=_("PU By Time Hours DME"), blank=True, default=0, null=True
    )
    pu_PickUp_By_Time_Minutes_DME = models.IntegerField(
        verbose_name=_("PU By Time Minutes DME"), blank=True, default=0, null=True
    )
    pu_Actual_Date = models.DateField(
        verbose_name=_("PU Actual Date"), blank=True, null=True, default=None
    )
    pu_Actual_PickUp_Time = models.TimeField(
        verbose_name=_("Actual PU Time"), blank=True, null=True, default=None
    )
    de_Deliver_From_Date = models.DateField(
        verbose_name=_("DE From Date"), blank=True, null=True, default=None
    )
    de_Deliver_From_Hours = models.IntegerField(
        verbose_name=_("DE From Hours"), blank=True, default=0, null=True
    )
    de_Deliver_From_Minutes = models.IntegerField(
        verbose_name=_("DE From Minutes"), blank=True, default=0, null=True
    )
    de_Deliver_By_Date = models.DateField(
        verbose_name=_("DE By Date"), blank=True, null=True, default=None
    )
    de_Deliver_By_Hours = models.IntegerField(
        verbose_name=_("DE By Hours"), blank=True, default=0, null=True
    )
    de_Deliver_By_Minutes = models.IntegerField(
        verbose_name=_("De By Minutes"), blank=True, default=0, null=True
    )
    DME_Base_Cost = models.FloatField(
        verbose_name=_("DME Base Cost"), default=0, blank=True, null=True
    )
    vx_Transit_Duration = models.IntegerField(
        verbose_name=_("Transit Duration"), blank=True, default=0, null=True
    )
    vx_freight_time = models.DateTimeField(
        verbose_name=_("Freight Time"), blank=True, null=True, default=None
    )
    vx_price_Booking = models.FloatField(
        verbose_name=_("VX Price Booking"), default=0, blank=True, null=True
    )
    vx_price_Tax = models.FloatField(
        verbose_name=_("VX Price Tax"), default=0, blank=True, null=True
    )
    vx_price_Total_Sell_Price_Override = models.FloatField(
        verbose_name=_("VX Price Total Sell Price Override"),
        default=0,
        blank=True,
        null=True,
    )
    vx_fp_pu_eta_time = models.DateTimeField(
        verbose_name=_("FP PickUp ETA Time"), blank=True, null=True, default=None
    )
    vx_fp_del_eta_time = models.DateTimeField(
        verbose_name=_("FP Delivery ETA Time"), blank=True, null=True, default=None
    )
    vx_service_Name_ID = models.CharField(
        verbose_name=_("Service Name ID"),
        max_length=64,
        blank=True,
        null=True,
        default=None,
    )
    vx_futile_Booking_Notes = models.CharField(
        verbose_name=_("Futile Booking Notes"),
        max_length=200,
        blank=True,
        null=True,
        default=None,
    )
    z_CreatedByAccount = models.TextField(
        verbose_name=_("Created By Account"),
        max_length=30,
        blank=True,
        null=True,
        default=None,
    )
    pu_Operting_Hours = models.TextField(
        verbose_name=_("PU Operating hours"),
        max_length=500,
        blank=True,
        null=True,
        default=None,
    )
    de_Operating_Hours = models.TextField(
        verbose_name=_("DE Operating hours"),
        max_length=500,
        blank=True,
        null=True,
        default=None,
    )
    z_CreatedTimestamp = models.DateTimeField(blank=True, null=True, auto_now_add=True)
    z_ModifiedByAccount = models.CharField(
        verbose_name=_("Modified By Account"),
        max_length=25,
        blank=True,
        null=True,
        default=None,
    )
    z_ModifiedTimestamp = models.DateTimeField(null=True, blank=True, auto_now=True)
    pu_PickUp_TimeSlot_TimeEnd = models.TimeField(
        verbose_name=_("PU TimeSlot TimeEnd"), blank=True, null=True, default=None
    )
    de_TimeSlot_TimeStart = models.TimeField(
        verbose_name=_("DE TimeSlot TimeStart"), blank=True, null=True, default=None
    )
    de_TimeSlot_Time_End = models.TimeField(
        verbose_name=_("TimeSlot Time End"), blank=True, null=True, default=None
    )
    de_Nospecific_Time = models.IntegerField(
        verbose_name=_("No Specific Time"), blank=True, default=0, null=True
    )
    de_to_TimeSlot_Date_End = models.DateField(
        verbose_name=_("DE to TimeSlot Date End"), blank=True, null=True, default=None
    )
    rec_do_not_Invoice = models.IntegerField(
        verbose_name=_("Rec Doc Not Invoice"), blank=True, default=0, null=True
    )
    b_email_Template_Name = models.CharField(
        verbose_name=_("Email Template Name"),
        max_length=30,
        blank=True,
        null=True,
        default=None,
    )
    pu_No_specified_Time = models.IntegerField(
        verbose_name=_("PU No Specific Time"), blank=True, default=0, null=True
    )
    notes_cancel_Booking = models.CharField(
        verbose_name=_("Notes Cancel Booking"),
        max_length=500,
        blank=True,
        null=True,
        default=None,
    )
    booking_Created_For_Email = models.CharField(
        verbose_name=_("Booking Created For Email"),
        max_length=64,
        blank=True,
        null=True,
        default=None,
    )
    z_Notes_Bugs = models.CharField(
        verbose_name=_("Notes Bugs"),
        max_length=200,
        blank=True,
        null=True,
        default=None,
    )
    DME_GST_Percentage = models.IntegerField(
        verbose_name=_("DME GST Percentage"), blank=True, default=0, null=True
    )
    x_ReadyStatus = models.CharField(
        verbose_name=_("Ready Status"),
        max_length=32,
        blank=True,
        null=True,
        default=None,
    )
    DME_Notes = models.CharField(
        verbose_name=_("DME Notes"), max_length=500, blank=True, null=True, default=None
    )
    b_client_Reference_RA_Numbers_lastupdate = models.DateTimeField(
        verbose_name=_("Client Reference RA Number Last Update"),
        blank=True,
        null=True,
        default=None,
    )
    s_04_Max_Duration_To_Delivery_Number = models.IntegerField(
        verbose_name=_("04 Max Duration To Delivery Number"),
        blank=True,
        default=0,
        null=True,
    )
    b_client_MarkUp_PercentageOverRide = models.FloatField(
        verbose_name=_("Client MarkUp Percentage Override"),
        default=0,
        blank=True,
        null=True,
    )
    z_admin_dme_invoice_number = models.CharField(
        verbose_name=_("Admin DME Invoice Number"),
        max_length=25,
        blank=True,
        null=True,
        default=None,
    )
    z_included_with_manifest_date = models.DateTimeField(
        verbose_name=_("Included With Manifest Date"),
        blank=True,
        null=True,
        default=None,
    )
    b_dateinvoice = models.DateField(
        verbose_name=_("Date Invoice"), blank=True, null=True, default=None
    )
    b_booking_tail_lift_pickup = models.BooleanField(
        verbose_name=_("Booking Tail Lift PU"), default=False, blank=True, null=True
    )
    b_booking_tail_lift_deliver = models.BooleanField(
        verbose_name=_("Booking Tail Lift DE"), default=False, blank=True, null=True
    )
    b_booking_no_operator_pickup = models.PositiveIntegerField(
        verbose_name=_("Booking No Operator PU"), blank=True, default=None, null=True
    )
    b_bookingNoOperatorDeliver = models.PositiveIntegerField(
        verbose_name=_("Booking No Operator DE"), blank=True, default=None, null=True
    )
    b_ImportedFromFile = models.CharField(
        verbose_name=_("Imported File Filed"),
        max_length=128,
        blank=True,
        null=True,
        default=None,
    )
    b_email2_return_sent_numberofTimes = models.IntegerField(
        verbose_name=_("Email2 Return Sent Number Of Times"),
        blank=True,
        default=0,
        null=True,
    )
    b_email1_general_sent_Number_of_times = models.IntegerField(
        verbose_name=_("Email1 General sent Number Of Times"),
        blank=True,
        default=0,
        null=True,
    )
    b_email3_pickup_sent_numberOfTimes = models.IntegerField(
        verbose_name=_("Email3 PU Sent Number Of Times"),
        blank=True,
        default=0,
        null=True,
    )
    b_email4_futile_sent_number_of_times = models.IntegerField(
        verbose_name=_("Email4 Futile Sent Number Of Times"),
        blank=True,
        default=0,
        null=True,
    )
    b_send_POD_eMail = models.BooleanField(default=False, null=True, blank=True)
    b_booking_status_manual = models.CharField(
        verbose_name=_("Booking Status Manual"),
        max_length=30,
        blank=True,
        null=True,
        default=None,
    )
    b_booking_status_manual_DME = models.CharField(
        verbose_name=_("Booking Status Manual DME"),
        max_length=2,
        blank=True,
        null=True,
        default=None,
    )
    b_booking_statusmanual_DME_Note = models.CharField(
        verbose_name=_("Booking Status Manual DME Note"),
        max_length=200,
        blank=True,
        null=True,
        default=None,
    )
    client_overrided_quote = models.FloatField(blank=True, default=None, null=True)
    z_label_url = models.CharField(
        verbose_name=_("PDF Url"), max_length=255, blank=True, null=True, default=None
    )
    z_lastStatusAPI_ProcessedTimeStamp = models.DateTimeField(
        verbose_name=_("Last StatusAPI Processed Timestamp"),
        blank=True,
        null=True,
        default=None,
    )
    b_client_booking_ref_num = models.CharField(
        verbose_name=_("Booking Ref Num"),
        max_length=64,
        blank=True,
        null=True,
        default=None,
    )
    b_client_sales_inv_num = models.CharField(
        verbose_name=_("Sales Inv Num"),
        max_length=64,
        blank=True,
        null=True,
        default=None,
    )
    b_client_order_num = models.CharField(
        verbose_name=_("Order Num"), max_length=64, blank=True, null=True, default=None
    )
    b_client_del_note_num = models.CharField(
        verbose_name=_("Del Note Num"),
        max_length=64,
        blank=True,
        null=True,
        default=None,
    )
    b_client_warehouse_code = models.CharField(
        verbose_name=_("Warehouse code"),
        max_length=64,
        blank=True,
        null=True,
        default=None,
    )
    z_downloaded_shipping_label_timestamp = models.DateTimeField(
        verbose_name=_("downloaded_shipping_label_timestamp"),
        blank=True,
        null=True,
        default=None,
    )
    vx_fp_order_id = models.CharField(
        verbose_name=_("Order ID"), max_length=64, blank=True, null=True, default=None
    )
    z_manifest_url = models.CharField(
        verbose_name=_("Manifest URL"),
        max_length=128,
        blank=True,
        null=True,
        default=None,
    )
    z_pod_url = models.CharField(max_length=255, blank=True, null=True, default=None)
    z_pod_signed_url = models.CharField(
        max_length=255, blank=True, null=True, default=None
    )
    z_connote_url = models.CharField(
        max_length=255, blank=True, null=True, default=None
    )
    z_downloaded_pod_timestamp = models.DateTimeField(
        blank=True, null=True, default=None
    )
    z_downloaded_pod_sog_timestamp = models.DateTimeField(
        blank=True, null=True, default=None
    )
    z_downloaded_connote_timestamp = models.DateTimeField(
        blank=True, null=True, default=None
    )
    booking_api_start_TimeStamp = models.DateTimeField(
        blank=True, null=True, default=None
    )
    booking_api_end_TimeStamp = models.DateTimeField(
        blank=True, null=True, default=None
    )
    booking_api_try_count = models.IntegerField(blank=True, default=0, null=True)
    z_manual_booking_set_to_confirm = models.DateTimeField(
        blank=True, null=True, default=None
    )
    z_manual_booking_set_time_push_to_fm = models.DateTimeField(
        blank=True, null=True, default=None
    )
    z_lock_status = models.BooleanField(default=False, blank=True, null=True)
    z_locked_status_time = models.DateTimeField(blank=True, null=True, default=None)
    delivery_kpi_days = models.IntegerField(blank=True, default=0, null=True)
    delivery_days_from_booked = models.IntegerField(blank=True, default=0, null=True)
    delivery_actual_kpi_days = models.IntegerField(blank=True, default=0, null=True)
    b_status_sub_client = models.CharField(
        max_length=50, blank=True, null=True, default=None
    )
    b_status_sub_fp = models.CharField(
        max_length=50, blank=True, null=True, default=None
    )
    fp_store_event_date = models.DateField(blank=True, null=True, default=None)
    fp_store_event_time = models.TimeField(blank=True, null=True, default=None)
    fp_store_event_desc = models.CharField(
        max_length=255, blank=True, null=True, default=None
    )
    e_qty_scanned_fp_total = models.IntegerField(blank=True, null=True, default=0)
    dme_status_detail = models.CharField(
        max_length=100, blank=True, null=True, default=None
    )
    dme_status_action = models.CharField(
        max_length=100, blank=True, null=True, default=None
    )
    dme_status_linked_reference_from_fp = models.TextField(
        max_length=150, blank=True, null=True, default=None
    )
    rpt_pod_from_file_time = models.DateTimeField(blank=True, null=True, default=None)
    rpt_proof_of_del_from_csv_time = models.DateTimeField(
        blank=True, null=True, default=None
    )
    z_status_process_notes = models.TextField(
        max_length=1000, blank=True, null=True, default=None
    )
    tally_delivered = models.IntegerField(blank=True, default=0, null=True)
    manifest_timestamp = models.DateTimeField(blank=True, null=True, default=None)
    inv_billing_status = models.CharField(
        max_length=32, blank=True, null=True, default=None
    )
    inv_billing_status_note = models.TextField(blank=True, null=True, default=None)
    dme_client_notes = models.TextField(blank=True, null=True, default=None)
    check_pod = models.BooleanField(default=False, blank=True, null=True)
    vx_freight_provider_carrier = models.CharField(
        max_length=32, blank=True, null=True, default=None
    )
    fk_manifest = models.ForeignKey(
        Dme_manifest_log, on_delete=models.CASCADE, default=None, null=True
    )
    b_is_flagged_add_on_services = models.BooleanField(
        default=False, blank=True, null=True
    )
    z_calculated_ETA = models.DateField(blank=True, null=True, default=None)
    b_client_name_sub = models.CharField(
        max_length=64, blank=True, null=True, default=None
    )
    fp_invoice_no = models.CharField(max_length=16, blank=True, null=True, default=None)
    inv_cost_quoted = models.FloatField(blank=True, default=0, null=True)
    inv_cost_actual = models.FloatField(blank=True, default=0, null=True)
    inv_sell_quoted = models.FloatField(blank=True, default=0, null=True)
    inv_sell_quoted_override = models.FloatField(blank=True, default=None, null=True)
    inv_sell_actual = models.FloatField(blank=True, default=0, null=True)
    inv_booked_quoted = models.FloatField(blank=True, default=0, null=True)
    client_sales_total = models.FloatField(blank=True, default=None, null=True)
    b_del_to_signed_name = models.CharField(
        max_length=64, blank=True, null=True, default=None
    )
    b_del_to_signed_time = models.DateTimeField(blank=True, null=True, default=None)
    z_pushed_to_fm = models.BooleanField(default=False, blank=True, null=True)
    b_fp_qty_delivered = models.IntegerField(blank=True, default=0, null=True)
    jobNumber = models.CharField(max_length=45, blank=True, null=True, default=None)
    jobDate = models.CharField(max_length=45, blank=True, null=True, default=None)
    vx_account_code = models.CharField(
        max_length=32, blank=True, null=True, default=None
    )
    b_booking_project = models.CharField(
        max_length=250, blank=True, null=True, default=None
    )
    v_project_percentage = models.FloatField(default=0, blank=True, null=True)
    b_project_opened = models.DateTimeField(blank=True, null=True, default=None)
    b_project_inventory_due = models.DateTimeField(blank=True, null=True, default=None)
    b_project_wh_unpack = models.DateTimeField(blank=True, null=True, default=None)
    b_project_dd_receive_date = models.DateTimeField(
        blank=True, null=True, default=None
    )
    b_project_due_date = models.DateField(blank=True, null=True, default=None)
    b_given_to_transport_date_time = models.DateTimeField(
        blank=True, null=True, default=None
    )
    fp_received_date_time = models.DateTimeField(blank=True, null=True)
    api_booking_quote = models.OneToOneField(
        API_booking_quotes,
        on_delete=models.CASCADE,
        null=True,
        related_name="booked_quote",
    )  # quote for Booked $
    quote_id = models.OneToOneField(
        API_booking_quotes,
        on_delete=models.CASCADE,
        null=True,
        related_name="quoted_quote",
    )  # quote for Quoted $
    prev_dme_status_detail = models.CharField(
        max_length=255, blank=True, null=True, default=None
    )
    dme_status_detail_updated_at = models.DateTimeField(
        blank=True, null=True, default=None
    )
    dme_status_detail_updated_by = models.CharField(
        max_length=64, blank=True, null=True, default=None
    )
    delivery_booking = models.DateField(default=None, blank=True, null=True)
    pu_location = models.CharField(
        max_length=64, default=None, null=True, choices=LOCATION_CHOICES
    )
    de_to_location = models.CharField(
        max_length=64, default=None, null=True, choices=LOCATION_CHOICES
    )
    pu_floor_number = models.IntegerField(default=0, null=True)
    de_floor_number = models.IntegerField(default=0, null=True)
    pu_floor_access_by = models.CharField(
        max_length=32, default=None, null=True, choices=FLOOR_ACCESS_BY_CHOICES
    )
    de_to_floor_access_by = models.CharField(
        max_length=32, default=None, null=True, choices=FLOOR_ACCESS_BY_CHOICES
    )
    de_to_sufficient_space = models.BooleanField(default=True, null=True)
    de_to_assembly_required = models.BooleanField(default=False, null=True)
    pu_no_of_assists = models.IntegerField(default=0, null=True)
    de_no_of_assists = models.IntegerField(default=0, null=True)
    pu_access = models.CharField(max_length=32, default=None, null=True)
    de_access = models.CharField(max_length=32, default=None, null=True)
    pu_service = models.CharField(max_length=32, default=None, null=True)
    de_service = models.CharField(max_length=32, default=None, null=True)
    booking_type = models.CharField(
        max_length=4, default=None, null=True, choices=BOOKING_TYPE_CHOICES
    )
    is_quote_locked = models.BooleanField(default=False, null=True)
    selected = models.BooleanField(default=None, null=True)
    packed_status = models.CharField(
        max_length=16, default=None, null=True, choices=PACKED_STATUS_CHOICES
    )
    fp_atl_number = models.IntegerField(default=0, blank=True, null=True)
    opt_authority_to_leave = models.BooleanField(default=False, null=True)
    bid_closing_at = models.DateTimeField(blank=True, null=True, default=None)
    b_pallet_loscam_account = models.CharField(max_length=25, default=None, null=True)

    class Meta:
        db_table = "dme_bookings"

    def get_new_booking_visual_id():
        bookings = Bookings.objects.all().only("id").order_by("id")
        return bookings.last().pk + 1 + 15000

    def had_status(self, status):
        results = Dme_status_history.objects.filter(
            fk_booking_id=self.pk_booking_id, status_last__icontains=status
        )

        return True if results else False

    def get_status_histories(self, status=None):
        status_histories = []

        if status:
            status_histories = Dme_status_history.objects.filter(
                fk_booking_id=self.pk_booking_id, status_last__iexact=status
            )
        else:
            status_histories = Dme_status_history.objects.filter(
                fk_booking_id=self.pk_booking_id
            )

        return status_histories

    # @property
    # def business_group(self):
    #     customer_group_name = ""
    #     customer_groups = Dme_utl_client_customer_group.objects.all()

    #     for customer_group in customer_groups:
    #         if (
    #             customer_group
    #             and self.deToCompanyName
    #             and customer_group.name_lookup.lower() in self.deToCompanyName.lower()
    #         ):
    #             customer_group_name = customer_group.group_name

    #     return customer_group_name

    # @property
    # def dme_delivery_status_category(self):
    #     from api.fp_apis.utils import get_status_category_from_status

    #     return get_status_category_from_status(self.b_status)

    def lines(self):
        return Booking_lines.objects.filter(
            fk_booking_id=self.pk_booking_id, is_deleted=False
        )

    def line_datas(self):
        return Booking_lines_data.objects.filter(fk_booking_id=self.pk_booking_id)

    def get_total_lines_qty(self):
        try:
            qty = 0
            booking_lines = Booking_lines.objects.filter(
                fk_booking_id=self.pk_booking_id
            )

            for booking_line in booking_lines:
                if booking_line.e_qty:
                    qty += int(booking_line.e_qty)

            return qty
        except Exception as e:
            trace_error.print()
            logger.error(f"#552 [get_total_lines_qty] - {str(e)}")
            return 0

    # @property
    # def client_item_references(self):
    #     try:
    #         client_item_references = []
    #         booking_lines = Booking_lines.objects.filter(
    #             fk_booking_id=self.pk_booking_id
    #         )

    #         for booking_line in booking_lines:
    #             if booking_line.client_item_reference is not None:
    #                 client_item_references.append(booking_line.client_item_reference)

    #         return ", ".join(client_item_references)
    #     except Exception as e:
    #         trace_error.print()
    #         logger.error(f"#553 [client_item_references] - {str(e)}")
    #         return ""

    @property
    def clientRefNumbers(self):
        try:
            clientRefNumbers = []
            booking_lines_data = Booking_lines_data.objects.filter(
                fk_booking_id=self.pk_booking_id
            ).only("clientRefNumber")

            for booking_line_data in booking_lines_data:
                clientRefNumber = booking_line_data.clientRefNumber
                if clientRefNumber and not clientRefNumber in clientRefNumbers:
                    clientRefNumbers.append(clientRefNumber)

            return ", ".join(clientRefNumbers)
        except Exception as e:
            trace_error.print()
            logger.error(f"#554 [clientRefNumbers] - {str(e)}")
            return ""

    @property
    def gap_ras(self):
        try:
            gap_ras = []
            booking_lines_data = Booking_lines_data.objects.filter(
                fk_booking_id=self.pk_booking_id
            ).only("gap_ra")

            for booking_line_data in booking_lines_data:
                gap_ra = booking_line_data.gap_ra
                if gap_ra and not gap_ra in gap_ras:
                    gap_ras.append(gap_ra)

            return ", ".join(gap_ras)
        except Exception as e:
            trace_error.print()
            logger.error(f"#555 [gap_ras] - {str(e)}")
            return ""

    def get_etd(self):
        if self.api_booking_quote:
            if self.vx_freight_provider.lower() == "tnt":
                return round(float(self.api_booking_quote.etd)), "days"
            elif self.api_booking_quote:
                freight_provider = Fp_freight_providers.objects.get(
                    fp_company_name=self.vx_freight_provider
                )
                service_etd = FP_Service_ETDs.objects.filter(
                    freight_provider_id=freight_provider.id,
                    fp_delivery_time_description=self.api_booking_quote.etd,
                ).first()

                if service_etd is not None:
                    if service_etd.fp_service_time_uom.lower() == "days":
                        return service_etd.fp_03_delivery_hours / 24, "days"
                    elif service_etd.fp_service_time_uom.lower() == "hours":
                        return service_etd.fp_03_delivery_hours, "hours"

    def get_fp(self):
        try:
            return Fp_freight_providers.objects.get(
                fp_company_name=self.vx_freight_provider
            )
        except:
            return None

    def get_client(self):
        try:
            return DME_clients.objects.get(dme_account_num=self.kf_client_id)
        except:
            return None

    def get_manual_surcharges_total(self):
        _total = 0
        manual_surcharges = Surcharge.objects.filter(booking=self)

        for surcharge in manual_surcharges:
            _total += surcharge.qty * surcharge.amount

        return _total

    def get_s_06(self):
        from api.common.time import next_business_day

        LOG_ID = "[GET_s_06]"
        _s_06 = None

        if (
            not self.s_06_Latest_Delivery_Date_TimeSet
            and not self.s_06_Latest_Delivery_Date_Time_Override
        ):
            return None
            logger.error(f"{LOG_ID} No ETA: {self.b_bookingID_Visual}")

        if self.s_06_Latest_Delivery_Date_Time_Override:
            _s_06 = self.s_06_Latest_Delivery_Date_Time_Override
        elif self.s_06_Latest_Delivery_Date_TimeSet:
            _s_06 = self.s_06_Latest_Delivery_Date_TimeSet

        return next_business_day(_s_06, 1)

    def save(self, *args, **kwargs):
        LOG_ID = "[BOOKING SAVE]"
        self.z_ModifiedTimestamp = datetime.now()
        creating = self._state.adding

        if not creating:
            cls = self.__class__
            old = cls.objects.get(pk=self.pk)
            new = self

            # When address is changed, re-quote
            if (
                new.pu_Address_State != old.pu_Address_State
                or new.pu_Address_PostalCode != old.pu_Address_PostalCode
                or new.pu_Address_Suburb != old.pu_Address_Suburb
                or new.de_To_Address_State != old.de_To_Address_State
                or new.de_To_Address_PostalCode != old.de_To_Address_PostalCode
                or new.de_To_Address_Suburb != old.de_To_Address_Suburb
            ):
                self.b_error_Capture = None

                if self.b_client_name not in ["BioPak"]:
                    logger.info(
                        f"{LOG_ID} - Address is updated! re-quote will be started in 5s"
                    )
                    quote_in_bg(new)

            if (
                old.vx_freight_provider != new.vx_freight_provider
                and new.vx_freight_provider == "Deliver-ME"
                and not new.b_booking_project
            ):
                self.b_booking_project = "not assigned yet"
            elif (
                old.vx_freight_provider != new.vx_freight_provider
                and old.vx_freight_provider == "Deliver-ME"
                and new.b_booking_project == "not assigned yet"
            ):
                self.b_booking_project = None

            # On quote change
            if old.api_booking_quote != new.api_booking_quote:
                from api.common.booking_quote import after_select_quote_bg

                # Background function
                after_select_quote_bg(new, new.api_booking_quote)
            else:
                if old.vx_freight_provider != new.vx_freight_provider:
                    from api.common.booking_quote import set_booking_quote
                    from api.common.booking_quote import after_select_quote_bg

                    if old.api_booking_quote:
                        set_booking_quote(new, None)
                    else:
                        # Background function
                        after_select_quote_bg(new, None)

            changed_fields = []
            for field in cls._meta.get_fields():
                field_name = field.name
                try:
                    if getattr(old, field_name) != getattr(new, field_name):
                        changed_fields.append(field_name)
                except Exception as ex:  # Catch field does not exist exception
                    pass
            kwargs["update_fields"] = changed_fields
        return super(Bookings, self).save(*args, **kwargs)


@receiver(pre_save, sender=Bookings)
def pre_save_booking(sender, instance, update_fields, **kwargs):
    from api.signal_handlers.booking import pre_save_handler

    pre_save_handler(instance, update_fields)


# @receiver(post_save, sender=Bookings)
# def post_save_booking(sender, instance, created, update_fields, **kwargs):
#     from api.signal_handlers.booking import post_save_handler

#     post_save_handler(instance, created, update_fields)


class Booking_lines(models.Model):
    ORIGINAL = "original"
    AUTO_PACK = "auto"
    MANUAL_PACK = "manual"
    SCANNED_PACK = "scanned"
    PACKED_STATUS_CHOICES = (
        (ORIGINAL, "original"),
        (AUTO_PACK, "auto"),
        (MANUAL_PACK, "manual"),
        (SCANNED_PACK, "scanned"),
    )

    pk_lines_id = models.AutoField(primary_key=True)
    fk_booking_id = models.CharField(
        verbose_name=_("FK Booking Id"), max_length=64, blank=True, null=True
    )
    pk_booking_lines_id = models.CharField(max_length=64, blank=True, null=True)
    e_type_of_packaging = models.CharField(
        verbose_name=_("Type Of Packaging"), max_length=36, blank=True, null=True
    )
    e_item_type = models.CharField(
        verbose_name=_("Item Type"), max_length=64, blank=True, null=True
    )
    e_pallet_type = models.CharField(
        verbose_name=_("Pallet Type"), max_length=24, blank=True, null=True
    )
    e_item = models.CharField(
        verbose_name=_("Item"), max_length=256, blank=True, null=True
    )
    e_qty = models.IntegerField(verbose_name=_("Quantity"), blank=True, null=True)
    e_weightUOM = models.CharField(
        verbose_name=_("Weight UOM"), max_length=56, blank=True, null=True
    )
    e_weightPerEach = models.FloatField(
        verbose_name=_("Weight Per Each"), blank=True, null=True
    )
    e_dimUOM = models.CharField(
        verbose_name=_("Dim UOM"), max_length=10, blank=True, null=True
    )
    e_dimLength = models.FloatField(verbose_name=_("Dim Length"), blank=True, null=True)
    e_dimWidth = models.FloatField(verbose_name=_("Dim Width"), blank=True, null=True)
    e_dimHeight = models.FloatField(verbose_name=_("Dim Height"), blank=True, null=True)
    e_dangerousGoods = models.IntegerField(
        verbose_name=_("Dangerous Goods"), blank=True, null=True
    )
    e_insuranceValueEach = models.IntegerField(
        verbose_name=_("Insurance Value Each"), blank=True, null=True
    )
    discount_rate = models.IntegerField(
        verbose_name=_("Discount Rate"), blank=True, null=True
    )
    e_options1 = models.CharField(
        verbose_name=_("Option 1"), max_length=56, blank=True, null=True
    )
    e_options2 = models.CharField(
        verbose_name=_("Option 2"), max_length=56, blank=True, null=True
    )
    e_options3 = models.CharField(
        verbose_name=_("Option 3"), max_length=56, blank=True, null=True
    )
    e_options4 = models.CharField(
        verbose_name=_("Option 4"), max_length=56, blank=True, null=True
    )
    fk_service_id = models.CharField(
        verbose_name=_("Service ID"), max_length=64, blank=True, null=True
    )
    z_createdByAccount = models.CharField(
        verbose_name=_("Created By Account"), max_length=24, blank=True, null=True
    )
    z_documentUploadedUser = models.CharField(
        verbose_name=_("Document Uploaded User"), max_length=24, blank=True, null=True
    )
    z_modifiedByAccount = models.CharField(
        verbose_name=_("Modified By Account"), max_length=24, blank=True, null=True
    )
    e_spec_clientRMA_Number = models.TextField(
        verbose_name=_("Spec ClientRMA Number"), max_length=300, blank=True, null=True
    )
    e_spec_customerReferenceNo = models.TextField(
        verbose_name=_("Spec Customer Reference No"),
        max_length=200,
        blank=True,
        null=True,
    )
    taxable = models.BooleanField(
        verbose_name=_("Taxable"), default=False, blank=True, null=True
    )
    e_Total_KG_weight = models.FloatField(
        verbose_name=_("Total KG Weight"), blank=True, default=0, null=True
    )
    e_1_Total_dimCubicMeter = models.FloatField(
        verbose_name=_("Total Dim Cubic Meter"), blank=True, default=0, null=True
    )
    client_item_reference = models.CharField(
        max_length=64, blank=True, null=True, default=None
    )
    total_2_cubic_mass_factor_calc = models.FloatField(
        verbose_name=_("Cubic Mass Factor"), blank=True, default=0, null=True
    )
    e_qty_awaiting_inventory = models.IntegerField(blank=True, null=True, default=0)
    e_qty_collected = models.IntegerField(blank=True, null=True, default=0)
    e_qty_scanned_depot = models.IntegerField(blank=True, null=True, default=0)
    e_qty_delivered = models.IntegerField(blank=True, null=True, default=0)
    e_qty_adjusted_delivered = models.IntegerField(blank=True, null=True, default=0)
    e_qty_damaged = models.IntegerField(blank=True, null=True, default=0)
    e_qty_returned = models.IntegerField(blank=True, null=True, default=0)
    e_qty_shortages = models.IntegerField(blank=True, null=True, default=0)
    e_qty_scanned_fp = models.IntegerField(blank=True, null=True, default=0)
    z_pushed_to_fm = models.BooleanField(default=False, blank=True, null=True)
    is_deleted = models.BooleanField(default=False)
    # Code from warehouse when item is picked up
    sscc = models.TextField(blank=True, null=True, default=None)
    picked_up_timestamp = models.DateTimeField(
        verbose_name=_("Picked up timestamp at Warehouse"),
        null=True,
        blank=True,
        default=None,
    )
    packed_status = models.CharField(
        max_length=16, default=None, null=True, choices=PACKED_STATUS_CHOICES
    )
    zbl_121_integer_1 = models.IntegerField(
        blank=True, null=True, default=None
    )  # JasonL - OLD Sequence
    zbl_131_decimal_1 = models.FloatField(
        blank=True, null=True, default=None
    )  # JasonL - NEW Sequence
    zbl_102_text_2 = models.CharField(
        max_length=64, blank=True, null=True, default=None
    )  # JasonL - ProductCode
    e_util_height = models.FloatField(
        verbose_name=_("Utilised Height"), blank=True, null=True
    )
    e_util_cbm = models.FloatField(
        verbose_name=_("Utilised Cubic Meter"), blank=True, null=True
    )
    e_util_kg = models.FloatField(
        verbose_name=_("Utilised Cubic KG"), blank=True, null=True
    )
    e_bin_number = models.CharField(
        max_length=64, blank=True, null=True, default=None
    )  # Bin Number | Aisle Number
    z_createdByAccount = models.CharField(
        verbose_name=_("Created by account"), max_length=64, blank=True, null=True
    )
    z_createdTimeStamp = models.DateTimeField(
        verbose_name=_("Created Timestamp"),
        null=True,
        blank=True,
        auto_now_add=True,
    )
    z_modifiedByAccount = models.CharField(
        verbose_name=_("Modified by account"), max_length=64, blank=True, null=True
    )
    z_modifiedTimeStamp = models.DateTimeField(
        verbose_name=_("Modified Timestamp"),
        null=True,
        blank=True,
        auto_now=True,
    )
    warranty_value = models.FloatField(blank=True, null=True, default=0)
    warranty_percent = models.FloatField(blank=True, null=True, default=0)
    note = models.CharField(max_length=200, blank=True, null=True, default=None)
    b_pallet_loscam_account = models.CharField(max_length=25, default=None, null=True)

    def booking(self):
        try:
            return (
                Bookings.objects.filter(pk_booking_id=self.fk_booking_id)
                .order_by("id")
                .first()
            )
        except Exception as e:
            trace_error.print()
            logger.error(f"#516 Error: {str(e)}")
            return None

    def get_is_scanned(self):
        try:
            api_bcl = Api_booking_confirmation_lines.objects.filter(
                fk_booking_line_id=self.pk_lines_id
            ).first()

            if api_bcl and api_bcl.tally:
                return True
            return False
        except Exception as e:
            trace_error.print()
            logger.error(f"#561 get_is_scanned - {str(e)}")
            return False

    @property
    def gap_ras(self):
        try:
            _gap_ras = []
            booking_lines_data = Booking_lines_data.objects.filter(
                fk_booking_lines_id=self.pk_booking_lines_id
            )

            for booking_line_data in booking_lines_data:
                gap_ra = booking_line_data.gap_ra
                if gap_ra and not gap_ra in _gap_ras:
                    _gap_ras.append(gap_ra)

            return ", ".join(_gap_ras)
        except Exception as e:
            trace_error.print()
            logger.error(f"#562 gap_ras - {str(e)}")
            return ""

    def modelNumbers(self):
        try:
            _modelNumbers = []
            booking_lines_data = Booking_lines_data.objects.filter(
                fk_booking_lines_id=self.pk_booking_lines_id
            )

            for booking_line_data in booking_lines_data:
                if booking_line_data.modelNumber:
                    _modelNumbers.append(booking_line_data.modelNumber)

            return ", ".join(_modelNumbers)
        except Exception as e:
            trace_error.print()
            logger.error(f"#563 modelNumbers - {str(e)}")
            return ""

    @transaction.atomic
    def save(self, *args, **kwargs):
        # Check if all other lines are picked at Warehouse
        creating = self._state.adding
        self.z_modifiedTimeStamp = datetime.now()
        self.e_1_Total_dimCubicMeter = round(
            get_cubic_meter(
                self.e_dimLength,
                self.e_dimWidth,
                self.e_dimHeight,
                self.e_dimUOM,
                self.e_qty,
            ),
            5,
        )

        bookings = Bookings.objects.filter(pk_booking_id=self.fk_booking_id).only(
            "vx_freight_provider"
        )
        if bookings:
            from api.fp_apis.utils import get_m3_to_kg_factor
            from api.helpers.cubic import get_rounded_cubic_meter
            from api.common.constants import PALLETS, SKIDS
            from api.common.ratio import _get_dim_amount, _get_weight_amount

            if bookings[0].vx_freight_provider and bookings[0].vx_freight_provider.lower() == "team global express":
                self.e_1_Total_dimCubicMeter = round(
                    get_rounded_cubic_meter(
                        self.e_dimLength,
                        self.e_dimWidth,
                        self.e_dimHeight,
                        self.e_dimUOM,
                        self.e_qty,
                    ),
                    5,
                )

            m3ToKgFactor = getM3ToKgFactor(
                bookings[0].vx_freight_provider,
                self.e_dimLength,
                self.e_dimWidth,
                self.e_dimHeight,
                self.e_weightPerEach,
                self.e_dimUOM,
                self.e_weightUOM,
            )

            self.total_2_cubic_mass_factor_calc = (
                self.e_1_Total_dimCubicMeter * m3ToKgFactor
            )
            self.total_2_cubic_mass_factor_calc = round(
                self.total_2_cubic_mass_factor_calc, 2
            )

            # Check if `Pallet` or `Skid`
            is_pallet = (
                self.e_type_of_packaging.upper() in PALLETS
                or self.e_type_of_packaging.upper() in SKIDS
            )

            need_update = True
            if not is_pallet:
                need_update = False
            # Check if height is less than 1.4m
            dim_ratio = _get_dim_amount(self.e_dimUOM)
            height = self.e_dimHeight * dim_ratio
            if height > 1.4:
                need_update = False

            self.e_util_height = 1.4 if need_update else height
            self.e_util_height = self.e_util_height / dim_ratio

            # Calc cubic mass factor
            weight_ratio = _get_weight_amount(self.e_weightUOM)
            item_dead_weight = self.e_weightPerEach * weight_ratio
            e_cubic_2_mass_factor = get_m3_to_kg_factor(
                bookings[0].vx_freight_provider,
                {
                    "is_pallet": is_pallet,
                    "item_length": self.e_dimLength * dim_ratio,
                    "item_width": self.e_dimWidth * dim_ratio,
                    "item_height": self.e_util_height * dim_ratio,
                    "item_dead_weight": item_dead_weight,
                },
            )
            # Calc
            self.e_util_cbm = get_cubic_meter(
                self.e_dimLength,
                self.e_dimWidth,
                self.e_util_height,
                self.e_dimUOM,
                1,
            )
            self.e_util_cbm = round(self.e_util_cbm * self.e_qty, 3)
            self.e_util_kg = self.e_util_cbm * e_cubic_2_mass_factor
            self.e_util_kg = round(self.e_util_kg * self.e_qty, 3)

        if self.pk:
            cls = self.__class__
            old = cls.objects.get(pk=self.pk)
            new = self
            changed_fields = []
            for field in cls._meta.get_fields():
                field_name = field.name
                try:
                    if getattr(old, field_name) != getattr(new, field_name):
                        changed_fields.append(field_name)
                except Exception as ex:  # Catch field does not exist exception
                    pass
            kwargs["update_fields"] = changed_fields

        if not creating and self.picked_up_timestamp:
            try:
                if "plum" in booking.b_client_name.lower():
                    booking_lines = Booking_lines.objects.filter(
                        fk_booking_id=booking.pk_booking_id
                    ).exclude(pk=self.pk)
                    booking_lines_cnt = booking_lines.count()
                    picked_up_lines_cnt = booking_lines.filter(
                        picked_up_timestamp__isnull=False
                    ).count()

                    if booking_lines_cnt - 1 == picked_up_lines_cnt:
                        status_history.create(booking, "Ready for Booking", "DME_BE")
            except:
                pass

        return super(Booking_lines, self).save(*args, **kwargs)

    class Meta:
        db_table = "dme_booking_lines"


# @receiver(pre_save, sender=Booking_lines)
# def pre_save_booking_line(sender, instance, **kwargs):
#     from api.signal_handlers.booking_line import pre_save_handler

#     pre_save_handler(instance)


# @receiver(post_save, sender=Booking_lines)
# def post_save_booking_line(sender, instance, created, update_fields, **kwargs):
#     from api.signal_handlers.booking_line import post_save_handler

#     post_save_handler(instance, created, update_fields)


# @receiver(post_delete, sender=Booking_lines)
# def post_delete_booking_line(sender, instance, **kwargs):
#     from api.signal_handlers.booking_line import post_delete_handler

#     post_delete_handler(instance)


class Booking_lines_data(models.Model):
    ORIGINAL = "original"
    AUTO_PACK = "auto"
    MANUAL_PACK = "manual"
    SCANNED_PACK = "scanned"
    PACKED_STATUS_CHOICES = (
        (ORIGINAL, "original"),
        (AUTO_PACK, "auto"),
        (MANUAL_PACK, "manual"),
        (SCANNED_PACK, "scanned"),
    )

    pk_id_lines_data = models.AutoField(primary_key=True)
    fk_booking_lines_id = models.CharField(
        verbose_name=_("FK Booking Lines Id"),
        max_length=64,
        blank=True,
        null=True,
        default=None,
    )
    fk_booking_id = models.CharField(
        verbose_name=_("FK Booking Id"), max_length=64, blank=True, null=True
    )
    modelNumber = models.CharField(
        verbose_name=_("Model Number"), max_length=50, blank=True, null=True
    )
    itemDescription = models.TextField(
        verbose_name=_("Item Description"), max_length=200, blank=True, null=True
    )
    quantity = models.IntegerField(verbose_name=_("Quantity"), blank=True, null=True)
    itemFaultDescription = models.TextField(
        verbose_name=_("Item Description"), max_length=200, blank=True, null=True
    )
    insuranceValueEach = models.FloatField(
        verbose_name=_("Insurance Value Each"), blank=True, null=True
    )
    gap_ra = models.TextField(
        verbose_name=_("Gap Ra"), max_length=300, blank=True, null=True
    )
    clientRefNumber = models.CharField(
        verbose_name=_("Client Ref Number"), max_length=50, blank=True, null=True
    )
    itemSerialNumbers = models.CharField(
        verbose_name=_("Item Serial Numbers"), max_length=100, blank=True, null=True
    )
    z_pushed_to_fm = models.BooleanField(default=False, blank=True, null=True)
    packed_status = models.CharField(
        max_length=16, default=None, null=True, choices=PACKED_STATUS_CHOICES
    )
    z_createdByAccount = models.CharField(
        verbose_name=_("Created by account"), max_length=64, blank=True, null=True
    )
    z_createdTimeStamp = models.DateTimeField(
        verbose_name=_("Created Timestamp"),
        null=True,
        blank=True,
        auto_now_add=True,
    )
    z_modifiedByAccount = models.CharField(
        verbose_name=_("Modified by account"), max_length=64, blank=True, null=True
    )
    z_modifiedTimeStamp = models.DateTimeField(
        verbose_name=_("Modified Timestamp"),
        null=True,
        blank=True,
        auto_now=True,
    )

    def booking(self):
        try:
            return (
                Bookings.objects.filter(pk_booking_id=self.fk_booking_id)
                .order_by("id")
                .first()
            )
        except Exception as e:
            trace_error.print()
            logger.info(f"#516 Error: {str(e)}")
            return None

    def booking_line(self):
        try:
            return (
                Booking_lines.objects.filter(
                    pk_booking_lines_id=self.fk_booking_lines_id
                )
                .order_by("id")
                .first()
            )
        except Exception as e:
            trace_error.print()
            logger.info(f"#516 Error: {str(e)}")
            return None

    def save(self, *args, **kwargs):
        self.z_modifiedTimeStamp = datetime.now()
        return super(Booking_lines_data, self).save(*args, **kwargs)

    class Meta:
        db_table = "dme_booking_lines_data"


# @receiver(post_delete, sender=Booking_lines_data)
# def post_delete_booking_lines_data(sender, instance, **kwargs):
#     from api.signal_handlers.booking_line_data import post_delete_handler

#     post_delete_handler(instance)


class Dme_attachments(models.Model):
    pk_id_attachment = models.AutoField(primary_key=True)
    fk_id_dme_client = models.ForeignKey(DME_clients, on_delete=models.CASCADE)
    fk_id_dme_booking = models.CharField(
        verbose_name=_("FK Booking Id"), max_length=64, blank=True, null=True
    )
    fileName = models.CharField(verbose_name=_("filename"), max_length=230, blank=False)
    linkurl = models.CharField(
        verbose_name=_("linkurl"), max_length=430, blank=True, null=True
    )
    upload_Date = models.DateField(
        verbose_name=_("Upload Datatime"), default=date.today, blank=True, null=True
    )
    is_hidden = models.BooleanField(
        verbose_name=_("is_hidden"),
        default="False",
        blank=True,
        null=True,
    )
    desc = models.CharField(
        verbose_name=_("desc"), max_length=500, blank=True, null=True
    )

    class Meta:
        db_table = "dme_attachments"


class BOK_0_BookingKeys(models.Model):
    pk_auto_id = models.AutoField(primary_key=True)
    client_booking_id = models.CharField(
        verbose_name=_("Client booking id"), max_length=64, blank=True
    )
    filename = models.CharField(
        verbose_name=_("File name"), max_length=128, blank=False
    )
    success = models.CharField(verbose_name=_("Success"), max_length=1)
    timestampCreated = models.DateTimeField(
        verbose_name=_("PickUp Available From"), default=timezone.now, blank=True
    )
    client = models.CharField(
        verbose_name=_("Client"), max_length=64, blank=True, null=True, default=None
    )
    v_client_pk_consigment_num = models.CharField(
        verbose_name=_("Consigment num"), max_length=64, blank=True
    )
    l_000_client_acct_number = models.CharField(
        verbose_name=_("Client account number"), max_length=64, blank=True, null=True
    )
    l_011_client_warehouse_id = models.IntegerField(
        verbose_name=_("Client warehouse Id"), blank=True
    )
    l_012_client_warehouse_name = models.CharField(
        verbose_name=_("Client warehouse Name"), max_length=240, blank=True
    )

    class Meta:
        db_table = "bok_0_bookingkeys"


class BOK_1_headers(models.Model):
    PDWD = "Pickup at Door / Warehouse Dock"
    DDWD = "Drop at Door / Warehouse Dock"
    DDW = "Drop in Door / Warehouse"
    ROC = "Room of Choice"
    LOCATION_CHOICES = (
        (PDWD, "Pickup at Door / Warehouse Dock"),
        (DDWD, "Drop at Door / Warehouse Dock"),
        (DDW, "Drop in Door / Warehouse"),
        (ROC, "Room of Choice"),
    )

    NONE = "NONE"
    ELEVATOR = "Elevator"
    ESCALATOR = "Escalator"
    STAIRS = "Stairs"
    FLOOR_ACCESS_BY_CHOICES = (
        (NONE, "NONE"),
        (ELEVATOR, "Elevator"),
        (ESCALATOR, "Escalator"),
        (STAIRS, "Stairs"),
    )

    DMEM = "DMEM"
    DMEA = "DMEA"
    DMEP = "DMEP"  # Pickup
    BOOKING_TYPE_CHOICES = ((DMEM, "DMEM"), (DMEA, "DMEA"), (DMEP, "DMEP"))

    pk_auto_id = models.AutoField(primary_key=True)
    quote = models.OneToOneField(
        API_booking_quotes, on_delete=models.CASCADE, null=True
    )  # Optional
    client_booking_id = models.CharField(
        verbose_name=_("Client booking id"), max_length=64, blank=True
    )
    b_021_b_pu_avail_from_date = models.DateField(
        verbose_name=_("Available From"), default=None, blank=True, null=True
    )
    b_003_b_service_name = models.CharField(
        verbose_name=_("Service Name"), max_length=64, blank=True, null=True
    )
    b_500_b_client_cust_job_code = models.CharField(
        verbose_name=_("Client Job Code"), max_length=20, blank=True, null=True
    )
    b_054_b_del_company = models.CharField(
        verbose_name=_("Del company"), max_length=100, blank=True, null=True
    )
    b_000_b_total_lines = models.IntegerField(
        verbose_name=_("b_000_b_total_lines"), blank=True, null=True
    )
    b_058_b_del_address_suburb = models.CharField(
        verbose_name=_("Address suburb"), max_length=40, blank=True, null=True
    )
    b_057_b_del_address_state = models.CharField(
        verbose_name=_("Address state"), max_length=20, blank=True, null=True
    )
    b_059_b_del_address_postalcode = models.CharField(
        verbose_name=_("Address Postal Code"),
        max_length=16,
        blank=True,
        null=True,
        default=None,
    )
    v_client_pk_consigment_num = models.CharField(
        verbose_name=_("Consigment num"), max_length=64, blank=True, null=True
    )
    total_kg = models.FloatField(verbose_name=_("Total Kg"), blank=True, null=True)
    success = models.CharField(
        verbose_name=_("Success"), max_length=1, default=0, null=True
    )
    fk_client_warehouse = models.ForeignKey(
        Client_warehouses, on_delete=models.CASCADE, default="1"
    )
    b_clientPU_Warehouse = models.CharField(
        verbose_name=_("warehouse"), max_length=64, blank=True, null=True
    )
    fk_client_id = models.CharField(
        verbose_name=_("fk_client_id"), max_length=64, blank=True, null=True
    )
    date_processed = models.DateTimeField(
        verbose_name=_("date_processed"), default=timezone.now, blank=True, null=True
    )
    pk_header_id = models.CharField(
        verbose_name=_("pk_header_id"), max_length=64, blank=True, null=True
    )
    b_000_1_b_clientReference_RA_Numbers = models.CharField(
        verbose_name=_("b_000_1_b_clientReference_RA_Numbers"),
        max_length=500,
        blank=True,
        null=True,
    )
    b_000_2_b_price = models.FloatField(
        verbose_name=_("b_000_2_b_price"),
        max_length=4,
        blank=True,
        default=0,
        null=True,
    )
    b_001_b_freight_provider = models.CharField(
        verbose_name=_("b_001_b_freight_provider"), max_length=36, blank=True, null=True
    )
    b_002_b_vehicle_type = models.CharField(
        verbose_name=_("b_002_b_vehicle_type"), max_length=36, blank=True, null=True
    )
    b_005_b_created_for = models.CharField(
        verbose_name=_("b_005_b_created_for"), max_length=50, blank=True, null=True
    )
    b_006_b_created_for_email = models.CharField(
        verbose_name=_("b_006_b_created_for_email"),
        max_length=64,
        blank=True,
        null=True,
    )
    b_007_b_ready_status = models.CharField(
        verbose_name=_("b_007_b_ready_status"), max_length=24, blank=True, null=True
    )
    b_008_b_category = models.CharField(
        verbose_name=_("b_008_b_category"), max_length=64, blank=True, null=True
    )
    b_009_b_priority = models.CharField(
        verbose_name=_("b_009_b_priority"), max_length=20, blank=True, null=True
    )
    b_010_b_notes = models.CharField(
        verbose_name=_("b_010_b_notes"), max_length=500, blank=True, null=True
    )
    b_012_b_driver_bring_connote = models.BooleanField(
        verbose_name=_("b_012_b_driver_bring_connote"),
        default="False",
        blank=True,
        null=True,
    )
    b_013_b_package_job = models.BooleanField(
        verbose_name=_("b_013_b_package_job"), default=False, blank=True, null=True
    )
    b_014_b_pu_handling_instructions = models.TextField(
        verbose_name=_("b_014_b_pu_handling_instructions"),
        max_length=512,
        blank=True,
        null=True,
    )
    b_015_b_pu_instructions_contact = models.TextField(
        verbose_name=_("b_015_b_pu_instructions_contact"),
        max_length=512,
        blank=True,
        null=True,
    )
    b_016_b_pu_instructions_address = models.TextField(
        verbose_name=_("b_016_b_pu_instructions_address"),
        max_length=512,
        blank=True,
        null=True,
    )
    b_017_b_pu_warehouse_num = models.CharField(
        verbose_name=_("b_017_b_pu_warehouse_num"), max_length=10, blank=True, null=True
    )
    b_018_b_pu_warehouse_bay = models.CharField(
        verbose_name=_("b_018_b_pu_warehouse_bay"), max_length=10, blank=True, null=True
    )
    b_019_b_pu_tail_lift = models.BooleanField(
        verbose_name=_("b_019_b_pu_tail_lift"), default=False, blank=True, null=True
    )
    b_020_b_pu_num_operators = models.PositiveIntegerField(
        verbose_name=_("b_020_b_pu_num_operators"), blank=True, default=False, null=True
    )
    b_022_b_pu_avail_from_time_hour = models.IntegerField(
        verbose_name=_("b_022_b_pu_avail_from_time_hour"),
        blank=True,
        default=0,
        null=True,
    )
    b_023_b_pu_avail_from_time_minute = models.IntegerField(
        verbose_name=_("b_023_b_pu_avail_from_time_minute"),
        blank=True,
        default=0,
        null=True,
    )
    b_024_b_pu_by_date = models.DateField(default=None, blank=True, null=True)
    b_025_b_pu_by_time_hour = models.IntegerField(
        verbose_name=_("b_025_b_pu_by_time_hour"), blank=True, default=0, null=True
    )
    b_026_b_pu_by_time_minute = models.IntegerField(
        verbose_name=_("b_026_b_pu_by_time_minute"), blank=True, default=0, null=True
    )
    b_027_b_pu_address_type = models.CharField(
        verbose_name=_("b_027_b_pu_address_type"), max_length=20, blank=True, null=True
    )
    b_028_b_pu_company = models.CharField(
        verbose_name=_("b_028_b_pu_company"), max_length=40, blank=True, null=True
    )
    b_029_b_pu_address_street_1 = models.CharField(
        verbose_name=_("b_029_b_pu_address_street_1"),
        max_length=50,
        blank=True,
        null=True,
    )
    b_030_b_pu_address_street_2 = models.CharField(
        verbose_name=_("b_030_b_pu_address_street_2"),
        max_length=50,
        blank=True,
        null=True,
    )
    b_031_b_pu_address_state = models.CharField(
        verbose_name=_("b_031_b_pu_address_state"), max_length=20, blank=True, null=True
    )
    b_032_b_pu_address_suburb = models.CharField(
        verbose_name=_("b_032_b_pu_address_suburb"),
        max_length=20,
        blank=True,
        null=True,
    )
    b_033_b_pu_address_postalcode = models.CharField(
        verbose_name=_("b_033_b_pu_address_postalcode"),
        max_length=15,
        blank=True,
        null=True,
    )
    b_034_b_pu_address_country = models.CharField(
        verbose_name=_("b_034_b_pu_address_country"),
        max_length=15,
        blank=True,
        null=True,
    )
    b_035_b_pu_contact_full_name = models.CharField(
        verbose_name=_("b_035_b_pu_contact_full_name"),
        max_length=50,
        blank=True,
        null=True,
    )
    b_036_b_pu_email_group = models.TextField(max_length=512, blank=True, null=True)
    b_037_b_pu_email = models.CharField(
        verbose_name=_("b_037_b_pu_email"), max_length=50, blank=True, null=True
    )
    b_038_b_pu_phone_main = models.CharField(
        verbose_name=_("b_038_b_pu_phone_main"), max_length=25, blank=True, null=True
    )
    b_039_b_pu_phone_mobile = models.CharField(
        verbose_name=_("b_039_b_pu_phone_mobile"), max_length=25, blank=True, null=True
    )
    b_040_b_pu_communicate_via = models.CharField(
        verbose_name=_("b_040_b_pu_communicate_via"),
        max_length=30,
        blank=True,
        null=True,
    )
    b_041_b_del_tail_lift = models.BooleanField(
        verbose_name=_("b_041_b_del_tail_lift"), default=False, blank=True, null=True
    )
    b_042_b_del_num_operators = models.PositiveIntegerField(
        verbose_name=_("b_042_b_del_num_operators"),
        blank=True,
        default=False,
        null=True,
    )
    b_043_b_del_instructions_contact = models.TextField(
        verbose_name=_("b_043_b_del_instructions_contact"),
        max_length=512,
        blank=True,
        null=True,
    )
    b_044_b_del_instructions_address = models.TextField(
        verbose_name=_("b_044_b_del_instructions_address"),
        max_length=512,
        blank=True,
        null=True,
    )
    b_045_b_del_warehouse_bay = models.CharField(
        verbose_name=_("b_045_b_del_warehouse_bay"),
        max_length=100,
        blank=True,
        null=True,
    )
    b_046_b_del_warehouse_number = models.CharField(
        verbose_name=_("b_046_b_del_warehouse_number"),
        max_length=1,
        blank=True,
        null=True,
    )
    b_047_b_del_avail_from_date = models.DateField(default=None, blank=True, null=True)
    b_048_b_del_avail_from_time_hour = models.IntegerField(
        verbose_name=_("b_048_b_del_avail_from_time_hour"),
        blank=True,
        default=0,
        null=True,
    )
    b_049_b_del_avail_from_time_minute = models.IntegerField(
        verbose_name=_("b_049_b_del_avail_from_time_minute"),
        blank=True,
        default=0,
        null=True,
    )
    b_050_b_del_by_date = models.DateField(default=None, blank=True, null=True)
    b_051_b_del_by_time_hour = models.IntegerField(
        verbose_name=_("b_051_b_del_by_time_hour"), blank=True, default=0, null=True
    )
    b_052_b_del_by_time_minute = models.IntegerField(
        verbose_name=_("b_052_b_del_by_time_minute"), blank=True, default=0, null=True
    )
    b_055_b_del_address_street_1 = models.CharField(
        verbose_name=_("b_055_b_del_address_street_1"),
        max_length=50,
        blank=True,
        null=True,
    )
    b_056_b_del_address_street_2 = models.CharField(
        verbose_name=_("b_056_b_del_address_street_2"),
        max_length=50,
        blank=True,
        null=True,
    )
    b_060_b_del_address_country = models.CharField(
        verbose_name=_("b_060_b_del_address_country"),
        max_length=15,
        blank=True,
        null=True,
    )
    b_061_b_del_contact_full_name = models.CharField(
        verbose_name=_("b_061_b_del_contact_full_name"),
        max_length=50,
        blank=True,
        null=True,
    )
    b_062_b_del_email_group = models.TextField(max_length=512, blank=True, null=True)
    b_063_b_del_email = models.CharField(
        verbose_name=_("b_063_b_del_email"), max_length=50, blank=True, null=True
    )
    b_064_b_del_phone_main = models.CharField(
        verbose_name=_("b_064_b_del_phone_main"), max_length=25, blank=True, null=True
    )
    b_065_b_del_phone_mobile = models.CharField(
        verbose_name=_("b_065_b_del_phone_mobile"), max_length=25, blank=True, null=True
    )
    b_066_b_del_communicate_via = models.CharField(
        verbose_name=_("b_066_b_del_communicate_via"),
        max_length=30,
        blank=True,
        null=True,
    )
    b_500_b_client_UOM = models.CharField(
        verbose_name=_("b_500_b_client_UOM"), max_length=20, blank=True, null=True
    )
    b_501_b_client_code = models.CharField(
        verbose_name=_("b_501_b_client_code"), max_length=50, blank=True, null=True
    )
    pu_addressed_saved = models.CharField(
        verbose_name=_("pu_addressed_saved"), max_length=3, blank=True, null=True
    )
    de_to_addressed_saved = models.CharField(
        verbose_name=_("de_to_addressed_saved"), max_length=3, blank=True, null=True
    )
    b_client_max_book_amount = models.IntegerField(
        verbose_name=_("b_client_max_book_amount"), blank=True, default=0, null=True
    )
    vx_serviceType_XXX = models.CharField(
        verbose_name=_("vx_serviceType_XXX"), max_length=50, blank=True, null=True
    )
    b_053_b_del_address_type = models.CharField(
        verbose_name=_("b_053_b_del_address_type"), max_length=50, blank=True, null=True
    )
    b_client_sales_inv_num = models.CharField(
        verbose_name=_("Sales Inv Num"),
        max_length=64,
        blank=True,
        null=True,
        default=None,
    )
    b_client_order_num = models.CharField(
        verbose_name=_("Order Num"), max_length=64, blank=True, null=True, default=None
    )
    b_client_del_note_num = models.CharField(
        verbose_name=_("Del Note Num"),
        max_length=64,
        blank=True,
        null=True,
        default=None,
    )
    z_createdByAccount = models.CharField(
        verbose_name=_("Created by account"), max_length=64, blank=True, null=True
    )
    z_createdTimeStamp = models.DateTimeField(
        verbose_name=_("Created Timestamp"),
        null=True,
        blank=True,
        auto_now_add=True,
    )
    z_modifiedByAccount = models.CharField(
        verbose_name=_("Modified by account"), max_length=64, blank=True, null=True
    )
    z_modifiedTimeStamp = models.DateTimeField(
        verbose_name=_("Modified Timestamp"),
        null=True,
        blank=True,
        auto_now=True,
    )
    b_client_warehouse_code = models.CharField(
        verbose_name=_("Warehouse code"),
        max_length=64,
        blank=True,
        null=True,
        default=None,
    )
    fp_pu_id = models.CharField(
        verbose_name=_("Warehouse code"),
        max_length=64,
        blank=True,
        null=True,
        default=None,
    )
    b_100_client_price_paid_or_quoted = models.FloatField(
        max_length=64, blank=True, null=True, default=0
    )
    b_000_3_consignment_number = models.CharField(
        max_length=32, blank=True, null=True, default=None
    )
    b_000_0_b_client_agent_code = models.CharField(
        max_length=32, blank=True, null=True, default=None
    )
    x_booking_Created_With = models.CharField(
        verbose_name=_("Booking Created With"),
        max_length=32,
        blank=True,
        null=True,
    )
    b_067_assembly_required = models.BooleanField(default=False, null=True)
    b_068_b_del_location = models.CharField(
        max_length=64, default=None, null=True, choices=LOCATION_CHOICES
    )
    b_069_b_del_floor_number = models.IntegerField(default=0, null=True)
    b_070_b_del_floor_access_by = models.CharField(
        max_length=32, default=None, null=True, choices=FLOOR_ACCESS_BY_CHOICES
    )
    b_071_b_del_sufficient_space = models.BooleanField(default=True, null=True)
    b_072_b_pu_no_of_assists = models.IntegerField(default=0, null=True)
    b_073_b_del_no_of_assists = models.IntegerField(default=0, null=True)
    b_074_b_pu_access = models.CharField(max_length=32, default=None, null=True)
    b_075_b_del_access = models.CharField(max_length=32, default=None, null=True)
    b_076_b_pu_service = models.CharField(max_length=32, default=None, null=True)
    b_077_b_del_service = models.CharField(max_length=32, default=None, null=True)
    b_078_b_pu_location = models.CharField(
        max_length=64, default=None, null=True, choices=LOCATION_CHOICES
    )
    b_079_b_pu_floor_number = models.IntegerField(default=0, null=True)
    b_080_b_pu_floor_access_by = models.CharField(
        max_length=32, default=None, null=True, choices=FLOOR_ACCESS_BY_CHOICES
    )
    b_081_b_pu_auto_pack = models.BooleanField(default=None, null=True)
    b_091_send_quote_to_pronto = models.BooleanField(default=False, null=True)
    b_092_booking_type = models.CharField(
        max_length=4, default=None, null=True, choices=BOOKING_TYPE_CHOICES
    )
    b_092_is_quote_locked = models.BooleanField(default=False, null=True)
    b_093_b_promo_code = models.CharField(max_length=32, default=None, null=True)
    b_094_client_sales_total = models.FloatField(blank=True, default=None, null=True)
    b_095_authority_to_leave = models.BooleanField(blank=True, default=False, null=True)
    b_096_v_customer_code = models.CharField(
        max_length=20,
        blank=True,
        null=True,
        default=None,
    )
    b_097_bid_closing_at = models.DateTimeField(blank=True, null=True, default=None)
    b_098_pallet_loscam_account = models.CharField(max_length=25, default=None, null=True)
    z_test = models.CharField(max_length=64, blank=True, null=True, default=None)
    zb_101_text_1 = models.CharField(max_length=64, blank=True, null=True, default=None)
    zb_102_text_2 = models.CharField(max_length=64, blank=True, null=True, default=None)
    zb_103_text_3 = models.CharField(max_length=64, blank=True, null=True, default=None)
    zb_104_text_4 = models.CharField(max_length=64, blank=True, null=True, default=None)
    # b_errorCapture
    zb_105_text_5 = models.TextField(blank=True, null=True, default=None)
    zb_121_integer_1 = models.IntegerField(blank=True, default=0, null=True)
    zb_122_integer_2 = models.IntegerField(blank=True, default=0, null=True)
    zb_123_integer_3 = models.IntegerField(blank=True, default=0, null=True)
    zb_124_integer_4 = models.IntegerField(blank=True, default=0, null=True)
    zb_125_integer_5 = models.IntegerField(blank=True, default=0, null=True)
    zb_131_decimal_1 = models.FloatField(blank=True, default=0, null=True)
    zb_132_decimal_2 = models.FloatField(blank=True, default=0, null=True)
    zb_133_decimal_3 = models.FloatField(blank=True, default=0, null=True)
    zb_134_decimal_4 = models.FloatField(blank=True, default=0, null=True)
    zb_135_decimal_5 = models.FloatField(blank=True, default=0, null=True)
    zb_141_date_1 = models.DateField(default=date.today, blank=True, null=True)
    zb_142_date_2 = models.DateField(default=date.today, blank=True, null=True)
    zb_143_date_3 = models.DateField(default=date.today, blank=True, null=True)
    zb_144_date_4 = models.DateField(default=date.today, blank=True, null=True)
    zb_145_date_5 = models.DateField(default=date.today, blank=True, null=True)

    def bok_2s(self):
        return BOK_2_lines.objects.filter(fk_header_id=self.pk_header_id)

    def bok_3s(self):
        return BOK_3_lines_data.objects.filter(fk_header_id=self.pk_header_id)

    def save(self, *args, **kwargs):
        if self._state.adding:
            from api.signal_handlers.bok_1 import on_create_bok_1_handler

            on_create_bok_1_handler(self)

        return super(BOK_1_headers, self).save(*args, **kwargs)

    class Meta:
        db_table = "bok_1_headers"


# @receiver(post_save, sender=BOK_1_headers)
# def post_save_bok_1(sender, instance, **kwargs):
#     from api.signal_handlers.boks import post_save_bok_1_handler

#     post_save_bok_1_handler(instance)


class BOK_2_lines(models.Model):
    ORIGINAL = "original"
    AUTO_PACK = "auto"
    MANUAL_PACK = "manual"
    PACKED_STATUS_CHOICES = (
        (ORIGINAL, "original"),
        (AUTO_PACK, "auto"),
        (MANUAL_PACK, "manual"),
    )

    pk_lines_id = models.AutoField(primary_key=True)
    success = models.CharField(
        verbose_name=_("Success"), max_length=1, default=0, blank=True, null=True
    )
    fk_header_id = models.CharField(
        verbose_name=_("Header id"), max_length=64, blank=True, null=True
    )
    pk_booking_lines_id = models.CharField(max_length=64, blank=True, null=True)
    client_booking_id = models.CharField(
        verbose_name=_("Client booking id"), max_length=64, blank=True, null=True
    )
    l_501_client_UOM = models.CharField(
        verbose_name=_("Client UOM"), max_length=10, blank=True, null=True
    )
    l_009_weight_per_each = models.FloatField(
        verbose_name=_("Weight per each"), blank=True, null=True
    )
    l_010_totaldim = models.FloatField(
        verbose_name=_("Totaldim"), blank=True, null=True
    )
    l_500_client_run_code = models.CharField(
        verbose_name=_("Client run code"), max_length=7, blank=True, null=True
    )
    l_003_item = models.CharField(
        verbose_name=_("Item"), max_length=256, blank=True, null=True
    )
    l_004_dim_UOM = models.CharField(
        verbose_name=_("DIM UOM"), max_length=10, blank=True, null=True
    )
    v_client_pk_consigment_num = models.CharField(
        verbose_name=_("Consigment num"), max_length=64, blank=True, null=True
    )
    l_cubic_weight = models.FloatField(
        verbose_name=_("Cubic Weight"), blank=True, null=True
    )
    l_002_qty = models.IntegerField(
        verbose_name=_("Address Postal Code"), blank=True, null=True
    )
    e_pallet_type = models.CharField(
        verbose_name=_("Pallet Type"), max_length=24, blank=True, null=True
    )
    e_item_type = models.CharField(
        verbose_name=_("Item Type"), max_length=64, blank=True, null=True
    )
    e_item_type_new = models.CharField(
        verbose_name=_("Item Type New"), max_length=32, blank=True, null=True
    )
    date_processed = models.DateTimeField(
        verbose_name=_("Date Pocessed"), default=timezone.now, blank=True, null=True
    )
    l_001_type_of_packaging = models.CharField(
        verbose_name=_("Type Of Packaging"), max_length=24, blank=True, null=True
    )
    l_005_dim_length = models.FloatField(
        verbose_name=_("DIM Length"), blank=True, null=True
    )
    l_006_dim_width = models.FloatField(
        verbose_name=_("DIM Width"), blank=True, null=True
    )
    l_007_dim_height = models.FloatField(
        verbose_name=_("DIM Height"), blank=True, null=True
    )
    l_008_weight_UOM = models.CharField(
        verbose_name=_("DIM Weight"), max_length=10, default=None, blank=True, null=True
    )
    l_009_weight_per_each_original = models.IntegerField(
        verbose_name=_("Weight Per Each Original"), blank=True, null=True
    )
    l_500_b_client_cust_job_code = models.CharField(
        verbose_name=_("Client Cust Job Code"), max_length=32, blank=True, null=True
    )
    client_item_number = models.CharField(
        max_length=64, blank=True, null=True, default=None
    )
    client_item_reference = models.CharField(
        max_length=64, blank=True, null=True, default=None
    )
    is_deleted = models.BooleanField(default=False, null=True)
    b_093_packed_status = models.CharField(
        max_length=16, default=None, null=True, choices=PACKED_STATUS_CHOICES
    )
    b_097_e_bin_number = models.CharField(
        max_length=64, blank=True, null=True, default=None
    )    
    b_098_pallet_loscam_account = models.CharField(max_length=25, default=None, null=True)
    z_createdByAccount = models.CharField(
        verbose_name=_("Created by account"), max_length=64, blank=True, null=True
    )
    z_createdTimeStamp = models.DateTimeField(
        verbose_name=_("Created Timestamp"),
        null=True,
        blank=True,
        auto_now_add=True,
    )
    z_modifiedByAccount = models.CharField(
        verbose_name=_("Modified by account"), max_length=64, blank=True, null=True
    )
    z_modifiedTimeStamp = models.DateTimeField(
        verbose_name=_("Modified Timestamp"),
        null=True,
        blank=True,
        auto_now=True,
    )
    zbl_101_text_1 = models.CharField(
        max_length=64, blank=True, null=True, default=None
    )
    zbl_102_text_2 = models.CharField(
        max_length=64, blank=True, null=True, default=None
    )
    zbl_103_text_3 = models.CharField(
        max_length=64, blank=True, null=True, default=None
    )
    zbl_104_text_4 = models.CharField(
        max_length=64, blank=True, null=True, default=None
    )
    zbl_105_text_5 = models.CharField(
        max_length=64, blank=True, null=True, default=None
    )
    # JasonL OLD sequence
    zbl_121_integer_1 = models.IntegerField(blank=True, default=0, null=True)
    zbl_122_integer_2 = models.IntegerField(blank=True, default=0, null=True)
    zbl_123_integer_3 = models.IntegerField(blank=True, default=0, null=True)
    zbl_124_integer_4 = models.IntegerField(blank=True, default=0, null=True)
    zbl_125_integer_5 = models.IntegerField(blank=True, default=0, null=True)
    # JasonL NEW sequence
    zbl_131_decimal_1 = models.FloatField(blank=True, default=0, null=True)
    zbl_132_decimal_2 = models.FloatField(blank=True, default=0, null=True)
    zbl_133_decimal_3 = models.FloatField(blank=True, default=0, null=True)
    zbl_134_decimal_4 = models.FloatField(blank=True, default=0, null=True)
    zbl_135_decimal_5 = models.FloatField(blank=True, default=0, null=True)
    zbl_141_date_1 = models.DateField(default=date.today, blank=True, null=True)
    zbl_142_date_2 = models.DateField(default=date.today, blank=True, null=True)
    zbl_143_date_3 = models.DateField(default=date.today, blank=True, null=True)
    zbl_144_date_4 = models.DateField(default=date.today, blank=True, null=True)
    zbl_145_date_5 = models.DateField(default=date.today, blank=True, null=True)

    class Meta:
        db_table = "bok_2_lines"


class BOK_3_lines_data(models.Model):
    pk_auto_id = models.AutoField(primary_key=True)
    client_booking_id = models.CharField(
        verbose_name=_("Client booking id"), max_length=64, blank=True, null=True
    )
    fk_header_id = models.CharField(max_length=64, blank=True)
    fk_booking_lines_id = models.CharField(max_length=64, blank=True, default=None)
    v_client_pk_consigment_num = models.CharField(
        verbose_name=_("Consigment num"), max_length=64, blank=True, null=True
    )
    ld_001_qty = models.IntegerField(verbose_name=_("Quantity"), blank=True, null=True)
    ld_002_model_number = models.CharField(
        verbose_name=_("Consigment num"), max_length=40, blank=True, null=True
    )
    ld_003_item_description = models.TextField(
        verbose_name=_("Item Description"), max_length=500, blank=True, null=True
    )
    ld_004_fault_description = models.CharField(
        verbose_name=_("fault Description"), max_length=500, blank=True, null=True
    )
    ld_005_item_serial_number = models.CharField(
        verbose_name=_("Item Serial Number"), max_length=40, blank=True, null=True
    )
    ld_006_insurance_value = models.FloatField(
        verbose_name=_("Insurance Value"), blank=True, null=True
    )
    ld_007_gap_ra = models.TextField(
        verbose_name=_("Gap Ra"), max_length=300, blank=True, null=True
    )
    ld_008_client_ref_number = models.CharField(
        verbose_name=_("Client Ref Number"), max_length=40, blank=True, null=True
    )
    success = models.CharField(
        verbose_name=_("Success"), max_length=1, default=2, blank=True, null=True
    )
    is_deleted = models.BooleanField(default=False, null=True)
    zbld_101_text_1 = models.CharField(
        max_length=64, blank=True, null=True, default=None
    )
    zbld_102_text_2 = models.CharField(
        max_length=64, blank=True, null=True, default=None
    )
    zbld_103_text_3 = models.CharField(
        max_length=64, blank=True, null=True, default=None
    )
    zbld_104_text_4 = models.CharField(
        max_length=64, blank=True, null=True, default=None
    )
    zbld_105_text_5 = models.CharField(
        max_length=255, blank=True, null=True, default=None
    )
    zbld_121_integer_1 = models.IntegerField(blank=True, default=0, null=True)
    zbld_122_integer_2 = models.IntegerField(blank=True, default=0, null=True)
    zbld_123_integer_3 = models.IntegerField(blank=True, default=0, null=True)
    zbld_124_integer_4 = models.IntegerField(blank=True, default=0, null=True)
    zbld_125_integer_5 = models.IntegerField(blank=True, default=0, null=True)
    zbld_131_decimal_1 = models.FloatField(blank=True, default=0, null=True)
    zbld_132_decimal_2 = models.FloatField(blank=True, default=0, null=True)
    zbld_133_decimal_3 = models.FloatField(blank=True, default=0, null=True)
    zbld_134_decimal_4 = models.FloatField(blank=True, default=0, null=True)
    zbld_135_decimal_5 = models.FloatField(blank=True, default=0, null=True)
    zbld_141_date_1 = models.DateField(default=date.today, blank=True, null=True)
    zbld_142_date_2 = models.DateField(default=date.today, blank=True, null=True)
    zbld_143_date_3 = models.DateField(default=date.today, blank=True, null=True)
    zbld_144_date_4 = models.DateField(default=date.today, blank=True, null=True)
    zbld_145_date_5 = models.DateField(default=date.today, blank=True, null=True)
    z_createdByAccount = models.CharField(
        verbose_name=_("Created By Account"), max_length=25, blank=True, null=True
    )
    z_createdTimeStamp = models.DateTimeField(
        verbose_name=_("Created Timestamp"),
        blank=True,
        auto_now_add=True,
    )
    z_modifiedByAccount = models.CharField(
        verbose_name=_("Modified By Account"), max_length=25, blank=True, null=True
    )
    z_modifiedTimeStamp = models.DateTimeField(
        verbose_name=_("Modified Timestamp"),
        blank=True,
        auto_now=True,
    )

    class Meta:
        db_table = "bok_3_lines_data"


class Log(models.Model):
    id = models.AutoField(primary_key=True)
    fk_booking_id = models.CharField(
        verbose_name=_("FK Booking Id"), max_length=64, blank=True, null=True
    )
    request_payload = models.TextField(
        verbose_name=_("Request Payload"), max_length=2000, blank=True, default=None
    )
    response = models.TextField(
        verbose_name=_("Response"), max_length=10000, blank=True, default=None
    )
    request_timestamp = models.DateTimeField(
        verbose_name=_("Request Timestamp"), default=timezone.now, blank=True
    )
    request_status = models.CharField(
        verbose_name=_("Request Status"), max_length=20, blank=True, default=None
    )
    request_type = models.CharField(
        verbose_name=_("Request Type"), max_length=30, blank=True, default=None
    )
    fk_service_provider_id = models.CharField(
        verbose_name=_("Service Provider ID"),
        max_length=36,
        blank=True,
        default=None,
        null=True,
    )
    z_temp_success_seaway_history = models.BooleanField(
        verbose_name=_("Passed by log script"), default=False, blank=True, null=True
    )
    z_createdByAccount = models.CharField(
        verbose_name=_("Created by account"), max_length=64, blank=True, null=True
    )
    z_createdTimeStamp = models.DateTimeField(
        verbose_name=_("Created Timestamp"),
        null=True,
        blank=True,
        auto_now_add=True,
    )
    z_modifiedByAccount = models.CharField(
        verbose_name=_("Modified by account"), max_length=64, blank=True, null=True
    )
    z_modifiedTimeStamp = models.DateTimeField(
        verbose_name=_("Modified Timestamp"),
        null=True,
        blank=True,
        auto_now=True,
    )

    class Meta:
        db_table = "dme_log"


class Api_booking_confirmation_lines(models.Model):
    id = models.AutoField(primary_key=True)
    fk_booking_id = models.CharField(
        verbose_name=_("Booking ID"), max_length=64, blank=True, null=True
    )
    fk_booking_line_id = models.CharField(
        verbose_name=_("Booking Line ID"), max_length=64, blank=True, null=True
    )
    kf_booking_confirmation_id = models.CharField(
        verbose_name=_("Booking Confimration ID"), max_length=64, blank=True, null=True
    )
    pk_booking_confirmation_lines = models.IntegerField(
        verbose_name=_("Booking confirmation lines"), blank=True, null=True
    )
    fk_api_results_id = models.IntegerField(
        verbose_name=_("Result ID"), blank=True, null=True
    )
    service_provider = models.CharField(
        verbose_name=_("Service Provider"), max_length=64, blank=True, null=True
    )
    api_artical_id = models.CharField(
        verbose_name=_("Artical ID"), max_length=64, blank=True, null=True
    )
    api_consignment_id = models.CharField(
        verbose_name=_("Consignment ID"), max_length=64, blank=True, null=True
    )
    api_cost = models.CharField(
        verbose_name=_("Cost"), max_length=64, blank=True, null=True
    )
    api_gst = models.CharField(
        verbose_name=_("GST"), max_length=64, blank=True, null=True
    )
    api_item_id = models.CharField(
        verbose_name=_("Item ID"), max_length=64, blank=True, null=True
    )
    api_item_reference = models.CharField(
        verbose_name=_("Item Reference"), max_length=64, blank=True, null=True
    )
    api_product_id = models.CharField(
        verbose_name=_("Product ID"), max_length=64, blank=True, null=True
    )
    api_status = models.CharField(
        verbose_name=_("Status"), max_length=64, blank=True, null=True
    )
    label_code = models.CharField(max_length=64, blank=True, null=True)
    client_item_reference = models.CharField(
        max_length=64, blank=True, null=True, default=None
    )
    fp_event_date = models.DateField(blank=True, null=True)
    fp_event_time = models.TimeField(blank=True, null=True)
    fp_scan_data = models.CharField(max_length=64, blank=True, null=True, default=None)
    tally = models.IntegerField(blank=True, null=True, default=0)
    barcode_data = models.CharField(max_length=64, blank=True, null=True, default=None)
    barcode_time = models.DateTimeField(null=True, blank=True)
    barcode_scanned_by = models.CharField(
        max_length=64, blank=True, null=True, default=None
    )
    fm_date = models.DateField(blank=True, null=True)
    fm_date_text = models.CharField(max_length=32, blank=True, null=True, default=None)
    z_createdByAccount = models.CharField(
        verbose_name=_("Created by account"), max_length=64, blank=True, null=True
    )
    z_createdTimeStamp = models.DateTimeField(
        verbose_name=_("Created Timestamp"),
        null=True,
        blank=True,
        auto_now_add=True,
    )
    z_modifiedByAccount = models.CharField(
        verbose_name=_("Modified by account"), max_length=64, blank=True, null=True
    )
    z_modifiedTimeStamp = models.DateTimeField(
        verbose_name=_("Modified Timestamp"),
        null=True,
        blank=True,
        auto_now=True,
    )

    class Meta:
        db_table = "api_booking_confirmation_lines"


class Api_booking_quotes_confirmation(models.Model):
    id = models.AutoField(primary_key=True)
    api_shipment_id = models.CharField(
        verbose_name=_("API shipment ID"), max_length=64, blank=True, null=True
    )
    fk_booking_id = models.CharField(
        verbose_name=_("Booking ID"), max_length=64, blank=True, null=True
    )
    kf_order_id = models.CharField(
        verbose_name=_("Order ID"), max_length=64, blank=True, null=True
    )
    fk_freight_provider_id = models.CharField(
        verbose_name=_("Freight Provider ID"), max_length=64, blank=True, null=True
    )
    fk_booking_quote_confirmation = models.CharField(
        verbose_name=_("Freight Provider ID"), max_length=64, blank=True, null=True
    )
    job_date = models.DateTimeField(
        verbose_name=_("Job Date"), default=timezone.now, blank=True, null=True
    )
    provider = models.CharField(
        verbose_name=_("Provider"), max_length=64, blank=True, null=True
    )
    tracking_number = models.CharField(
        verbose_name=_("Tracking Number"), max_length=64, blank=True, null=True
    )
    job_number = models.CharField(
        verbose_name=_("Job Number"), max_length=64, blank=True, null=True
    )
    api_number_of_shipment_items = models.CharField(
        verbose_name=_("API Number Of Shipment Items"),
        max_length=64,
        blank=True,
        null=True,
    )
    etd = models.CharField(verbose_name=_("ETD"), max_length=64, blank=True, null=True)
    fee = models.FloatField(verbose_name=_("Fee"), blank=True, null=True)
    tax_id_1 = models.CharField(
        verbose_name=_("Tax ID 1"), max_length=10, blank=True, null=True
    )
    tax_value_1 = models.IntegerField(
        verbose_name=_("Tax Value 1"), blank=True, null=True
    )
    tax_id_2 = models.CharField(
        verbose_name=_("Tax ID 2"), max_length=10, blank=True, null=True
    )
    tax_value_2 = models.IntegerField(
        verbose_name=_("Tax Value 2"), blank=True, null=True
    )
    tax_id_3 = models.CharField(
        verbose_name=_("Tax ID 3"), max_length=10, blank=True, null=True
    )
    tax_value_3 = models.IntegerField(
        verbose_name=_("Tax Value 3"), blank=True, null=True
    )
    tax_id_4 = models.CharField(
        verbose_name=_("Tax ID 4"), max_length=10, blank=True, null=True
    )
    tax_value_4 = models.IntegerField(
        verbose_name=_("Tax Value 4"), blank=True, null=True
    )
    tax_id_5 = models.CharField(
        verbose_name=_("Tax ID 5"), max_length=10, blank=True, null=True
    )
    z_createdByAccount = models.CharField(
        verbose_name=_("Created by account"), max_length=64, blank=True, null=True
    )
    z_createdTimeStamp = models.DateTimeField(
        verbose_name=_("Created Timestamp"),
        null=True,
        blank=True,
        auto_now_add=True,
    )
    z_modifiedByAccount = models.CharField(
        verbose_name=_("Modified by account"), max_length=64, blank=True, null=True
    )
    z_modifiedTimeStamp = models.DateTimeField(
        verbose_name=_("Modified Timestamp"),
        null=True,
        blank=True,
        auto_now=True,
    )

    class Meta:
        db_table = "api_booking_quotes_confirmation"


class Utl_suburbs(models.Model):
    id = models.AutoField(primary_key=True)
    postal_code = models.CharField(
        verbose_name=_("Postal Code"), max_length=64, blank=True, null=True
    )
    fk_state_id = models.IntegerField(
        verbose_name=_("FK State ID"), blank=True, null=False, default=0
    )
    state = models.CharField(
        verbose_name=_("State"), max_length=64, blank=True, null=True
    )
    suburb = models.CharField(
        verbose_name=_("Suburb"), max_length=64, blank=True, null=True
    )
    ROUTING_ZONE = models.CharField(
        verbose_name=_("Routing Zone"), max_length=64, blank=True, null=True
    )
    ROUTING_CODE = models.CharField(
        verbose_name=_("Routing Code"), max_length=64, blank=True, null=True
    )
    RATING_ZONE_DIRECT = models.CharField(
        verbose_name=_("Rating Zone Direct"), max_length=64, blank=True, null=True
    )
    RATING_ZONE_MEGA = models.CharField(
        verbose_name=_("Rating Zone Mega"), max_length=64, blank=True, null=True
    )
    category = models.CharField(
        verbose_name=_("Category"), max_length=64, blank=True, null=True
    )
    z_BorderExpressEmailForState = models.CharField(
        verbose_name=_("Border Express Email For State"),
        max_length=64,
        blank=True,
        null=True,
    )
    comment = models.CharField(
        verbose_name=_("Comment"), max_length=64, blank=True, null=True
    )
    z_createdByAccount = models.CharField(
        verbose_name=_("Created by account"), max_length=64, blank=True, null=True
    )
    z_createdTimeStamp = models.DateTimeField(
        verbose_name=_("Created Timestamp"),
        null=True,
        blank=True,
        auto_now_add=True,
    )
    z_modifiedByAccount = models.CharField(
        verbose_name=_("Modified by account"), max_length=64, blank=True, null=True
    )
    z_modifiedTimeStamp = models.DateTimeField(
        verbose_name=_("Modified Timestamp"),
        null=True,
        blank=True,
        auto_now=True,
    )

    class Meta:
        db_table = "utl_suburbs"


class Utl_states(models.Model):
    id = models.AutoField(primary_key=True)
    type = models.CharField(
        verbose_name=_("Type"), max_length=64, blank=True, null=True
    )
    fk_country_id = models.CharField(max_length=32, blank=True, null=True, default=None)
    pk_state_id = models.IntegerField(
        verbose_name=_("PK State ID"), blank=True, null=False, default=0
    )
    state_code = models.CharField(
        verbose_name=_("State Code"), max_length=10, blank=True, null=True
    )
    state_name = models.CharField(
        verbose_name=_("State Name"), max_length=64, blank=True, null=True
    )
    sender_code = models.CharField(
        verbose_name=_("Sender Code"), max_length=64, blank=True, null=True
    )
    borderExpress_pu_emails = models.CharField(
        verbose_name=_("Border Express PU Emails"), max_length=64, blank=True, null=True
    )
    z_createdByAccount = models.CharField(
        verbose_name=_("Created by account"), max_length=64, blank=True, null=True
    )
    z_createdTimeStamp = models.DateTimeField(
        verbose_name=_("Created Timestamp"),
        null=True,
        blank=True,
        auto_now_add=True,
    )
    z_modifiedByAccount = models.CharField(
        verbose_name=_("Modified by account"), max_length=64, blank=True, null=True
    )
    z_modifiedTimeStamp = models.DateTimeField(
        verbose_name=_("Modified Timestamp"),
        null=True,
        blank=True,
        auto_now=True,
    )

    class Meta:
        db_table = "utl_states"


class Utl_country_codes(models.Model):
    id = models.AutoField(primary_key=True)
    pk_country_id = models.IntegerField(
        verbose_name=_("PK Country Id"), blank=True, null=False, default=0
    )
    country_code_abbr = models.CharField(
        verbose_name=_("Country Code Abbr"), max_length=16, blank=True, null=True
    )
    country_name = models.CharField(
        verbose_name=_("Country Name"), max_length=36, blank=True, null=True
    )
    z_createdByAccount = models.CharField(
        verbose_name=_("Created by account"), max_length=64, blank=True, null=True
    )
    z_createdTimeStamp = models.DateTimeField(
        verbose_name=_("Created Timestamp"),
        null=True,
        blank=True,
        auto_now_add=True,
    )
    z_modifiedByAccount = models.CharField(
        verbose_name=_("Modified by account"), max_length=64, blank=True, null=True
    )
    z_modifiedTimeStamp = models.DateTimeField(
        verbose_name=_("Modified Timestamp"),
        null=True,
        blank=True,
        auto_now=True,
    )

    class Meta:
        db_table = "utl_country_codes"


class Utl_sql_queries(models.Model):
    id = models.AutoField(primary_key=True)
    sql_title = models.CharField(
        verbose_name=_("SQL Title"), max_length=36, blank=True, null=True
    )
    sql_query = models.TextField(verbose_name=_("SQL Query"), blank=True, null=True)
    sql_description = models.TextField(
        verbose_name=_("SQL Description"), blank=True, null=True
    )
    sql_notes = models.TextField(verbose_name=_("SQL Notes"), blank=True, null=True)
    z_createdByAccount = models.CharField(
        verbose_name=_("Created by account"), max_length=64, blank=True, null=True
    )
    z_createdTimeStamp = models.DateTimeField(
        verbose_name=_("Created Timestamp"),
        null=True,
        blank=True,
        auto_now_add=True,
    )
    z_modifiedByAccount = models.CharField(
        verbose_name=_("Modified by account"), max_length=64, blank=True, null=True
    )
    z_modifiedTimeStamp = models.DateTimeField(
        verbose_name=_("Modified Timestamp"),
        null=True,
        blank=True,
        auto_now=True,
    )

    class Meta:
        db_table = "utl_sql_queries"


class Dme_status_history(models.Model):
    id = models.AutoField(primary_key=True)
    fk_booking_id = models.CharField(
        verbose_name=_("Booking ID"), max_length=64, blank=True, null=True
    )
    status_from_api = models.CharField(
        verbose_name=_("Status From API"),
        max_length=50,
        blank=True,
        default=None,
        null=True,
    )
    status_code_api = models.CharField(
        verbose_name=_("Status Code API"),
        max_length=50,
        blank=True,
        default=None,
        null=True,
    )
    status_last = models.CharField(
        verbose_name=_("Status Last"), max_length=64, blank=True, null=True
    )
    notes = models.CharField(
        verbose_name=_("Notes"), max_length=200, blank=True, null=True
    )
    communicate_tick = models.BooleanField(
        verbose_name=_("Communicate Tick"), default=False, blank=True, null=True
    )
    notes_type = models.CharField(
        verbose_name=_("Notes Type"), max_length=24, blank=True, null=True
    )
    status_old = models.CharField(
        verbose_name=_("Status Old"), max_length=64, blank=True, null=True
    )
    api_status_pretranslation = models.CharField(
        verbose_name=_("Api Status Pretranslation"),
        max_length=64,
        blank=True,
        null=True,
    )
    booking_request_data = models.CharField(
        verbose_name=_("Booking Request Data"), max_length=64, blank=True, null=True
    )
    request_dates = models.CharField(
        verbose_name=_("Request Dates"), max_length=64, blank=True, null=True
    )
    recipient_name = models.CharField(
        verbose_name=_("Recipient Name"),
        max_length=64,
        blank=True,
        null=True,
        default=None,
    )
    fk_fp_id = models.CharField(
        verbose_name=_("FP ID"), max_length=64, blank=True, default=None, null=True
    )
    depot_name = models.CharField(
        verbose_name=_("Depot Name"), max_length=64, blank=True, default=None, null=True
    )
    dme_notes = models.TextField(
        verbose_name=_("DME notes"), max_length=500, blank=True, default=None, null=True
    )
    event_time_stamp = models.DateTimeField(
        verbose_name=_("Event Timestamp"), default=timezone.now, blank=True, null=True
    )
    status_update_via = models.CharField(
        verbose_name=_("Status Updated Via"), max_length=64, blank=True, null=True
    )  # one of 3 - fp api, manual, excel
    dme_status_detail = models.TextField(
        max_length=500, blank=True, null=True, default=None
    )
    dme_status_action = models.TextField(
        max_length=500, blank=True, null=True, default=None
    )
    dme_status_linked_reference_from_fp = models.TextField(
        max_length=150, blank=True, null=True, default=None
    )
    b_booking_visualID = models.CharField(max_length=64, blank=True, null=True)
    b_status_api = models.CharField(max_length=64, blank=True, null=True)
    total_scanned = models.IntegerField(blank=True, null=False, default=0)
    z_createdByAccount = models.CharField(
        verbose_name=_("Created by account"), max_length=64, blank=True, null=True
    )
    z_createdTimeStamp = models.DateTimeField(
        verbose_name=_("Created Timestamp"),
        null=True,
        blank=True,
        auto_now_add=True,
    )
    z_modifiedByAccount = models.CharField(
        verbose_name=_("Modified by account"), max_length=64, blank=True, null=True
    )
    z_modifiedTimeStamp = models.DateTimeField(
        verbose_name=_("Modified Timestamp"),
        null=True,
        blank=True,
        auto_now=True,
    )

    class Meta:
        db_table = "dme_status_history"

    def is_last_status_of_booking(self, booking):
        status_histories = Dme_status_history.objects.filter(
            fk_booking_id=booking.pk_booking_id
        ).order_by("id")

        if status_histories.exists():
            if self.pk == status_histories.last().pk:
                return True

        return False


class Dme_urls(models.Model):
    id = models.AutoField(primary_key=True)
    url = models.CharField(verbose_name=_("URL"), max_length=255, blank=True, null=True)
    description = models.CharField(
        verbose_name=_("Description"), max_length=255, blank=True, null=True
    )

    class Meta:
        db_table = "dme_urls"


class Dme_log_addr(models.Model):
    id = models.AutoField(primary_key=True)
    addresses = models.TextField(
        verbose_name=_("Address Info"), blank=True, null=True, default=None
    )
    fk_booking_id = models.CharField(
        verbose_name=_("Description"),
        max_length=255,
        blank=True,
        null=True,
        default=None,
    )
    consignmentNumber = models.CharField(
        verbose_name=_("Consignment Number"),
        max_length=255,
        blank=True,
        null=True,
        default=None,
    )
    length = models.FloatField(
        verbose_name=_("Length"), blank=True, null=True, default=0
    )
    width = models.FloatField(verbose_name=_("Width"), blank=True, null=True, default=0)
    height = models.FloatField(
        verbose_name=_("Height"), blank=True, null=True, default=0
    )
    weight = models.FloatField(
        verbose_name=_("Height"), blank=True, null=True, default=0
    )

    class Meta:
        db_table = "dme_log_addr"


class Dme_comm_and_task(models.Model):
    id = models.AutoField(primary_key=True)
    fk_booking_id = models.CharField(
        verbose_name=_("Booking ID"), max_length=64, blank=True, null=True
    )
    assigned_to = models.CharField(
        verbose_name=_("Assigned To"), max_length=64, blank=True, null=True
    )
    priority_of_log = models.CharField(
        verbose_name=_("Priority Of Log"), max_length=64, blank=True, null=True
    )
    dme_action = models.TextField(
        verbose_name=_("DME Action"), max_length=4000, blank=True, null=True
    )
    dme_com_title = models.TextField(
        verbose_name=_("DME Comm Title"), max_length=4000, blank=True, null=True
    )
    dme_detail = models.CharField(
        verbose_name=_("DME Detail"), max_length=255, blank=True, null=True
    )
    dme_notes_type = models.CharField(
        verbose_name=_("DME Notes Type"), max_length=64, blank=True, null=True
    )
    dme_notes_external = models.TextField(
        verbose_name=_("DME Notes External"), max_length=4096, blank=True, null=True
    )
    status = models.CharField(
        verbose_name=_("Status"), max_length=32, blank=True, null=True
    )
    query = models.CharField(
        verbose_name=_("Query"), max_length=254, blank=True, null=True
    )
    closed = models.BooleanField(
        verbose_name=_("Closed"), blank=True, null=True, default=False
    )
    due_by_date = models.DateField(verbose_name=_("Due By Date"), blank=True, null=True)
    due_by_time = models.TimeField(verbose_name=_("Due By Time"), blank=True, null=True)
    due_by_new_date = models.DateField(
        verbose_name=_("Due By New Date"), blank=True, null=True
    )
    due_by_new_time = models.TimeField(
        verbose_name=_("Due By New Time"), blank=True, null=True
    )
    final_due_date_time = models.DateTimeField(
        verbose_name=_("Final Due Date Time"), blank=True, null=True
    )
    status_log_closed_time = models.DateTimeField(
        verbose_name=_("Status Log Closed Time"), blank=True, null=True
    )
    z_snooze_option = models.FloatField(
        verbose_name=_("Snooze Option"), blank=True, null=True
    )
    z_time_till_due_sec = models.FloatField(
        verbose_name=_("Time Till Due Second"), blank=True, null=True
    )
    z_createdByAccount = models.CharField(
        verbose_name=_("Created by account"), max_length=64, blank=True, null=True
    )
    z_createdTimeStamp = models.DateTimeField(
        verbose_name=_("Created Timestamp"), null=True, blank=True, auto_now_add=True
    )
    z_modifiedByAccount = models.CharField(
        verbose_name=_("Modified by account"), max_length=64, blank=True, null=True
    )
    z_modifiedTimeStamp = models.DateTimeField(
        verbose_name=_("Modified Timestamp"),
        null=True,
        blank=True,
        auto_now=True,
    )

    class Meta:
        db_table = "dme_comm_and_task"


class Dme_comm_notes(models.Model):
    id = models.AutoField(primary_key=True)
    comm = models.ForeignKey(Dme_comm_and_task, on_delete=models.CASCADE)
    username = models.CharField(
        verbose_name=_("User"), max_length=64, blank=True, null=True
    )
    dme_notes = models.TextField(verbose_name=_("DME Notes"), blank=True, null=True)
    dme_notes_type = models.CharField(
        verbose_name=_("DME Notes Type"), max_length=64, blank=True, null=True
    )
    dme_notes_no = models.IntegerField(
        verbose_name=_("DME Notes No"), blank=False, null=False, default=1
    )
    note_date_created = models.DateField(
        verbose_name=_("Date First"), blank=True, null=True
    )
    note_date_updated = models.DateField(
        verbose_name=_("Date Modified"), blank=True, null=True
    )
    note_time_created = models.TimeField(
        verbose_name=_("Time First"), blank=True, null=True
    )
    note_time_updated = models.TimeField(
        verbose_name=_("Time Modified"), blank=True, null=True
    )
    z_createdByAccount = models.CharField(
        verbose_name=_("Created by account"), max_length=64, blank=True, null=True
    )
    z_createdTimeStamp = models.DateTimeField(
        verbose_name=_("Created Timestamp"), null=True, blank=True, auto_now_add=True
    )
    z_modifiedByAccount = models.CharField(
        verbose_name=_("Modified by account"), max_length=64, blank=True, null=True
    )
    z_modifiedTimeStamp = models.DateTimeField(
        verbose_name=_("Modified Timestamp"),
        null=True,
        blank=True,
        auto_now=True,
    )

    class Meta:
        db_table = "dme_comm_notes"


class Dme_status_notes(models.Model):
    id = models.AutoField(primary_key=True)
    status = models.CharField(
        verbose_name=_("status"), max_length=64, blank=True, null=True
    )

    class Meta:
        db_table = "dme_status_notes"


class Dme_package_types(models.Model):
    id = models.AutoField(primary_key=True)
    dmePackageTypeCode = models.CharField(
        verbose_name=_("DME Package Type Code"), max_length=25, blank=True, null=True
    )
    dmePackageCategory = models.CharField(
        verbose_name=_("DME Package Category"), max_length=25, blank=True, null=True
    )
    dmePackageTypeDesc = models.CharField(
        verbose_name=_("DME Package Type Desc"), max_length=50, blank=True, null=True
    )
    z_createdByAccount = models.CharField(
        verbose_name=_("Created by account"), max_length=64, blank=True, null=True
    )
    z_createdTimeStamp = models.DateTimeField(
        verbose_name=_("Created Timestamp"),
        null=True,
        blank=True,
        auto_now_add=True,
    )
    z_modifiedByAccount = models.CharField(
        verbose_name=_("Modified by account"), max_length=64, blank=True, null=True
    )
    z_modifiedTimeStamp = models.DateTimeField(
        verbose_name=_("Modified Timestamp"),
        null=True,
        blank=True,
        auto_now=True,
    )

    class Meta:
        db_table = "dme_package_types"


class Utl_dme_status(models.Model):
    id = models.AutoField(primary_key=True)
    phone = models.IntegerField(verbose_name=_("phone number"), null=True, blank=True)
    dme_delivery_status_category = models.CharField(
        max_length=64, blank=True, null=True
    )
    dme_delivery_status = models.CharField(max_length=64, blank=True, null=True)
    dev_notes = models.TextField(max_length=400, blank=True, null=True)
    sort_order = models.FloatField(verbose_name=_("sort order"), default=1)
    z_show_client_option = models.BooleanField(null=True, blank=True, default=False)
    dme_status_label = models.CharField(max_length=128, blank=True, null=True)
    z_createdByAccount = models.CharField(
        verbose_name=_("Created by account"), max_length=64, blank=True, null=True
    )
    z_createdTimeStamp = models.DateTimeField(
        verbose_name=_("Created Timestamp"),
        null=True,
        blank=True,
        auto_now_add=True,
    )
    z_modifiedByAccount = models.CharField(
        verbose_name=_("Modified by account"), max_length=64, blank=True, null=True
    )
    z_modifiedTimeStamp = models.DateTimeField(
        verbose_name=_("Modified Timestamp"),
        null=True,
        blank=True,
        auto_now=True,
    )

    class Meta:
        db_table = "utl_dme_status"


class Dme_utl_fp_statuses(models.Model):
    id = models.AutoField(primary_key=True)
    fk_fp_id = models.IntegerField(default=1, blank=True, null=True)
    fp_name = models.CharField(max_length=50, blank=True, null=True)
    fp_original_status = models.TextField(max_length=400, blank=True, null=True)
    fp_lookup_status = models.TextField(max_length=400, blank=True, null=True)
    fp_status_description = models.TextField(
        max_length=1024, blank=True, null=True, default=None
    )
    dme_status = models.CharField(max_length=150, blank=True, null=True)
    if_scan_total_in_booking_greaterthanzero = models.CharField(
        max_length=32, blank=True, null=True
    )
    pod_delivery_override = models.BooleanField(blank=True, null=True, default=False)
    z_createdByAccount = models.CharField(
        verbose_name=_("Created by account"), max_length=64, blank=True, null=True
    )
    z_createdTimeStamp = models.DateTimeField(
        verbose_name=_("Created Timestamp"),
        null=True,
        blank=True,
        auto_now_add=True,
    )
    z_modifiedByAccount = models.CharField(
        verbose_name=_("Modified by account"), max_length=64, blank=True, null=True
    )
    z_modifiedTimeStamp = models.DateTimeField(
        verbose_name=_("Modified Timestamp"),
        null=True,
        blank=True,
        auto_now=True,
    )

    class Meta:
        db_table = "dme_utl_fp_statuses"


class Dme_utl_client_customer_group(models.Model):
    id = models.AutoField(primary_key=True)
    fk_client_id = models.CharField(max_length=11, blank=True, null=True)
    name_lookup = models.CharField(max_length=50, blank=True, null=True)
    group_name = models.CharField(max_length=64, blank=True, null=True)
    z_createdByAccount = models.CharField(
        verbose_name=_("Created by account"), max_length=64, blank=True, null=True
    )
    z_createdTimeStamp = models.DateTimeField(
        verbose_name=_("Created Timestamp"),
        null=True,
        blank=True,
        auto_now_add=True,
    )
    z_modifiedByAccount = models.CharField(
        verbose_name=_("Modified by account"), max_length=64, blank=True, null=True
    )
    z_modifiedTimeStamp = models.DateTimeField(
        verbose_name=_("Modified Timestamp"),
        null=True,
        blank=True,
        auto_now=True,
    )

    class Meta:
        db_table = "dme_utl_client_customer_group"


class Utl_fp_delivery_times(models.Model):
    id = models.AutoField(primary_key=True)
    fk_fp_id = models.IntegerField(default=1, blank=True, null=True)
    fp_name = models.CharField(max_length=50, blank=True, null=True)
    postal_code_from = models.IntegerField(default=1, blank=True, null=True)
    postal_code_to = models.IntegerField(default=1, blank=True, null=True)
    delivery_days = models.FloatField(default=7, blank=True, null=True)
    z_createdByAccount = models.CharField(
        verbose_name=_("Created by account"), max_length=64, blank=True, null=True
    )
    z_createdTimeStamp = models.DateTimeField(
        verbose_name=_("Created Timestamp"),
        null=True,
        blank=True,
        auto_now_add=True,
    )
    z_modifiedByAccount = models.CharField(
        verbose_name=_("Modified by account"), max_length=64, blank=True, null=True
    )
    z_modifiedTimeStamp = models.DateTimeField(
        verbose_name=_("Modified Timestamp"),
        null=True,
        blank=True,
        auto_now=True,
    )

    class Meta:
        db_table = "utl_fp_delivery_times"


class Utl_dme_status_details(models.Model):
    id = models.AutoField(primary_key=True)
    dme_status_detail = models.TextField(max_length=500, blank=True, null=True)
    z_createdByAccount = models.CharField(
        verbose_name=_("Created by account"), max_length=64, blank=True, null=True
    )
    z_createdTimeStamp = models.DateTimeField(
        verbose_name=_("Created Timestamp"),
        null=True,
        blank=True,
        auto_now_add=True,
    )
    z_modifiedByAccount = models.CharField(
        verbose_name=_("Modified by account"), max_length=64, blank=True, null=True
    )
    z_modifiedTimeStamp = models.DateTimeField(
        verbose_name=_("Modified Timestamp"),
        null=True,
        blank=True,
        auto_now=True,
    )

    class Meta:
        db_table = "utl_dme_status_details"


class Utl_dme_status_actions(models.Model):
    id = models.AutoField(primary_key=True)
    dme_status_action = models.TextField(max_length=500, blank=True, null=True)
    z_createdByAccount = models.CharField(
        verbose_name=_("Created by account"), max_length=64, blank=True, null=True
    )
    z_createdTimeStamp = models.DateTimeField(
        verbose_name=_("Created Timestamp"),
        null=True,
        blank=True,
        auto_now_add=True,
    )
    z_modifiedByAccount = models.CharField(
        verbose_name=_("Modified by account"), max_length=64, blank=True, null=True
    )
    z_modifiedTimeStamp = models.DateTimeField(
        verbose_name=_("Modified Timestamp"),
        null=True,
        blank=True,
        auto_now=True,
    )

    class Meta:
        db_table = "utl_dme_status_actions"


class FP_zones(models.Model):
    id = models.AutoField(primary_key=True)
    suburb = models.CharField(max_length=50, blank=True, null=True)
    state = models.CharField(max_length=50, blank=True, null=True)
    postal_code = models.CharField(max_length=16, blank=True, null=True)
    zone = models.CharField(max_length=50, blank=True, null=True)
    carrier = models.CharField(max_length=50, blank=True, null=True)
    service = models.CharField(max_length=50, blank=True, null=True)
    sender_code = models.CharField(max_length=50, blank=True, null=True)
    fk_fp = models.CharField(max_length=32, blank=True, null=True, default=None)
    start_postal_code = models.CharField(
        max_length=16, blank=True, null=True, default=None
    )
    end_postal_code = models.CharField(
        max_length=16, blank=True, null=True, default=None
    )

    class Meta:
        db_table = "fp_zones"

    def __str__(self):
        return f"#{self.id}, {self.fk_fp}, {self.zone}, {self.state}, {self.postal_code}, {self.suburb}"


class FP_carriers(models.Model):
    id = models.AutoField(primary_key=True)
    fk_fp = models.CharField(max_length=32, blank=True, null=True, default=None)
    carrier = models.CharField(max_length=50, blank=True, null=True)
    connote_start_value = models.IntegerField(default=None, blank=True, null=True)
    connote_end_value = models.IntegerField(default=None, blank=True, null=True)
    label_start_value = models.IntegerField(default=None, blank=True, null=True)
    label_end_value = models.IntegerField(default=None, blank=True, null=True)
    current_value = models.IntegerField(default=None, blank=True, null=True)

    class Meta:
        db_table = "fp_carriers"


class FP_label_scans(models.Model):
    id = models.AutoField(primary_key=True)
    fk_fp = models.CharField(max_length=32, blank=True, null=True, default=None)
    label_code = models.CharField(max_length=32, blank=True, null=True, default=None)
    client_item_reference = models.CharField(
        max_length=32, blank=True, null=True, default=None
    )
    scanned_date = models.DateField(blank=True, null=True, default=None)
    scanned_time = models.TimeField(blank=True, null=True, default=None)
    scanned_by = models.CharField(max_length=32, blank=True, null=True, default=None)
    z_createdTimeStamp = models.DateTimeField(
        verbose_name=_("Created Timestamp"),
        null=True,
        blank=True,
        auto_now_add=True,
    )
    z_modifiedTimeStamp = models.DateTimeField(
        verbose_name=_("Modified Timestamp"),
        null=True,
        blank=True,
        auto_now=True,
    )

    class Meta:
        db_table = "fp_label_scans"


class FP_onforwarding(models.Model):
    id = models.AutoField(primary_key=True)
    fp_id = models.IntegerField()
    fp_company_name = models.CharField(max_length=64)
    state = models.CharField(max_length=64)
    postcode = models.CharField(max_length=6)
    suburb = models.CharField(max_length=64)
    base_price = models.FloatField()
    price_per_kg = models.FloatField()

    class Meta:
        db_table = "fp_onforwarding"


class DME_reports(models.Model):
    id = models.AutoField(primary_key=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    name = models.CharField(max_length=128, blank=True, null=True)
    type = models.CharField(max_length=32, blank=True, null=True)
    url = models.TextField(max_length=512, blank=True, null=True)
    z_createdByAccount = models.CharField(
        verbose_name=_("Created by account"), max_length=64, blank=True, null=True
    )
    z_createdTimeStamp = models.DateTimeField(
        verbose_name=_("Created Timestamp"),
        null=True,
        blank=True,
        auto_now_add=True,
    )
    z_modifiedByAccount = models.CharField(
        verbose_name=_("Modified by account"), max_length=64, blank=True, null=True
    )
    z_modifiedTimeStamp = models.DateTimeField(
        verbose_name=_("Modified Timestamp"),
        null=True,
        blank=True,
        auto_now=True,
    )

    class Meta:
        db_table = "dme_reports"


class DME_Label_Settings(models.Model):
    id = models.AutoField(primary_key=True)
    uom = models.CharField(max_length=24, blank=True, null=True, default=None)
    font_family = models.CharField(max_length=128, blank=True, null=True)
    font_size_small = models.FloatField(blank=True, null=True, default=0)
    font_size_medium = models.FloatField(blank=True, null=True, default=0)
    font_size_large = models.FloatField(blank=True, null=True, default=0)
    label_dimension_length = models.FloatField(blank=True, null=True, default=0)
    label_dimension_width = models.FloatField(blank=True, null=True, default=0)
    label_image_size_length = models.FloatField(blank=True, null=True, default=0)
    label_image_size_width = models.FloatField(blank=True, null=True, default=0)
    barcode_dimension_length = models.FloatField(blank=True, null=True, default=0)
    barcode_dimension_width = models.FloatField(blank=True, null=True, default=0)
    z_createdByAccount = models.CharField(
        verbose_name=_("Created by account"), max_length=64, blank=True, null=True
    )
    z_createdTimeStamp = models.DateTimeField(
        verbose_name=_("Created Timestamp"),
        null=True,
        blank=True,
        auto_now_add=True,
    )
    z_modifiedByAccount = models.CharField(
        verbose_name=_("Modified by account"), max_length=64, blank=True, null=True
    )
    z_modifiedTimeStamp = models.DateTimeField(
        verbose_name=_("Modified Timestamp"),
        null=True,
        blank=True,
        auto_now=True,
    )

    class Meta:
        db_table = "label_settings"


class DME_Email_Templates(models.Model):
    id = models.AutoField(primary_key=True)
    fk_idEmailParent = models.IntegerField(blank=True, null=True, default=0)
    emailName = models.CharField(max_length=255, blank=True, null=True)
    emailBody = models.TextField(blank=True, null=True)
    sectionName = models.TextField(max_length=255, blank=True, null=True)
    emailBodyRepeatEven = models.TextField(max_length=2048, blank=True, null=True)
    emailBodyRepeatOdd = models.TextField(max_length=2048, blank=True, null=True)
    whenAttachmentUnavailable = models.TextField(blank=True, null=True)
    z_createdByAccount = models.CharField(
        verbose_name=_("Created by account"), max_length=64, blank=True, null=True
    )
    z_createdTimeStamp = models.DateTimeField(
        verbose_name=_("Created Timestamp"),
        null=True,
        blank=True,
        auto_now_add=True,
    )
    z_modifiedByAccount = models.CharField(
        verbose_name=_("Modified by account"), max_length=64, blank=True, null=True
    )
    z_modifiedTimeStamp = models.DateTimeField(
        verbose_name=_("Modified Timestamp"),
        null=True,
        blank=True,
        auto_now=True,
    )

    class Meta:
        db_table = "dme_email_templates"


class DME_Options(models.Model):
    id = models.AutoField(primary_key=True)
    option_name = models.CharField(max_length=255, blank=True, null=False)
    option_value = models.CharField(max_length=8, blank=True, null=False)
    option_description = models.TextField(max_length=1024, blank=True, null=False)
    option_schedule = models.IntegerField(blank=True, null=True, default=0)
    start_time = models.DateTimeField(default=None, blank=True, null=True)
    end_time = models.DateTimeField(default=None, blank=True, null=True)
    start_count = models.IntegerField(blank=True, null=True, default=0)
    end_count = models.IntegerField(blank=True, null=True, default=0)
    elapsed_seconds = models.IntegerField(blank=True, null=True, default=0)
    is_running = models.BooleanField(blank=True, null=True, default=False)
    show_in_admin = models.BooleanField(blank=True, null=True, default=False)
    arg1 = models.IntegerField(blank=True, null=True, default=0)
    arg2 = models.DateTimeField(blank=True, null=True, default=None)
    z_createdByAccount = models.CharField(
        verbose_name=_("Created by account"), max_length=64, blank=True, null=True
    )
    z_createdTimeStamp = models.DateTimeField(
        verbose_name=_("Created Timestamp"),
        null=True,
        blank=True,
        auto_now_add=True,
    )
    z_modifiedByAccount = models.CharField(
        verbose_name=_("Modified by account"), max_length=64, blank=True, null=True
    )
    z_modifiedTimeStamp = models.DateTimeField(
        verbose_name=_("Modified Timestamp"),
        null=True,
        blank=True,
        auto_now=True,
    )

    class Meta:
        db_table = "dme_options"


class FP_Store_Booking_Log(models.Model):
    id = models.AutoField(primary_key=True)
    v_FPBookingNumber = models.CharField(
        max_length=40,
        blank=True,
        null=True,
        default=None,
    )
    delivery_booking = models.DateField(default=None, blank=True, null=True)
    fp_store_event_date = models.DateField(default=None, blank=True, null=True)
    fp_store_event_time = models.TimeField(default=None, blank=True, null=True)
    fp_store_event_desc = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        default=None,
    )
    csv_file_name = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        default=None,
    )
    z_createdTimeStamp = models.DateTimeField(
        verbose_name=_("Created Timestamp"), auto_now_add=True
    )

    class Meta:
        db_table = "fp_store_booking_log"


class Pallet(models.Model):
    id = models.AutoField(primary_key=True)
    code = models.CharField(max_length=64, null=True, default=None)
    type = models.CharField(max_length=64, null=True, default=None)
    desc = models.CharField(max_length=254, null=True, default=None)
    length = models.FloatField(null=True, default=None)
    width = models.FloatField(null=True, default=None)
    height = models.FloatField(null=True, default=None)
    weight = models.FloatField(null=True, default=None)  # UOM: kg
    max_weight = models.FloatField(null=True, default=None)  # UOM: kg

    class Meta:
        db_table = "utl_pallet"


class FP_availabilities(models.Model):
    id = models.AutoField(primary_key=True)
    freight_provider = models.ForeignKey(Fp_freight_providers, on_delete=models.CASCADE)
    code = models.CharField(
        max_length=64,
        blank=True,
        null=True,
        default=None,
    )
    mon_start = models.TimeField(default=None, blank=True, null=True)
    mon_end = models.TimeField(default=None, blank=True, null=True)
    tue_start = models.TimeField(default=None, blank=True, null=True)
    tue_end = models.TimeField(default=None, blank=True, null=True)
    wed_start = models.TimeField(default=None, blank=True, null=True)
    wed_end = models.TimeField(default=None, blank=True, null=True)
    thu_start = models.TimeField(default=None, blank=True, null=True)
    thu_end = models.TimeField(default=None, blank=True, null=True)
    fri_start = models.TimeField(default=None, blank=True, null=True)
    fri_end = models.TimeField(default=None, blank=True, null=True)
    sat_start = models.TimeField(default=None, blank=True, null=True)
    sat_end = models.TimeField(default=None, blank=True, null=True)
    sun_start = models.TimeField(default=None, blank=True, null=True)
    sun_end = models.TimeField(default=None, blank=True, null=True)

    class Meta:
        db_table = "fp_availabilities"


class FP_costs(models.Model):
    id = models.AutoField(primary_key=True)
    UOM_charge = models.CharField(
        max_length=16,
        blank=True,
        null=True,
        default=None,
    )
    start_qty = models.IntegerField(default=0, null=True, blank=True)
    end_qty = models.IntegerField(default=0, null=True, blank=True)
    basic_charge = models.FloatField(default=0, null=True, blank=True)
    min_charge = models.FloatField(default=0, null=True, blank=True)
    per_UOM_charge = models.FloatField(default=0, null=True, blank=True)
    oversize_premium = models.FloatField(default=0, null=True, blank=True)
    oversize_price = models.FloatField(default=0, null=True, blank=True)
    m3_to_kg_factor = models.IntegerField(default=0, null=True, blank=True)
    dim_UOM = models.CharField(
        max_length=16,
        blank=True,
        null=True,
        default=None,
    )
    price_up_to_length = models.FloatField(default=0, null=True, blank=True)
    price_up_to_width = models.FloatField(default=0, null=True, blank=True)
    price_up_to_height = models.FloatField(default=0, null=True, blank=True)
    weight_UOM = models.CharField(
        max_length=16,
        blank=True,
        null=True,
        default=None,
    )
    price_up_to_weight = models.FloatField(default=0, null=True, blank=True)
    max_length = models.FloatField(default=0, null=True, blank=True)
    max_width = models.FloatField(default=0, null=True, blank=True)
    max_height = models.FloatField(default=0, null=True, blank=True)
    max_weight = models.FloatField(default=0, null=True, blank=True)
    max_volume = models.FloatField(default=0, null=True, blank=True)

    class Meta:
        db_table = "fp_costs"


class FP_pricing_rules(models.Model):
    id = models.AutoField(primary_key=True)
    freight_provider = models.ForeignKey(Fp_freight_providers, on_delete=models.CASCADE)
    client = models.ForeignKey(DME_clients, on_delete=models.CASCADE, null=True)
    cost = models.ForeignKey(FP_costs, on_delete=models.CASCADE, null=True)
    etd = models.ForeignKey(FP_Service_ETDs, on_delete=models.CASCADE, null=True)
    vehicle = models.ForeignKey(
        FP_vehicles, on_delete=models.CASCADE, null=True, default=None
    )
    service_type = models.CharField(
        max_length=64,
        blank=True,
        null=True,
        default=None,
    )
    service_timing_code = models.CharField(
        max_length=32,
        blank=True,
        null=True,
        default=None,
    )
    both_way = models.BooleanField(blank=True, null=True, default=False)
    pu_zone = models.CharField(max_length=16, blank=True, null=True, default=None)
    pu_state = models.CharField(max_length=32, blank=True, null=True, default=None)
    pu_postal_code = models.CharField(max_length=8, blank=True, null=True, default=None)
    pu_suburb = models.CharField(max_length=32, blank=True, null=True, default=None)
    de_zone = models.CharField(max_length=16, blank=True, null=True, default=None)
    de_state = models.CharField(max_length=32, blank=True, null=True, default=None)
    de_postal_code = models.CharField(max_length=8, blank=True, null=True, default=None)
    de_suburb = models.CharField(max_length=32, blank=True, null=True, default=None)

    class Meta:
        db_table = "fp_pricing_rules"


class DME_Files(models.Model):
    id = models.AutoField(primary_key=True)
    file_name = models.CharField(max_length=255, blank=False, null=True, default=None)
    file_path = models.TextField(max_length=1024, blank=False, null=True, default=None)
    file_type = models.CharField(max_length=16, blank=False, null=True, default=None)
    file_extension = models.CharField(
        max_length=8, blank=False, null=True, default=None
    )
    note = models.TextField(max_length=2048, blank=False, null=True, default=None)
    z_createdTimeStamp = models.DateTimeField(blank=True, null=True, auto_now_add=True)
    z_createdByAccount = models.CharField(
        max_length=32, blank=False, null=True, default=None
    )

    class Meta:
        db_table = "dme_files"


class Client_Auto_Augment(models.Model):
    de_Email = models.CharField(max_length=64, blank=True, null=True, default=None)
    de_Email_Group_Emails = models.TextField(
        max_length=512, blank=True, null=True, default=None
    )
    de_To_Address_Street_1 = models.CharField(
        max_length=40, blank=True, null=True, default=None
    )
    de_To_Address_Street_2 = models.CharField(
        max_length=40, blank=True, null=True, default=None
    )
    fk_id_dme_client = models.ForeignKey(
        DME_clients, on_delete=models.CASCADE, default=3
    )
    de_to_companyName = models.CharField(
        max_length=40, blank=True, null=True, default=None
    )
    company_hours_info = models.CharField(
        max_length=40, blank=True, null=True, default=None
    )

    class Meta:
        db_table = "client_auto_augment"


class Client_Process_Mgr(models.Model):
    fk_booking_id = models.CharField(
        verbose_name=_("Booking ID"), max_length=64, blank=True, null=True, default=None
    )

    process_name = models.CharField(
        verbose_name=_("Process Name"), max_length=40, blank=False, null=True
    )

    z_createdTimeStamp = models.DateTimeField(
        verbose_name=_("Created Timestamp"),
        blank=True,
        null=True,
        auto_now_add=True,
    )

    origin_puCompany = models.CharField(
        verbose_name=_("Origin PU Company"), max_length=128, blank=False, null=True
    )

    origin_pu_Address_Street_1 = models.CharField(
        verbose_name=_("Origin PU Address Street1"),
        max_length=40,
        blank=False,
        null=True,
    )

    origin_pu_Address_Street_2 = models.CharField(
        verbose_name=_("Origin PU Address Street2"),
        max_length=40,
        blank=False,
        null=True,
    )

    origin_pu_pickup_instructions_address = models.TextField(
        verbose_name=_("Origin PU instrunctions address"),
        max_length=512,
        blank=True,
        null=True,
        default=None,
    )

    origin_deToCompanyName = models.CharField(
        verbose_name=_("Origin DE Company Name"),
        max_length=128,
        blank=True,
        null=True,
        default=None,
    )

    origin_de_Email = models.CharField(
        verbose_name=_("Origin DE Email"),
        max_length=64,
        blank=True,
        null=True,
        default=None,
    )

    origin_de_Email_Group_Emails = models.TextField(
        max_length=512,
        blank=True,
        null=True,
        default=None,
    )

    origin_de_To_Address_Street_1 = models.CharField(
        verbose_name=_("Origin DE Address Street 1"),
        max_length=40,
        blank=True,
        null=True,
        default=None,
    )

    origin_de_To_Address_Street_2 = models.CharField(
        verbose_name=_("Origin DE Address Street 2"),
        max_length=40,
        blank=True,
        null=True,
        default=None,
    )

    origin_puPickUpAvailFrom_Date = models.DateField(
        verbose_name=_("Origin PU Available From Date"),
        blank=True,
        default=None,
        null=True,
    )

    origin_pu_PickUp_Avail_Time_Hours = models.IntegerField(
        verbose_name=_("Origin PU Available Time Hours"),
        blank=True,
        default=0,
        null=True,
    )

    origin_pu_PickUp_Avail_Time_Minutes = models.IntegerField(
        verbose_name=_("Origin PU Available Time Minutes"),
        blank=True,
        default=0,
        null=True,
    )

    origin_pu_PickUp_By_Date = models.DateField(
        verbose_name=_("Origin PU By Date DME"), blank=True, null=True
    )

    origin_pu_PickUp_By_Time_Hours = models.IntegerField(
        verbose_name=_("Origin PU By Time Hours"),
        blank=True,
        default=0,
        null=True,
    )

    origin_pu_PickUp_By_Time_Minutes = models.IntegerField(
        verbose_name=_("Origin PU By Time Minutes"),
        blank=True,
        default=0,
        null=True,
    )

    class Meta:
        db_table = "client_process_mgr"


class EmailLogs(models.Model):
    id = models.AutoField(primary_key=True)
    booking = models.ForeignKey(Bookings, on_delete=models.CASCADE)
    emailName = models.CharField(max_length=255, blank=True, null=True, default=None)
    to_emails = models.CharField(max_length=255, blank=True, null=True, default=None)
    cc_emails = models.TextField(max_length=512, blank=True, null=True, default=None)
    z_createdByAccount = models.CharField(
        verbose_name=_("Created by account"), max_length=64, blank=True, null=True
    )
    z_createdTimeStamp = models.DateTimeField(
        verbose_name=_("Created Timestamp"),
        null=True,
        blank=True,
        auto_now_add=True,
    )

    class Meta:
        db_table = "email_logs"


class BookingSets(models.Model):
    id = models.AutoField(primary_key=True)
    name = models.CharField(max_length=255, blank=True, null=True, default=None)
    booking_ids = models.TextField(blank=True, null=True, default=None)
    note = models.TextField(max_length=512, blank=True, null=True, default=None)
    status = models.CharField(max_length=255, blank=True, null=True, default=None)
    auto_select_type = models.BooleanField(
        max_length=255, blank=True, null=True, default=True
    )  # True: lowest | False: Fastest
    vehicle = models.ForeignKey(
        FP_vehicles, on_delete=models.CASCADE, null=True, default=None
    )
    line_haul_date = models.DateField(null=True, blank=True, default=timezone.now)
    z_createdByAccount = models.CharField(
        verbose_name=_("Created by account"), max_length=64, blank=True, null=True
    )
    z_createdTimeStamp = models.DateTimeField(
        verbose_name=_("Created Timestamp"),
        null=True,
        blank=True,
        auto_now_add=True,
    )
    z_modifiedByAccount = models.CharField(
        verbose_name=_("Modified by account"), max_length=64, blank=True, null=True
    )
    z_modifiedTimeStamp = models.DateTimeField(
        verbose_name=_("Modified Timestamp"),
        null=True,
        blank=True,
        auto_now=True,
    )

    class Meta:
        db_table = "dme_booking_sets"

        # Deactivated on 2022-09-22
        # @transaction.atomic
        # def save(self, *args, **kwargs):
        #     creating = self._state.adding

        #     if not creating:
        #         old_obj = BookingSets.objects.get(pk=self.pk)

        #     if self.status == "Starting BOOK" and self.status != old_obj.status:
        #         # Check if set includes bookings that should be BOOKed via CSV
        #         booking_ids = self.booking_ids.split(", ")
        #         bookings = Bookings.objects.filter(
        #             pk__in=booking_ids,
        #             vx_freight_provider="State Transport",
        #             b_dateBookedDate__isnull=True,
        #         )

        #         if bookings:
        #             from api.operations.csv.index import build_csv
        #             from api.operations.labels.index import build_label
        #             from api.operations.email_senders import send_booking_status_email
        #             from api.utils import get_sydney_now_time
        #             from api.common import status_history

        #             build_csv(bookings.values_list("pk", flat=True))

        #             for booking in bookings:
        #                 booking.b_dateBookedDate = get_sydney_now_time(
        #                     return_type="datetime"
        #                 )
        #                 booking.v_FPBookingNumber = "DME" + str(booking.b_bookingID_Visual)
        #                 status_history.create(booking, "Booked", "DME_BE")
        #                 booking.save()

        #                 # Build Label and send booking email
        #                 _fp_name = booking.vx_freight_provider.lower()
        #                 file_path = f"{S3_URL}/pdfs/{_fp_name}_au/"
        #                 file_path, file_name = build_label(booking, file_path)
        #                 booking.z_label_url = f"{_fp_name}_au/{file_name}"
        #                 booking.save()

        #                 # Send email when GET_LABEL
        #                 email_template_name = "General Booking"

        #                 # if booking.b_booking_Category == "Salvage Expense":
        #                 #     email_template_name = "Return Booking"

        #                 send_booking_status_email(booking.pk, email_template_name, "DME_BE")

        #   return super(BookingSets, self).save(*args, **kwargs)


class Tokens(models.Model):
    id = models.AutoField(primary_key=True)
    value = models.CharField(max_length=255, default=None)
    type = models.CharField(max_length=255, default=None)
    z_createdTimeStamp = models.DateTimeField(
        verbose_name=_("Created Timestamp"),
        null=True,
        blank=True,
        auto_now_add=True,
    )
    z_expiryTimeStamp = models.DateTimeField(default=None)

    class Meta:
        db_table = "tokens"


class Client_Products(models.Model):
    id = models.AutoField(primary_key=True)
    fk_id_dme_client = models.ForeignKey(
        DME_clients, on_delete=models.CASCADE, blank=True, null=True
    )
    parent_model_number = models.CharField(max_length=64, default=None)
    child_model_number = models.CharField(max_length=64, default=None)
    description = models.CharField(max_length=1024, default=None, null=True, blank=True)
    qty = models.PositiveIntegerField(default=1)
    e_dimUOM = models.CharField(
        verbose_name=_("Dim UOM"), max_length=10, blank=True, null=True
    )
    e_weightUOM = models.CharField(
        verbose_name=_("Weight UOM"), max_length=56, blank=True, null=True
    )
    e_dimLength = models.FloatField(verbose_name=_("Dim Length"), blank=True, null=True)
    e_dimWidth = models.FloatField(verbose_name=_("Dim Width"), blank=True, null=True)
    e_dimHeight = models.FloatField(verbose_name=_("Dim Height"), blank=True, null=True)
    e_weightPerEach = models.FloatField(
        verbose_name=_("Weight Per Each"), blank=True, null=True
    )
    is_ignored = models.BooleanField(blank=True, null=True, default=False)
    z_createdByAccount = models.CharField(
        verbose_name=_("Created by account"), max_length=64, blank=True, null=True
    )
    z_createdTimeStamp = models.DateTimeField(
        verbose_name=_("Created Timestamp"),
        null=True,
        blank=True,
        auto_now_add=True,
    )
    z_modifiedByAccount = models.CharField(
        verbose_name=_("Modified by account"), max_length=64, blank=True, null=True
    )
    z_modifiedTimeStamp = models.DateTimeField(
        verbose_name=_("Modified Timestamp"),
        null=True,
        blank=True,
        auto_now=True,
    )

    class Meta:
        db_table = "client_products"


class Client_Ras(models.Model):
    id = models.AutoField(primary_key=True)
    ra_number = models.CharField(max_length=30, blank=True, null=True)
    dme_number = models.CharField(max_length=50, blank=True, null=True)
    name_first = models.CharField(max_length=50, blank=True, null=True)
    name_surname = models.CharField(max_length=50, blank=True, null=True)
    phone_mobile = models.CharField(max_length=30, blank=True, null=True)
    address1 = models.CharField(max_length=80, blank=True, null=True)
    address2 = models.CharField(max_length=80, blank=True, null=True)
    suburb = models.CharField(max_length=50, blank=True, null=True)
    postal_code = models.CharField(max_length=30, blank=True, null=True)
    state = models.CharField(max_length=25, blank=True, null=True)
    country = models.CharField(max_length=50, blank=True, null=True)
    item_model_num = models.CharField(max_length=50, blank=True, null=True)
    description = models.CharField(max_length=150, blank=True, null=True)
    serial_number = models.CharField(max_length=50, blank=True, null=True)
    product_in_box = models.BooleanField(blank=True, null=True, default=False)
    fk_id_dme_client = models.ForeignKey(
        DME_clients, on_delete=models.CASCADE, blank=True, null=True
    )

    z_createdByAccount = models.CharField(
        verbose_name=_("Created by account"), max_length=64, blank=True, null=True
    )
    z_createdTimeStamp = models.DateTimeField(
        verbose_name=_("Created Timestamp"),
        null=True,
        blank=True,
        auto_now_add=True,
    )
    z_modifiedByAccount = models.CharField(
        verbose_name=_("Modified by account"), max_length=64, blank=True, null=True
    )
    z_modifiedTimeStamp = models.DateTimeField(
        verbose_name=_("Modified Timestamp"),
        null=True,
        blank=True,
        auto_now=True,
    )

    class Meta:
        db_table = "client_ras"


class DME_Error(models.Model):
    id = models.AutoField(primary_key=True)
    freight_provider = models.ForeignKey(Fp_freight_providers, on_delete=models.CASCADE)
    accountCode = models.CharField(max_length=32, blank=True, null=True)
    fk_booking_id = models.CharField(
        verbose_name=_("Booking ID"), max_length=64, blank=True, null=True
    )
    error_code = models.CharField(max_length=32, blank=True, null=True)
    error_description = models.TextField(max_length=500, blank=True, null=True)
    z_createdByAccount = models.CharField(
        verbose_name=_("Created by account"), max_length=64, blank=True, null=True
    )
    z_createdTimeStamp = models.DateTimeField(
        verbose_name=_("Created Timestamp"),
        null=True,
        blank=True,
        auto_now_add=True,
    )
    z_modifiedByAccount = models.CharField(
        verbose_name=_("Modified by account"), max_length=64, blank=True, null=True
    )
    z_modifiedTimeStamp = models.DateTimeField(
        verbose_name=_("Modified Timestamp"),
        null=True,
        blank=True,
        auto_now=True,
    )

    class Meta:
        db_table = "dme_errors"


class DME_Augment_Address(models.Model):
    id = models.AutoField(primary_key=True)
    origin_word = models.CharField(max_length=32, blank=True, null=True)
    augmented_word = models.CharField(max_length=32, blank=True, null=True)

    class Meta:
        db_table = "dme_augment_address"


class DME_SMS_Templates(models.Model):
    id = models.AutoField(primary_key=True)
    smsName = models.CharField(max_length=255, blank=True, null=True)
    smsMessage = models.TextField(blank=True, null=True)
    z_createdByAccount = models.CharField(
        verbose_name=_("Created by account"), max_length=64, blank=True, null=True
    )
    z_createdTimeStamp = models.DateTimeField(
        verbose_name=_("Created Timestamp"),
        null=True,
        blank=True,
        auto_now_add=True,
    )
    z_modifiedByAccount = models.CharField(
        verbose_name=_("Modified by account"), max_length=64, blank=True, null=True
    )
    z_modifiedTimeStamp = models.DateTimeField(
        verbose_name=_("Modified Timestamp"),
        null=True,
        blank=True,
        auto_now=True,
    )

    class Meta:
        db_table = "dme_sms_templates"


class FC_Log(models.Model):
    id = models.AutoField(primary_key=True)
    client_booking_id = models.CharField(max_length=64)
    old_quote = models.ForeignKey(
        API_booking_quotes, on_delete=models.CASCADE, null=True, related_name="+"
    )  # Optional
    new_quote = models.ForeignKey(
        API_booking_quotes, on_delete=models.CASCADE, null=True, related_name="+"
    )  # Optional
    z_createdTimeStamp = models.DateTimeField(
        verbose_name=_("Created Timestamp"),
        null=True,
        blank=True,
        auto_now_add=True,
    )

    class Meta:
        db_table = "fc_log"


class Client_FP(models.Model):
    id = models.AutoField(primary_key=True)
    client = models.ForeignKey(DME_clients, on_delete=models.CASCADE)
    fp = models.ForeignKey(Fp_freight_providers, on_delete=models.CASCADE)
    fuel_levy = models.FloatField(default=None, blank=True, null=True)
    connote_number = models.IntegerField(blank=True, null=True, default=0)
    sscc_seq = models.IntegerField(blank=True, null=True, default=0)
    is_active = models.BooleanField(default=True)
    z_createdTimeStamp = models.DateTimeField(null=True, auto_now_add=True)

    class Meta:
        db_table = "client_fp"


class FPRouting(models.Model):
    """
    This table is used only for TNT
    zFpDpc_Label spec with Full Integration Doc.pdf - 33p
    """

    id = models.AutoField(primary_key=True)
    freight_provider = models.ForeignKey(
        Fp_freight_providers, on_delete=models.CASCADE, default=None, null=True
    )
    data_code = models.CharField(max_length=10, default=None, null=True)
    dest_suburb = models.CharField(max_length=45, default=None, null=True)
    dest_state = models.CharField(max_length=45, default=None, null=True)
    dest_postcode = models.CharField(max_length=45, default=None, null=True)
    orig_depot = models.CharField(max_length=10, default=None, null=True)
    orig_depot_except = models.CharField(max_length=10, default=None, null=True)
    gateway = models.CharField(max_length=10, default=None, null=True)
    onfwd = models.CharField(max_length=10, default=None, null=True)
    sort_bin = models.CharField(max_length=10, default=None, null=True)
    orig_postcode = models.CharField(max_length=10, default=None, null=True)
    routing_group = models.CharField(max_length=32, default=None, null=True)

    class Meta:
        db_table = "fp_routing"


class AlliedETD(models.Model):
    """
    This table is used only for ALLIED Built-in pricing
    """

    id = models.AutoField(primary_key=True)
    zone = models.ForeignKey(FP_zones, on_delete=models.CASCADE, null=True)
    syd = models.FloatField(null=True, default=None)
    mel = models.FloatField(null=True, default=None)
    bne = models.FloatField(null=True, default=None)
    adl = models.FloatField(null=True, default=None)
    per = models.FloatField(null=True, default=None)

    class Meta:
        db_table = "allied_etd"


class PostalCode(models.Model):
    """
    "QLD", "State", "Townsville", "4806-4824, 4835-4850, 9960-9979"
    """

    id = models.AutoField(primary_key=True)
    type = models.CharField(max_length=16, default=None, null=True)
    state = models.CharField(max_length=16, default=None, null=True)
    name = models.CharField(max_length=128, default=None, null=True)
    range = models.CharField(max_length=255, default=None, null=True)

    class Meta:
        db_table = "postal_code"


class Surcharge(models.Model):
    id = models.AutoField(primary_key=True)
    quote = models.ForeignKey(API_booking_quotes, on_delete=models.CASCADE, null=True)
    fp = models.ForeignKey(Fp_freight_providers, on_delete=models.CASCADE, null=True)
    name = models.CharField(max_length=255, default=None, null=True)
    amount = models.FloatField(null=True, default=None)
    line_id = models.CharField(max_length=36, default=None, null=True)  # Line/BOK_2 pk
    qty = models.IntegerField(blank=True, null=True, default=0)  # Line/BOK_2 qty

    ### New fields from 2022-02-24 ###
    booking = models.ForeignKey(
        Bookings, on_delete=models.CASCADE, null=True, default=None
    )
    # Visible to Customer
    visible = models.BooleanField(default=False)
    # Is manually entered by DME admin
    is_manually_entered = models.BooleanField(default=False)
    connote_or_reference = models.CharField(max_length=64, default=None, null=True)
    booked_date = models.DateTimeField(null=True, default=timezone.now)
    eta_pu_date = models.DateTimeField(null=True, default=None)
    eta_de_date = models.DateTimeField(null=True, default=None)
    actual_pu_date = models.DateTimeField(null=True, default=None)
    actual_de_date = models.DateTimeField(null=True, default=None)

    def save(self, *args, **kwargs):
        creating = self._state.adding

        if not creating:
            cls = self.__class__
            old = cls.objects.get(pk=self.pk)
            new = self

            changed_fields = []
            for field in cls._meta.get_fields():
                field_name = field.name
                try:
                    if getattr(old, field_name) != getattr(new, field_name):
                        changed_fields.append(field_name)
                except Exception as ex:  # Catch field does not exist exception
                    pass
            kwargs["update_fields"] = changed_fields
        return super(Surcharge, self).save(*args, **kwargs)

    class Meta:
        db_table = "dme_surcharge"


@receiver(post_save, sender=Surcharge)
def post_save_surcharge(sender, instance, created, update_fields, **kwargs):
    from api.signal_handlers.surcharge import post_save_handler

    post_save_handler(instance, created, update_fields)


@receiver(post_delete, sender=Surcharge)
def post_delete_surcharge(sender, instance, **kwargs):
    from api.signal_handlers.surcharge import post_delete_handler

    post_delete_handler(instance)


class FP_status_history(models.Model):
    id = models.AutoField(primary_key=True)
    booking = models.ForeignKey(Bookings, on_delete=models.CASCADE)
    fp = models.ForeignKey(Fp_freight_providers, on_delete=models.CASCADE)
    status = models.CharField(max_length=32, default=None, null=True)
    desc = models.TextField(default=None, null=True)
    event_timestamp = models.DateTimeField(null=True, default=None)
    driver = models.CharField(max_length=32, default=None, null=True)
    location = models.CharField(max_length=32, default=None, null=True)
    is_active = models.BooleanField(default=True)
    z_createdAt = models.DateTimeField(null=True, default=timezone.now)

    class Meta:
        db_table = "fp_status_history"


@receiver(post_save, sender=FP_status_history)
def post_save_fp_status_history(sender, instance, **kwargs):
    from api.signal_handlers.fp_status_history import post_save_handler

    post_save_handler(instance)


class ZohoTicketSummary(models.Model):
    id = models.AutoField(primary_key=True)
    summary = models.TextField(default=None, null=True)
    z_createdAt = models.DateTimeField(null=True, default=timezone.now)

    class Meta:
        db_table = "zoho_ticket_summary"


class S_Bookings(models.Model):
    id = models.AutoField(primary_key=True)
    b_bookingID_Visual = models.IntegerField(blank=True, null=True, default=0)
    b_client_booking_ref_num = models.CharField(
        max_length=64,
        blank=True,
        null=True,
        default=None,
    )
    b_dateBookedDate = models.DateTimeField(blank=True, null=True, default=None)
    v_FPBookingNumber = models.CharField(
        max_length=40,
        blank=True,
        null=True,
        default=None,
    )
    b_client_order_num = models.CharField(
        max_length=64, blank=True, null=True, default=None
    )
    de_Deliver_By_Date = models.DateField(blank=True, null=True, default=None)
    b_client_name = models.CharField(max_length=64, blank=True, null=True, default=None)
    b_client_name_sub = models.CharField(
        max_length=64, blank=True, null=True, default=None
    )
    b_client_id = models.CharField(
        max_length=64,
        blank=True,
        null=True,
        default=None,
    )
    vx_freight_provider = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        default=None,
    )
    vx_serviceName = models.CharField(
        max_length=30,
        blank=True,
        null=True,
        default=None,
    )
    b_status = models.CharField(
        verbose_name=_("Status"), max_length=40, blank=True, null=True, default=None
    )
    b_status_category = models.CharField(
        max_length=32, blank=True, null=True, default=None
    )
    de_To_Address_Street_1 = models.CharField(
        max_length=40,
        blank=True,
        null=True,
        default=None,
    )
    de_To_Address_Street_2 = models.CharField(
        max_length=40,
        blank=True,
        null=True,
        default=None,
    )
    de_To_Address_State = models.CharField(
        max_length=20,
        blank=True,
        null=True,
        default=None,
    )
    de_To_Address_Suburb = models.CharField(
        max_length=50,
        blank=True,
        null=True,
        default=None,
    )
    de_To_Address_PostalCode = models.CharField(
        max_length=30,
        blank=True,
        null=True,
        default=None,
    )
    de_To_Address_Country = models.CharField(
        max_length=12,
        blank=True,
        null=True,
        default=None,
    )
    de_to_Contact_F_LName = models.CharField(
        max_length=50,
        blank=True,
        null=True,
        default=None,
    )
    de_Email = models.CharField(max_length=64, blank=True, null=True, default=None)
    de_to_Phone_Mobile = models.CharField(
        max_length=25,
        blank=True,
        null=True,
        default=None,
    )
    de_to_Phone_Main = models.CharField(
        max_length=30,
        blank=True,
        null=True,
        default=None,
    )
    fp_event_datetime = models.DateTimeField(blank=True, null=True, default=None)
    fp_message = models.CharField(max_length=255, blank=True, null=True, default=None)
    zoho_summary = models.CharField(max_length=255, blank=True, null=True, default=None)
    zoho_event_datetime = models.DateTimeField(blank=True, null=True, default=None)
    booked_for_comm_communicate_via = models.CharField(
        max_length=120,
        blank=True,
        null=True,
        default=None,
    )
    last_cs_note = models.TextField(null=True, default=None)
    last_cs_note_timestamp = models.DateTimeField(null=True, default=None)
    s_06_Estimated_Delivery_TimeStamp = models.DateTimeField(
        blank=True, null=True, default=None
    )
    s_06_Latest_Delivery_Date_Time_Override = models.DateTimeField(
        blank=True, null=True, default=None
    )
    s_21_Actual_Delivery_TimeStamp = models.DateTimeField(
        blank=True, null=True, default=None
    )
    b_booking_Priority = models.CharField(
        max_length=32,
        blank=True,
        null=True,
        default=None,
    )
    z_createdAt = models.DateTimeField(null=True, default=timezone.now)
    z_updatedAt = models.DateTimeField(null=True, default=timezone.now)

    class Meta:
        db_table = "shared_bookings"


class S_Booking_Lines(models.Model):
    id = models.AutoField(primary_key=True)
    booking = models.ForeignKey(S_Bookings, on_delete=models.CASCADE)
    e_type_of_packaging = models.CharField(
        verbose_name=_("Type Of Packaging"), max_length=36, blank=True, null=True
    )
    e_item_type = models.CharField(
        verbose_name=_("Item Type"), max_length=64, blank=True, null=True
    )
    e_pallet_type = models.CharField(
        verbose_name=_("Pallet Type"), max_length=24, blank=True, null=True
    )
    e_item = models.CharField(
        verbose_name=_("Item"), max_length=256, blank=True, null=True
    )
    e_qty = models.IntegerField(blank=True, null=True)
    e_weightUOM = models.CharField(
        verbose_name=_("Weight UOM"), max_length=56, blank=True, null=True
    )
    e_weightPerEach = models.FloatField(
        verbose_name=_("Weight Per Each"), blank=True, null=True
    )
    e_dimUOM = models.CharField(
        verbose_name=_("Dim UOM"), max_length=10, blank=True, null=True
    )
    e_dimLength = models.FloatField(verbose_name=_("Dim Length"), blank=True, null=True)
    e_dimWidth = models.FloatField(verbose_name=_("Dim Width"), blank=True, null=True)
    e_dimHeight = models.FloatField(verbose_name=_("Dim Height"), blank=True, null=True)
    e_cubic = models.FloatField(blank=True, null=True)
    e_cubic_2_mass_factor = models.FloatField(blank=True, null=True)
    e_cubic_mass = models.FloatField(blank=True, null=True)
    fp_event_datetime = models.DateTimeField(blank=True, null=True, default=None)
    fp_status = models.CharField(max_length=64, blank=True, null=True, default=None)
    fp_message = models.CharField(max_length=255, blank=True, null=True, default=None)
    z_createdAt = models.DateTimeField(null=True, default=timezone.now)
    z_updatedAt = models.DateTimeField(null=True, default=timezone.now)

    class Meta:
        db_table = "shared_booking_lines"


class DMEBookingCSNote(models.Model):
    id = models.AutoField(primary_key=True)
    booking = models.ForeignKey(Bookings, on_delete=models.CASCADE)
    note = models.TextField()
    z_createdByAccount = models.CharField(
        verbose_name=_("Created by account"), max_length=64, blank=True, null=True
    )
    z_createdTimeStamp = models.DateTimeField(
        verbose_name=_("Created Timestamp"),
        null=True,
        blank=True,
        auto_now_add=True,
    )
    z_modifiedByAccount = models.CharField(
        verbose_name=_("Modified by account"), max_length=64, blank=True, null=True
    )
    z_modifiedTimeStamp = models.DateTimeField(
        verbose_name=_("Modified Timestamp"),
        null=True,
        blank=True,
        auto_now=True,
    )

    class Meta:
        db_table = "dme_booking_cs_note"


class DME_Vehicle(models.Model):
    id = models.AutoField(primary_key=True)
    number = models.CharField(max_length=32, blank=True, null=True, default=None)
    code = models.CharField(max_length=128, blank=True, null=True, default=None)
    vehicle = models.CharField(max_length=128, blank=True, null=True, default=None)
    provider = models.CharField(max_length=128, blank=True, null=True, default=None)
    suburb_from = models.CharField(max_length=32, blank=True, null=True, default=None)
    suburb_to = models.CharField(max_length=32, blank=True, null=True, default=None)
    linehaul_booked_date = models.DateTimeField(null=True)
    departure_date_planned = models.TimeField(null=True)
    arrival_date_planned = models.DateTimeField(null=True)
    arrival_date_actual = models.DateTimeField(null=True)
    inv_linehaul_cost_ex_gst = models.FloatField(blank=True, null=True)
    guarantor = models.CharField(max_length=64, blank=True, null=True, default=None)
    guaranteed_fill_percent = models.FloatField(blank=True, null=True)
    notes = models.CharField(max_length=255, blank=True, null=True, default=None)
    status = models.CharField(max_length=64, blank=True, null=True, default=None)
    active = models.BooleanField(null=True, default=None)
    paid_for_by = models.CharField(max_length=32, blank=True, null=True, default=None)
    constant_1 = models.BooleanField(null=True, default=None)
    constant_2 = models.IntegerField(default=2)
    fp_to_view = models.CharField(max_length=64, blank=True, null=True, default=None)
    consignment_to_view = models.CharField(
        max_length=64, blank=True, null=True, default=None
    )
    fp_invoice_id_to_set = models.CharField(
        max_length=64, blank=True, null=True, default=None
    )
    dme_linehaul_extra01 = models.CharField(
        max_length=64, blank=True, null=True, default=None
    )
    dme_linehaul_extra02 = models.CharField(
        max_length=64, blank=True, null=True, default=None
    )
    planned_arrival = models.CharField(
        max_length=32, blank=True, null=True, default=None
    )
    z_createdByAccount = models.CharField(
        verbose_name=_("Created by account"), max_length=64, blank=True, null=True
    )
    z_createdTimeStamp = models.DateTimeField(
        verbose_name=_("Created Timestamp"),
        null=True,
        blank=True,
        auto_now_add=True,
    )
    z_modifiedByAccount = models.CharField(
        verbose_name=_("Modified by account"), max_length=64, blank=True, null=True
    )
    z_modifiedTimeStamp = models.DateTimeField(
        verbose_name=_("Modified Timestamp"),
        null=True,
        blank=True,
        auto_now=True,
    )

    class Meta:
        db_table = "dme_vehicle"


class LinehaulOrder(models.Model):
    id = models.AutoField(primary_key=True)
    linehaul = models.ForeignKey(DME_Vehicle, on_delete=models.CASCADE)
    booking = models.ForeignKey(Bookings, on_delete=models.CASCADE)
    quote = models.ForeignKey(API_booking_quotes, on_delete=models.CASCADE)
    z_createdByAccount = models.CharField(
        verbose_name=_("Created by account"), max_length=64, blank=True, null=True
    )
    z_createdTimeStamp = models.DateTimeField(
        verbose_name=_("Created Timestamp"),
        null=True,
        blank=True,
        auto_now_add=True,
    )
    z_modifiedByAccount = models.CharField(
        verbose_name=_("Modified by account"), max_length=64, blank=True, null=True
    )
    z_modifiedTimeStamp = models.DateTimeField(
        verbose_name=_("Modified Timestamp"),
        null=True,
        blank=True,
        auto_now=True,
    )

    class Meta:
        db_table = "dme_linehaul_orders"


class DME_Voice_Calls(models.Model):
    id = models.AutoField(primary_key=True)
    booking = models.ForeignKey(Bookings, on_delete=models.CASCADE)
    uid = models.CharField(verbose_name=_("uid"), max_length=45, blank=True, null=True)
    last_call_timestamp = models.DateTimeField(
        verbose_name=_("Created Timestamp"),
        null=True,
        blank=True,
        auto_now_add=True,
    )
    call_count = models.IntegerField(blank=True, null=True, default=0)
    is_client_received = models.IntegerField(blank=True, null=True, default=0)

    class Meta:
        db_table = "dme_voice_calls"


class SupplierInvoice(models.Model):
    id = models.AutoField(primary_key=True)
    fk_booking_id = models.CharField(max_length=128, blank=True, null=True)
    fk_import_file_id = models.CharField(max_length=128, blank=True, null=True)
    imported_from_xls = models.CharField(max_length=128, blank=True, null=True)
    si_01_fp = models.CharField(max_length=32, blank=True, null=True)
    si_03_fp_booking_date = models.DateField(blank=True, null=True)
    si_04_5fp_invoice_num = models.CharField(max_length=32, blank=True, null=True)
    si_50_1_dme_invoice_number = models.CharField(max_length=64, blank=True, null=True)
    si_17_02_fpchargefinal_2_00 = models.FloatField(blank=True, null=True)
    si_17_8_fpfuellevy = models.FloatField(blank=True, null=True)
    fk_dmevisual_id_final = models.CharField(max_length=16, blank=True, null=True)
    text_01 = models.CharField(max_length=64, blank=True, null=True)
    text_02 = models.CharField(max_length=64, blank=True, null=True)
    text_03 = models.CharField(max_length=64, blank=True, null=True)
    num_01 = models.FloatField(blank=True, null=True)
    is_flagged_no_show_bi = models.FloatField(blank=True, null=True)
    total_cost_show_client = models.FloatField(blank=True, null=True)
    b_client_name = models.CharField(
        verbose_name=_("Client Name"),
        max_length=36,
        blank=True,
        null=True,
        default=None,
    )
    rec_200_Supplier_approvedToInvoice_YD_YS_NO_TR = models.CharField(
        max_length=128, blank=True, null=True
    )
    x09_fp_charge_description = models.CharField(max_length=128, blank=True, null=True)
    si_13_Service = models.CharField(max_length=128, blank=True, null=True)
    si_18_0_Markup = models.FloatField(blank=True, null=True)
    fpinv_total_mass_kg = models.FloatField(blank=True, null=True)
    fpinv_total_cbm = models.FloatField(blank=True, null=True)
    fpinv_factor = models.FloatField(blank=True, null=True)
    fpinv_factor_fp = models.IntegerField(blank=True, null=True)
    fpinv_total_cbm_kg = models.FloatField(blank=True, null=True)
    dme_added_amt = models.FloatField(blank=True, null=True)
    pk_idinvoicedata = models.CharField(max_length=64, blank=True, null=True)
    si_18_5markupfinal = models.FloatField(blank=True, null=True)

    class Meta:
        db_table = "supinv_supplierinvoice"


class Fpinv_order_totals(models.Model):
    id = models.AutoField(primary_key=True)
    pk_fm = models.CharField(max_length=64, blank=True, null=True)
    fk_booking_id = models.CharField(
        verbose_name=_("FK Booking Id"), max_length=64, blank=True, null=True
    )
    dme_number = models.IntegerField(blank=True, null=True)
    fpinv_total_mass_kg = models.FloatField(blank=True, null=True)
    fpinv_total_cbm = models.FloatField(blank=True, null=True)
    fpinv_factor = models.FloatField(blank=True, null=True)
    fpinv_total_cbm_kg = models.FloatField(blank=True, null=True)

    class Meta:
        db_table = "fpinv_order_totals"


class Allocation(models.Model):
    id = models.AutoField(primary_key=True)
    b_bookingID_Visual = models.IntegerField(
        verbose_name=_("BookingID Visual"), blank=True, null=True, default=0
    )
    imported_from_xls = models.CharField(max_length=128, blank=True, null=True)
    allocation_dollar_amount = models.FloatField(blank=True, null=True)
    dme_invoice_number = models.CharField(max_length=64, blank=True, null=True)
    text_01 = models.CharField(max_length=64, blank=True, null=True)
    text_02 = models.CharField(max_length=64, blank=True, null=True)
    text_03 = models.CharField(max_length=64, blank=True, null=True)
    num_01 = models.FloatField(blank=True, null=True)
    num_02 = models.FloatField(blank=True, null=True)
    num_03 = models.FloatField(blank=True, null=True)
    b_client_name = models.CharField(
        verbose_name=_("Client Name"),
        max_length=36,
        blank=True,
        null=True,
        default=None,
    )
    rec_200_Supplier_approvedToInvoice_YD_YS_NO_TR = models.CharField(
        max_length=128, blank=True, null=True
    )
    x09_fp_charge_description = models.CharField(max_length=128, blank=True, null=True)
    si_13_Service = models.CharField(max_length=128, blank=True, null=True)
    si_18_0_Markup = models.FloatField(blank=True, null=True)
    cost_to_show_client = models.FloatField(blank=True, null=True)
    cost_to_add_to_fp_cost = models.FloatField(blank=True, null=True)
    is_flagged_no_show_bi = models.FloatField(blank=True, null=True)
    total_cost_show_client = models.FloatField(blank=True, null=True)


class DME_Tokens(models.Model):
    id = models.AutoField(primary_key=True)
    token_type = models.CharField(max_length=32, blank=True, null=True, default=None)
    token = models.CharField(max_length=128, blank=True, null=True, default=None)
    email = models.CharField(max_length=128, blank=True, null=True, default=None)
    api_booking_quote_id = models.IntegerField(blank=True, null=True)
    vx_freight_provider = models.CharField(
        max_length=128, blank=True, null=True, default=None
    )
    booking_id = models.IntegerField(default=None, blank=True, null=True)
    z_createdTimeStamp = models.DateTimeField(
        verbose_name=_("Created Timestamp"),
        null=True,
        blank=True,
        auto_now_add=True,
    )
    z_expiredTimeStamp = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "dme_tokens"


class SHIP_SSCC_Ranges(models.Model):
    id = models.AutoField(primary_key=True)
    freight_provider = models.ForeignKey(Fp_freight_providers, on_delete=models.CASCADE)
    service_type = models.CharField(max_length=32, blank=True, null=True, default=None)
    account_number = models.CharField(
        max_length=32, blank=True, null=True, default=None
    )
    source_system_code = models.CharField(
        max_length=32, blank=True, null=True, default=None
    )
    prefix_1 = models.CharField(
        max_length=32, blank=True, null=True, default=None
    )  # SHIP (connote)
    prefix_2 = models.CharField(
        max_length=32, blank=True, null=True, default=None
    )  # SSCC
    ship_start = models.IntegerField(blank=True, null=True, default=None)
    ship_current = models.IntegerField(blank=True, null=True, default=None)
    ship_end = models.IntegerField(blank=True, null=True, default=None)
    sscc_start = models.IntegerField(blank=True, null=True, default=None)
    sscc_current = models.IntegerField(blank=True, null=True, default=None)
    sscc_end = models.IntegerField(blank=True, null=True, default=None)
    created_at = models.DateTimeField(
        verbose_name=_("Created Timestamp"),
        null=True,
        blank=True,
        auto_now_add=True,
    )
    updated_at = models.DateTimeField(
        verbose_name=_("Modified Timestamp"),
        null=True,
        blank=True,
        auto_now=True,
    )

    class Meta:
        db_table = "ship_sscc_ranges"
