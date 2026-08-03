#!/usr/bin/env python3
"""
quality-findings-log — persistent per-repo findings log CLI.

Manages ~/.hermes/state/quality-findings/<repo-name>.md files with
structured New/Tracked/Partial annotations. The log replaces the
Eneve `tickets/quality-findings.md` in-repo pattern.

Usage:
    python3 quality_findings_log.py append --repo X --phase Y --severity Z --target T --issue I --fix F
    python3 quality_findings_log.py read --repo X
    python3 quality_findings_log.py update --repo X --id Y --status done --note "..."
    python3 quality_findings_log.py list-open
    python3 quality_findings_log.py dedupe --repo X --candidate-file path:line
    python3 quality_findings_log.py find-stale --days 90
    python3 quality_findings_log.py stale-cleanup --days 90
    python3 quality_findings_log.py archive-done --repo X
"""
from __future__ import annotations
import argparse
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

LOG_DIR = Path('/root/.hermes/state/quality-findings')
LOG_DIR.mkdir(parents=True, exist_ok=True)

VALID_PHASES = {'cov': 'coverage', 'crap': 'crap', 'cc': 'cc', 'prod-doc': 'prod-doc',
                'test-doc': 'test-doc', 'refactor': 'refactor',
                'arch': 'architecture', 'sec': 'security', 'dep': 'dependency',
                'other': 'other'}
# short alias -> full phase name (used in finding IDs)
PHASE_ALIASES = {'cov': 'coverage', 'arch': 'architecture', 'sec': 'security', 'dep': 'dependency'}
VALID_SEVERITIES = {'Critical', 'High', 'Medium', 'Low'}
VALID_STATUSES = {'open', 'tracked', 'partial', 'done', 'wontfix', 'stale'}

# ---------- low-level log I/O ----------

def log_path(repo: str) -> Path:
    return LOG_DIR / f'{repo}.md'

def read_log(repo: str) -> str:
    p = log_path(repo)
    return p.read_text(encoding='utf-8') if p.exists() else ''

def write_log(repo: str, content: str) -> None:
    log_path(repo).write_text(content, encoding='utf-8')

def next_finding_id(content: str, phase_alias: str) -> str:
    """Generate next YYYY-MM-DD-NNN ID for a phase (using short alias)."""
    today = datetime.now(timezone.utc).strftime('%Y-%m-%d')
    pattern = re.compile(rf'^### {re.escape(phase_alias)}-{today}-(\d{{3}})', re.MULTILINE)
    matches = pattern.findall(content)
    next_n = max([int(m) for m in matches], default=0) + 1
    return f'{phase_alias}-{today}-{next_n:03d}'

def parse_findings(content: str) -> list[dict]:
    """Parse all findings from a log into a list of dicts.

    Note: raw_lines preserves the trailing newline of each line so that
    content.replace(''.join(raw_lines), ...) works correctly.
    """
    findings = []
    current_phase = None
    current_finding = None
    # Use splitlines(keepends=True) so we keep \n
    for line in content.splitlines(keepends=True):
        # strip \n for the heading detection
        stripped = line.rstrip('\n')
        if stripped.startswith('## ') and not stripped.startswith('### '):
            current_phase = stripped[3:].strip()
        elif stripped.startswith('### ') and current_phase:
            if current_finding:
                findings.append(current_finding)
            current_finding = {
                'id': stripped[4:].strip(),
                'phase': current_phase,
                'fields': {},
                'raw_lines': [line],
            }
        elif current_finding and stripped.startswith('- **') and '**:' in stripped:
            # Format: - **Key**: value (single star on each side)
            key, _, value = stripped[4:].partition('**:')
            current_finding['fields'][key.strip()] = value.strip()
            current_finding['raw_lines'].append(line)
        elif current_finding:
            current_finding['raw_lines'].append(line)
    if current_finding:
        findings.append(current_finding)
    return findings

# ---------- append ----------

def cmd_append(args) -> int:
    if args.phase not in VALID_PHASES:
        print(f'ERROR: phase {args.phase!r} not in {list(VALID_PHASES.keys())}', file=sys.stderr)
        return 1
    if args.severity not in VALID_SEVERITIES:
        print(f'ERROR: severity {args.severity!r} not in {VALID_SEVERITIES}', file=sys.stderr)
        return 1
    full_phase = PHASE_ALIASES.get(args.phase, args.phase)
    content = read_log(args.repo)
    if not content:
        # bootstrap
        now = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')
        content = f'# Quality Findings — {args.repo}\n\n> Last updated: {now}\n\n'
    # ensure phase section (use full name as section header)
    section_header = f'## {full_phase}'
    if section_header not in content:
        content += f'\n{section_header}\n\n(empty — no findings yet)\n\n'
    fid = next_finding_id(content, args.phase)
    today = datetime.now(timezone.utc).strftime('%Y-%m-%d')
    block = (
        f'### {fid}\n'
        f'- **Phase**: {full_phase}\n'
        f'- **Severity**: {args.severity}\n'
        f'- **Target**: {args.target}\n'
        f'- **Issue**: {args.issue}\n'
        f'- **Fix**: {args.fix}\n'
        f'- **First seen**: {today}\n'
        f'- **Status**: open\n'
        f'- **Annotation history**: New ({today})\n\n'
    )
    # insert at end of phase section (just before the next ## or EOF)
    parts = content.split(section_header)
    if len(parts) == 2:
        phase_body = parts[1]
        lines = phase_body.splitlines(keepends=True)
        insert_idx = len(lines)
        rest = ''
        for i, line in enumerate(lines):
            if line.startswith('## '):
                insert_idx = i
                rest = ''.join(lines[i:])
                phase_body = ''.join(lines[:i])
                break
        phase_body = phase_body.rstrip() + '\n\n' + block + rest.lstrip('\n')
        content = parts[0] + section_header + phase_body
    # update "Last updated"
    now = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')
    content = re.sub(r'> Last updated: .+', f'> Last updated: {now}', content, count=1)
    write_log(args.repo, content)
    print(f'Appended: {fid}')
    return 0

# ---------- read ----------

def cmd_read(args) -> int:
    content = read_log(args.repo)
    if not content:
        print(f'(no log for {args.repo} — file: {log_path(args.repo)})')
        return 0
    print(content)
    return 0

# ---------- update ----------

def cmd_update(args) -> int:
    if args.status not in VALID_STATUSES:
        print(f'ERROR: status {args.status!r} not in {VALID_STATUSES}', file=sys.stderr)
        return 1
    content = read_log(args.repo)
    if not content:
        print(f'ERROR: no log for {args.repo}', file=sys.stderr)
        return 1
    findings = parse_findings(content)
    target = next((f for f in findings if f['id'] == args.id), None)
    if not target:
        print(f'ERROR: finding {args.id!r} not found in {args.repo}', file=sys.stderr)
        return 1
    # replace Status line and append to Annotation history
    old_status = target['fields'].get('Status', 'open')
    new_lines = []
    for line in target['raw_lines']:
        # raw_lines have trailing \n
        stripped = line.rstrip('\n')
        if stripped.startswith('- **Status**'):
            new_lines.append(f'- **Status**: {args.status}\n')
        elif stripped.startswith('- **Annotation history**') and args.note:
            today = datetime.now(timezone.utc).strftime('%Y-%m-%d')
            existing = stripped[4:].partition('**:')[2].strip()
            new_lines.append(f'- **Annotation history**: {existing} → {args.status} ({today}): {args.note}\n')
        else:
            new_lines.append(line)
    new_block = ''.join(new_lines)
    content = content.replace(''.join(target['raw_lines']), new_block)
    # update Last updated
    now = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')
    content = re.sub(r'> Last updated: .+', f'> Last updated: {now}', content, count=1)
    write_log(args.repo, content)
    print(f'Updated: {args.id} ({old_status} → {args.status})')
    return 0

# ---------- list-open ----------

def cmd_list_open(args) -> int:
    today = datetime.now(timezone.utc).strftime('%Y-%m-%d')
    open_count = 0
    for log_file in sorted(LOG_DIR.glob('*.md')):
        if log_file.name.endswith('.archive.md'):
            continue
        repo = log_file.stem
        for f in parse_findings(log_file.read_text()):
            status = f['fields'].get('Status', '?')
            if status in ('open', 'tracked', 'partial'):
                severity = f['fields'].get('Severity', '?')
                target = f['fields'].get('Target', '?')
                issue = f['fields'].get('Issue', '?')[:80]
                print(f'[{repo}] {f["id"]:30s} [{severity:8s}] {target:40s} {issue}')
                open_count += 1
    print(f'\n{open_count} open findings across {len(list(LOG_DIR.glob("*.md")))} repos')
    return 0

# ---------- dedupe ----------

def cmd_dedupe(args) -> int:
    """Check if a candidate finding (by file:line) is already in the log."""
    content = read_log(args.repo)
    findings = parse_findings(content)
    matches = []
    for f in findings:
        target = f['fields'].get('Target', '')
        # match by file path substring
        candidate_file = args.candidate_file.split(':')[0]
        if candidate_file in target:
            status = f['fields'].get('Status', '?')
            matches.append((f['id'], status, target))
    if matches:
        print('TRACKED — matches:')
        for fid, status, target in matches:
            print(f'  {fid} [{status}] {target}')
        return 0
    print('NEW — no matching findings in log')
    return 0

# ---------- find-stale ----------

def cmd_find_stale(args) -> int:
    cutoff = datetime.now(timezone.utc) - timedelta(days=args.days)
    cutoff_str = cutoff.strftime('%Y-%m-%d')
    stale = []
    for log_file in sorted(LOG_DIR.glob('*.md')):
        if log_file.name.endswith('.archive.md'):
            continue
        repo = log_file.stem
        for f in parse_findings(log_file.read_text()):
            status = f['fields'].get('Status', '?')
            if status not in ('open', 'tracked', 'partial'):
                continue
            first_seen = f['fields'].get('First seen', '')
            if first_seen < cutoff_str:
                stale.append((repo, f['id'], status, first_seen, f['fields'].get('Issue', '')[:60]))
    print(f'{len(stale)} findings older than {args.days} days:')
    for repo, fid, status, first, issue in stale:
        print(f'  [{repo}] {fid:30s} [{status:8s}] first_seen={first}  {issue}')
    return 0

# ---------- stale-cleanup ----------

def cmd_stale_cleanup(args) -> int:
    """Mark stale findings as wontfix (operator review recommended first)."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=args.days)
    cutoff_str = cutoff.strftime('%Y-%m-%d')
    today = datetime.now(timezone.utc).strftime('%Y-%m-%d')
    count = 0
    for log_file in sorted(LOG_DIR.glob('*.md')):
        if log_file.name.endswith('.archive.md'):
            continue
        repo = log_file.stem
        content = log_file.read_text()
        findings = parse_findings(content)
        for f in findings:
            status = f['fields'].get('Status', '?')
            if status not in ('open', 'tracked', 'partial'):
                continue
            first_seen = f['fields'].get('First seen', '')
            if first_seen < cutoff_str:
                # update
                args_dry = argparse.Namespace(repo=repo, id=f['id'], status='wontfix',
                                               note=f'auto-stale-cleanup: first_seen={first_seen}')
                cmd_update(args_dry)
                count += 1
    print(f'Marked {count} findings as wontfix (older than {args.days} days)')
    return 0

# ---------- archive-done ----------

def cmd_archive_done(args) -> int:
    """Move done findings to <repo>.archive.md."""
    content = read_log(args.repo)
    if not content:
        return 0
    findings = parse_findings(content)
    done = [f for f in findings if f['fields'].get('Status', '') == 'done']
    if not done:
        print(f'No done findings to archive in {args.repo}')
        return 0
    archive_path = LOG_DIR / f'{args.repo}.archive.md'
    archive = archive_path.read_text() if archive_path.exists() else f'# Quality Findings Archive — {args.repo}\n\n'
    archive += f'\n## Archived on {datetime.now(timezone.utc).strftime("%Y-%m-%d")}\n\n'
    for f in done:
        archive += ''.join(f['raw_lines']) + '\n'
    archive_path.write_text(archive, encoding='utf-8')
    # remove done findings from main log
    for f in done:
        content = content.replace(''.join(f['raw_lines']) + '\n', '')
    write_log(args.repo, content)
    print(f'Archived {len(done)} done findings to {archive_path}')
    return 0

# ---------- main ----------

def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest='cmd', required=True)

    p_append = sub.add_parser('append')
    p_append.add_argument('--repo', required=True)
    p_append.add_argument('--phase', required=True)
    p_append.add_argument('--severity', required=True)
    p_append.add_argument('--target', required=True)
    p_append.add_argument('--issue', required=True)
    p_append.add_argument('--fix', required=True)

    p_read = sub.add_parser('read')
    p_read.add_argument('--repo', required=True)

    p_upd = sub.add_parser('update')
    p_upd.add_argument('--repo', required=True)
    p_upd.add_argument('--id', required=True)
    p_upd.add_argument('--status', required=True)
    p_upd.add_argument('--note', default='')

    sub.add_parser('list-open')

    p_ded = sub.add_parser('dedupe')
    p_ded.add_argument('--repo', required=True)
    p_ded.add_argument('--candidate-file', required=True)

    p_stale = sub.add_parser('find-stale')
    p_stale.add_argument('--days', type=int, default=90)

    p_cleanup = sub.add_parser('stale-cleanup')
    p_cleanup.add_argument('--days', type=int, default=90)

    p_arch = sub.add_parser('archive-done')
    p_arch.add_argument('--repo', required=True)

    args = ap.parse_args()
    return {
        'append': cmd_append,
        'read': cmd_read,
        'update': cmd_update,
        'list-open': cmd_list_open,
        'dedupe': cmd_dedupe,
        'find-stale': cmd_find_stale,
        'stale-cleanup': cmd_stale_cleanup,
        'archive-done': cmd_archive_done,
    }[args.cmd](args)

if __name__ == '__main__':
    sys.exit(main())
