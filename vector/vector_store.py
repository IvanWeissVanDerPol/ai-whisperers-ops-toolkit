#!/usr/bin/env python3
"""
vector/vector_store.py — SQLite-backed vector store with cosine similarity.

Pure-Python implementation using only the standard library (sqlite3 + struct).
Designed for the no-deps runtime environment where numpy/transformers aren't available.

Storage:
- Each document is one row with: source, doc_id, content, embedding (BLOB), metadata
- Embeddings are stored as packed float32 bytes (8x smaller than JSON)
- Cosine similarity computed in pure Python (O(N*D), fine for <10k chunks)

When numpy IS available later, swap in `numpy.dot` for 100x speedup.

Usage:
    store = VectorStore(":memory:")
    store.add(source="docs", doc_id="r1", content="...", embedding=[0.1, 0.2, ...])
    results = store.search(embedding=[0.1, 0.2, ...], top_k=5)
"""

import json
import math
import sqlite3
import struct
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Union


SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL,
    doc_id TEXT NOT NULL,
    content TEXT NOT NULL,
    embedding BLOB,
    metadata TEXT DEFAULT '{}',
    created_at TEXT NOT NULL,
    UNIQUE(source, doc_id)
);
CREATE INDEX IF NOT EXISTS idx_source ON documents(source);
CREATE INDEX IF NOT EXISTS idx_doc_id ON documents(doc_id);
CREATE INDEX IF NOT EXISTS idx_created ON documents(created_at);
"""


@dataclass
class SearchResult:
    """One result from a similarity search."""
    id: int
    source: str
    doc_id: str
    content: str
    score: float
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "source": self.source,
            "doc_id": self.doc_id,
            "content": self.content,
            "score": round(self.score, 4),
            "metadata": self.metadata,
        }


def encode_vector(vec: list[float]) -> bytes:
    """Pack a list of floats into bytes (float32 LE)."""
    return struct.pack(f"<{len(vec)}f", *vec)


def decode_vector(blob: bytes) -> list[float]:
    """Unpack bytes back into a list of floats."""
    n = len(blob) // 4
    return list(struct.unpack(f"<{n}f", blob))


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """Cosine similarity between two equal-length vectors. Pure Python."""
    if len(a) != len(b):
        # Different dimensions — pad/truncate (shouldn't happen in practice)
        m = min(len(a), len(b))
        a, b = a[:m], b[:m]
    dot = 0.0
    mag_a = 0.0
    mag_b = 0.0
    for ai, bi in zip(a, b):
        dot += ai * bi
        mag_a += ai * ai
        mag_b += bi * bi
    if mag_a == 0 or mag_b == 0:
        return 0.0
    return dot / (math.sqrt(mag_a) * math.sqrt(mag_b))


class VectorStore:
    """SQLite-backed vector store with pure-Python cosine similarity."""

    def __init__(self, db_path: Union[str, Path] = ":memory:"):
        self.db_path = str(db_path)
        self.conn = sqlite3.connect(self.db_path)
        self.conn.execute("PRAGMA journal_mode=WAL")  # concurrent reads
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def add(
        self,
        source: str,
        doc_id: str,
        content: str,
        embedding: list[float],
        metadata: Optional[dict] = None,
    ) -> int:
        """Add or replace a document. Returns the row id."""
        if not embedding:
            raise ValueError("embedding cannot be empty")
        metadata = metadata or {}
        blob = encode_vector(embedding)
        created_at = datetime.now(timezone.utc).isoformat()
        meta_json = json.dumps(metadata)
        cur = self.conn.execute(
            """
            INSERT OR REPLACE INTO documents (source, doc_id, content, embedding, metadata, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (source, doc_id, content, blob, meta_json, created_at),
        )
        self.conn.commit()
        return cur.lastrowid

    def add_many(
        self,
        items: list[dict],
    ) -> list[int]:
        """Batch add. Each item must have source, doc_id, content, embedding."""
        if not items:
            return []
        rows = []
        now = datetime.now(timezone.utc).isoformat()
        for item in items:
            emb = item.get("embedding", [])
            if not emb:
                continue
            rows.append((
                item["source"],
                item["doc_id"],
                item["content"],
                encode_vector(emb),
                json.dumps(item.get("metadata", {})),
                now,
            ))
        if not rows:
            return []
        # Track starting id for return list
        first_id = self.conn.execute("SELECT COALESCE(MAX(id), 0) FROM documents").fetchone()[0]
        self.conn.executemany(
            """INSERT OR REPLACE INTO documents
            (source, doc_id, content, embedding, metadata, created_at)
            VALUES (?, ?, ?, ?, ?, ?)""",
            rows,
        )
        self.conn.commit()
        # Return the ids we just inserted
        return list(range(first_id + 1, first_id + len(rows) + 1))

    def search(
        self,
        embedding: list[float],
        top_k: int = 5,
        source: Optional[str] = None,
        min_score: float = 0.0,
    ) -> list[SearchResult]:
        """Cosine similarity search. Returns top-K results above min_score."""
        if not embedding:
            return []
        # Filter by source first (uses index)
        if source:
            rows = self.conn.execute(
                "SELECT id, source, doc_id, content, embedding, metadata FROM documents WHERE source = ?",
                (source,),
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT id, source, doc_id, content, embedding, metadata FROM documents"
            ).fetchall()

        scores = []
        for row in rows:
            doc_id, source, dc_id, content, blob, meta_json = row
            vec = decode_vector(blob)
            score = cosine_similarity(embedding, vec)
            if score >= min_score:
                scores.append((score, doc_id, source, dc_id, content, meta_json))
        scores.sort(key=lambda x: -x[0])
        results = []
        for score, doc_id, source, dc_id, content, meta_json in scores[:top_k]:
            try:
                metadata = json.loads(meta_json)
            except json.JSONDecodeError:
                metadata = {}
            results.append(SearchResult(
                id=doc_id,
                source=source,
                doc_id=dc_id,
                content=content,
                score=score,
                metadata=metadata,
            ))
        return results

    def get(self, source: str, doc_id: str) -> Optional[dict]:
        """Get a specific document by source + doc_id."""
        row = self.conn.execute(
            "SELECT id, source, doc_id, content, embedding, metadata, created_at FROM documents WHERE source = ? AND doc_id = ?",
            (source, doc_id),
        ).fetchone()
        if not row:
            return None
        doc_id_pk, src, dc_id, content, blob, meta_json, created_at = row
        return {
            "id": doc_id_pk,
            "source": src,
            "doc_id": dc_id,
            "content": content,
            "embedding": decode_vector(blob),
            "metadata": json.loads(meta_json) if meta_json else {},
            "created_at": created_at,
        }

    def delete(self, source: str, doc_id: Optional[str] = None) -> int:
        """Delete by source (+ optional doc_id). Returns rows deleted."""
        if doc_id:
            cur = self.conn.execute(
                "DELETE FROM documents WHERE source = ? AND doc_id = ?",
                (source, doc_id),
            )
        else:
            cur = self.conn.execute(
                "DELETE FROM documents WHERE source = ?",
                (source,),
            )
        self.conn.commit()
        return cur.rowcount

    def count(self, source: Optional[str] = None) -> int:
        """Count documents, optionally filtered by source."""
        if source:
            return self.conn.execute(
                "SELECT COUNT(*) FROM documents WHERE source = ?", (source,)
            ).fetchone()[0]
        return self.conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0]

    def list_sources(self) -> list[tuple[str, int]]:
        """List sources with document counts."""
        rows = self.conn.execute(
            "SELECT source, COUNT(*) FROM documents GROUP BY source ORDER BY source"
        ).fetchall()
        return [(s, c) for s, c in rows]

    def stats(self) -> dict:
        """Get database stats."""
        total = self.count()
        sources = self.list_sources()
        return {
            "total_documents": total,
            "n_sources": len(sources),
            "sources": [{"source": s, "count": c} for s, c in sources],
            "db_path": self.db_path,
        }


def main():
    """CLI: manage vector store from command line."""
    import argparse
    import sys

    p = argparse.ArgumentParser(description="Vector store CLI")
    p.add_argument("--db", required=True, help="Path to SQLite file (use :memory: for ephemeral)")
    sub = p.add_subparsers(dest="cmd", required=True)

    p_add = sub.add_parser("add", help="Add a document")
    p_add.add_argument("--source", required=True)
    p_add.add_argument("--doc-id", required=True)
    p_add.add_argument("--content", required=True)
    p_add.add_argument("--embedding", help="JSON list of floats")
    p_add.add_argument("--metadata", default="{}", help="JSON metadata")

    p_search = sub.add_parser("search", help="Cosine similarity search")
    p_search.add_argument("--embedding", required=True, help="JSON list of floats")
    p_search.add_argument("--top-k", type=int, default=5)
    p_search.add_argument("--source", help="Restrict to a source")
    p_search.add_argument("--min-score", type=float, default=0.0)

    sub.add_parser("stats", help="Print database stats")
    sub.add_parser("sources", help="List sources")

    p_del = sub.add_parser("delete", help="Delete documents")
    p_del.add_argument("--source", required=True)
    p_del.add_argument("--doc-id", help="If set, delete only this one")

    args = p.parse_args()
    store = VectorStore(args.db)
    try:
        if args.cmd == "add":
            emb = json.loads(args.embedding)
            meta = json.loads(args.metadata)
            row_id = store.add(args.source, args.doc_id, args.content, emb, meta)
            print(f"Added row {row_id}")
        elif args.cmd == "search":
            emb = json.loads(args.embedding)
            results = store.search(emb, top_k=args.top_k, source=args.source, min_score=args.min_score)
            for i, r in enumerate(results, 1):
                print(f"\n[{i}] score={r.score:.4f} source={r.source} doc_id={r.doc_id}")
                print(f"    content: {r.content[:200]}")
        elif args.cmd == "stats":
            print(json.dumps(store.stats(), indent=2))
        elif args.cmd == "sources":
            for source, count in store.list_sources():
                print(f"  {source:30} {count}")
        elif args.cmd == "delete":
            n = store.delete(args.source, args.doc_id)
            print(f"Deleted {n} rows")
    finally:
        store.close()


if __name__ == "__main__":
    main()
