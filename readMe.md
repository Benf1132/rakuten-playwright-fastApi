# Rakuten Store Lookup API (FastAPI + Playwright)

A simple FastAPI service that logs into Rakuten and looks up a store’s Cash Back rate using Playwright.

✅ Features:
- Headless Chromium
- Auto-login using `.env` credentials
- `/store?term=...` endpoint
- Returns one exact match if found; otherwise returns top suggestions (3–5) from Rakuten’s carousel
- Terminal logs for debugging

## 1. Setup

### Create and activate a virtual environment (Windows PowerShell)

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1

pip install -r requirements.txt
python -m playwright install
```
## 2 Configure .env

### Create a file named .env in the same folder as app.py:
RAKUTEN_EMAIL=your_email_here
RAKUTEN_PASSWORD=your_password_here

## 3 run the app
uvicorn app:app --reload
