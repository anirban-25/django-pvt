from django.db.models import Q
from datetime import datetime, date, timedelta

from api.common.time import convert_to_UTC_tz, TIME_DIFFERENCE


def replace_operator(keyword):
    keyword = keyword.replace("or", "|")
    keyword = keyword.replace("||", "|")
    keyword = keyword.replace("and", "&")
    keyword = keyword.replace("&&", "&")

    return keyword


def _build_query(keyword, field_name, search_type):
    q = Q()

    if search_type == "isnull":
        filter1 = field_name + "__" + search_type
        filter2 = field_name + "__" + "exact"
        q1 = Q(**{filter1: True})
        q2 = Q(**{filter2: ""})
        q = q1 | q2
    elif search_type == "iregex":
        filter = field_name + "__" + search_type
        keyword = keyword.replace("*", "[a-zA-Z0-9-]+")
        if "|" in keyword:
            for key in keyword.split("|"):
                q1 = Q()
                if "&" in key:
                    for k in key.split("&"):
                        q1 &= Q(**{filter: k.strip()})
                    q |= q1
                else:
                    q1 = Q(**{filter: key.strip()})
                    q |= q1
        elif "&" in keyword:
            for key in keyword.split("&"):
                q &= Q(**{filter: key.strip()})
        else:
            q &= Q(**{filter: keyword.strip()})
    elif search_type == "icontains":
        filter = field_name
        if "|" in keyword:
            for key in keyword.split("|"):
                q1 = Q()
                if "&" in key:
                    for k in key.split("&"):
                        q1 &= Q(**{filter: k.strip()})
                    q |= q1
                else:
                    q1 = Q(**{filter: key.strip()})
                    q |= q1
        elif "&" in keyword:
            for key in keyword.split("&"):
                q &= Q(**{filter: key.strip()})
        else:
            q &= Q(**{filter: keyword.strip()})

    return q


def filter_bookings_by_columns(queryset, column_filters, active_tab_index):
    # Column filter

    field_names = [
        "b_bookingID_Visual",
        "b_client_name",
        "b_client_name_sub",
        "b_booking_Category",
        "puCompany",
        "pu_Address_Suburb",
        "pu_Address_State",
        "pu_Comm_Booking_Communicate_Via",
        "deToCompanyName",
        "de_To_Address_Suburb",
        "de_To_Address_State",
        "de_To_Comm_Delivery_Communicate_Via",
        "b_clientReference_RA_Numbers",
        "vx_freight_provider",
        "vx_serviceName",
        "v_FPBookingNumber",
        "b_status",
        "b_status_API",
        "s_05_LatestPickUpDateTimeFinal",
        "s_06_LatestDeliveryDateTimeFinal",
        "s_20_Actual_Pickup_TimeStamp",
        "s_21_Actual_Delivery_TimeStamp",
        "b_client_order_num",
        "b_client_sales_inv_num",
        "dme_status_detail",
        "dme_status_action",
        "z_calculated_ETA",
        "de_to_PickUp_Instructions_Address",
        "b_booking_project",
        "de_Deliver_By_Date",
        "b_project_due_date",
        "b_project_due_date",
        "delivery_booking",
    ]

    for field_name in field_names:
        keyword = column_filters.get(field_name)

        if keyword:
            keyword = replace_operator(keyword)
            if "<>''" in keyword or '<>""' in keyword:
                queryset = queryset.exclude(_build_query(keyword, field_name, "isnull"))
            elif (
                "=''" in keyword
                or '=""' in keyword
                or "''" in keyword
                or '""' in keyword
            ):
                queryset = queryset.filter(_build_query(keyword, field_name, "isnull"))
            elif "<>" in keyword and "*" not in keyword:
                queryset = queryset.exclude(
                    _build_query(keyword[2:], field_name, "icontains")
                )
            elif "<>" in keyword and "*" in keyword:
                queryset = queryset.exclude(
                    _build_query(keyword[2:], field_name, "iregex")
                )
            elif "=" in keyword and "*" in keyword:
                queryset = queryset.filter(
                    _build_query(keyword[1:], field_name, "iregex")
                )
            else:
                queryset = queryset.filter(
                    _build_query(keyword, field_name, "icontains")
                )

    try:
        keyword = column_filters["b_dateBookedDate"]  # MMDDYY-MMDDYY

        if keyword and "-" in keyword:
            start_date_str = keyword.split("-")[0]
            end_date_str = keyword.split("-")[1]
            start_date = datetime.strptime(start_date_str, "%d/%m/%y")
            end_date = datetime.strptime(end_date_str, "%d/%m/%y")
            end_date = end_date.replace(hour=23, minute=59, second=59)
            queryset = queryset.filter(
                b_dateBookedDate__range=(
                    convert_to_UTC_tz(start_date),
                    convert_to_UTC_tz(end_date),
                )
            )
        elif keyword and not "-" in keyword:
            date = datetime.strptime(keyword, "%d/%m/%y")
            queryset = queryset.filter(b_dateBookedDate=date)
    except KeyError:
        keyword = ""

    try:
        keyword = column_filters["puPickUpAvailFrom_Date"]  # MMDDYY-MMDDYY

        if keyword and "-" in keyword:
            start_date_str = keyword.split("-")[0]
            end_date_str = keyword.split("-")[1]
            start_date = datetime.strptime(start_date_str, "%d/%m/%y")
            end_date = datetime.strptime(end_date_str, "%d/%m/%y")
            end_date = end_date.replace(hour=23, minute=59, second=59)
            queryset = queryset.filter(
                puPickUpAvailFrom_Date__range=(start_date, end_date)
            )
        elif keyword and not "-" in keyword:
            date = datetime.strptime(keyword, "%d/%m/%y")
            queryset = queryset.filter(puPickUpAvailFrom_Date=date)
    except KeyError:
        keyword = ""

    try:
        keyword = column_filters["manifest_timestamp"]  # MMDDYY-MMDDYY

        if keyword and "-" in keyword:
            start_date_str = keyword.split("-")[0]
            end_date_str = keyword.split("-")[1]
            start_date = datetime.strptime(start_date_str, "%d/%m/%y")
            end_date = datetime.strptime(end_date_str, "%d/%m/%y")
            end_date = end_date.replace(hour=23, minute=59, second=59)
            start_date = start_date - timedelta(hours=TIME_DIFFERENCE)
            end_date = end_date - timedelta(hours=TIME_DIFFERENCE)
            queryset = queryset.filter(manifest_timestamp__range=(start_date, end_date))
        elif keyword and not "-" in keyword:
            date = datetime.strptime(keyword, "%d/%m/%y")
            queryset = queryset.filter(manifest_timestamp=date)
    except KeyError:
        keyword = ""

    try:
        keyword = column_filters["pu_Address_PostalCode"]

        if keyword and "-" in keyword:
            start_postal_code = keyword.split("-")[0]
            end_postal_code = keyword.split("-")[1]
            queryset = queryset.filter(
                pu_Address_PostalCode__gte=start_postal_code,
                pu_Address_PostalCode__lt=end_postal_code,
            )
        elif keyword and not "-" in keyword:
            queryset = queryset.filter(pu_Address_PostalCode__icontains=keyword)
    except KeyError:
        keyword = ""

    try:
        keyword = column_filters["de_To_Address_PostalCode"]

        if keyword and "-" in keyword:
            start_postal_code = keyword.split("-")[0]
            end_postal_code = keyword.split("-")[1]
            queryset = queryset.filter(
                de_To_Address_PostalCode__gte=start_postal_code,
                de_To_Address_PostalCode__lt=end_postal_code,
            )
        elif keyword and not "-" in keyword:
            queryset = queryset.filter(de_To_Address_PostalCode__icontains=keyword)
    except KeyError:
        keyword = ""

    keyword = column_filters.get("b_status_category")
    if keyword:
        queryset = queryset.filter(b_status_category__icontains=keyword)

    if not keyword and active_tab_index == 6:
        queryset = queryset.filter(b_status_category__in=["Booked", "Transit"])

    return queryset
