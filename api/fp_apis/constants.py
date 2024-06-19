from django.conf import settings
from api.fps.mrl_sampson import get_account_detail as get_mrl_sampson_account_detail

if settings.ENV == "local":
    DME_LEVEL_API_URL = "http://localhost:3000"
    S3_URL = "./static"
elif settings.ENV == "dev":
    DME_LEVEL_API_URL = "http://52.62.109.115:3000"
    S3_URL = "/opt/s3_public"
elif settings.ENV == "prod":
    DME_LEVEL_API_URL = "http://52.62.102.72:3000"
    S3_URL = "/opt/s3_public"

PRICING_TIME = 40  # seconds

# "Camerons", "Toll", "Sendle", "Capital", "Century", "Fastway", "Startrack", "TNT", "Hunter", "AUSPost", "ATC"
AVAILABLE_FPS_4_FC = [
    "Startrack",
    "AUSPost",
    "TNT",
    "TNT__AFS",
    "Capital",
    "Hunter",
    "Sendle",
    "Allied",
    "Camerons",
    "Toll",
    "Toll Carton__AFS",
    "Century",
    "ATC",
    "Northline",  # Anchor Packaging
    "Blacks",  # Anchor Packaging
    "Blanner",  # Anchor Packaging
    "Bluestar",  # Anchor Packaging
    "Hi-Trans",  # Anchor Packaging
    "VFS",  # Anchor Packaging
    "Sadleirs",  # Anchor Packaging
    "Followmont",  # Anchor Packaging
    "DXT",  # Anchor Packaging
    "Direct Freight",
    "Team Global Express",
    "PFM Corp",
    "Deliver-ME Direct",
    "MRL Sampson",
]

BUILT_IN_PRICINGS = {
    "atc": {"service_types": ["standard", "vip", "express"]},
    "century": {"service_types": ["standard", "vip", "priority"]},
    "camerons": {"service_types": ["Road"]},
    "toll": {"service_types": ["Road Service"]},
    "toll carton__afs": {"service_types": ["IPEC"]},
    "northline": {"service_types": ["standard"]},
    "blacks": {"service_types": ["Road Service"]},
    "blanner": {"service_types": ["Road Service"]},
    "bluestar": {"service_types": ["Road Service"]},
    "startrack": {"service_types": ["EXP"]},
    "hi-trans": {"service_types": ["Road Service"]},
    "vfs": {"service_types": ["Road Service"]},
    "sadleirs": {"service_types": ["Road Service"]},
    "followmont": {"service_types": ["Road Service"]},
    "dxt": {"service_types": ["Road Service", "Pallet"]},
    "tnt": {
        "service_types": [
            #         "Overnight - 9:00 Express*",
            #         "Overnight - 10:00 Express",
            #         "Overnight - 12:00 Express",
            #         "Overnight - Express",
            #         "Overnight - Pay As You Go Satchel Express",
            "Road Express",
            #         "Technology Express Premium",
            #         "Technology Express Sensitive",
            #         "Time Critical Nationwide",
            #         "Failsafe Security Satchel ",
            #         "Failsafe Secure Service",
        ]
    },
    "tnt__afs": {"service_types": ["Road Express"]},
    "hunter": {"service_types": ["Road Express"]},
    "allied": {  # Deactivated
        "service_types": [
            "Road Express",
            "Standard Pallet Rate",
            "Oversized Pallet Rate",
        ]
    },
    "sendle": {"service_types": ["Pro"]},
    # "hunter": {"service_types": ["Road Express"]},
    # "allied": {  # Deactivated
    #     "service_types": [
    #         "Road Express",
    #         "Standard Pallet Rate",
    #         "Oversized Pallet Rate",
    #     ]
    # },
    # "sendle": {"service_types": ["Pro"]},
    "direct freight": {"service_types": ["Road"]},
    "team global express": {"service_types": ["Standard Pallet Service", "IPEC"]},
    "pfm corp": {"service_types": ["Road Express"]},
    "deliver-me direct": {"service_types": ["Express"]},
}

FP_CREDENTIALS = {
    "auspost": {
        "test": {
            "test_bed_0": {
                "accountCode": "2006871123",  # eParcel and International (Stephen)
                "accountKey": "77003860-d920-42d8-a776-1643d65ab179",
                "accountPassword": "x06503301e1ddfb58a7a",
            },
        },
    },
    "startrack": {
        "test": {
            # "test_bed_0": {
            #     "accountCode": "00956684",  # Original
            #     "accountKey": "4a7a2e7d-d301-409b-848b-2e787fab17c9",
            #     "accountPassword": "xab801a41e663b5cb889",
            # },
            # "test_bed_1": {
            #     "accountCode": "00251522",  # ST Premium and ST Express
            #     "accountKey": "71eb98b2-fa8d-4a38-b1b7-6fb2a5c5c486",
            #     "accountPassword": "x9083d2fed4d50aa2ad5",
            # },
            # "test_bed_2": {
            #     "accountCode": "3006871123",  # Same Day Services (Stephen)
            #     "accountKey": "77003860-d920-42d8-a776-1643d65ab179",
            #     "accountPassword": "x06503301e1ddfb58a7a",
            # },
            # "test_bed_3": {
            #     "accountCode": "06871123",  # ST Premium and ST Express (Stephen)
            #     "accountKey": "77003860-d920-42d8-a776-1643d65ab179",
            #     "accountPassword": "x06503301e1ddfb58a7a",
            # },
            "test_bed_4": {
                "accountCode": "01002618",  # ST Postman Collection
                "accountKey": "7be21f35-a067-4ac8-8e12-3f748a792ca3",
                "accountPassword": "uD5W23Kc7YY6cn3shtMy",
            },
        },
        "dme": {
            "DELIVERME_YGBZ": {
                "accountCode": "10170477",
                "accountKey": "99c0e9da-59d1-4494-957c-2a54354c79c4",
                "accountPassword": "iF4eScdu6xxY4TEFob9y",
                "suburb": "WETHERILL PARK",
                "postcode": "2164",
                "state": "NSW",
                "country": "AU",
            },
            "DELIVERME_QLS_YGCZ": {
                "accountCode": "10170478",
                "accountKey": "99c0e9da-59d1-4494-957c-2a54354c79c4",
                "accountPassword": "iF4eScdu6xxY4TEFob9y",
                "suburb": "BLACKTOWN",
                "postcode": "2148",
                "state": "NSW",
                "country": "AU",
            },
            "DELIVERME_XPOZ": {
                "accountCode": "10170226",
                "accountKey": "99c0e9da-59d1-4494-957c-2a54354c79c4",
                "accountPassword": "iF4eScdu6xxY4TEFob9y",
            },
            "DELIVERME_QLD_XPXZ": {
                "accountCode": "10170227",
                "accountKey": "99c0e9da-59d1-4494-957c-2a54354c79c4",
                "accountPassword": "iF4eScdu6xxY4TEFob9y",
            },
            "DELIVERME_VIC_XPZZ": {
                "accountCode": "10170228",
                "accountKey": "99c0e9da-59d1-4494-957c-2a54354c79c4",
                "accountPassword": "iF4eScdu6xxY4TEFob9y",
            },
        },
        "biopak": {
            "BIO - BON": {
                "accountCode": "10145902",
                "accountKey": "d36fca86-53da-4db8-9a7d-3029975aa134",
                "accountPassword": "x81775935aece65541c9",
            },
            "BIO - ROC": {
                "accountCode": "10145593",
                "accountKey": "d36fca86-53da-4db8-9a7d-3029975aa134",
                "accountPassword": "x81775935aece65541c9",
            },
            "BIO - CAV": {
                "accountCode": "10145596",
                "accountKey": "d36fca86-53da-4db8-9a7d-3029975aa134",
                "accountPassword": "x81775935aece65541c9",
            },
            "BIO - TRU": {
                "accountCode": "10149944",
                "accountKey": "d36fca86-53da-4db8-9a7d-3029975aa134",
                "accountPassword": "x81775935aece65541c9",
            },
            "BIO - HAZ": {
                "accountCode": "10145597",
                "accountKey": "d36fca86-53da-4db8-9a7d-3029975aa134",
                "accountPassword": "x81775935aece65541c9",
            },
            "BIO - EAS": {
                "accountCode": "10149943",
                "accountKey": "d36fca86-53da-4db8-9a7d-3029975aa134",
                "accountPassword": "x81775935aece65541c9",
            },
            "BIO - RIC": {
                "accountCode": "10160226",
                "accountKey": "d36fca86-53da-4db8-9a7d-3029975aa134",
                "accountPassword": "x81775935aece65541c9",
            },
            "VIC-HZ": {
                "accountCode": "10164661",
                "accountKey": "d36fca86-53da-4db8-9a7d-3029975aa134",
                "accountPassword": "x81775935aece65541c9",
            },
            "SA-HZ": {
                "accountCode": "10164671",
                "accountKey": "d36fca86-53da-4db8-9a7d-3029975aa134",
                "accountPassword": "x81775935aece65541c9",
            },
            "WA-HZ": {
                "accountCode": "10164660",
                "accountKey": "d36fca86-53da-4db8-9a7d-3029975aa134",
                "accountPassword": "x81775935aece65541c9",
            },
        },
    },
    "hunter": {
        "test": {
            "test_bed_1": {
                "accountCode": "APITEST",
                "accountKey": "55010|XXLFNZRLPW",
                "accountPassword": "",
            },
            # "test_bed_2": {
            #     "accountCode": "DUMMY",
            #     "accountKey": "aHh3czpoeHdz",
            #     "accountPassword": "hxws",
            # },
        },
        "dme": {
            # "live_1": {
            #     "accountCode": "DEMELP",
            #     "accountKey": "55010|XXLFNZRLPW",
            #     "accountPassword": "deliver",
            # },
            # "live_3": {
            #     "accountCode": "DMEBNE",
            #     "accountKey": "55010|XXLFNZRLPW",
            #     "accountPassword": "deliver",
            # },
            # "live_4": {
            #     "accountCode": "DMEPAL",
            #     "accountKey": "55010|XXLFNZRLPW",
            #     "accountPassword": "deliver",
            # },
            # "live_5": {
            #     "accountCode": "DEMELK",
            #     "accountKey": "55010|XXLFNZRLPW",
            #     "accountPassword": "deliver",
            # },
            # "live_6": {
            #     "accountCode": "DMEADL",
            #     "accountKey": "55010|XXLFNZRLPW",
            #     "accountPassword": "deliver",
            # },
            "live_7": {
                "accountCode": "DELIME",
                "accountKey": "55010|XXLFNZRLPW",
                "accountPassword": "deliver",
            },
        },
        # "bunnings": {
        #     "live_bunnings_0": {
        #         "accountCode": "DELIMB",
        #         "accountKey": "REVMSU1COmRlbGl2ZXIyMA==",
        #         "accountPassword": "deliver20",
        #     },
        #     "live_bunnings_1": {
        #         "accountCode": "DELIMS",
        #         "accountKey": "REVMSU1TOmRlbGl2ZXIyMA==",
        #         "accountPassword": "deliver20",
        #     },
        # },
        "plum products australia ltd": {
            "live_plum_0": {
                "accountCode": "PLUMPR",
                "accountKey": "55010|XXLFNZRLPW",
                "accountPassword": "deliver",
            },
        },
    },
    "tnt": {
        "dme": {
            "live_0": {
                "accountCode": "30021385",
                "accountKey": "30021385",
                "accountState": "DELME",
                "accountPassword": "Deliver123",
                "accountUsername": "CIT00000000000098839",
            }
        },
        "jason l": {
            "live_jasonl_0": {
                "accountCode": "21879211",
                "accountKey": "21879211",
                "accountState": "JSONL",
                "accountPassword": "prodTNT123",
                "accountUsername": "CIT00000000000136454",
            },
        },
    },
    "capital": {
        "dme": {
            "live_0": {
                "accountCode": "DMENSW",
                "accountKey": "eYte9AeLruGYmM78",
                "accountState": "NSW",
                "accountUsername": "deliverme",
            }
        }
    },
    "sendle": {
        "test": {
            "test_bed_1": {
                "accountCode": "XXX",
                "accountKey": "greatroyalone_outloo",
                "accountPassword": "KJJrS7xDZZfvfQccyrdStKhh",
            },
        },
        "dme": {
            "live_0": {
                "accountCode": "XXX",
                "accountKey": "bookings_tempo_deliv",
                "accountPassword": "3KZRdXVpfTkFTPknqzjqDXw6",
            }
        },
    },
    "fastway": {
        "dme": {
            "live_0": {
                "accountCode": "XXX",
                "accountKey": "ebdb18c3ce966bc3a4e3f115d311b453",
                "accountState": "FAKE_accountState_01",
            }
        }
    },
    "allied": {
        "test": {
            "test_bed_1": {
                "accountCode": "DELVME",
                "accountKey": "11e328f646051c3decc4b2bb4584530b",
                "accountState": "NSW",
            },
        },
        "bathroom sales direct": {
            "live_0": {
                "accountCode": "bsdsmi",
                "accountKey": "ce0d58fd22ae8619974958e65302a715",
                "accountState": "NSW",
            }
        },
        "dme": {
            "live_0": {
                "accountCode": "DELVME",
                "accountKey": "ce0d58fd22ae8619974958e65302a715",
                "accountState": "NSW",
            }
        },
    },
    "dhl": {
        "dme": {
            "live_0": {
                "accountCode": "XXX",
                "accountKey": "DELIVER_ME_CARRIER_API",
                "accountPassword": "RGVsaXZlcmNhcnJpZXJhcGkxMjM=",
            }
        }
    },
    "camerons": {
        "dme": {
            "live_0": {
                "accountCode": "DEMO_CDE",
                "accountKey": "DMEO_USER",
                "accountPassword": "DEMO_PASS",
            }
        }
    },
    "team global express": {
        # "dme": {
        #     "live_0": {
        #         "accountCode": "XXX",
        #         "accountKey": "DELIVER_ME_CARRIER_API",
        #         "accountPassword": "RGVsaXZlcmNhcnJpZXJhcGkxMjM=",
        #     }
        # }
    },
    "direct freight": {
        "test": {
            "test_bed_1": {
                "accountCode": "21483",
                "accountKey": "42C82374-43C8-4578-B8D7-6A2F86DC2524",
                "SenderSIteID": "0",  # Always 0 unless specified by DFE
            },
        },
        "jason l": {
            "live_0": {
                "accountCode": "24564",
                "accountKey": "AD28D38E-C675-4BC7-92F0-14139291FA00",
                "accountPassword": "",
                "SenderSIteID": "0",  # Always 0 unless specified by DFE
            },
        },
        "aberdeen paper": {
            "live_0": {
                "accountCode": "31989",
                "accountKey": "78C751EF-8A13-4616-88DD-E0B5E224EE61",
                "accountPassword": "",
                "SenderSIteID": "0",  # Always 0 unless specified by DFE
            },
        },
    },
    "camerons": {
        "dme": {
            "live_0": {
                "accountCode": "SPOJIT_TEST_CODE",
                "accountKey": "SPOJIT_TEST_KEY",
                "accountPassword": "SPOJIT_TEST_PWD",
            }
        }
    },
    "dxt": {
        "dme": {
            "live_0": {
                "accountCode": "SPOJIT_TEST_CODE",
                "accountKey": "SPOJIT_TEST_KEY",
                "accountPassword": "SPOJIT_TEST_PWD",
            }
        }
    },
    "northline": {},
    "pfm corp": {},
    # "deliver-me direct": {},
    "mrl sampson": {"dme": {"live_0": get_mrl_sampson_account_detail()}},
}

FP_UOM = {
    "startrack": {"dim": "cm", "weight": "kg"},
    "auspost": {"dim": "cm", "weight": "kg"},
    "hunter": {"dim": "cm", "weight": "kg"},
    "tnt": {"dim": "cm", "weight": "kg"},
    "capital": {"dim": "cm", "weight": "kg"},
    "sendle": {"dim": "cm", "weight": "kg"},
    "fastway": {"dim": "cm", "weight": "kg"},
    "allied": {"dim": "cm", "weight": "kg"},
    "dhl": {"dim": "cm", "weight": "kg"},
    "team global express": {"dim": "cm", "weight": "kg"},
    "direct freight": {"dim": "cm", "weight": "kg"},
    "camerons": {"dim": "cm", "weight": "kg"},
    "dxt": {"dim": "cm", "weight": "kg"},
    "northline": {"dim": "cm", "weight": "kg"},
    "mrl sampson": {"dim": "cm", "weight": "kg"},
}

SPECIAL_FPS = [
    "Deliver-ME",
    "Customer Pickup",
    "Customer Collect",
    "In House Fleet",
]

# security header for DME_NODE
HEADER_FOR_NODE = {"X-SECURITY-TOKEN": "DELIVER-ME-API"}

FP_INFO = {
    "TGE": {
        "ipec": {
            "consignmentPrefix": "89",
        },
        "ins": {
            "consignmentPrefix": "26",
        },
        "ssccPrefix": "0009327510",
    },
    "CAMERONS": {
        "ssccPrefix": "9330915",
    },
}

FP_SPOJIT = {
    "camerons": "691bacb2-8c81-11ee-ac6f-e2a3cdbe54a2",
    "dxt": "4b1f6df6-a9b0-11ee-985a-72699bac6232",
    "northline": "cf679a9a-87f8-11ee-bd1f-e2a3cdbe54a2",
}
