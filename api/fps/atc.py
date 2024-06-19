# Need to split properly to each FP like what we did for `Direct Frieght`


# def build_xml(booking_ids, vx_freight_provider, one_manifest_file):
#     try:
#         mysqlcon = pymysql.connect(
#             host=DB_HOST,
#             port=DB_PORT,
#             user=DB_USER,
#             password=DB_PASS,
#             db=DB_NAME,
#             charset="utf8mb4",
#             cursorclass=pymysql.cursors.DictCursor,
#         )
#     except:
#         exit(1)
#     mycursor = mysqlcon.cursor()

#     bookings = get_available_bookings(mysqlcon, booking_ids)
#     booked_list = get_booked_list(bookings)

#     if len(booked_list) > 0:
#         return booked_list

#     if vx_freight_provider.lower() == "allied":
#         # start check if xmls folder exists
#         if production:
#             local_filepath = "/opt/s3_private/xmls/allied_au/"
#             local_filepath_dup = (
#                 "/opt/s3_private/xmls/allied_au/archive/"
#                 + str(datetime.now().strftime("%Y_%m_%d"))
#                 + "/"
#             )
#         else:
#             local_filepath = "./static/xmls/allied_au/"
#             local_filepath_dup = (
#                 "./static/xmls/allied_au/archive/"
#                 + str(datetime.now().strftime("%Y_%m_%d"))
#                 + "/"
#             )

#         if not os.path.exists(local_filepath):
#             os.makedirs(local_filepath)
#         # end check if xmls folder exists

#         i = 1
#         for booking in bookings:
#             try:
#                 # start db query for fetching data from dme_booking_lines table
#                 sql1 = "SELECT pk_lines_id, e_qty, e_item_type, e_item, e_dimWidth, e_dimLength, e_dimHeight, e_Total_KG_weight \
#                         FROM dme_booking_lines \
#                         WHERE fk_booking_id = %s"
#                 adr1 = (booking["pk_booking_id"],)
#                 mycursor.execute(sql1, adr1)
#                 booking_lines = mycursor.fetchall()

#                 # start calculate total item quantity and total item weight
#                 totalQty = 0
#                 totalWght = 0
#                 for booking_line in booking_lines:
#                     totalQty = totalQty + booking_line["e_qty"]
#                     totalWght = totalWght + booking_line["e_Total_KG_weight"]
#                 # start calculate total item quantity and total item weight

#                 # start xml file name using naming convention
#                 date = (
#                     datetime.now().strftime("%Y%m%d")
#                     + "_"
#                     + datetime.now().strftime("%H%M%S")
#                 )
#                 filename = "AL_HANALT_" + date + "_" + str(i) + ".xml"
#                 i += 1
#                 # end xml file name using naming convention

#                 # start formatting xml file and putting data from db tables
#                 root = xml.Element(
#                     "AlTransportData",
#                     **{"xmlns:xsi": "http://www.w3.org/2001/XMLSchema-instance"},
#                 )
#                 consignmentHeader = xml.Element("ConsignmentHeader")
#                 root.append(consignmentHeader)
#                 chargeAccount = xml.SubElement(consignmentHeader, "ChargeAccount")
#                 chargeAccount.text = "HANALT"
#                 senderName = xml.SubElement(consignmentHeader, "SenderName")
#                 senderName.text = "Hankook"
#                 senderAddressLine1 = xml.SubElement(
#                     consignmentHeader, "SenderAddressLine1"
#                 )
#                 senderAddressLine1.text = booking["pu_Address_Street_1"]
#                 senderLocality = xml.SubElement(consignmentHeader, "SenderLocality")
#                 senderLocality.text = booking["pu_Address_Suburb"]
#                 senderState = xml.SubElement(consignmentHeader, "SenderState")
#                 senderState.text = booking["pu_Address_State"]
#                 senderPostcode = xml.SubElement(consignmentHeader, "SenderPostcode")
#                 senderPostcode.text = booking["pu_Address_PostalCode"]

#                 companyName = booking["deToCompanyName"].replace("<", "")
#                 companyName = companyName.replace(">", "")
#                 companyName = companyName.replace('"', "")
#                 companyName = companyName.replace("'", "")
#                 companyName = companyName.replace("&", "and")

#                 consignmentShipments = xml.Element("ConsignmentShipments")
#                 root.append(consignmentShipments)
#                 consignmentShipment = xml.SubElement(
#                     consignmentShipments, "ConsignmentShipment"
#                 )
#                 ConsignmentNumber = xml.SubElement(
#                     consignmentShipment, "ConsignmentNumber"
#                 )
#                 ConsignmentNumber.text = gen_consignment_num(
#                     vx_freight_provider, booking["b_bookingID_Visual"]
#                 )
#                 DespatchDate = xml.SubElement(consignmentShipment, "DespatchDate")
#                 DespatchDate.text = str(booking["puPickUpAvailFrom_Date"])
#                 CarrierService = xml.SubElement(consignmentShipment, "CarrierService")
#                 CarrierService.text = booking["vx_serviceName"]
#                 totalQuantity = xml.SubElement(consignmentShipment, "totalQuantity")
#                 totalQuantity.text = str(totalQty)
#                 totalWeight = xml.SubElement(consignmentShipment, "totalWeight")
#                 totalWeight.text = str(totalWght)
#                 ReceiverName = xml.SubElement(consignmentShipment, "ReceiverName")
#                 ReceiverName.text = companyName
#                 ReceiverAddressLine1 = xml.SubElement(
#                     consignmentShipment, "ReceiverAddressLine1"
#                 )
#                 ReceiverAddressLine1.text = booking["de_To_Address_Street_1"]
#                 ReceiverLocality = xml.SubElement(
#                     consignmentShipment, "ReceiverLocality"
#                 )
#                 ReceiverLocality.text = booking["de_To_Address_Suburb"]
#                 ReceiverState = xml.SubElement(consignmentShipment, "ReceiverState")
#                 ReceiverState.text = booking["de_To_Address_State"]
#                 ReceiverPostcode = xml.SubElement(
#                     consignmentShipment, "ReceiverPostcode"
#                 )
#                 ReceiverPostcode.text = booking["de_To_Address_PostalCode"]
#                 ItemsShipment = xml.SubElement(consignmentShipment, "ItemsShipment")

#                 for booking_line in booking_lines:
#                     Item = xml.SubElement(ItemsShipment, "Item")
#                     Quantity = xml.SubElement(Item, "Quantity")
#                     Quantity.text = str(booking_line["e_qty"])
#                     ItemType = xml.SubElement(Item, "ItemType")
#                     ItemType.text = get_item_type(booking_line["e_item_type"])
#                     ItemDescription = xml.SubElement(Item, "ItemDescription")
#                     ItemDescription.text = booking_line["e_item"]

#                     Width = xml.SubElement(Item, "Width")
#                     if (
#                         booking_line["e_dimWidth"] == None
#                         or booking_line["e_dimWidth"] == ""
#                         or booking_line["e_dimWidth"] == 0
#                     ):
#                         Width.text = str("1")

#                         sql2 = "UPDATE dme_booking_lines set e_dimWidth = %s WHERE pk_lines_id = %s"
#                         adr2 = (1, booking_line["pk_lines_id"])
#                         mycursor.execute(sql2, adr2)
#                         mysqlcon.commit()
#                     else:
#                         Width.text = str(booking_line["e_dimWidth"])

#                     Length = xml.SubElement(Item, "Length")
#                     if (
#                         booking_line["e_dimLength"] == None
#                         or booking_line["e_dimLength"] == ""
#                         or booking_line["e_dimLength"] == 0
#                     ):
#                         Length.text = str("1")

#                         sql2 = "UPDATE dme_booking_lines set e_dimLength = %s WHERE pk_lines_id = %s"
#                         adr2 = (1, booking_line["pk_lines_id"])
#                         mycursor.execute(sql2, adr2)
#                         mysqlcon.commit()
#                     else:
#                         Length.text = str(booking_line["e_dimLength"])

#                     Height = xml.SubElement(Item, "Height")
#                     if (
#                         booking_line["e_dimHeight"] == None
#                         or booking_line["e_dimHeight"] == ""
#                         or booking_line["e_dimHeight"] == 0
#                     ):
#                         Height.text = str("1")

#                         sql2 = "UPDATE dme_booking_lines set e_dimHeight = %s WHERE pk_lines_id = %s"
#                         adr2 = (1, booking_line["pk_lines_id"])
#                         mycursor.execute(sql2, adr2)
#                         mysqlcon.commit()
#                     else:
#                         Height.text = str(booking_line["e_dimHeight"])

#                     DeadWeight = xml.SubElement(Item, "DeadWeight")
#                     DeadWeight.text = (
#                         format(
#                             booking_line["e_Total_KG_weight"] / booking_line["e_qty"],
#                             ".2f",
#                         )
#                         if booking_line["e_qty"] > 0
#                         else 0
#                     )

#                     SSCCs = xml.SubElement(Item, "SSCCs")
#                     SSCC = xml.SubElement(SSCCs, "SSCC")
#                     SSCC.text = booking["pk_booking_id"]
#                 # end formatting xml file and putting data from db tables

#                 # start writting data into xml files
#                 tree = xml.ElementTree(root)
#                 with open(local_filepath + filename, "wb") as fh:
#                     tree.write(fh, encoding="UTF-8", xml_declaration=True)

#                 # start copying xml files to sftp server
#                 # sftp_filepath = "/home/NSW/delvme.external/indata/"
#                 # cnopts = pysftp.CnOpts()
#                 # cnopts.hostkeys = None
#                 # with pysftp.Connection(host="edi.alliedexpress.com.au", username="delvme.external", password="987899e64", cnopts=cnopts) as sftp_con:
#                 #     with sftp_con.cd(sftp_filepath):
#                 #         sftp_con.put(local_filepath + filename)
#                 #         sftp_file_size = sftp_con.lstat(sftp_filepath + filename).st_size
#                 #         local_file_size = os.stat(local_filepath + filename).st_size

#                 #         if sftp_file_size == local_file_size:
#                 #             if not os.path.exists(local_filepath_dup):
#                 #                 os.makedirs(local_filepath_dup)
#                 #             shutil.move(local_filepath + filename, local_filepath_dup + filename)

#                 #     sftp_con.close()
#                 # end copying xml files to sftp server

#                 # start update booking status in dme_booking table
#                 # sql2 = "UPDATE dme_bookings set b_status = %s, b_dateBookedDate = %s WHERE pk_booking_id = %s"
#                 # adr2 = ("Booked", get_sydney_now_time(), booking["pk_booking_id"])
#                 # mycursor.execute(sql2, adr2)
#                 # mysqlcon.commit()
#             except Exception as e:
#                 # print('@300 Allied XML - ', e)
#                 return e
#     elif vx_freight_provider.lower() == "tasfr":
#         # start check if xmls folder exists
#         if production:
#             local_filepath = "/opt/s3_private/xmls/tas_au/"
#             local_filepath_dup = (
#                 "/opt/s3_private/xmls/tas_au/archive/"
#                 + str(datetime.now().strftime("%Y_%m_%d"))
#                 + "/"
#             )
#         else:
#             local_filepath = "./static/xmls/tas_au/"
#             local_filepath_dup = (
#                 "./static/xmls/tas_au/archive/"
#                 + str(datetime.now().strftime("%Y_%m_%d"))
#                 + "/"
#             )

#         if not os.path.exists(local_filepath):
#             os.makedirs(local_filepath)
#         # end check if xmls folder exists

#         # start loop through data fetched from dme_bookings table
#         i = 1
#         if one_manifest_file == 0:
#             for booking in bookings:
#                 try:
#                     dme_manifest_log = Dme_manifest_log.objects.filter(
#                         fk_booking_id=booking["pk_booking_id"]
#                     ).last()
#                     manifest_number = dme_manifest_log.manifest_number
#                     fp_info = Fp_freight_providers.objects.get(fp_company_name="Tas")
#                     initial_connot_index = int(fp_info.new_connot_index) - len(bookings)
#                     # start db query for fetching data from dme_booking_lines table
#                     booking_lines = get_available_booking_lines(mysqlcon, booking)
#                     # end db query for fetching data from dme_booking_lines table

#                     # start calculate total item quantity and total item weight
#                     totalQty = 0
#                     totalWght = 0
#                     for booking_line in booking_lines:
#                         totalQty = totalQty + booking_line["e_qty"]
#                         totalWght = totalWght + booking_line["e_Total_KG_weight"]
#                     # start calculate total item quantity and total item weight

#                     # start xml file name using naming convention
#                     filename = (
#                         "TAS_FP_"
#                         + str(datetime.now().strftime("%d-%m-%Y %H_%M_%S"))
#                         + "_"
#                         + str(i)
#                         + ".xml"
#                     )

#                     # end xml file name using naming convention

#                     # start formatting xml file and putting data from db tables
#                     root = xml.Element(
#                         "fd:Manifest",
#                         **{
#                             "xmlns:xsi": "http://www.w3.org/2001/XMLSchema-instance",
#                             "xmlns:fd": "http://www.ezysend.com/FreightDescription/2.0",
#                             "Version": "2.0",
#                             "Action": "Submit",
#                             "Number": manifest_number,
#                             "Type": "Outbound",
#                             "xsi:schemaLocation": "http://www.ezysend.com/FreightDescription/2.0 http://www.ezysend.com/EDI/FreightDescription/2.0/schema.xsd",
#                         },
#                     )

#                     # IndependentContainers = xml.Element("fd:IndependentContainers")
#                     # root.append(IndependentContainers)
#                     # xml.SubElement(IndependentContainers, "fd:Container", **{'Identifier': "IC"+ ACCOUNT_CODE +"00001", 'Volume': "1.02", 'Weight': "200", 'Commodity': "Pallet"})
#                     connote_number = ACCOUNT_CODE + str(
#                         initial_connot_index + i - 1
#                     ).zfill(5)

#                     # consignment = xml.Element("fd:Consignment", **{'Number': "DME"+str(booking['b_bookingID_Visual'])})
#                     consignment = xml.Element(
#                         "fd:Consignment", **{"Number": connote_number}
#                     )
#                     root.append(consignment)

#                     Carrier = xml.SubElement(consignment, "fd:Carrier")
#                     Carrier.text = booking["vx_freight_provider"]
#                     AccountCode = xml.SubElement(consignment, "fd:AccountCode")
#                     AccountCode.text = ACCOUNT_CODE

#                     senderName = xml.SubElement(
#                         consignment, "fd:Sender", **{"Name": ACCOUNT_CODE}
#                     )
#                     senderAddress = xml.SubElement(senderName, "fd:Address")
#                     senderAddressLine1 = xml.SubElement(senderAddress, "fd:Address1")
#                     senderAddressLine1.text = booking["pu_Address_Street_1"]
#                     senderLocality = xml.SubElement(senderAddress, "fd:Locality")
#                     senderLocality.text = booking["pu_Address_Suburb"]
#                     senderState = xml.SubElement(senderAddress, "fd:Territory")
#                     senderState.text = booking["pu_Address_State"]
#                     senderPostcode = xml.SubElement(senderAddress, "fd:PostCode")
#                     senderPostcode.text = booking["pu_Address_PostalCode"]
#                     senderCountry = xml.SubElement(senderAddress, "fd:Country")
#                     senderCountry.text = booking["pu_Address_Country"]

#                     companyName = booking["deToCompanyName"].replace("<", "")
#                     companyName = companyName.replace(">", "")
#                     companyName = companyName.replace('"', "")
#                     companyName = companyName.replace("'", "")
#                     companyName = companyName.replace("&", "and")

#                     ReceiverName = xml.SubElement(
#                         consignment,
#                         "fd:Receiver",
#                         **{"Name": companyName, "Reference": "CUST0001"},
#                     )
#                     ReceiverAddress = xml.SubElement(ReceiverName, "fd:Address")
#                     ReceiverAddressLine1 = xml.SubElement(
#                         ReceiverAddress, "fd:Address1"
#                     )
#                     ReceiverAddressLine1.text = booking["de_To_Address_Street_1"]
#                     ReceiverLocality = xml.SubElement(ReceiverAddress, "fd:Locality")
#                     ReceiverLocality.text = booking["de_To_Address_Suburb"]
#                     ReceiverState = xml.SubElement(ReceiverAddress, "fd:Territory")
#                     ReceiverState.text = booking["de_To_Address_State"]
#                     ReceiverPostcode = xml.SubElement(ReceiverAddress, "fd:PostCode")
#                     ReceiverPostcode.text = booking["de_To_Address_PostalCode"]
#                     ReceiverCountry = xml.SubElement(ReceiverAddress, "fd:Country")
#                     ReceiverCountry.text = booking["de_To_Address_Country"]

#                     ContactName = xml.SubElement(ReceiverName, "fd:ContactName")
#                     ContactName.text = (
#                         str(booking["de_to_Contact_FName"])
#                         if booking["de_to_Contact_FName"]
#                         else ""
#                     ) + (
#                         " " + str(booking["de_to_Contact_Lname"])
#                         if booking["de_to_Contact_Lname"]
#                         else ""
#                     )
#                     PhoneNumber = xml.SubElement(ReceiverName, "fd:PhoneNumber")
#                     PhoneNumber.text = (
#                         str(booking["de_to_Phone_Main"])
#                         if booking["de_to_Phone_Main"]
#                         else ""
#                     )

#                     FreightForwarderName = xml.SubElement(
#                         consignment, "fd:FreightForwarder", **{"Name": companyName}
#                     )
#                     FreightForwarderAddress = xml.SubElement(
#                         FreightForwarderName, "fd:Address"
#                     )
#                     FreightForwarderAddressLine1 = xml.SubElement(
#                         FreightForwarderAddress, "fd:Address1"
#                     )
#                     FreightForwarderAddressLine1.text = booking[
#                         "de_To_Address_Street_1"
#                     ]
#                     FreightForwarderLocality = xml.SubElement(
#                         FreightForwarderAddress, "fd:Locality"
#                     )
#                     FreightForwarderLocality.text = booking["de_To_Address_Suburb"]
#                     FreightForwarderState = xml.SubElement(
#                         FreightForwarderAddress, "fd:Territory"
#                     )
#                     FreightForwarderState.text = booking["de_To_Address_State"]
#                     FreightForwarderPostcode = xml.SubElement(
#                         FreightForwarderAddress, "fd:PostCode"
#                     )
#                     FreightForwarderPostcode.text = booking["de_To_Address_PostalCode"]
#                     FreightForwarderCountry = xml.SubElement(
#                         FreightForwarderAddress, "fd:Country"
#                     )
#                     FreightForwarderCountry.text = booking["de_To_Address_Country"]

#                     Fragile = xml.SubElement(consignment, "fd:Fragile")
#                     Fragile.text = "true"

#                     ServiceType = xml.SubElement(consignment, "fd:ServiceType")
#                     ServiceType.text = booking["vx_serviceName"]

#                     DeliveryWindow = xml.SubElement(
#                         consignment,
#                         "fd:DeliveryWindow",
#                         **{
#                             "From": (
#                                 booking["puPickUpAvailFrom_Date"].strftime("%Y-%m-%d")
#                                 + "T09:00:00"
#                             ),
#                             "To": (
#                                 booking["pu_PickUp_By_Date"].strftime("%Y-%m-%d")
#                                 + "T17:00:00"
#                             )
#                             if booking["pu_PickUp_By_Date"] is not None
#                             else (
#                                 booking["puPickUpAvailFrom_Date"].strftime("%Y-%m-%d")
#                                 + "T17:00:00"
#                             ),
#                         },
#                     )

#                     DeliveryInstructions = xml.SubElement(
#                         consignment, "fd:DeliveryInstructions"
#                     )
#                     DeliveryInstructions.text = (
#                         str(booking["de_to_PickUp_Instructions_Address"])
#                         + " "
#                         + str(booking["de_to_Pick_Up_Instructions_Contact"])
#                     )

#                     # FPBookingNumber = xml.SubElement(consignment, "fd:FPBookingNumber")
#                     # FPBookingNumber.text = booking['v_FPBookingNumber']

#                     # BulkPricing = xml.SubElement(consignment, "fd:BulkPricing")
#                     # xml.SubElement(BulkPricing, "fd:Container", **{ 'Weight': "500", 'Identifier': "C"+ ACCOUNT_CODE +"00003", 'Volume': "0.001", 'Commodity': "PALLET" })

#                     for booking_line in booking_lines:
#                         FreightDetails = xml.SubElement(
#                             consignment,
#                             "fd:FreightDetails",
#                             **{
#                                 "Reference": str(booking_line["client_item_reference"])
#                                 if booking_line["client_item_reference"]
#                                 else "",
#                                 "Quantity": str(booking_line["e_qty"]),
#                                 "Commodity": (
#                                     get_item_type(booking_line["e_item_type"])
#                                     if booking_line["e_item_type"]
#                                     else ""
#                                 ),
#                                 "CustomDescription": str(booking_line["e_item"])
#                                 if booking_line["e_item"]
#                                 else "",
#                             },
#                         )
#                         if booking_line["e_dangerousGoods"]:
#                             DangerousGoods = xml.SubElement(
#                                 FreightDetails,
#                                 "fd:DangerousGoods",
#                                 **{"Class": "1", "UNNumber": "1003"},
#                             )

#                         ItemDimensions = xml.SubElement(
#                             FreightDetails,
#                             "fd:ItemDimensions",
#                             **{
#                                 "Length": str("1")
#                                 if booking_line["e_dimLength"] == None
#                                 or booking_line["e_dimLength"] == ""
#                                 or booking_line["e_dimLength"] == 0
#                                 else str(booking_line["e_dimLength"]),
#                                 "Width": str("1")
#                                 if booking_line["e_dimWidth"] == None
#                                 or booking_line["e_dimWidth"] == ""
#                                 or booking_line["e_dimWidth"] == 0
#                                 else str(booking_line["e_dimWidth"]),
#                                 "Height": str("1")
#                                 if booking_line["e_dimHeight"] == None
#                                 or booking_line["e_dimHeight"] == ""
#                                 or booking_line["e_dimHeight"] == 0
#                                 else str(booking_line["e_dimHeight"]),
#                             },
#                         )

#                         if (
#                             booking_line["e_dimWidth"] == None
#                             or booking_line["e_dimWidth"] == ""
#                             or booking_line["e_dimWidth"] == 0
#                         ):
#                             sql2 = "UPDATE dme_booking_lines set e_dimWidth = %s WHERE pk_lines_id = %s"
#                             adr2 = (1, booking_line["pk_lines_id"])
#                             mycursor.execute(sql2, adr2)
#                             mysqlcon.commit()

#                         if (
#                             booking_line["e_dimLength"] == None
#                             or booking_line["e_dimLength"] == ""
#                             or booking_line["e_dimLength"] == 0
#                         ):
#                             sql2 = "UPDATE dme_booking_lines set e_dimLength = %s WHERE pk_lines_id = %s"
#                             adr2 = (1, booking_line["pk_lines_id"])
#                             mycursor.execute(sql2, adr2)
#                             mysqlcon.commit()

#                         if (
#                             booking_line["e_dimHeight"] == None
#                             or booking_line["e_dimHeight"] == ""
#                             or booking_line["e_dimHeight"] == 0
#                         ):
#                             sql2 = "UPDATE dme_booking_lines set e_dimHeight = %s WHERE pk_lines_id = %s"
#                             adr2 = (1, booking_line["pk_lines_id"])
#                             mycursor.execute(sql2, adr2)
#                             mysqlcon.commit()

#                         ItemWeight = xml.SubElement(FreightDetails, "fd:ItemWeight")
#                         ItemWeight.text = (
#                             format(
#                                 booking_line["e_Total_KG_weight"]
#                                 / booking_line["e_qty"],
#                                 ".2f",
#                             )
#                             if booking_line["e_qty"] > 0
#                             else 0
#                         )

#                         # ItemVolume = xml.SubElement(FreightDetails, "fd:ItemVolume")
#                         # if booking_line['e_1_Total_dimCubicMeter'] is not None:
#                         #     ItemVolume.text = format(booking_line['e_1_Total_dimCubicMeter'], '.2f')

#                         Items = xml.SubElement(FreightDetails, "fd:Items")
#                         for j in range(1, booking_line["e_qty"] + 1):
#                             Item = xml.SubElement(
#                                 Items,
#                                 "fd:Item",
#                                 **{" Container": "IC" + ACCOUNT_CODE + str(i).zfill(5)},
#                             )
#                             Item.text = "S" + connote_number + str(j).zfill(3)

#                     i += 1
#                     # end formatting xml file and putting data from db tables

#                     # start writting data into xml files
#                     tree = xml.ElementTree(root)

#                     with open(local_filepath + filename, "wb") as fh:
#                         tree.write(fh, encoding="UTF-8", xml_declaration=True)

#                     # start update booking status in dme_booking table
#                     sql2 = "UPDATE dme_bookings set b_status=%s, b_dateBookedDate=%s, v_FPBookingNumber=%s WHERE pk_booking_id = %s"
#                     adr2 = (
#                         "Booked",
#                         get_sydney_now_time(),
#                         connote_number,
#                         booking["pk_booking_id"],
#                     )
#                     mycursor.execute(sql2, adr2)
#                     mysqlcon.commit()
#                 except Exception as e:
#                     logger.info(f"@300 TAS XML - {e}")
#                     return e
#         elif one_manifest_file == 1:
#             try:
#                 dme_manifest_log = Dme_manifest_log.objects.filter(
#                     fk_booking_id=bookings[0]["pk_booking_id"]
#                 ).last()
#                 manifest_number = dme_manifest_log.manifest_number
#                 fp_info = Fp_freight_providers.objects.get(fp_company_name="Tas")
#                 initial_connot_index = int(fp_info.new_connot_index) - len(bookings)
#                 # start xml file name using naming convention
#                 filename = (
#                     "TAS_FP_"
#                     + str(datetime.now().strftime("%d-%m-%Y %H_%M_%S"))
#                     + "_multiple connots in one.xml"
#                 )
#                 # end xml file name using naming convention

#                 # start formatting xml file and putting data from db tables
#                 root = xml.Element(
#                     "fd:Manifest",
#                     **{
#                         "xmlns:xsi": "http://www.w3.org/2001/XMLSchema-instance",
#                         "xmlns:fd": "http://www.ezysend.com/FreightDescription/2.0",
#                         "Version": "2.0",
#                         "Action": "Submit",
#                         "Number": manifest_number,
#                         "Type": "Outbound",
#                         "xsi:schemaLocation": "http://www.ezysend.com/FreightDescription/2.0 http://www.ezysend.com/EDI/FreightDescription/2.0/schema.xsd",
#                     },
#                 )

#                 # IndependentContainers = xml.Element("fd:IndependentContainers")
#                 # root.append(IndependentContainers)
#                 # xml.SubElement(IndependentContainers, "fd:Container", **{'Identifier': "IC"+ ACCOUNT_CODE +"00001", 'Volume': "1.02", 'Weight': "200", 'Commodity': "Pallet"})

#                 for booking in bookings:
#                     # start db query for fetching data from dme_booking_lines table
#                     booking_lines = get_available_booking_lines(mysqlcon, booking)
#                     # end db query for fetching data from dme_booking_lines table

#                     # start calculate total item quantity and total item weight
#                     totalQty = 0
#                     totalWght = 0
#                     for booking_line in booking_lines:
#                         totalQty = totalQty + booking_line["e_qty"]
#                         totalWght = totalWght + booking_line["e_Total_KG_weight"]
#                     # start calculate total item quantity and total item weight

#                     connote_number = ACCOUNT_CODE + str(
#                         initial_connot_index + i - 1
#                     ).zfill(5)

#                     # consignment = xml.Element("fd:Consignment", **{'Number': "DME"+str(booking['b_bookingID_Visual'])})
#                     consignment = xml.Element(
#                         "fd:Consignment", **{"Number": connote_number}
#                     )
#                     root.append(consignment)

#                     Carrier = xml.SubElement(consignment, "fd:Carrier")
#                     Carrier.text = booking["vx_freight_provider"]
#                     AccountCode = xml.SubElement(consignment, "fd:AccountCode")
#                     AccountCode.text = ACCOUNT_CODE

#                     senderName = xml.SubElement(
#                         consignment, "fd:Sender", **{"Name": ACCOUNT_CODE}
#                     )
#                     senderAddress = xml.SubElement(senderName, "fd:Address")
#                     senderAddressLine1 = xml.SubElement(senderAddress, "fd:Address1")
#                     senderAddressLine1.text = booking["pu_Address_Street_1"]
#                     senderLocality = xml.SubElement(senderAddress, "fd:Locality")
#                     senderLocality.text = booking["pu_Address_Suburb"]
#                     senderState = xml.SubElement(senderAddress, "fd:Territory")
#                     senderState.text = booking["pu_Address_State"]
#                     senderPostcode = xml.SubElement(senderAddress, "fd:PostCode")
#                     senderPostcode.text = booking["pu_Address_PostalCode"]
#                     senderCountry = xml.SubElement(senderAddress, "fd:Country")
#                     senderCountry.text = booking["pu_Address_Country"]

#                     companyName = booking["deToCompanyName"].replace("<", "")
#                     companyName = companyName.replace(">", "")
#                     companyName = companyName.replace('"', "")
#                     companyName = companyName.replace("'", "")
#                     companyName = companyName.replace("&", "and")

#                     ReceiverName = xml.SubElement(
#                         consignment,
#                         "fd:Receiver",
#                         **{"Name": companyName, "Reference": "CUST0001"},
#                     )
#                     ReceiverAddress = xml.SubElement(ReceiverName, "fd:Address")
#                     ReceiverAddressLine1 = xml.SubElement(
#                         ReceiverAddress, "fd:Address1"
#                     )
#                     ReceiverAddressLine1.text = booking["de_To_Address_Street_1"]
#                     ReceiverLocality = xml.SubElement(ReceiverAddress, "fd:Locality")
#                     ReceiverLocality.text = booking["de_To_Address_Suburb"]
#                     ReceiverState = xml.SubElement(ReceiverAddress, "fd:Territory")
#                     ReceiverState.text = booking["de_To_Address_State"]
#                     ReceiverPostcode = xml.SubElement(ReceiverAddress, "fd:PostCode")
#                     ReceiverPostcode.text = booking["de_To_Address_PostalCode"]
#                     ReceiverCountry = xml.SubElement(ReceiverAddress, "fd:Country")
#                     ReceiverCountry.text = booking["de_To_Address_Country"]

#                     ContactName = xml.SubElement(ReceiverName, "fd:ContactName")
#                     ContactName.text = (
#                         str(booking["de_to_Contact_FName"])
#                         if booking["de_to_Contact_FName"]
#                         else ""
#                     ) + (
#                         " " + str(booking["de_to_Contact_Lname"])
#                         if booking["de_to_Contact_Lname"]
#                         else ""
#                     )
#                     PhoneNumber = xml.SubElement(ReceiverName, "fd:PhoneNumber")
#                     PhoneNumber.text = (
#                         str(booking["de_to_Phone_Main"])
#                         if booking["de_to_Phone_Main"]
#                         else ""
#                     )

#                     FreightForwarderName = xml.SubElement(
#                         consignment, "fd:FreightForwarder", **{"Name": companyName}
#                     )
#                     FreightForwarderAddress = xml.SubElement(
#                         FreightForwarderName, "fd:Address"
#                     )
#                     FreightForwarderAddressLine1 = xml.SubElement(
#                         FreightForwarderAddress, "fd:Address1"
#                     )
#                     FreightForwarderAddressLine1.text = booking[
#                         "de_To_Address_Street_1"
#                     ]
#                     FreightForwarderLocality = xml.SubElement(
#                         FreightForwarderAddress, "fd:Locality"
#                     )
#                     FreightForwarderLocality.text = booking["de_To_Address_Suburb"]
#                     FreightForwarderState = xml.SubElement(
#                         FreightForwarderAddress, "fd:Territory"
#                     )
#                     FreightForwarderState.text = booking["de_To_Address_State"]
#                     FreightForwarderPostcode = xml.SubElement(
#                         FreightForwarderAddress, "fd:PostCode"
#                     )
#                     FreightForwarderPostcode.text = booking["de_To_Address_PostalCode"]
#                     FreightForwarderCountry = xml.SubElement(
#                         FreightForwarderAddress, "fd:Country"
#                     )
#                     FreightForwarderCountry.text = booking["de_To_Address_Country"]

#                     Fragile = xml.SubElement(consignment, "fd:Fragile")
#                     Fragile.text = "true"

#                     ServiceType = xml.SubElement(consignment, "fd:ServiceType")
#                     ServiceType.text = booking["vx_serviceName"]

#                     DeliveryWindow = xml.SubElement(
#                         consignment,
#                         "fd:DeliveryWindow",
#                         **{
#                             "From": (
#                                 booking["puPickUpAvailFrom_Date"].strftime("%Y-%m-%d")
#                                 + "T09:00:00"
#                             ),
#                             "To": (
#                                 booking["pu_PickUp_By_Date"].strftime("%Y-%m-%d")
#                                 + "T17:00:00"
#                             )
#                             if booking["pu_PickUp_By_Date"] is not None
#                             else (
#                                 booking["puPickUpAvailFrom_Date"].strftime("%Y-%m-%d")
#                                 + "T17:00:00"
#                             ),
#                         },
#                     )

#                     DeliveryInstructions = xml.SubElement(
#                         consignment, "fd:DeliveryInstructions"
#                     )
#                     DeliveryInstructions.text = (
#                         str(booking["de_to_PickUp_Instructions_Address"])
#                         + " "
#                         + str(booking["de_to_Pick_Up_Instructions_Contact"])
#                     )

#                     # FPBookingNumber = xml.SubElement(consignment, "fd:FPBookingNumber")
#                     # FPBookingNumber.text = booking['v_FPBookingNumber']

#                     # BulkPricing = xml.SubElement(consignment, "fd:BulkPricing")
#                     # xml.SubElement(BulkPricing, "fd:Container", **{ 'Weight': "500", 'Identifier': "C"+ ACCOUNT_CODE +"00003", 'Volume': "0.001", 'Commodity': "PALLET" })

#                     serial_index = 0
#                     for booking_line in booking_lines:
#                         FreightDetails = xml.SubElement(
#                             consignment,
#                             "fd:FreightDetails",
#                             **{
#                                 "Reference": str(booking_line["client_item_reference"])
#                                 if booking_line["client_item_reference"]
#                                 else "",
#                                 "Quantity": str(booking_line["e_qty"]),
#                                 "Commodity": (
#                                     get_item_type(booking_line["e_item_type"])
#                                     if booking_line["e_item_type"]
#                                     else ""
#                                 ),
#                                 "CustomDescription": str(booking_line["e_item"])
#                                 if booking_line["e_item"]
#                                 else "",
#                             },
#                         )
#                         if booking_line["e_dangerousGoods"]:
#                             DangerousGoods = xml.SubElement(
#                                 FreightDetails,
#                                 "fd:DangerousGoods",
#                                 **{"Class": "1", "UNNumber": "1003"},
#                             )

#                         ItemDimensions = xml.SubElement(
#                             FreightDetails,
#                             "fd:ItemDimensions",
#                             **{
#                                 "Length": str("1")
#                                 if booking_line["e_dimLength"] == None
#                                 or booking_line["e_dimLength"] == ""
#                                 or booking_line["e_dimLength"] == 0
#                                 else str(booking_line["e_dimLength"]),
#                                 "Width": str("1")
#                                 if booking_line["e_dimWidth"] == None
#                                 or booking_line["e_dimWidth"] == ""
#                                 or booking_line["e_dimWidth"] == 0
#                                 else str(booking_line["e_dimWidth"]),
#                                 "Height": str("1")
#                                 if booking_line["e_dimHeight"] == None
#                                 or booking_line["e_dimHeight"] == ""
#                                 or booking_line["e_dimHeight"] == 0
#                                 else str(booking_line["e_dimHeight"]),
#                             },
#                         )

#                         if (
#                             booking_line["e_dimWidth"] == None
#                             or booking_line["e_dimWidth"] == ""
#                             or booking_line["e_dimWidth"] == 0
#                         ):
#                             sql2 = "UPDATE dme_booking_lines set e_dimWidth = %s WHERE pk_lines_id = %s"
#                             adr2 = (1, booking_line["pk_lines_id"])
#                             mycursor.execute(sql2, adr2)
#                             mysqlcon.commit()

#                         if (
#                             booking_line["e_dimLength"] == None
#                             or booking_line["e_dimLength"] == ""
#                             or booking_line["e_dimLength"] == 0
#                         ):
#                             sql2 = "UPDATE dme_booking_lines set e_dimLength = %s WHERE pk_lines_id = %s"
#                             adr2 = (1, booking_line["pk_lines_id"])
#                             mycursor.execute(sql2, adr2)
#                             mysqlcon.commit()

#                         if (
#                             booking_line["e_dimHeight"] == None
#                             or booking_line["e_dimHeight"] == ""
#                             or booking_line["e_dimHeight"] == 0
#                         ):
#                             sql2 = "UPDATE dme_booking_lines set e_dimHeight = %s WHERE pk_lines_id = %s"
#                             adr2 = (1, booking_line["pk_lines_id"])
#                             mycursor.execute(sql2, adr2)
#                             mysqlcon.commit()

#                         ItemWeight = xml.SubElement(FreightDetails, "fd:ItemWeight")
#                         ItemWeight.text = (
#                             format(
#                                 booking_line["e_Total_KG_weight"]
#                                 / booking_line["e_qty"],
#                                 ".2f",
#                             )
#                             if booking_line["e_qty"] > 0
#                             else 0
#                         )

#                         # ItemVolume = xml.SubElement(FreightDetails, "fd:ItemVolume")
#                         # if booking_line['e_1_Total_dimCubicMeter'] is not None:
#                         #     ItemVolume.text = format(booking_line['e_1_Total_dimCubicMeter'], '.2f')

#                         Items = xml.SubElement(FreightDetails, "fd:Items")
#                         for j in range(1, booking_line["e_qty"] + 1):
#                             serial_index += 1
#                             Item = xml.SubElement(
#                                 Items,
#                                 "fd:Item",
#                                 **{" Container": "IC" + ACCOUNT_CODE + str(i).zfill(5)},
#                             )
#                             Item.text = (
#                                 "S" + connote_number + str(serial_index).zfill(3)
#                             )

#                     i += 1
#                     # end formatting xml file and putting data from db tables

#                     # start writting data into xml files
#                     tree = xml.ElementTree(root)

#                     with open(local_filepath + filename, "wb") as fh:
#                         tree.write(fh, encoding="UTF-8", xml_declaration=True)

#                     # start update booking status in dme_booking table
#                     sql2 = "UPDATE dme_bookings set b_status=%s, b_dateBookedDate=%s, v_FPBookingNumber=%s WHERE pk_booking_id = %s"
#                     adr2 = (
#                         "Booked",
#                         get_sydney_now_time(),
#                         connote_number,
#                         booking["pk_booking_id"],
#                     )
#                     mycursor.execute(sql2, adr2)
#                     mysqlcon.commit()
#             except Exception as e:
#                 logger.info(f"@301 TAS XML - {e}")
#                 return e
#     elif vx_freight_provider.lower() == "act":
#         # start check if xmls folder exists
#         if production:
#             local_filepath = "/opt/s3_private/xmls/act_au/"
#             local_filepath_dup = (
#                 "/opt/s3_private/xmls/act_au/archive/"
#                 + str(datetime.now().strftime("%Y_%m_%d"))
#                 + "/"
#             )
#         else:
#             local_filepath = "./static/xmls/act_au/"
#             local_filepath_dup = (
#                 "./static/xmls/act_au/archive/"
#                 + str(datetime.now().strftime("%Y_%m_%d"))
#                 + "/"
#             )

#         if not os.path.exists(local_filepath):
#             os.makedirs(local_filepath)
#         # end check if xmls folder exists

#         try:
#             for booking in bookings:
#                 # start xml file name using naming convention
#                 date = (
#                     datetime.now().strftime("%Y%m%d")
#                     + "_"
#                     + datetime.now().strftime("%H%M%S")
#                 )
#                 filename = "ACT_" + date + "_" + str(i) + ".xml"
#                 i += 1
#                 # end xml file name using naming convention

#                 root = xml.Element(
#                     "Manifest"
#                     # **{"xmlns:xsi": "http://www.w3.org/2001/XMLSchema-instance"},
#                 )
#                 File = xml.Element("FILE")
#                 FileName = xml.SubElement(File, "FILENAME")
#                 FileName.text = "ACT_BOOKING_" + str(
#                     datetime.now().strftime("%Y_%m_%d")
#                 )

#                 CreationTimeStamp = xml.SubElement(File, "CREATIONTIMESTAMP")
#                 CreationTimeStamp.text = str(
#                     datetime.now().strftime("%d/%m/%Y %I:%M:%S %p")
#                 )

#                 Id = xml.SubElement(File, "ID")
#                 Id.text = booking["pk_booking_id"]

#                 Consignment = xml.Element("CONSIGNMENT")
#                 Account = xml.SubElement(Consignment, "ACCOUNT")
#                 Account.text = ACCOUNT_CODE

#                 ConsignmentNumber = xml.SubElement(Consignment, "CONSIGNMENTNUMBER")
#                 ConsignmentNumber.text = gen_consignment_num(
#                     vx_freight_provider, booking["b_bookingID_Visual"]
#                 )

#                 Service = xml.SubElement(Consignment, "SERVICE")
#                 Service.text = booking["vx_serviceName"]

#                 Reference = xml.SubElement(Consignment, "REFERENCE")
#                 Reference.text = "JJ9208"

#                 PickupTime = xml.SubElement(Consignment, "PICKUPTIME")
#                 # PickupTime.text = booking["puPickUpAvailFrom_Date"]

#                 AdditionalInstructions = xml.SubElement(
#                     Consignment, "ADDITIONALINSTRUCTIONS"
#                 )
#                 AdditionalInstructions.text = "ACT Service"

#                 PuAddress = xml.Element("ADDRESS", **{"type": "pickup"})

#                 PuName = xml.SubElement(PuAddress, "NAME")
#                 PuAddress1 = xml.SubElement(PuAddress, "ADDRESS1")
#                 PuAddress1.text = booking["pu_Address_Street_1"]
#                 PuAddress2 = xml.SubElement(PuAddress, "ADDRESS2")
#                 PuAddress2.text = booking["pu_Address_street_2"]
#                 PuAddress3 = xml.SubElement(PuAddress, "ADDRESS3")
#                 PuAddress3.text = booking["pu_Address_Country"]
#                 PuSuburb = xml.SubElement(PuAddress, "SUBURB")
#                 PuSuburb.text = booking["pu_Address_Suburb"]
#                 PuState = xml.SubElement(PuAddress, "STATE")
#                 PuState.text = booking["pu_Address_State"]
#                 PuPostCode = xml.SubElement(PuAddress, "POSTCODE")
#                 PuPostCode.text = booking["pu_Address_PostalCode"]
#                 PuContact = xml.SubElement(PuAddress, "CONTACT")
#                 PuContact.text = booking["pu_Contact_F_L_Name"]
#                 PuPhone = xml.SubElement(PuAddress, "PHONE")
#                 PuPhone.text = booking["pu_Phone_Main"]

#                 puCompanyName = booking["puCompany"].replace("<", "")
#                 puCompanyName = puCompanyName.replace(">", "")
#                 puCompanyName = puCompanyName.replace('"', "")
#                 puCompanyName = puCompanyName.replace("'", "")
#                 puCompanyName = puCompanyName.replace("&", "and")
#                 PuName.text = puCompanyName

#                 DeToAddress = xml.Element("ADDRESS", **{"type": "delivery"})

#                 DeToName = xml.SubElement(DeToAddress, "NAME")
#                 DeToAddress1 = xml.SubElement(DeToAddress, "ADDRESS1")
#                 DeToAddress1.text = booking["de_To_Address_Street_1"]
#                 DeToAddress2 = xml.SubElement(DeToAddress, "ADDRESS2")
#                 DeToAddress2.text = booking["de_To_Address_Street_2"]
#                 DeToAddress3 = xml.SubElement(DeToAddress, "ADDRESS3")
#                 DeToAddress3.text = booking["de_To_Address_Country"]
#                 DeToSuburb = xml.SubElement(DeToAddress, "SUBURB")
#                 DeToSuburb.text = booking["de_To_Address_Suburb"]
#                 DeToState = xml.SubElement(DeToAddress, "STATE")
#                 DeToState.text = booking["de_To_Address_State"]
#                 DeToPostCode = xml.SubElement(DeToAddress, "POSTCODE")
#                 DeToPostCode.text = booking["de_To_Address_PostalCode"]
#                 DeToContact = xml.SubElement(DeToAddress, "CONTACT")
#                 DeToContact.text = booking["de_to_Contact_F_LName"]
#                 DeToPhone = xml.SubElement(DeToAddress, "PHONE")
#                 DeToPhone.text = booking["de_to_Phone_Main"]

#                 DeToCompanyName = booking["deToCompanyName"].replace("<", "")
#                 DeToCompanyName = DeToCompanyName.replace(">", "")
#                 DeToCompanyName = DeToCompanyName.replace('"', "")
#                 DeToCompanyName = DeToCompanyName.replace("'", "")
#                 DeToCompanyName = DeToCompanyName.replace("&", "and")
#                 DeToName.text = DeToCompanyName

#                 Sender = xml.SubElement(File, "SENDER")
#                 Sender.text = puCompanyName

#                 Receiver = xml.SubElement(File, "RECEIVER")
#                 Receiver.text = DeToCompanyName

#                 sql1 = "SELECT pk_lines_id, e_qty, e_item_type, e_item, e_dimWidth, e_dimLength, e_dimHeight, e_Total_KG_weight \
#                                     FROM dme_booking_lines \
#                                     WHERE fk_booking_id = %s"
#                 adr1 = (booking["pk_booking_id"],)
#                 mycursor.execute(sql1, adr1)
#                 booking_lines = mycursor.fetchall()

#                 # start calculate total item quantity and total item weight

#                 totalWght = 0
#                 for booking_line in booking_lines:
#                     totalWght = totalWght + booking_line["e_Total_KG_weight"]

#                 TotalItems = xml.SubElement(Consignment, "TOTALITEMS")
#                 TotalItems.text = str(len(booking_lines))

#                 TotalWeight = xml.SubElement(Consignment, "TOTALWEIGHT")
#                 TotalWeight.text = str(totalWght)

#                 Labels = xml.SubElement(Consignment, "LABELS")

#                 for booking_line in booking_lines:
#                     Item = xml.Element("ITEM")

#                     Weight = xml.SubElement(Item, "WEIGHT")
#                     Weight.text = (
#                         format(
#                             booking_line["e_Total_KG_weight"] / booking_line["e_qty"],
#                             ".2f",
#                         )
#                         if booking_line["e_qty"] > 0
#                         else 0
#                     )
#                     X = xml.SubElement(Item, "X")
#                     Y = xml.SubElement(Item, "Y")
#                     Z = xml.SubElement(Item, "Z")

#                     Description = xml.SubElement(Item, "DESCRIPTION")
#                     Description.text = booking_line["e_item"]

#                     Label = xml.SubElement(Item, "LABEL")
#                     Label.text = booking_line["e_item"]

#                     Quantity = xml.SubElement(Item, "QUANTITY")
#                     Quantity.text = str(booking_line["e_qty"])

#                     X = xml.SubElement(Item, "X")
#                     if (
#                         booking_line["e_dimWidth"] == None
#                         or booking_line["e_dimWidth"] == ""
#                         or booking_line["e_dimWidth"] == 0
#                     ):
#                         X.text = str("1")

#                         sql2 = "UPDATE dme_booking_lines set e_dimWidth = %s WHERE pk_lines_id = %s"
#                         adr2 = (1, booking_line["pk_lines_id"])
#                         mycursor.execute(sql2, adr2)
#                         mysqlcon.commit()
#                     else:
#                         X.text = str(booking_line["e_dimWidth"])

#                     Z = xml.SubElement(Item, "Z")
#                     if (
#                         booking_line["e_dimLength"] == None
#                         or booking_line["e_dimLength"] == ""
#                         or booking_line["e_dimLength"] == 0
#                     ):
#                         Z.text = str("1")

#                         sql2 = "UPDATE dme_booking_lines set e_dimLength = %s WHERE pk_lines_id = %s"
#                         adr2 = (1, booking_line["pk_lines_id"])
#                         mycursor.execute(sql2, adr2)
#                         mysqlcon.commit()
#                     else:
#                         Z.text = str(booking_line["e_dimLength"])

#                     Y = xml.SubElement(Item, "Y")
#                     if (
#                         booking_line["e_dimHeight"] == None
#                         or booking_line["e_dimHeight"] == ""
#                         or booking_line["e_dimHeight"] == 0
#                     ):
#                         Y.text = str("1")

#                         sql2 = "UPDATE dme_booking_lines set e_dimHeight = %s WHERE pk_lines_id = %s"
#                         adr2 = (1, booking_line["pk_lines_id"])
#                         mycursor.execute(sql2, adr2)
#                         mysqlcon.commit()
#                     else:
#                         Y.text = str(booking_line["e_dimHeight"])

#                     Consignment.append(Item)

#                 Consignment.append(PuAddress)
#                 Consignment.append(DeToAddress)

#                 root.append(File)
#                 root.append(Consignment)

#                 date = (
#                     datetime.now().strftime("%Y%m%d")
#                     + "_"
#                     + datetime.now().strftime("%H%M%S")
#                 )

#                 tree = xml.ElementTree(root)
#                 with open(local_filepath + filename, "wb") as fh:
#                     tree.write(fh, encoding="UTF-8", xml_declaration=True)

#         except Exception as e:
#             logger.info(f"@302 ST ACT XML - {e}")
#             return e
#     elif vx_freight_provider.lower() == "jet":
#         # start check if xmls folder exists
#         if production:
#             local_filepath = "/opt/s3_private/xmls/jet_au/"
#             local_filepath_dup = (
#                 "/opt/s3_private/xmls/jet_au/archive/"
#                 + str(datetime.now().strftime("%Y_%m_%d"))
#                 + "/"
#             )
#         else:
#             local_filepath = "./static/xmls/jet_au/"
#             local_filepath_dup = (
#                 "./static/xmls/jet_au/archive/"
#                 + str(datetime.now().strftime("%Y_%m_%d"))
#                 + "/"
#             )

#         if not os.path.exists(local_filepath):
#             os.makedirs(local_filepath)
#         # end check if xmls folder exists

#         try:
#             for booking in bookings:
#                 # start xml file name using naming convention
#                 date = (
#                     datetime.now().strftime("%Y%m%d")
#                     + "_"
#                     + datetime.now().strftime("%H%M%S")
#                 )
#                 filename = "JET_" + date + "_" + str(i) + ".xml"
#                 i += 1
#                 # end xml file name using naming convention

#                 root = xml.Element(
#                     "Manifest"
#                     # **{"xmlns:xsi": "http://www.w3.org/2001/XMLSchema-instance"},
#                 )
#                 File = xml.Element("FILE")
#                 FileName = xml.SubElement(File, "FILENAME")
#                 FileName.text = "ACT_BOOKING_" + str(
#                     datetime.now().strftime("%Y_%m_%d")
#                 )

#                 CreationTimeStamp = xml.SubElement(File, "CREATIONTIMESTAMP")
#                 CreationTimeStamp.text = str(
#                     datetime.now().strftime("%d/%m/%Y %I:%M:%S %p")
#                 )

#                 Id = xml.SubElement(File, "ID")
#                 Id.text = booking["pk_booking_id"]

#                 Consignment = xml.Element("CONSIGNMENT")
#                 Account = xml.SubElement(Consignment, "ACCOUNT")
#                 Account.text = ACCOUNT_CODE

#                 ConsignmentNumber = xml.SubElement(Consignment, "CONSIGNMENTNUMBER")
#                 ConsignmentNumber.text = gen_consignment_num(
#                     vx_freight_provider, booking["b_bookingID_Visual"]
#                 )

#                 Service = xml.SubElement(Consignment, "SERVICE")
#                 Service.text = booking["vx_serviceName"]

#                 Reference = xml.SubElement(Consignment, "REFERENCE")
#                 Reference.text = "JJ9208"

#                 PickupTime = xml.SubElement(Consignment, "PICKUPTIME")
#                 # PickupTime.text = booking["puPickUpAvailFrom_Date"]

#                 AdditionalInstructions = xml.SubElement(
#                     Consignment, "ADDITIONALINSTRUCTIONS"
#                 )
#                 AdditionalInstructions.text = "JET Service"

#                 PuAddress = xml.Element("ADDRESS", **{"type": "pickup"})

#                 PuName = xml.SubElement(PuAddress, "NAME")
#                 PuAddress1 = xml.SubElement(PuAddress, "ADDRESS1")
#                 PuAddress1.text = booking["pu_Address_Street_1"]
#                 PuAddress2 = xml.SubElement(PuAddress, "ADDRESS2")
#                 PuAddress2.text = booking["pu_Address_street_2"]
#                 PuAddress3 = xml.SubElement(PuAddress, "ADDRESS3")
#                 PuAddress3.text = booking["pu_Address_Country"]
#                 PuSuburb = xml.SubElement(PuAddress, "SUBURB")
#                 PuSuburb.text = booking["pu_Address_Suburb"]
#                 PuState = xml.SubElement(PuAddress, "STATE")
#                 PuState.text = booking["pu_Address_State"]
#                 PuPostCode = xml.SubElement(PuAddress, "POSTCODE")
#                 PuPostCode.text = booking["pu_Address_PostalCode"]
#                 PuContact = xml.SubElement(PuAddress, "CONTACT")
#                 PuContact.text = booking["pu_Contact_F_L_Name"]
#                 PuPhone = xml.SubElement(PuAddress, "PHONE")
#                 PuPhone.text = booking["pu_Phone_Main"]

#                 puCompanyName = booking["puCompany"].replace("<", "")
#                 puCompanyName = puCompanyName.replace(">", "")
#                 puCompanyName = puCompanyName.replace('"', "")
#                 puCompanyName = puCompanyName.replace("'", "")
#                 puCompanyName = puCompanyName.replace("&", "and")
#                 PuName.text = puCompanyName

#                 DeToAddress = xml.Element("ADDRESS", **{"type": "delivery"})

#                 DeToName = xml.SubElement(DeToAddress, "NAME")
#                 DeToAddress1 = xml.SubElement(DeToAddress, "ADDRESS1")
#                 DeToAddress1.text = booking["de_To_Address_Street_1"]
#                 DeToAddress2 = xml.SubElement(DeToAddress, "ADDRESS2")
#                 DeToAddress2.text = booking["de_To_Address_Street_2"]
#                 DeToAddress3 = xml.SubElement(DeToAddress, "ADDRESS3")
#                 DeToAddress3.text = booking["de_To_Address_Country"]
#                 DeToSuburb = xml.SubElement(DeToAddress, "SUBURB")
#                 DeToSuburb.text = booking["de_To_Address_Suburb"]
#                 DeToState = xml.SubElement(DeToAddress, "STATE")
#                 DeToState.text = booking["de_To_Address_State"]
#                 DeToPostCode = xml.SubElement(DeToAddress, "POSTCODE")
#                 DeToPostCode.text = booking["de_To_Address_PostalCode"]
#                 DeToContact = xml.SubElement(DeToAddress, "CONTACT")
#                 DeToContact.text = booking["de_to_Contact_F_LName"]
#                 DeToPhone = xml.SubElement(DeToAddress, "PHONE")
#                 DeToPhone.text = booking["de_to_Phone_Main"]

#                 DeToCompanyName = booking["deToCompanyName"].replace("<", "")
#                 DeToCompanyName = DeToCompanyName.replace(">", "")
#                 DeToCompanyName = DeToCompanyName.replace('"', "")
#                 DeToCompanyName = DeToCompanyName.replace("'", "")
#                 DeToCompanyName = DeToCompanyName.replace("&", "and")
#                 DeToName.text = DeToCompanyName

#                 Sender = xml.SubElement(File, "SENDER")
#                 Sender.text = puCompanyName

#                 Receiver = xml.SubElement(File, "RECEIVER")
#                 Receiver.text = DeToCompanyName

#                 sql1 = "SELECT pk_lines_id, e_qty, e_item_type, e_item, e_dimWidth, e_dimLength, e_dimHeight, e_Total_KG_weight \
#                                     FROM dme_booking_lines \
#                                     WHERE fk_booking_id = %s"
#                 adr1 = (booking["pk_booking_id"],)
#                 mycursor.execute(sql1, adr1)
#                 booking_lines = mycursor.fetchall()

#                 # start calculate total item quantity and total item weight

#                 totalWght = 0
#                 for booking_line in booking_lines:
#                     totalWght = totalWght + booking_line["e_Total_KG_weight"]

#                 TotalItems = xml.SubElement(Consignment, "TOTALITEMS")
#                 TotalItems.text = str(len(booking_lines))

#                 TotalWeight = xml.SubElement(Consignment, "TOTALWEIGHT")
#                 TotalWeight.text = str(totalWght)

#                 Labels = xml.SubElement(Consignment, "LABELS")

#                 for booking_line in booking_lines:
#                     Item = xml.Element("ITEM")

#                     Weight = xml.SubElement(Item, "WEIGHT")
#                     Weight.text = (
#                         format(
#                             booking_line["e_Total_KG_weight"] / booking_line["e_qty"],
#                             ".2f",
#                         )
#                         if booking_line["e_qty"] > 0
#                         else 0
#                     )
#                     X = xml.SubElement(Item, "X")
#                     Y = xml.SubElement(Item, "Y")
#                     Z = xml.SubElement(Item, "Z")

#                     Description = xml.SubElement(Item, "DESCRIPTION")
#                     Description.text = booking_line["e_item"]

#                     Label = xml.SubElement(Item, "LABEL")
#                     Label.text = booking_line["e_item"]

#                     Quantity = xml.SubElement(Item, "QUANTITY")
#                     Quantity.text = str(booking_line["e_qty"])

#                     X = xml.SubElement(Item, "X")
#                     if (
#                         booking_line["e_dimWidth"] == None
#                         or booking_line["e_dimWidth"] == ""
#                         or booking_line["e_dimWidth"] == 0
#                     ):
#                         X.text = str("1")

#                         sql2 = "UPDATE dme_booking_lines set e_dimWidth = %s WHERE pk_lines_id = %s"
#                         adr2 = (1, booking_line["pk_lines_id"])
#                         mycursor.execute(sql2, adr2)
#                         mysqlcon.commit()
#                     else:
#                         X.text = str(booking_line["e_dimWidth"])

#                     Z = xml.SubElement(Item, "Z")
#                     if (
#                         booking_line["e_dimLength"] == None
#                         or booking_line["e_dimLength"] == ""
#                         or booking_line["e_dimLength"] == 0
#                     ):
#                         Z.text = str("1")

#                         sql2 = "UPDATE dme_booking_lines set e_dimLength = %s WHERE pk_lines_id = %s"
#                         adr2 = (1, booking_line["pk_lines_id"])
#                         mycursor.execute(sql2, adr2)
#                         mysqlcon.commit()
#                     else:
#                         Z.text = str(booking_line["e_dimLength"])

#                     Y = xml.SubElement(Item, "Y")
#                     if (
#                         booking_line["e_dimHeight"] == None
#                         or booking_line["e_dimHeight"] == ""
#                         or booking_line["e_dimHeight"] == 0
#                     ):
#                         Y.text = str("1")

#                         sql2 = "UPDATE dme_booking_lines set e_dimHeight = %s WHERE pk_lines_id = %s"
#                         adr2 = (1, booking_line["pk_lines_id"])
#                         mycursor.execute(sql2, adr2)
#                         mysqlcon.commit()
#                     else:
#                         Y.text = str(booking_line["e_dimHeight"])

#                     Consignment.append(Item)

#                 Consignment.append(PuAddress)
#                 Consignment.append(DeToAddress)

#                 root.append(File)
#                 root.append(Consignment)

#                 date = (
#                     datetime.now().strftime("%Y%m%d")
#                     + "_"
#                     + datetime.now().strftime("%H%M%S")
#                 )

#                 tree = xml.ElementTree(root)
#                 with open(local_filepath + filename, "wb") as fh:
#                     tree.write(fh, encoding="UTF-8", xml_declaration=True)

#         except Exception as e:
#             logger.info(f"@301 JET XML - {e}")
#             return e
#     mysqlcon.close()
