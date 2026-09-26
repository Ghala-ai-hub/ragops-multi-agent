"""Monitoring Agent for the unified four-platform RAGOps corpus.

The Monitoring Agent observes retrieval behavior and produces raw evidence for
Diagnosis. It does not assign issue_type and does not choose an optimization.

Default baseline retrieval uses Top-K = 4, matching the project's evaluation
configuration (Recall@4 / Precision@4 / MRR).

Ground-truth-dependent fields are populated only for offline evaluation when
expected_platform + expected_service are explicitly supplied. In normal
production usage those fields remain None rather than being invented.
"""
from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

DEFAULT_BASELINE_K = 4
DEFAULT_EXPANDED_K = 10
MIN_CHUNK_CHARS = 80

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_LOG_PATH = PROJECT_ROOT / "logs" / "monitoring_reports.jsonl"


class MonitoringAgent:
    def __init__(
        self,
        vector_store: Any,
        log_path: Path = DEFAULT_LOG_PATH,
    ) -> None:
        self.vector_store = vector_store
        self.log_path = Path(log_path)
        self.log_path.parent.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _is_relevant(
        metadata: Dict[str, Any],
        expected_platform: str,
        expected_service: str,
    ) -> bool:
        return (
            metadata.get("platform") == expected_platform
            and metadata.get("service") == expected_service
        )

    @staticmethod
    def _normalize_results(
        scored_docs: List[Any],
        *,
        expected_platform: Optional[str] = None,
        expected_service: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        normalized: List[Dict[str, Any]] = []

        for rank, item in enumerate(scored_docs, start=1):
            if isinstance(item, tuple):
                doc, score = item
            else:
                doc, score = item, None

            metadata = dict(getattr(doc, "metadata", {}) or {})
            text = str(getattr(doc, "page_content", "") or "")

            relevant: Optional[bool] = None
            if (
                expected_platform is not None
                and expected_service is not None
            ):
                relevant = MonitoringAgent._is_relevant(
                    metadata,
                    expected_platform,
                    expected_service,
                )

            row: Dict[str, Any] = {
                "rank": rank,
                "platform": metadata.get("platform"),
                "service": metadata.get("service"),
                "source": metadata.get("source"),
                "chunk_index": metadata.get("chunk_index"),
                "text": text,
                "char_len": len(text),
            }

            # LangChain/FAISS raw score semantics depend on distance strategy.
            # We log it as evidence only and never treat it as a universal
            # confidence threshold.
            if score is not None:
                row["raw_score"] = float(score)

            if relevant is not None:
                row["relevant"] = relevant

            normalized.append(row)

        return normalized

    def _search(
        self,
        query: str,
        k: int,
        *,
        expected_platform: Optional[str] = None,
        expected_service: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        if hasattr(self.vector_store, "similarity_search_with_score"):
            scored_docs = self.vector_store.similarity_search_with_score(
                query,
                k=k,
            )
        else:
            docs = self.vector_store.similarity_search(query, k=k)
            scored_docs = list(docs)

        return self._normalize_results(
            list(scored_docs),
            expected_platform=expected_platform,
            expected_service=expected_service,
        )

    @staticmethod
    def _first_relevant_rank(
        results: List[Dict[str, Any]],
    ) -> Optional[int]:
        for item in results:
            if item.get("relevant") is True:
                return int(item["rank"])
        return None

    @staticmethod
    def _chunking_signal(
        results: List[Dict[str, Any]],
    ) -> bool:
        """Conservative heuristic: flag only clearly tiny/empty chunks.

        This is an observation signal, not a final diagnosis.
        """
        return any(
            int(item.get("char_len") or 0) < MIN_CHUNK_CHARS
            for item in results
        )

    def build_monitoring_report(
        self,
        query: str,
        *,
        baseline_k: int = DEFAULT_BASELINE_K,
        expanded_k: int = DEFAULT_EXPANDED_K,
        expected_platform: Optional[str] = None,
        expected_service: Optional[str] = None,
        rewritten_query: Optional[str] = None,
    ) -> Dict[str, Any]:
        query = str(query).strip()
        if not query:
            raise ValueError("query must not be empty")
        if baseline_k < 1:
            raise ValueError("baseline_k must be >= 1")
        if expanded_k < baseline_k:
            raise ValueError(
                "expanded_k must be >= baseline_k"
            )

        start = time.perf_counter()
        baseline_results = self._search(
            query,
            baseline_k,
            expected_platform=expected_platform,
            expected_service=expected_service,
        )
        retrieval_latency_ms = (
            time.perf_counter() - start
        ) * 1000.0

        has_ground_truth = (
            expected_platform is not None
            and expected_service is not None
        )

        baseline_relevant_found: Optional[bool] = None
        baseline_first_relevant_rank: Optional[int] = None
        expanded_first_relevant_rank: Optional[int] = None

        if has_ground_truth:
            baseline_first_relevant_rank = (
                self._first_relevant_rank(baseline_results)
            )
            baseline_relevant_found = (
                baseline_first_relevant_rank is not None
            )

            if not baseline_relevant_found:
                expanded_results = self._search(
                    query,
                    expanded_k,
                    expected_platform=expected_platform,
                    expected_service=expected_service,
                )
                expanded_first_relevant_rank = (
                    self._first_relevant_rank(expanded_results)
                )

            # A retrieval can contain the expected service and still expose
            # a chunking-quality problem (for example, an extremely short or
            # fragmented chunk). Keep that evidence visible to Diagnosis.
            failure_detected = (
                not baseline_relevant_found
                or self._chunking_signal(baseline_results)
            )
        else:
            # In production we do not invent relevance. A complete lack of
            # retrieval or a clearly broken/tiny chunk is enough to flag the
            # run for review; otherwise Diagnosis receives "insufficient
            # evidence" until feedback/judge evidence is available.
            failure_detected = (
                len(baseline_results) == 0
                or self._chunking_signal(baseline_results)
            )

        report: Dict[str, Any] = {
            "original_query": query,
            "baseline_k": baseline_k,
            "failure_detected": failure_detected,
            "baseline_relevant_found": baseline_relevant_found,
            "baseline_first_relevant_rank": (
                baseline_first_relevant_rank
            ),
            "expanded_first_relevant_rank": (
                expanded_first_relevant_rank
            ),
            "chunking_signal": self._chunking_signal(
                baseline_results
            ),
            "retrieval_latency_ms": round(
                retrieval_latency_ms, 3
            ),
            "retrieved_results": baseline_results,
        }

        if rewritten_query:
            rewritten_query = str(rewritten_query).strip()
            rewritten_results = self._search(
                rewritten_query,
                baseline_k,
                expected_platform=expected_platform,
                expected_service=expected_service,
            )

            probe: Dict[str, Any] = {
                "rewritten_query": rewritten_query,
                "rewritten_first_relevant_rank": None,
                "rewrite_probe_improved": None,
            }

            if has_ground_truth:
                rewritten_rank = self._first_relevant_rank(
                    rewritten_results
                )
                probe["rewritten_first_relevant_rank"] = (
                    rewritten_rank
                )

                if (
                    baseline_first_relevant_rank is None
                    and rewritten_rank is not None
                ):
                    improved = True
                elif rewritten_rank is None:
                    improved = False
                else:
                    improved = (
                        baseline_first_relevant_rank is not None
                        and rewritten_rank
                        < baseline_first_relevant_rank
                    )

                probe["rewrite_probe_improved"] = improved

            report["diagnostic_probe"] = probe

        self._append_log(
            {
                "timestamp": datetime.now(
                    timezone.utc
                ).isoformat(),
                "monitoring_report": report,
            }
        )
        return report

    def _append_log(self, payload: Dict[str, Any]) -> None:
        with self.log_path.open(
            "a",
            encoding="utf-8",
        ) as handle:
            handle.write(
                json.dumps(
                    payload,
                    ensure_ascii=False,
                )
                + "\n"
            )
