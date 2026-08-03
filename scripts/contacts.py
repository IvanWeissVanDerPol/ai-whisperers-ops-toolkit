"""
contacts.py — single source of truth for client contacts and leads.

Differentiates between:
  - INTERNAL team (Ivan, Kiki, Lua, Sonia) — in HUMAN_PEOPLE inside kanban_common.py
  - CLIENTS — in this file (people we work for, e.g. Sonia for Nexa)
  - LEADS — in this file (people to reach out to, e.g. Mark, Romi)

Storage: ~/.hermes/inbox/contacts.json
Schema:
  {
    "contacts": [
      {
        "id": "<slug>",
        "name": "Mark Van der pol",
        "phone": "+31 6 47140868",
        "phone_e164": "+31647140868",
        "email": "fake@example.com",
        "city": "Heeswijk Dinther",
        "country": "NL",
        "line_of_work": "constructora",
        "stage": "lead",
        "tenant": "...",
        "notes": "...",
        "registered_at": "2026-07-29",
        "tasks": []  # task IDs referencing this contact
      }
    ]
  }

CLI:
  contacts.py list                                  # all contacts
  contacts.py list --stage lead                     # filter by stage
  contacts.py show <name-or-id>                    # detail
  contacts.py add --name X --phone X --stage lead   # add a new contact
  contacts.py update <id> --stage client            # change stage
  contacts.py find-by-phone <phone>                 # reverse lookup
  contacts.py link-task <contact_id> <task_id>      # link kanban task
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from kanban_common import INBOX_DIR, today_iso, eprint

CONTACTS_PATH = INBOX_DIR / "contacts.json"

# Helper: normalize phone to E.164
def normalize_phone(phone: str, default_country: str = "+595") -> str:
    """Strip spaces/dashes, normalize to E.164 (+595 prefix unless other country)."""
    if not phone:
        return ""
    # Already E.164
    if phone.startswith("+"):
        return "+" + re.sub(r"[^\d]", "", phone[1:])
    digits = re.sub(r"[^\d]", "", phone)
    # Country code prefix
    if digits.startswith("595"):
        return "+" + digits
    if digits.startswith("098") or digits.startswith("9"):
        # Local Paraguay number, strip leading 0 or 9
        if digits.startswith("0"):
            digits = digits[1:]
        return default_country + digits
    # Netherlands +31
    if digits.startswith("31"):
        return "+" + digits
    # Default to whatever was given
    return "+" + digits


def load() -> dict:
    if not CONTACTS_PATH.exists():
        return {"contacts": []}
    try:
        return json.loads(CONTACTS_PATH.read_text())
    except Exception:
        return {"contacts": []}


def save(data: dict) -> None:
    data["updated_at"] = today_iso()
    CONTACTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONTACTS_PATH.write_text(json.dumps(data, indent=2))


def slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def find_by_phone(data: dict, phone: str) -> list[dict]:
    """Find all contacts matching a phone (exact or last-9-digits)."""
    norm = re.sub(r"[^\d]", "", phone)
    matches = []
    for c in data.get("contacts", []):
        c_norm = re.sub(r"[^\d]", "", c.get("phone_e164", ""))
        if norm == c_norm or norm[-9:] == c_norm[-9:]:
            matches.append(c)
    return matches


def get_contact(data: dict, id_or_name: str) -> dict | None:
    """Lookup by id or fuzzy name match."""
    id_or_name = id_or_name.lower()
    for c in data.get("contacts", []):
        if c.get("id", "").lower() == id_or_name:
            return c
        if id_or_name in c.get("name", "").lower():
            return c
    return None


def cmd_list(args):
    data = load()
    contacts = data.get("contacts", [])
    if args.stage:
        contacts = [c for c in contacts if c.get("stage") == args.stage]
    if not contacts:
        print("No contacts. Start with: contacts.py add --name X --phone X --stage lead")
        return
    print(f"\n{'='*70}\nContacts ({len(contacts)}){'+' if args.stage else ''}\n{'='*70}\n")
    print(f"  {'ID':<25} {'Name':<25} {'Stage':<12} {'Line of work':<20} Phone")
    print(f"  {'-'*25} {'-'*25} {'-'*12} {'-'*20} {'-'*15}")
    for c in contacts:
        cid = c.get("id", "?")[:25]
        name = c.get("name", "?")[:25]
        stage = c.get("stage", "?")[:12]
        lck = c.get("line_of_work", "?")[:20]
        phone = c.get("phone_e164", "?")[:15]
        print(f"  {cid:<25} {name:<25} {stage:<12} {lck:<20} {phone}")


def cmd_show(args):
    data = load()
    c = get_contact(data, args.target)
    if not c:
        eprint(f"not found: {args.target}")
        sys.exit(1)
    print(json.dumps(c, indent=2))


def cmd_add(args):
    data = load()
    phone = args.phone or ""
    phone_e164 = normalize_phone(phone, args.country or "+595")
    cid = slugify(args.name)
    # Check duplicate
    if get_contact(data, cid):
        eprint(f"contact exists: {cid}")
        sys.exit(1)
    if find_by_phone(data, phone_e164):
        eprint(f"phone already registered: {phone_e164}")
        sys.exit(1)
    contact = {
        "id": cid,
        "name": args.name,
        "phone": phone,
        "phone_e164": phone_e164,
        "email": args.email or "",
        "city": args.city or "",
        "country": args.country or "",
        "line_of_work": args.line_of_work or "",
        "stage": args.stage or "lead",
        "tenant": args.tenant or "",
        "notes": args.notes or "",
        "registered_at": today_iso(),
        "tasks": [],
    }
    data["contacts"].append(contact)
    save(data)
    print(f"✓ added contact: {cid} ({contact['name']})")


def cmd_update(args):
    data = load()
    c = get_contact(data, args.target)
    if not c:
        eprint(f"not found: {args.target}")
        sys.exit(1)
    # Update fields
    for field in ["name", "stage", "tenant", "line_of_work", "city", "email", "notes"]:
        v = getattr(args, field, None)
        if v is not None:
            c[field] = v
    if args.phone:
        c["phone"] = args.phone
        c["phone_e164"] = normalize_phone(args.phone, args.country or "+595")
    save(data)
    print(f"✓ updated: {c['id']}")


def cmd_find_by_phone(args):
    data = load()
    matches = find_by_phone(data, args.phone)
    if not matches:
        print(f"no match for: {args.phone}")
        return
    for c in matches:
        print(json.dumps(c, indent=2))


def cmd_link_task(args):
    data = load()
    c = get_contact(data, args.contact)
    if not c:
        eprint(f"contact not found: {args.contact}")
        sys.exit(1)
    tasks = c.setdefault("tasks", [])
    if args.task_id not in tasks:
        tasks.append(args.task_id)
    save(data)
    print(f"✓ linked task {args.task_id} to contact {c['id']}")


def cmd_pipeline(args):
    """Show contacts by stage — closer-bot's outreach pipeline."""
    data = load()
    by_stage = {}
    for c in data.get("contacts", []):
        by_stage.setdefault(c.get("stage", "?"), []).append(c)
    print(f"\n{'='*70}\nOutreach Pipeline — {sum(len(v) for v in by_stage.values())} contacts\n{'='*70}\n")
    for stage in ["lead", "qualifying", "opportunity", "client", "main client", "cold", "lost"]:
        if stage in by_stage:
            print(f"  {stage.upper()} ({len(by_stage[stage])}):")
            for c in by_stage[stage]:
                tenant = c.get("tenant", "-") or "-"
                lc = c.get("line_of_work", "-") or "-"
                print(f"    · {c['id']:<25} {c['name']:<25} {lc:<20} tenant={tenant}")
            print()


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="command", required=True)

    p_list = sub.add_parser("list", help="list contacts")
    p_list.add_argument("--stage", help="filter by stage")
    p_list.set_defaults(func=cmd_list)

    p_show = sub.add_parser("show", help="show contact detail")
    p_show.add_argument("target")
    p_show.set_defaults(func=cmd_show)

    p_add = sub.add_parser("add", help="add a contact")
    p_add.add_argument("--name", required=True)
    p_add.add_argument("--phone", required=True)
    p_add.add_argument("--email")
    p_add.add_argument("--city")
    p_add.add_argument("--country", default="+595")
    p_add.add_argument("--line-of-work")
    p_add.add_argument("--stage", choices=["lead", "qualifying", "opportunity", "client", "main client", "cold", "lost"], default="lead")
    p_add.add_argument("--tenant")
    p_add.add_argument("--notes")
    p_add.set_defaults(func=cmd_add)

    p_upd = sub.add_parser("update", help="update a contact")
    p_upd.add_argument("target")
    p_upd.add_argument("--name")
    p_upd.add_argument("--phone")
    p_upd.add_argument("--email")
    p_upd.add_argument("--city")
    p_upd.add_argument("--country")
    p_upd.add_argument("--line-of-work")
    p_upd.add_argument("--stage")
    p_upd.add_argument("--tenant")
    p_upd.add_argument("--notes")
    p_upd.set_defaults(func=cmd_update)

    p_find = sub.add_parser("find-by-phone", help="reverse lookup")
    p_find.add_argument("phone")
    p_find.set_defaults(func=cmd_find_by_phone)

    p_link = sub.add_parser("link-task", help="link a kanban task to a contact")
    p_link.add_argument("contact")
    p_link.add_argument("task_id")
    p_link.set_defaults(func=cmd_link_task)

    p_pipe = sub.add_parser("pipeline", help="show outreach pipeline by stage")
    p_pipe.set_defaults(func=cmd_pipeline)

    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
