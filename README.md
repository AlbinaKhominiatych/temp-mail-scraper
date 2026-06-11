# Temporary Mail Scraper API

A production-ready RESTful API built with Python, Flask, and Playwright that automates interactions with [tempail.com](https://tempail.com/) to generate temporary email addresses, fetch inboxes, and retrieve individual message contents.

This project is tailored for performance, thread safety, and resilience, serving as a robust solution for automated email verification pipelines.

---

## 🚀 Features

* **Instant Email Generation:** Dynamically fetch a new, active anonymous email address.
* **Real-time Inbox Monitoring:** List all received emails including metadata (IDs, senders, subjects, and timestamps).
* **Deep Content Inspection:** Retrieve full HTML/Text message bodies by specific email IDs.
* **Session Refreshing:** Abandon the current mailbox and spin up a pristine session instantly.
* **Production-Grade Architecture:** Custom background-thread orchestration ensuring stability under concurrent API requests.
* **Containerized & CI/CD Ready:** Fully dockerized setup backed by automated GitHub Actions validation.

---

## 🏗️ Architecture & Design Decisions

### The Concurrency Challenge & The Solution
Playwright's synchronous API relies heavily on `greenlets`, tying browser automation instances strictly to the OS thread in which they were initialized. Because Flask handles incoming HTTP requests on a multi-threaded pool, making direct Playwright calls inside standard Flask routes invariably throws a fatal `RuntimeError: Cannot switch to a different thread` exception.

To address this, this project implements a **Dedicated Daemon Thread Worker Pattern**:
* **Isolation:** On application startup, a single, persistent `TempMailScraper` daemon thread is spawned, owning the exclusive lifetime of the Playwright/Chromium process.
* **Thread-Safe Dispatcher:** Flask request threads never touch Playwright directly. Instead, they encapsulate operations into callables, push them onto a thread-safe synchronized `queue.Queue`, and safely block until the daemon thread processes the task and returns the execution result.
* **Failover & Auto-Recovery:** If the underlying browser state becomes corrupted, selectors fail, or the remote site drops connections, custom domain exceptions (`SessionError`, `ElementNotFoundError`) are gracefully caught, triggering an isolated browser context recreation (`_recover`) without disrupting the main Flask server process.

---

## 📂 Project Structure

```text
temp-mail-scraper/
├── .github/workflows/
│   └── ci.yml             # GitHub Actions CI pipeline (linting & unit tests)
├── app/
│   ├── __init__.py        # Application factory attaching the Scraper thread
│   ├── config.py          # Environment-aware configuration dataclass
│   ├── exceptions.py      # Custom domain exceptions (TempMailError, etc.)
│   ├── routes.py          # API endpoints (Thin Controllers pattern)
│   └── scraper.py         # Playwright automation core (Daemon thread loop)
├── tests/
│   └── test_routes.py     # Isolated endpoint unit tests using Pytest & Mocks
├── Dockerfile             # Multi-stage image utilizing official Microsoft Playwright runtime
├── docker-compose.yml     # Self-contained container setup with built-in API healthchecks
├── main.py                # Process entry point, graceful shutdown & signal registration
├── pytest.ini             # Pytest runtime path configuration
└── requirements.txt       # Hardened application dependency manifest
```

---

## ⚙️ Configuration (.env)

The application dynamically configures itself via environment variables. See configurations below:

| Variable | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `HEADLESS` | Boolean | `true` | Runs Chromium without a GUI (set to `false` for debugging local runs). |
| `LOG_LEVEL` | String | `INFO` | Level of logging output (`DEBUG`, `INFO`, `WARNING`, `ERROR`). |
| `PORT` | Integer | `5000` | Port on which the Flask server binds. |

---

## 🚀 Getting Started

### Option 1: Running with Docker Compose (Recommended)

The easiest way to launch the service with all its system dependencies (Chromium, fonts, window-server hooks) pre-configured is via Docker.

```bash
# Build and spin up the containerized stack
docker-compose up --build -d

# Check API health status
docker-compose ps
```

### Option 2: Local Development Setup

Ensure you have Python 3.11+ installed on your host system.

```bash
# Create and activate a virtual environment
python -m venv venv
source venv/bin/activate  # On Windows use: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Install Playwright browser binaries and system hooks
playwright install chromium

# Launch the server
python main.py
```
> ⚠️ **Note:** When launching locally, the script utilizes `use_reloader=False` deliberately. Flask's development auto-reloader forks the OS process, which would cause an unwanted secondary browser thread initialization.

---

## 📋 API Documentation

### 1. Get Current Email
Fetches the active temporary email address bound to the current session.
* **URL:** `/api/email`
* **Method:** `GET`
* **Success Response (200 OK):**
  ```json
  {
    "email": "example55@tempail.com"
  }
  ```

### 2. Get Inbox
Retrieves a list of all incoming messages with metadata details.
* **URL:** `/api/inbox`
* **Method:** `GET`
* **Success Response (200 OK):**
  ```json
  {
    "count": 1,
    "emails": [
      {
        "id": "e4a5d8...",
        "sender": "no-reply@github.com",
        "subject": "Verify your account",
        "timestamp": "14:25"
      }
    ]
  }
  ```

### 3. Get Email Content by ID
Extracts the complete payload and body markup of an individual message.
* **URL:** `/api/email/<email_id>`
* **Method:** `GET`
* **Success Response (200 OK):**
  ```json
  {
    "id": "e4a5d8...",
    "sender": "no-reply@github.com",
    "subject": "Verify your account",
    "timestamp": "14:25",
    "body": "<html>...Please click this link to verify...</html>"
  }
  ```
* **Error Response (404 Not Found):** Sent if the requested message ID does not exist in the active mailbox cache.

### 4. Refresh Session
Forces the browser session to clear cookies, abandon the current inbox, and fetch a new address.
* **URL:** `/api/email/refresh`
* **Method:** `POST`
* **Success Response (200 OK):**
  ```json
  {
    "email": "fresh_session99@tempail.com",
    "message": "Email refreshed successfully"
  }
  ```

---

## 🧪 Testing and Quality Gates

The project maintains code standards and guarantees route safety using `pytest` alongside mock assertions to completely isolate HTTP layers from heavy browser instances during CI.

```bash
# Execute unit testing suite locally
pytest -v

# Run styling and syntax verification checks
flake8 . --count --select=E9,F63,F7,F82 --show-source --statistics
```
