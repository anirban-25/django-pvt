# bok tables success status
BOK_SUCCESS_1 = 1  # Already mapped
BOK_SUCCESS_2 = 2  # Ready for mapping
BOK_SUCCESS_3 = 3  # Getting quotes...
BOK_SUCCESS_4 = 4  # Ordered and waiting pick up signal from Warehouse
BOK_SUCCESS_5 = 5  # Imported / Integrated

# API KEY for 8x8.com
EIGHT_EIGHT_API_KEY = "kZrvN9q37ryQ40tojTuEZMTdlti1EcF7ha4zqyV8"

# AU State Abbreviation
AU_STATES = [
    "New South Wales",
    "Northern Territory",
    "Queensland",
    "South Australia",
    "Tasmania",
    "Victoria",
    "Western Australia",
]
AU_STATE_ABBRS = ["NSW", "NT", "QLD", "SA", "TAS", "VIC", "WA", "ACT"]

# Package types
PALLETS = ["PALLET", "PLT", "PAL"]
CARTONS = ["CARTON", "CTN"]
SKIDS = ["SKID"]
ROLLS = ["ROLL", "ROLLS"]
PACKETS = ["PACKET", "PACKETS", "PKT"]

# Booking fields for AllBookings table
BOOKING_FIELDS_4_ALLBOOKING_TABLE = [
    "id",
    "pk_booking_id",
    "b_bookingID_Visual",
    "puCompany",
    "pu_Address_Street_1",
    "pu_Address_street_2",
    "pu_Address_PostalCode",
    "pu_Address_Suburb",
    "pu_Address_Country",
    "de_To_Address_Street_1",
    "de_To_Address_Street_2",
    "de_To_Address_PostalCode",
    "de_To_Address_Suburb",
    "de_To_Address_Country",
    "deToCompanyName",
    "v_FPBookingNumber",
    "vx_freight_provider",
    "vx_serviceName",
    "z_label_url",
    "z_pod_url",
    "z_pod_signed_url",
    "z_manifest_url",
    "pu_Address_State",
    "de_To_Address_State",
    "b_status",
    "b_status_category",
    "b_dateBookedDate",
    "s_06_Latest_Delivery_Date_TimeSet",
    "s_06_Latest_Delivery_Date_Time_Override",
    "s_20_Actual_Pickup_TimeStamp",
    "s_21_Actual_Delivery_TimeStamp",
    "b_client_name",
    "fk_client_warehouse",
    "b_client_warehouse_code",
    "b_clientPU_Warehouse",
    "booking_Created_For",
    "b_clientReference_RA_Numbers",
    "de_to_PickUp_Instructions_Address",
    "b_dateBookedDate",
    "z_lock_status",
    "dme_status_detail",
    "dme_status_action",
    "puPickUpAvailFrom_Date",
    "pu_PickUp_By_Date",
    "de_Deliver_From_Date",
    "de_Deliver_By_Date",
    "b_client_order_num",
    "b_client_sales_inv_num",
    "b_client_name_sub",
    "x_manual_booked_flag",
    "b_fp_qty_delivered",
    "manifest_timestamp",
    "b_booking_project",
    "z_calculated_ETA",
    "b_project_due_date",
    "delivery_booking",
    "fp_store_event_date",
    "fp_store_event_time",
    "fp_store_event_desc",
    "fp_received_date_time",
    "b_given_to_transport_date_time",
    "z_downloaded_shipping_label_timestamp",
    "api_booking_quote",
    "b_status_API",
    "b_error_Capture",
    "kf_client_id",
    "z_locked_status_time",
    "b_booking_Priority",
    "b_booking_Category",
    "b_promo_code",
    "pu_Address_Type",
    "de_To_AddressType",
    "vx_fp_order_id",
]
