"""Offline test for LangGraph native HITL interrupt/resume.

Validates the high-impact Chunking Quality route:
Diagnosis -> Optimization -> interrupt for human approval -> resume ->
Execution -> Validation.

No OpenAI key, embeddings, FAISS build, or network is required.
"""
from __future__ import annotations

from action_executor import ApprovedActionExecutor
from diagnosis_agent import DiagnosisAgent
from langgraph_workflow import LangGraphRAGOps
from optimization_agent import OptimizationAgent


class FakeMonitoring:
    def build_monitoring_report(self, query, **kwargs):
        return {
            "original_query": query,
            "baseline_k": 4,
            "failure_detected": True,
            "baseline_relevant_found": True,
            "baseline_first_relevant_rank": 4,
            "expanded_first_relevant_rank": None,
            "chunking_signal": True,
            "retrieved_results": [],
        }


def run_candidate(query: str, top_k: int):
    # This callback is unused for rechunk but required by the executor.
    return {
        "query": query,
        "top_k": top_k,
        "retrieved_results": [],
        "latency_seconds": 0.01,
    }


def fake_rechunk(parameters):
    return {
        "after_run": {
            "query": parameters["original_query"],
            "top_k": parameters.get("baseline_k", 4),
            "retrieved_results": [
                {
                    "rank": 1,
                    "platform": "sakani",
                    "service": "online_financing",
                    "relevant": True,
                },
                {
                    "rank": 2,
                    "platform": "sakani",
                    "service": "other",
                    "relevant": False,
                },
            ],
            "answer": "",
            "judge_score": None,
            "latency_seconds": 0.02,
        },
        "action_result": {
            "candidate_index_path": (
                "vector_store/candidates/"
                "rechunk_750_150_test"
            ),
            "non_destructive": True,
            "chunk_size": 750,
            "chunk_overlap": 150,
        },
    }


def run_tests():
    executor = ApprovedActionExecutor(
        run_candidate=run_candidate,
        default_k=4,
        rechunk_candidate=fake_rechunk,
    )

    workflow = LangGraphRAGOps(
        monitoring_agent=FakeMonitoring(),
        diagnosis_agent=DiagnosisAgent(),
        optimization_agent=OptimizationAgent(),
        action_executor=executor,
    )

    before_run = {
        "query": "chunking test",
        "top_k": 4,
        "retrieved_results": [
            {
                "rank": 1,
                "platform": "sakani",
                "service": "other_1",
                "relevant": False,
            },
            {
                "rank": 2,
                "platform": "sakani",
                "service": "other_2",
                "relevant": False,
            },
            {
                "rank": 3,
                "platform": "sakani",
                "service": "other_3",
                "relevant": False,
            },
            {
                "rank": 4,
                "platform": "sakani",
                "service": "online_financing",
                "relevant": True,
            },
        ],
        "answer": "",
        "judge_score": None,
        "latency_seconds": 0.01,
    }

    thread_id = "langgraph-hitl-chunking-test"

    interrupted = workflow.invoke(
        {
            "query": "chunking test",
            "before_run": before_run,
            "expected_platform": "sakani",
            "expected_service": "online_financing",
            "trace": [],
        },
        thread_id=thread_id,
    )

    assert "__interrupt__" in interrupted
    assert interrupted["__interrupt__"]

    interrupt_payload = interrupted["__interrupt__"][0].value
    assert (
        interrupt_payload["type"]
        == "human_approval_required"
    )
    assert (
        interrupt_payload["action"]
        == "rechunk_and_reindex"
    )

    resumed = workflow.resume(
        "approve",
        thread_id=thread_id,
    )

    assert (
        resumed["approval_result"]["approval_status"]
        == "approved"
    )
    assert (
        resumed["approval_result"]["execution_allowed"]
        is True
    )
    assert (
        resumed["execution_result"]["action_result"][
            "non_destructive"
        ]
        is True
    )
    assert (
        resumed["execution_result"]["action_result"][
            "chunk_size"
        ]
        == 750
    )
    assert (
        resumed["validation_result"]["verdict"]
        == "IMPROVED"
    )
    assert (
        resumed["validation_result"]["recommendation"]
        == "ACCEPT_OPTIMIZED"
    )
    assert resumed["final_status"] == "IMPROVED"

    stages = [
        item["stage"]
        for item in resumed["trace"]
    ]
    assert stages == [
        "monitoring",
        "diagnosis",
        "optimization",
        "approval",
        "execution",
        "validation",
    ]

    print("LangGraph native HITL interrupt/resume tests passed.")


if __name__ == "__main__":
    run_tests()
