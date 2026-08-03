#!/usr/bin/env bash
# Add Traefik Host() rules for fleet aliases to the corresponding Docker service labels.
# Some services use standalone toml files, others use Docker labels — handle both.

set -euo pipefail
VPS="root@72.61.44.159"
TRAEFIK_DIR="/opt/traefik/dynamic"

# Map: alias → canonical service name
declare -a ALIASES=(
  "bichosgym|bichos-gym"
  "cocodrilofitness|cocodrilo-fitness"
  "dayah|dayah-litworks"
  "jotaink|jota-ink-tattoo"
  "luis-de-leon|luis-de-leon-concept"
  "trentina|trentina-cerveza"
  "villa-mayor-asociados|villamayor-asociados"
  "magnolia-flower|magnolia-peluqueria"
)

for entry in "${ALIASES[@]}"; do
  IFS='|' read -r alias canon <<< "$entry"
  svc="${canon}_web"
  rule_key="traefik.http.routers.${canon}.rule"
  rule_val="Host(\`${alias}.paragu-ai.com\`)"

  echo "--- $alias → $canon ---"

  # Approach 1: standalone toml file
  CANON_FILE="$TRAEFIK_DIR/${canon}.toml"
  if ssh "$VPS" "test -f $CANON_FILE" 2>/dev/null; then
    ROUTE_FILE="$TRAEFIK_DIR/${alias}-alias.toml"

    # Find service URL from canonical
    SERVICE_URL=$(ssh "$VPS" "grep -oE 'url = \"[^\"]+\"' $CANON_FILE | head -1 | cut -d'\"' -f2")

    if [ -n "$SERVICE_URL" ]; then
      CONTENT="[http.routers]
  [http.routers.${alias}-alias]
    entryPoints = [\"web\", \"websecure\"]
    rule = \"Host(\`${alias}.paragu-ai.com\`)\"
    service = \"${svc}-alias-service\"
    [http.routers.${alias}-alias.tls]
      certResolver = \"letsencryptresolver\"

[http.services]
  [http.services.${svc}-alias-service.loadBalancer]
    [[http.services.${svc}-alias-service.loadBalancer.servers]]
      url = \"$SERVICE_URL\"
"
      echo "$CONTENT" | ssh "$VPS" "cat > $ROUTE_FILE"
      ssh "$VPS" "chmod 644 $ROUTE_FILE"
      echo "  ✓ toml: $ROUTE_FILE"
      continue
    fi
  fi

  # Approach 2: Docker labels
  # Check if service exists + current rule
  CURRENT=$(ssh "$VPS" "docker service inspect $svc --format '{{index .Spec.Labels \"$rule_key\"}}'" 2>/dev/null || echo "")
  if [ -z "$CURRENT" ]; then
    echo "  ✗ service $svc not found or has no rule label"
    continue
  fi

  # Add a new router label for the alias (don't modify the canonical)
  SAFE_NAME="${canon}-${alias//-/_}"
  # The Traefik Host() rule syntax requires backticks (e.g. Host(`alias.com`)) per Traefik docs.
  # However, when sshing to run docker service update, bash interprets those backticks as
  # command substitution (parses `alias.paragu-ai.com` as a sub-command) which fails.
  #
  # Traefik ALSO accepts single-quoted Host() syntax: Host('alias.paragu-ai.com')
  # This is equivalent and doesn't conflict with bash parsing.
  # Source: https://doc.traefik.io/traefik/routing/routers/#rule
  #
  # Build the docker label command via printf to avoid any bash interpretation,
  # then pipe to ssh as stdin. This sidesteps the 3-layer bash quoting nightmare
  # (local bash → ssh arg → remote bash -c).
  SSH_SCRIPT=$(printf 'docker service update --label-add=traefik.enable=true %s\n' "$svc"
               printf 'docker service update --label-add='"'"'traefik.http.routers.%s.rule=Host(%s.paragu-ai.com)'"'"' %s\n' "$SAFE_NAME" "$alias" "$svc"
               printf 'docker service update --label-add=traefik.http.routers.%s.entrypoints=websecure %s\n' "$SAFE_NAME" "$svc"
               printf 'docker service update --label-add=traefik.http.routers.%s.tls=true %s\n' "$SAFE_NAME" "$svc"
               printf 'docker service update --label-add=traefik.http.routers.%s.tls.certresolver=letsencryptresolver %s\n' "$SAFE_NAME" "$svc")
  printf '%s' "$SSH_SCRIPT" | ssh "$VPS" bash 2>&1 | tail -5
  echo "  ✓ labels added to $svc (router name: $SAFE_NAME)"
done

echo ""
echo "Waiting 8s for Traefik to reload..."
sleep 8

echo ""
echo "=== Verification ==="
for entry in "${ALIASES[@]}"; do
  IFS='|' read -r alias _ <<< "$entry"
  code=$(curl -sL -o /dev/null -w "%{http_code}" --max-time 10 "https://${alias}.paragu-ai.com/" 2>/dev/null)
  echo "  ${alias}.paragu-ai.com → $code"
done