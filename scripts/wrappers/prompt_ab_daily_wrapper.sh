#!/usr/bin/env bash
# prompt_ab_daily_wrapper.sh — R21-5: Daily A/B test status report
# Reports active A/B experiments and any promotion decisions.
# Watchdog semantic (R16): output is the signal; exit 0 means ran successfully.
exec python3 /root/.hermes/scripts/prompt_ab_tester.py status
