"""Adapters that convert a real retriever run into ValidationAgent's contract."""
from __future__ import annotations

import time
from typing import Any, Dict, Optional


def build_retrieval_run(
    store: Any,
    query: str,
    top_k: int,
    *,
    expected_platform: Optional[str] = None,
    expected_service: Optional[str] = None,
) -> Dict[str, Any]:
    """Run the real store and normalize results for before/after validation.

    This adapter intentionally evaluates retrieval only. ``answer`` and
    ``judge_score`` remain neutral until the API-backed RAG answer generator and
    LLM-as-a-Judge are connected in the next integration layer.
    """
    start = time.perf_counter()
    results = store.search(query, top_k=top_k)
    latency_seconds = time.perf_counter() - start

    normalized = []
    for result in results:
        platform = getattr(result, "platform", None)
        service = getattr(result, "service_id", None)
        relevant = (
            (expected_platform is None or platform == expected_platform)
            and (expected_service is None or service == expected_service)
        )
        normalized.append(
            {
                "rank": int(result.rank),
                "score": float(result.score),
                "platform": platform,
                "service": service,
                "source": getattr(result, "source_file", ""),
                "chunk_index": getattr(result, "chunk_index", 0),
                "chunk_id": getattr(result, "chunk_id", ""),
                "text": getattr(result, "text", ""),
                "relevant": relevant,
            }
        )

    return {
        "query": query,
        "top_k": top_k,
        "retrieved_results": normalized,
        "answer": "",
        "judge_score": None,
        "latency_seconds": latency_seconds,
    }
