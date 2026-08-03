#!/usr/bin/env python3
"""
kanban_log_rotate — rotate kanban cron logs when they get too big or too old.

Tier 3.5 — log rotation by size (>10MB) or age (>30 days).

Usage:
  python3 kanban_log_rotate.py            # rotate as needed
  python3 kanban_log_rotate.py --dry-run  # show what would be rotated, don't do it

Rotates:
  ~/.hermes/inbox/kanban-*.log
  ~/.hermes/inbox/kanban-*.log.N.gz (existing rotations)

Strategy:
  - When log > MAX_SIZE_BYTES, rotate to <log>.1.gz
  - Existing rotations shift up: .1.gz → .2.gz, .2.gz → .3.gz, etc.
  - Keep MAX_ROTATIONS old rotations
  - When log > MAX_AGE_DAYS, also rotate
  - Dry-run prints what would be done
"""

from __future__ import annotations

import argparse
import gzip
import shutil
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from kanban_common import INBOX_DIR

MAX_SIZE_BYTES = 10 * 1024 * 1024  # 10 MB
MAX_AGE_DAYS = 30
MAX_ROTATIONS = 5


def should_rotate(log_path: Path) -> tuple[bool, str]:
    """Return (should_rotate, reason)."""
    if not log_path.exists():
        return False, "does not exist"
    size = log_path.stat().st_size
    if size > MAX_SIZE_BYTES:
        return True, f"size {size:,} bytes > {MAX_SIZE_BYTES:,}"
    age_days = (datetime.now().timestamp() - log_path.stat().st_mtime) / 86400
    if age_days > MAX_AGE_DAYS:
        return True, f"age {age_days:.1f} days > {MAX_AGE_DAYS}"
    return False, "ok"


def rotate_log(log_path: Path, dry_run: bool = False) -> list[str]:
    """Rotate one log file. Returns list of actions taken."""
    actions = []

    # Shift existing rotations up: .4.gz → .5.gz, .3.gz → .4.gz, ..., .1.gz → .2.gz
    for i in range(MAX_ROTATIONS, 0, -1):
        src = log_path.with_suffix(f"{log_path.suffix}.{i}.gz")
        if src.exists():
            if i == MAX_ROTATIONS:
                # Delete the oldest
                if not dry_run:
                    src.unlink()
                    actions.append(f"deleted {src.name}")
                else:
                    actions.append(f"would delete {src.name}")
            else:
                dst = log_path.with_suffix(f"{log_path.suffix}.{i+1}.gz")
                if not dry_run:
                    src.rename(dst)
                    actions.append(f"renamed {src.name} → {dst.name}")
                else:
                    actions.append(f"would rename {src.name} → {dst.name}")

    # Rotate current log to .1.gz (compress)
    new_rotated = log_path.with_suffix(f"{log_path.suffix}.1.gz")
    if not dry_run:
        # Compress log to .1.gz
        with open(log_path, "rb") as f_in:
            with gzip.open(new_rotated, "wb") as f_out:
                shutil.copyfileobj(f_in, f_out)
        # Truncate original
        log_path.write_text("")
        actions.append(f"compressed {log_path.name} → {new_rotated.name}")
    else:
        actions.append(f"would compress {log_path.name} → {new_rotated.name}")

    return actions


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--dry-run", action="store_true", help="show what would be rotated")
    args = p.parse_args()

    if not INBOX_DIR.exists():
        print(f"inbox directory not found: {INBOX_DIR}")
        sys.exit(1)

    log_patterns = [
        "kanban-*.log",
        "kanban-pipeline-cron.log",
        "kanban-recurring-state.log",
    ]

    rotated = 0
    for pattern in log_patterns:
        for log_path in INBOX_DIR.glob(pattern):
            if log_path.suffix == ".gz":
                continue
            should, reason = should_rotate(log_path)
            if should:
                print(f"ROTATE {log_path.name}: {reason}")
                actions = rotate_log(log_path, dry_run=args.dry_run)
                for a in actions:
                    print(f"  {a}")
                rotated += 1
            else:
                pass  # silent for not-rotated

    if rotated == 0:
        print("No logs need rotation.")
    else:
        print(f"\n{rotated} log(s) {'would be' if args.dry_run else ''} rotated.")


if __name__ == "__main__":
    main()
