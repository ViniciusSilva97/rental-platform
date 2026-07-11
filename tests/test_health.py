import pytest
from django.urls import reverse


@pytest.mark.django_db
def test_health_check(client):
    response = client.get(reverse("health-check"))

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.django_db
def test_home_page(client):
    response = client.get(reverse("home"))

    assert response.status_code == 200
    assert "Rental Platform" in response.content.decode()

