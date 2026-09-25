"""Validation Agent for RAGOps.

Compares BEFORE vs AFTER retrieval/RAG runs and returns one of:
IMPROVED, SAME, WORSE.

The current project validation is retrieval-first:
Recall@K -> Reciprocal Rank -> Precision@K.
An optional judge_score can be included later for answer-level evaluation.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Dict, Iterable, Optional


@dataclass
class RunMetrics:
    recall_at_k: float
    precision_at_k: float
    reciprocal_rank: float
    judge_score: Optional[float]
    latency_seconds: float


class ValidationAgent:
    """Validate an optimized candidate against the baseline."""

    def __init__(
        self,
        min_judge_gain: float = 0.5,
        latency_tolerance_seconds: float = 2.0,
    ) -> None:
        self.min_judge_gain = min_judge_gain
        self.latency_tolerance_seconds = latency_tolerance_seconds

    @staticmethod
    def retrieval_metrics(
        retrieved_results: Iterable[Dict[str, Any]],
        expected_platform: Optional[str] = None,
        expected_service: Optional[str] = None,
    ) -> Dict[str, float]:
        results = list(retrieved_results)
        relevant_count = 0
        first_relevant_rank: Optional[int] = None

        for rank, item in enumerate(results, start=1):
            if "relevant" in item:
                relevant = bool(item["relevant"])
            else:
                platform_ok = (
                    expected_platform is None
                    or item.get("platform") == expected_platform
                )
                service_ok = (
                    expected_service is None
                    or item.get("service") == expected_service
                )
                relevant = platform_ok and service_ok

            if relevant:
                relevant_count += 1
                if first_relevant_rank is None:
                    first_relevant_rank = rank

        return {
            "recall_at_k": 1.0 if relevant_count else 0.0,
            "precision_at_k": (
                relevant_count / len(results) if results else 0.0
            ),
            "reciprocal_rank": (
                1.0 / first_relevant_rank
                if first_relevant_rank is not None
                else 0.0
            ),
        }

    def build_metrics(
        self,
        run: Dict[str, Any],
        expected_platform: Optional[str] = None,
        expected_service: Optional[str] = None,
    ) -> RunMetrics:
        retrieval = self.retrieval_metrics(
            run.get("retrieved_results", []),
            expected_platform=expected_platform,
            expected_service=expected_service,
        )
        return RunMetrics(
            **retrieval,
            judge_score=run.get("judge_score"),
            latency_seconds=float(run.get("latency_seconds", 0.0)),
        )

    def validate(
        self,
        before_run: Dict[str, Any],
        after_run: Dict[str, Any],
        expected_platform: Optional[str] = None,
        expected_service: Optional[str] = None,
    ) -> Dict[str, Any]:
        before = self.build_metrics(
            before_run, expected_platform, expected_service
        )
        after = self.build_metrics(
            after_run, expected_platform, expected_service
        )

        delta = {
            "recall_at_k": after.recall_at_k - before.recall_at_k,
            "precision_at_k": after.precision_at_k - before.precision_at_k,
            "reciprocal_rank": (
                after.reciprocal_rank - before.reciprocal_rank
            ),
            "judge_score": None,
            "latency_seconds": (
                after.latency_seconds - before.latency_seconds
            ),
        }

        if (
            before.judge_score is not None
            and after.judge_score is not None
        ):
            delta["judge_score"] = (
                after.judge_score - before.judge_score
            )

        # Retrieval-first priority:
        # 1) Recall@K, 2) first relevant rank (RR), 3) Precision@K.
        if after.recall_at_k != before.recall_at_k:
            verdict = (
                "IMPROVED"
                if after.recall_at_k > before.recall_at_k
                else "WORSE"
            )
        elif after.reciprocal_rank != before.reciprocal_rank:
            verdict = (
                "IMPROVED"
                if after.reciprocal_rank > before.reciprocal_rank
                else "WORSE"
            )
        elif after.precision_at_k != before.precision_at_k:
            verdict = (
                "IMPROVED"
                if after.precision_at_k > before.precision_at_k
                else "WORSE"
            )
        elif delta["judge_score"] is not None:
            if delta["judge_score"] >= self.min_judge_gain:
                verdict = "IMPROVED"
            elif delta["judge_score"] <= -self.min_judge_gain:
                verdict = "WORSE"
            else:
                verdict = "SAME"
        else:
            verdict = "SAME"

        # Do not accept a quality gain if it causes an excessive latency cost.
        excessive_latency = (
            delta["latency_seconds"] > self.latency_tolerance_seconds
        )
        if verdict == "IMPROVED" and excessive_latency:
            verdict = "SAME"

        recommendation = (
            "ACCEPT_OPTIMIZED"
            if verdict == "IMPROVED"
            else "RETAIN_BASELINE"
        )

        return {
            "verdict": verdict,
            "recommendation": recommendation,
            "before": asdict(before),
            "after": asdict(after),
            "delta": delta,
            "answer_comparison": {
                "before": before_run.get("answer", ""),
                "after": after_run.get("answer", ""),
            },
        }
