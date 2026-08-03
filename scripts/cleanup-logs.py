#!/usr/bin/env python3
"""
Hermes Log Cleanup — runs daily via cron.

Compresses log files older than 7 days, deletes logs older than 30 days.
Caps total logs size at 50MB by default.
Reports freed space.
"""
import os
import sys
import time
import gzip
import shutil
from datetime import datetime

LOG_DIR = "/root/.hermes/logs"
DAYS_KEEP_UNCOMPRESSED = 7
DAYS_KEEP_COMPRESSED = 30
MAX_TOTAL_MB = 50


def file_age_days(path):
    return (time.time() - os.path.getmtime(path)) / 86400


def file_size_mb(path):
    return os.path.getsize(path) / (1024 * 1024)


def main():
    if not os.path.isdir(LOG_DIR):
        print(f"Log dir {LOG_DIR} not found")
        return 0

    total_before = sum(file_size_mb(os.path.join(r, f))
                        for r, _, files in os.walk(LOG_DIR) for f in files) * 1024 * 1024

    compressed = 0
    deleted = 0
    freed_bytes = 0

    for root, _, files in os.walk(LOG_DIR):
        for fname in files:
            fpath = os.path.join(root, fname)
            if fname.endswith(('.gz', '.zip', '.tar', '.lock', '.tmp', '.swp', '.pid')):
                continue

            age = file_age_days(fpath)
            size = os.path.getsize(fpath)

            try:
                if age > DAYS_KEEP_COMPRESSED:
                    os.remove(fpath)
                    deleted += 1
                    freed_bytes += size
                elif age > DAYS_KEEP_UNCOMPRESSED and not fname.endswith('.log.1'):
                    if fname.endswith(('.log', '.txt', '.jsonl')):
                        with open(fpath, 'rb') as f_in:
                            with gzip.open(fpath + '.gz', 'wb') as f_out:
                                shutil.copyfileobj(f_in, f_out)
                        os.remove(fpath)
                        compressed += 1
                        freed_bytes += size - os.path.getsize(fpath + '.gz')
            except (PermissionError, OSError) as e:
                print(f"  skipped {fname}: {e}")

    # If still over budget, delete oldest compressed files
    total_after = sum(file_size_mb(os.path.join(r, f))
                      for r, _, files in os.walk(LOG_DIR) for f in files) * 1024 * 1024
    total_mb = total_after / (1024 * 1024)

    if total_mb > MAX_TOTAL_MB:
        all_logs = []
        for r, _, files in os.walk(LOG_DIR):
            for f in files:
                p = os.path.join(r, f)
                all_logs.append((os.path.getmtime(p), p, os.path.getsize(p)))
        all_logs.sort()
        for _, p, sz in all_logs:
            if total_mb <= MAX_TOTAL_MB:
                break
            try:
                os.remove(p)
                deleted += 1
                freed_bytes += sz
                total_mb -= sz / (1024 * 1024)
            except OSError:
                pass

    freed_mb = freed_bytes / (1024 * 1024)
    print(f"🧹 Log cleanup: {compressed} compressed, {deleted} deleted, {freed_mb:.1f}MB freed (now {total_mb:.0f}MB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
