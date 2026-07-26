from .base import *  # noqa: F403
from .base import database_config

SECRET_KEY = "test-only-secret-key"
DEBUG = True
ALLOWED_HOSTS = ["testserver", "localhost", "127.0.0.1"]
DATABASES = {"default": database_config(sqlite_name=":memory:")}
DATABASES["default"]["CONN_MAX_AGE"] = 0

PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
