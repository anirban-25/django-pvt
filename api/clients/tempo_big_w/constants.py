from django.conf import settings

if settings.ENV != "prod":
    FP_INFO = {
        "TGE": {
            "spojit_url": "https://deliver-me.spojit.com/gateway/dme/tge",
            "ipec": {
                "account_number": "80638968",
                "source_system_code": "YF53",
                "consignmentPrefix": "897053",
                "ssccPrefix": "9327510",
            },
            "ins": {
                "account_number": "V18511",
                "source_system_code": "YF53",
                "ssccPrefix": "9327510",
            },
        }
    }
else:
    FP_INFO = {
        "TGE": {
            "spojit_url": "https://deliver-me.spojit.com/gateway/dme/tge",
            "ipec": {
                "account_number": "80638968",
                "source_system_code": "YF53",
                "consignmentPrefix": "897053",
                "ssccPrefix": "9327510",
            },
            "ins": {
                "account_number": "V18511",
                "source_system_code": "YF53",
                "ssccPrefix": "9327510",
            },
        }
    }
