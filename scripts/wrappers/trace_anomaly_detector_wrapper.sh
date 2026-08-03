#!/usr/bin/env bash
# trace_anomaly_detector_wrapper.sh — R18: Daily anomaly detection
# Output: human-readable anomaly report (delivered via cron deliver]
# Watchdog semantic (R16): output is the signal; exit 0 means ran successfully.
exec python3 /root/.hermes/scripts/trace_anomaly_detector.py
