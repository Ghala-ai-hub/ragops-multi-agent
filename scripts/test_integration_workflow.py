"""Tests for the RAGOps shared integration workflow."""

from scripts.integration_workflow import RAGOpsWorkflow
from scripts.validation_agent import ValidationAgent


class FakeMonitoringAgent:
    def build_monitoring_report(self, query, **kwargs):
        return {
            "original_query": query,
            "baseline_k": 4,
            "failure_detected": True,
            "baseline_relevant_found": False,
            "baseline_first_relevant_rank": None,
            "expanded_first_relevant_rank": 6,
            "chunking_signal": False,
            "retrieved_results": [],
        }


class FakeDiagnosisAgent:
    def diagnose(self, monitoring_report, diagnostic_probe=None):
        return {
            "issue_type": "Query Mismatch",
            "original_query": monitoring_report["original_query"],
            "recommended_action": "rewrite_query",
            "confidence": 0.95,
            "reason": "A rewritten query is expected to improve retrieval.",
        }


class HealthyDiagnosisAgent:
    def diagnose(self, monitoring_report, diagnostic_probe=None):
        return {
            "issue_type": None,
            "original_query": monitoring_report["original_query"],
            "recommended_action": "none",
            "confidence": 0.90,
            "reason": "Baseline retrieval is healthy.",
        }


BEFORE_RUN = {
    "retrieved_results": [
        {"rank": 1, "relevant": False},
        {"rank": 2, "relevant": False},
        {"rank": 3, "relevant": False},
        {"rank": 4, "relevant": False},
    ],
    "answer": "المعلومات غير كافية.",
    "judge_score": 1.0,
    "latency_seconds": 1.0,
}

AFTER_RUN = {
    "retrieved_results": [
        {"rank": 1, "relevant": True},
        {"rank": 2, "relevant": True},
        {"rank": 3, "relevant": True},
        {"rank": 4, "relevant": False},
    ],
    "answer": "إجابة محسنة مبنية على الأدلة المسترجعة.",
    "judge_score": 5.0,
    "latency_seconds": 1.8,
}


def successful_executor(approved_proposal):
    assert approved_proposal["execution_allowed"] is True
    return {
        "action_result": {"status": "applied"},
        "after_run": AFTER_RUN,
    }


def forbidden_executor(_approved_proposal):
    raise AssertionError("Executor must not run after rejection")


def test_approved_flow():
    workflow = RAGOpsWorkflow(
        monitoring_agent=FakeMonitoringAgent(),
        diagnosis_agent=FakeDiagnosisAgent(),
        action_executor=successful_executor,
        validation_agent=ValidationAgent(),
    )
    state = workflow.run(
        query="كيف أجدد رخصة بلدي؟",
        human_decision="approve",
        before_run=BEFORE_RUN,
    )
    assert state["approval_result"]["approval_status"] == "approved"
    assert state["final_status"] == "IMPROVED"
    assert state["validation_result"]["recommendation"] == "ACCEPT_OPTIMIZED"
    assert [step["stage"] for step in state["trace"]] == [
        "monitoring",
        "diagnosis",
        "optimization",
        "human_approval",
        "execution",
        "validation",
    ]


def test_rejected_flow():
    workflow = RAGOpsWorkflow(
        monitoring_agent=FakeMonitoringAgent(),
        diagnosis_agent=FakeDiagnosisAgent(),
        action_executor=forbidden_executor,
    )
    state = workflow.run(
        query="كيف أجدد رخصة بلدي؟",
        human_decision="reject",
        before_run=BEFORE_RUN,
    )
    assert state["final_status"] == "REJECTED"
    assert state["final_run"] == BEFORE_RUN
    assert "execution_result" not in state
    assert "validation_result" not in state


def test_healthy_flow_skips_optimization():
    workflow = RAGOpsWorkflow(
        monitoring_agent=FakeMonitoringAgent(),
        diagnosis_agent=HealthyDiagnosisAgent(),
        action_executor=forbidden_executor,
    )
    state = workflow.run(
        query="استعلام سليم",
        human_decision="approve",
        before_run=BEFORE_RUN,
    )
    assert state["final_status"] == "NO_ACTION_REQUIRED"
    assert "optimization_proposal" not in state
    assert "approval_result" not in state


if __name__ == "__main__":
    test_approved_flow()
    test_rejected_flow()
    test_healthy_flow_skips_optimization()
    print("Integration workflow tests passed: APPROVE, REJECT, and healthy-baseline paths.")
