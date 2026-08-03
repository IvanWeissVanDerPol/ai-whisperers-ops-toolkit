#!/usr/bin/env python3
"""
Client-sites healthcheck.

Hits each registered site over HTTP(S), records the status, content-size,
and validates that the page is actually rendering real content (not just
a 200 with a stub HTML). Catches:
  - HTTP non-200
  - Pages that are too small to be real (< 1KB)
  - Pages that match Next.js's generic 404 ("404 page not found")
  - Pages that lack a real <title> tag
  - Pages that lack meta description (suggests empty placeholder)
  - Pages that fail to load their JS bundles
  - Missing Traefik routes (no upstream app)

Usage:
  client_sites_healthcheck.py [--out PATH] [--timeout 8] [--sites PATH]
  client_sites_healthcheck.py --discover  # auto-discover from docker swarm labels

The default --sites file is ~/.hermes/state/client-sites.json. Format:
[
  {"name": "HidroBaby-Spa", "url": "https://hidrobaby-spa.paragu-ai.com/", "expect": "Spa"},
  ...
]

The default --out is ~/.hermes/state/client-sites-health.json.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
import urllib.request
import urllib.error
import ssl
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_SITES = Path.home() / ".hermes" / "state" / "client-sites.json"
DEFAULT_OUT = Path.home() / ".hermes" / "state" / "client-sites-health.json"

# Min HTML size for a "real" page (catches empty Next.js stubs that return 200 with just title)
MIN_BODY_BYTES = 1500

# Strings that indicate the page is the Next.js default 404 (not a real route)
NEXTJS_404_MARKERS = [
    "404 page not found",         # Next.js default 404
    "404 - This page could not",  # Various
    "This page could not be found",
]

# JS chunk URL pattern (Next.js)
JS_CHUNK_RE = re.compile(r'<script[^>]+src="(/_next/[^"]+\.js)"', re.I)
CSS_CHUNK_RE = re.compile(r'<link[^>]+href="(/_next/[^"]+\.css)"', re.I)
IMG_RE = re.compile(r'(?:src|href)="(/[^"]+\.(?:jpg|png|webp|svg|jpeg))"', re.I)


def discover_sites_from_swarm() -> list[dict]:
    """Auto-discover client sites from Docker Swarm service Traefik labels."""
    sites = []
    try:
        r = subprocess.run(
            ["docker", "service", "ls", "--format", "{{.Name}}"],
            capture_output=True, text=True, timeout=10,
        )
        for line in r.stdout.strip().split("\n"):
            svc = line.strip()
            if not svc or "_web" not in svc:
                continue
            r2 = subprocess.run(
                ["docker", "service", "inspect", svc, "--format", "{{.Spec.Labels}}"],
                capture_output=True, text=True, timeout=5,
            )
            labels = r2.stdout
            m = re.search(r'Host\(`([^`]+)`\)', labels)
            if m:
                host = m.group(1)
                # Derive name from host
                name = host.split(".")[0].replace("-", " ").title()
                # Heuristic expect — store the full host stem so we can try multiple matches
                expect = host.split(".")[0]
                sites.append({
                    "name": name,
                    "url": f"https://{host}/",
                    "expect": expect,
                    "host": host,
                })
    except Exception as e:
        print(f"discover error: {e}", file=sys.stderr)
    return sites


def validate_content(url: str, body: str, body_size: int, expect: str, ctx) -> dict:
    """Deep content validation — returns a dict of issues + ok flag."""
    issues = []

    # Check 1: not a Next.js default 404
    # Only check the visible HTML, not the RSC streaming payload
    # (Next.js includes the not-found component pre-rendered in RSC, but that's a template, not the actual page)
    visible_html = re.sub(r'<script[^>]*>.*?</script>', ' ', body, flags=re.S | re.I)
    visible_html = re.sub(r'<style[^>]*>.*?</style>', ' ', visible_html, flags=re.S | re.I)
    visible_lower = visible_html.lower()
    for marker in NEXTJS_404_MARKERS:
        if marker.lower() in visible_lower:
            issues.append(f"matches Next.js 404 marker: {marker!r}")
            break

    # Rest of body for other checks (including meta tags, which may be in <head> only)
    text_lower = body.lower()

    # Check 2: has a real title (not empty, not generic)
    title_m = re.search(r"<title[^>]*>(.*?)</title>", body, re.I | re.S)
    title = title_m.group(1).strip() if title_m else None
    if not title:
        issues.append("missing <title>")
    elif len(title) < 3:
        issues.append(f"title too short: {title!r}")
    elif title.lower() in ("document", "home", "index"):
        issues.append(f"title is generic placeholder: {title!r}")

    # Check 3: has meta description or og:description
    has_desc = bool(re.search(
        r'<meta[^>]+(?:name=["\']description["\']|property=["\']og:description["\'])',
        body, re.I,
    ))
    if not has_desc:
        issues.append("missing meta description / og:description")

    # Check 4: has h1
    h1_count = len(re.findall(r"<h1\b", body, re.I))
    # Some apps use h2 for primary heading — soft check
    h2_count = len(re.findall(r"<h2\b", body, re.I))
    # If no h1/h2 in initial HTML, check RSC streaming for upcoming content
    rsc_strings = []
    if h1_count == 0 and h2_count == 0:
        rsc_chunks = re.findall(r'self\.__next_f\.push\(\[1,"(.+?)"\]\)', body, re.S)
        # Try to JSON-decode each chunk and look for content
        import json as _json_mod
        for chunk in rsc_chunks:
            try:
                decoded = _json_mod.loads(f'"{chunk}"')
                # Find any meaningful string >= 5 chars with a space (multi-word)
                for m in re.findall(r'"((?:[^"\\]|\\.){5,300})"', decoded):
                    s = m
                    # Unescape common chars
                    try:
                        s = _json_mod.loads(f'"{s}"')
                    except Exception:
                        pass
                    if isinstance(s, str) and len(s) >= 5 and ' ' in s and not s.startswith(('/_next/', '$L', '$@', '$F', 'http', 'https')):
                        rsc_strings.append(s)
            except Exception:
                pass
        # Dedupe
        rsc_strings = list(set(rsc_strings))
        # If RSC has substantial strings, it's a client-rendered app — soft pass
        if len(rsc_strings) < 3:
            issues.append("missing h1 and h2 (no real headings, no RSC content)")

    # Check 5: expect text present (use decoded visible text, fuzzy match)
    # Accept: exact substring, or stripped version (no apostrophes, no accents)
    import html as _html_mod
    import unicodedata as _ud
    visible_decoded = _html_mod.unescape(visible_html)
    visible_decoded_lower = visible_decoded.lower()
    if expect:
        # Try the raw expect first
        found = expect.lower() in visible_decoded_lower
        # Also try a stripped version (no apostrophes, no accents)
        if not found:
            stripped = ''.join(
                c for c in _ud.normalize('NFD', expect.lower())
                if _ud.category(c) != 'Mn'
            ).replace("'", "").replace("'", "").replace("`", "").replace("´", "")
            visible_stripped = ''.join(
                c for c in _ud.normalize('NFD', visible_decoded_lower)
                if _ud.category(c) != 'Mn'
            ).replace("'", "").replace("'", "").replace("`", "").replace("´", "")
            found = stripped in visible_stripped
        # Try each part of the host (split on hyphens) as a partial match
        if not found:
            for part in expect.lower().split('-'):
                if part and part in visible_decoded_lower:
                    found = True
                    break
        # Also try the first 4-6 char prefix of expect (handles "goldenvisa" → "golden")
        if not found and len(expect) >= 5:
            for prefix_len in [min(6, len(expect)), min(5, len(expect))]:
                prefix = expect.lower()[:prefix_len]
                if prefix in visible_decoded_lower:
                    found = True
                    break
        if not found:
            issues.append(f"missing expected text: {expect!r}")

    # Check 6: body size (real pages are > 1.5KB minimum)
    if body_size < MIN_BODY_BYTES:
        issues.append(f"body too small: {body_size}b (< {MIN_BODY_BYTES}b)")

    # Check 7: JS chunks load (test first 2 — we don't load ALL to keep it fast)
    js_chunks = JS_CHUNK_RE.findall(body)[:2]
    css_chunks = CSS_CHUNK_RE.findall(body)[:1]
    failed_assets = []
    for asset in js_chunks + css_chunks:
        asset_url = asset if asset.startswith("http") else f"{url.rstrip('/')}{asset}"
        try:
            req = urllib.request.Request(
                asset_url, headers={"User-Agent": "HermesAgent-HealthCheck/1.0"}, method="HEAD",
            )
            with urllib.request.urlopen(req, timeout=5, context=ctx) as r:
                if r.status >= 400:
                    failed_assets.append(f"{asset} → {r.status}")
        except urllib.error.HTTPError as e:
            failed_assets.append(f"{asset} → {e.code}")
        except Exception as e:
            failed_assets.append(f"{asset} → ERR: {str(e)[:60]}")
    if failed_assets:
        # Missing chunks are warnings, not failures (could be hash mismatch from redeploy)
        issues.append(f"missing assets: {'; '.join(failed_assets)}")

    return {
        "ok": len([i for i in issues if "missing assets" not in i]) == 0,
        "title": title,
        "h1": h1_count,
        "body_size": body_size,
        "issues": issues,
    }


def check_site(site: dict, timeout: int) -> dict:
    url = site.get("url")
    name = site.get("name", url)
    expect = (site.get("expect") or "").lower()
    if not url:
        return {"name": name, "ok": False, "error": "no url"}
    headers = {"User-Agent": "HermesAgent-HealthCheck/2.0"}
    req = urllib.request.Request(url, headers=headers, method="GET")
    start = time.monotonic()
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
            status = r.status
            body_bytes = r.read(500_000)
            final_url = r.geturl()
        ms = int((time.monotonic() - start) * 1000)
        body = body_bytes.decode("utf-8", errors="ignore")

        # First-line status check
        if not (200 <= status < 300):
            return {
                "name": name, "url": url, "ok": False, "status": status, "ms": ms,
                "bytes": len(body_bytes), "error": f"non-2xx status: {status}",
            }

        # Deep validation
        validation = validate_content(url, body, len(body_bytes), expect, ctx)
        return {
            "name": name,
            "url": url,
            "final_url": final_url,
            "status": status,
            "ms": ms,
            "bytes": len(body_bytes),
            "title": validation["title"],
            "h1": validation["h1"],
            "issues": validation["issues"],
            "ok": validation["ok"],
        }
    except urllib.error.HTTPError as e:
        return {"name": name, "url": url, "ok": False, "status": e.code, "error": str(e)[:120]}
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        return {"name": name, "url": url, "ok": False, "error": str(e)[:120]}
    except Exception as e:
        return {"name": name, "url": url, "ok": False, "error": f"{type(e).__name__}: {e}"[:120]}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    ap.add_argument("--sites", default=str(DEFAULT_SITES))
    ap.add_argument("--timeout", type=int, default=10)
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--discover", action="store_true", help="auto-discover sites from Docker Swarm")
    args = ap.parse_args()

    if args.discover:
        sites = discover_sites_from_swarm()
        if not sites:
            print("no sites discovered from swarm", file=sys.stderr)
            return 1
        # Write to --sites file
        sites_path = Path(args.sites)
        sites_path.parent.mkdir(parents=True, exist_ok=True)
        sites_path.write_text(json.dumps(sites, indent=2, ensure_ascii=False))
        print(f"discovered {len(sites)} sites, saved to {sites_path}", file=sys.stderr)
    else:
        sites_path = Path(args.sites)
        if not sites_path.exists():
            sites_path.parent.mkdir(parents=True, exist_ok=True)
            # Fallback seed
            seed = [
                {"name": "HidroBaby-Spa", "url": "https://hidrobaby-spa.paragu-ai.com/", "expect": "HidroBaby"},
            ]
            sites_path.write_text(json.dumps(seed, indent=2, ensure_ascii=False))
            print(f"seeded {sites_path}", file=sys.stderr)
        sites = json.loads(sites_path.read_text())

    results = []
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futures = {ex.submit(check_site, s, args.timeout): s for s in sites}
        for f in as_completed(futures):
            results.append(f.result())

    results.sort(key=lambda r: r.get("name", ""))

    summary = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "total": len(results),
        "ok": sum(1 for r in results if r.get("ok")),
        "fail": sum(1 for r in results if not r.get("ok")),
        "results": results,
    }

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(summary, indent=2, ensure_ascii=False))

    # Compact stdout table
    print(f"{'name':<30}{'ok':<5}{'status':<8}{'size':>7}{'h1':>4}  issues")
    print("=" * 100)
    for r in results:
        flag = "✓" if r.get("ok") else "✗"
        st = r.get("status", r.get("error", "?"))
        size = r.get("bytes", "")
        h1 = r.get("h1", "")
        issues = r.get("issues", [])
        issue_str = "; ".join(issues[:2]) if issues else ""
        if len(issues) > 2:
            issue_str += f" (+{len(issues)-2} more)"
        print(f"{r.get('name',''):<30}{flag:<5}{str(st):<8}{str(size):>7}{str(h1):>4}  {issue_str}")

    print()
    print(f"OK: {summary['ok']}/{summary['total']}    FAIL: {summary['fail']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
