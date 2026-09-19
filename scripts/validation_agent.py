"""Validation Agent for RAGOps.

Compares a baseline RAG run with an optimized candidate run using retrieval
quality, answer quality, and latency. This module does not apply optimizations;
it only validates their measured impact.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Dict, Iterable, Optional


@dataclass
class RunMetrics:
    recall_at_k: float
    precision_at_k: float
    reciprocal_rank: float
    judge_score: Optional[float]
    latency_seconds: float


class ValidationAgent:
    """Compare BEFORE and AFTER RAG runs and return a measurable verdict."""

    def __init__(self, min_judge_gain: float = 0.5, latency_tolerance: float = 2.0):
        self.min_judge_gain = min_judge_gain
        self.latency_tolerance = latency_tolerance

    @staticmethod
    def retrieval_metrics(
        retrieved_results: Iterable[Dict[str, Any]],
        expected_platform: Optional[str] = None,
        expected_service: Optional[str] = None,
    ) -> Dict[str, float]:
        results = list(retrieved_results)
        relevant_count = 0
        first_relevant_rank = None

        for rank, item in enumerate(results, start=1):
            # Prefer an explicit relevance label when the evaluator provides one.
            if "relevant" in item:
                relevant = bool(item["relevant"])
            else:
                platform_ok = expected_platform is None or item.get("platform") == expected_platform
                service_ok = expected_service is None or item.get("service") == expected_service
                relevant = platform_ok and service_ok

            if relevant:
                relevant_count += 1
                if first_relevant_rank is None:
                    first_relevant_rank = rank

        recall_at_k = 1.0 if relevant_count else 0.0
        precision_at_k = relevant_count / len(results) if results else 0.0
        reciprocal_rank = 1.0 / first_relevant_rank if first_relevant_rank else 0.0
        return {
            "recall_at_k": recall_at_k,
            "precision_at_k": precision_at_k,
            "reciprocal_rank": reciprocal_rank,
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
        before = self.build_metrics(before_run, expected_platform, expected_service)
        after = self.build_metrics(after_run, expected_platform, expected_service)

        delta = {
            "recall_at_k": after.recall_at_k - before.recall_at_k,
            "precision_at_k": after.precision_at_k - before.precision_at_k,
            "reciprocal_rank": after.reciprocal_rank - before.reciprocal_rank,
            "judge_score": None,
            "latency_seconds": after.latency_seconds - before.latency_seconds,
        }
        if before.judge_score is not None and after.judge_score is not None:
            delta["judge_score"] = after.judge_score - before.judge_score

        quality_improved = any(
            delta[key] > 0
            for key in ("recall_at_k", "precision_at_k", "reciprocal_rank")
        )
        if delta["judge_score"] is not None:
            quality_improved = quality_improved or delta["judge_score"] >= self.min_judge_gain

        quality_worse = any(
            delta[key] < 0
            for key in ("recall_at_k", "precision_at_k", "reciprocal_rank")
        )
        if delta["judge_score"] is not None:
            quality_worse = quality_worse or delta["judge_score"] <= -self.min_judge_gain

        excessive_latency = delta["latency_seconds"] > self.latency_tolerance

        if quality_worse:
            verdict = "WORSE"
            recommendation = "RETAIN_BASELINE"
        elif quality_improved and not excessive_latency:
            verdict = "IMPROVED"
            recommendation = "ACCEPT_OPTIMIZED"
        else:
            verdict = "NO_MEANINGFUL_CHANGE"
            recommendation = "RETAIN_BASELINE"

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
