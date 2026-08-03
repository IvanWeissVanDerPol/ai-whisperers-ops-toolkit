#!/usr/bin/env python3
"""
telegram_bot.py — Interactive Telegram bot for Hermes dashboard.

Provides slash commands:
  /health         — overall health summary
  /repo <name>    — health for a specific repo
  /tick           — trigger a fresh tick for all repos
  /regressions    — show current regressions
  /help           — show commands

Implements Telegram Bot API via simple HTTP polling (no library).
Designed for the hermes-config setup where:
  - TELEGRAM_BOT_TOKEN is in ~/.hermes/.env
  - TELEGRAM_HOME_CHANNEL is configured (e.g. via `hermes config set`)

Usage:
    python3 ~/.hermes/scripts/telegram_bot.py
    python3 ~/.hermes/scripts/telegram_bot.py --poll-interval 5
    python3 ~/.hermes/scripts/telegram_bot.py --json
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

HERMES_HOME = Path.home() / ".hermes"
SCRIPTS = HERMES_HOME / "scripts"
STATE = HERMES_HOME / "state"
SNAPSHOTS_DIR = STATE / "health-snapshots"


def get_env_file() -> dict:
    """Read TELEGRAM_BOT_TOKEN from .env."""
    env_path = HERMES_HOME / ".env"
    if not env_path.exists():
        return {}
    env = {}
    for line in env_path.read_text().split("\n"):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            k, _, v = line.partition("=")
            env[k.strip()] = v.strip()
    return env


def get_home_channel() -> str | None:
    """Read TELEGRAM_HOME_CHANNEL from config.yaml."""
    cfg_path = HERMES_HOME / "config.yaml"
    if not cfg_path.exists():
        return None
    content = cfg_path.read_text()
    # Look for telegram section
    m = re.search(r"^telegram:\s*\n(?:\s+.+\n)*\s+home_channel:\s*['\"]?([^\s'\"]+)", content, re.MULTILINE)
    if m:
        return m.group(1)
    return None


def api_call(bot_token: str, method: str, params: dict | None = None) -> dict:
    """Call Telegram Bot API."""
    url = f"https://api.telegram.org/bot{bot_token}/{method}"
    if params:
        url += "?" + urllib.parse.urlencode(params)
    try:
        with urllib.request.urlopen(url, timeout=30) as resp:
            return json.loads(resp.read())
    except Exception as e:
        return {"ok": False, "error": str(e)}


def send_message(bot_token: str, chat_id: str, text: str, parse_mode: str = "Markdown") -> dict:
    """Send a message via Telegram."""
    # Telegram max message length is 4096 chars
    if len(text) > 4000:
        text = text[:3997] + "..."
    return api_call(bot_token, "sendMessage", {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": parse_mode,
        "disable_web_page_preview": "true",
    })


def cmd_health() -> str:
    """Overall health summary."""
    snapshots = list_snapshots()
    if not snapshots:
        return "No snapshots yet. Run `repo_tick.py --all` first."
    total = len(snapshots)
    avg_score = sum(s.get("health_score", 0) for s in snapshots) / total
    low = sorted(snapshots, key=lambda s: s.get("health_score", 0))[:5]
    lines = [f"🤖 *Hermes Dashboard — Overall Health*"]
    lines.append(f"")
    lines.append(f"Repos: *{total}*")
    lines.append(f"Avg score: *{avg_score:.1f}*")
    lines.append(f"")
    lines.append(f"*Bottom 5 repos:*")
    for s in low:
        score = s.get("health_score", 0)
        repo = s.get("repo", "?")
        cov = s.get("coverage", {}).get("final_coverage", 0)
        cov_str = f"{cov*100:.0f}%" if isinstance(cov, (int, float)) else "N/A"
        icon = "🟢" if score >= 70 else ("🟡" if score >= 50 else "🔴")
        lines.append(f"  {icon} `{repo}` — score {score}, coverage {cov_str}")
    return "\n".join(lines)


def cmd_repo(repo_name: str) -> str:
    """Health for a specific repo."""
    snap_path = SNAPSHOTS_DIR / f"{repo_name}.json"
    if not snap_path.exists():
        return f"❌ No snapshot for `{repo_name}`. Available: {', '.join(p.stem for p in SNAPSHOTS_DIR.glob('*.json'))}"
    s = json.loads(snap_path.read_text())
    score = s.get("health_score", 0)
    cov = s.get("coverage", {}).get("final_coverage", 0)
    cov_str = f"{cov*100:.1f}%" if isinstance(cov, (int, float)) else "N/A"
    branch = s.get("current_branch", "?")
    days = s.get("git_status", {}).get("days_since_commit", "?")
    uncommitted = s.get("git_status", {}).get("uncommitted_files", 0)
    lines = [
        f"📊 *Repo: {repo_name}*",
        f"  Score: *{score}*",
        f"  Coverage: {cov_str}",
        f"  Branch: `{branch}`",
        f"  Last commit: {days}d ago",
        f"  Uncommitted files: {uncommitted}",
    ]
    return "\n".join(lines)


def cmd_tick(parallel: int = 4) -> str:
    """Trigger a fresh tick."""
    try:
        result = subprocess.run(
            ["python3", str(SCRIPTS / "repo_tick.py"), "--all", "--quiet", "--parallel", str(parallel), "--json"],
            capture_output=True, text=True, timeout=900,
        )
        if result.returncode == 0:
            try:
                data = json.loads(result.stdout)
                n = data.get("repos_ticked", "?")
                regs = len(data.get("regressions", []))
                return f"✅ Tick complete. {n} repos ticked, {regs} regressions detected."
            except json.JSONDecodeError:
                return f"✅ Tick complete (output not JSON). Exit code: {result.returncode}"
        return f"❌ Tick failed. Exit code: {result.returncode}\n{result.stderr[-500:]}"
    except subprocess.TimeoutExpired:
        return "❌ Tick timed out (>15m)."
    except Exception as e:
        return f"❌ Tick error: {e}"


def cmd_regressions() -> str:
    """Show current regressions."""
    try:
        result = subprocess.run(
            ["python3", str(SCRIPTS / "snapshot_diff.py"), "--all", "--compare", "7d", "--json"],
            capture_output=True, text=True, timeout=60,
        )
        if result.returncode in (0, 1):
            try:
                data = json.loads(result.stdout)
                results = data.get("results", [])
                total_reg = data.get("total_regressions", 0)
                if total_reg == 0:
                    return f"✅ No regressions in {len(results)} repos."
                lines = [f"⚠️ *Regressions detected: {total_reg}*"]
                for r in results:
                    repo = r.get("repo", "?")
                    regs = r.get("diff", {}).get("regressions", [])
                    if regs:
                        lines.append(f"  `{repo}`:")
                        for reg in regs:
                            lines.append(f"    – {reg}")
                return "\n".join(lines)
            except json.JSONDecodeError:
                return "Snapshot diff produced invalid JSON."
        return f"Snapshot diff failed. Exit code: {result.returncode}"
    except Exception as e:
        return f"❌ Error: {e}"


def cmd_compare(repo_a: str, repo_b: str) -> str:
    """Compare two repos."""
    snap_a_path = SNAPSHOTS_DIR / f"{repo_a}.json"
    snap_b_path = SNAPSHOTS_DIR / f"{repo_b}.json"
    if not snap_a_path.exists():
        return f"❌ Snapshot for `{repo_a}` not found."
    if not snap_b_path.exists():
        return f"❌ Snapshot for `{repo_b}` not found."
    a = json.loads(snap_a_path.read_text())
    b = json.loads(snap_b_path.read_text())
    lines = [
        f"⚖️ *Compare: {repo_a} vs {repo_b}*",
        "",
        f"{'metric':<22} | {repo_a:<14} | {repo_b:<14} | delta",
        f"{'-'*22}-+-{'-'*14}-+-{'-'*14}-+------",
    ]
    a_score = a.get("health_score", 0)
    b_score = b.get("health_score", 0)
    a_cov = a.get("coverage", {}).get("final_coverage", 0)
    b_cov = b.get("coverage", {}).get("final_coverage", 0)
    a_days = a.get("git_status", {}).get("days_since_commit", 0)
    b_days = b.get("git_status", {}).get("days_since_commit", 0)
    lines.append(f"{'Health score':<22} | {a_score:<14} | {b_score:<14} | {b_score - a_score:+d}")
    lines.append(f"{'Coverage':<22} | {a_cov*100:<13.1f}% | {b_cov*100:<13.1f}% | {(b_cov - a_cov)*100:+.1f}%")
    a_days_disp = f"{a_days:.1f}" if isinstance(a_days, (int, float)) else str(a_days)
    b_days_disp = f"{b_days:.1f}" if isinstance(b_days, (int, float)) else str(b_days)
    delta_disp = f"{b_days - a_days:+.1f}" if isinstance(a_days, (int, float)) and isinstance(b_days, (int, float)) else "?"
    lines.append(f"{'Days since commit':<22} | {a_days_disp:<14} | {b_days_disp:<14} | {delta_disp}")
    return "\n".join(lines)


def cmd_top(n: int = 10) -> str:
    """Show top N and bottom N repos by score."""
    snapshots = list_snapshots()
    if not snapshots:
        return "No snapshots yet."
    snapshots.sort(key=lambda s: s.get("health_score", 0))
    lines = [f"🏆 *Top {n} / Bottom {n} repos by health score*", ""]
    lines.append("*Top:*")
    for s in snapshots[-n:][::-1]:
        lines.append(f"  🟢 `{s.get('repo', '?')}` — {s.get('health_score', 0)}")
    lines.append("")
    lines.append("*Bottom:*")
    for s in snapshots[:n]:
        lines.append(f"  🔴 `{s.get('repo', '?')}` — {s.get('health_score', 0)}")
    return "\n".join(lines)


def cmd_anomalies() -> str:
    """Show current anomalies."""
    anomalies_path = STATE / "anomalies.json"
    if not anomalies_path.exists():
        return "No anomalies detected yet. Run anomaly_detector.py first."
    try:
        data = json.loads(anomalies_path.read_text())
        rule = data.get("rule_anomalies", [])
        if not rule:
            return f"✅ No anomalies detected in {data.get('snapshots_analyzed', 0)} repos."
        lines = [f"⚠️ *Anomalies detected: {len(rule)}*"]
        for a in rule[:15]:
            lines.append(f"  • `[{a['kind']}]` {a['repo']}: {a['explanation'][:80]}")
        if len(rule) > 15:
            lines.append(f"  ... and {len(rule) - 15} more")
        return "\n".join(lines)
    except Exception as e:
        return f"❌ Could not read anomalies: {e}"


def cmd_help() -> str:
    return (
        "🤖 *Hermes Bot — Commands*\n\n"
        "/health — overall health summary\n"
        "/repo <name> — health for a specific repo\n"
        "/compare <a> <b> — compare two repos\n"
        "/top [N=10] — top/bottom N by score\n"
        "/tick — trigger fresh tick for all repos\n"
        "/regressions — show current regressions\n"
        "/anomalies — show current anomalies\n"
        "/help — show this help\n"
    )


def list_snapshots() -> list[dict]:
    snapshots = []
    for path in sorted(SNAPSHOTS_DIR.glob("*.json")):
        try:
            snapshots.append(json.loads(path.read_text()))
        except Exception:
            continue
    return snapshots


def dispatch_command(text: str, is_private: bool) -> str | None:
    """Dispatch a Telegram command. Return reply text or None if not a command."""
    text = text.strip()
    if not text.startswith("/"):
        return None
    parts = text.split()
    cmd = parts[0].lower().split("@")[0]  # strip @botname
    args = parts[1:]
    if cmd == "/health":
        return cmd_health()
    if cmd == "/repo":
        if not args:
            return "❓ Usage: `/repo <name>`"
        return cmd_repo(args[0])
    if cmd == "/compare":
        if len(args) < 2:
            return "❓ Usage: `/compare <repo_a> <repo_b>`"
        return cmd_compare(args[0], args[1])
    if cmd == "/top":
        try:
            n = int(args[0]) if args else 10
        except ValueError:
            n = 10
        return cmd_top(n)
    if cmd == "/tick":
        return cmd_tick()
    if cmd == "/regressions":
        return cmd_regressions()
    if cmd == "/anomalies":
        return cmd_anomalies()
    if cmd == "/help" or cmd == "/start":
        return cmd_help()
    return f"❓ Unknown command: `{cmd}`. Try /help."


def poll_updates(bot_token: str, offset: int = 0) -> tuple[list[dict], int]:
    """Poll Telegram for updates. Returns (updates, new_offset)."""
    url = f"https://api.telegram.org/bot{bot_token}/getUpdates"
    params = {"timeout": "30", "allowed_updates": '["message"]'}
    if offset:
        params["offset"] = str(offset)
    full_url = url + "?" + urllib.parse.urlencode(params)
    try:
        with urllib.request.urlopen(full_url, timeout=45) as resp:
            data = json.loads(resp.read())
        if not data.get("ok"):
            return [], offset
        updates = data.get("result", [])
        if updates:
            offset = max(u["update_id"] for u in updates) + 1
        return updates, offset
    except Exception as e:
        sys.stderr.write(f"poll error: {e}\n")
        return [], offset


def main() -> int:
    parser = argparse.ArgumentParser(description="Interactive Telegram bot for Hermes dashboard")
    parser.add_argument("--poll-interval", type=int, default=5, help="Poll interval (sec)")
    parser.add_argument("--once", action="store_true", help="Poll once then exit (for cron)")
    parser.add_argument("--json", action="store_true", help="JSON output (with --once)")
    args = parser.parse_args()

    env = get_env_file()
    bot_token = env.get("TELEGRAM_BOT_TOKEN")
    if not bot_token:
        print("error: TELEGRAM_BOT_TOKEN not found in ~/.hermes/.env", file=sys.stderr)
        return 2

    home_channel = get_home_channel()
    if not home_channel:
        print("error: TELEGRAM_HOME_CHANNEL not set in config.yaml", file=sys.stderr)
        print("hint: hermes config set TELEGRAM_HOME_CHANNEL <chat_id>", file=sys.stderr)
        return 2

    offset = 0
    if args.once:
        # Single poll, JSON output, then exit
        updates, offset = poll_updates(bot_token, offset)
        results = []
        for update in updates:
            msg = update.get("message", {})
            chat = msg.get("chat", {}).get("id", "")
            text = msg.get("text", "")
            from_user = msg.get("from", {}).get("username", "?")
            reply = dispatch_command(text, is_private=msg.get("chat", {}).get("type") == "private")
            results.append({
                "update_id": update["update_id"],
                "chat_id": chat,
                "from": from_user,
                "text": text,
                "reply": reply,
            })
            if reply:
                send_message(bot_token, str(chat), reply)
        if args.json:
            print(json.dumps({"skill": "telegram-bot", "version": "1.0.0", "results": results}, indent=2))
        return 0

    # Long-running mode
    print(f"🤖 Hermes Telegram Bot — polling every {args.poll_interval}s")
    print(f"  Home channel: {home_channel}")
    while True:
        try:
            updates, offset = poll_updates(bot_token, offset)
            for update in updates:
                msg = update.get("message", {})
                chat = msg.get("chat", {}).get("id", "")
                text = msg.get("text", "")
                from_user = msg.get("from", {}).get("username", "?")
                if not text:
                    continue
                print(f"  [{from_user}] {text}", file=sys.stderr)
                reply = dispatch_command(text, is_private=msg.get("chat", {}).get("type") == "private")
                if reply:
                    send_message(bot_token, str(chat), reply)
        except KeyboardInterrupt:
            print("\nShutting down...")
            break
        except Exception as e:
            sys.stderr.write(f"loop error: {e}\n")
            time.sleep(args.poll_interval)
    return 0


if __name__ == "__main__":
    sys.exit(main())