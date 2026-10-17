"""SportIQ settings. Values come from environment variables (see .env.example)."""
import os
from pathlib import Path

import dj_database_url
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


def env_bool(name, default=False):
    return os.getenv(name, str(default)).lower() in ("1", "true", "yes", "on")


SECRET_KEY = os.getenv("SECRET_KEY", "dev-insecure-change-me")
DEBUG = env_bool("DEBUG", True)
ALLOWED_HOSTS = [h for h in os.getenv("ALLOWED_HOSTS", "localhost,127.0.0.1,testserver").split(",") if h]
CSRF_TRUSTED_ORIGINS = [o for o in os.getenv("CSRF_TRUSTED_ORIGINS", "").split(",") if o]
SITE_URL = os.getenv("SITE_URL", "http://127.0.0.1:8000")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.humanize",
    "django.contrib.sitemaps",
    "rest_framework",
    "drf_spectacular",
    "apps.core",
    "apps.accounts",
    "apps.institutions",
    "apps.catalog",
    "apps.learning",
    "apps.assessments",
    "apps.credentials",
    "apps.commerce",
    "apps.support",
    "apps.notifications",
    "apps.analytics",
    "apps.web",
    "apps.backoffice",
    "apps.practicals",
    "apps.live",
    "apps.library",
    "apps.integrations",
    "apps.careers",
    "apps.ai",
    "apps.labs",
    "apps.community",
    "apps.workforce",
    "apps.research",
    "apps.integrity",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.locale.LocaleMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "apps.accounts.middleware.PrivatePageCacheMiddleware",
]

# Sign people out after this much inactivity (each request extends the session).
SESSION_COOKIE_AGE = int(os.getenv("SESSION_IDLE_MINUTES", "240")) * 60
SESSION_SAVE_EVERY_REQUEST = True

ROOT_URLCONF = "sportiq.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.template.context_processors.media",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "apps.core.context_processors.site",
            ],
        },
    },
]

WSGI_APPLICATION = "sportiq.wsgi.application"

DATABASES = {
    "default": dj_database_url.config(
        default=f"sqlite:///{BASE_DIR / 'db.sqlite3'}", conn_max_age=600
    )
}

AUTH_USER_MODEL = "accounts.User"
AUTHENTICATION_BACKENDS = ["apps.accounts.backends.EmailBackend"]
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]
LOGIN_URL = "accounts:login"
LOGIN_REDIRECT_URL = "learning:dashboard"
LOGOUT_REDIRECT_URL = "web:home"


LANGUAGE_CODE = "en"
# Phase 4: interface languages. Non-English strings are draft translations pending expert review.
LANGUAGES = [("en", "English"), ("pcm", "Naijá (Pidgin)"), ("yo", "Yorùbá"), ("ha", "Hausa"), ("ig", "Igbo")]
LOCALE_PATHS = [BASE_DIR / "locale"]
TIME_ZONE = "Africa/Lagos"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"
        if not DEBUG
        else "django.contrib.staticfiles.storage.StaticFilesStorage"
    },
}
DATA_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

EMAIL_BACKEND = os.getenv("EMAIL_BACKEND", "django.core.mail.backends.console.EmailBackend")
EMAIL_HOST = os.getenv("EMAIL_HOST", "")
EMAIL_PORT = int(os.getenv("EMAIL_PORT", "587"))
EMAIL_HOST_USER = os.getenv("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.getenv("EMAIL_HOST_PASSWORD", "")
EMAIL_USE_TLS = env_bool("EMAIL_USE_TLS", True)
DEFAULT_FROM_EMAIL = os.getenv("DEFAULT_FROM_EMAIL", "SportIQ <no-reply@sportiq.edu.ng>")

# SMS (Termii). Empty key = messages are logged instead of sent.
TERMII_API_KEY = os.getenv("TERMII_API_KEY", "")
TERMII_SENDER_ID = os.getenv("TERMII_SENDER_ID", "SportIQ")

# Payments (Paystack). Empty key = test-mode simulator page is used.
PAYSTACK_SECRET_KEY = os.getenv("PAYSTACK_SECRET_KEY", "")
PAYSTACK_PUBLIC_KEY = os.getenv("PAYSTACK_PUBLIC_KEY", "")

# Celery. In dev with no broker, tasks run inline.
CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL", "")
CELERY_TASK_ALWAYS_EAGER = not CELERY_BROKER_URL
CELERY_TASK_EAGER_PROPAGATES = True
CELERY_TIMEZONE = TIME_ZONE

FFMPEG_BINARY = os.getenv("FFMPEG_BINARY", "ffmpeg")

REST_FRAMEWORK = {
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DEFAULT_AUTHENTICATION_CLASSES": ["rest_framework.authentication.SessionAuthentication"],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticatedOrReadOnly"],
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 20,
}
SPECTACULAR_SETTINGS = {
    "TITLE": "SportIQ API",
    "DESCRIPTION": "NIS Digital Sports Academy public API",
    "VERSION": "1.0.0",
}

if not DEBUG:
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = 31536000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
    SECURE_SSL_REDIRECT = env_bool("SECURE_SSL_REDIRECT", True)
    SECURE_HSTS_PRELOAD = True

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "loggers": {"apps": {"handlers": ["console"], "level": "INFO"}},
}

CELERY_BEAT_SCHEDULE = {
    "daily-inactivity": {"task": "apps.learning.tasks.inactivity_reminders", "schedule": 60 * 60 * 24},
    "daily-deadlines": {"task": "apps.learning.tasks.deadline_reminders", "schedule": 60 * 60 * 24},
    "daily-renewals": {"task": "apps.learning.tasks.renewal_reminders", "schedule": 60 * 60 * 24},
    "nightly-snapshot": {"task": "apps.learning.tasks.nightly_snapshot", "schedule": 60 * 60 * 24},
    "daily-outcome-surveys": {"task": "apps.learning.tasks.outcome_surveys", "schedule": 60 * 60 * 24},
    "scheduled-publishing": {"task": "apps.learning.tasks.scheduled_publishing", "schedule": 60 * 15},
    "nightly-ai": {"task": "apps.learning.tasks.ai_maintenance", "schedule": 60 * 60 * 24},
    "daily-reports": {"task": "apps.learning.tasks.scheduled_reports", "schedule": 60 * 60 * 24},
}

# SAMEORIGIN in development so pages can be previewed in frames; DENY in production.
X_FRAME_OPTIONS = "SAMEORIGIN" if DEBUG else "DENY"


# --- Phase 2-4 integrations -------------------------------------------------------------
JITSI_DOMAIN = os.getenv("JITSI_DOMAIN", "meet.jit.si")
INTEGRITY_ENCRYPTION_KEY = os.getenv("INTEGRITY_ENCRYPTION_KEY", "")  # Fernet key; dev derives one from SECRET_KEY

# AI study assistant. Without a key the assistant answers extractively from approved content (no generation).
# AI_PROVIDER: "openai" (default when OPENAI_API_KEY is set) or "anthropic".
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
AI_MODEL = os.getenv("AI_MODEL", "claude-opus-5-5")  # used when AI_PROVIDER=anthropic
AI_PROVIDER = os.getenv("AI_PROVIDER", "openai" if OPENAI_API_KEY else ("anthropic" if ANTHROPIC_API_KEY else ""))

# Single sign-on for institutional users (any OpenID Connect provider, e.g. Microsoft Entra, Google Workspace).
OIDC_PROVIDER_NAME = os.getenv("OIDC_PROVIDER_NAME", "")
OIDC_ISSUER = os.getenv("OIDC_ISSUER", "")
OIDC_CLIENT_ID = os.getenv("OIDC_CLIENT_ID", "")
OIDC_CLIENT_SECRET = os.getenv("OIDC_CLIENT_SECRET", "")
OIDC_ALLOWED_DOMAINS = [d for d in os.getenv("OIDC_ALLOWED_DOMAINS", "").split(",") if d]

# LTI 1.3 tool keys (generated with `python manage.py lti_keys` if absent)
LTI_PRIVATE_KEY_PATH = BASE_DIR / os.getenv("LTI_PRIVATE_KEY_PATH", "keys/lti_private.pem")

# Phase 4 registry / identity adapters: off unless legally authorised and configured.
FEDERATION_REGISTRY_URL = os.getenv("FEDERATION_REGISTRY_URL", "")
FEDERATION_REGISTRY_TOKEN = os.getenv("FEDERATION_REGISTRY_TOKEN", "")
IDENTITY_VERIFICATION_ENABLED = env_bool("IDENTITY_VERIFICATION_ENABLED", False)
IDENTITY_VERIFICATION_PROVIDER = os.getenv("IDENTITY_VERIFICATION_PROVIDER", "sandbox")
FORMS_URLFIELD_ASSUME_HTTPS = True
