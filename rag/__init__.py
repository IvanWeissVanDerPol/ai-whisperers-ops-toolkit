"""rag — Retrieval-Augmented Generation glue.

Bridge between the swarm (R30-R32) and the vector DB (R33):
- rag.py: high-level retrieve() that returns formatted context
- index_swarm_run.py: index a swarm's snapshots + blackboard for RAG
- worker_integration: load RAG context inside a swarm worker (via env var)
"""
