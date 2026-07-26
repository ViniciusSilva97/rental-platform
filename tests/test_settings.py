import pytest
from django.core.exceptions import ImproperlyConfigured

from config.settings.base import database_config, env_bool, env_int, env_list, required_env


@pytest.mark.parametrize("value", ["1", "true", "TRUE", "yes", "on"])
def test_env_bool_recognizes_true_values(monkeypatch, value):
    monkeypatch.setenv("FEATURE_FLAG", value)

    assert env_bool("FEATURE_FLAG") is True


def test_env_int_rejects_non_integer(monkeypatch):
    monkeypatch.setenv("WORKER_COUNT", "two")

    with pytest.raises(ImproperlyConfigured):
        env_int("WORKER_COUNT", default=1)


def test_env_list_ignores_empty_items(monkeypatch):
    monkeypatch.setenv("HOSTS", "example.com, ,api.example.com")

    assert env_list("HOSTS") == ["example.com", "api.example.com"]


def test_required_env_rejects_blank_value(monkeypatch):
    monkeypatch.setenv("REQUIRED_VALUE", " ")

    with pytest.raises(ImproperlyConfigured):
        required_env("REQUIRED_VALUE")


def test_database_config_parses_postgresql_url(monkeypatch):
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql://rental%40user:p%40ss@db:5433/rental?sslmode=require",
    )

    config = database_config()

    assert config["ENGINE"] == "django.db.backends.postgresql"
    assert config["NAME"] == "rental"
    assert config["USER"] == "rental@user"
    assert config["PASSWORD"] == "p@ss"
    assert config["HOST"] == "db"
    assert config["PORT"] == 5433
    assert config["OPTIONS"] == {"sslmode": "require"}


def test_database_config_requires_postgresql_in_production(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)

    with pytest.raises(ImproperlyConfigured):
        database_config(require_url=True)
