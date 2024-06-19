import logging
from base64 import b64encode

from django.conf import settings
from api.fps.team_global_express import is_valid_connote
from api.helpers.line import is_pallet

from api.models import (
    Bookings,
    Booking_lines,
    Fp_freight_providers,
    FPRouting,
    FP_zones,
    Booking_lines_data,
)
from api.common import trace_error
from api.fp_apis.utils import gen_consignment_num
from api.convertors import pdf
from api.operations.labels import (
    ship_it,
    dhl,
    hunter,
    hunter_normal,
    hunter_thermal,
    tnt,
    allied,
    startrack,
    default,
    small_label,
    crossdock,
    team_global_express,
    direct_freight,
    carton,
    northline,
    camerons,
    dxt,
    ariston_wire,
)
from api.fps.team_global_express import gen_sscc as team_global_express_gen_sscc

logger = logging.getLogger(__name__)


def get_barcode(booking, booking_lines, pre_data, line_index=1, sscc_cnt=1):
    """
    Get barcode for label
    """
    result = None

    if pre_data["fp_name"] == "hunter":
        result = hunter.gen_barcode(booking, booking_lines, line_index, sscc_cnt)
    elif pre_data["fp_name"] == "tnt":
        result = tnt.gen_barcode(booking, booking_lines, line_index, sscc_cnt)
    elif pre_data["fp_name"] == "startrack":
        result = startrack.gen_barcode(
            booking, pre_data["v_FPBookingNumber"], line_index
        )
    elif pre_data["fp_name"] == "team global express":
        result = team_global_express_gen_sscc(
            booking, booking_lines[line_index - 1], line_index - 1
        )
    else:  # "auspost", "startrack", "TNT", "State Transport"
        result = ship_it.gen_barcode(booking, booking_lines, line_index, sscc_cnt)

    return result


def _get_pre_data(booking):
    _pre_data = {}
    fp_name = booking.vx_freight_provider.lower()
    _pre_data["fp_name"] = fp_name
    fp = Fp_freight_providers.objects.get(fp_company_name__iexact=fp_name)
    _pre_data["fp_id"] = fp.pk
    _pre_data["color_code"] = fp.hex_color_code

    _pre_data["v_FPBookingNumber"] = booking.v_FPBookingNumber

    v_FPBookingNumber = gen_consignment_num(
        booking.vx_freight_provider,
        booking.b_bookingID_Visual,
        booking.kf_client_id,
        booking,
    )
    _pre_data["v_FPBookingNumber"] = v_FPBookingNumber

    if fp_name == "dhl":
        pass
    elif fp_name == "hunter":
        pass
    elif fp_name == "tnt":
        lines_data = Booking_lines_data.objects.filter(
            fk_booking_id=booking.pk_booking_id
        ).only("fk_booking_lines_id", "gap_ra", "modelNumber")
        _pre_data["lines_data"] = lines_data
        _pre_data["lines_data_cnt"] = lines_data.count()

        """
        Let's assume service group EXP
        Using the D records relating to that service group, establish the origin depot thaservices the consignment’s origin postcode.
        This should appear in section 3 of the routing label preceded by “Ex “.
        """
        crecords = FPRouting.objects.filter(
            freight_provider=12,
            dest_suburb=booking.de_To_Address_Suburb,
            dest_postcode=booking.de_To_Address_PostalCode,
            dest_state=booking.de_To_Address_State,
            data_code="C"
            # routing_group=routing_group,
        ).only("orig_depot_except", "gateway", "onfwd", "sort_bin")

        routing = None
        orig_depot = ""
        if crecords.exists():
            drecord = (
                FPRouting.objects.filter(
                    freight_provider=12,
                    orig_postcode=booking.pu_Address_PostalCode,
                    # routing_group=routing_group,
                    orig_depot__isnull=False,
                    data_code="D",
                )
                .only("orig_depot")
                .first()
            )

            if drecord:
                orig_depot = drecord.orig_depot
                for crecord in crecords:
                    if crecord.orig_depot_except == drecord.orig_depot:
                        routing = crecord
                        break

            if not routing:
                routing = (
                    FPRouting.objects.filter(
                        freight_provider=12,
                        dest_suburb=booking.de_To_Address_Suburb,
                        dest_postcode=booking.de_To_Address_PostalCode,
                        dest_state=booking.de_To_Address_State,
                        orig_depot_except__isnull=True,
                        data_code="C"
                        # routing_group=routing_group,
                    )
                    .only("orig_depot_except", "gateway", "onfwd", "sort_bin")
                    .first()
                )
            if not routing:
                raise Exception(
                    f"FPRouting does not exist: {booking.de_To_Address_Suburb}, {booking.de_To_Address_PostalCode}, {booking.de_To_Address_State}"
                )

            logger.info(
                f"#113 [TNT LABEL] Found FPRouting: {routing}, {routing.gateway}, {routing.onfwd}, {routing.sort_bin}, {orig_depot}"
            )

            _pre_data["routing"] = routing
            _pre_data["orig_depot"] = orig_depot
        else:
            msg = f"#114 [TNT LABEL] FPRouting does not exist: {booking.de_To_Address_Suburb}, {booking.de_To_Address_PostalCode}, {booking.de_To_Address_State}"
            logger.error(msg)
            raise Exception(
                f"FPRouting does not exist: {booking.de_To_Address_Suburb}, {booking.de_To_Address_PostalCode}, {booking.de_To_Address_State}"
            )
    elif fp_name == "allied":
        try:
            carrier = FP_zones.objects.get(
                state=booking.de_To_Address_State,
                suburb=booking.de_To_Address_Suburb,
                postal_code=booking.de_To_Address_PostalCode,
                fk_fp=fp.pk,
            ).carrier
            _pre_data["carrier"] = carrier
        except FP_zones.DoesNotExist:
            _pre_data["carrier"] = ""
        except Exception as e:
            logger.info(f"#110 [ALLIED LABEL] Error: {str(e)}")
    elif fp_name == "camerons":
        try:
            zone = FP_zones.objects.get(
                state=booking.de_To_Address_State,
                suburb=booking.de_To_Address_Suburb,
                postal_code=booking.de_To_Address_PostalCode,
                fk_fp=fp.pk,
            ).zone
            _pre_data["zone"] = zone
        # except FP_zones.DoesNotExist:
        #     _pre_data["zone"] = ""
        except Exception as e:
            logger.info(f"#110 [CAMERONS LABEL] Error: {str(e)}")
    elif fp_name == "direct freight":
        crecords = FPRouting.objects.filter(
            freight_provider=88,
            dest_suburb=booking.de_To_Address_Suburb.upper(),
            dest_state=booking.de_To_Address_State.upper(),
            dest_postcode=booking.de_To_Address_PostalCode,
        ).only("gateway", "onfwd", "sort_bin", "orig_depot")

        routing = None
        orig_depot = ""
        if crecords.exists():
            drecord = crecords.first()
            orig_depot = drecord.orig_depot
            routing = drecord
            logger.info(
                f"#113 [DIRECT FREIGHT LABEL] Found FPRouting: {routing.gateway}, {routing.onfwd}, {routing.sort_bin}"
            )
        else:
            logger.info(
                f"#114 [DIRECT FREIGHT LABEL] FPRouting does not exist: {booking.de_To_Address_Suburb}, {booking.de_To_Address_PostalCode}, {booking.de_To_Address_State}"
            )
            raise Exception(
                f"FPRouting does not exist: {booking.de_To_Address_Suburb}, {booking.de_To_Address_PostalCode}, {booking.de_To_Address_State}"
            )
        _pre_data["routing"] = routing
        _pre_data["orig_depot"] = orig_depot
    elif fp_name == "team global express":
        booking_lines = Booking_lines.objects.filter(
            fk_booking_id=booking.pk_booking_id, is_deleted=False
        ).order_by("pk_lines_id")
        lines_data = Booking_lines_data.objects.filter(
            fk_booking_id=booking.pk_booking_id
        ).only("fk_booking_lines_id", "gap_ra", "clientRefNumber")
        _pre_data["lines_data"] = lines_data

        original_lines, scanned_lines = [], []
        for line in booking_lines:
            if line.packed_status == "original":
                original_lines.append(line)
            if line.packed_status == "scanned":
                scanned_lines.append(line)

        booking_lines = scanned_lines or original_lines
        if is_pallet(booking_lines[0].e_type_of_packaging):
            carrier = "I & S"
        else:
            carrier = "IPEC"

        _pre_data["carrier"] = carrier

        crecords = (
            FPRouting.objects.filter(
                freight_provider=109,
                dest_suburb=booking.de_To_Address_Suburb.upper(),
                dest_state=booking.de_To_Address_State.upper(),
                dest_postcode=booking.de_To_Address_PostalCode,
                routing_group__in=[
                    "IntermodalSpecialised" if carrier == "I & S" else "IPEC",
                    "MyTeamGE",
                ],
            )
            .only("orig_depot", "orig_depot_except", "routing_group")
            .order_by("-routing_group")
        )

        orig_depot = ""
        if crecords.exists():
            drecord = crecords.first()
            orig_depot = (  # Firstly, it finds MyTeamGE record and if it is I & S booking, use orig_depot_except field
                drecord.orig_depot_except
                if carrier == "I & S" and drecord.routing_group == "MyTeamGE"
                else drecord.orig_depot
            )
            logger.info(
                f"#113 [TEAM GLOBAL EXPRESS LABEL] Found orig_depot: {orig_depot}"
            )
        _pre_data["orig_depot"] = orig_depot

    elif fp_name == "startrack":
        pass
    elif fp_name == "dxt":
        try:
            zone = FP_zones.objects.get(
                state=booking.de_To_Address_State,
                suburb=booking.de_To_Address_Suburb,
                postal_code=booking.de_To_Address_PostalCode,
                fk_fp=fp.pk,
            ).zone
            _pre_data["zone"] = zone
        except FP_zones.DoesNotExist:
            _pre_data["zone"] = ""
        except Exception as e:
            logger.info(f"#110 [DXT LABEL] Error: {str(e)}")
    else:  # "Century", "ATC", "JasonL In house"
        try:
            carrier = FP_zones.objects.get(
                state=booking.de_To_Address_State,
                suburb=booking.de_To_Address_Suburb,
                postal_code=booking.de_To_Address_PostalCode,
                fk_fp=fp.pk,
            ).carrier
            _pre_data["carrier"] = carrier
        except FP_zones.DoesNotExist:
            _pre_data["carrier"] = ""
        except Exception as e:
            logger.info(f"#110 [ALLIED LABEL] Error: {str(e)}")

    return _pre_data


def _build_sscc_label(
    booking,
    file_path,
    pre_data,
    lines=[],
    label_index=0,
    sscc=None,
    sscc_cnt=1,
    one_page_label=False,
):
    try:
        if pre_data["fp_name"] == "dhl":
            file_path, file_name = dhl.build_label(
                booking,
                file_path,
                pre_data,
                lines,
                label_index,
                sscc,
                sscc_cnt,
                one_page_label,
            )
        elif pre_data["fp_name"] == "hunter":
            file_path, file_name = hunter_normal.build_label(
                booking,
                file_path,
                pre_data,
                lines,
                label_index,
                sscc,
                sscc_cnt,
                one_page_label,
            )
        elif pre_data["fp_name"] == "tnt":
            file_path, file_name = tnt.build_label(
                booking,
                file_path,
                pre_data,
                lines,
                label_index,
                sscc,
                sscc_cnt,
                one_page_label,
            )
        elif pre_data["fp_name"] == "allied":
            file_path, file_name = allied.build_label(
                booking,
                file_path,
                pre_data,
                lines,
                label_index,
                sscc,
                sscc_cnt,
                one_page_label,
            )
        elif pre_data["fp_name"] == "startrack":
            file_path, file_name = startrack.build_label(
                booking,
                file_path,
                pre_data,
                lines,
                label_index,
                sscc,
                sscc_cnt,
                one_page_label,
            )
        elif pre_data["fp_name"] == "team global express":
            file_path, file_name = team_global_express.build_label(
                booking,
                file_path,
                pre_data,
                lines,
                label_index,
                sscc,
                sscc_cnt,
                one_page_label,
            )
        elif pre_data["fp_name"] == "direct freight":
            file_path, file_name = direct_freight.build_label(
                booking,
                file_path,
                pre_data,
                lines,
                label_index,
                sscc,
                sscc_cnt,
                one_page_label,
            )
        elif pre_data["fp_name"] == "northline":
            file_path, file_name = northline.build_label(
                booking,
                file_path,
                pre_data,
                lines,
                label_index,
                sscc,
                sscc_cnt,
                one_page_label,
            )
        elif pre_data["fp_name"] == "camerons":
            file_path, file_name = camerons.build_label(
                booking,
                file_path,
                pre_data,
                lines,
                label_index,
                sscc,
                sscc_cnt,
                one_page_label,
            )
        elif pre_data["fp_name"] == "dxt":
            file_path, file_name = dxt.build_label(
                booking,
                file_path,
                pre_data,
                lines,
                label_index,
                sscc,
                sscc_cnt,
                one_page_label,
            )
        else:  # "Century", "ATC", "JasonL In house"
            file_path, file_name = default.build_label(
                booking,
                file_path,
                pre_data,
                lines,
                label_index,
                sscc,
                sscc_cnt,
                one_page_label,
            )

        # Big W | Cross Dock
        if booking.kf_client_id == "d69f550a-9327-4ff9-bc8f-242dfca00f7e":
            file_path_1 = f"{settings.STATIC_PUBLIC}/pdfs/cross dock_au"
            file_path_1, file_name_1 = crossdock.build_label(
                booking,
                file_path_1,
                pre_data,
                lines,
                label_index,
                sscc,
                sscc_cnt,
                one_page_label,
            )

        # Deactivated on 2024-02-23
        # # Abereen Paper | Carton
        # if (
        #     booking.kf_client_id == "4ac9d3ee-2558-4475-bdbb-9d9405279e81"
        #     and lines
        #     and lines[0].packed_status == Booking_lines.ORIGINAL
        # ):
        #     file_path_1 = f"{settings.STATIC_PUBLIC}/pdfs/carton_au"
        #     file_path_1, file_name_1 = carton.build_label(
        #         booking,
        #         file_path_1,
        #         pre_data,
        #         lines,
        #         label_index,
        #         sscc,
        #         sscc_cnt,
        #         one_page_label,
        #     )

        return file_path, file_name
    except Exception as e:
        trace_error.print()
        logger.error(f"[LABEL] error: {str(e)}")
        return None


def build_consignment(
    booking,
    file_path,
    pre_data,
    lines=[],
    label_index=0,
    sscc=None,
    sscc_cnt=1,
    one_page_label=False,
):
    try:
        file_name = None

        if pre_data["fp_name"] == "dxt":
            file_path, file_name = dxt.build_consignment(
                booking,
                file_path,
                pre_data,
                lines,
                label_index,
                sscc,
                sscc_cnt,
                one_page_label,
            )

        return file_path, file_name
    except Exception as e:
        trace_error.print()
        logger.error(f"[LABEL] error: {str(e)}")
        return None

def build_docket(
    booking,
    file_path,
    pre_data,
    lines=[],
    label_index=0,
    sscc=None,
    sscc_cnt=1,
    one_page_label=False,
):
    try:
        file_name = None

        if booking.b_client_name.lower() == "ariston wire":
            file_path, file_name = ariston_wire.build_docket(
                booking,
                file_path,
                pre_data,
                lines,
                label_index,
                sscc,
                sscc_cnt,
                one_page_label,
            )

        return file_path, file_name
    except Exception as e:
        trace_error.print()
        logger.error(f"[LABEL] error: {str(e)}")
        return None

def build_small_label(
    booking,
    file_path,
    lines=[],
    label_index=0,
    sscc=None,
    sscc_cnt=1,
    one_page_label=False,
):
    fp_name = booking.vx_freight_provider.lower()

    try:
        file_path, file_name = small_label.build_label(
            booking, file_path, lines, label_index, sscc, sscc_cnt, one_page_label
        )

        return file_path, file_name
    except Exception as e:
        trace_error.print()
        logger.error(f"[LABEL] error: {str(e)}")
        return None


def build_label(
    booking,
    file_path,
    total_qty,
    sscc_list=[],
    sscc_lines=[],
    need_base64=False,
    need_zpl=False,
    scanned_items=[],
):
    label_data = {"urls": [], "labels": []}
    logger.info(f"@368 - building label with SSCC...\n sscc_lines: {sscc_lines}")

    # Prepare data
    pre_data = _get_pre_data(booking)

    label_index = len(scanned_items)
    sscc = None
    for index, sscc in enumerate(sscc_list):
        file_path, file_name = _build_sscc_label(
            booking=booking,
            file_path=file_path,
            pre_data=pre_data,
            lines=sscc_lines[sscc],
            label_index=label_index,
            sscc=sscc,
            sscc_cnt=total_qty,
            one_page_label=False,
        )

        for _line in sscc_lines[sscc]:
            label_index += _line.e_qty

        label_url = f"{file_path}/{file_name}"
        label_data["urls"].append(label_url)
        label = {}
        label["sscc"] = sscc
        # label["barcode"] = get_barcode(
        #     booking, sscc_lines[sscc], pre_data, index + 1, len(sscc_list)
        # )

        if need_base64:
            label["base64"] = str(pdf.pdf_to_base64(label_url))[2:-1]

        if need_zpl:
            # Convert label into ZPL format
            msg = f"@369 converting LABEL({label_url}) into ZPL format..."
            logger.info(msg)

            # Plum ZPL printer requries portrait label
            if booking.vx_freight_provider.lower() in ["hunter", "tnt"]:
                label_url = pdf.rotate_pdf(label_url)

            result = pdf.pdf_to_zpl(label_url, label_url[:-4] + ".zpl")

            if not result:
                msg = f"Please contact DME support center. <bookings@deliver-me.com.au>"
                raise Exception(msg)

            with open(label_url[:-4] + ".zpl", "rb") as zpl:
                label["zpl"] = str(b64encode(zpl.read()))[2:-1]
                label["label"] = label["zpl"]

        label_data["labels"].append(label)
    build_consignment(
        booking=booking,
        file_path=file_path,
        pre_data=pre_data,
        lines=[item for sublist in sscc_lines.values() for item in sublist],
        label_index=label_index,
        sscc=sscc,
        sscc_cnt=total_qty,
        one_page_label=False,
    )
    build_docket(
        booking=booking,
        file_path=file_path,
        pre_data=pre_data,
        lines=[item for sublist in sscc_lines.values() for item in sublist],
        label_index=label_index,
        sscc=sscc,
        sscc_cnt=total_qty,
        one_page_label=False,
    )
    # # Set consignment number
    # booking.v_FPBookingNumber = gen_consignment_num(
    #     booking.vx_freight_provider,
    #     booking.b_bookingID_Visual,
    #     booking.kf_client_id,
    #     booking,
    # )
    # booking.save()
    return label_data
