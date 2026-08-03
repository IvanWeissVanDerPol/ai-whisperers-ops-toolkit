#!/usr/bin/env bash
# Drive sync — list/search files in a Google Drive folder.
# Usage: drive-list.sh [folder_id] [search_query]
# If folder_id omitted, lists root. If search_query provided, searches by name.
# Requires: google_token.json + python3 with google-api-python-client

set -euo pipefail
FOLDER_ID="${1:-}"
QUERY="${2:-}"

TOKEN_FILE="/root/.hermes/google_token.json"
[ -f "$TOKEN_FILE" ] || { echo "❌ $TOKEN_FILE missing. See OMETZ_SETUP_GUIDE.md §3"; exit 1; }

# Activate venv if exists (where google libs were installed)
VENV="/root/.hermes/venv-google"
if [ -d "$VENV" ]; then
  source "$VENV/bin/activate"
fi

python3 << EOF
import json, os, sys
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

with open('$TOKEN_FILE') as f:
    token_data = json.load(f)

creds = Credentials.from_authorized_user_info(token_data)
service = build('drive', 'v3', credentials=creds)

q_parts = []
if '$FOLDER_ID':
    q_parts.append(f"'$FOLDER_ID' in parents")
if '$QUERY':
    q_parts.append(f"name contains '$QUERY'")
q_parts.append("trashed=false")
q = " and ".join(q_parts)

results = service.files().list(
    q=q, pageSize=30,
    fields="files(id, name, mimeType, modifiedTime, size)",
    orderBy="modifiedTime desc"
).execute()

files = results.get('files', [])
if not files:
    print("(no files)")
else:
    print(f"{'ID':<44} {'MODIFIED':<20} {'NAME':<50}")
    print("-" * 114)
    for f in files:
        name = f['name'][:48] + '..' if len(f['name']) > 50 else f['name']
        print(f"{f['id']:<44} {f['modifiedTime'][:19]:<20} {name}")
EOF