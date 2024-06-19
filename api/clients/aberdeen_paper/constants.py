from django.conf import settings

if settings.ENV != "prod":
    CS_EMAIL = settings.ADMIN_EMAIL_02

    FP_INFO = {
        "TGE": {
            "spojit_url": "https://deliver-me.spojit.com/gateway/dme/tge",
            "ipec": {
                "account_number": "80638968",
                "source_system_code": "YF46",
                "consignmentPrefix": "897046",
                "ssccPrefix": "9327510",
            },
            "ins": {
                "account_number": "V18511",
                "source_system_code": "YF46",
                "ssccPrefix": "9327510",
            },
        }
    }
else:
    CS_EMAIL = "jfranklin@aberdeenpaper.com.au"

    FP_INFO = {
        "TGE": {
            "spojit_url": "https://deliver-me.spojit.com/gateway/dme/tge",
            "ipec": {
                "account_number": "80638968",
                "source_system_code": "YF46",
                "consignmentPrefix": "897046",
                "ssccPrefix": "9327510",
            },
            "ins": {
                "account_number": "V18511",
                "source_system_code": "YF46",
                "ssccPrefix": "9327510",
            },
        }
    }
