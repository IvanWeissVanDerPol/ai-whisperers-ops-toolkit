#!/usr/bin/env python3
"""Screenshot all Nexa pages for visual regression testing."""
import sys, os
from playwright.sync_api import sync_playwright

BASE = "https://nexa.paragu-ai.com"
PAGES = [
    ("/es", "nexa-es.png"),
    ("/en", "nexa-en.png"),
    ("/nl", "nexa-nl.png"),
    ("/de", "nexa-de.png"),
    ("/es/contacto", "nexa-es-contacto.png"),
    ("/en/contact", "nexa-en-contact.png"),
]

output_dir = sys.argv[1] if len(sys.argv) > 1 else "./screenshots/current"
os.makedirs(output_dir, exist_ok=True)

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
    context = browser.new_context(viewport={"width": 1440, "height": 900})
    page = context.new_page()
    for path, filename in PAGES:
        url = BASE + path
        out = os.path.join(output_dir, filename)
        try:
            page.goto(url, wait_until="networkidle", timeout=15000)
            page.wait_for_timeout(1000)
            page.screenshot(path=out, full_page=True)
            print(f"[screenshot] OK {filename} ({url})")
        except Exception as e:
            print(f"[screenshot] FAIL {filename} ({url}): {e}")
    browser.close()
print("[screenshot-all] Done")
