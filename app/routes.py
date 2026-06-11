import logging
from http import HTTPStatus

from flask import Blueprint, current_app, jsonify

from .exceptions import EmailNotFoundError, TempMailError

log = logging.getLogger(__name__)

api = Blueprint("api", __name__, url_prefix="/api")


def _scraper():
    """Shortcut to the scraper instance stored on the current app."""
    return current_app.scraper  # type: ignore[attr-defined]


# ── GET /api/email ────────────────────────────────────────────────────────────

@api.get("/email")
def get_current_email():
    """Return the active temporary email address."""
    try:
        email = _scraper().get_email()
        return jsonify({"email": email})
    except TempMailError as exc:
        log.error("get_email error: %s", exc)
        return jsonify({"error": str(exc)}), HTTPStatus.SERVICE_UNAVAILABLE


# ── GET /api/inbox ────────────────────────────────────────────────────────────

@api.get("/inbox")
def get_inbox():
    """Return a list of received messages with id, sender, subject, timestamp."""
    try:
        messages = _scraper().get_inbox()
        return jsonify({"emails": messages, "count": len(messages)})
    except TempMailError as exc:
        log.error("get_inbox error: %s", exc)
        return jsonify({"error": str(exc)}), HTTPStatus.SERVICE_UNAVAILABLE


# ── POST /api/email/refresh ───────────────────────────────────────────────────
#   Declared BEFORE the /<email_id> route so Flask resolves it unambiguously
#   for POST requests regardless of method.

@api.post("/email/refresh")
def refresh_email():
    """Generate a new temporary email address (abandons the current inbox)."""
    try:
        new_email = _scraper().refresh()
        return jsonify({"email": new_email, "message": "Email refreshed successfully"})
    except TempMailError as exc:
        log.error("refresh error: %s", exc)
        return jsonify({"error": str(exc)}), HTTPStatus.SERVICE_UNAVAILABLE


# ── GET /api/email/<email_id> ─────────────────────────────────────────────────

@api.get("/email/<email_id>")
def get_email_by_id(email_id: str):
    """Return the full content of a specific message (sender, subject, timestamp, body)."""
    try:
        message = _scraper().get_email_by_id(email_id)
        return jsonify(message)
    except EmailNotFoundError as exc:
        return jsonify({"error": str(exc)}), HTTPStatus.NOT_FOUND
    except TempMailError as exc:
        log.error("get_email_by_id(%s) error: %s", email_id, exc)
        return jsonify({"error": str(exc)}), HTTPStatus.SERVICE_UNAVAILABLE
