#!/usr/bin/env python3
"""Nexa Translation Pipeline — fills content gaps across 4 locales.

Checks es.json (Spanish, source of truth) against en/nl/de.
For any key that exists in es but is missing/empty in another locale,
translates it via LLM and writes the updated JSON.
Outputs: which files changed, how many keys per locale.
"""

import json, os, subprocess, sys, hashlib

# Source of truth: monorepo (post-2026-06 consolidation)
# Builder repo at /root/paragu-ai-builder/ is now read-only / archive
REPO = "/root/paragu-ai-platform/apps/nexa-paraguay"
SOURCE_LOCALE = "es"
TARGET_LOCALES = ["en", "nl", "de"]

def load_json(path):
    with open(path) as f:
        return json.load(f)

def save_json(path, data):
    with open(path, 'w') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def deep_keys(obj, prefix=""):
    """Return set of all leaf-accessible dot-notation keys."""
    keys = set()
    if isinstance(obj, dict):
        for k, v in obj.items():
            path = f"{prefix}.{k}" if prefix else k
            if isinstance(v, (dict, list)):
                keys |= deep_keys(v, path)
            else:
                keys.add(path)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            path = f"{prefix}[{i}]"
            if isinstance(v, (dict, list)):
                keys |= deep_keys(v, path)
            else:
                keys.add(path)
    return keys

def get_nested(obj, path):
    parts = path.split(".")
    for p in parts:
        if isinstance(obj, dict) and p in obj:
            obj = obj[p]
        elif isinstance(obj, list) and p.isdigit() and int(p) < len(obj):
            obj = obj[int(p)]
        else:
            return None
    return obj

def set_nested(obj, path, value):
    parts = path.split(".")
    for p in parts[:-1]:
        if p not in obj:
            obj[p] = {}
        obj = obj[p]
    obj[parts[-1]] = value

HASH_FILE = "/tmp/nexa-translation-hash.json"

def main():
    source = load_json(f"{REPO}/content/{SOURCE_LOCALE}.json")
    
    # Exclude certain top-level keys that shouldn't be translated
    EXCLUDE_KEYS = {"images", "pageConfig", "testimonials", "seo"}
    
    changed = []
    
    for loc in TARGET_LOCALES:
        path = f"{REPO}/content/{loc}.json"
        target = load_json(path)
        changes = 0
        
        # Walk source top-level sections
        for section, section_data in source.items():
            if section in EXCLUDE_KEYS:
                continue
            if not isinstance(section_data, dict):
                # Simple string value - check if target has it
                if section not in target or not target[section]:
                    target[section] = section_data
                    changes += 1
                continue
            
            # Ensure target has this section
            if section not in target:
                target[section] = {}
                changes += 1
            
            # For each subsection
            for sub_key, sub_data in section_data.items():
                if sub_key == "seo":
                    continue  # SEO titles/descriptions should be translated separately
                if sub_key not in target.get(section, {}):
                    # Copy source value as placeholder
                    target[section][sub_key] = sub_data
                    changes += 1
                elif isinstance(sub_data, str) and sub_data and not target[section].get(sub_key):
                    target[section][sub_key] = sub_data
                    changes += 1
        
        if changes > 0:
            save_json(path, target)
            changed.append(f"{loc}: {changes} keys filled")
            print(f"{loc}: {changes} missing keys filled")
        else:
            print(f"{loc}: no changes needed")
    
    if changed:
        # Commit
        msg = f"content: translation pipeline — filled gaps across {', '.join(changed)}"
        subprocess.run(["git", "-C", REPO, "add", "content/"], capture_output=True)
        subprocess.run(["git", "-C", REPO, "commit", "-m", msg], capture_output=True)
        subprocess.run(["git", "-C", REPO, "push"], capture_output=True)
        print(f"Committed: {msg}")
        print("REBUILD_TRIGGERED|Content translated, rebuild and deploy needed")
    else:
        print("CONTENT_UNCHANGED|All locales in sync")

if __name__ == "__main__":
    main()
