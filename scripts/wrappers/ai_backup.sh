#!/usr/bin/env bash
mkdir -p /var/backups/ai-whisperers /var/log
exec /usr/bin/env python3 /root/.hermes/scripts/ai_backup.py
