#!/bin/bash
# kanban_pipeline_cron — runs every 15 min
# 1. Detect new voice transcripts → voice-inbox board
# 2. Send WhatsApp notifications for due/overdue tasks (3 boards: ivan/kiki/lua)
# 3. Process incoming WhatsApp DONE replies (3 boards)

set -uo pipefail
LOG=/root/.hermes/inbox/kanban-pipeline-cron.log
echo "=== kanban pipeline cron $(date -Iseconds) ===" >> "$LOG"

# 1. Voice transcript detection
python3 /root/.hermes/scripts/kanban_voice_cron.py >> "$LOG" 2>&1

# 2. WhatsApp due/overdue notifications — all three people
for board in ivan-tasks kiki-tasks lua-tasks; do
    python3 /root/.hermes/scripts/kanban_whatsapp_notify.py \
        --board "$board" --mode overdue >> "$LOG" 2>&1
done

# 3. Process incoming WhatsApp DONE replies — all three boards
for board in ivan-tasks kiki-tasks lua-tasks; do
    python3 /root/.hermes/scripts/kanban_whatsapp_done_handler.py \
        --board "$board" >> "$LOG" 2>&1
done

echo "=== done $(date -Iseconds) ===" >> "$LOG"