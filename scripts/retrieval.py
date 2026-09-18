"""
retrieval.py
------------
Person 1 (Absher RAG improvement) — Steps: vector store + Top-K retrieval.

Embedding backend
==================
`VectorStore` doesn't hardcode a backend — it takes any `Embedder`
(embeddings.py) and calls `.fit()` / `.transform_corpus()` /
`.transform_query()`. As of this revision the DEFAULT is `openai` (see
embeddings.DEFAULT_EMBEDDER_BACKEND), matching the project proposal's
stated technology stack (Python • LangChain • FAISS • OpenAI API);
sentence-transformers and TF-IDF remain as the offline-friendly fallback
chain. `VectorStore.backend_info()` below reports which backend actually
produced the embeddings for a given store instance — always check this
before labeling a result "semantic" or "FAISS-backed", because a
requested-but-unavailable backend silently falls back rather than crashing.

Vector store choice
====================
Two search implementations live side by side here, selected automatically
by which embedder is active — `search()` itself doesn't change, callers
never need to know which path ran:

- tfidf / sentence-transformers -> brute-force cosine similarity
  (`sklearn.metrics.pairwise.cosine_similarity`) over an in-memory matrix.
  Exact, fast enough for this corpus size (a few dozen chunks), no extra
  dependency. This is the ORIGINAL, fully-tested path — completely
  unchanged by this revision.
- openai -> a real `langchain_community.vectorstores.FAISS` index for
  candidate selection (built with `distance_strategy=DistanceStrategy.COSINE`),
  but the reported score/final ordering is computed independently via direct
  cosine similarity against stored embedding vectors, NOT by trusting
  `similarity_search_with_score()`'s raw returned value — found empirically
  necessary on the first real run with a live OpenAI key (that value did not
  reliably come back sorted descending; see the note in `build()`/`search()`
  below for the exact fix). This is the NEW path, matching the proposal's
  stated FAISS requirement, while keeping score semantics guaranteed correct
  and on the same "higher = more similar" scale the rest of this codebase
  already assumes, independent of any particular library version's internal
  scoring convention.

KNOWN CAVEAT — read before trusting query_mismatch signals under "openai":
Even with the cosine distance strategy above, OpenAI's dense embeddings do
not necessarily produce similarity scores on the exact same numeric
distribution TF-IDF did (dense embedding cosine similarities for
loosely-related text commonly run higher than sparse TF-IDF's do for the
same relationship). monitoring_agent.py's QUERY_MISMATCH_THRESHOLD (0.12)
was empirically calibrated against TF-IDF's scores and is NOT changed by
this revision (that's a calibration decision needing real OpenAI-backed
data this sandbox cannot produce — no network access here). This is an
inherited limitation (it already existed between TF-IDF and
sentence-transformers, sharing one threshold), not a new one — but it is
more likely to actually matter once "openai" is the live default. Suggest
running a handful of known good/bad queries once this is live and checking
the resulting top1 scores against 0.12 before trusting that signal.

Top-K
=====
`search(query, top_k)` returns the top_k chunks by similarity, each with
its score, so `evaluation.py` can compare K=3 / 5 / 7 and so
`monitoring_agent.py` can log exactly what was retrieved — regardless of
which embedding backend or search implementation is behind it.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
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
        self._faiss_index = None    # only set when the active embedder is "openai"
        self._faiss_vectors = None  # raw embedding vectors, for independent re-scoring — see search()

    def build(self, chunks: List[Dict[str, Any]]) -> "VectorStore":
        self.chunks = chunks
        texts = [c["text"] for c in chunks]

        if self.embedder.name == "openai":
            # Real FAISS index, matching the project proposal's stated
            # technology stack. Built ONLY for the openai backend — the
            # original sklearn cosine-similarity path below (the `else`
            # branch) is completely untouched for tfidf/sentence-transformers,
            # so none of the already-tested default behavior changes.
            from langchain_community.vectorstores import FAISS
            from langchain_community.vectorstores.utils import DistanceStrategy
            from langchain_core.documents import Document

            # Embed once here (not just letting FAISS.from_documents() do it
            # internally) so search() below can independently recompute
            # cosine similarity for the final reported score/order, instead
            # of trusting similarity_search_with_score()'s raw returned
            # value. FOUND EMPIRICALLY (first real run with a live OpenAI
            # key, 2026-09-xx): trusting that raw score directly did NOT
            # reliably come back sorted by descending relevance — the exact
            # score sign/ordering convention for LangChain's FAISS wrapper
            # isn't something this sandbox could verify against a real API
            # beforehand, and it turned out to need this fix. FAISS is still
            # doing the real nearest-neighbor search/candidate selection
            # (distance_strategy=COSINE below); only the reported score and
            # final ordering are computed independently now.
            vectors = self.embedder.langchain_embeddings.embed_documents(texts)
            documents = [
                Document(page_content=text, metadata={"_chunk_index": i})
                for i, text in enumerate(texts)
            ]
            self._faiss_index = FAISS.from_documents(
                documents,
                self.embedder.langchain_embeddings,
                distance_strategy=DistanceStrategy.COSINE,
            )
            self._faiss_vectors = np.asarray(vectors)
        else:
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
        requested. `fallback_from` is non-None only when a different backend
        was requested but unavailable and this one silently stood in for it —
        always check this before labeling a result "semantic" or "FAISS"."""
        return {
            "requested_backend": os.environ.get("ABSHER_EMBEDDER", DEFAULT_EMBEDDER_BACKEND),
            "actual_backend": self.embedder.name,
            "fallback_from": getattr(self.embedder, "fallback_from", None),
            "fallback_reason": getattr(self.embedder, "fallback_reason", None),
        }

    def _to_retrieved_chunk(self, rank: int, score: float, c: Dict[str, Any]) -> RetrievedChunk:
        """Shared by both search paths below so a chunk's metadata is mapped
        into RetrievedChunk exactly the same way regardless of which backend
        produced the match — the only thing that differs per-path is how
        `rank`/`score`/`c` get computed upstream."""
        return RetrievedChunk(
            rank=rank,
            score=score,
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
        )

    def search(self, query: str, top_k: int = 5) -> List[RetrievedChunk]:
        if self._faiss_index is not None:
            # FAISS does the real nearest-neighbor candidate selection
            # (distance_strategy=COSINE, set in build() above). The score
            # used for the FINAL reported order/value is then computed
            # independently via direct cosine similarity against the query
            # embedding, rather than trusting the raw score
            # similarity_search_with_score() returns — see the note in
            # build() for why (empirically found necessary, not a
            # theoretical worry).
            hits = self._faiss_index.similarity_search_with_score(query, k=top_k)
            query_vec = np.asarray(self.embedder.langchain_embeddings.embed_query(query))
            q_norm = float(np.linalg.norm(query_vec)) + 1e-10

            scored = []
            for doc, _raw_score in hits:
                idx = doc.metadata["_chunk_index"]
                doc_vec = self._faiss_vectors[idx]
                sim = float(np.dot(query_vec, doc_vec) / (q_norm * (float(np.linalg.norm(doc_vec)) + 1e-10)))
                scored.append((sim, idx))
            scored.sort(key=lambda pair: pair[0], reverse=True)

            return [
                self._to_retrieved_chunk(rank, sim, self.chunks[idx])
                for rank, (sim, idx) in enumerate(scored, start=1)
            ]

        if self._matrix is None:
            raise RuntimeError("Call build() before search().")
        q_vec = self.embedder.transform_query(query)
        sims = cosine_similarity(q_vec, self._matrix)[0]
        order = sims.argsort()[::-1][:top_k]
        return [
            self._to_retrieved_chunk(rank, float(sims[idx]), self.chunks[idx])
            for rank, idx in enumerate(order, start=1)
        ]


if __name__ == "__main__":
    store = VectorStore.from_jsonl()
    print(f"Backend info: {store.backend_info()}\n")
    demo_query = "كم سنة يمكنني تجديد رخصة القيادة؟"
    print(f"Query: {demo_query}\n")
    for r in store.search(demo_query, top_k=5):
        print(f"#{r.rank} score={r.score:.3f} [{r.chunk_id}] {r.section_title_ar}")
        print(f"    {r.text[:120]}...")

