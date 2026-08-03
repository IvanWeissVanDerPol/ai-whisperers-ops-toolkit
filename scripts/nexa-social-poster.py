#!/usr/bin/env python3
"""
Nexa Social Poster — LinkedIn Auto-Posting Script
==================================================
Checks content/es.json for new blog posts (within last 7 days),
generates LinkedIn-optimized post content, and prints what would be posted.

Dry-run mode: prints formatted post previews without actual API calls.

Usage:
    python3 nexa-social-poster.py              # dry-run (prints posts)
    python3 nexa-social-poster.py --live       # actual LinkedIn API posting
    python3 nexa-social-poster.py --reset      # reset posted tracker
"""

import json
import sys
import os
from datetime import datetime, timedelta, timezone

# ─── Configuration ───────────────────────────────────────────────────────────

CONTENT_PATH = "/root/nexa-paraguay/content/es.json"
TRACKER_PATH = "/tmp/nexa-social-posted.json"
SITE_URL = "https://nexa.paragu-ai.com"
LOCALE = "es"
DAYS_LOOKBACK = 7
LINKEDIN_API_URL = "https://api.linkedin.com/v2/ugcPosts"

# ─── Helpers ─────────────────────────────────────────────────────────────────

def load_json(path):
    """Load a JSON file, returning None on failure."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        print(f"ERROR|Could not load {path}: {e}", file=sys.stderr)
        return None


def save_json(path, data):
    """Atomically write JSON data to a file."""
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def load_posted_tracker():
    """Load the set of already-posted slugs."""
    data = load_json(TRACKER_PATH)
    if data and isinstance(data, dict) and "posted" in data:
        return set(data["posted"])
    return set()


def save_posted_tracker(posted_slugs):
    """Persist the set of posted slugs."""
    save_json(TRACKER_PATH, {"posted": sorted(posted_slugs), "updated": datetime.now(timezone.utc).isoformat()})


def parse_date(date_str):
    """Parse date string (YYYY-MM-DD) into a datetime object."""
    try:
        return datetime.strptime(date_str.strip(), "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except (ValueError, AttributeError):
        return None


def is_within_days(post_date, days=DAYS_LOOKBACK):
    """Check if post_date is within the last N days from now."""
    if post_date is None:
        return False
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=days)
    return cutoff <= post_date <= now


def get_post_body(post):
    """Get the main body/content of a post, handling both 'body' and 'content' keys."""
    return post.get("body") or post.get("content") or post.get("excerpt", "")


def generate_linkedin_post(post):
    """
    Generate a LinkedIn-optimized post from a blog post entry.
    
    Template:
    - Hook question (opens with a question to grab attention)
    - 3-5 bullet points with key facts
    - Ends with a CTA and link to the blog
    - Max 1300 chars (LinkedIn limit)
    - Uses emojis sparingly
    """
    title = post.get("title", "New blog post")
    excerpt = post.get("excerpt", "")
    slug = post.get("slug", "")
    post_url = f"{SITE_URL}/blog/{slug}"
    body = get_post_body(post)
    
    # Extract key bullet points from the body content
    bullets = extract_bullets(body, title, excerpt)
    
    # Build post
    lines = []
    
    # Hook question (varies by category/topic)
    hook = generate_hook(title, post)
    lines.append(hook)
    lines.append("")
    
    # Bullet points
    for b in bullets:
        lines.append(b)
    
    lines.append("")
    
    # CTA
    cta = (
        f"Read the full guide here: {post_url}\n"
        f"\n"
        f"---\n"
        f"\u00bfListo para dar el paso? Agenda una consulta gratuita de 30 min "
        f"(sin compromiso) \u2192 {SITE_URL}/contacto"
    )
    lines.append(cta)
    
    post_text = "\n".join(lines)
    
    # Truncate to 1300 chars if needed (at a line boundary)
    if len(post_text) > 1300:
        # Find last line break before 1270 chars
        cutoff = 1270
        while cutoff > 0 and post_text[cutoff] not in ('\n', '.', ' '):
            cutoff -= 1
        post_text = post_text[:cutoff] + "\n\n[...] " + cta
    
    return post_text


def generate_hook(title, post):
    """Generate a hook question based on the post title and content."""
    title_lower = title.lower()
    
    hooks = {
        "residencia": "Ya pensaste en tener una segunda residencia en Sudam\u00e9rica?",
        "cuenta bancaria": "Sab\u00edas que abrir una cuenta bancaria en Paraguay es m\u00e1s simple de lo que crees?",
        "costo de vida": "Te imaginas reducir tu costo de vida un 50-60% sin sacrificar calidad?",
        "compra": "Invertir en propiedades en el extranjero suena complicado, pero \u00bfy si no lo fuera?",
        "propiedades": "Comprar propiedades en el extranjero: \u00bfsue\u00f1o o estrategia real?",
        "fiscal": "Sab\u00edas que hay un pa\u00eds donde tus ingresos del extranjero pagan 0% de impuestos?",
        "impuesto": "Y si tu dinero trabajara para ti sin que el fisco se lleve la mitad?",
        "empresa": "Constituir una empresa en Sudam\u00e9rica: \u00bfburocracia infernal o proceso \u00e1gil?",
        "emprender": "Paraguay est\u00e1 viviendo un boom emprendedor. \u00bfEst\u00e1s mirando en la direcci\u00f3n correcta?",
        "constituir": "Montar una empresa en el extranjero: \u00bfpor d\u00f3nde empezar?",
        "mercado inmobiliario": "El mercado inmobiliario paraguayo est\u00e1 en plena transformaci\u00f3n. \u00bfVale la pena invertir?",
        "panam\u00e1": "Paraguay o Panam\u00e1 para residencia en 2026? Te damos los datos fr\u00edos.",
        "europeos": "Por qu\u00e9 cada vez m\u00e1s europeos est\u00e1n mirando a Paraguay en 2026?",
        "gu\u00eda completa": "Todo lo que necesitas saber sobre residencia en Paraguay\u2026 \u00bfpero sab\u00edas esto?",
        "documentos": "Te has preguntado qu\u00e9 documentos necesitas realmente para mudarte a Paraguay?",
        "jornada": "Hacer todo en un solo viaje a Paraguay: \u00bfrealidad o ficci\u00f3n?",
        "gestor\u00eda": "Contratas una gestor\u00eda o un equipo profesional para tu mudanza? No es lo mismo.",
    }
    
    for keyword, hook in hooks.items():
        if keyword in title_lower:
            return hook
    
    # Fallback: generate from title
    return f"Sab\u00edas esto sobre {title.lower()}?"


def extract_bullets(body, title, excerpt):
    """
    Extract 3-5 bullet points from the blog post body content.
    Falls back to excerpt-based points if body is too sparse.
    
    Handles both 'body' (markdown text) and 'content' (including ## headers)
    formats found in the blog posts.
    """
    bullets = []
    
    # Strategy 1: Look for list items and relevant content in the body
    if body:
        # Skip intro/summary sections that list "Qu\u00e9 cubre este art\u00edculo" boilerplate
        skip_headers = {"qu\u00e9 cubre este art\u00edculo", "introducci\u00f3n", "contexto",
                        "pr\u00f3ximos pasos", "errores comunes"}
        in_skip_section = False
        
        lines = body.split("\n")
        for line in lines:
            line = line.strip()
            if not line:
                continue
            
            # Track section headers to skip boilerplate
            if line.startswith("##"):
                section_name = line.lstrip("#").strip().lower()
                in_skip_section = any(s in section_name for s in skip_headers)
                # Extract ## headers as potential bullet content
                clean = line.lstrip("#").strip()
                # Filter out very short headers (likely table labels, not sections)
                meaningful = len(clean) > 20
                if (not in_skip_section and meaningful
                        and not any(s in clean.lower() for s in skip_headers)):
                    bullets.append(f"\u2022 {clean}")
                continue
            
            if in_skip_section:
                continue
            
            # Match bullet points like "- item", "* item", or numbered "1. item"
            if line.startswith("- ") or line.startswith("* "):
                clean = line.lstrip("-* ").strip()
                if clean and len(clean) > 10 and len(clean) < 200:
                    bullets.append(f"\u2022 {clean}")
            elif line.startswith("**") and "**" in line[2:]:
                # Bold text like "**Requisitos:**" - extract
                clean = line.strip("*").strip()
                if clean and len(clean) < 200:
                    bullets.append(f"\u2022 {clean}")
            elif line and line[0].isdigit() and ". " in line[:4]:
                clean = line.split(". ", 1)[1].strip()
                if clean and len(clean) > 10 and len(clean) < 200:
                    bullets.append(f"\u2022 {clean}")
            # Also grab strong bold keywords (skip very short table cells and pipe artifacts)
            elif "**" in line and line.count("**") >= 2:
                import re
                bolds = re.findall(r'\*\*(.+?)\*\*', line)
                for b in bolds:
                    b_clean = b.strip().rstrip(":").strip()
                    # Skip: short (< 22 chars), table-looking (contains |),
                    # sparse (<= 3 words), or ending with colon
                    word_count = len(b_clean.split())
                    if (b_clean and len(b_clean) >= 22
                            and "|" not in b_clean
                            and not b_clean.endswith(":")
                            and word_count >= 4):
                        bullets.append(f"\u2022 {b_clean}")
            
            if len(bullets) >= 5:
                break
    
    # Strategy 2: If no bullets found, generate from excerpt and title
    if len(bullets) < 3:
        bullets = []
        
        # Parse excerpt into factoids - split on colons and significant punctuation
        excerpt_parts = [s.strip() for s in excerpt.replace(":", ".\n").split("\n") if s.strip()]
        
        if len(excerpt_parts) >= 2:
            for part in excerpt_parts[:5]:
                if part and len(part) > 15:
                    bullets.append(f"\u2022 {part.rstrip('.')}.")
        else:
            # Generate generic bullets based on common Nexa themes
            generic_bullets = [
                "\u2022 Paraguay ofrece uno de los sistemas tributarios m\u00e1s atractivos de Am\u00e9rica Latina: 0% sobre ingresos del extranjero.",
                "\u2022 El proceso de residencia es accesible, transparente y cada vez m\u00e1s eficiente.",
                "\u2022 Con Nexa Paraguay tienes acompa\u00f1amiento completo, desde la documentaci\u00f3n hasta la post-llegada.",
                "\u2022 Sin inversi\u00f3n m\u00ednima requerida para obtener la residencia temporaria.",
                "\u2022 Costo de vida hasta 60% menor que en Europa, sin renunciar a calidad.",
            ]
            bullets = generic_bullets[:5]
    
    return bullets[:5]


# ─── Main Logic ──────────────────────────────────────────────────────────────

def reset_tracker():
    """Reset the posted tracker."""
    save_posted_tracker(set())
    print(f"TRACKER_RESET|Posted tracker cleared at {TRACKER_PATH}")
    return 0


def main():
    # Handle flags
    if "--reset" in sys.argv:
        return reset_tracker()
    
    is_live = "--live" in sys.argv
    
    # Load content
    content = load_json(CONTENT_PATH)
    if content is None:
        print("ERROR|Failed to load content file. Exiting.", file=sys.stderr)
        return 1
    
    # Extract blog posts
    blog = content.get("blog", {})
    posts = blog.get("posts", [])
    
    if not posts:
        print("STATUS|No blog posts found in content.")
        return 0
    
    # Load posted tracker
    posted_slugs = load_posted_tracker()
    
    # Find new posts within lookback window
    new_posts = []
    for post in posts:
        slug = post.get("slug", "")
        date_str = post.get("date", "")
        post_date = parse_date(date_str)
        
        if not slug:
            continue
        
        if slug in posted_slugs:
            continue
        
        if is_within_days(post_date):
            new_posts.append(post)
    
    if not new_posts:
        print("STATUS|No new posts to share.")
        return 0
    
    # Process each new post
    for post in new_posts:
        slug = post.get("slug", "")
        title = post.get("title", "Untitled")
        post_date = post.get("date", "unknown")
        locale = LOCALE
        
        # Generate LinkedIn post
        linkedin_text = generate_linkedin_post(post)
        
        # Print in pipe-friendly format
        print(f"LINKEDIN_POST|{locale}|{slug}|{title}|{linkedin_text}")
        
        # In live mode, attempt API call
        if is_live:
            linkedin_api_token = os.environ.get("LINKEDIN_ACCESS_TOKEN", "")
            linkedin_author_urn = os.environ.get("LINKEDIN_AUTHOR_URN", "")
            
            if not linkedin_api_token or not linkedin_author_urn:
                print(f"  WARNING|LIVE mode requires LINKEDIN_ACCESS_TOKEN and LINKEDIN_AUTHOR_URN env vars. Skipping {slug}.",
                      file=sys.stderr)
            #     # --- LinkedIn API POST (commented out until keys are available) ---
            #     # import requests  # would need 'requests' or use urllib
            #     # payload = {
            #     #     "author": linkedin_author_urn,
            #     #     "lifecycleState": "PUBLISHED",
            #     #     "specificContent": {
            #     #         "com.linkedin.ugc.ShareContent": {
            #     #             "shareCommentary": {
            #     #                 "text": linkedin_text
            #     #             },
            #     #             "shareMediaCategory": "NONE"
            #     #         }
            #     #     },
            #     #     "visibility": {
            #     #         "com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"
            #     #     }
            #     # }
            #     # headers = {
            #     #     "Authorization": f"Bearer {linkedin_api_token}",
            #     #     "X-Restli-Protocol-Version": "2.0.0",
            #     #     "Content-Type": "application/json"
            #     # }
            #     # resp = requests.post(LINKEDIN_API_URL, json=payload, headers=headers)
            #     # resp.raise_for_status()
            #     # print(f"  POSTED|{slug}|LinkedIn post ID: {resp.json().get('id')}")
        
        # Mark as posted
        posted_slugs.add(slug)
    
    # Save updated tracker
    save_posted_tracker(posted_slugs)
    
    print(f"STATUS|Processed {len(new_posts)} new post(s). Tracker has {len(posted_slugs)} total entries.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
