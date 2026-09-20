"""Offline contract tests for Monitoring -> Diagnosis.

Uses a fake vector store so no OpenAI key/network is required.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Dict, List

from diagnosis_agent import DiagnosisAgent
from monitoring_agent import (
    DEFAULT_BASELINE_K,
    MonitoringAgent,
)


@dataclass
class FakeDoc:
    page_content: str
    metadata: Dict[str, object]


class FakeVectorStore:
    def __init__(
        self,
        responses: Dict[str, List[FakeDoc]],
    ) -> None:
        self.responses = responses

    def similarity_search_with_score(
        self,
        query: str,
        k: int,
    ):
        docs = self.responses.get(query, [])
        return [
            (doc, float(index + 1))
            for index, doc in enumerate(docs[:k])
        ]


def doc(
    platform: str,
    service: str,
    text: str = "x" * 160,
) -> FakeDoc:
    return FakeDoc(
        page_content=text,
        metadata={
            "platform": platform,
            "service": service,
            "source": f"{platform}/{service}/content_final.md",
            "chunk_index": 0,
        },
    )


def run_tests() -> None:
    assert DEFAULT_BASELINE_K == 4

    with TemporaryDirectory() as temp_dir:
        log_path = Path(temp_dir) / "monitoring.jsonl"

        # Healthy baseline: relevant service is inside Top-4.
        store = FakeVectorStore(
            {
                "healthy": [
                    doc("balady", "building_permit_issuance"),
                    doc("balady", "other"),
                ]
            }
        )
        monitor = MonitoringAgent(store, log_path=log_path)
        diagnosis = DiagnosisAgent()

        healthy_report = monitor.build_monitoring_report(
            "healthy",
            expected_platform="balady",
            expected_service="building_permit_issuance",
        )
        healthy = diagnosis.diagnose(healthy_report)
        assert healthy["recommended_action"] == "none"

        # Top-K: correct service is rank 6, outside baseline Top-4.
        topk_docs = [
            doc("balady", f"other_{i}")
            for i in range(5)
        ] + [
            doc("balady", "commercial_license_renewal")
        ]
        store.responses["topk"] = topk_docs
        topk_report = monitor.build_monitoring_report(
            "topk",
            expected_platform="balady",
            expected_service="commercial_license_renewal",
            expanded_k=10,
        )
        topk = diagnosis.diagnose(topk_report)
        assert topk["issue_type"] == "Top-K"
        assert topk["recommended_k"] == 6

        # Query mismatch: original misses; rewritten query retrieves rank 1.
        store.responses["mismatch"] = [
            doc("najiz", f"other_{i}")
            for i in range(4)
        ]
        store.responses["better wording"] = [
            doc("najiz", "enforcement_request"),
            doc("najiz", "other"),
        ]
        mismatch_report = monitor.build_monitoring_report(
            "mismatch",
            expected_platform="najiz",
            expected_service="enforcement_request",
            rewritten_query="better wording",
        )
        mismatch = diagnosis.diagnose(
            mismatch_report,
            mismatch_report["diagnostic_probe"],
        )
        assert mismatch["issue_type"] == "Query Mismatch"
        assert mismatch["recommended_action"] == "rewrite_query"

        # Production mode: no ground truth is invented.
        production_report = monitor.build_monitoring_report(
            "healthy"
        )
        assert production_report[
            "baseline_relevant_found"
        ] is None
        production = diagnosis.diagnose(production_report)
        assert production["recommended_action"] == "needs_review"

        # Chunking signal: a clearly tiny chunk is observable evidence.
        store.responses["tiny"] = [
            doc("sakani", "online_financing", text="قصير")
        ]
        tiny_report = monitor.build_monitoring_report(
            "tiny",
            expected_platform="sakani",
            expected_service="online_financing",
        )
        tiny = diagnosis.diagnose(tiny_report)
        assert tiny["issue_type"] == "Chunking Quality"

    print("Monitoring -> Diagnosis contract tests passed.")


if __name__ == "__main__":
    run_tests()
