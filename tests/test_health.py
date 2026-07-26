import pytest
from django.db import DatabaseError
from django.urls import reverse


@pytest.mark.django_db
def test_health_check(client):
    response = client.get(reverse("health-check"))

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.django_db
def test_liveness_check(client):
    response = client.get(reverse("health-live"))

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.django_db
def test_readiness_check(client):
    response = client.get(reverse("health-ready"))

    assert response.status_code == 200
    assert response.json() == {"status": "ready"}


@pytest.mark.django_db
def test_readiness_check_reports_database_failure(client, monkeypatch):
    def unavailable_cursor():
        raise DatabaseError("database unavailable")

    monkeypatch.setattr("common.views.connection.cursor", unavailable_cursor)

    response = client.get(reverse("health-ready"))

    assert response.status_code == 503
    assert response.json() == {"status": "unavailable"}


@pytest.mark.django_db
@pytest.mark.parametrize("route_name", ["health-check", "health-live", "health-ready"])
def test_health_checks_reject_post(client, route_name):
    response = client.post(reverse(route_name))

    assert response.status_code == 405


@pytest.mark.django_db
def test_home_page(client):
    response = client.get(reverse("home"))

    assert response.status_code == 200
    assert "Rental Platform" in response.content.decode()
