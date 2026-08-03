#!/usr/bin/env bash
#
# pre-curator-snapshot.sh — snapshot skills, config, profiles, cron before curator runs
#
# Pattern from r/hermesagent "local-first Hermes plugin that evolves skills" thread:
#   "before trusting automated curator runs, the system should be able to restore
#    into a clean Hermes home and verify the previous skill set, evidence store,
#    provenance metadata, and scheduler hooks before the curator is allowed to run again"
#
# Output:
#   ~/.hermes/backups/snapshot-YYYYMMDD-HHMMSS/
#     ├── skills/         (full skill dir copy)
#     ├── config.yaml
#     ├── config.yaml.backup
#     ├── profiles/       (full profiles dir)
#     ├── cron/jobs.json
#     ├── plugin-manifest.json  (provenance: who/what/when for each skill)
#     └── MANIFEST.txt
#
# Cron usage: runs BEFORE weekly-curator-report and weekly-self-evolution
set -euo pipefail

# Ensure HOME is set
HOME="${HOME:-/root}"

HERMES_HOME="${HOME}/.hermes"
BACKUP_ROOT="${HERMES_HOME}/backups"
TS="$(date +%Y%m%d-%H%M%S)"
SNAP="${BACKUP_ROOT}/snapshot-${TS}"

mkdir -p "${SNAP}"

echo "📸 Pre-curator snapshot → ${SNAP}"

# 1. Config files
cp -a "${HERMES_HOME}/config.yaml" "${SNAP}/" 2>/dev/null || true
cp -a "${HERMES_HOME}/config.yaml.backup" "${SNAP}/" 2>/dev/null || true

# 2. Skills
if [ -d "${HERMES_HOME}/skills" ]; then
    cp -a "${HERMES_HOME}/skills" "${SNAP}/skills"
fi

# 3. Optional skills
if [ -d "${HERMES_HOME}/optional-skills" ]; then
    cp -a "${HERMES_HOME}/optional-skills" "${SNAP}/optional-skills"
fi

# 4. Profiles
if [ -d "${HERMES_HOME}/profiles" ]; then
    cp -a "${HERMES_HOME}/profiles" "${SNAP}/profiles"
fi

# 5. Cron
if [ -d "${HERMES_HOME}/cron" ]; then
    cp -a "${HERMES_HOME}/cron" "${SNAP}/cron"
fi

# 6. Plugins
if [ -d "${HERMES_HOME}/plugins" ]; then
    cp -a "${HERMES_HOME}/plugins" "${SNAP}/plugins"
fi

# 7. Build a provenance manifest — for each skill, when it was last edited
PROV="${SNAP}/plugin-manifest.json"
echo "{" > "${PROV}"
echo "  \"snapshot_ts\": \"${TS}\"," >> "${PROV}"
echo "  \"skills\": [" >> "${PROV}"
FIRST=1
for skill_dir in "${HERMES_HOME}/skills"/*/; do
    [ -d "${skill_dir}" ] || continue
    skill_name=$(basename "${skill_dir}")
    skill_md="${skill_dir}/SKILL.md"
    if [ -f "${skill_md}" ]; then
        last_modified=$(stat -c %Y "${skill_md}" 2>/dev/null || stat -f %m "${skill_md}" 2>/dev/null || echo "0")
        size=$(stat -c %s "${skill_md}" 2>/dev/null || stat -f %z "${skill_md}" 2>/dev/null || echo "0")
    else
        last_modified="0"
        size="0"
    fi
    if [ ${FIRST} -eq 0 ]; then echo "," >> "${PROV}"; fi
    FIRST=0
    printf '    {"name": "%s", "last_modified": "%s", "size": "%s"}' \
        "${skill_name}" "${last_modified}" "${size}" >> "${PROV}"
done
echo "" >> "${PROV}"
echo "  ]" >> "${PROV}"
echo "}" >> "${PROV}"

# 8. Manifest
cat > "${SNAP}/MANIFEST.txt" <<EOF
Hermes Pre-Curator Snapshot
============================
Timestamp: ${TS}
Trigger:  pre-curator (manual or auto)

Contents:
  - config.yaml (live)
  - config.yaml.backup
  - skills/ (full directory)
  - optional-skills/ (if present)
  - profiles/ (full directory)
  - cron/ (full directory)
  - plugins/ (full directory)
  - plugin-manifest.json (provenance: per-skill last-modified)

Restore command:
  rsync -a ${SNAP}/ ${HERMES_HOME}/
  # Or selective:
  cp ${SNAP}/config.yaml ${HERMES_HOME}/config.yaml

Retention:
  Keep last 5 snapshots. Run:
    ls -1dt ${BACKUP_ROOT}/snapshot-* | tail -n +6 | xargs rm -rf
EOF

# 9. Prune old snapshots (keep 5 most recent)
SNAPSHOTS=$(ls -1dt "${BACKUP_ROOT}"/snapshot-* 2>/dev/null | wc -l)
if [ "${SNAPSHOTS}" -gt 5 ]; then
    ls -1dt "${BACKUP_ROOT}"/snapshot-* | tail -n +6 | while read -r old; do
        echo "🗑️  Pruning old snapshot: ${old}"
        rm -rf "${old}"
    done
fi

TOTAL_SIZE=$(du -sh "${SNAP}" | cut -f1)
echo "✅ Snapshot complete: ${SNAP} (${TOTAL_SIZE})"
echo "   Skills captured: $(ls -1d ${SNAP}/skills/*/ 2>/dev/null | wc -l)"
echo "   Profiles captured: $(ls -1d ${SNAP}/profiles/*/ 2>/dev/null | wc -l)"
echo "   Retention: 5 most recent"
