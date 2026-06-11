# Temp Mail Scraper API

A REST API built with Python, Flask, and Playwright that automates interaction with [tempail.com](https://tempail.com/ua/) to generate temporary email addresses and read incoming messages. 

This project was developed as a technical assessment and fulfills all core and bonus requirements, including Dockerization, leveled logging, and thread-safe browser automation.

---

## 🚀 Features

* **Generate Temp Email:** Instantly fetch a new temporary email address.
* **Monitor Inbox:** Retrieve all incoming emails (sender, subject, timestamp, ID).
* **Read Messages:** Fetch the full HTML/Text body of a specific email by ID.
* **Refresh Session:** Discard the current email and generate a completely new one.
* **Thread-Safe Automation:** Uses a single persistent Playwright/Chromium context protected by `threading.RLock` to handle concurrent API requests efficiently.
* **Graceful Shutdown:** Intercepts system signals to cleanly close the browser process.

---

## 🛠️ Project Structure

\`\`\`text
temp-mail-scraper/
├── app/
│   ├── __init__.py      # App factory, connects config, scraper, and routes
│   ├── config.py        # Environment-aware configuration dataclass
│   ├── exceptions.py    # Custom domain exceptions for error handling
│   ├── scraper.py       # Playwright automation logic, thread-safe session
│   └── routes.py        # API Endpoints (Flask Blueprint)
├── main.py              # Application entry point & graceful shutdown handlers
├── requirements.txt     # Project dependencies
├── Dockerfile           # Uses official Playwright image
└── docker-compose.yml   # Multi-container setup with healthchecks
\`\`\`

---

## 🐳 Running with Docker (Recommended)

The easiest way to run the application is via Docker, as it uses the official Microsoft Playwright image which includes all necessary Chromium system dependencies.

1. Clone the repository.
2. Start the container:
   \`\`\`bash
   docker compose up --build
   \`\`\`
3. The API will be available at \`http://localhost:5000\`.

*(Note: The first startup might take a few extra seconds as Playwright initializes the browser context).*

---

## 💻 Running Locally

### Prerequisites
* Python 3.11+
* Virtual Environment

### Setup Steps

1. **Create and activate a virtual environment:**
   \`\`\`bash
   python -m venv .venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   \`\`\`

2. **Install Python dependencies:**
   \`\`\`bash
   pip install -r requirements.txt
   \`\`\`

3. **Install Playwright browsers:**
   \`\`\`bash
   playwright install chromium
   \`\`\`

4. **Environment Variables (Optional):**
   Copy `.env.example` to `.env` (or set them manually):
   \`\`\`env
   HEADLESS=true
   LOG_LEVEL=INFO
   PORT=5000
   \`\`\`
   *Tip: Set `HEADLESS=false` to watch the browser actions in real-time.*

5. **Start the server:**
   \`\`\`bash
   python main.py
   \`\`\`

---

## 📖 API Reference

All responses are returned as `application/json`.

### 1. Get Current Email
Returns the currently active temporary email address.
* **URL:** `/api/email`
* **Method:** `GET`
* **Response (200 OK):**
  \`\`\`json
  {
    "email": "example123@tempail.com"
  }
  \`\`\`

### 2. Get Inbox
Returns a list of all received emails in the current session.
* **URL:** `/api/inbox`
* **Method:** `GET`
* **Response (200 OK):**
  \`\`\`json
  {
    "count": 1,
    "emails": [
      {
        "id": "12345",
        "sender": "noreply@github.com",
        "subject": "Please verify your email address",
        "timestamp": "14:30"
      }
    ]
  }
  \`\`\`

### 3. Get Email Content
Retrieves the full body/content of a specific email by its ID.
* **URL:** `/api/email/<id>`
* **Method:** `GET`
* **Response (200 OK):**
  \`\`\`json
  {
    "id": "12345",
    "sender": "noreply@github.com",
    "subject": "Please verify your email address",
    "timestamp": "14:30",
    "body": "Welcome! Please click the link below to verify..."
  }
  \`\`\`
* **Error Responses:** * `404 Not Found` if the ID does not exist.

### 4. Refresh Email
Abandons the current inbox and generates a brand new temporary email address.
* **URL:** `/api/email/refresh`
* **Method:** `POST`
* **Response (200 OK):**
  \`\`\`json
  {
    "email": "new_address99@tempail.com",
    "message": "Email refreshed successfully"
  }
  \`\`\`

---

## 🛡️ Architecture & Design Decisions

* **Singleton Browser Process:** Starting a new browser for every request is highly inefficient. This API launches a single Headless Chromium instance on startup. 
* **Concurrency Handling:** Because Flask handles requests in multiple threads, Playwright interactions are locked using Python's `threading.RLock` to prevent race conditions during DOM manipulation.
* **Resilience & Auto-Recovery:** If the DOM selectors fail or the site drops the connection, custom exceptions (`ElementNotFoundError`, `SessionError`) are caught, logged, and return clean `503 Service Unavailable` JSON responses rather than crashing the app.
* **Caching:** Email body content is cached in-memory after the first fetch to avoid unnecessary, repetitive browser clicks.
