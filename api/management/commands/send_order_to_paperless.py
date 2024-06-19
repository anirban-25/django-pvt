from django.core.management.base import BaseCommand

from api.models import BOK_1_headers
from api.operations import paperless


class Command(BaseCommand):
    def add_arguments(self, parser):
        parser.add_argument("bok_1_pk")

    def handle(self, *args, **options):
        # print("----- Sending order info to Paperless... -----")
        bok_1_pk = options["bok_1_pk"]
        bok_1 = BOK_1_headers.objects.filter(pk=bok_1_pk).first()

        if not bok_1:
            # print(f"@100 Error: There is no BOK_1 with given pk{bok_1_pk}")

        result = paperless.send_order_info(bok_1)
        # print("@101 Result: ", result)
        # print("\n----- Finished! -----")
