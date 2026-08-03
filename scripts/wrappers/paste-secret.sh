#!/usr/bin/env bash
# Safely paste a secret into /root/.hermes/.env without truncation.
# Usage: bash paste-secret.sh VAR_NAME
# Will prompt for the value (hidden input), then write/update .env with 0600 perms.

set -euo pipefail

VAR="${1:?usage: paste-secret.sh VAR_NAME}"

if [ ! -f /root/.hermes/.env ]; then
  touch /root/.hermes/.env
fi

# Prompt hidden
read -rs -p "Paste value for $VAR (input hidden): " VAL
echo

if [ -z "$VAL" ]; then
  echo "✗ Empty value — nothing written"
  exit 1
fi

# Check if exists
if grep -q "^${VAR}=" /root/.hermes/.env; then
  # Replace existing line
  python3 << EOF
import re
with open('/root/.hermes/.env') as f:
    lines = f.readlines()
for i, l in enumerate(lines):
    if l.startswith('${VAR}='):
        lines[i] = '${VAR}="' + '''$VAL''' + '"\n'
        break
with open('/root/.hermes/.env', 'w') as f:
    f.writelines(lines)
EOF
  echo "✓ $VAR updated (existing entry replaced)"
else
  # Append new
  echo "${VAR}=\"$VAL\"" >> /root/.hermes/.env
  echo "✓ $VAR appended"
fi

chmod 600 /root/.hermes/.env
echo "  /root/.hermes/.env perms: $(stat -c '%a' /root/.hermes/.env)"