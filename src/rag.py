"""
src/rag.py — Lightweight RAG using BM25 keyword search

BM25 is chosen over neural embeddings because:
  - No model download (fast startup, small memory)
  - <5ms retrieval — critical for real-time voice
  - Works excellently for structured business documents
  - Handles both Amharic and English keywords naturally

Usage:
    index = RAGIndex(knowledge_text)
    context = index.search("የታክስ አገልግሎት", top_k=3)
"""

import re
from rank_bm25 import BM25Okapi


# ── Text chunking ─────────────────────────────────────────────────────────────

def _chunk_text(text: str, chunk_size: int = 120, overlap: int = 20) -> list[str]:
    """Split knowledge base text into overlapping word-level chunks.

    Smaller chunks (120 words) = more precise retrieval for voice responses.
    Overlap (20 words) = context is not lost at chunk boundaries.
    """
    # Split on section headers to keep logical units together
    sections = re.split(r"\n(?==)", text)   # split before == headings
    chunks: list[str] = []

    for section in sections:
        words = section.split()
        if not words:
            continue
        if len(words) <= chunk_size:
            chunks.append(section.strip())
        else:
            i = 0
            while i < len(words):
                chunk = " ".join(words[i: i + chunk_size])
                if chunk.strip():
                    chunks.append(chunk.strip())
                i += chunk_size - overlap

    return [c for c in chunks if len(c.strip()) > 20]


def _tokenize(text: str) -> list[str]:
    """Tokenize for BM25 — works for both Amharic (Unicode words) and English."""
    # Keep Ethiopic chars, Latin chars, and digits as tokens
    tokens = re.findall(r"[\u1200-\u137F]+|[a-zA-Z]+|\d+", text.lower())
    return tokens if tokens else ["_empty_"]


# ── RAG Index ─────────────────────────────────────────────────────────────────

class RAGIndex:
    """BM25 index built from a company's knowledge base text."""

    def __init__(self, knowledge_text: str):
        self.chunks = _chunk_text(knowledge_text)
        if self.chunks:
            tokenized = [_tokenize(c) for c in self.chunks]
            self.bm25  = BM25Okapi(tokenized)
        else:
            self.bm25 = None
        print(f"[RAG] Indexed {len(self.chunks)} chunks")

    def search(self, query: str, top_k: int = 3, min_score: float = 0.1) -> str:
        """Return the most relevant knowledge chunks for this query.

        Returns an empty string if nothing relevant is found.
        """
        if not self.bm25 or not self.chunks or not query.strip():
            return ""

        tokens = _tokenize(query)
        scores = self.bm25.get_scores(tokens)

        # Pick top-k above minimum relevance threshold
        ranked = sorted(
            enumerate(scores), key=lambda x: x[1], reverse=True
        )
        results = [
            self.chunks[i]
            for i, score in ranked[:top_k]
            if score >= min_score
        ]

        return "\n\n".join(results)
