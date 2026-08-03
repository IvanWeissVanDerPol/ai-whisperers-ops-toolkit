#!/usr/bin/env bash
# List recent Jira issues (or one specific issue).
# Usage: jira-list.sh [project_key] [count]
# Example: jira-list.sh OMETZ 5
# Requires: JIRA_URL, JIRA_USERNAME, JIRA_API_TOKEN

set -euo pipefail
PROJECT="${1:-}"
COUNT="${2:-10}"

set -a; source /root/.hermes/.env; set +a
: "${JIRA_URL:?JIRA_URL not set}"
: "${JIRA_USERNAME:?JIRA_USERNAME not set}"
: "${JIRA_API_TOKEN:?JIRA_API_TOKEN not set}"

JQL="${PROJECT:+project=${PROJECT}} ORDER BY created DESC"
curl -sf -u "${JIRA_USERNAME}:${JIRA_API_TOKEN}" \
  -G --data-urlencode "jql=${JQL}" \
  --data-urlencode "maxResults=${COUNT}" \
  "${JIRA_URL}/rest/api/3/search" | python3 -c "
import json, sys
d = json.load(sys.stdin)
for i in d.get('issues', []):
    fields = i['fields']
    key = i['key']
    summary = fields.get('summary', '?')[:60]
    status = fields.get('status', {}).get('name', '?')
    assignee = fields.get('assignee', {})
    assignee_name = assignee.get('displayName', 'Unassigned') if assignee else 'Unassigned'
    print(f\"  {key:<12} {status:<15} {assignee_name:<25} {summary}\")
"