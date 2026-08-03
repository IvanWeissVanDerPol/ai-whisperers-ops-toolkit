#!/usr/bin/env bash
# Create a Jira issue.
# Usage: jira-create.sh <project_key> <summary> [description] [issue_type]
# Example: jira-create.sh OMETZ "Update hero image" "Per Gaby feedback..." "Task"
# Requires: JIRA_URL, JIRA_USERNAME, JIRA_API_TOKEN

set -euo pipefail
PROJECT="${1:?usage: jira-create.sh <project> <summary> [description] [type]}"
SUMMARY="${2:?usage: jira-create.sh <project> <summary> [description] [type]}"
DESCRIPTION="${3:-}"
ISSUE_TYPE="${4:-Task}"

set -a; source /root/.hermes/.env; set +a
: "${JIRA_URL:?JIRA_URL not set}"
: "${JIRA_USERNAME:?JIRA_USERNAME not set}"
: "${JIRA_API_TOKEN:?JIRA_API_TOKEN not set}"

# Use Jira REST API v3 (requires ADF for description)
# For simplicity, use plain text by wrapping in ADF paragraph
ADF_DESC=$(python3 -c "
import json
print(json.dumps({
    'type': 'doc',
    'version': 1,
    'content': [{'type': 'paragraph', 'content': [{'type': 'text', 'text': '''${DESCRIPTION//\'/\\\'}'''}]}]
}))
")

curl -sf -u "${JIRA_USERNAME}:${JIRA_API_TOKEN}" \
  -X POST "${JIRA_URL}/rest/api/3/issue" \
  -H "Content-Type: application/json" \
  -d "$(python3 -c "
import json
print(json.dumps({
    'fields': {
        'project': {'key': '${PROJECT}'},
        'summary': '''${SUMMARY//\'/\\\'}''',
        'description': ${ADF_DESC},
        'issuetype': {'name': '${ISSUE_TYPE}'}
    }
}))
")" | python3 -c "
import json, sys
d = json.load(sys.stdin)
if 'key' in d:
    print(f\"✓ Created {d['key']}: ${JIRA_URL}/browse/{d['key']}\")
else:
    print(f'❌ {json.dumps(d, indent=2)}')
    sys.exit(1)
"