"""Non-destructive re-chunk candidate adapter for RAGOps.

Bridges OptimizationTools.rechunk_and_reindex() to ApprovedActionExecutor's
expected callback contract:

    parameters -> {
        "after_run": {...},
        "action_result": {...}
    }

The active evaluation index is never overwritten. A new candidate index is
built under vector_store/candidates/, the same query is rerun against it, and
ValidationAgent can then compare BEFORE vs AFTER.
"""
from __future__ import annotations

from typing import Any, Callable, Dict, Optional

try:
    from scripts.optimization_tools import rechunk_and_reindex
    from scripts.retrieval_run import build_retrieval_run
except ModuleNotFoundError:
    from optimization_tools import rechunk_and_reindex
    from retrieval_run import build_retrieval_run


BuildCandidate = Callable[..., Dict[str, Any]]
BuildRetrievalRun = Callable[..., Dict[str, Any]]


class RechunkCandidateAdapter:
    def __init__(
        self,
        *,
        expected_platform: Optional[str] = None,
        expected_service: Optional[str] = None,
        build_candidate: BuildCandidate = rechunk_and_reindex,
        build_run: BuildRetrievalRun = build_retrieval_run,
    ) -> None:
        self.expected_platform = expected_platform
        self.expected_service = expected_service
        self.build_candidate = build_candidate
        self.build_run = build_run

    def set_expected(
        self,
        *,
        platform: Optional[str],
        service: Optional[str],
    ) -> None:
        """Update offline ground truth for the next validation run."""
        self.expected_platform = platform
        self.expected_service = service

    def __call__(
        self,
        parameters: Dict[str, Any],
    ) -> Dict[str, Any]:
        original_query = str(
            parameters.get("original_query", "")
        ).strip()
        baseline_k = int(
            parameters.get("baseline_k", 4)
        )
        chunk_size = int(
            parameters.get("chunk_size", 500)
        )
        chunk_overlap = int(
            parameters.get("chunk_overlap", 100)
        )

        if not original_query:
            raise ValueError(
                "rechunk candidate requires original_query"
            )
        if baseline_k < 1:
            raise ValueError("baseline_k must be >= 1")

        candidate = self.build_candidate(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
        )

        vector_store = candidate.get("vector_store")
        if vector_store is None:
            raise ValueError(
                "candidate builder did not return vector_store"
            )

        after_run = self.build_run(
            vector_store,
            original_query,
            baseline_k,
            expected_platform=self.expected_platform,
            expected_service=self.expected_service,
        )

        action_result = {
            "candidate_status": candidate.get("status"),
            "candidate_index_path": candidate.get(
                "candidate_index_path"
            ),
            "non_destructive": True,
            "chunk_size": candidate.get(
                "chunk_size", chunk_size
            ),
            "chunk_overlap": candidate.get(
                "chunk_overlap", chunk_overlap
            ),
            "chunks": candidate.get("chunks"),
            "final_files": candidate.get("final_files"),
            "platforms": candidate.get("platforms"),
            "embedding_model": candidate.get(
                "embedding_model"
            ),
        }

        return {
            "after_run": after_run,
            "action_result": action_result,
        }
