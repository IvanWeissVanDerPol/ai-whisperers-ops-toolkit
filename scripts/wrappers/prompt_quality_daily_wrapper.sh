#!/usr/bin/env bash
# prompt_quality_daily_wrapper.sh — R20-5: Daily prompt quality report
# Links traces to registered prompts, reports quality scores.
# Watchdog semantic (R16): output is the signal; exit 0 means ran successfully.
exec python3 /root/.hermes/scripts/trace_prompt_linker.py --days 7
