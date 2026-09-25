"""Normalize a LangChain/FAISS retrieval run for ValidationAgent."""
from __future__ import annotations

import time
from typing import Any, Dict, Optional


def build_retrieval_run(
    vector_store: Any,
    query: str,
    top_k: int = 4,
    *,
    expected_platform: Optional[str] = None,
    expected_service: Optional[str] = None,
) -> Dict[str, Any]:
    start = time.perf_counter()

    if hasattr(vector_store, "similarity_search_with_score"):
        raw_results = vector_store.similarity_search_with_score(
            query,
            k=top_k,
        )
    else:
        raw_results = [
            (doc, None)
            for doc in vector_store.similarity_search(
                query,
                k=top_k,
            )
        ]

    latency_seconds = time.perf_counter() - start
    normalized = []

    for rank, (doc, score) in enumerate(
        raw_results,
        start=1,
    ):
        metadata = dict(
            getattr(doc, "metadata", {}) or {}
        )
        platform = metadata.get("platform")
        service = metadata.get("service")

        relevant = None
        if (
            expected_platform is not None
            and expected_service is not None
        ):
            relevant = (
                platform == expected_platform
                and service == expected_service
            )

        item = {
            "rank": rank,
            "platform": platform,
            "service": service,
            "source": metadata.get("source"),
            "chunk_index": metadata.get("chunk_index"),
            "text": str(
                getattr(doc, "page_content", "") or ""
            ),
        }

        if score is not None:
            item["raw_score"] = float(score)
        if relevant is not None:
            item["relevant"] = relevant

        normalized.append(item)

    return {
        "query": query,
        "top_k": top_k,
        "retrieved_results": normalized,
        "answer": "",
        "judge_score": None,
        "latency_seconds": latency_seconds,
    }
