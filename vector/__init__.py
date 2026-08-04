"""vector — Atlas F-1 Vector DB foundation.

Pure-Python + SQLite semantic search stack:
- vector_store.py: storage + cosine similarity (sqlite3, zero-deps)
- embedder.py: text → vectors via OpenAI-compatible API
- indexer.py: chunk + embed + store documents
- searcher.py: query → top-K results CLI
"""
