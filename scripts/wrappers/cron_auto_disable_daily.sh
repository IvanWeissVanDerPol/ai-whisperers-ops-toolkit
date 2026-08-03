#!/usr/bin/env bash
# cron_auto_disable_daily.sh — R17: Wire cron_auto_disable.py into a daily cron
# Runs with --threshold 5 (5 consecutive failures = auto-disable).
# Watchdog semantic (R16): cron_auto_disable.py always exits 0 (auto-disabling IS its job).
exec python3 /root/.hermes/scripts/cron_auto_disable.py --threshold 5
