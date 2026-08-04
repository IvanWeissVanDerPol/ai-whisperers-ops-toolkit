#!/usr/bin/env python3
"""
swarm/worker_registry.py — Multi-host worker registry for the swarm.

A central registry tracks worker hosts and their capabilities, allowing the
orchestrator to dispatch subtasks to the right host based on:
- Capability match (which roles can this host run?)
- Current load (how many subtasks is it processing?)
- Health (is the heartbeat fresh?)

Architecture:
- Registry = small HTTP server backed by a JSON file (atomic writes)
- Workers POST heartbeats every 10s with: host, capabilities, current_load
- Orchestrator GETs registry to find the best worker for a subtask
- File-based persistence means no DB needed; survives restarts

Wire protocol (plain HTTP, no auth — assume trusted network):
- POST /register       body: {host, capabilities: [...], metadata: {...}}
- POST /heartbeat      body: {host, load: int, status: "alive"|"busy"|"dead"}
- GET  /workers        returns: [{host, capabilities, load, last_seen, ...}, ...]
- GET  /pick?role=X    returns: best worker for role X
- DELETE /workers/:host unregister a worker

CLI:
    # Start registry server
    python3 worker_registry.py --port 8766 --db /tmp/registry.json

    # Register a worker
    python3 worker_registry.py --host localhost:8766 register \
        --host-id gpu-box-1 --capabilities coder,gpu-heavy

    # List workers
    python3 worker_registry.py --host localhost:8766 list
"""

import argparse
import json
import sys
import time
import threading
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse, parse_qs


WORKER_TIMEOUT = 30  # seconds — workers are considered dead after this


class WorkerRegistry:
    """File-backed registry of workers."""

    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        self.lock = threading.Lock()
        if not self.db_path.exists():
            self._save({})

    def _save(self, data: dict):
        # Atomic write: tmp file + rename
        tmp = self.db_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=2))
        tmp.replace(self.db_path)

    def _load(self) -> dict:
        if not self.db_path.exists():
            return {}
        return json.loads(self.db_path.read_text())

    def register(self, host_id: str, capabilities: list[str], metadata: Optional[dict] = None):
        with self.lock:
            data = self._load()
            data[host_id] = {
                "host_id": host_id,
                "capabilities": capabilities,
                "metadata": metadata or {},
                "load": 0,
                "status": "alive",
                "first_seen": data.get(host_id, {}).get("first_seen", datetime.now(timezone.utc).isoformat()),
                "last_seen": datetime.now(timezone.utc).isoformat(),
            }
            self._save(data)
            return data[host_id]

    def heartbeat(self, host_id: str, load: int = 0, status: str = "alive"):
        with self.lock:
            data = self._load()
            if host_id not in data:
                return None  # not registered
            data[host_id]["load"] = load
            data[host_id]["status"] = status
            data[host_id]["last_seen"] = datetime.now(timezone.utc).isoformat()
            self._save(data)
            return data[host_id]

    def unregister(self, host_id: str):
        with self.lock:
            data = self._load()
            data.pop(host_id, None)
            self._save(data)

    def list_workers(self, role: Optional[str] = None, alive_only: bool = True) -> list[dict]:
        with self.lock:
            data = self._load()
        now = time.time()
        workers = []
        for host_id, info in data.items():
            if alive_only:
                last_seen = datetime.fromisoformat(info["last_seen"]).timestamp()
                if now - last_seen > WORKER_TIMEOUT:
                    continue  # worker is dead
            if role and role not in info.get("capabilities", []):
                continue  # doesn't have the right capability
            workers.append(info)
        # Sort by load (asc) — least busy first
        workers.sort(key=lambda w: w.get("load", 0))
        return workers

    def pick_worker(self, role: str) -> Optional[dict]:
        """Pick the best worker for a given role."""
        candidates = self.list_workers(role=role, alive_only=True)
        return candidates[0] if candidates else None

    def stats(self) -> dict:
        with self.lock:
            data = self._load()
        now = time.time()
        total = len(data)
        alive = 0
        for info in data.values():
            last_seen = datetime.fromisoformat(info["last_seen"]).timestamp()
            if now - last_seen <= WORKER_TIMEOUT:
                alive += 1
        return {
            "total_workers": total,
            "alive_workers": alive,
            "dead_workers": total - alive,
            "db_path": str(self.db_path),
        }


# ============================================================================
# HTTP server
# ============================================================================

def make_server(registry: WorkerRegistry, host: str, port: int):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format, *args):
            pass  # quiet

        def _send_json(self, status: int, payload):
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps(payload).encode())

        def _read_body(self) -> dict:
            length = int(self.headers.get("Content-Length", 0))
            if length == 0:
                return {}
            body = self.rfile.read(length).decode()
            try:
                return json.loads(body)
            except json.JSONDecodeError:
                return {}

        def do_POST(self):
            parsed = urlparse(self.path)
            if parsed.path == "/register":
                body = self._read_body()
                result = registry.register(
                    host_id=body["host_id"],
                    capabilities=body.get("capabilities", []),
                    metadata=body.get("metadata", {}),
                )
                self._send_json(200, {"ok": True, "worker": result})
                return
            if parsed.path == "/heartbeat":
                body = self._read_body()
                result = registry.heartbeat(
                    host_id=body["host_id"],
                    load=body.get("load", 0),
                    status=body.get("status", "alive"),
                )
                if result is None:
                    self._send_json(404, {"ok": False, "error": "not_registered"})
                else:
                    self._send_json(200, {"ok": True, "worker": result})
                return
            self._send_json(404, {"error": "not_found"})

        def do_GET(self):
            parsed = urlparse(self.path)
            qs = parse_qs(parsed.query)
            if parsed.path in ("/", "/health"):
                self._send_json(200, registry.stats())
                return
            if parsed.path == "/workers":
                role = qs.get("role", [None])[0]
                workers = registry.list_workers(role=role)
                self._send_json(200, {"workers": workers, "count": len(workers)})
                return
            if parsed.path == "/pick":
                role = qs.get("role", [None])[0]
                if not role:
                    self._send_json(400, {"error": "missing role param"})
                    return
                worker = registry.pick_worker(role)
                self._send_json(200, {"worker": worker})
                return
            self._send_json(404, {"error": "not_found"})

        def do_DELETE(self):
            parsed = urlparse(self.path)
            if parsed.path.startswith("/workers/"):
                host_id = parsed.path[len("/workers/"):]
                registry.unregister(host_id)
                self._send_json(200, {"ok": True})
                return
            self._send_json(404, {"error": "not_found"})

    return ThreadingHTTPServer((host, port), Handler)


# ============================================================================
# CLI
# ============================================================================

def main():
    p = argparse.ArgumentParser(description="Multi-host worker registry")
    sub = p.add_subparsers(dest="cmd", required=False)

    # Server mode (default if no subcommand)
    p.add_argument("--port", type=int, default=8766)
    p.add_argument("--host", default="0.0.0.0")
    p.add_argument("--db", default="/tmp/worker_registry.json")

    # Client mode flags (use --host to point at registry)
    p.add_argument("--registry", default="http://localhost:8766",
                   help="Registry URL for client commands")

    # register
    p_reg = sub.add_parser("register", help="Register a worker")
    p_reg.add_argument("--host-id", required=True)
    p_reg.add_argument("--capabilities", default="", help="Comma-separated roles")
    p_reg.add_argument("--metadata", default="{}")

    # heartbeat
    p_hb = sub.add_parser("heartbeat", help="Send heartbeat")
    p_hb.add_argument("--host-id", required=True)
    p_hb.add_argument("--load", type=int, default=0)
    p_hb.add_argument("--status", default="alive")

    # list
    sub.add_parser("list", help="List workers")

    # pick
    p_pick = sub.add_parser("pick", help="Pick best worker for role")
    p_pick.add_argument("--role", required=True)

    # unregister
    p_un = sub.add_parser("unregister", help="Unregister a worker")
    p_un.add_argument("--host-id", required=True)

    args = p.parse_args()

    if args.cmd is None:
        # Server mode
        db_path = Path(args.db)
        registry = WorkerRegistry(db_path)
        server = make_server(registry, args.host, args.port)
        print(f"✓ Worker registry: http://{args.host}:{args.port}/")
        print(f"  DB: {db_path}")
        print(f"  Worker timeout: {WORKER_TIMEOUT}s")
        print()
        print("Endpoints:")
        print("  POST /register     {host_id, capabilities, metadata}")
        print("  POST /heartbeat    {host_id, load, status}")
        print("  GET  /workers?role=X")
        print("  GET  /pick?role=X")
        print("  GET  /health       → stats")
        print()
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            print("\nShutting down...")
            server.shutdown()
        return

    # Client mode
    import urllib.request
    base = args.registry.rstrip("/")

    if args.cmd == "register":
        body = json.dumps({
            "host_id": args.host_id,
            "capabilities": [c.strip() for c in args.capabilities.split(",") if c.strip()],
            "metadata": json.loads(args.metadata),
        }).encode()
        req = urllib.request.Request(f"{base}/register", data=body,
                                     headers={"Content-Type": "application/json"})
        resp = urllib.request.urlopen(req)
        print(json.loads(resp.read()))

    elif args.cmd == "heartbeat":
        body = json.dumps({"host_id": args.host_id, "load": args.load, "status": args.status}).encode()
        req = urllib.request.Request(f"{base}/heartbeat", data=body,
                                     headers={"Content-Type": "application/json"})
        resp = urllib.request.urlopen(req)
        print(json.loads(resp.read()))

    elif args.cmd == "list":
        resp = urllib.request.urlopen(f"{base}/workers")
        data = json.loads(resp.read())
        print(f"Workers ({data['count']} alive):")
        for w in data["workers"]:
            caps = ",".join(w.get("capabilities", []))
            print(f"  • {w['host_id']:30} load={w.get('load', 0):3}  caps={caps}")
            print(f"    last_seen: {w['last_seen']}")

    elif args.cmd == "pick":
        resp = urllib.request.urlopen(f"{base}/pick?role={args.role}")
        data = json.loads(resp.read())
        if data["worker"]:
            print(f"Best worker for '{args.role}': {data['worker']['host_id']}")
        else:
            print(f"No alive worker with capability '{args.role}'")

    elif args.cmd == "unregister":
        req = urllib.request.Request(f"{base}/workers/{args.host_id}", method="DELETE")
        resp = urllib.request.urlopen(req)
        print(json.loads(resp.read()))


if __name__ == "__main__":
    main()