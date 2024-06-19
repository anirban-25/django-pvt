def _set_error(booking, error_msg):
    booking.b_error_Capture = str(error_msg)[:999]
    booking.save()
