"""Offline LangGraph orchestration tests for RAGOps.

Tests graph routing without OpenAI/network access.
"""
from __future__ import annotations

from action_executor import ApprovedActionExecutor
from diagnosis_agent import DiagnosisAgent
from langgraph_workflow import LangGraphRAGOps
from optimization_agent import OptimizationAgent


def result(rank, platform, service):
    return {
        "rank": rank,
        "platform": platform,
        "service": service,
        "relevant": (
            service == "commercial_license_renewal"
        ),
    }


class FakeMonitoring:
    def __init__(self, report):
        self.report = report

    def build_monitoring_report(
        self,
        query,
        **kwargs,
    ):
        return dict(self.report)


def run_candidate(query, top_k):
    retrieved = [
        result(i, "balady", f"other_{i}")
        for i in range(1, min(top_k, 5) + 1)
    ]
    if top_k >= 6:
        retrieved.append(
            result(
                6,
                "balady",
                "commercial_license_renewal",
            )
        )
    return {
        "query": query,
        "top_k": top_k,
        "retrieved_results": retrieved,
        "latency_seconds": 0.02,
    }


def run_tests():
    monitoring_report = {
        "original_query": "top-k query",
        "baseline_k": 4,
        "failure_detected": True,
        "baseline_relevant_found": False,
        "baseline_first_relevant_rank": None,
        "expanded_first_relevant_rank": 6,
        "chunking_signal": False,
        "retrieved_results": [],
    }

    before_run = {
        "query": "top-k query",
        "top_k": 4,
        "retrieved_results": [
            {
                "rank": i,
                "platform": "balady",
                "service": f"other_{i}",
                "relevant": False,
            }
            for i in range(1, 5)
        ],
        "latency_seconds": 0.01,
    }

    executor = ApprovedActionExecutor(
        run_candidate=run_candidate,
        default_k=4,
    )

    workflow = LangGraphRAGOps(
        monitoring_agent=FakeMonitoring(
            monitoring_report
        ),
        diagnosis_agent=DiagnosisAgent(),
        optimization_agent=OptimizationAgent(),
        action_executor=executor,
    )

    state = workflow.invoke(
        {
            "query": "top-k query",
            "before_run": before_run,
            "expected_platform": "balady",
            "expected_service": (
                "commercial_license_renewal"
            ),
            "trace": [],
        },
        thread_id="langgraph-topk-test",
    )

    assert (
        state["diagnosis_report"]["issue_type"]
        == "Top-K"
    )
    assert (
        state["optimization_proposal"]["action"]
        == "change_top_k"
    )
    assert (
        state["approval_result"]["approval_status"]
        == "auto_approved"
    )
    assert state["final_status"] == "IMPROVED"

    stages = [
        item["stage"]
        for item in state["trace"]
    ]
    assert stages == [
        "monitoring",
        "diagnosis",
        "optimization",
        "approval",
        "execution",
        "validation",
    ]


    # 2) Healthy baseline: graph stops after Diagnosis with no optimization.
    healthy_report = {
        "original_query": "healthy query",
        "baseline_k": 4,
        "failure_detected": False,
        "baseline_relevant_found": True,
        "baseline_first_relevant_rank": 1,
        "expanded_first_relevant_rank": None,
        "chunking_signal": False,
        "retrieved_results": [
            {
                "rank": 1,
                "platform": "balady",
                "service": "commercial_license_renewal",
                "relevant": True,
            }
        ],
    }
    healthy_workflow = LangGraphRAGOps(
        monitoring_agent=FakeMonitoring(healthy_report),
        diagnosis_agent=DiagnosisAgent(),
        optimization_agent=OptimizationAgent(),
        action_executor=executor,
    )
    healthy_before = {
        "query": "healthy query",
        "top_k": 4,
        "retrieved_results": healthy_report["retrieved_results"],
        "latency_seconds": 0.01,
    }
    healthy_state = healthy_workflow.invoke(
        {
            "query": "healthy query",
            "before_run": healthy_before,
            "expected_platform": "balady",
            "expected_service": "commercial_license_renewal",
            "trace": [],
        },
        thread_id="langgraph-healthy-test",
    )
    assert healthy_state["final_status"] == "NO_ACTION_REQUIRED"
    assert "optimization_proposal" not in healthy_state
    assert "execution_result" not in healthy_state
    assert [
        item["stage"]
        for item in healthy_state["trace"]
    ] == ["monitoring", "diagnosis"]

    print(
        "LangGraph RAGOps orchestration tests passed "
        "(Top-K + healthy baseline)."
    )


if __name__ == "__main__":
    run_tests()
