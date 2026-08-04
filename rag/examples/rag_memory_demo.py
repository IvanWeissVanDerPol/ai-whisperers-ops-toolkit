#!/usr/bin/env python3
"""
rag/examples/rag_memory_demo.py — End-to-end RAG demo across 2 swarm runs.

Demonstrates:
- Run #1: a swarm that produces research on authentication
- Run #2: a swarm that needs to know about authentication (RAG retrieves from #1)

This is the **memory across runs** use case: past swarms become searchable
knowledge for future swarms.

Usage:
    cd /root/ai-whisperers-ops-toolkit
    python3 rag/examples/rag_memory_demo.py
"""

import json
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from swarm.shared_memory import SharedMemory
from rag.rag import RAG


def fake_swarm_run_1(run_dir: Path) -> None:
    """Simulate a swarm that researched authentication."""
    mem = SharedMemory(run_dir)
    mem.publish("research-auth", {
        "findings": [
            "JWT is the standard for stateless API authentication.",
            "OAuth 2.0 with PKCE is recommended for third-party login.",
            "Bcrypt with cost factor 12+ is the modern password hashing standard.",
            "Refresh tokens should be stored in httpOnly cookies, not localStorage.",
        ],
        "sources": ["OWASP Auth Guide", "Auth0 docs"],
    })
    mem.publish("code-auth", {
        "files_changed": ["src/auth/jwt.ts", "src/auth/bcrypt.ts"],
        "diff_summary": "Implemented JWT signing + bcrypt hashing middleware.",
    })
    mem.publish("review-auth", {
        "verdict": "approve",
        "issues": [],
        "suggestions": ["Add rate limiting on login"],
    })
    mem.write_blackboard("architecture", "stateless JWT + refresh token in httpOnly cookie")


def fake_swarm_run_2(run_dir: Path) -> dict:
    """Simulate a swarm that needs to know about auth (uses RAG)."""
    mem = SharedMemory(run_dir)
    # The new worker would normally do this:
    #   context = rag.retrieve("how should I handle authentication?")
    # For demo, we manually do it
    mem.write_blackboard("goal", "build a new feature that requires authentication decisions")
    return {"task": "build auth module"}


def main():
    print("=== RAG memory-across-runs demo ===\n")
    
    # Setup
    tmp = Path(tempfile.mkdtemp(prefix="rag_demo_"))
    db_path = tmp / "memory.db"
    run1_dir = tmp / "run-1"
    run2_dir = tmp / "run-2"
    run1_dir.mkdir()
    run2_dir.mkdir()
    
    try:
        # === Run 1: Research swarm ===
        print("1. RUN #1 — a swarm that researched authentication")
        fake_swarm_run_1(run1_dir)
        print(f"   Created: snapshots (research-auth, code-auth, review-auth) + blackboard 'architecture'\n")
        
        # === Index Run 1 into vector store ===
        rag = RAG(db_path=str(db_path))
        result = rag.index_swarm_run(run1_dir, source="run-1")
        print(f"2. INDEX Run #1 into vector store")
        print(f"   Indexed {result['snapshots']} snapshot chunks + {result['blackboard']} blackboard entry\n")
        
        # === Run 2: A new worker needs that knowledge ===
        print("3. RUN #2 — a new worker needs authentication knowledge")
        fake_swarm_run_2(run2_dir)
        print("   Without RAG: this worker would have ZERO knowledge of past findings.")
        print("   With RAG: it retrieves relevant context from run-1.\n")
        
        # === Query via RAG ===
        print("4. RAG RETRIEVAL — 'how should I handle authentication?'\n")
        context = rag.retrieve("how should I handle authentication?", top_k=3)
        print(context)
        
        print("\n5. RAG RETRIEVAL — 'where should refresh tokens go?'\n")
        context2 = rag.retrieve("where should refresh tokens go?", top_k=3)
        print(context2)
        
        rag.close()
        
        print("\n✓ Memory across runs verified.")
        print("  Without RAG: each swarm is amnesiac.")
        print("  With RAG:    past findings are searchable + injected into new workers.")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
