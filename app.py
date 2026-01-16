import os
import time
from typing import Dict, Any, List

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query
from playwright.sync_api import sync_playwright, Page, Locator

load_dotenv()
EMAIL = os.getenv("RAKUTEN_EMAIL")
PASSWORD = os.getenv("RAKUTEN_PASSWORD")
if not EMAIL or not PASSWORD:
    raise RuntimeError("Missing RAKUTEN_EMAIL or RAKUTEN_PASSWORD in .env")

app = FastAPI(title="Rakuten Store Lookup API")


def log(msg: str) -> None:
    print(f"[rakuten] {msg}", flush=True)


def norm(s: str) -> str:
    return (s or "").strip().lower()


def close_initial_popup_retry(page: Page, tries: int = 10, delay_s: float = 0.6) -> None:
    log("Closing initial popup if present...")
    for i in range(tries):
        try:
            page.get_by_role("button", name="Close").click(timeout=1200)
            log(f"Closed initial popup (try {i+1}/{tries}).")
            return
        except Exception:
            time.sleep(delay_s)
    log("No initial popup found (or it never appeared).")


def login(page: Page) -> None:
    log("Opening Rakuten...")
    page.goto("https://www.rakuten.com/", wait_until="domcontentloaded")

    log("Clicking Sign In...")
    page.get_by_role("button", name="Sign In").click()

    log("Filling credentials in auth iframe...")
    f = page.frame_locator('[data-testid="auth-microsite-iframe"]')
    f.get_by_role("textbox", name="Email").fill(EMAIL)
    f.get_by_role("textbox", name="Password (8+ characters)").fill(PASSWORD)
    f.get_by_role("button", name="Sign In").click()

    log("Waiting for post-login page readiness...")
    page.wait_for_load_state("networkidle", timeout=60000)
    page.get_by_test_id("search-term").wait_for(timeout=20000)

    close_initial_popup_retry(page)


def pick_rate(container: Locator) -> str:
    spans = container.locator("span")

    for i in range(spans.count()):
        t = (spans.nth(i).inner_text() or "").strip()
        tl = t.lower()
        if ("cash back" in tl) or ("online" in tl) or ("up to" in tl):
            return t

    for i in range(spans.count()):
        t = (spans.nth(i).inner_text() or "").strip()
        if ("%" in t) or ("$" in t):
            return t

    return ""


def submit_search(page: Page, term: str) -> None:
    log(f"Searching for: {term}")
    s = page.get_by_test_id("search-term")
    s.click()
    s.fill(term)
    page.wait_for_timeout(500)

    log("Clicking search submit button...")
    s.locator(
        'xpath=ancestor::div[contains(@class,"chakra-input__group")]//button[@type="submit"]'
    ).click()

    log("Waiting for search results containers...")
    page.wait_for_timeout(700)
    try:
        page.wait_for_selector(
            '[template="promoted_search_store_v3"], [template="store_mark_iscb_carousel_v1"]',
            timeout=20000,
        )
        log("Search results containers appeared.")
    except Exception:
        log("Search results containers not detected yet (continuing).")

    page.wait_for_timeout(600)


def find_store(page: Page, term: str, max_suggestions: int = 5) -> Dict[str, Any]:
    want = norm(term)
    submit_search(page, term)

    promo = page.locator('[template="promoted_search_store_v3"]').first
    if promo.count() > 0:
        img = promo.locator('img[alt*=" - Rakuten coupons and Cash Back"]').first
        if img.count() > 0:
            alt = (img.get_attribute("alt") or "").strip()
            store = (alt.split(" - ")[0] if " - " in alt else alt).strip()
            rate = pick_rate(promo) or "No Cash Back shown"
            log(f"Promoted: {store} — {rate}")
            if norm(store) == want:
                return {"mode": "exact", "results": [{"store": store, "rate": rate}]}

    car = page.locator('[template="store_mark_iscb_carousel_v1"]').first
    if car.count() > 0:
        cards = car.locator('a:has(img[alt*=" - Rakuten coupons and Cash Back"])')
        n = min(cards.count(), max_suggestions)
        if n > 0:
            log(f"Returning {n} suggestions.")
            out: List[Dict[str, str]] = []
            for i in range(n):
                a = cards.nth(i)
                alt = (a.locator("img").first.get_attribute("alt") or "").strip()
                store = (alt.split(" - ")[0] if " - " in alt else alt).strip()
                rate = pick_rate(a) or "No Cash Back shown"
                out.append({"store": store, "rate": rate})
            return {"mode": "suggestions", "results": out}

    return {"mode": "not_found", "results": []}


def run_job(job_fn):
    with sync_playwright() as p:
        log("Launching Chromium (headless=True)...")
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        try:
            login(page)
            return job_fn(page)
        finally:
            browser.close()
            log("Browser closed.")


@app.get("/store")
def store(term: str = Query(..., min_length=1), max_suggestions: int = 5):
    term = term.strip()
    log(f"/store term='{term}' max_suggestions={max_suggestions}")

    data = run_job(lambda page: find_store(page, term, max_suggestions=max_suggestions))

    if data["mode"] == "not_found":
        raise HTTPException(status_code=404, detail="Store not found")

    return {"query": term, **data}
