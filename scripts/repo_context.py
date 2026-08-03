"""
repo_context — single source of truth: clients, repos, and how they connect.

Replaces ad-hoc "remember the dentist repo is at /root/dentist" knowledge.

Storage: ~/.hermes/inbox/repo_context.json
Schema:
  {
    "tenants": {
      "Ai-Whisperers": {"description": "...", "contact": "Ivan"},
      "mark-nl":       {"description": "...", "contact": "Mark"},
      ...
    },
    "repos": {
      "/root/dentist-template-scan": {
        "tenant": "Ai-Whisperers",
        "git_repo": "github.com/.../dentist-template",
        "live_url": "https://...",
        "deploy_status": "live|staging|broken|draft",
        "agent_owner": "design-bot",
        "human_owner": "Ivan",
        "brand_file": "designer-handoff.json",
        "kanban_board": "client-deploy",
        "tags": ["nextjs", "tailwind-v4"]
      }
    },
    "client_name_to_repo": {
      "dentist": "/root/dentist-template-scan",
      ...
    }
  }

CLI:
  repo_context.py list                              # show all
  repo_context.py show <tenant>                     # tenant detail
  repo_context.py show <repo_path>                  # repo detail
  repo_context.py register-tenant <name>            # add tenant
  repo_context.py register-repo <path> <tenant> ... # add repo
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from kanban_common import INBOX_DIR, today_iso, eprint

CONTEXT_PATH = INBOX_DIR / "repo_context.json"

EMPTY = {"tenants": {}, "repos": {}, "client_name_to_repo": {}}


def load() -> dict:
    if not CONTEXT_PATH.exists():
        return json.loads(json.dumps(EMPTY))  # deep copy
    try:
        return json.loads(CONTEXT_PATH.read_text())
    except Exception:
        return json.loads(json.dumps(EMPTY))


def save(data: dict) -> None:
    data["updated_at"] = today_iso()
    CONTEXT_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONTEXT_PATH.write_text(json.dumps(data, indent=2))


def cmd_list(args):
    data = load()
    if not data.get("tenants") and not data.get("repos"):
        print("repo_context is empty. Start with: repo_context.py register-tenant <name>")
        return
    print(f"\n{'='*70}\nrepo_context — {len(data['tenants'])} tenants, {len(data['repos'])} repos\n{'='*70}")
    for tenant, info in data["tenants"].items():
        repos = [p for p, r in data["repos"].items() if r["tenant"] == tenant]
        print(f"\n {tenant} — {info.get('description', '')}")
        for r in repos:
            r_info = data["repos"][r]
            print(f"   • {r}")
            print(f"     owner: {r_info.get('agent_owner')}, human: {r_info.get('human_owner')}, status: {r_info.get('deploy_status')}")


def cmd_show(args):
    data = load()
    target = args.target
    # Try tenant first
    if target in data["tenants"]:
        info = data["tenants"][target]
        repos = [p for p, r in data["repos"].items() if r["tenant"] == target]
        print(f"\n=== Tenant: {target} ===")
        print(json.dumps(info, indent=2))
        print(f"\nRepos ({len(repos)}):")
        for r in repos:
            print(f"  {r}")
            print(f"    {json.dumps(data['repos'][r], indent=4)}")
        return
    # Try repo path
    for path, info in data["repos"].items():
        if path == target or path.endswith(f"/{target}"):
            print(f"\n=== Repo: {path} ===")
            print(json.dumps(info, indent=2))
            return
    eprint(f"not found: {target}")
    sys.exit(1)


def cmd_register_tenant(args):
    data = load()
    name = args.name
    if name in data["tenants"]:
        eprint(f"tenant already exists: {name}")
        return
    data["tenants"][name] = {
        "description": args.description or "",
        "contact": args.contact or "",
        "registered_at": today_iso(),
    }
    save(data)
    print(f"✓ registered tenant: {name}")


def cmd_register_repo(args):
    data = load()
    path = str(Path(args.path).resolve())
    if not Path(path).exists():
        eprint(f"path does not exist: {path}")
        sys.exit(1)
    tenant = args.tenant
    if tenant not in data["tenants"]:
        eprint(f"tenant not registered: {tenant}. Run register-tenant first.")
        sys.exit(1)
    info = {
        "tenant": tenant,
        "agent_owner": args.agent_owner or "delivery-bot",
        "human_owner": args.human_owner or "Ivan",
        "deploy_status": args.deploy_status or "draft",
        "live_url": args.live_url or "",
        "brand_file": args.brand_file or "designer-handoff.json",
        "kanban_board": args.kanban_board or "client-deploy",
        "git_repo": args.git_repo or "",
        "tags": args.tags or [],
    }
    data["repos"][path] = info
    data["client_name_to_repo"][Path(path).name] = path
    save(data)
    print(f"✓ registered repo: {path} (tenant={tenant})")


def cmd_lookup(args):
    """Find which repo a tenant or client name maps to."""
    data = load()
    name = args.name
    if name in data["client_name_to_repo"]:
        path = data["client_name_to_repo"][name]
        print(path)
        return
    if name in data["repos"]:
        print(name)
        return
    if name in data["tenants"]:
        repos = [p for p, r in data["repos"].items() if r["tenant"] == name]
        for r in repos:
            print(r)
        return
    eprint(f"no match for: {name}")
    sys.exit(1)


def cmd_priority(args):
    """Show the priority of all clients (which is the only external one)."""
    data = load()
    priority = data.get("client_priority", {})
    if not priority:
        print("No client_priority set. Default: dentist-template-scan")
        return

    print("\n" + "="*70)
    print(f"Client Priority — {today_iso()}")
    print("="*70 + "\n")
    print(f"  External client active: {priority.get('is_external_client')}")
    print(f"  Primary tenant:         {priority.get('tenant')}")
    print(f"  Primary repo:           {priority.get('primary_repo')}")
    print(f"  Primary label:          {priority.get('primary_tenant_label', '(unset)')}")
    print(f"\n  Note: {priority.get('note', '(no note)')}")

    paused = priority.get("paused_clients", [])
    if paused:
        print(f"\n  Paused clients ({len(paused)}):")
        for p in paused:
            print(f"    - {p.get('repo')}: {p.get('reason', '')}")

    primary_tenant = priority.get("tenant", "")
    if primary_tenant:
        print(f"\n  Active repos in '{primary_tenant}':")
        for path, info in data.get("repos", {}).items():
            if info.get("tenant") == primary_tenant:
                marker = "*" if path == priority.get("primary_repo") else "."
                status = info.get("deploy_status", "?")
                print(f"    {marker} {path} [{status}]")
    print()


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="command", required=True)

    p_list = sub.add_parser("list", help="show all tenants + repos")
    p_list.set_defaults(func=cmd_list)

    p_show = sub.add_parser("show", help="show detail for tenant or repo")
    p_show.add_argument("target")
    p_show.set_defaults(func=cmd_show)

    p_rt = sub.add_parser("register-tenant", help="register a new tenant")
    p_rt.add_argument("name")
    p_rt.add_argument("--description", help="human-readable description")
    p_rt.add_argument("--contact", help="primary contact")
    p_rt.set_defaults(func=cmd_register_tenant)

    p_rr = sub.add_parser("register-repo", help="register a repo")
    p_rr.add_argument("path", help="absolute path to repo")
    p_rr.add_argument("tenant", help="tenant name (must be registered)")
    p_rr.add_argument("--agent-owner", default="delivery-bot", help="which bot owns this repo")
    p_rr.add_argument("--human-owner", default="Ivan", help="which human owns this repo")
    p_rr.add_argument("--deploy-status", choices=["draft", "staging", "live", "broken", "paused"], default="draft")
    p_rr.add_argument("--live-url", help="live URL")
    p_rr.add_argument("--brand-file", default="designer-handoff.json", help="brand handoff file name")
    p_rr.add_argument("--kanban-board", default="client-deploy", help="kanban board for tasks")
    p_rr.add_argument("--git-repo", help="github URL")
    p_rr.add_argument("--tags", nargs="*", default=[], help="tags (nextjs, tailwind-v4, etc.)")
    p_rr.set_defaults(func=cmd_register_repo)

    p_lk = sub.add_parser("lookup", help="find repo path for a tenant or client name")
    p_lk.add_argument("name")
    p_lk.set_defaults(func=cmd_lookup)

    p_pr = sub.add_parser("priority", help="show client priority (which is the ONLY external client)")
    p_pr.set_defaults(func=cmd_priority)

    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
