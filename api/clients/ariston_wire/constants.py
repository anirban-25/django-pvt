from django.conf import settings

if settings.ENV in ["local", "dev"]:  # Non-PROD
    ARISTON_WIRE_CS_EMAILS = [
        "dev.deliverme@gmail.com",
        "darianw@deliver-me.com.au",
        "goldj@deliver-me.com.au",
    ]
    ARISTON_WIRE_FPS = {
        "FP1": {
            "freight_provider": "BKC",
            "email": "darianw@deliver-me.com.au",
            "postal_codes": ["1000-2000", "2500", "3000-4000"],
        },
        "FP2": {
            "freight_provider": "Charter Trucks",
            "email": "dev.deliverme@gmail.com",
            "postal_codes": ["5000-6000"],
        },
        "FP3": {
            "freight_provider": "Arrow Transport",
            "email": "goldj@deliver-me.com.au",
            "postal_codes": ["3000-4000"],
        },
    }
    # FP_INFO = {
    #     "TGE": {
    #         "spojit_url": "https://deliver-me.spojit.com/gateway/dme/tge",
    #         "ipec": {
    #             "account_number": "80638968",
    #             "source_system_code": "YF48",
    #             "consignmentPrefix": "897048",
    #             "ssccPrefix": "9327510",
    #         },
    #         "ins": {
    #             "account_number": "V18511",
    #             "source_system_code": "YF48",
    #             "ssccPrefix": "9327510",
    #         },
    #     }
    # }
else:  # PROD
    ARISTON_WIRE_CS_EMAILS = ["cs@aristonwire.com.au"]
    ARISTON_WIRE_FPS = {
        "FP1": {
            "freight_provider": "BKC",
            "email": "darianw@deliver-me.com.au",
            "postal_codes": [],
        },
        "FP2": {
            "freight_provider": "Charter Trucks",
            "email": "darianw@yopmail.com",
            "postal_codes": [],
        },
        "FP3": {
            "freight_provider": "Arrow Transport",
            "email": "anthony@aristonwire.com.au",
            "postal_codes": [],
        },
    }
    # FP_INFO = {
    #     "TGE": {
    #         "spojit_url": "https://deliver-me.spojit.com/gateway/dme/tge",
    #         "ipec": {
    #             "account_number": "80638968",
    #             "source_system_code": "YF48",
    #             "consignmentPrefix": "897048",
    #             "ssccPrefix": "9327510",
    #         },
    #         "ins": {
    #             "account_number": "V18511",
    #             "source_system_code": "YF48",
    #             "ssccPrefix": "9327510",
    #         },
    #     }
    # }

ARISTON_WIRE_FP_NAMES = ["BKC", "Charter Trucks", "Arrow Transport"]
