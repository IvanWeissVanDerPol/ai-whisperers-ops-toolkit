#!/usr/bin/env python3
"""Nexa image health watchdog. Checks that critical images load on nexa.paragu-ai.com and dev.nexa.paragu-ai.com."""
import json
import urllib.request
from pathlib import Path

# After monorepo consolidation, images.json lives in the paragu-ai-platform app dir
ROOT = Path('/root/paragu-ai-platform/apps/nexa-paraguay')
IMAGES_PATH = ROOT / 'images.json'
if not IMAGES_PATH.exists():
    print(f"Nexa image health: {IMAGES_PATH} not found — skipping")
    exit(0)

IMAGES = json.loads(IMAGES_PATH.read_text())

items = []

def walk(node):
    if isinstance(node, dict):
        if isinstance(node.get('src'), str):
            items.append(node['src'])
        for v in node.values():
            walk(v)
    elif isinstance(node, list):
        for v in node:
            walk(v)

walk(IMAGES.get('images', {}))

# Check critical + sample to keep it fast
critical = [
    '/images/brand/logo.webp',
    '/images/hero/hero-bg.webp',
    '/images/process/consultation.webp',
]
sample = sorted(set(items))[::max(1, len(set(items)) // 25)]
check_list = sorted(set(critical + sample))

base_hosts = ['https://nexa.paragu-ai.com', 'https://dev.nexa.paragu-ai.com']
errors = []

for host in base_hosts:
    for path in check_list:
        url = host + path
        try:
            req = urllib.request.Request(url, method='HEAD')
            with urllib.request.urlopen(req, timeout=12) as r:
                if r.status != 200:
                    errors.append(f'{url} -> {r.status}')
        except Exception as e:
            errors.append(f'{url} -> ERR:{e.__class__.__name__}')

if errors:
    print('Nexa image health alert')
    for e in errors[:60]:
        print(e)
