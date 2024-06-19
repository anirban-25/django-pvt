import os
import logging
import xml.etree.ElementTree as xml
from datetime import datetime, timedelta

from django.conf import settings

from api.models import Bookings, Booking_lines, Client_warehouses, Client_FP
from api.fp_apis.constants import FP_CREDENTIALS
from api.helpers.line import is_carton, is_pallet
from api.helpers.cubic import get_cubic_meter

logger = logging.getLogger(__name__)


def get_account_detail(booking):
    account_detail = {}

    # Aberdeen Paper
    if booking.kf_client_id == "4ac9d3ee-2558-4475-bdbb-9d9405279e81":
        return {
            "accountCode": "31989",
            "accountKey": "78C751EF-8A13-4616-88DD-E0B5E224EE61",
            "accountPassword": "",
            "SenderSIteID": "0",  # Always 0 unless specified by DFE
        }
    else:
        return None


def gen_consignment(booking):
    from api.clients.operations.index import get_client

    # Check from Booking
    if booking.v_FPBookingNumber:
        return booking.v_FPBookingNumber

    client = get_client(None, booking.kf_client_id)
    client_fp = Client_FP.objects.get(client=client, fp_id=88)
    client_fp.connote_number += 1
    client_fp.save()

    sender_account_number = FP_CREDENTIALS["direct freight"][
        booking.b_client_name.lower()
    ]["live_0"]["accountCode"]
    site_indicator = "1"
    sequence_no = str(client_fp.connote_number).zfill(7)

    # Save on Booking
    booking.v_FPBookingNumber = f"{sender_account_number}{site_indicator}{sequence_no}"
    booking.save()

    return booking.v_FPBookingNumber


def build_book_xml(booking):
    from api.fp_apis.utils import _convert_UOM

    LOG_ID = "[DF BOOK XML]"
    logger.info(f"{LOG_ID} Booking ID: {booking.pk}")
    credential = FP_CREDENTIALS["direct freight"][booking.b_client_name.lower()]
    sender_account_number = credential["live_0"]["accountCode"]
    site_id = credential["live_0"]["SenderSIteID"]
    v_FPBookingNumber = gen_consignment(booking)

    original_lines = []
    scanned_lines = []
    lines = []
    lines = Booking_lines.objects.filter(
        fk_booking_id=booking.pk_booking_id, is_deleted=False
    )

    for line in lines:
        if line.packed_status == "original":
            original_lines.append(line)
        elif line.packed_status == "scanned":
            scanned_lines.append(line)

    lines = scanned_lines or original_lines

    # start check if xmls folder exists
    if settings.ENV == "prod":  # Production
        local_filepath = "/opt/s3_private/xmls/direct_freight_au/"
        local_filepath_dup = (
            "/opt/s3_private/xmls/direct_freight_au/archive/"
            + str(datetime.now().strftime("%Y_%m_%d"))
            + "/"
        )
    else:
        local_filepath = "./static/xmls/direct_freight_au/"
        local_filepath_dup = (
            "./static/xmls/direct_freight_au/archive/"
            + str(datetime.now().strftime("%Y_%m_%d"))
            + "/"
        )

    if not os.path.exists(local_filepath):
        os.makedirs(local_filepath)
    # end check if xmls folder exists

    # Pre data
    filename = f"Manifest_{sender_account_number}_{datetime.now().strftime('%Y%m%d%H%M')}_{booking.v_FPBookingNumber}.xml"
    special_instruction = ""
    if booking.de_to_PickUp_Instructions_Address:
        special_instruction = f"{booking.de_to_PickUp_Instructions_Address}"
    if booking.de_to_Pick_Up_Instructions_Contact:
        special_instruction += f" {booking.de_to_Pick_Up_Instructions_Contact}"

    # start formatting xml
    NewDataSet = xml.Element("NewDataSet")

    Table = xml.Element("Table")
    ReceiverName = xml.SubElement(Table, "ReceiverName")
    ReceiverName.text = booking.deToCompanyName
    ReceiverAddress1 = xml.SubElement(Table, "ReceiverAddress1")
    ReceiverAddress1.text = booking.de_To_Address_Street_1
    ReceiverAddress2 = xml.SubElement(Table, "ReceiverAddress2")
    ReceiverAddress2.text = booking.de_To_Address_Street_2 or ""
    ReceiverAddress3 = xml.SubElement(Table, "ReceiverAddress3")
    ReceiverAddress3.text = ""
    ReceiverCity = xml.SubElement(Table, "ReceiverCity")
    ReceiverCity.text = booking.de_To_Address_Suburb.upper()
    ReceiverState = xml.SubElement(Table, "ReceiverState")
    ReceiverState.text = booking.de_To_Address_State.upper()
    ReceiverPostcode = xml.SubElement(Table, "ReceiverPostcode")
    ReceiverPostcode.text = booking.de_To_Address_PostalCode.upper()
    AccountNumber = xml.SubElement(Table, "AccountNumber")
    AccountNumber.text = sender_account_number
    SiteID = xml.SubElement(Table, "SiteID")
    SiteID.text = site_id
    Connote = xml.SubElement(Table, "Connote")
    Connote.text = v_FPBookingNumber
    Special = xml.SubElement(Table, "Special")
    Special.text = special_instruction
    ConnoteDate = xml.SubElement(Table, "ConnoteDate")
    ConnoteDate.text = datetime.now().strftime("%Y-%m-%dT%H:%M:%S%Z")
    Items = xml.SubElement(Table, "Items")
    Items.text = ""  # Leave Blank
    Pallets = xml.SubElement(Table, "Pallets")
    Pallets.text = ""  # Leave Blank
    KGS = xml.SubElement(Table, "KGS")
    KGS.text = ""  # Leave Blank
    Cubic = xml.SubElement(Table, "Cubic")
    Cubic.text = ""  # Leave Blank
    Service = xml.SubElement(Table, "Service")
    Service.text = "ATL" if booking.opt_authority_to_leave else ""
    CustomerReference = xml.SubElement(Table, "CustomerReference")
    CustomerReference.text = booking.b_clientReference_RA_Numbers
    StartDate = xml.SubElement(Table, "StartDate")
    StartDate.text = (datetime.now() + timedelta(days=5)).strftime("%Y-%m-%dT00:00:00")
    StopDate = xml.SubElement(Table, "StopDate")
    StopDate.text = ""
    Class = xml.SubElement(Table, "Class")
    Class.text = ""  # Leave Blank
    InsuranceAmount = xml.SubElement(Table, "InsuranceAmount")
    InsuranceAmount.text = "0.00"  # Set to '0.00'
    DangerousGoods = xml.SubElement(Table, "DangerousGoods")
    DangerousGoods.text = "False"
    ReceiverContactName = xml.SubElement(Table, "ReceiverContactName")
    ReceiverContactName.text = booking.de_to_Contact_F_LName
    ReceiverPhone = xml.SubElement(Table, "ReceiverPhone")
    ReceiverPhone.text = booking.de_to_Phone_Main or booking.de_to_Phone_Mobile
    ReceiverEmail = xml.SubElement(Table, "ReceiverEmail")
    ReceiverEmail.text = booking.de_Email
    NewDataSet.append(Table)

    for index, line in enumerate(lines):
        fp_name = "Direct Freight"

        # Added on 2023-12-14
        if booking.kf_client_id == "4ac9d3ee-2558-4475-bdbb-9d9405279e81":
            line.e_dimLength = 10
            line.e_dimWidth = 10
            line.e_dimHeight = 10
            line.e_weightPerEach = 1
            line.e_dimUOM = "cm"
            line.e_weightUOM = "kg"

        weight = _convert_UOM(line.e_weightPerEach, line.e_weightUOM, "weight", fp_name)
        length = _convert_UOM(line.e_dimLength, line.e_dimUOM, "dim", fp_name)
        width = _convert_UOM(line.e_dimWidth, line.e_dimUOM, "dim", fp_name)
        height = _convert_UOM(line.e_dimHeight, line.e_dimUOM, "dim", fp_name)
        cubic = round(
            get_cubic_meter(
                line.e_dimLength,
                line.e_dimWidth,
                line.e_dimHeight,
                line.e_dimUOM,
                1,
            ),
            3,
        )

        Table1 = xml.Element("Table1")
        ConNoteDetailsID = xml.SubElement(Table1, "ConNoteDetailsID")
        ConNoteDetailsID.text = str(index + 1)
        Connote = xml.SubElement(Table1, "Connote")
        Connote.text = v_FPBookingNumber
        SenderReference = xml.SubElement(Table1, "SenderReference")
        SenderReference.text = str(line.pk)
        PackageType = xml.SubElement(Table1, "PackageType")
        PackageType.text = (
            "CARTON" if not is_pallet(line.e_type_of_packaging) else "PALLET"
        )
        Items = xml.SubElement(Table1, "Items")
        Items.text = str(line.e_qty)
        KGS = xml.SubElement(Table1, "KGS")
        KGS.text = str(weight)
        Length = xml.SubElement(Table1, "Length")
        Length.text = str(length)
        Width = xml.SubElement(Table1, "Width")
        Width.text = str(width)
        Height = xml.SubElement(Table1, "Height")
        Height.text = str(height)
        Quantity = xml.SubElement(Table1, "Quantity")
        Quantity.text = str(line.e_qty)
        Cubic = xml.SubElement(Table1, "Cubic")
        Cubic.text = str(cubic)
        Type = xml.SubElement(Table1, "Type")
        Type.text = "ITEM" if not is_pallet(line.e_type_of_packaging) else "PALLET"
        NewDataSet.append(Table1)

    track_code = 0
    for line_index, line in enumerate(lines):
        for i in range(line.e_qty):
            Table2 = xml.Element("Table2")
            Connote = xml.SubElement(Table2, "Connote")
            Connote.text = v_FPBookingNumber
            ConNoteDetailsID = xml.SubElement(Table2, "ConNoteDetailsID")
            ConNoteDetailsID.text = str(line_index + 1)
            track_code += 1
            LabelTrackCode = xml.SubElement(Table2, "LabelTrackCode")
            LabelTrackCode.text = f"{v_FPBookingNumber}{str(track_code).zfill(3)}"
            NewDataSet.append(Table2)

    # start writting data into xml files
    tree = xml.ElementTree(NewDataSet)
    with open(local_filepath + filename, "wb") as fh:
        tree.write(fh, encoding="UTF-8", xml_declaration=False)

    logger.info(f"{LOG_ID} XML completed: {local_filepath + filename}")
    return True
