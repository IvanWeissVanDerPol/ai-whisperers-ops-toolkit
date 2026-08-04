#!/usr/bin/env python3
"""
vector/indexer.py — Chunk + embed + store documents into VectorStore.

Takes text content + metadata, splits into chunks (paragraphs or sentences),
embeds each chunk, and adds to the vector store.

Chunking strategies:
- paragraph: split on \n\n (best for articles, docs)
- sentence: split on .?! (best for chats, short content)
- window:   fixed-size sliding window (best for code, dense text)

Usage:
    from indexer import index_text, index_file
    count = index_text("docs", "intro", content, store, embedder)
    count = index_file("docs", "doc1", Path("README.md"), store, embedder)
"""

import re
import sys
from pathlib import Path
from typing import Optional, Union

sys.path.insert(0, str(Path(__file__).parent))
from vector_store import VectorStore  # noqa: E402
from embedder import Embedder  # noqa: E402


def chunk_paragraphs(text: str) -> list[str]:
    """Split on blank lines. Filters out very short paragraphs."""
    chunks = []
    for para in re.split(r"\n\s*\n", text):
        para = para.strip()
        if len(para) >= 20:  # skip tiny fragments
            chunks.append(para)
    return chunks


def chunk_sentences(text: str) -> list[str]:
    """Split on sentence boundaries, group by 3 sentences."""
    sentences = re.split(r"(?<=[.!?])\s+", text)
    sentences = [s.strip() for s in sentences if s.strip()]
    chunks = []
    for i in range(0, len(sentences), 3):
        chunk = " ".join(sentences[i:i + 3])
        if len(chunk) >= 20:
            chunks.append(chunk)
    return chunks


def chunk_window(text: str, window_size: int = 200, overlap: int = 40) -> list[str]:
    """Sliding fixed-size window (best for code)."""
    chunks = []
    words = text.split()
    if not words:
        return chunks
    i = 0
    while i < len(words):
        chunk_words = words[i:i + window_size]
        chunk = " ".join(chunk_words)
        if len(chunk) >= 20:
            chunks.append(chunk)
        if i + window_size >= len(words):
            break
        i += window_size - overlap
    return chunks


CHUNKERS = {
    "paragraph": chunk_paragraphs,
    "sentence": chunk_sentences,
    "window": chunk_window,
}


def index_text(
    source: str,
    base_doc_id: str,
    text: str,
    store: VectorStore,
    embedder: Embedder,
    strategy: str = "paragraph",
    metadata: Optional[dict] = None,
) -> int:
    """Index a chunk of text. Returns number of chunks added."""
    metadata = metadata or {}
    chunker = CHUNKERS.get(strategy, chunk_paragraphs)
    chunks = chunker(text)
    if not chunks:
        return 0
    # Embed all chunks in batch (faster than per-text)
    embeddings = embedder.embed_many(chunks)
    items = []
    for i, (chunk, emb) in enumerate(zip(chunks, embeddings)):
        items.append({
            "source": source,
            "doc_id": f"{base_doc_id}_{i:03d}",
            "content": chunk,
            "embedding": emb,
            "metadata": {
                **metadata,
                "chunk_index": i,
                "strategy": strategy,
                "base_doc_id": base_doc_id,
            },
        })
    store.add_many(items)
    return len(items)


def index_file(
    source: str,
    doc_id: str,
    path: Union[str, Path],
    store: VectorStore,
    embedder: Embedder,
    strategy: Optional[str] = None,
) -> int:
    """Index a single file. Auto-detects strategy by extension."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(path)
    content = path.read_text(errors="replace")
    if strategy is None:
        suffix = path.suffix.lower()
        if suffix in (".md", ".txt", ".rst"):
            strategy = "paragraph"
        elif suffix in (".py", ".js", ".ts", ".tsx", ".jsx", ".go", ".rs", ".c", ".cpp"):
            strategy = "window"
        else:
            strategy = "paragraph"
    return index_text(
        source,
        doc_id,
        content,
        store,
        embedder,
        strategy=strategy,
        metadata={"file": str(path)},
    )


def index_directory(
    source: str,
    dir_path: Union[str, Path],
    store: VectorStore,
    embedder: Embedder,
    glob_patterns: tuple = ("*.md", "*.txt", "*.py"),
) -> int:
    """Index all files matching patterns in a directory."""
    dir_path = Path(dir_path)
    if not dir_path.exists():
        raise FileNotFoundError(dir_path)
    count = 0
    for pattern in glob_patterns:
        for file_path in sorted(dir_path.glob(f"**/{pattern}")):
            doc_id = str(file_path.relative_to(dir_path))
            count += index_file(
                source,
                doc_id,
                file_path,
                store,
                embedder,
            )
    return count


def main():
    """CLI: index text or file from the command line."""
    import argparse

    p = argparse.ArgumentParser(description="Index documents into vector store")
    p.add_argument("--db", required=True, help="Path to SQLite DB")
    p.add_argument("--source", required=True, help="Source name (e.g., 'docs', 'swarm-state')")
    sub = p.add_subparsers(dest="cmd", required=True)

    p_text = sub.add_parser("text", help="Index raw text")
    p_text.add_argument("--doc-id", required=True)
    p_text.add_argument("--text", required=True)
    p_text.add_argument("--strategy", default="paragraph",
                       choices=list(CHUNKERS))
    p_text.add_argument("--metadata", default="{}")

    p_file = sub.add_parser("file", help="Index a single file")
    p_file.add_argument("--doc-id", required=True)
    p_file.add_argument("--path", required=True)
    p_file.add_argument("--strategy", default=None)

    p_dir = sub.add_parser("dir", help="Index a directory")
    p_dir.add_argument("--path", required=True)
    p_dir.add_argument("--patterns", nargs="+", default=["*.md"])

    args = p.parse_args()
    store = VectorStore(args.db)
    e = Embedder()
    try:
        if args.cmd == "text":
            n = index_text(
                args.source,
                args.doc_id,
                args.text,
                store,
                e,
                strategy=args.strategy,
                metadata={"doc_id": args.doc_id},
            )
            print(f"Indexed {n} chunks")
        elif args.cmd == "file":
            n = index_file(
                args.source,
                args.doc_id,
                args.path,
                store,
                e,
                strategy=args.strategy,
            )
            print(f"Indexed {n} chunks")
        elif args.cmd == "dir":
            n = index_directory(
                args.source,
                args.path,
                store,
                e,
                glob_patterns=tuple(args.patterns),
            )
            print(f"Indexed {n} chunks total")
    finally:
        store.close()


if __name__ == "__main__":
    main()
