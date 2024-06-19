import logging

from django.db.models import Q
from rest_framework.exceptions import ValidationError

from api.models import Client_Products
from api.clients.jason_l.constants import DIM_BY_GROUP_CODE as JASONL_DIM_BY_GROUP_CODE

logger = logging.getLogger(__name__)


def _append_line(results, line, qty, is_bundle_by_model_number):
    """
    if same e_item_type(model_number), then merge both
    """
    is_new = True

    if is_bundle_by_model_number:
        for index, result in enumerate(results):
            if result["e_item_type"] == line["e_item_type"]:
                results[index]["qty"] += line["qty"]
                is_new = False
                break

    if is_new:
        results.append(line)

    return results


def get_product_items(bok_2s, client, is_web=False, is_bundle_by_model_number=True):
    """
    get all items from array of "model_number" and "qty"
    """
    results = []

    for bok_2 in bok_2s:
        model_number = bok_2.get("model_number")
        qty = bok_2.get("qty")
        # "Jason L"
        zbl_131_decimal_1 = bok_2.get("sequence")
        e_type_of_packaging = bok_2.get("UOMCode")
        zbl_102_text_2 = bok_2.get("ProductGroupCode")

        if not model_number:
            logger.info(f"[GET PRODUCT ITEMS] model_number: {model_number} qty: {qty}")
            raise ValidationError(
                "'model_number' and 'qty' are required for each booking_line"
            )

        products = Client_Products.objects.filter(
            Q(parent_model_number=model_number) | Q(child_model_number=model_number)
        ).filter(fk_id_dme_client=client)

        # JasonL
        if (
            products.count() == 0
            and client.dme_account_num == "1af6bcd2-6148-11eb-ae93-0242ac130002"
        ):
            # raise ValidationError(
            #     f"Can't find Product with provided 'model_number'({model_number})."
            # )

            line = {
                "e_item_type": model_number,
                "description": "(Missed Product)",
                "qty": qty,
                "e_dimUOM": "m",
                "e_weightUOM": "kg",
                "e_dimLength": 0.5,
                "e_dimWidth": 0.5,
                "e_dimHeight": 0.5,
                "e_weightPerEach": 1,
                "zbl_131_decimal_1": zbl_131_decimal_1,
                "zbl_102_text_2": "(Missed Product)",
                "e_type_of_packaging": e_type_of_packaging or "Carton",
            }

            results = _append_line(results, line, qty, is_bundle_by_model_number)
        elif is_web:  # Web - Magento, Shopify
            for product in products:
                if (
                    products.count() > 1
                    and product.child_model_number == product.parent_model_number
                ):
                    continue

                line = {
                    "e_item_type": product.child_model_number,
                    "description": product.description,
                    "qty": qty,
                    "e_dimUOM": product.e_dimUOM,
                    "e_weightUOM": product.e_weightUOM,
                    "e_dimLength": product.e_dimLength,
                    "e_dimWidth": product.e_dimWidth,
                    "e_dimHeight": product.e_dimHeight,
                    "e_weightPerEach": product.e_weightPerEach,
                    "zbl_131_decimal_1": zbl_131_decimal_1,  # Sequence
                    "zbl_102_text_2": zbl_102_text_2,  # ProductGroupCode
                    "e_type_of_packaging": e_type_of_packaging or "Carton",
                }

                results = _append_line(results, line, qty, is_bundle_by_model_number)
        else:  # Biz - Sap/b1, Pronto
            _product = None
            for product in products:
                if product.child_model_number != product.parent_model_number:
                    _product = product

                if (
                    product.child_model_number == product.parent_model_number
                    and product.e_dimLength
                    and product.e_dimWidth
                    and product.e_dimHeight
                ):
                    _product = product

            if _product:
                product = _product
                line = {
                    "e_item_type": product.child_model_number,
                    "description": product.description
                    if not product.is_ignored
                    else f"{product.description} (Ignored)",
                    "qty": qty,
                    "e_dimUOM": product.e_dimUOM,
                    "e_weightUOM": product.e_weightUOM,
                    "e_dimLength": product.e_dimLength,
                    "e_dimWidth": product.e_dimWidth,
                    "e_dimHeight": product.e_dimHeight,
                    "e_weightPerEach": product.e_weightPerEach,
                    "zbl_131_decimal_1": zbl_131_decimal_1,
                    "zbl_102_text_2": zbl_102_text_2,
                    "e_type_of_packaging": e_type_of_packaging or "Carton",
                }

                results = _append_line(results, line, qty, is_bundle_by_model_number)

    # Jason L: populate DIMs by ProductGroupCode
    # for result in results:
    #     if (
    #         result["zbl_102_text_2"]
    #         and not "(Ignored)" in result["zbl_102_text_2"]
    #         and result["e_dimLength"] == 1
    #         and result["e_dimWidth"] == 1
    #         and result["e_dimHeight"] == 1
    #     ):
    #         if result["zbl_102_text_2"] in JASONL_DIM_BY_GROUP_CODE:
    #             logger.info(
    #                 f"[GET PRODUCT ITEMS] Dims with GroupCode: {result['zbl_102_text_2']}, ItemCode: {result['e_item_type']}"
    #             )
    #             dims = JASONL_DIM_BY_GROUP_CODE[result["zbl_102_text_2"]]
    #             result["e_dimLength"] = dims["length"]
    #             result["e_dimWidth"] = dims["width"]
    #             result["e_dimHeight"] = dims["height"]
    #             result["e_weightPerEach"] = dims["weight"]

    logger.info(f"[GET PRODUCT ITEMS] {results}")
    return results


def find_missing_model_numbers(bok_2s, client):
    _missing_model_numbers = []

    for bok_2 in bok_2s:
        model_number = bok_2.get("model_number")
        products = Client_Products.objects.filter(
            Q(parent_model_number=model_number) | Q(child_model_number=model_number)
        ).filter(fk_id_dme_client=client)

        if not products.exists():
            _missing_model_numbers.append(model_number)

    return _missing_model_numbers
