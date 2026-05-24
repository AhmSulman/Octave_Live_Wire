import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent

_on_vercel = bool(os.environ.get("VERCEL") or os.environ.get("VERCEL_ENV"))

# ── Core ─────────────────────────────────────────────────────────────────────

SECRET_KEY = os.environ.get(
    "SECRET_KEY",
    "django-insecure-($)0yh77gshs)bn*@2=_s!!^!**o-!4%-j0uc)la$7i8p%5h@z",
)

DEBUG = os.environ.get("DEBUG", "False") == "True"

ALLOWED_HOSTS = [
    h.strip()
    for h in os.environ.get("ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")
    if h.strip()
]
if _on_vercel:
    ALLOWED_HOSTS += [".vercel.app"]
    _vercel_url = os.environ.get("VERCEL_URL", "")
    if _vercel_url:
        ALLOWED_HOSTS.append(_vercel_url)

# ── CSRF ─────────────────────────────────────────────────────────────────────

CSRF_TRUSTED_ORIGINS = [
    "https://*.vercel.app",
]
_extra_origins = os.environ.get("CSRF_TRUSTED_ORIGINS", "")
if _extra_origins:
    CSRF_TRUSTED_ORIGINS += [o.strip() for o in _extra_origins.split(",") if o.strip()]

# ── Applications ─────────────────────────────────────────────────────────────

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "backing_track_creator",
]

# ── Middleware ────────────────────────────────────────────────────────────────

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "octave_live_wire.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "octave_live_wire.wsgi.application"

# ── Database ──────────────────────────────────────────────────────────────────
# Vercel's filesystem is ephemeral; /tmp persists for the Lambda lifetime only.
# For durable data, swap to PostgreSQL via DATABASE_URL.

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": Path("/tmp/db.sqlite3") if _on_vercel else BASE_DIR / "db.sqlite3",
    }
}

# ── Auth password validators ──────────────────────────────────────────────────

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# ── Internationalisation ──────────────────────────────────────────────────────

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

# ── Static files ──────────────────────────────────────────────────────────────

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}

# ── Media (user uploads) ──────────────────────────────────────────────────────
# Note: Vercel's filesystem is read-only except /tmp. Uploads won't persist
# across Lambda invocations. Use external object storage (S3, Cloudinary, etc.)
# for durable media in production.

MEDIA_URL = "/media/"
MEDIA_ROOT = Path("/tmp/media") if _on_vercel else BASE_DIR / "media"

# ── Security hardening (active when DEBUG=False) ──────────────────────────────

if not DEBUG:
    SECURE_CONTENT_TYPE_NOSNIFF = True
    # Vercel terminates SSL at the edge and forwards via X-Forwarded-Proto.
    # Do NOT set SECURE_SSL_REDIRECT=True here — it causes redirect loops.
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    X_FRAME_OPTIONS = "DENY"
    SECURE_HSTS_SECONDS = 31536000  # 1 year
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True

# Silence the SSL-redirect warning — handled by Vercel's edge, not Django.
SILENCED_SYSTEM_CHECKS = ["security.W008"]

# ── Misc ──────────────────────────────────────────────────────────────────────

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
