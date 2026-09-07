from datetime import timedelta
from pathlib import Path

import environ

BASE_DIR = Path(__file__).resolve().parent.parent

env = environ.Env(
    DEBUG=(bool, True),
    ALLOWED_HOSTS=(list, []),
)
environ.Env.read_env(BASE_DIR / ".env")

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = env("DJANGO_SECRET_KEY", default="django-insecure-__CHANGE_ME__")

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = env("DJANGO_DEBUG", default=False)

ALLOWED_HOSTS = env("DJANGO_ALLOWED_HOSTS", default=["*"])

# Application definition
INSTALLED_APPS = [
    'jazzmin',
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.sites',
    # Third-party
    'rest_framework',
    'django_filters',
    'allauth',
    'allauth.account',
    'allauth.socialaccount',
    'allauth.socialaccount.providers.google',
    'dj_rest_auth',
    'dj_rest_auth.registration',
    'rest_framework_simplejwt.token_blacklist',
    'corsheaders',
    # Local
    'shop',
    'accounts.apps.AccountsConfig',
]

MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'allauth.account.middleware.AccountMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'mah_beauty_project.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'mah_beauty_project.wsgi.application'

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

SITE_ID = 1

AUTH_USER_MODEL = 'accounts.User'

# ── Authentication: custom user + backend chain ────────────────────────────
# First backend handles username | email | phone login (FR-001); allauth's
# backend supports its own authentication flows; ModelBackend is the fallback.
AUTHENTICATION_BACKENDS = [
    'accounts.backends.EmailOrPhoneUsernameBackend',
    'allauth.account.auth_backends.AuthenticationBackend',
    'django.contrib.auth.backends.ModelBackend',
]

# ── Email (transactional + reset delivery; console in dev) ─────────────────
# Default mailer uses a console backend in dev. Set DJANGO_EMAIL_BACKEND to an
# SMTP backend and DJANGO_EMAIL_HOST to a provider host for production.
# OPTIONS are only populated when a host is configured so the console backend
# (dev) stays free of unknown-option warnings.
_mailer_backend = env(
    "DJANGO_EMAIL_BACKEND",
    default="django.core.mail.backends.console.EmailBackend",
)

_mailer_options = {}
_email_host = env("DJANGO_EMAIL_HOST", default="")
if _email_host:
    _mailer_options.update(
        {
            "host": _email_host,
            "port": env("DJANGO_EMAIL_PORT", default=587),
            "username": env("DJANGO_EMAIL_HOST_USER", default=""),
            "password": env("DJANGO_EMAIL_HOST_PASSWORD", default=""),
            "use_tls": env("DJANGO_EMAIL_USE_TLS", default=True),
        }
    )

MAILERS = {
    "default": {
        "BACKEND": _mailer_backend,
        "OPTIONS": _mailer_options,
    }
}
DEFAULT_FROM_EMAIL = env("DJANGO_DEFAULT_FROM_EMAIL", default="webmaster@localhost")
ADMIN_EMAIL = env("DJANGO_ADMIN_EMAIL", default="")
SPA_PASSWORD_RESET_URL = env(
    "DJANGO_SPA_PASSWORD_RESET_URL",
    default="http://localhost:5173/reset-password",
)

STATIC_URL = 'static/'
MEDIA_URL = 'media/'
MEDIA_ROOT = BASE_DIR / 'media'
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

LOGIN_REDIRECT_URL = '/'
LOGOUT_REDIRECT_URL = '/'

REST_FRAMEWORK = {
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticatedOrReadOnly',
    ],
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework_simplejwt.authentication.JWTAuthentication',
        'rest_framework.authentication.SessionAuthentication',
    ],
    'DEFAULT_FILTER_BACKENDS': [
        'django_filters.rest_framework.DjangoFilterBackend',
        'rest_framework.filters.SearchFilter',
        'rest_framework.filters.OrderingFilter',
    ],
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 100,
    # FR-015: backoff-not-lockout anon throttling on auth endpoints.
    # dj-rest-auth sets throttle_scope="dj_rest_auth" on login/google/reset.
    'DEFAULT_THROTTLE_CLASSES': [
        'rest_framework.throttling.ScopedRateThrottle',
    ],
    'DEFAULT_THROTTLE_RATES': {
        'dj_rest_auth': '7/min',
    },
}

# ── JWT (SimpleJWT) + dj-rest-auth ─────────────────────────────────────────
SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(minutes=15),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=7),
    'ROTATE_REFRESH_TOKENS': True,
    'BLACKLIST_AFTER_ROTATION': True,
    'AUTH_HEADER_TYPES': ('Bearer',),
}

REST_AUTH = {
    'USE_JWT': True,
    'JWT_AUTH_HTTPONLY': False,
    'TOKEN_MODEL': None,
    'OLD_PASSWORD_FIELD_ENABLED': True,
    'LOGIN_SERIALIZER': 'accounts.serializers.LoginSerializer',
    'REGISTER_SERIALIZER': 'accounts.serializers.RegisterSerializer',
    'USER_DETAILS_SERIALIZER': 'accounts.serializers.UserDetailsSerializer',
    'PASSWORD_RESET_SERIALIZER': 'accounts.serializers.PasswordResetSerializer',
}

# ── django-allauth: account + socialaccount ────────────────────────────────
# MVP concession: ACCOUNT_EMAIL_VERIFICATION="none". Tracked follow-up: flip to
# "mandatory" (and point DJANGO_EMAIL_BACKEND at a real SMTP backend) for
# production (research.md §9).
ACCOUNT_SIGNUP_FIELDS = ['email*', 'username*', 'password1*', 'password2*']
ACCOUNT_UNIQUE_EMAIL = True
ACCOUNT_EMAIL_VERIFICATION = env(
    "DJANGO_ACCOUNT_EMAIL_VERIFICATION",
    default="none",
)

# FR-008: merge google email onto an existing password account, keep both paths.
SOCIALACCOUNT_EMAIL_AUTHENTICATION = True
SOCIALACCOUNT_EMAIL_AUTHENTICATION_AUTO_CONNECT = True
SOCIALACCOUNT_ADAPTER = 'accounts.adapters.MahBeautySocialAccountAdapter'
# allauth 65.14 security notice: trusted-proxy/rate-limit settings
# (ALLAUTH_TRUSTED_ORIGINS + reverse-proxy config) are deployment concerns;
# app-level auth throttling runs via DRF DEFAULT_THROTTLE_RATES above.
SOCIALACCOUNT_PROVIDERS = {
    'google': {
        'APP': {
            'client_id': env('GOOGLE_CLIENT_ID', default=''),
            'secret': env('GOOGLE_CLIENT_SECRET', default=''),
        },
    },
}

# ── eSewa Payment Gateway (via .env) ────────────────────────────────────────
ESEWA_MERCHANT_CODE = env("ESEWA_MERCHANT_CODE", default="")
ESEWA_SECRET_KEY = env("ESEWA_SECRET_KEY", default="")
ESEWA_SANDBOX = env("ESEWA_SANDBOX", default=True)
ESEWA_BASE_URL = env("ESEWA_BASE_URL", default="")
ESEWA_SUCCESS_URL = env("ESEWA_SUCCESS_URL", default="")
ESEWA_FAILURE_URL = env("ESEWA_FAILURE_URL", default="")

# ── Jazzmin Admin UI ─────────────────────────────────────────────────────────
JAZZMIN_SETTINGS = {
    "site_title": "mah_beauty_project Admin",
    "site_header": "mah_beauty_project",
    "site_brand": "mah_beauty_project",
    "welcome_sign": "Welcome to mah_beauty_project",
    "copyright": "mah_beauty_project",
    "show_sidebar": True,
    "navigation_expanded": True,
    "icons": {
        "auth": "fas fa-users-cog",
        "auth.user": "fas fa-user",
        "auth.Group": "fas fa-users",
    },
    "default_icon_parents": "fas fa-chevron-circle-right",
    "default_icon_children": "fas fa-circle",
    "related_modal_active": True,
    "use_google_fonts_cdn": True,
    "show_ui_builder": False,
}

JAZZMIN_UI_TWEAKS = {
    "navbar": "navbar-dark",
    "no_navbar_border": False,
    "navbar_fixed": True,
    "layout_boxed": False,
    "sidebar_fixed": True,
    "sidebar": "sidebar-dark-primary",
    "sidebar_nav_child_indent": True,
    "theme": "default",
    "button_classes": {
        "primary": "btn-primary",
        "secondary": "btn-secondary",
        "info": "btn-info",
        "warning": "btn-warning",
        "danger": "btn-danger",
        "success": "btn-success",
    },
}

# ── CORS ────────────────────────────────────────────────────────────────────
CORS_ALLOW_CREDENTIALS = True
CORS_ALLOWED_ORIGINS = env.list(
    "CORS_ALLOWED_ORIGINS",
    default=[
        "http://localhost:5173",
        "http://localhost:3000",
        "http://localhost:4173",
    ],
)
