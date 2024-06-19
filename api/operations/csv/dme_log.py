def wrap_in_quote(string):
    return '"' + str(string) + '"'


def build_csv(fileHandler, logs):
    has_error = False

    # Write Header
    fileHandler.write(
        "fk_booking_id, request_payload, request_status, request_timestamp, request_type, response"
    )

    # Write Each Line
    comma = ","
    newLine = "\n"
    for log in logs:
        h0=wrap_in_quote(log.fk_booking_id)
        h1=wrap_in_quote(log.request_payload)
        h2=wrap_in_quote(log.request_status)
        h3=wrap_in_quote(str(log.request_timestamp))
        h4=wrap_in_quote(log.request_type)
        h5=wrap_in_quote(log.response)
        eachLineText = (
            h0
            + comma
            + h1
            + comma
            + h2
            + comma
            + h3
            + comma
            + h4
            + comma
            + h5
        )
        fileHandler.write(newLine + eachLineText)

    return has_error
