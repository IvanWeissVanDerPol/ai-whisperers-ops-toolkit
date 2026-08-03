#!/usr/bin/env python3
"""session-review.py — analyze recent Hermes sessions for patterns and drift.

Pattern from r/hermesagent: periodically review session archives to catch
drift, repeated errors, and improvement opportunities.
"""
import os
import sys
import json
import datetime
import sqlite3
import argparse
import re
from collections import Counter, defaultdict

HERMES_HOME = os.path.expanduser("~/.hermes")
SESSION_DB = os.path.join(HERMES_HOME, "sessions/session.db")
NOTES_DIR = os.path.join(HERMES_HOME, "notes")
LOG_DIR = os.path.join(HERMES_HOME, "logs")


def parse_period(period):
    now = datetime.datetime.now()
    if period == "today":
        return now - datetime.timedelta(days=1)
    if period == "week":
        return now - datetime.timedelta(days=7)
    if period == "month":
        return now - datetime.timedelta(days=30)
    return now - datetime.timedelta(days=7)


def query_sessions(since):
    """Read recent session JSONL files (Hermes stores sessions as .jsonl, not SQLite)."""
    sessions_dir = os.path.join(HERMES_HOME, "sessions")
    if not os.path.isdir(sessions_dir):
        return []

    messages = []
    cutoff = since

    for fname in os.listdir(sessions_dir):
        if not fname.endswith(".jsonl"):
            continue
        fpath = os.path.join(sessions_dir, fname)
        try:
            file_mtime = datetime.datetime.fromtimestamp(os.path.getmtime(fpath))
            if file_mtime < cutoff:
                continue
        except OSError:
            continue

        try:
            with open(fpath) as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        record = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    # Records are dicts with role, content, etc.
                    if "role" in record and "content" in record:
                        messages.append({
                            "session_id": fname,
                            "role": record["role"],
                            "content": record.get("content", ""),
                            "created_at": record.get("created_at", 0),
                        })
        except (OSError, IOError) as e:
            continue

    return messages


def extract_errors(messages):
    """Find error/exception patterns in assistant messages."""
    error_patterns = Counter()
    for m in messages:
        if m["role"] not in ("assistant", "tool"):
            continue
        content = m["content"] or ""
        # Common error patterns
        for pattern in [r"Error: ([^\n]{1,80})", r"Exception: ([^\n]{1,80})",
                        r"❌ ([^\n]{1,80})", r"FAILED: ([^\n]{1,80})"]:
            for match in re.finditer(pattern, content):
                error_patterns[match.group(1)[:60]] += 1
    return error_patterns


def extract_user_intents(messages):
    """Cluster user messages by first verb/topic."""
    intents = Counter()
    stop_starts = {"the", "a", "an", "is", "are", "i", "you", "we", "this", "that", "do", "does", "can", "could"}
    for m in messages:
        if m["role"] != "user":
            continue
        content = (m["content"] or "").strip().lower()
        if not content:
            continue
        first_word = content.split()[0] if content.split() else ""
        if first_word in stop_starts and len(content.split()) > 1:
            first_word = content.split()[1]
        intents[first_word[:30]] += 1
    return intents


def count_skills_used(messages):
    """Count how often each skill appears in assistant responses."""
    skills = Counter()
    for m in messages:
        if m["role"] != "assistant":
            continue
        content = m["content"] or ""
        # Look for skill invocations like "Using skill X" or "Loaded X"
        for match in re.finditer(r"skill[:\s]+([a-z0-9\-/]+)", content.lower()):
            skills[match.group(1)] += 1
    return skills


def generate_report(period, focus, max_sessions, since):
    messages = query_sessions(since)
    if not messages:
        return f"# Session Review — {datetime.date.today()}\n\nNo sessions found in DB."

    # Group by session
    sessions = defaultdict(list)
    for m in messages:
        sessions[m["session_id"]].append(dict(m))

    # Get session counts
    n_sessions = len(sessions)
    n_messages = len(messages)

    # Errors
    errors = extract_errors(messages)
    top_errors = errors.most_common(5)

    # Intents
    intents = extract_user_intents(messages)
    top_intents = intents.most_common(8)

    # Skills
    skills = count_skills_used(messages)
    top_skills = skills.most_common(5)

    # Per-session summary
    session_summaries = []
    for sid, msgs in list(sessions.items())[:max_sessions]:
        first_user = next((m["content"][:80] for m in msgs if m["role"] == "user"), "(no user msg)")
        last_assistant = next(
            (m["content"][:80] for m in reversed(msgs) if m["role"] == "assistant"),
            "(no assistant msg)"
        )
        session_summaries.append({
            "id": sid[:8],
            "messages": len(msgs),
            "first_user": first_user.replace("\n", " "),
            "last_assistant": last_assistant.replace("\n", " "),
        })

    # Build report
    lines = [
        f"# Session Review — {datetime.date.today().isoformat()}",
        f"",
        f"**Period:** last {period}",
        f"**Sessions:** {n_sessions}",
        f"**Total messages:** {n_messages}",
        f"**Focus:** {focus}",
        f"",
    ]

    if focus in ("all", "errors"):
        lines.extend([
            "## Top Error Patterns",
            "",
        ])
        if top_errors:
            for err, count in top_errors:
                lines.append(f"- **{count}x** `{err}`")
        else:
            lines.append("- (no errors detected)")
        lines.append("")

    if focus in ("all", "decisions"):
        lines.extend([
            "## Top User Intents (first word)",
            "",
        ])
        for intent, count in top_intents:
            lines.append(f"- **{count}x** `{intent}`")
        lines.append("")

    if focus in ("all", "skills"):
        lines.extend([
            "## Top Skills Used",
            "",
        ])
        if top_skills:
            for s, count in top_skills:
                lines.append(f"- **{count}x** `{s}`")
        else:
            lines.append("- (no skill invocations detected)")
        lines.append("")

    lines.extend([
        f"## Recent Sessions (max {max_sessions})",
        "",
    ])
    for s in session_summaries:
        lines.append(f"### Session `{s['id']}` ({s['messages']} msgs)")
        lines.append(f"- First: `{s['first_user']}`")
        lines.append(f"- Last:  `{s['last_assistant']}`")
        lines.append("")

    lines.extend([
        "---",
        "",
        "*Auto-generated by `~/.hermes/scripts/session-review.py`.*",
        f"*Database: `{SESSION_DB}`*",
    ])

    return "\n".join(lines)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--period", default="week", choices=["today", "week", "month"])
    p.add_argument("--focus", default="all", choices=["all", "errors", "decisions", "skills"])
    p.add_argument("--max-sessions", type=int, default=20)
    args = p.parse_args()

    since = parse_period(args.period)
    report = generate_report(args.period, args.focus, args.max_sessions, since)

    # Always print to stdout
    print(report)

    # Also write to notes/
    os.makedirs(NOTES_DIR, exist_ok=True)
    today = datetime.date.today().isoformat()
    note_path = os.path.join(NOTES_DIR, f"session-review-{today}.md")
    with open(note_path, "w") as f:
        f.write(report)

    # Also write to logs/
    os.makedirs(LOG_DIR, exist_ok=True)
    log_path = os.path.join(LOG_DIR, "session-review.log")
    with open(log_path, "a") as f:
        f.write(f"\n\n{'='*60}\n{datetime.datetime.now().isoformat()}\n{'='*60}\n{report}\n")

    return 0


if __name__ == "__main__":
    sys.exit(main())
