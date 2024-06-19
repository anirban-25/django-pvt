from django.conf import settings

if settings.ENV in ["local", "dev"]:  # Non-PROD
    TEMPO_CS_EMAILS = [settings.ADMIN_EMAIL_02]
    RETAILER_COLLECTIONS = [settings.ADMIN_EMAIL_02]
    MICROWAVE_PORTAL_COLLECTIONS = [settings.ADMIN_EMAIL_02]
    ALDI_TV_COLLECTIONS = [settings.ADMIN_EMAIL_02]
    OTHER_CUSTOMER_COLLECTIONS = [settings.ADMIN_EMAIL_02]
    BRINDLEY_WAREHOUSE_COLLECTIONS = [settings.ADMIN_EMAIL_02]
    BULK_SALVAGE_COLLECTIONS = [settings.ADMIN_EMAIL_02]
    TEMPO_AGENT = {"email": settings.ADMIN_EMAIL_02}

else:  # PROD
    TEMPO_CS_EMAILS = ["pickups@tempo.org"]
    TEMPO_AGENT = {"email": "Blake.Wolfson@tempo.org"}
    RETAILER_COLLECTIONS = [
        "Gizelle.Arcayan@tempo.org",
        "RA@tempo.org",
        "Pickups@tempo.org",
        "Cherrylyn.Fokno@tempo.org",
        "Marcus.Abad@tempo.org",
    ]
    MICROWAVE_PORTAL_COLLECTIONS = [
        "Gizelle.Arcayan@tempo.org",
        "RA@tempo.org",
        "Pickups@tempo.org",
        "Cherrylyn.Fokno@tempo.org",
        "Marcus.Abad@tempo.org",
    ]
    ALDI_TV_COLLECTIONS = [
        "Gizelle.Arcayan@tempo.org",
        "AldiTVCollections@tempo.org",
        "Antonette.Hacermida@tempo.org",
        "April.Bala@tempo.org",
    ]
    OTHER_CUSTOMER_COLLECTIONS = [
        "Gizelle.Arcayan@tempo.org",
        "JeanMarc.Paruit@tempo.org",
    ]
    BRINDLEY_WAREHOUSE_COLLECTIONS = [
        "Kristine.Ocana@tempo.org",
    ]
    BULK_SALVAGE_COLLECTIONS = [
        "RA@tempo.org",
        "Pickups@tempo.org",
        "Cherrylyn.Fokno@tempo.org",
    ]


if settings.ENV in ["local", "dev"]:  # Non-PROD
    FP_INFO = {
        "TGE": {
            "spojit_url": "https://deliver-me.spojit.com/gateway/dme/tge",
            "ipec": {
                "account_number": "80638968",
                "source_system_code": "YF48",
                "consignmentPrefix": "897048",
                "ssccPrefix": "9327510",
            },
            "ins": {
                "account_number": "V18511",
                "source_system_code": "YF48",
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
                "source_system_code": "YF48",
                "consignmentPrefix": "897048",
                "ssccPrefix": "9327510",
            },
            "ins": {
                "account_number": "V18511",
                "source_system_code": "YF48",
                "ssccPrefix": "9327510",
            },
        }
    }
