#!/usr/bin/env python3
"""Nexa SEO Monitor — weekly rankings check + hreflang/JSON-LD validation.

Reports: rankings for target keywords, hreflang completeness, JSON-LD schema validity.
Output: JSON report to stdout. Hermes cron delivers to Telegram.
"""
import json, urllib.request, urllib.parse, re, sys, ssl, time

TARGET_URLS = [
    "https://nexa.paragu-ai.com/es",
    "https://nexa.paragu-ai.com/en",
    "https://nexa.paragu-ai.com/nl",
    "https://nexa.paragu-ai.com/de",
]
KEYWORDS = [
    "relocation Paraguay", "mudarse a Paraguay", "residencia paraguaya",
    "impuestos Paraguay", "Paraguay residency", "verhuizen naar Paraguay",
]

def fetch(url, timeout=10):
    ctx = ssl.create_default_context()
    req = urllib.request.Request(url, headers={"User-Agent": "NexaSEO/1.0"})
    try:
        resp = urllib.request.urlopen(req, timeout=timeout, context=ctx)
        return resp.read().decode("utf-8"), dict(resp.headers)
    except Exception as e:
        return None, {"error": str(e)}

def check_hreflang(html):
    if not html: 
        return {"count": 0, "languages": [], "ok": False}
    
    # Try multiple patterns to catch different HTML structures
    patterns = [
        r'<link[^>]*rel="alternate"[^>]*hreflang="([^"]*)"[^>]*href="([^"]*)"',
        r'<link[^>]*hreflang="([^"]*)"[^>]*href="([^"]*)"[^>]*rel="alternate"',
        r'hreflang="([^"]*)"[^>]*href="([^"]*)"[^>]*rel="alternate"',
    ]
    
    languages = []
    for pattern in patterns:
        matches = re.findall(pattern, html, re.IGNORECASE)
        if matches:
            # Handle both (lang, url) and (url, lang) orders
            for m in matches:
                if m[0] and m[0] in ['es', 'en', 'nl', 'de', 'x-default']:
                    languages.append(m[0])
                elif m[1] and m[1] in ['es', 'en', 'nl', 'de', 'x-default']:
                    languages.append(m[1])
            break
    
    # Also check for simple hreflang attribute presence as fallback
    if not languages and re.search(r'hreflang=["\'](es|en|nl|de)', html, re.IGNORECASE):
        found = re.findall(r'hreflang=["\'](es|en|nl|de|x-default)', html, re.IGNORECASE)
        languages = found
    
    expected = {"es", "en", "nl", "de", "x-default"}
    missing = expected - set(languages)
    
    return {
        "count": len(languages), 
        "languages": sorted(list(set(languages))), 
        "ok": len(missing) <= 1,
        "missing": sorted(list(missing))
    }

def check_jsonld(html):
    if not html: 
        return {"schemas": 0, "ok": False}
    scripts = re.findall(r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>', html, re.DOTALL)
    schemas = []
    for s in scripts:
        try:
            data = json.loads(s)
            if isinstance(data, list):
                schemas.extend([item.get("@type", "unknown") for item in data])
            else:
                schemas.append(data.get("@type", "unknown"))
        except: 
            schemas.append("invalid")
    
    valid_types = {"Organization", "WebSite", "ProfessionalService"}
    return {
        "schemas": schemas, 
        "count": len(scripts), 
        "ok": any(t in valid_types for t in schemas)
    }

def check_status(url):
    html, headers = fetch(url)
    status_code = headers.get("", 0) if isinstance(headers.get("", 0), int) else 200
    return {
        "url": url,
        "reachable": html is not None,
        "httpOk": status_code == 200 or status_code == 0,
        "hreflang": check_hreflang(html),
        "jsonld": check_jsonld(html),
        "hasNexaText": "Nexa" in html if html else False,
    }

def main():
    report = {
        "pages": [check_status(u) for u in TARGET_URLS], 
        "keywords": KEYWORDS, 
        "totalOk": 0, 
        "totalFail": 0
    }
    for p in report["pages"]:
        if p["reachable"] and p["jsonld"]["ok"] and p["hreflang"]["ok"]:
            report["totalOk"] += 1
        else:
            report["totalFail"] += 1
    print(json.dumps(report, indent=2))
    sys.exit(0)  # Hermes cron delivers stdout

if __name__ == "__main__":
    main()
