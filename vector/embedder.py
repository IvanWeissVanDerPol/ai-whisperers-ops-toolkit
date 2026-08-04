#!/usr/bin/env python3
"""
vector/embedder.py — Generate embeddings via OpenAI-compatible APIs.

Strategy:
- If a real OpenAI-compatible API is configured (OPENAI_API_KEY set),
  use it (text-embedding-3-small = 1536 dims, fast + cheap).
- Otherwise, fall back to **deterministic feature hashing** of n-grams.
  This is rough but allows the full pipeline to work without any external API.

The fallback is the key insight: we can ship a working semantic-search
infrastructure without GPU, without API keys, without internet. The quality
is lower (no real semantic understanding) but the *system* is the same.

When you do add a real API key, just set OPENAI_API_KEY and the embedder
auto-promotes. No code changes elsewhere.

Usage:
    from embedder import Embedder
    e = Embedder()  # auto-detects API
    vec = e.embed("hello world")  # list of floats
"""

import hashlib
import math
import os
import re
from typing import Optional, Union

DEFAULT_MODEL = "text-embedding-3-small"
DEFAULT_FALLBACK_DIM = 256


def _normalize(vec: list[float]) -> list[float]:
    """L2 normalize a vector in pure Python."""
    mag = math.sqrt(sum(v * v for v in vec))
    if mag == 0:
        return vec
    return [v / mag for v in vec]


def _tokenize(text: str) -> list[str]:
    """Simple word tokenization: lowercase, split on non-alpha, drop empties."""
    text = text.lower()
    tokens = re.findall(r"[a-z0-9]+", text)
    return tokens


def _fallback_embed(text: str, dim: int = DEFAULT_FALLBACK_DIM) -> list[float]:
    """Feature-hashing embedding.

    Maps tokens to dim-dimensional space via hash. Reusable across runs
    (deterministic). Quality is low but it's a real vector with real
    cosine similarity.
    """
    vec = [0.0] * dim
    tokens = _tokenize(text)
    if not tokens:
        return vec
    # Single tokens
    for token in tokens:
        h = int(hashlib.md5(token.encode()).hexdigest()[:8], 16)
        idx = h % dim
        sign = 1.0 if (h >> 8) & 1 else -1.0
        vec[idx] += sign
    # Bigrams (catches local context)
    for i in range(len(tokens) - 1):
        bigram = f"{tokens[i]}_{tokens[i+1]}"
        h = int(hashlib.md5(bigram.encode()).hexdigest()[:8], 16)
        idx = h % dim
        sign = 1.0 if (h >> 8) & 1 else -1.0
        vec[idx] += sign * 0.5
    return _normalize(vec)


class Embedder:
    """Embedding backend with automatic fallback."""

    def __init__(
        self,
        model: str = DEFAULT_MODEL,
        dim: int = DEFAULT_FALLBACK_DIM,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
    ):
        self.model = model
        self.dim = dim
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY")
        self.base_url = base_url or os.environ.get("OPENAI_BASE_URL")
        self._client = None
        self._using_real_api = False

        # Try to initialize OpenAI client if we have a key
        if self.api_key:
            try:
                import openai
                self._client = openai.OpenAI(
                    api_key=self.api_key,
                    base_url=self.base_url,
                )
                self._using_real_api = True
            except ImportError:
                self._client = None

    @property
    def backend(self) -> str:
        return "openai" if self._using_real_api else "fallback"

    def embed(self, text: str) -> list[float]:
        """Generate an embedding for a single text string."""
        return self._embed_with_real_api(text) if self._using_real_api else _fallback_embed(text, self.dim)

    def embed_many(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings for a batch of texts."""
        if not texts:
            return []
        if not self._using_real_api:
            return [_fallback_embed(t, self.dim) for t in texts]
        try:
            response = self._client.embeddings.create(
                model=self.model,
                input=texts,
            )
            return [item.embedding for item in response.data]
        except Exception as e:
            # Fallback to per-text in case batch fails
            return [self.embed(t) for t in texts]

    def _embed_with_real_api(self, text: str) -> list[float]:
        try:
            response = self._client.embeddings.create(
                model=self.model,
                input=[text[:8000]],  # limit to avoid huge inputs
            )
            return response.data[0].embedding
        except Exception:
            # Fall back to deterministic on any API error
            return _fallback_embed(text, self.dim)

    def info(self) -> dict:
        """Get embedder info."""
        return {
            "backend": self.backend,
            "model": self.model if self._using_real_api else "feature-hash",
            "dim": self.dim if not self._using_real_api else "1536 (auto)",
        }


def main():
    """CLI: embed a text from the command line."""
    import argparse
    import json

    p = argparse.ArgumentParser(description="Generate embeddings")
    p.add_argument("text", nargs="?", help="Text to embed")
    p.add_argument("--dim", type=int, default=DEFAULT_FALLBACK_DIM)
    p.add_argument("--info", action="store_true", help="Print embedder info and exit")
    args = p.parse_args()

    e = Embedder(dim=args.dim)
    if args.info:
        print(json.dumps(e.info(), indent=2))
        return
    if not args.text:
        print("Usage: embedder.py <text> [--dim N]")
        sys.exit(1)
    vec = e.embed(args.text)
    print(f"Backend: {e.backend}")
    print(f"Dim: {len(vec)}")
    print(f"First 10 dims: {vec[:10]}")


if __name__ == "__main__":
    import sys
    main()
