#!/usr/bin/env python3
"""
rag/rag.py — Retrieval-Augmented Generation glue for the swarm.

The pattern:
1. Worker has a task
2. RAG retrieves top-K relevant chunks from past swarm runs
3. Context is injected into the worker's prompt
4. Worker produces better-grounded output

This gives the swarm **memory across runs** — workers today see only
current-run context (recent log + snapshots + blackboard). RAG adds
historical context from any indexed run.

Usage:
    from rag import RAG
    rag = RAG("/path/to/vector.db")
    context = rag.retrieve("how do I handle auth?", top_k=3)
    # Returns formatted markdown with sources

    rag.index_snapshot("swarm-state/run-123", "research-1",
                       {"findings": ["..."]}, source="swarm-runs")
"""

import json
import os
import re
import sys
from pathlib import Path
from typing import Optional, Union

sys.path.insert(0, str(Path(__file__).parent.parent))
from vector.vector_store import VectorStore  # noqa: E402
from vector.embedder import Embedder  # noqa: E402
from vector.indexer import chunk_paragraphs  # noqa: E402
from vector.searcher import Searcher, ScoredResult  # noqa: E402


DEFAULT_DB = os.path.expanduser("~/.hermes/state/vector/swarm-memory.db")


class RAG:
    """High-level retrieval-augmented generation interface."""

    def __init__(
        self,
        db_path: Union[str, Path] = DEFAULT_DB,
        embedder: Optional[Embedder] = None,
        searcher: Optional[Searcher] = None,
    ):
        self.db_path = str(db_path)
        # Make sure parent dir exists
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self.embedder = embedder or Embedder()
        self.searcher = searcher or Searcher(self.db_path, embedder=self.embedder)

    def close(self):
        self.searcher.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def retrieve(
        self,
        query: str,
        top_k: int = 5,
        source: Optional[str] = None,
        min_score: float = 0.0,
        max_chars: int = 4000,
    ) -> str:
        """Retrieve relevant context, formatted as markdown for LLM prompts."""
        results = self.searcher.search(
            query, top_k=top_k, source=source, min_score=min_score,
        )
        if not results:
            return ""
        parts = [f"## Retrieved context ({len(results)} relevant chunks)\n"]
        for i, r in enumerate(results, 1):
            content = r.content[:max_chars]
            if len(r.content) > max_chars:
                content += "..."
            parts.append(
                f"### [{i}] {r.source}/{r.doc_id} (score={r.score:.3f})\n"
                f"{content}\n"
            )
        return "\n".join(parts)

    def retrieve_raw(
        self,
        query: str,
        top_k: int = 5,
        source: Optional[str] = None,
        min_score: float = 0.0,
    ) -> list[ScoredResult]:
        """Retrieve results as ScoredResult objects (for programmatic use)."""
        return self.searcher.search(
            query, top_k=top_k, source=source, min_score=min_score,
        )

    def index_snapshot(
        self,
        source: str,
        doc_id: str,
        data,
        metadata: Optional[dict] = None,
    ) -> int:
        """Index a swarm snapshot (typically JSON/dict).

        Recursively flattens the structure into text chunks by serializing
        each leaf value with its key.
        """
        metadata = metadata or {}
        if isinstance(data, (dict, list)):
            text = _flatten_to_text(data, prefix=doc_id)
        else:
            text = str(data)
        chunks = chunk_paragraphs(text)
        if not chunks:
            chunks = [text]
        items = []
        for i, chunk in enumerate(chunks):
            emb = self.embedder.embed(chunk)
            items.append({
                "source": source,
                "doc_id": f"{doc_id}_{i:03d}",
                "content": chunk,
                "embedding": emb,
                "metadata": {**metadata, "doc_id": doc_id, "chunk_index": i},
            })
        return len(self.searcher.store.add_many(items))

    def index_blackboard(
        self,
        source: str,
        key: str,
        value,
        metadata: Optional[dict] = None,
    ) -> int:
        """Index a blackboard key (any JSON-serializable value)."""
        metadata = metadata or {}
        text = f"{key}: {json.dumps(value, default=str, indent=2)}"
        emb = self.embedder.embed(text)
        self.searcher.store.add(
            source=source,
            doc_id=key,
            content=text,
            embedding=emb,
            metadata=metadata,
        )
        return 1

    def index_swarm_run(
        self,
        memory_dir: Union[str, Path],
        source: Optional[str] = None,
    ) -> dict:
        """Index ALL of a swarm run's snapshots + blackboard into the vector store.

        Args:
            memory_dir: path to a swarm run directory (e.g. /tmp/swarm-state/run-123/)
            source: name to use in the vector store (default: memory_dir basename)
        """
        import sys
        sys.path.insert(0, str(Path(__file__).parent.parent / 'swarm'))
        from shared_memory import SharedMemory
        memory_dir = Path(memory_dir)
        if source is None:
            source = f"swarm-run-{memory_dir.name}"
        memory = SharedMemory(memory_dir)
        indexed = {"snapshots": 0, "blackboard": 0}

        # Index snapshots
        for name in memory.list_snapshots():
            data = memory.read(name)
            if data is None:
                continue
            n = self.index_snapshot(
                source=source,
                doc_id=name,
                data=data,
                metadata={"snapshot_name": name, "memory_dir": str(memory_dir)},
            )
            indexed["snapshots"] += n

        # Index blackboard
        for key in memory.list_blackboard_keys():
            value = memory.read_blackboard(key)
            if value is None:
                continue
            n = self.index_blackboard(
                source=source,
                key=key,
                value=value,
                metadata={"memory_dir": str(memory_dir)},
            )
            indexed["blackboard"] += n

        return {"source": source, **indexed}


def _flatten_to_text(data, prefix="", separator="\n\n") -> str:
    """Recursively flatten a dict/list into text chunks.

    Each leaf becomes a separate paragraph for embedding.
    """
    parts = []
    if isinstance(data, dict):
        for k, v in data.items():
            new_prefix = f"{prefix}.{k}" if prefix else k
            parts.append(_flatten_to_text(v, new_prefix))
    elif isinstance(data, list):
        for i, v in enumerate(data):
            new_prefix = f"{prefix}[{i}]"
            parts.append(_flatten_to_text(v, new_prefix))
    else:
        leaf = f"{prefix}: {data}"
        parts.append(leaf)
    return separator.join(parts)


def main():
    """CLI: index a swarm run or query the RAG store."""
    import argparse

    p = argparse.ArgumentParser(description="RAG for swarm memory")
    p.add_argument("--db", default=DEFAULT_DB)
    sub = p.add_subparsers(dest="cmd", required=True)

    p_index = sub.add_parser("index-run", help="Index a swarm run directory")
    p_index.add_argument("--memory-dir", required=True)
    p_index.add_argument("--source", help="Override source name")

    p_query = sub.add_parser("query", help="Semantic search across indexed runs")
    p_query.add_argument("query")
    p_query.add_argument("--top-k", type=int, default=5)
    p_query.add_argument("--source", help="Restrict to a source")
    p_query.add_argument("--min-score", type=float, default=0.0)

    p_stats = sub.add_parser("stats", help="Print DB stats")

    args = p.parse_args()
    rag = RAG(db_path=args.db)
    try:
        if args.cmd == "index-run":
            result = rag.index_swarm_run(args.memory_dir, source=args.source)
            print(json.dumps(result, indent=2))
        elif args.cmd == "query":
            ctx = rag.retrieve(args.query, top_k=args.top_k,
                              source=args.source, min_score=args.min_score)
            print(ctx)
        elif args.cmd == "stats":
            print(json.dumps(rag.searcher.info(), indent=2))
    finally:
        rag.close()


if __name__ == "__main__":
    main()
