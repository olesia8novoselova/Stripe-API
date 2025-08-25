from pathlib import Path
import environ

BASE_DIR = Path(__file__).resolve().parent.parent

# env
env = environ.Env(
    DEBUG=(bool, False),
    DEFAULT_CURRENCY=(str, 'usd'),
)

env_file = BASE_DIR / '.env'
if env_file.exists():
    environ.Env.read_env(env_file)

SECRET_KEY = env('SECRET_KEY', default='dev-secret-key')
DEBUG = env('DEBUG')
ALLOWED_HOSTS = [h.strip() for h in env('ALLOWED_HOSTS', default='*').split(',')]

# apps
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'catalog',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'config.urls'

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

WSGI_APPLICATION = 'config.wsgi.application'

# DB
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}

# статика
STATIC_URL = 'static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_DIRS = [BASE_DIR / 'static'] if (BASE_DIR / 'static').exists() else []

# локализация
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# Stripe (мультивалюта)
STRIPE_SECRET_KEY = env('STRIPE_SECRET_KEY', default='')  # legacy (не обязателен)
STRIPE_PUBLISHABLE_KEY = env('STRIPE_PUBLISHABLE_KEY', default='')  # legacy (не обязателен)

# основная валюта по умолчанию
DEFAULT_CURRENCY = env('DEFAULT_CURRENCY').lower()

# пары ключей по валютам
STRIPE_KEYS = {
    'usd': {
        'secret': env('STRIPE_SECRET_KEY_USD', default=''),
        'publishable': env('STRIPE_PUBLISHABLE_KEY_USD', default=''),
    },
    'eur': {
        'secret': env('STRIPE_SECRET_KEY_EUR', default=''),
        'publishable': env('STRIPE_PUBLISHABLE_KEY_EUR', default=''),
    },
}

# вернёт секретный ключ Stripe для заданной валюты
def get_stripe_secret_for(currency: str) -> str:
    cur = (currency or DEFAULT_CURRENCY).lower()
    pair = STRIPE_KEYS.get(cur) or STRIPE_KEYS.get(DEFAULT_CURRENCY, {})
    secret = (pair or {}).get('secret', '')
    if not secret:
        # fallback на legacy ключ (если он задан единственный)
        if STRIPE_SECRET_KEY:
            return STRIPE_SECRET_KEY
        raise RuntimeError(f"Не удалось получить Stripe secret key для валюты '{cur}'")
    return secret

# вернёт публичный ключ Stripe для заданной валюты
def get_stripe_publishable_for(currency: str) -> str:
    cur = (currency or DEFAULT_CURRENCY).lower()
    pair = STRIPE_KEYS.get(cur) or STRIPE_KEYS.get(DEFAULT_CURRENCY, {})
    pk = (pair or {}).get('publishable', '')
    if not pk:
        # fallback на legacy ключ (если он задан единственный)
        if STRIPE_PUBLISHABLE_KEY:
            return STRIPE_PUBLISHABLE_KEY
        raise RuntimeError(f"Не удалось получить Stripe publishable key для валюты '{cur}'")
    return pk

SUCCESS_URL = env('SUCCESS_URL', default='http://localhost:8000/success/')
CANCEL_URL = env('CANCEL_URL', default='http://localhost:8000/cancel/')
STRIPE_WEBHOOK_SECRET = env('STRIPE_WEBHOOK_SECRET', default='')