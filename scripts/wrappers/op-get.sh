#!/usr/bin/env bash
# Read a 1Password secret and print to stdout.
# Usage: op-get.sh "op://Vault/Item/field"
# Requires: OP_SERVICE_ACCOUNT_TOKEN in /root/.hermes/.env

set -euo pipefail
REF="${1:?usage: op-get.sh op://Vault/Item/field}"

set -a; source /root/.hermes/.env; set +a
: "${OP_SERVICE_ACCOUNT_TOKEN:?OP_SERVICE_ACCOUNT_TOKEN not set}"

if ! command -v op >/dev/null; then
  echo "❌ op CLI not installed. See OMETZ_SETUP_GUIDE.md §5"; exit 1
fi

op read "$REF"