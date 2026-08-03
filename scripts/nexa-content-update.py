#!/usr/bin/env python3
"""Nexa Content Update Check — runs daily via Hermes cron.
Checks if content files have changed since last run. If so, triggers rebuild.
"""
import json, os, hashlib, subprocess, sys

REPO = "/root/nexa-paraguay"
STATE_FILE = "/tmp/nexa-content-hash.json"

def hash_content():
    hasher = hashlib.sha256()
    for root, dirs, files in os.walk(os.path.join(REPO, "content")):
        for f in sorted(files):
            path = os.path.join(root, f)
            if f.startswith("."): continue
            with open(path, "rb") as fh:
                hasher.update(fh.read())
    for root, dirs, files in os.walk(os.path.join(REPO, "nexa-pages")):
        for f in sorted(files):
            path = os.path.join(root, f)
            with open(path, "rb") as fh:
                hasher.update(fh.read())
    return hasher.hexdigest()

def main():
    current = hash_content()
    old = {}
    try:
        with open(STATE_FILE) as f:
            old = json.load(f)
    except: pass

    if old.get("hash") == current:
        print(f"CONTENT_UNCHANGED|Hash {current[:12]} — no action needed")
        return

    print(f"CONTENT_CHANGED|Hash changed: {old.get('hash','none')[:12]} → {current[:12]}")
    print("REBUILD_TRIGGERED|Running build and deploy...")
    
    result = subprocess.run(
        ["docker", "service", "update", "--force", "nexa_web"],
        capture_output=True, text=True, timeout=120
    )
    print(result.stdout[-200:] if result.stdout else f"EXIT|{result.returncode}")

    # Save new hash
    with open(STATE_FILE, "w") as f:
        json.dump({"hash": current}, f)

    print("REBUILD_OK|Content deployed")

if __name__ == "__main__":
    main()
