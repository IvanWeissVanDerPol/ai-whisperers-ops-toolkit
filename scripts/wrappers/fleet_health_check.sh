#!/usr/bin/env bash
# Wrapper: ensure logs dir, suppress stack traces, exit with python's code.
mkdir -p /var/log
exec /usr/bin/env python3 /root/.hermes/scripts/fleet_health_check.py
