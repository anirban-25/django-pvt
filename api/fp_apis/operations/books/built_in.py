from datetime import datetime

from api.common import status_history, trace_error


def book(booking, booker):
    """
    Used to avoid calling Truck from TNT
    """
    from api.fp_apis.utils import gen_consignment_num

    booking.v_FPBookingNumber = gen_consignment_num(
        booking.vx_freight_provider, booking.b_bookingID_Visual
    )
    booking.b_dateBookedDate = datetime.now()
    booking.b_error_Capture = None
    status_history.create(booking, "Booked", booker)
    booking.save()
