import uuid
import logging
from base64 import b64encode
from datetime import datetime
from django.db import transaction
from rest_framework.exceptions import ValidationError
from api.common import time as dme_time_lib, constants as dme_constants
from api.models import (
    Bookings,
    Booking_lines,
    Client_warehouses,
    BOK_2_lines,
    BOK_1_headers,
)

from django.conf import settings

from api.clients.biopak.constants import FTP_INFO
from api.common import sftp, trace_error
from api.serializers_client import *

logger = logging.getLogger(__name__)


def reprint_label(params, client):
    """
    get label(already built)
    """
    LOG_ID = "[REPRINT BioPak]"
    b_clientReference_RA_Numbers = params.get("clientReferences")
    item_description = params.get("itemDescription")
    labels = []

    if not b_clientReference_RA_Numbers:
        message = "'clientReferences' is required."
        raise ValidationError(message)
    else:
        b_clientReference_RA_Numbers = b_clientReference_RA_Numbers.split(",")

    bookings = Bookings.objects.filter(
        b_clientReference_RA_Numbers__in=b_clientReference_RA_Numbers,
        b_client_name=client.company_name,
    ).exclude(b_status="Closed")

    pk_booking_ids = [booking.pk_booking_id for booking in bookings]
    lines = Booking_lines.objects.filter(fk_booking_id__in=pk_booking_ids)

    if bookings[0].vx_freight_provider == "Team Global Express":
        if bookings[0].b_client_warehouse_code in ["BIO - HAZ", "BIO - RIC"]:
            lines = lines.filter(packed_status=Booking_lines.SCANNED_PACK)
        else:
            lines = lines.filter(packed_status=Booking_lines.ORIGINAL)
    elif bookings[0].vx_freight_provider == "Startrack":
        lines = lines.filter(packed_status=Booking_lines.SCANNED_PACK)

    if item_description:
        lines = lines.filter(e_item=item_description)

    for booking in bookings:
        booking_lines = []
        label = {"reference": booking.b_clientReference_RA_Numbers}

        # Get each line's label
        label_lines = []
        for line in lines:
            if booking.pk_booking_id == line.fk_booking_id:
                if booking.vx_freight_provider == "Team Global Express":
                    filename = (
                        booking.pu_Address_State
                        + "_"
                        + str(booking.b_bookingID_Visual)
                        + "_"
                        + str(line.pk)
                        + ".pdf"
                    )
                elif booking.vx_freight_provider == "Startrack":
                    filename = (
                        booking.pu_Address_State
                        + "_"
                        + str(booking.b_bookingID_Visual)
                        + "_"
                        + str(line.sscc)
                        + ".pdf"
                    )
                label_url = f"{settings.STATIC_PUBLIC}/pdfs/{booking.vx_freight_provider.lower()}_au/{filename}"
                with open(label_url, "rb") as file:
                    pdf_data = str(b64encode(file.read()))[2:-1]
                label_line = {"itemid": line.e_item, "label_base64": pdf_data}
                label_lines.append(label_line)

        if not item_description:
            # Get merged label
            label_url = f"{settings.STATIC_PUBLIC}/pdfs/{booking.vx_freight_provider.lower()}_au/DME{booking.b_bookingID_Visual}.pdf"
            with open(label_url, "rb") as file:
                pdf_data = str(b64encode(file.read()))[2:-1]
            label["merged"] = pdf_data

        label["lines"] = label_lines
        labels.append(label)

    return {"success": True, "labels": labels}


def _csv_write(fp_path, f):
    pass


def update_biopak(booking, fp, status, event_at):
    csv_name = str(datetime.now().strftime("%d-%m-%Y__%H_%M_%S")) + ".csv"
    f = open(CSV_DIR + csv_name, "w")
    csv_write(fpath, f)
    f.close()

    sftp.upload_sftp(
        FTP_INFO["host"],
        FTP_INFO["username"],
        FTP_INFO["password"],
        FTP_INFO["sftp_filepath"],
        FTP_INFO["local_filepath"],
        FTP_INFO["local_filepath_archive"],
        csv_name,
    )


def push_boks(payload, client):
    """
    PUSH api (bok_1, bok_2, bok_3)
    """
    LOG_ID = "[PB Standard]"  # PB - PUSH BOKS
    bok_1 = payload["booking"]
    bok_1["pk_header_id"] = str(uuid.uuid4())
    bok_2s = payload["booking_lines"]

    ffl_number = bok_1["b_000_1_b_clientReference_RA_Numbers"]
    bok_1_count = BOK_1_headers.objects.filter(
        b_000_1_b_clientReference_RA_Numbers=ffl_number
    ).count()
    if bok_1_count > 0:
        res_json = {"success": False, "message": "FFL number is duplicated"}
        return res_json

    with transaction.atomic():
        # Save bok_1
        bok_1["fk_client_id"] = client.dme_account_num
        bok_1["x_booking_Created_With"] = "DME PUSH API"
        bok_1["success"] = dme_constants.BOK_SUCCESS_2  # Default success code

        if client.company_name == "Seaway-Tempo-Aldi":  # Seaway-Tempo-Aldi
            bok_1["b_001_b_freight_provider"] = "DHL"
        else:
            # BioPak
            warehouse = Client_warehouses.objects.get(
                client_warehouse_code=bok_1["b_client_warehouse_code"]
            )
            bok_1["client_booking_id"] = bok_1["pk_header_id"]
            bok_1["fk_client_warehouse"] = warehouse.pk_id_client_warehouses
            bok_1["b_clientPU_Warehouse"] = warehouse.name
            bok_1["b_client_warehouse_code"] = warehouse.client_warehouse_code

        if not bok_1.get("b_054_b_del_company"):
            bok_1["b_054_b_del_company"] = bok_1["b_061_b_del_contact_full_name"]

        bok_1["b_057_b_del_address_state"] = bok_1["b_057_b_del_address_state"].upper()
        bok_1["b_031_b_pu_address_state"] = bok_1["b_031_b_pu_address_state"].upper()

        bok_1_serializer = BOK_1_Serializer(data=bok_1)
        if not bok_1_serializer.is_valid():
            message = f"Serialiser Error - {bok_1_serializer.errors}"
            logger.info(f"@8811 {LOG_ID} {message}")
            raise Exception(message)

        # Save bok_2s
        for index, bok_2 in enumerate(bok_2s):
            _bok_2 = bok_2["booking_line"]
            _bok_2["fk_header_id"] = bok_1["pk_header_id"]
            _bok_2["v_client_pk_consigment_num"] = bok_1["pk_header_id"]
            _bok_2["pk_booking_lines_id"] = str(uuid.uuid1())
            _bok_2["success"] = bok_1["success"]
            _bok_2["b_093_packed_status"] = BOK_2_lines.ORIGINAL
            l_001 = _bok_2.get("l_001_type_of_packaging") or "Carton"
            _bok_2["l_001_type_of_packaging"] = l_001

            bok_2_serializer = BOK_2_Serializer(data=_bok_2)
            if bok_2_serializer.is_valid():
                bok_2_serializer.save()
            else:
                message = f"Serialiser Error - {bok_2_serializer.errors}"
                logger.info(f"@8821 {LOG_ID} {message}")
                raise Exception(message)

            # Save bok_3s
            if not "booking_lines_data" in bok_2:
                continue

            bok_3s = bok_2["booking_lines_data"]
            for bok_3 in bok_3s:
                bok_3["fk_header_id"] = bok_1["pk_header_id"]
                bok_3["fk_booking_lines_id"] = _bok_2["pk_booking_lines_id"]
                bok_3["v_client_pk_consigment_num"] = bok_1["pk_header_id"]
                bok_3["success"] = bok_1["success"]

                bok_3_serializer = BOK_3_Serializer(data=bok_3)
                if bok_3_serializer.is_valid():
                    bok_3_serializer.save()
                else:
                    message = f"Serialiser Error - {bok_2_serializer.errors}"
                    logger.info(f"@8831 {LOG_ID} {message}")
                    raise Exception(message)

        bok_1_obj = bok_1_serializer.save()

    res_json = {"success": True, "message": "Push success!"}
    return res_json
