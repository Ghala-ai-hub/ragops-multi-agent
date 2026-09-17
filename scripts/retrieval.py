"""
retrieval.py
------------
Person 1 (Absher RAG improvement) — Steps: vector store + Top-K retrieval.

Embedding backend
==================
`VectorStore` doesn't hardcode a backend — it takes any `Embedder`
(embeddings.py) and calls `.fit()` / `.transform_corpus()` /
`.transform_query()`. As of this revision the DEFAULT is
`sentence-transformers` (see embeddings.DEFAULT_EMBEDDER_BACKEND); TF-IDF is
the retained baseline and automatic fallback. `VectorStore.backend_info()`
below reports which backend actually produced the embeddings for a given
store instance — always check this before labeling a result "semantic",
because a requested-but-unavailable sentence-transformers backend silently
still runs (on TF-IDF) rather than crashing.

Vector store choice
====================
The assignment allows "FAISS or another simple vector store". This corpus is
tiny (a few dozen chunks), so a brute-force cosine-similarity search over
the embedding matrix (`sklearn.metrics.pairwise.cosine_similarity`) is exact,
fast enough (milliseconds), and works identically for the sparse TF-IDF
matrix and a dense sentence-transformers matrix — the same `search()` below
needs no changes when the backend changes. Needs no extra dependency that
this sandbox cannot install. If the corpus grows into the tens of thousands
of chunks, swapping in FAISS's `IndexFlatIP` is a ~10-line change behind the
same `VectorStore` interface — noted in README as a scaling follow-up, not
built now because it is not needed yet ("do not over-engineer").

Top-K
=====
`search(query, top_k)` returns the top_k chunks by cosine similarity, each
with its score, so `evaluation.py` can compare K=3 / 5 / 7 and so
`monitoring_agent.py` can log exactly what was retrieved — regardless of
which embedding backend is behind it.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from sklearn.metrics.pairwise import cosine_similarity

from embeddings import DEFAULT_EMBEDDER_BACKEND, Embedder, get_embedder

BASE_DIR = Path(__file__).resolve().parent.parent
PROCESSED_DIR = BASE_DIR / "data" / "processed"


@dataclass
class RetrievedChunk:
    rank: int
    score: float
    chunk_id: str
    service_id: str
    service_name_ar: str
    chunk_type: str
    section_title_ar: str
    source_documents: List[str]
    data_completeness: str
    platform: str
    source_file: str
    chunk_index: int
    text: str


class VectorStore:
    def __init__(self, embedder: Optional[Embedder] = None):
        self.embedder = embedder or get_embedder()
        self.chunks: List[Dict[str, Any]] = []
        self._matrix = None

    def build(self, chunks: List[Dict[str, Any]]) -> "VectorStore":
        self.chunks = chunks
        texts = [c["text"] for c in chunks]
        self.embedder.fit(texts)
        self._matrix = self.embedder.transform_corpus(texts)
        return self

    @classmethod
    def from_jsonl(cls, path: Path = PROCESSED_DIR / "chunks.jsonl",
                    embedder: Optional[Embedder] = None) -> "VectorStore":
        chunks = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
        return cls(embedder).build(chunks)

    def backend_info(self) -> Dict[str, Any]:
        """What backend actually embedded this store's chunks, vs. what was
        requested. `fallback_from` is non-None only when sentence-transformers
        was requested but unavailable and TF-IDF silently stood in for it —
        always check this before calling a result "semantic retrieval"."""
        return {
            "requested_backend": os.environ.get("ABSHER_EMBEDDER", DEFAULT_EMBEDDER_BACKEND),
            "actual_backend": self.embedder.name,
            "fallback_from": getattr(self.embedder, "fallback_from", None),
            "fallback_reason": getattr(self.embedder, "fallback_reason", None),
        }

    def search(self, query: str, top_k: int = 5) -> List[RetrievedChunk]:
        if self._matrix is None:
            raise RuntimeError("Call build() before search().")
        q_vec = self.embedder.transform_query(query)
        sims = cosine_similarity(q_vec, self._matrix)[0]
        order = sims.argsort()[::-1][:top_k]
        results: List[RetrievedChunk] = []
        for rank, idx in enumerate(order, start=1):
            c = self.chunks[idx]
            results.append(RetrievedChunk(
                rank=rank,
                score=float(sims[idx]),
                chunk_id=c["chunk_id"],
                service_id=c["service_id"],
                service_name_ar=c["service_name_ar"],
                chunk_type=c["chunk_type"],
                section_title_ar=c["section_title_ar"],
                source_documents=c["source_documents"],
                data_completeness=c["data_completeness"],
                platform=c.get("platform", "unknown"),
                source_file=c.get("source_file", ""),
                chunk_index=c.get("chunk_index", 0),
                text=c["text"],
            ))
        return results


if __name__ == "__main__":
    store = VectorStore.from_jsonl()
    print(f"Backend info: {store.backend_info()}\n")
    demo_query = "كم سنة يمكنني تجديد رخصة القيادة؟"
    print(f"Query: {demo_query}\n")
    for r in store.search(demo_query, top_k=5):
        print(f"#{r.rank} score={r.score:.3f} [{r.chunk_id}] {r.section_title_ar}")
        print(f"    {r.text[:120]}...")
