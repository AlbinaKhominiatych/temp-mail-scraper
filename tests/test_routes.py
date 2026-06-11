import pytest
from http import HTTPStatus
from unittest.mock import patch, MagicMock

from app import create_app
from app.config import Config
from app.exceptions import TempMailError, EmailNotFoundError


@pytest.fixture
def mock_scraper_instance():
    return MagicMock()


@pytest.fixture
def client(mock_scraper_instance):


    with patch("app.TempMailScraper", return_value=mock_scraper_instance):

        cfg = Config(HEADLESS=True, LOG_LEVEL="DEBUG")
        app = create_app(cfg)
        app.testing = True

        with app.test_client() as client:
            yield client


# ── Тести для GET /api/email ──────────────────────────────────────────────────

def test_get_current_email_success(client, mock_scraper_instance):
    mock_scraper_instance.get_email.return_value = "test@tempail.com"

    response = client.get("/api/email")

    assert response.status_code == HTTPStatus.OK
    assert response.json == {"email": "test@tempail.com"}
    mock_scraper_instance.get_email.assert_called_once()


def test_get_current_email_error(client, mock_scraper_instance):
    mock_scraper_instance.get_email.side_effect = TempMailError("Browser crashed")

    response = client.get("/api/email")

    assert response.status_code == HTTPStatus.SERVICE_UNAVAILABLE
    assert "Browser crashed" in response.json["error"]


# ── Тести для GET /api/inbox ──────────────────────────────────────────────────

def test_get_inbox_success(client, mock_scraper_instance):
    mock_inbox = [
        {"id": "1", "sender": "test@mail.com", "subject": "Hello", "timestamp": "12:00"}
    ]
    mock_scraper_instance.get_inbox.return_value = mock_inbox

    response = client.get("/api/inbox")

    assert response.status_code == HTTPStatus.OK
    assert response.json["count"] == 1
    assert response.json["emails"] == mock_inbox


# ── Тести для POST /api/email/refresh ─────────────────────────────────────────

def test_refresh_email_success(client, mock_scraper_instance):
    mock_scraper_instance.refresh.return_value = "new@tempail.com"

    response = client.post("/api/email/refresh")

    assert response.status_code == HTTPStatus.OK
    assert response.json["email"] == "new@tempail.com"
    assert response.json["message"] == "Email refreshed successfully"


# ── Тести для GET /api/email/<email_id> ───────────────────────────────────────

def test_get_email_by_id_success(client, mock_scraper_instance):
    mock_email_data = {"id": "123", "body": "Hello World"}
    mock_scraper_instance.get_email_by_id.return_value = mock_email_data

    response = client.get("/api/email/123")

    assert response.status_code == HTTPStatus.OK
    assert response.json == mock_email_data


def test_get_email_by_id_not_found(client, mock_scraper_instance):
    mock_scraper_instance.get_email_by_id.side_effect = EmailNotFoundError("Email 123 not found")

    response = client.get("/api/email/123")

    assert response.status_code == HTTPStatus.NOT_FOUND
    assert "Email 123 not found" in response.json["error"]
