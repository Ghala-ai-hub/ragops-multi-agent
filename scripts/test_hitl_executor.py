"""Offline tests for HITL routing and approved action execution.

No OpenAI key, network, or real vector store is required.
"""
from __future__ import annotations

from action_executor import ApprovedActionExecutor
from hitl import route_approval


def fake_run_candidate(query: str, top_k: int):
    return {
        "query": query,
        "top_k": top_k,
        "retrieved_results": [],
        "latency_seconds": 0.01,
    }


def fake_rewrite(query: str) -> str:
    return f"rewritten: {query}"


def fake_rechunk(parameters):
    return {
        "after_run": {
            "query": parameters["original_query"],
            "top_k": parameters.get("baseline_k", 4),
            "retrieved_results": [],
            "latency_seconds": 0.02,
        },
        "action_result": {
            "candidate_index": "vector_store/candidates/test",
            "non_destructive": True,
        },
    }


def run_tests() -> None:
    executor = ApprovedActionExecutor(
        run_candidate=fake_run_candidate,
        default_k=4,
        rewrite_function=fake_rewrite,
        rechunk_candidate=fake_rechunk,
    )

    # 1) Low-impact Top-K is auto-approved and executed.
    topk_proposal = {
        "action": "change_top_k",
        "parameters": {
            "original_query": "top-k test",
            "baseline_k": 4,
            "new_k": 6,
        },
    }
    topk_approval = route_approval(topk_proposal)
    assert topk_approval["approval_status"] == "auto_approved"
    assert topk_approval["execution_allowed"] is True
    topk_result = executor(topk_approval)
    assert topk_result["action_result"]["applied_k"] == 6
    assert topk_result["after_run"]["top_k"] == 6

    # 2) Low-impact rewrite is auto-approved and executed.
    rewrite_proposal = {
        "action": "rewrite_query",
        "parameters": {
            "original_query": "original wording",
            "baseline_k": 4,
        },
    }
    rewrite_approval = route_approval(rewrite_proposal)
    assert rewrite_approval["approval_status"] == "auto_approved"
    rewrite_result = executor(rewrite_approval)
    assert rewrite_result["action_result"]["rewritten_query"] == (
        "rewritten: original wording"
    )
    assert rewrite_result["after_run"]["top_k"] == 4

    # 3) High-impact rechunk waits for an explicit human decision.
    rechunk_proposal = {
        "action": "rechunk_and_reindex",
        "parameters": {
            "original_query": "chunking test",
            "baseline_k": 4,
            "chunk_size": 500,
            "chunk_overlap": 100,
        },
    }
    pending = route_approval(rechunk_proposal)
    assert pending["approval_status"] == "pending_human_approval"
    assert pending["execution_allowed"] is False

    # Executor must refuse an unapproved structural action.
    try:
        executor(pending)
        raise AssertionError("pending action should not execute")
    except PermissionError:
        pass

    # 4) Human rejection keeps execution disabled.
    rejected = route_approval(
        rechunk_proposal,
        human_decision="reject",
    )
    assert rejected["approval_status"] == "rejected"
    assert rejected["execution_allowed"] is False

    # 5) Human approval permits non-destructive candidate execution.
    approved = route_approval(
        rechunk_proposal,
        human_decision="approve",
    )
    assert approved["approval_status"] == "approved"
    assert approved["execution_allowed"] is True
    rechunk_result = executor(approved)
    assert rechunk_result["action_result"]["non_destructive"] is True
    assert (
        rechunk_result["action_result"]["candidate_index"]
        == "vector_store/candidates/test"
    )

    print("HITL + Action Executor tests passed.")


if __name__ == "__main__":
    run_tests()
