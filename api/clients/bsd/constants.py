from django.conf import settings

if settings.ENV != "prod":
    BSD_CS_EMAILS = [
        "dev.deliverme@gmail.com",
        "darianw@deliver-me.com.au",
        "goldj@deliver-me.com.au",
    ]
    FP_INFO = {
        "TGE": {
            "spojit_url": "https://deliver-me.spojit.com/gateway/dme/tge",
            "ipec": {
                "account_number": "80638968",
                "source_system_code": "YF49",
                "consignmentPrefix": "897049",
                "ssccPrefix": "9327510",
            },
            "ins": {
                "account_number": "V18511",
                "source_system_code": "YF49",
                "ssccPrefix": "9327510",
            },
        }
    }
else:
    BSD_CS_EMAILS = ["warehouse@bathroomsalesdirect.com.au"]
    FP_INFO = {
        "TGE": {
            "spojit_url": "https://deliver-me.spojit.com/gateway/dme/tge",
            "ipec": {
                "account_number": "80638968",
                "source_system_code": "YF49",
                "consignmentPrefix": "897049",
                "ssccPrefix": "9327510",
            },
            "ins": {
                "account_number": "V18511",
                "source_system_code": "YF49",
                "ssccPrefix": "9327510",
            },
        }
    }

# WooCommerce
WC_URL = "https://bathroomsalesdirect.com.au"
WC_CONSUMER_KEY = "ck_a60c770abdc7f5cf3491b951afb2c4f5ac366ab4"
WC_CONSUMER_SECRET = "cs_91aa66dce9939ab75c5aa2b8e16d5e89db6ab609"
WC_VERSION = "wc/v3"
