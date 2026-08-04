#!/usr/bin/env python3
"""
swarm/worker.py — A worker agent template that executes a single subtask.

A worker is spawned by the orchestrator with:
- A role (researcher, coder, reviewer, tester)
- A task description
- Optional context from shared memory

The worker:
1. Loads role-specific prompt template
2. Reads relevant context from shared memory
3. Spawns claude subprocess with task + tools
4. Captures output, publishes result
5. Logs completion to shared memory

Usage:
    python3 worker.py \\
        --role researcher \\
        --task "Find the 3 main competitors for our AI Whisperers offering" \\
        --memory-dir /tmp/swarm-state/run-123 \\
        --worker-id w1
"""

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

# Add this file's directory to path so we can import shared_memory
sys.path.insert(0, str(Path(__file__).parent))
from shared_memory import SharedMemory  # noqa: E402


# Role-specific system prompts. Customize per role.
ROLE_PROMPTS = {
    "researcher": """You are a RESEARCHER worker in an AI agent swarm.

Your job: gather information, analyze data, identify patterns, and produce findings.

Approach:
1. Start by reading any context from shared memory (snapshots + blackboard)
2. Use available tools to gather information (web_search, web_extract, file reads)
3. Synthesize findings into a clear, structured report
4. Publish your findings to shared memory under a descriptive name

Output format:
- JSON snapshot with key "findings": list of insights
- Or natural-language summary if JSON isn't appropriate
- Always log your work to shared memory

Be efficient. Don't repeat work other workers have done.""",

    "coder": """You are a CODER worker in an AI agent swarm.

Your job: write code, modify files, run commands, fix bugs.

Approach:
1. Read task + relevant context from shared memory
2. Plan the change (what files to touch, what to write)
3. Make the edits using patch/write_file tools
4. Verify (typecheck, lint, smoke test if applicable)
5. Publish the diff + verification result to shared memory

Output format:
- JSON snapshot with: "files_changed", "diff_summary", "verification"
- Log each step to shared memory

Keep changes minimal. Don't refactor unrelated code.""",

    "reviewer": """You are a REVIEWER worker in an AI agent swarm.

Your job: review code, findings, or plans from other workers.

Approach:
1. Read what other workers published to shared memory
2. Check for: bugs, missing tests, security issues, design problems
3. Verify claims (don't trust, verify)
4. Publish a structured review

Output format:
- JSON snapshot with: "verdict" (approve/changes_requested/comment), "issues" (list), "suggestions"

Be specific and constructive. Point to line numbers and concrete fixes.""",

    "tester": """You are a TESTER worker in an AI agent swarm.

Your job: verify code works as claimed.

Approach:
1. Read what was published (claim: "X works")
2. Actually run/verify it
3. Report PASS/FAIL with evidence

Output format:
- JSON snapshot with: "claim", "result", "evidence"

If something fails, do NOT silently fix it. Report it as a failure so the orchestrator can decide.""",

    "writer": """You are a WRITER worker in an AI agent swarm.

Your job: produce polished prose, documentation, content.

Approach:
1. Read research/data from shared memory
2. Draft clear, structured content
3. Use the user's preferred voice (per settings)
4. Publish to shared memory

Output format:
- Markdown text published under a descriptive name
- Log the structure (sections, word count) to shared memory""",
}


class Worker:
    """A single agent that executes one task within a swarm."""

    def __init__(
        self,
        role: str,
        task: str,
        memory_dir: str,
        worker_id: str,
        model: str = "haiku",
        timeout: int = 300,
        extra_context: Optional[str] = None,
    ):
        if role not in ROLE_PROMPTS:
            raise ValueError(f"unknown role: {role}. Choices: {list(ROLE_PROMPTS)}")
        self.role = role
        self.task = task
        self.memory = SharedMemory(memory_dir)
        self.worker_id = worker_id
        self.model = model
        self.timeout = timeout
        self.extra_context = extra_context

    def load_context(self) -> str:
        """Load relevant context from shared memory.

        Includes:
        - Recent log entries (last 20)
        - Snapshots from other workers
        - Blackboard keys
        - Optional RAG-retrieved context (if SWARM_RAG_DB env var is set)
        """
        parts = []
        # Recent log entries (last 20)
        recent = self.memory.read_log()[-20:]
        if recent:
            parts.append("## Recent activity:")
            for e in recent:
                parts.append(f"- [{e['ts']}] {e['agent_id']} ({e['role']}): {e['event']}")

        # Snapshots from other workers
        snapshots = self.memory.list_snapshots()
        if snapshots:
            parts.append("\n## Available snapshots:")
            for name in snapshots:
                data = self.memory.read(name)
                if data:
                    parts.append(f"\n### {name}:\n```json\n{json.dumps(data, indent=2, default=str)[:1000]}\n```")

        # Blackboard keys
        bb_keys = self.memory.list_blackboard_keys()
        if bb_keys:
            parts.append("\n## Blackboard keys:")
            for k in bb_keys:
                val = self.memory.read_blackboard(k)
                parts.append(f"- {k}: {str(val)[:200]}")

        # RAG context (if enabled via env var)
        rag_db = os.environ.get("SWARM_RAG_DB")
        if rag_db:
            try:
                sys.path.insert(0, str(Path(__file__).parent.parent / "rag"))
                from rag.rag import RAG  # type: ignore
                rag = RAG(db_path=rag_db)
                try:
                    # Use the task description as the query
                    rag_context = rag.retrieve(self.task, top_k=3, max_chars=2000)
                    if rag_context:
                        parts.append("\n## RAG-retrieved context from past runs:")
                        parts.append(rag_context)
                finally:
                    rag.close()
            except Exception as e:
                parts.append(f"\n## RAG (failed: {str(e)[:100]})")

        return "\n".join(parts)

    def run(self) -> dict:
        """Execute the task. Returns a result dict."""
        self.memory.log(self.worker_id, self.role, "started", {"task": self.task[:500]})

        # Build the prompt
        context = self.load_context()
        extra = f"\n\nADDITIONAL CONTEXT:\n{self.extra_context}" if self.extra_context else ""
        prompt = f"""{ROLE_PROMPTS[self.role]}

---

# YOUR TASK

{self.task}

---

# SHARED MEMORY CONTEXT

{context}
{extra}

When you're done:
1. Log your key actions to shared memory via the cli (`python3 swarm/shared_memory.py --dir {self.memory.base_dir} log --agent {self.worker_id} --role {self.role} --event "..."`)
2. Publish your result via `python3 swarm/shared_memory.py --dir {self.memory.base_dir} publish --name "your-result-name" --data '{{...}}'`
3. Reply with a short summary of what you did."""

        # Spawn claude subprocess
        cmd = [
            "claude",
            "-p", prompt,
            "--model", self.model,
            "--output-format", "json",
            "--no-input",
        ]

        self.memory.log(self.worker_id, self.role, "subprocess_started", {
            "model": self.model,
            "cmd_len": len(prompt),
        })

        start = time.time()
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self.timeout,
            )
            duration = time.time() - start
            self.memory.log(self.worker_id, self.role, "subprocess_completed", {
                "duration_sec": round(duration, 1),
                "exit_code": result.returncode,
                "stdout_len": len(result.stdout),
                "stderr_len": len(result.stderr),
            })
            if result.returncode != 0:
                self.memory.log(self.worker_id, self.role, "FAILED", {
                    "exit_code": result.returncode,
                    "stderr_tail": result.stderr[-500:],
                })
                return {
                    "ok": False,
                    "error": f"subprocess exit {result.returncode}",
                    "stderr_tail": result.stderr[-500:],
                    "duration_sec": round(duration, 1),
                }
            # Try to extract a "result" snapshot from the worker's actions
            final_snap = None
            for name in reversed(self.memory.list_snapshots()):
                snap = self.memory.read(name)
                if isinstance(snap, dict) and snap.get("worker_id") == self.worker_id:
                    final_snap = snap
                    break
            return {
                "ok": True,
                "worker_id": self.worker_id,
                "role": self.role,
                "duration_sec": round(duration, 1),
                "stdout_tail": result.stdout[-2000:],
                "result_snapshot": final_snap,
            }
        except subprocess.TimeoutExpired:
            duration = time.time() - start
            self.memory.log(self.worker_id, self.role, "TIMEOUT", {
                "timeout_sec": self.timeout,
                "duration_sec": round(duration, 1),
            })
            return {
                "ok": False,
                "error": "timeout",
                "duration_sec": round(duration, 1),
            }


def main():
    p = argparse.ArgumentParser(description="Spawn a single worker agent")
    p.add_argument("--role", required=True, choices=list(ROLE_PROMPTS))
    p.add_argument("--task", required=True)
    p.add_argument("--memory-dir", required=True)
    p.add_argument("--worker-id", required=True)
    p.add_argument("--model", default="haiku",
                   help="Model to use (default: haiku for speed)")
    p.add_argument("--timeout", type=int, default=300)
    p.add_argument("--extra-context", default=None,
                   help="Additional context for this worker")
    p.add_argument("--json", action="store_true",
                   help="Output result as JSON only")
    args = p.parse_args()

    worker = Worker(
        role=args.role,
        task=args.task,
        memory_dir=args.memory_dir,
        worker_id=args.worker_id,
        model=args.model,
        timeout=args.timeout,
        extra_context=args.extra_context,
    )
    result = worker.run()
    if args.json:
        print(json.dumps(result, indent=2, default=str))
    else:
        print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()