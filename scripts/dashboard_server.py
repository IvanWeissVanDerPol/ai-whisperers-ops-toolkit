#!/usr/bin/env python3
"""
dashboard_server.py — Serve the Hermes dashboard with operator-only auth.

Lightweight HTTP server that serves:
  - ~/.hermes/state/dashboard.html (the cross-repo health dashboard)
  - ~/.hermes/state/cron-orchestrator-digest.json
  - /api/health (returns status)

Auth: Basic auth via env vars HERMES_DASHBOARD_USER / HERMES_DASHBOARD_PASS.
Defaults to 'admin' / 'hermes' if not set (operator should rotate).

Usage:
    python3 ~/.hermes/scripts/dashboard_server.py --port 8645
    python3 ~/.hermes/scripts/dashboard_server.py --port 8645 --bind 0.0.0.0

Routes:
  /                       → dashboard.html
  /api/health             → JSON status
  /api/digest             → cron-orchestrator-digest.json
  /api/snapshots          → list of health snapshots
  /api/projects           → projects.yaml as JSON
  /api/traces             → LLM trace summary (last 7d)
  /api/cost               → cost forecast with budget alert
  /api/evals              → latest eval results
  /api/cost-budget        → current budget setting
  /api/quality            → latest delivery_prep result (psycology)
  /api/cron               → all cron jobs + cron_health summary
  /api/prompts            → list registered prompts (K-1)
  /api/prompts/<name>     → get a specific prompt (or /<name>/<version>)
  /api/usage              → usage analytics from traces (L-1)
  /api/gh-actions         → detect project type + generate CI workflow (J-1)
  /api/skills             → per-cron/skill usage breakdown (R17-9)
  /api/anomalies          → daily trace anomaly report (R18-6)
  /api/cost-router/audit  → list LLM-driven crons with model/provider (R18-4)
  /api/anomaly-pause      → auto-pause crons based on anomaly detection (R19-3)
  /api/orchestration     → last weekly orchestration digest (R19-4)
  /api/prompt-quality    → trace → prompt linkage with quality scores (R20-2)
  /api/prompt-ab         → list active A/B experiments (R21-2)
  /api/prompt-ab/compare → compare two prompt versions (R21-2)
  /api/prompt-ab/promote → auto-promote winner (R21-4)
  /api/prompt-ab/quality → per-version stats with real trace data (R22-4)
  /api/usage?days=N       → analytics for last N days (default 7)
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path


HERMES_HOME = Path.home() / ".hermes"
STATE = HERMES_HOME / "state"
SCRIPTS = HERMES_HOME / "scripts"
DASHBOARD_HTML = STATE / "dashboard.html"
DIGEST = STATE / "cron-orchestrator-digest.json"
SNAPSHOTS_DIR = STATE / "health-snapshots"
PROJECTS_YAML = STATE / "projects.yaml"
COST_BUDGET_FILE = STATE / "cost-budget.json"
EVALS_LATEST = STATE / "evals" / "latest.json"
TRACES_DIR = STATE / "traces"


def check_auth(headers) -> bool:
    """Check basic auth header."""
    expected_user = os.environ.get("HERMES_DASHBOARD_USER", "admin")
    expected_pass = os.environ.get("HERMES_DASHBOARD_PASS", "hermes")
    auth_header = headers.get("Authorization", "")
    if not auth_header.startswith("Basic "):
        return False
    try:
        decoded = base64.b64decode(auth_header[6:]).decode("utf-8")
        user, _, password = decoded.partition(":")
        return user == expected_user and password == expected_pass
    except Exception:
        return False


class DashboardHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        if not check_auth(self.headers):
            self.send_response(401)
            self.send_header("WWW-Authenticate", 'Basic realm="Hermes Dashboard"')
            self.end_headers()
            self.wfile.write(b"401 Unauthorized")
            return
        path = self.path
        # Parse query string
        from urllib.parse import urlparse, parse_qs
        parsed = urlparse(path)
        query_path = parsed.path
        query = parse_qs(parsed.query)
        # Use query_path for route matching
        path = query_path
        if path == "/" or path == "/dashboard":
            self._serve_html(DASHBOARD_HTML)
        elif path == "/api/health":
            self._serve_json({
                "status": "ok",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "uptime_since": "2026-07-29",
            })
        elif path == "/api/digest":
            self._serve_json_path(DIGEST)
        elif path == "/api/snapshots":
            self._serve_snapshots()
        elif path == "/api/projects":
            self._serve_projects()
        elif path == "/api/traces":
            self._serve_traces()
        elif path == "/api/cost":
            self._serve_cost()
        elif path == "/api/evals":
            self._serve_evals()
        elif path == "/api/cost-budget":
            if COST_BUDGET_FILE.exists():
                self._serve_json(json.loads(COST_BUDGET_FILE.read_text()))
            else:
                self._serve_json({"budget_monthly": 10})
        elif path == "/api/quality":
            self._serve_quality()
        elif path == "/api/cron":
            self._serve_cron()
        elif path == "/api/prompts":
            self._serve_prompts()
        elif path.startswith("/api/prompts/"):
            self._serve_prompt_get(path)
        elif path == "/api/usage":
            self._serve_usage(query)
        elif path == "/api/gh-actions":
            self._serve_gh_actions(query)
        elif path == "/api/skills":
            self._serve_skills(query)
        elif path == "/api/anomalies":
            self._serve_anomalies(query)
        elif path == "/api/cost-router/audit":
            self._serve_cost_router_audit()
        elif path == "/api/anomaly-pause":
            self._serve_anomaly_pause(query)
        elif path == "/api/orchestration":
            self._serve_orchestration()
        elif path == "/api/prompt-quality":
            self._serve_prompt_quality(query)
        elif path == "/api/prompt-ab":
            self._serve_prompt_ab(query)
        elif path == "/api/prompt-ab/compare":
            self._serve_prompt_ab_compare(query)
        elif path == "/api/prompt-ab/promote":
            self._serve_prompt_ab_promote(query)
        elif path == "/api/prompt-ab/quality":
            self._serve_prompt_ab_quality(query)
    def _serve_html(self, path: Path) -> None:
        if not path.exists():
            # Render a simple fallback if dashboard.html hasn't been built yet
            html = "<h1>Hermes Dashboard</h1><p>Run <code>repo_dashboard.py</code> to populate.</p>"
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(html.encode())
            return
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        self.wfile.write(path.read_bytes())

    def _serve_json(self, data) -> None:
        body = json.dumps(data).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(body)

    def _serve_json_path(self, path: Path) -> None:
        if not path.exists():
            self._serve_json({"error": "not found"})
            return
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(path.read_bytes())

    def _serve_snapshots(self) -> None:
        snapshots = []
        for p in sorted(SNAPSHOTS_DIR.glob("*.json")):
            try:
                snapshots.append(json.loads(p.read_text()))
            except Exception:
                continue
        self._serve_json({"count": len(snapshots), "snapshots": snapshots})

    def _serve_projects(self) -> None:
        if not PROJECTS_YAML.exists():
            self._serve_json({"error": "no projects.yaml"})
            return
        import yaml
        data = yaml.safe_load(PROJECTS_YAML.read_text())
        self._serve_json(data)

    def _serve_traces(self) -> None:
        """Run llm_tracer.py --summary and return JSON."""
        try:
            result = subprocess.run(
                ["python3", str(SCRIPTS / "llm_tracer.py"), "--summary", "--since", "7d", "--json"],
                capture_output=True, text=True, timeout=60,
            )
            data = json.loads(result.stdout) if result.stdout else {"error": "no output"}
            self._serve_json(data)
        except Exception as e:
            self._serve_json({"error": str(e)})

    def _serve_cost(self) -> None:
        """Run cost_forecast.py and return JSON."""
        try:
            result = subprocess.run(
                ["python3", str(SCRIPTS / "cost_forecast.py"), "--json"],
                capture_output=True, text=True, timeout=60,
            )
            data = json.loads(result.stdout) if result.stdout else {"error": "no output"}
            self._serve_json(data)
        except Exception as e:
            self._serve_json({"error": str(e)})

    def _serve_evals(self) -> None:
        """Run eval_runner.py --regress and return JSON."""
        try:
            result = subprocess.run(
                ["python3", str(SCRIPTS / "eval_runner.py"), "--regress", "--json"],
                capture_output=True, text=True, timeout=60,
            )
            data = json.loads(result.stdout) if result.stdout else {"error": "no output"}
            # Also include latest result if it exists
            if EVALS_LATEST.exists():
                latest = json.loads(EVALS_LATEST.read_text())
                data["latest"] = {
                    "name": latest.get("name"),
                    "score": latest.get("overall_score"),
                    "passed": latest.get("passed_overall"),
                    "n_cases": latest.get("n_cases"),
                    "n_passed": latest.get("n_passed"),
                    "timestamp": latest.get("timestamp"),
                }
            self._serve_json(data)
        except Exception as e:
            self._serve_json({"error": str(e)})

    def _serve_cost_budget(self) -> None:
        """Return the current budget setting."""
        if not COST_BUDGET_FILE.exists():
            self._serve_json({"monthly_usd": 5.0, "set": False, "default": True})
            return
        try:
            self._serve_json(json.loads(COST_BUDGET_FILE.read_text()))
        except Exception as e:
            self._serve_json({"error": str(e)})

    def _serve_quality(self) -> None:
        """Run quality_gate.py on /root/psycology and return JSON."""
        try:
            result = subprocess.run(
                ["python3", "/root/.REPLACE_ME.py",
                 "--path", "/root/psycology", "--no-auto-fix", "--json"],
                capture_output=True, text=True, timeout=300,
            )
            if result.stdout:
                data = json.loads(result.stdout)
            else:
                data = {"error": result.stderr[:500] or "no output"}
            self._serve_json(data)
        except subprocess.TimeoutExpired:
            self._serve_json({"error": "quality_gate timeout (>300s)"})
        except Exception as e:
            self._serve_json({"error": str(e)})

    def _serve_cron(self) -> None:
        """Return JSON with all cron jobs + cron_health summary."""
        try:
            result = subprocess.run(
                ["python3", "/root/.hermes/scripts/cron_health.py", "--json"],
                capture_output=True, text=True, timeout=30,
            )
            if result.stdout:
                self._serve_json(json.loads(result.stdout))
            else:
                self._serve_json({"error": result.stderr[:500] or "no output"})
        except Exception as e:
            self._serve_json({"error": str(e)})

    def _serve_prompts(self) -> None:
        """Return list of registered prompts."""
        try:
            result = subprocess.run(
                ["python3", "/root/.hermes/scripts/prompt_registry.py", "list", "--json"],
                capture_output=True, text=True, timeout=10,
            )
            if result.stdout:
                self._serve_json(json.loads(result.stdout))
            else:
                self._serve_json({"error": result.stderr[:500] or "no output"})
        except Exception as e:
            self._serve_json({"error": str(e)})

    def _serve_prompt_get(self, path: str) -> None:
        """GET /api/prompts/<name> or /api/prompts/<name>/<version>."""
        # Path is like "/api/prompts/<name>" or "/api/prompts/<name>/<version>"
        parts = path[len("/api/prompts/"):].split("/")
        name = parts[0]
        version = parts[1] if len(parts) > 1 else "latest"
        try:
            result = subprocess.run(
                ["python3", "/root/.hermes/scripts/prompt_registry.py", "get",
                 "--name", name, "--version", version, "--json"],
                capture_output=True, text=True, timeout=10,
            )
            if result.stdout:
                self._serve_json(json.loads(result.stdout))
            else:
                self._serve_json({"error": result.stderr[:500] or "not found"})
        except Exception as e:
            self._serve_json({"error": str(e)})

    def _serve_usage(self, query: dict) -> None:
        """GET /api/usage?days=N — analytics from traces."""
        days = query.get("days", ["7"])[0]
        try:
            days_int = int(days)
        except Exception:
            days_int = 7
        try:
            result = subprocess.run(
                ["python3", "/root/.hermes/scripts/usage_analytics.py",
                 "--days", str(days_int), "--json"],
                capture_output=True, text=True, timeout=30,
            )
            if result.stdout:
                self._serve_json(json.loads(result.stdout))
            else:
                self._serve_json({"error": result.stderr[:500] or "no data"})
        except Exception as e:
            self._serve_json({"error": str(e)})

    def _serve_gh_actions(self, query: dict) -> None:
        """GET /api/gh-actions?path=<path>&matrix=1 — detect + generate workflow."""
        path = query.get("path", ["."])[0]
        matrix = query.get("matrix", ["0"])[0] in ("1", "true", "yes")
        args = ["python3", "/root/.hermes/scripts/gh_actions_generator.py",
                "--path", path, "--detect", "--json"]
        try:
            result = subprocess.run(args, capture_output=True, text=True, timeout=10)
            info = json.loads(result.stdout) if result.stdout else {}
            # Also generate the workflow YAML
            gen_args = ["python3", "/root/.hermes/scripts/gh_actions_generator.py",
                        "--path", path]
            if matrix:
                gen_args.append("--matrix")
            gen_result = subprocess.run(gen_args, capture_output=True, text=True, timeout=10)
            self._serve_json({
                "detect": info,
                "workflow_yaml": gen_result.stdout,
                "matrix": matrix,
            })
        except Exception as e:
            self._serve_json({"error": str(e)})

    def _serve_skills(self, query: dict) -> None:
        """GET /api/skills?days=N — per-cron/skill usage breakdown."""
        days = query.get("days", ["7"])[0]
        try:
            days_int = int(days)
        except Exception:
            days_int = 7
        try:
            result = subprocess.run(
                ["python3", "/root/.hermes/scripts/trace_skill_analytics.py",
                 "--days", str(days_int), "--json"],
                capture_output=True, text=True, timeout=30,
            )
            if result.stdout:
                self._serve_json(json.loads(result.stdout))
            else:
                self._serve_json({"error": result.stderr[:500] or "no data"})
        except Exception as e:
            self._serve_json({"error": str(e)})

    def _serve_anomalies(self, query: dict) -> None:
        """GET /api/anomalies — daily anomaly report."""
        threshold = query.get("threshold", ["0.3"])[0]
        try:
            threshold = float(threshold)
        except Exception:
            threshold = 0.3
        try:
            result = subprocess.run(
                ["python3", "/root/.hermes/scripts/trace_anomaly_detector.py",
                 "--threshold", str(threshold), "--json"],
                capture_output=True, text=True, timeout=30,
            )
            if result.stdout:
                self._serve_json(json.loads(result.stdout))
            else:
                self._serve_json({"error": result.stderr[:500] or "no data"})
        except Exception as e:
            self._serve_json({"error": str(e)})

    def _serve_cost_router_audit(self) -> None:
        """GET /api/cost-router/audit — list LLM-driven crons with current model."""
        try:
            result = subprocess.run(
                ["python3", "/root/.hermes/scripts/cost_router.py", "audit"],
                capture_output=True, text=True, timeout=15,
            )
            self._serve_json({
                "output": result.stdout,
                "stderr": result.stderr[:500] if result.stderr else "",
            })
        except Exception as e:
            self._serve_json({"error": str(e)})

    def _serve_anomaly_pause(self, query: dict) -> None:
        """GET /api/anomaly-pause — auto-pause crons based on anomaly detection."""
        threshold = query.get("threshold", ["5.0"])[0]
        dry_run = query.get("dry_run", ["true"])[0].lower() != "false"
        try:
            threshold = float(threshold)
        except Exception:
            threshold = 5.0
        cmd = ["python3", "/root/.hermes/scripts/anomaly_auto_pause.py",
               "--threshold", str(threshold), "--json"]
        if dry_run:
            cmd.append("--dry-run")
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            if result.stdout:
                self._serve_json(json.loads(result.stdout))
            else:
                self._serve_json({"error": result.stderr[:500]})
        except Exception as e:
            self._serve_json({"error": str(e)})

    def _serve_orchestration(self) -> None:
        """GET /api/orchestration — last weekly orchestration run summary."""
        # Read the last cron-orchestrator-digest if it exists
        digest_path = Path("/root/.hermes/state/cron-orchestrator-digest.json")
        if digest_path.exists():
            try:
                data = json.loads(digest_path.read_text())
                self._serve_json(data)
                return
            except Exception:
                pass
        # Fall back to running the digest-only mode
        try:
            result = subprocess.run(
                ["python3", "/root/.hermes/scripts/cron_orchestrator.py",
                 "--digest-only", "--json"],
                capture_output=True, text=True, timeout=30,
            )
            if result.stdout:
                self._serve_json(json.loads(result.stdout))
            else:
                self._serve_json({"error": "no digest available", "stderr": result.stderr[:500]})
        except Exception as e:
            self._serve_json({"error": str(e)})

    def _serve_prompt_quality(self, query: dict) -> None:
        """GET /api/prompt-quality — link traces to registered prompts with quality scores."""
        days = query.get("days", ["7"])[0]
        prompt_filter = query.get("prompt", [None])[0]
        try:
            days = int(days)
        except Exception:
            days = 7
        cmd = ["python3", "/root/.hermes/scripts/trace_prompt_linker.py",
               "--days", str(days), "--json"]
        if prompt_filter:
            cmd.extend(["--prompt", prompt_filter])
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            if result.stdout:
                self._serve_json(json.loads(result.stdout))
            else:
                self._serve_json({"error": result.stderr[:500]})
        except Exception as e:
            self._serve_json({"error": str(e)})

    def _serve_prompt_ab(self, query: dict) -> None:
        """GET /api/prompt-ab — list all active A/B experiments."""
        try:
            result = subprocess.run(
                ["python3", "/root/.hermes/scripts/prompt_ab_tester.py", "status", "--json"],
                capture_output=True, text=True, timeout=15,
            )
            if result.stdout:
                self._serve_json(json.loads(result.stdout))
            else:
                self._serve_json({"error": result.stderr[:500]})
        except Exception as e:
            self._serve_json({"error": str(e)})

    def _serve_prompt_ab_compare(self, query: dict) -> None:
        """GET /api/prompt-ab/compare?name=X&v1=v1&v2=v2 — compare two versions."""
        name = query.get("name", [None])[0]
        v1 = query.get("v1", ["v1"])[0]
        v2 = query.get("v2", ["v2"])[0]
        if not name:
            self._serve_json({"error": "name required"})
            return
        try:
            result = subprocess.run(
                ["python3", "/root/.hermes/scripts/prompt_ab_tester.py", "compare",
                 "--name", name, "--v1", v1, "--v2", v2, "--json"],
                capture_output=True, text=True, timeout=15,
            )
            if result.stdout:
                self._serve_json(json.loads(result.stdout))
            else:
                self._serve_json({"error": result.stderr[:500]})
        except Exception as e:
            self._serve_json({"error": str(e)})

    def _serve_prompt_ab_promote(self, query: dict) -> None:
        """GET /api/prompt-ab/promote?name=X — auto-promote winner."""
        name = query.get("name", [None])[0]
        if not name:
            self._serve_json({"error": "name required"})
            return
        try:
            result = subprocess.run(
                ["python3", "/root/.hermes/scripts/prompt_ab_tester.py", "promote",
                 "--name", name, "--dry-run", "--json"],
                capture_output=True, text=True, timeout=15,
            )
            if result.stdout:
                self._serve_json(json.loads(result.stdout))
            else:
                self._serve_json({"error": result.stderr[:500]})
        except Exception as e:
            self._serve_json({"error": str(e)})

    def _serve_prompt_ab_quality(self, query: dict) -> None:
        """GET /api/prompt-ab/quality?name=X — per-version stats for a prompt."""
        name = query.get("name", [None])[0]
        days = query.get("days", ["7"])[0]
        try:
            days = int(days)
        except Exception:
            days = 7
        if not name:
            self._serve_json({"error": "name required"})
            return
        try:
            result = subprocess.run(
                ["python3", "/root/.hermes/scripts/prompt_version_recorder.py", "stats",
                 "--name", name, "--days", str(days), "--json"],
                capture_output=True, text=True, timeout=15,
            )
            if result.stdout:
                self._serve_json(json.loads(result.stdout))
            else:
                self._serve_json({"error": result.stderr[:500]})
        except Exception as e:
            self._serve_json({"error": str(e)})

    def log_message(self, format: str, *args) -> None:
        sys.stderr.write(f"[dashboard] {self.address_string()} - {format % args}\n")


def main() -> int:
    parser = argparse.ArgumentParser(description="Serve Hermes dashboard with auth")
    parser.add_argument("--port", type=int, default=8645, help="Port (default 8645)")
    parser.add_argument("--bind", default="127.0.0.1", help="Bind address (default 127.0.0.1)")
    args = parser.parse_args()

    server = HTTPServer((args.bind, args.port), DashboardHandler)
    print(f"\n=== Hermes Dashboard Server ===")
    print(f"  URL: http://{args.bind}:{args.port}/")
    print(f"  User: {os.environ.get('HERMES_DASHBOARD_USER', 'admin')}")
    print(f"  Password: {'*' * len(os.environ.get('HERMES_DASHBOARD_PASS', 'hermes'))}")
    print(f"  Routes: / /api/health /api/digest /api/snapshots /api/projects")
    print(f"           /api/traces /api/cost /api/evals /api/cost-budget")
    print(f"\n  Press Ctrl+C to stop.\n")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down...")
        server.shutdown()
    return 0


if __name__ == "__main__":
    sys.exit(main())