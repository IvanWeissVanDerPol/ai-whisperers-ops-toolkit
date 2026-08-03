#!/usr/bin/env python3
"""
kanban_voice_cron — detect new WhatsApp voice note transcripts and create staging kanban tasks.

Watches ~/.hermes/desktop-attachments/ for files matching "WhatsApp Audio *.txt".
For each new transcript:
  1. Reads the file
  2. Sends to an LLM for action-item extraction (via Hermes `delegate_task` or direct LLM call)
  3. Creates kanban tasks on the "voice-inbox" board with --initial-status blocked
  4. Moves the file to ~/.hermes/inbox/processed-audio/<date>/

For now: simple parser that finds action verbs + dates. No LLM call yet
(skills/audio-transcript-to-kanban handles the rich parsing when user pastes transcript).

Usage:
  kanban_voice_cron.py                  # process new files
  kanban_voice_cron.py --dry-run        # show what would be created without doing it
  kanban_voice_cron.py --board voice-inbox
"""
import argparse
import re
import sqlite3
import subprocess
import sys
from datetime import datetime, date
from pathlib import Path

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from kanban_common import (
    KANBAN_ROOT, KANBAN_HOME, INBOX_DIR,
    board_db_path, list_boards,
    ensure_due_dates_table, ensure_task_assignees_table,
    quiet_hours, log_quiet_hours, send_to_platforms,
    PEOPLE, HUMAN_PEOPLE, AGENT_PEOPLE, DEFAULT_TENANT,
    is_human, is_known_person,
    now_ts, today_iso, eprint, exit_error,
)



ATTACHMENTS_DIR = Path.home() / ".hermes" / "desktop-attachments"
PROCESSED_DIR = Path.home() / ".hermes" / "inbox" / "processed-audio"
KANBAN_ROOT = Path.home() / ".hermes" / "kanban"
STATE_FILE = Path.home() / ".hermes" / "inbox" / ".voice-cron-state"


# board_db_path imported from kanban_common
def load_state():
    """Load last-processed timestamp."""
    if not STATE_FILE.exists():
        return 0
    try:
        return int(STATE_FILE.read_text().strip())
    except Exception:
        return 0


def save_state(ts):
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(str(ts))


def find_new_transcripts(since_ts):
    """Find WhatsApp Audio *.txt files modified after since_ts."""
    if not ATTACHMENTS_DIR.exists():
        return []
    pattern = re.compile(r"WhatsApp Audio \d{4}-\d{2}-\d{2} at \d{2}\.\d{2}\.\d{2}\.txt$")
    matches = []
    for f in ATTACHMENTS_DIR.iterdir():
        if not f.is_file():
            continue
        if not pattern.search(f.name):
            continue
        if f.stat().st_mtime <= since_ts:
            continue
        matches.append(f)
    return sorted(matches, key=lambda p: p.stat().st_mtime)


def parse_simple_actions(text):
    """
    Simple heuristic extractor. For now, splits transcript into sentences
    containing action verbs and returns them. Real LLM extraction happens
    when user pastes transcript into chat — this is the safety-net fallback.

    Returns list of (verb, sentence, confidence).
    """
    action_verbs = r"(?:you should|we need|must|have to|need to|gotta|let's|make sure to|remember to)"
    sentences = re.split(r'(?<=[.!?])\s+', text)
    found = []
    for s in sentences:
        if re.search(action_verbs, s, re.IGNORECASE):
            found.append(("imperative", s.strip(), 0.6))
    return found


def parse_llm_actions(text, board="voice-inbox"):
    """
    Extract structured actions from a transcript.

    HONEST NOTE: This function does NOT actually call an LLM yet.
    It loads the audio-transcript-to-kanban skill prompt for guidance,
    but the actual extraction uses the keyword-based heuristic
    (parse_simple_actions_to_dicts) because no LLM provider is configured.

    To wire a real LLM:
      1. Configure a provider (openrouter/anthropic/etc.) in Hermes.
      2. Replace the body of this function to:
         - Build a request: model=cheap, system_prompt=<the skill prompt>,
           user_prompt=<the transcript>
         - Call hermes-cli or delegate_task
         - Parse the JSON response into the same dict shape
      3. Keep the function signature so callers don't change.

    Returns list of dicts: {title, body, priority, owner, due_at, confidence}
    """
    # Print a warning once per run so users see the flag isn't real
    print("  [parse_llm_actions] WARNING: --llm flag set, but no LLM provider wired.")
    print("  [parse_llm_actions] Falling back to keyword heuristic.")
    print("  [parse_llm_actions] See kanban_voice_cron.py docstring to wire a real LLM.")
    try:
        # Reference the skill for documentation purposes; we don't use it yet
        skill_path = Path.home() / ".hermes" / "skills" / "audio-transcript-to-kanban" / "SKILL.md"
        if skill_path.exists():
            # Read for future use; currently just validates the file is there
            _ = skill_path.read_text()[:3000]
        return parse_simple_actions_to_dicts(text)
    except Exception as e:
        print(f"  [parse_llm_actions] error reading skill: {e}, using heuristic")
        return parse_simple_actions_to_dicts(text)


def parse_simple_actions_to_dicts(text):
    """Convert simple regex matches into dict format."""
    sentences = parse_simple_actions(text)
    return [
        {
            "title": sentence[:80],
            "body": sentence,
            "priority": 5,
            "owner": "voice",
            "due_at": None,
            "confidence": conf,
        }
        for verb, sentence, conf in sentences
    ]


def ensure_voice_inbox_board(board_name="voice-inbox"):
    """Create the voice-inbox board if it doesn't exist."""
    r = subprocess.run(
        ["hermes", "kanban", "boards", "list"],
        capture_output=True, text=True
    )
    if board_name in r.stdout:
        return
    subprocess.run([
        "hermes", "kanban", "boards", "create", board_name,
        "--name", "🎤 Voice Inbox",
        "--description", "Staging area for tasks extracted from WhatsApp voice notes. Review and move to your board.",
        "--icon", "🎤", "--color", "#a855f7"
    ], capture_output=True, text=True)


def create_task(board, title, body, source_file):
    """Create a kanban task on the staging board."""
    r = subprocess.run([
        "hermes", "kanban", "--board", board, "create", title,
        "--body", body,
        "--priority", "0",
        "--initial-status", "blocked",
        "--created-by", f"voice-cron-{date.today().isoformat()}"
    ], capture_output=True, text=True)
    if r.returncode != 0:
        print(f"  ERROR creating task: {r.stderr.strip()[:200]}", file=sys.stderr)
        return None
    # Extract task ID from output
    m = re.search(r"(t_[a-f0-9]+)", r.stdout)
    return m.group(1) if m else None


def archive_file(path):
    """Move processed file to inbox/processed-audio/<date>/."""
    target_dir = PROCESSED_DIR / date.today().isoformat()
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / path.name
    # Handle collisions
    counter = 1
    while target.exists():
        target = target_dir / f"{path.stem}.{counter}{path.suffix}"
        counter += 1
    path.rename(target)
    return target


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--board", default="voice-inbox")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--state-file", help="Override state file location")
    parser.add_argument("--llm", action="store_true",
                        help="Use LLM-based extraction. NOTE: provider not wired; falls back to keyword heuristic. See kanban_voice_cron.py docstring.")
    args = parser.parse_args()

    if args.state_file:
        global STATE_FILE
        STATE_FILE = Path(args.state_file)

    last_ts = load_state()
    new_files = find_new_transcripts(last_ts)
    if not new_files:
        print("(no new voice transcripts)")
        return 0

    print(f"Found {len(new_files)} new transcript(s)")
    if not args.dry_run:
        ensure_voice_inbox_board(args.board)

    processed_any = False
    max_ts = last_ts
    for f in new_files:
        print(f"\n--- {f.name} ---")
        # Capture mtime BEFORE we archive (the file will be moved)
        file_mtime = int(f.stat().st_mtime)
        text = f.read_text(errors="replace")
        # Strip TurboScribe watermark
        text = re.sub(r"\(Transcrito por TurboScribe\..*?\)", "", text, flags=re.DOTALL)
        text = text.strip()

        if args.llm:
            actions_dicts = parse_llm_actions(text, board=args.board)
            actions = [(d["title"], d["body"], d["confidence"]) for d in actions_dicts]
        else:
            actions = parse_simple_actions(text)
        print(f"  Found {len(actions)} candidate action(s)")

        if not args.dry_run:
            # Create summary task for the transcript itself
            summary_title = f"Voice note: {f.stem[:60]}"
            summary_body = (
                f"Source: {f.name}\n"
                f"Detected: {len(actions)} action candidate(s)\n\n"
                f"--- Transcript excerpt (first 500 chars) ---\n"
                f"{text[:500]}..."
            )
            summary_id = create_task(args.board, summary_title, summary_body, str(f))
            print(f"  Created summary task: {summary_id}")

            # Create one task per action candidate
            for i, (verb, sentence, conf) in enumerate(actions[:5]):
                task_title = sentence[:60] + ("…" if len(sentence) > 60 else "")
                task_body = (
                    f"From: {f.name}\n"
                    f"Confidence: {conf:.1f}\n"
                    f"Parent task: {summary_id}\n\n"
                    f"{sentence}"
                )
                tid = create_task(args.board, task_title, task_body, str(f))
                print(f"    Action {i+1}: {tid}")

            # Move processed file
            try:
                target = archive_file(f)
                print(f"  Archived to: {target}")
            except Exception as e:
                print(f"  ERROR archiving: {e}", file=sys.stderr)

            max_ts = max(max_ts, file_mtime)
            processed_any = True
        else:
            for verb, sentence, conf in actions[:3]:
                print(f"    [DRY] would create: {sentence[:60]}...")

    if processed_any and not args.dry_run:
        save_state(max_ts)
        print(f"\n✓ Processed {len(new_files)} transcript(s)")
    elif args.dry_run:
        print(f"\n[DRY RUN] Would process {len(new_files)} transcript(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())