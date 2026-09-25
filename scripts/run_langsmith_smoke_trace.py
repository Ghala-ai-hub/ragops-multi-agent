"""Send one safe LangGraph smoke trace to LangSmith.

This script intentionally uses offline/fake retrieval data:
- no OpenAI call
- no FAISS rebuild
- no corpus modification
- no candidate promotion

Prerequisites in local .env:
    LANGSMITH_TRACING=true
    LANGSMITH_API_KEY=<your private key>
    LANGSMITH_PROJECT=ragops-multi-agent
"""
from __future__ import annotations

import os

from dotenv import load_dotenv
from langsmith import Client

from action_executor import ApprovedActionExecutor
from diagnosis_agent import DiagnosisAgent
from langgraph_workflow import LangGraphRAGOps
from optimization_agent import OptimizationAgent


load_dotenv()


def _require_langsmith_config() -> None:
    tracing = os.getenv(
        "LANGSMITH_TRACING", ""
    ).strip().lower()
    api_key = os.getenv(
        "LANGSMITH_API_KEY", ""
    ).strip()
    project = os.getenv(
        "LANGSMITH_PROJECT", ""
    ).strip()

    if tracing not in {"true", "1", "yes"}:
        raise RuntimeError(
            "Set LANGSMITH_TRACING=true in your local .env."
        )
    if not api_key:
        raise RuntimeError(
            "Set LANGSMITH_API_KEY in your local .env. "
            "Do not commit or paste the key into chat."
        )
    if not project:
        raise RuntimeError(
            "Set LANGSMITH_PROJECT=ragops-multi-agent "
            "in your local .env."
        )


class FakeMonitoring:
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


def run_candidate(query, top_k):
    retrieved = [
        {
            "rank": i,
            "platform": "balady",
            "service": f"other_{i}",
            "relevant": False,
        }
        for i in range(1, min(top_k, 5) + 1)
    ]

    if top_k >= 6:
        retrieved.append(
            {
                "rank": 6,
                "platform": "balady",
                "service": "commercial_license_renewal",
                "relevant": True,
            }
        )

    return {
        "query": query,
        "top_k": top_k,
        "retrieved_results": retrieved,
        "latency_seconds": 0.02,
    }


def main() -> None:
    _require_langsmith_config()

    executor = ApprovedActionExecutor(
        run_candidate=run_candidate,
        default_k=4,
    )

    workflow = LangGraphRAGOps(
        monitoring_agent=FakeMonitoring(),
        diagnosis_agent=DiagnosisAgent(),
        optimization_agent=OptimizationAgent(),
        action_executor=executor,
    )

    before_run = {
        "query": "LangSmith observability smoke test",
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

    state = workflow.invoke(
        {
            "query": "LangSmith observability smoke test",
            "before_run": before_run,
            "expected_platform": "balady",
            "expected_service": "commercial_license_renewal",
            "trace": [],
        },
        thread_id="langsmith-smoke-test",
    )

    assert state["final_status"] == "IMPROVED"

    # LangSmith tracing is asynchronous. Flush before this short-lived
    # process exits so the trace reaches the service.
    Client().flush()

    print(
        "LangSmith smoke trace sent successfully. "
        "Project: "
        + os.environ["LANGSMITH_PROJECT"]
    )
    print(
        "Workflow result: "
        + state["final_status"]
    )


if __name__ == "__main__":
    main()
