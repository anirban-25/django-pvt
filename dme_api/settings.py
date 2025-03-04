"""
Django settings for DeliverMe project.

Generated by 'django-admin startproject' using Django 2.1.2.

For more information on this file, see
https://docs.djangoproject.com/en/2.1/topics/settings/

For the full list of settings and their values, see
https://docs.djangoproject.com/en/2.1/ref/settings/
"""

import os
import datetime

# Build paths inside the project like this: os.path.join(BASE_DIR, ...)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/2.1/howto/deployment/checklist/

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = os.environ["SECRET_KEY"]

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = os.environ["DEBUG"]

ALLOWED_HOSTS = ["*"]

# Env setting - local, dev, prod
ENV = os.environ["ENV"]

BUGSNAG = {"api_key": os.environ["BUGSNAG_API_KEY"]}

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django_filters",
    "api",
    "rest_framework",
    "rest_framework_xml",
    "django_rest_passwordreset",
    "corsheaders",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "bugsnag.django.middleware.BugsnagMiddleware",
]

ROOT_URLCONF = "dme_api.urls"

# Rest Framework
REST_FRAMEWORK = {
    "DEFAULT_PERMISSION_CLASSES": ("rest_framework.permissions.IsAuthenticated",),
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework.authentication.SessionAuthentication",
        "rest_framework.authentication.BasicAuthentication",
        "rest_framework_jwt.authentication.JSONWebTokenAuthentication",
    ),
    "DEFAULT_RENDERER_CLASSES": (
        "rest_framework.renderers.JSONRenderer",
        "rest_framework_xml.renderers.XMLRenderer",
    ),
    "DEFAULT_PARSER_CLASSES": (
        "rest_framework.parsers.JSONParser",
        "rest_framework_xml.parsers.XMLParser",
    ),
}

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [os.path.join(BASE_DIR, "templates")],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "django.template.context_processors.media",
            ]
        },
    }
]

WSGI_APPLICATION = "dme_api.wsgi.application"


# Database
# https://docs.djangoproject.com/en/2.1/ref/settings/#databases

DATABASES = {
    "default": {
        "ENGINE": os.environ["DB_ENGINE"],
        "NAME": os.environ["DB_NAME"],
        "USER": os.environ["DB_USER"],
        "PASSWORD": os.environ["DB_PASSWORD"],
        "HOST": os.environ["DB_HOST"],
        "PORT": int(os.environ["DB_PORT"]),
    },
    "shared_mail": {
        "ENGINE": os.environ["DB_ENGINE"],
        "NAME": os.environ["SHARED_DB_NAME"],
        "USER": os.environ["DB_USER"],
        "PASSWORD": os.environ["DB_PASSWORD"],
        "HOST": os.environ["DB_HOST"],
        "PORT": int(os.environ["DB_PORT"]),
    },
}

# Cache

CACHES = {
    "default": {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": "redis://127.0.0.1:6379/1",
        "OPTIONS": {"CLIENT_CLASS": "django_redis.client.DefaultClient"},
        "KEY_PREFIX": "dme",
    }
}

CACHE_TTL = 60 * 15  # 15 minutes

# Password validation
# https://docs.djangoproject.com/en/2.1/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"
    },
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]


# Internationalization
# https://docs.djangoproject.com/en/2.1/topics/i18n/

LANGUAGE_CODE = "en-us"

TIME_ZONE = "UTC"

USE_I18N = True

USE_L10N = True

USE_TZ = True


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/2.1/howto/static-files/

STATIC_URL = "/static/"

STATICFILES_DIRS = (os.path.join(BASE_DIR, "static"),)

STATIC_ROOT = os.path.join(BASE_DIR, "staticfiles")

LOGIN_REDIRECT_URL = "/"
LOGOUT_REDIRECT_URL = "/"

MEDIA_URL = "/media/"
MEDIA_ROOT = os.path.join(BASE_DIR, "media")

CORS_ORIGIN_ALLOW_ALL = True

CORS_ALLOW_HEADERS = (
    "accept",
    "accept-encoding",
    "authorization",
    "content-type",
    "dnt",
    "origin",
    "user-agent",
    "x-requested-with",
    "cache-control",
)

JWT_AUTH = {
    "JWT_EXPIRATION_DELTA": datetime.timedelta(
        seconds=int(os.environ["JWT_EXPIRATION_DELTA"])
    )
}  # Test case

# Email setting
EMAIL_BACKEND = os.environ["EMAIL_BACKEND"]
EMAIL_USE_TLS = os.environ["EMAIL_USE_TLS"]
EMAIL_HOST = os.environ["EMAIL_HOST"]
EMAIL_PORT = int(os.environ["EMAIL_PORT"])
EMAIL_HOST_USER = os.environ["EMAIL_HOST_USER"]
EMAIL_HOST_PASSWORD = os.environ["EMAIL_HOST_PASSWORD"]

EMAIL_URL = "/templates/email/"
EMAIL_ROOT = os.path.join(BASE_DIR, "templates/email")


# Logging setting
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "[%(asctime)s] %(levelname)s [%(name)s:%(lineno)s] %(message)s",
            "datefmt": "%d/%b/%Y %H:%M:%S",
        }
    },
    "handlers": {
        "console": {
            "level": "INFO",
            "class": "logging.StreamHandler",
            "formatter": "verbose",
        },
        "file": {
            "level": "INFO",
            "class": "logging.handlers.RotatingFileHandler",
            "filename": os.path.join(BASE_DIR, "logs/debug.log"),
            "backupCount": 50,  # keep at most 50 log files
            "maxBytes": 1024 * 1024 * 30,  # 10 MB
            "formatter": "verbose",
        },
    },
    "loggers": {"": {"handlers": ["file"], "level": "INFO", "propagate": True}},
}

if ENV == "prod":
    LOGGING["handlers"]["bugsnag"] = {
        "level": "ERROR",
        "class": "bugsnag.handlers.BugsnagHandler",
    }


# S3 url
S3_URL = os.environ["S3_URL"]

WEB_SITE_URL = os.environ["WEB_SITE_URL"]
STATIC_PUBLIC = os.environ["STATIC_PUBLIC"]
STATIC_PRIVATE = os.environ["STATIC_PRIVATE"]

# Zoho
CLIENT_ID_ZOHO = os.environ["CLIENT_ID_ZOHO"]
CLIENT_SECRET_ZOHO = os.environ["CLIENT_SECRET_ZOHO"]
ORG_ID = os.environ["ORG_ID"]
REDIRECT_URI_ZOHO = os.environ["REDIRECT_URI_ZOHO"]


# Twilio
TWILIO = {
    "APP_SID": os.environ.get("TWILIO_APP_SID"),
    "TOKEN": os.environ.get("TWILIO_TOKEN"),
    "AUTHY_API_KEY": os.environ.get("TWILIO_AUTHY_API_KEY"),
    "AUTHY_CODE_LENGTH": 5,
    "NUMBER": os.environ.get("TWILIO_NUMBER"),
    "EVENTS": ["initiated", "ringing", "answered", "completed"],
    "RECORD": True,
}


# Emails
ADMIN_EMAIL_01 = os.environ["ADMIN_EMAIL_01"]
ADMIN_EMAIL_02 = os.environ["ADMIN_EMAIL_02"]
SUPPORT_CENTER_EMAIL = os.environ["SUPPORT_CENTER_EMAIL"]
