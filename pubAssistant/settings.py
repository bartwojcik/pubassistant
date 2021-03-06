"""
Django settings for pubAssistant project.

Generated by 'django-admin startproject' using Django 1.9.3.

For more information on this file, see
https://docs.djangoproject.com/en/1.9/topics/settings/

For the full list of settings and their values, see
https://docs.djangoproject.com/en/1.9/ref/settings/
"""
import logging
import os, sys
from datetime import timedelta

import psycopg2
from celery.schedules import crontab
from kombu import Queue, Exchange

# Build paths inside the project like this: os.path.join(BASE_DIR, ...)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/1.9/howto/deployment/checklist/

# SECURITY WARNING: keep the secret key used in production secret!
# TODO when creating release image regenerate SECRET_KEY automatically
SECRET_KEY = os.getenv('DJANGO_SECRET_KEY', '2b^xlaxp(_g68lovmfn$#@vb!5pm!7r1du1iqwr3zouf$xg)@(')
# binascii.hexlify(os.urandom(24))

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = bool(os.getenv('DEBUG', False))
LOGLEVEL_DICT = {
    'DEBUG': logging.DEBUG,
    'INFO': logging.INFO,
    'WARNING': logging.WARNING,
    'ERROR': logging.ERROR,
    'CRITICAL': logging.CRITICAL
}
LOGLEVEL = LOGLEVEL_DICT[os.getenv('LOGLEVEL', 'DEBUG' if DEBUG else 'INFO')]

if DEBUG:
    LOGGING = {
        'version': 1,
        'disable_existing_loggers': True,
        'handlers': {
            'console': {
                'level': LOGLEVEL,
                'class': 'logging.StreamHandler',
                'stream': sys.stdout
            },
        },
        'loggers': {
            'django': {
                'handlers': ['console'],
                'level': logging.INFO,
                'propagate': True
            },
            'main_assistant': {
                'handlers': ['console'],
                'level': LOGLEVEL,
                'propagate': True
            },
            'paper_analyzer': {
                'handlers': ['console'],
                'level': LOGLEVEL,
                'propagate': True
            },
            'hype_cycle_graph': {
                'handlers': ['console'],
                'level': LOGLEVEL,
                'propagate': True
            },
            'author_browser': {
                'handlers': ['console'],
                'level': LOGLEVEL,
                'propagate': True
            },
        },
    }
else:
    logdir = os.getenv('DJANGO_LOGDIR', '/var/pubassistant/logs')
    logfile = os.getenv('DJANGO_LOGFILE', 'django.log')
    LOGGING = {
        'version': 1,
        'disable_existing_loggers': True,
        'formatters': {
            'standard': {
                'format': '[%(asctime)s, %(pathname)s:%(funcName)s] %(levelname)s: %(message)s',
                'datefmt': '%Y-%m-%d %H:%M:%S'
            }
        },
        'handlers': {
            'file': {
                'level': LOGLEVEL,
                'class': 'logging.handlers.RotatingFileHandler',
                'filename': logdir + '/' + logfile,
                'maxBytes': 1024 * 1024 * 20,
                'backupCount': 5,
                'formatter': 'standard'
            },
        },
        'loggers': {
            # 'django': {
            #     'handlers': ['file'],
            #     'level': logging.INFO,
            #     'propagate': True
            # },
            'main_assistant': {
                'handlers': ['file'],
                'level': LOGLEVEL,
                'propagate': True
            },
            'paper_analyzer': {
                'handlers': ['file'],
                'level': LOGLEVEL,
                'propagate': True
            },
            'hype_cycle_graph': {
                'handlers': ['file'],
                'level': LOGLEVEL,
                'propagate': True
            },
            'author_browser': {
                'handlers': ['file'],
                'level': LOGLEVEL,
                'propagate': True
            },
        },
    }

ALLOWED_HOSTS = []
ALLOWED_HOSTS.extend(os.getenv('DJANGO_ALLOWED_HOSTS', '').split(';'))

# Application definition

INSTALLED_APPS = [
    'main_assistant',
    'paper_analyzer',
    'hype_cycle_graph',
    'author_browser',
    'rest_framework',
    'haystack',
    'django.contrib.postgres',
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
]

MIDDLEWARE_CLASSES = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.auth.middleware.SessionAuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'pubAssistant.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
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

WSGI_APPLICATION = 'pubAssistant.wsgi.application'

SESSION_ENGINE = 'django.contrib.sessions.backends.cached_db'

CACHES = {
    'default': {
        'BACKEND': 'django_redis.cache.RedisCache',
        'LOCATION': 'redis://{}:{}/1'.format(os.getenv('CACHE_HOST', 'cache'), os.getenv('CACHE_PORT', '6379')),
        'OPTIONS': {
            'CLIENT_CLASS': 'django_redis.client.HerdClient'
        }
    }
}

# Database
# https://docs.djangoproject.com/en/1.9/ref/settings/#databases

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': 'postgres',
        'USER': os.getenv('DB_USER', 'postgres'),
        'PASSWORD': os.getenv('DB_PASSWORD'),
        'HOST': os.getenv('DB_HOST', 'db'),
        'PORT': os.getenv('DB_PORT', '5432'),
        'OPTIONS': {
            'isolation_level': psycopg2.extensions.ISOLATION_LEVEL_SERIALIZABLE,
        },
    },
}

# Index
# https://django-haystack.readthedocs.io/en/v2.5.0/tutorial.html

HAYSTACK_CONNECTIONS = {
    'default': {
        'ENGINE': 'haystack.backends.elasticsearch_backend.ElasticsearchSearchEngine',
        'URL': 'http://index:9200/',
        'INDEX_NAME': 'haystack',
    },
}

# CELERY SETTINGS
BROKER_URL = os.getenv('BROKER_URL', 'amqp://task_queue:5672/')
CELERY_RESULT_BACKEND = 'rpc'
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERYBEAT_SCHEDULE = {
    'scrap-update': {
        'task': 'main_assistant.tasks.update_articles_periodic',
        'schedule': timedelta(hours=4),
    },
    # 'update-index': {
    #     'task': 'main_assistant.tasks.update_index_periodic',
    #     'schedule': crontab(day_of_week='sunday', hour=1, minute=0),
    # },
}
CELERY_CREATE_MISSING_QUEUES = False
CELERY_DEFAULT_QUEUE = 'default'
CELERY_QUEUES = (
    Queue('default', Exchange('default'), routing_key='default'),
)
CELERY_ROUTES = {
}

# Password validation
# https://docs.djangoproject.com/en/1.9/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]

# Internationalization
# https://docs.djangoproject.com/en/1.9/topics/i18n/

LANGUAGE_CODE = 'en-us'

# TIME_ZONE = 'UTC'
TIME_ZONE = 'Europe/Warsaw'

USE_I18N = True

USE_L10N = True

USE_TZ = True

# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/1.9/howto/static-files/

STATIC_URL = '/static/'
STATICFILES_DIRS = [
    os.path.join(BASE_DIR, 'static'),
]

STATIC_ROOT = '/var/pubassistant/static/'
MEDIA_ROOT = '/var/pubassistant/media/'
