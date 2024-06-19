from django.conf import settings

if settings.ENV in ["local", "dev"]:  # Non-PROD
    FP_INFO = {
        "TGE": {
            "spojit_url": "https://deliver-me.spojit.com/gateway/dme/tge",
            "ipec": {
                "account_number": "80638968",
                "source_system_code": "YH80",
                "consignmentPrefix": "897280",
                "ssccPrefix": "9327510",
            },
            "ins": {
                "account_number": "V18511",
                "source_system_code": "YH80",
                "ssccPrefix": "9327510",
            },
        }
    }
else:  # PROD
    FP_INFO = {
        "TGE": {
            "spojit_url": "https://deliver-me.spojit.com/gateway/dme/tge",
            "ipec": {
                "account_number": "80638968",
                "source_system_code": "YH80",
                "consignmentPrefix": "897280",
                "ssccPrefix": "9327510",
            },
            "ins": {
                "account_number": "V18511",
                "source_system_code": "YH80",
                "ssccPrefix": "9327510",
            },
        }
    }
