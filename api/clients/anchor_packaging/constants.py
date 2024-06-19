from django.conf import settings

WAREHOUSE_MAPPINGS = {
    "MD1": "MCPHEE_SYD_MD1",
    "MD2": "MCPHEE_BRIS_MD2",
    "WA1": "MCPHEE_HAZ_MD3",
    "NQ1": "CARGO_WISE_NORTH_QLD_NQ1",
    "LG1": "CARGO_WISE_MEL_LG1",
    "AFS": "CARGO_WISE_MEL_AFS",
}

AP_FREIGHTS = [
    "TNT__AFS",
    "Toll__AFS",
    "Blacks",
    "Blanner",
    "Bluestar",
    "Hi-Trans",
    "VFS",
    "Followmont",
]

if settings.ENV != "prod":
    FP_INFO = {
        "TGE": {
            "spojit_url": "https://deliver-me.spojit.com/gateway/dme/tge",
            "ipec": {
                "account_number": "80638968",
                "source_system_code": "YF47",
                "consignmentPrefix": "897047",
                "ssccPrefix": "9327510",
            },
            "ins": {
                "account_number": "V18511",
                "source_system_code": "YF47",
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
                "source_system_code": "YF47",
                "consignmentPrefix": "897047",
                "ssccPrefix": "9327510",
            },
            "ins": {
                "account_number": "V18511",
                "source_system_code": "YF47",
                "ssccPrefix": "9327510",
            },
        }
    }
