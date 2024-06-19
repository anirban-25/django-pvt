from api.models import PostalCode


def get_postal_codes(name):
    postal_code = PostalCode.objects.get(name=name)
    range = postal_code.range
    return range.split(", ")
