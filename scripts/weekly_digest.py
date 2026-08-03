#!/usr/bin/env python3
"""Weekly client meeting digest - sends to Telegram."""
import json, subprocess, sys, time
from pathlib import Path
from datetime import datetime, timedelta

AGENTS_DIR = Path("/root/ai-agents")

def get_week_meetings():
    """Get all meetings from the past 7 days across all agents."""
    week_ago = datetime.now() - timedelta(days=7)
    meetings = []
    
    for agent_dir in AGENTS_DIR.iterdir():
        profile_path = agent_dir / "profile.json"
        if not profile_path.exists():
            continue
        data = json.loads(profile_path.read_text())
        client_name = data.get("client_name", agent_dir.name)
        repo = data.get("repo", "")
        
        for m in data.get("meeting_history", []):
            try:
                m_date = datetime.fromisoformat(m["date"])
                if m_date > week_ago:
                    meetings.append({
                        "client": client_name,
                        "repo": repo,
                        "date": m_date.strftime("%b %d %I:%M%p"),
                        "summary": m["summary"][:200],
                    })
            except:
                pass
    
    return meetings

def format_digest(meetings):
    """Format as a Telegram message."""
    if not meetings:
        return "📋 *Weekly Meeting Digest*\n\nNo meetings this week."
    
    lines = ["📋 *Weekly Meeting Digest*"]
    lines.append(f"📅 {datetime.now().strftime('%b %d, %Y')}")
    lines.append(f"📊 {len(meetings)} meetings across clients\n")
    
    for m in meetings:
        lines.append(f"▸ *{m['client']}* — {m['date']}")
        lines.append(f"  {m['summary'][:100]}...")
        lines.append("")
    
    return "\n".join(lines)

if __name__ == "__main__":
    meetings = get_week_meetings()
    digest = format_digest(meetings)
    print(digest)
    
    # Send to Telegram via Hermes
    subprocess.run(["hermes", "send", digest], timeout=30, capture_output=True)
