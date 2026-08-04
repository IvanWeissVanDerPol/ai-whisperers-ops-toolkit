#!/usr/bin/env python3
"""
vector/searcher.py — Query a VectorStore and return ranked results.

This is the high-level interface: take a text query, find similar chunks,
optionally re-rank by source or metadata filters, return top-K.

Usage:
    from searcher import Searcher
    s = Searcher("/path/to/db.db")
    results = s.search("how does auth work", top_k=5, source="docs")
    for r in results:
        print(f"{r.score:.3f}  {r.content[:100]}")
"""

import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Union

sys.path.insert(0, str(Path(__file__).parent))
from vector_store import VectorStore, SearchResult  # noqa: E402
from embedder import Embedder  # noqa: E402


@dataclass
class ScoredResult:
    """Search result with optional metadata."""
    score: float
    content: str
    source: str
    doc_id: str
    metadata: dict = field(default_factory=dict)

    def __str__(self):
        return f"[{self.score:.3f}] {self.source}/{self.doc_id}: {self.content[:80]}"


class Searcher:
    """High-level search interface backed by VectorStore."""

    def __init__(
        self,
        db_path: Union[str, Path],
        embedder: Optional[Embedder] = None,
    ):
        self.db_path = str(db_path)
        self.store = VectorStore(db_path)
        self.embedder = embedder or Embedder()

    def close(self):
        self.store.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def search(
        self,
        query: str,
        top_k: int = 5,
        source: Optional[str] = None,
        min_score: float = 0.0,
    ) -> list[ScoredResult]:
        """Search by text query. Returns ranked results."""
        embedding = self.embedder.embed(query)
        raw_results = self.store.search(
            embedding,
            top_k=top_k,
            source=source,
            min_score=min_score,
        )
        return [
            ScoredResult(
                score=r.score,
                content=r.content,
                source=r.source,
                doc_id=r.doc_id,
                metadata=r.metadata,
            )
            for r in raw_results
        ]

    def info(self) -> dict:
        """Get searcher + store info."""
        stats = self.store.stats()
        stats["embedder_backend"] = self.embedder.backend
        stats["embedder_model"] = self.embedder.model
        return stats


def main():
    """CLI: search from the command line."""
    import argparse
    import json

    p = argparse.ArgumentParser(description="Search a vector store")
    p.add_argument("--db", required=True, help="Path to SQLite DB")
    p.add_argument("query", nargs="?", help="Query text")
    p.add_argument("--top-k", type=int, default=5)
    p.add_argument("--source", help="Restrict to a source")
    p.add_argument("--min-score", type=float, default=0.0)
    p.add_argument("--json", action="store_true")
    p.add_argument("--info", action="store_true", help="Print db + embedder info")

    args = p.parse_args()
    if args.info:
        s = Searcher(args.db)
        print(json.dumps(s.info(), indent=2))
        s.close()
        return
    if not args.query:
        print("Usage: searcher.py [--db DB] QUERY")
        sys.exit(1)
    s = Searcher(args.db)
    try:
        results = s.search(args.query, top_k=args.top_k, source=args.source, min_score=args.min_score)
        if args.json:
            print(json.dumps([
                {
                    "score": r.score,
                    "content": r.content,
                    "source": r.source,
                    "doc_id": r.doc_id,
                    "metadata": r.metadata,
                }
                for r in results
            ], indent=2, default=str))
        else:
            print(f"\nTop {len(results)} results for: {args.query!r}")
            for i, r in enumerate(results, 1):
                print(f"\n[{i}] score={r.score:.4f}  source={r.source}  doc_id={r.doc_id}")
                print(f"    {r.content[:300]}")
                if r.metadata:
                    if any(r.metadata.values()):
                        print(f"    meta: {json.dumps(r.metadata, default=str)[:200]}")
    finally:
        s.close()


if __name__ == "__main__":
    main()
