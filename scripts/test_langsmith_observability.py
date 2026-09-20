"""Offline test for LangSmith-facing LangGraph config.

No LangSmith API key or network is required. This only verifies that graph
invocations expose stable tags and metadata that LangSmith will capture when
tracing is enabled through environment variables.
"""
from __future__ import annotations

from langgraph_workflow import LangGraphRAGOps


def run_tests():
    config = LangGraphRAGOps.config(
        "observability-test",
        tags=["ragops", "test"],
        metadata={
            "expected_platform": "balady",
            "expected_service": "building_permit_issuance",
        },
    )

    assert (
        config["configurable"]["thread_id"]
        == "observability-test"
    )
    assert config["tags"] == ["ragops", "test"]
    assert (
        config["metadata"]["workflow"]
        == "ragops_multi_agent"
    )
    assert config["metadata"]["baseline_k"] == 4
    assert (
        config["metadata"]["expected_platform"]
        == "balady"
    )
    assert (
        config["metadata"]["expected_service"]
        == "building_permit_issuance"
    )

    print("LangSmith observability config tests passed.")


if __name__ == "__main__":
    run_tests()
