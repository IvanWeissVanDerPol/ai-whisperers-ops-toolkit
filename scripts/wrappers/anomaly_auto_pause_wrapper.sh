#!/usr/bin/env bash
# anomaly_auto_pause_wrapper.sh — R19-3: Daily auto-pause for high-cost crons
# Threshold $5: pause any cron that triggered a high-severity cost anomaly.
# Watchdog semantic (R16): output is the signal; exit 0 means ran successfully.
exec python3 /root/.hermes/scripts/anomaly_auto_pause.py --threshold 5.0
