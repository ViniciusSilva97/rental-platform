import os

from .base import *  # noqa: F403
from .base import env_bool, env_list

SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "unsafe-development-key")
DEBUG = env_bool("DJANGO_DEBUG", default=True)
ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1")

SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False
