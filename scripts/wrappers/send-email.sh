#!/usr/bin/env bash
# Send email via Himalaya CLI (IMAP/SMTP).
# Usage: send-email.sh <to> <subject> <body_file>
# Example: send-email.sh "gaby@ometzdental.com" "Test" /tmp/body.txt

set -euo pipefail
TO="${1:?usage: send-email.sh <to> <subject> <body_file>}"
SUBJECT="${2:?usage: send-email.sh <to> <subject> <body_file>}"
BODY_FILE="${3:?usage: send-email.sh <to> <subject> <body_file>}"

if [ ! -f "$BODY_FILE" ]; then echo "❌ Body file not found: $BODY_FILE"; exit 1; fi

if ! command -v himalaya >/dev/null; then
  echo "❌ himalaya not installed. See OMETZ_SETUP_GUIDE.md §2"
  exit 1
fi

himalaya template send <<EOF
To: ${TO}
Subject: ${SUBJECT}

$(cat "$BODY_FILE")
EOF

echo "✓ Email sent to $TO"