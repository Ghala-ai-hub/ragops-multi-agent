"""Offline end-to-end contract test for the RAGOps workflow.

Covers the real project flow:
Monitoring evidence -> Diagnosis -> Optimization proposal -> HITL routing ->
Approved execution -> Validation -> final decision.

No OpenAI key, network, or real FAISS index is required.
"""
from __future__ import annotations

from action_executor import ApprovedActionExecutor
from diagnosis_agent import DiagnosisAgent
from integration_workflow import RAGOpsWorkflow
from optimization_agent import OptimizationAgent


def result(
    rank: int,
    platform: str,
    service: str,
):
    return {
        "rank": rank,
        "platform": platform,
        "service": service,
        "source": f"{platform}/{service}/content_final.md",
        "chunk_index": 0,
        "text": "example chunk",
    }


def before_irrelevant(query: str):
    return {
        "query": query,
        "top_k": 4,
        "retrieved_results": [
            result(i, "balady", f"other_{i}")
            for i in range(1, 5)
        ],
        "answer": "",
        "judge_score": None,
        "latency_seconds": 0.01,
    }


def run_candidate(query: str, top_k: int):
    # Query-rewrite candidate: relevant service becomes rank 1.
    if query == "better wording":
        retrieved = [
            result(1, "najiz", "enforcement_request"),
            result(2, "najiz", "other"),
        ]
    # Top-K candidate: relevant service exists only at rank 6.
    elif query == "top-k query" and top_k >= 6:
        retrieved = [
            result(i, "balady", f"other_{i}")
            for i in range(1, 6)
        ] + [
            result(
                6,
                "balady",
                "commercial_license_renewal",
            )
        ]
    else:
        retrieved = [
            result(i, "balady", f"other_{i}")
            for i in range(1, top_k + 1)
        ]

    return {
        "query": query,
        "top_k": top_k,
        "retrieved_results": retrieved,
        "answer": "",
        "judge_score": None,
        "latency_seconds": 0.02,
    }


def rechunk_candidate(parameters):
    # Simulate a non-destructive candidate index whose new chunking improves
    # the first relevant rank from 4 -> 1.
    return {
        "after_run": {
            "query": parameters["original_query"],
            "top_k": parameters.get("baseline_k", 4),
            "retrieved_results": [
                result(1, "sakani", "online_financing"),
                result(2, "sakani", "other"),
            ],
            "answer": "",
            "judge_score": None,
            "latency_seconds": 0.03,
        },
        "action_result": {
            "candidate_index": "vector_store/candidates/test_rechunk",
            "non_destructive": True,
        },
    }


def build_workflow():
    executor = ApprovedActionExecutor(
        run_candidate=run_candidate,
        default_k=4,
        rechunk_candidate=rechunk_candidate,
    )
    return RAGOpsWorkflow(
        diagnosis_agent=DiagnosisAgent(),
        optimization_agent=OptimizationAgent(),
        action_executor=executor,
    )


def run_tests() -> None:
    workflow = build_workflow()

    # 1) Top-K full flow: relevant service is rank 6, so K=4 -> K=6.
    topk_before = before_irrelevant("top-k query")
    topk_monitoring = {
        "original_query": "top-k query",
        "baseline_k": 4,
        "failure_detected": True,
        "baseline_relevant_found": False,
        "baseline_first_relevant_rank": None,
        "expanded_first_relevant_rank": 6,
        "chunking_signal": False,
        "retrieved_results": topk_before["retrieved_results"],
    }
    topk_state = workflow.run(
        query="top-k query",
        before_run=topk_before,
        monitoring_report=topk_monitoring,
        expected_platform="balady",
        expected_service="commercial_license_renewal",
    )
    assert topk_state["diagnosis_report"]["issue_type"] == "Top-K"
    assert (
        topk_state["approval_result"]["approval_status"]
        == "auto_approved"
    )
    assert (
        topk_state["execution_result"]["action_result"]["applied_k"]
        == 6
    )
    assert topk_state["validation_result"]["verdict"] == "IMPROVED"
    assert topk_state["final_status"] == "IMPROVED"

    # 2) Query mismatch full flow: rewrite improves retrieval to rank 1.
    mismatch_before = {
        "query": "mismatch query",
        "top_k": 4,
        "retrieved_results": [
            result(i, "najiz", f"other_{i}")
            for i in range(1, 5)
        ],
        "answer": "",
        "judge_score": None,
        "latency_seconds": 0.01,
    }
    mismatch_monitoring = {
        "original_query": "mismatch query",
        "baseline_k": 4,
        "failure_detected": True,
        "baseline_relevant_found": False,
        "baseline_first_relevant_rank": None,
        "expanded_first_relevant_rank": 7,
        "chunking_signal": False,
        "retrieved_results": mismatch_before["retrieved_results"],
        "diagnostic_probe": {
            "rewritten_query": "better wording",
            "rewrite_probe_improved": True,
            "rewritten_first_relevant_rank": 1,
        },
    }
    mismatch_state = workflow.run(
        query="mismatch query",
        before_run=mismatch_before,
        monitoring_report=mismatch_monitoring,
        expected_platform="najiz",
        expected_service="enforcement_request",
    )
    assert (
        mismatch_state["diagnosis_report"]["issue_type"]
        == "Query Mismatch"
    )
    assert (
        mismatch_state["optimization_proposal"]["parameters"][
            "rewritten_query"
        ]
        == "better wording"
    )
    assert (
        mismatch_state["approval_result"]["approval_status"]
        == "auto_approved"
    )
    assert (
        mismatch_state["validation_result"]["verdict"]
        == "IMPROVED"
    )

    # 3) Chunking is high-impact: no human decision -> no execution.
    chunk_before = {
        "query": "chunk query",
        "top_k": 4,
        "retrieved_results": [
            result(1, "sakani", "other_1"),
            result(2, "sakani", "other_2"),
            result(3, "sakani", "other_3"),
            result(4, "sakani", "online_financing"),
        ],
        "answer": "",
        "judge_score": None,
        "latency_seconds": 0.01,
    }
    chunk_monitoring = {
        "original_query": "chunk query",
        "baseline_k": 4,
        "failure_detected": True,
        "baseline_relevant_found": True,
        "baseline_first_relevant_rank": 4,
        "expanded_first_relevant_rank": None,
        "chunking_signal": True,
        "retrieved_results": chunk_before["retrieved_results"],
    }
    pending_state = workflow.run(
        query="chunk query",
        before_run=chunk_before,
        monitoring_report=chunk_monitoring,
        expected_platform="sakani",
        expected_service="online_financing",
    )
    assert pending_state["final_status"] == "PENDING_HUMAN_APPROVAL"
    assert "execution_result" not in pending_state

    # 4) Same structural action with human approval -> candidate -> validate.
    approved_state = workflow.run(
        query="chunk query",
        before_run=chunk_before,
        monitoring_report=chunk_monitoring,
        expected_platform="sakani",
        expected_service="online_financing",
        human_decision="approve",
    )
    assert (
        approved_state["approval_result"]["approval_status"]
        == "approved"
    )
    assert (
        approved_state["execution_result"]["action_result"][
            "non_destructive"
        ]
        is True
    )
    assert (
        approved_state["validation_result"]["verdict"]
        == "IMPROVED"
    )
    assert (
        approved_state["validation_result"]["recommendation"]
        == "ACCEPT_OPTIMIZED"
    )

    print("Full RAGOps integration workflow tests passed.")


if __name__ == "__main__":
    run_tests()
