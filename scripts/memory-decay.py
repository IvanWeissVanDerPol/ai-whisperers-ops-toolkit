#!/usr/bin/env python3
"""memory-decay.py — Mnemosyne memory decay analysis.

Pattern from r/hermesagent "Mnemosyne memory decay" thread.
Identifies stale memories with low importance scores and flags for review.

Usage:
    python3 memory-decay.py [--dry-run] [--threshold 0.3]
"""
import os
import json
import sys
import argparse
import datetime

HERMES_HOME = os.path.expanduser("~/.hermes")
LOG_DIR = os.path.join(HERMES_HOME, "logs")
MNEMOSYNE_DB = os.path.join(HERMES_HOME, "mnemosyne/memory.db")
MEMORY_FILE = os.path.join(HERMES_HOME, "MEMORY.md")
USER_FILE = os.path.join(HERMES_HOME, "USER.md")


def get_memories_from_file(path):
    """Read memories from a markdown file. Each line is a memory entry."""
    if not os.path.exists(path):
        return []
    with open(path) as f:
        lines = f.readlines()
    # Skip headers, blank lines, comments
    return [
        line.strip().lstrip("- ").strip()
        for line in lines
        if line.strip() and not line.strip().startswith("#")
    ]


def analyze_memory(memory_entries, threshold=0.3, dry_run=True):
    """Identify stale memories by simple heuristics.

    Heuristics:
      - Contains 'stale' or 'old' marker → high decay score
      - Has a date older than 60 days → decay
      - Very short entry (likely a context note) → medium decay
      - Contains user-specific fact (Kiki, Ivan) → keep
      - Contains 'boring reliability' / 'community' / 'pattern' → keep
    """
    stale = []
    keep = []
    now = datetime.datetime.now()

    for entry in memory_entries:
        decay_score = 0.0
        reasons = []

        # Short entries more likely to be transient
        if len(entry) < 30:
            decay_score += 0.1
            reasons.append("very short")

        # Old dates
        if "2024" in entry or "2023" in entry:
            decay_score += 0.4
            reasons.append("contains 2023/2024 date")
        elif "2025" in entry and "-" in entry[:20]:
            decay_score += 0.2
            reasons.append("contains 2025 date")

        # Stale markers
        if "stale" in entry.lower() or "deprecated" in entry.lower():
            decay_score += 0.5
            reasons.append("marked stale")

        # Important: user/identity facts get a penalty (don't decay)
        if any(k in entry for k in ["Kiki", "Ivan", "Eneve", "Ai-Whisperers", "Paragu-ai"]):
            decay_score -= 0.5
            reasons.append("user/identity fact — protect")

        # Important: community wisdom / patterns
        if any(k in entry.lower() for k in ["boring reliability", "pattern", "principle"]):
            decay_score -= 0.3
            reasons.append("community principle — protect")

        if decay_score >= threshold:
            stale.append((entry, decay_score, reasons))
        else:
            keep.append((entry, decay_score, reasons))

    return stale, keep


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--dry-run", action="store_true", default=True,
                   help="Don't modify files, just report")
    p.add_argument("--threshold", type=float, default=0.3,
                   help="Decay threshold (entries above this are stale)")
    args = p.parse_args()

    os.makedirs(LOG_DIR, exist_ok=True)

    print(f"🧠 Mnemosyne memory decay analysis — {datetime.date.today()}")
    print(f"   threshold: {args.threshold}")
    print(f"   mode: {'DRY-RUN' if args.dry_run else 'LIVE'}")
    print()

    total_stale = 0
    total_keep = 0

    for label, path in [("MEMORY.md", MEMORY_FILE), ("USER.md", USER_FILE)]:
        entries = get_memories_from_file(path)
        if not entries:
            print(f"  {label}: no entries")
            continue

        stale, keep = analyze_memory(entries, args.threshold, args.dry_run)
        total_stale += len(stale)
        total_keep += len(keep)

        print(f"  {label}: {len(entries)} entries → {len(stale)} stale, {len(keep)} keep")
        if stale:
            for entry, score, reasons in stale[:5]:
                preview = entry[:60].replace("\n", " ")
                print(f"    🗑 score={score:.2f} {preview}... ({', '.join(reasons)})")
            if len(stale) > 5:
                print(f"    ... and {len(stale) - 5} more")

    print()
    print(f"  TOTAL: {total_stale} stale / {total_keep} keep")

    # Log result
    log_path = os.path.join(LOG_DIR, "memory-decay.log")
    with open(log_path, "a") as f:
        f.write(f"{datetime.datetime.now().isoformat()} | stale={total_stale} keep={total_keep} threshold={args.threshold}\n")

    # Exit 0 if no stale, 1 if any stale (so cron can alert)
    return 0 if total_stale == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
