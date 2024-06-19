from django.conf import settings

if settings.ENV != "prod":
    CSV_DIR = "/Users/admin/work/goldmine/scripts/dir01/"
    ARCHIVE_CSV_DIR = "/Users/admin/work/goldmine/scripts/dir02/"
    FP_INFO = {
        "TGE": {
            "spojit_url": "https://biopak.spojit.com/gateway/biopak/tge",
            "ipec": {
                "consignmentPrefix": {
                    "BIO - CAV": "887999",
                    "BIO - TRU": "887999",
                    "BIO - HAZ": "887999",
                    "BIO - EAS": "887999",
                    "BIO - RIC": "887999",
                    "BIO - FDM": "887999",
                },
                "ssccPrefix": {
                    "BIO - CAV": "9327510",
                    "BIO - TRU": "9327510",
                    "BIO - HAZ": "9327510",
                    "BIO - EAS": "9327510",
                    "BIO - RIC": "9327510",
                    "BIO - FDM": "9327510",
                },
            },
            "ins": {
                "consignmentPrefix": {
                    "BIO - CAV": "",
                    "BIO - TRU": "",
                    "BIO - HAZ": "",
                    "BIO - EAS": "",
                    "BIO - RIC": "",
                    "BIO - FDM": "",
                },
                "ssccPrefix": {
                    "BIO - CAV": "9327510",
                    "BIO - TRU": "9327510",
                    "BIO - HAZ": "9327510",
                    "BIO - EAS": "9327510",
                    "BIO - RIC": "9327510",
                    "BIO - FDM": "9327510",
                },
            },
        }
    }
else:
    CSV_DIR = "/home/cope_au/dme_sftp/startrack_au/pickup_ext/indata/"
    ARCHIVE_CSV_DIR = "/home/cope_au/dme_sftp/startrack_au/pickup_ext/archive/"
    FP_INFO = {
        "TGE": {
            "spojit_url": "https://biopak.spojit.com/gateway/biopak/tge",
            "ipec": {
                "consignmentPrefix": {
                    "BIO - CAV": "896623",
                    "BIO - TRU": "896625",
                    "BIO - HAZ": "896624",
                    "BIO - EAS": "896622",
                    "BIO - RIC": "896621",
                    "BIO - FDM": "896626",
                    "SA-HZ": "896634",
                    "WA-HZ": "896635",
                },
                "ssccPrefix": {
                    "BIO - CAV": "9327510",
                    "BIO - TRU": "9327510",
                    "BIO - HAZ": "9327510",
                    "BIO - EAS": "9327510",
                    "BIO - RIC": "9327510",
                    "BIO - FDM": "9327510",
                    "SA-HZ": "9327510",
                    "WA-HZ": "9327510",
                },
            },
            "ins": {
                "consignmentPrefix": {
                    "BIO - CAV": "",
                    "BIO - TRU": "",
                    "BIO - HAZ": "",
                    "BIO - EAS": "",
                    "BIO - RIC": "",
                    "BIO - FDM": "",
                    "SA-HZ": "",
                    "WA-HZ": "",
                },
                "ssccPrefix": {
                    "BIO - CAV": "9327510",
                    "BIO - TRU": "9327510",
                    "BIO - HAZ": "9327510",
                    "BIO - EAS": "9327510",
                    "BIO - RIC": "9327510",
                    "BIO - FDM": "9327510",
                    "SA-HZ": "9327510",
                    "WA-HZ": "9327510",
                },
            },
        }
    }


SPOJIT_TOKEN = "eyJ0eXAiOiJKV1QiLCJhbGciOiJSUzI1NiJ9.eyJpYXQiOjE2ODQyOTQxMzYsImV4cCI6NDgzOTk2NzczNiwidXNlcklkIjoyLCJpZCI6NCwiZGF0ZSI6IjE2ODQyOTQxMzYifQ.UjS-63Ozl7bLAWyWP2PNZmsexP0SiMVhUgVfQfHwBVUox_7iht3nTUVpQsqcru8B4LxA43AS7yj8sjI2LRjuvnjZbXDTVAVeW8csXFtnA1yHVjPOCQwbEWRfJdTzkr19EkfjJn8EucEoniZ_teK4ujKJLN-7ENiQvsMWD5lmjNZm5OzoyIa5URSasMFRZjD2Gkk25Sdin9_YIV07UZRiSVP_liEaKqdNyb8-DOj-9u-5g-F33U1MYeZYJtOsBOV8z59IIa6EGwqWIQkYs-7nmulXP6pXgMMkkHjUm9ixHXGvivtE2Y-p22Ttcz_xd9GdC-YF4uw1GubKQ72woHfpwgZyKbCwEFiosyTzqGaotvhrV7FpBal4kYaKNaubKK7hX8VbwPLlPuEgaLHmZgLW5NkNDr1LZcp7k50L1ySLQYft4J93A8mO3UyTsv_77PKI0YoFkcxktt95wA8Zrslf8tP_hJh-CsQciFFbZYr6jvAXROT9UUhEhQAmn90QtiP2UfZIjvJiBUS8H-8TDvS-hm5s_MaPUtPKHJR1_NISF57_uWzuCWlC3a5R6LuQgxqJ789EhDkO5ZYHG2PpsKbDJZgy6QA2v16DeiEErqSL5C6ckYBOhokaPUjvAhPzreGCdz3HFduiHaDifvXIP9o9HJRJ14Co5bUzAWtxt-YdgBg"

FTP_INFO = {
    "name": "BIOPAK",
    "host": "ftp.biopak.com.au",
    "username": "dme_biopak",
    "password": "3rp2NcHS",
    "sftp_filepath": "/DME/POD/",
    "local_filepath": CSV_DIR,
    "local_filepath_archive": ARCHIVE_CSV_DIR,
}
