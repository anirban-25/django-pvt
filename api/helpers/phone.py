def is_mobile(mobile):
    temp = mobile.replace(" ", "")
    if (
        (len(temp) == 10 and temp[:2] == "04")
        or (len(temp) == 9 and temp[:1] == "4")
        or (len(temp) == 11 and temp[:3] == "614")
        or (len(temp) == 12 and temp[:4] == "+614")
    ):
        return True
    else:
        return False


def format_mobile(mobile):
    temp = mobile.replace(" ", "")
    if len(temp) == 9 and temp[:1] == "4":
        return f"+61{temp}"
    elif len(temp) == 10 and temp[:2] == "04":
        return f"+61{temp[1:]}"
    elif len(temp) == 11 and temp[:3] == "614":
        return f"+{temp}"
    elif len(temp) == 12 and temp[:4] == "+614":
        return temp


def compact_number(phone_number, length=11):
    if not phone_number:  # Case #1: None
        return "0283111500"

    cleaned_number = phone_number.replace(" ", "").replace("+", "")
    cleaned_number = cleaned_number.replace("(", "").replace(")", "")

    # First `0` is still required | 2024-04-16
    # if length == 10:  # Northline case
    #     if len(cleaned_number) == 11 and cleaned_number[0] == "0":
    #         cleaned_number = cleaned_number[1:]

    cleaned_number = cleaned_number[:length]

    if not phone_number:  # Case #2: Space
        return "0283111500"
    else:
        return cleaned_number
