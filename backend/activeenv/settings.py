"""
Django settings for the ActiveEnv project.

Configuration is environment-driven (see .env.example at the repo root) so the
same code runs locally and on Alibaba Cloud ECS without edits.
"""

import os
import sys
from pathlib import Path

import environ

BASE_DIR = Path(__file__).resolve().parent.parent

# --- Environment ---------------------------------------------------------
# Reads from process env; falls back to ../.env (repo root) during local dev.
# Under pytest we skip the .env file so the suite is hermetic and relies only on
# the in-memory SQLite config set in conftest.py.
env = environ.Env(
    DJANGO_DEBUG=(bool, False),
)
if "pytest" not in sys.modules:
    environ.Env.read_env(BASE_DIR.parent / ".env")

SECRET_KEY = env("DJANGO_SECRET_KEY", default="dev-insecure-change-me")
DEBUG = env.bool("DJANGO_DEBUG", default=True)
ALLOWED_HOSTS = env.list("DJANGO_ALLOWED_HOSTS", default=["localhost", "127.0.0.1"])


# --- Applications --------------------------------------------------------

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Third-party
    "rest_framework",
    "corsheaders",
    # Local
    "api",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "activeenv.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "activeenv.wsgi.application"
ASGI_APPLICATION = "activeenv.asgi.application"


# --- Database ------------------------------------------------------------
# Postgres in every environment. Uses DATABASE_URL if present, else the
# discrete POSTGRES_* vars. Falls back to local sqlite only if neither is set
# (keeps `manage.py check` runnable before infra is up).

if env("DATABASE_URL", default=""):
    DATABASES = {"default": env.db("DATABASE_URL")}
elif env("POSTGRES_DB", default=""):
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": env("POSTGRES_DB"),
            "USER": env("POSTGRES_USER", default="activeenv"),
            "PASSWORD": env("POSTGRES_PASSWORD", default="activeenv"),
            "HOST": env("POSTGRES_HOST", default="localhost"),
            "PORT": env("POSTGRES_PORT", default="5432"),
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }


# --- Password validation -------------------------------------------------

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]


# --- I18N ----------------------------------------------------------------

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True


# --- Static --------------------------------------------------------------

STATIC_URL = "static/"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"


# --- Django REST Framework ----------------------------------------------

REST_FRAMEWORK = {
    "DEFAULT_RENDERER_CLASSES": [
        "rest_framework.renderers.JSONRenderer",
        "rest_framework.renderers.BrowsableAPIRenderer",
    ],
}


# --- CORS ----------------------------------------------------------------
# The Next.js dev server talks to this API from a different origin.

CORS_ALLOWED_ORIGINS = env.list(
    "CORS_ALLOWED_ORIGINS",
    default=["http://localhost:3000", "http://127.0.0.1:3000"],
)


# --- Celery / Redis ------------------------------------------------------

CELERY_BROKER_URL = env("REDIS_URL", default="redis://localhost:6379/0")
CELERY_RESULT_BACKEND = env("REDIS_URL", default="redis://localhost:6379/0")
CELERY_TASK_TRACK_STARTED = True
CELERY_TASK_TIME_LIMIT = 60 * 10


# --- Qwen (Alibaba Cloud Model Studio, OpenAI-compatible) ----------------

QWEN_API_KEY = env("DASHSCOPE_API_KEY", default="")
QWEN_BASE_URL = env(
    "QWEN_BASE_URL",
    default="https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
)
QWEN_MODEL = env("QWEN_MODEL", default="qwen-plus")


# --- Secret vault --------------------------------------------------------
# Probeable secret values are stored encrypted at rest (never plaintext) so a
# probe / re-probe can use them. Uses ACTIVEENV_ENCRYPTION_KEY if provided
# (a urlsafe-base64 Fernet key), otherwise derives one from SECRET_KEY for dev.

import base64 as _base64  # noqa: E402
import hashlib as _hashlib  # noqa: E402

_vault_key = env("ACTIVEENV_ENCRYPTION_KEY", default="")
if not _vault_key:
    _vault_key = _base64.urlsafe_b64encode(
        _hashlib.sha256(SECRET_KEY.encode()).digest()
    ).decode()
SECRET_VAULT_KEY = _vault_key
