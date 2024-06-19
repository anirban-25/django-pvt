def calc_checksum(ai_1, extension_digit, prefix2, prefix3):
    value = f"{ai_1}{extension_digit}{prefix2}{prefix3}"
    muli_values = [3, 1]
    index = 0
    sum = 0

    for _iter in value[::-1]:
        iterSum = int(_iter) * muli_values[index % 2]
        index += 1
        sum += iterSum

    checksum = 10 - (sum % 10)
    checksum = 0 if checksum == 10 else checksum
    return checksum
