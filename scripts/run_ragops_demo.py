"""Unified real-data demo entry point for the RAGOps project.

Runs the tested LangGraph workflow over the current FAISS evaluation index:

Baseline Retrieval
    -> Monitoring
    -> Diagnosis
    -> Optimization Proposal
    -> Approval / HITL
    -> Execution
    -> Validation

The default demo case is a verified Query Mismatch failure. Use
--all-failures to run all current Recall@4 baseline failures.

Safety:
- The active FAISS index is never overwritten.
- Current real failure cases use only low-impact actions.
- If a high-impact structural action is encountered, the LangGraph interrupt
  is shown and this demo stops without approving or executing it.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any, Dict, List

from dotenv import load_dotenv
from langchain_community.vectorstores import FAISS
from langchain_openai import OpenAIEmbeddings

from action_executor import ApprovedActionExecutor
from diagnosis_agent import DiagnosisAgent
from langgraph_workflow import LangGraphRAGOps
from monitoring_agent import MonitoringAgent
from optimization_agent import OptimizationAgent
from retrieval_run import build_retrieval_run


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATASET_PATH = PROJECT_ROOT / "evaluation" / "dataset_v2.json"
RETRIEVAL_RESULTS_PATH = (
    PROJECT_ROOT / "evaluation" / "retrieval_results_v2.json"
)
REWRITE_RESULTS_PATH = (
    PROJECT_ROOT / "evaluation" / "rewrite_probe_results.json"
)
VECTORSTORE_PATH = Path("vector_store") / "evaluation_index"

EMBEDDING_MODEL = "text-embedding-3-small"
BASELINE_K = 4
EXPANDED_K = 10
DEFAULT_CASE_ID = "balady_commercial_license_cancellation_002"


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _failure_ids(retrieval_results: Dict[str, Any]) -> List[str]:
    return [
        item["id"]
        for item in retrieval_results["results"]
        if float(item.get("recall_at_k", 0.0)) == 0.0
    ]


def _metrics_line(metrics: Dict[str, Any]) -> str:
    return (
        f"Recall@4={float(metrics.get('recall_at_k', 0.0)):.2f}, "
        f"Precision@4={float(metrics.get('precision_at_k', 0.0)):.2f}, "
        f"MRR={float(metrics.get('reciprocal_rank', 0.0)):.2f}"
    )


def _print_case_summary(
    *,
    query_id: str,
    item: Dict[str, Any],
    state: Dict[str, Any],
) -> None:
    diagnosis = state.get("diagnosis_report") or {}
    proposal = state.get("optimization_proposal") or {}
    approval = state.get("approval_result") or {}
    validation = state.get("validation_result") or {}

    print()
    print("=" * 100)
    print(f"CASE       : {query_id}")
    print(
        f"EXPECTED   : {item['platform']} / {item['service']}"
    )
    print(f"QUERY TYPE : {item.get('query_type')}")
    print(f"QUERY      : {item['query']}")
    print("-" * 100)
    print(
        "DIAGNOSIS  : "
        f"{diagnosis.get('issue_type')} "
        f"(action={diagnosis.get('recommended_action')})"
    )
    print(
        "PROPOSAL   : "
        f"{proposal.get('action', 'none')}"
    )
    print(
        "APPROVAL   : "
        f"{approval.get('approval_status', 'not_required')}"
    )

    if validation:
        print(
            "BEFORE     : "
            + _metrics_line(validation["before"])
        )
        print(
            "AFTER      : "
            + _metrics_line(validation["after"])
        )
        print(
            "VALIDATION : "
            f"{validation['verdict']} | "
            f"{validation['recommendation']}"
        )

    print(f"FINAL      : {state.get('final_status')}")

    trace = state.get("trace") or []
    if trace:
        print(
            "GRAPH      : "
            + " -> ".join(
                str(step.get("stage"))
                for step in trace
            )
        )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run the unified real-data LangGraph RAGOps demo."
        )
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--case-id",
        default=None,
        help=(
            "Run one dataset query id. "
            f"Default: {DEFAULT_CASE_ID}"
        ),
    )
    group.add_argument(
        "--all-failures",
        action="store_true",
        help="Run all current baseline Recall@4 failures.",
    )
    group.add_argument(
        "--list-failures",
        action="store_true",
        help="List current baseline Recall@4 failure ids and exit.",
    )
    return parser


def main() -> None:
    args = _build_parser().parse_args()
    load_dotenv()

    dataset = _load_json(DATASET_PATH)
    retrieval_results = _load_json(RETRIEVAL_RESULTS_PATH)
    rewrite_results = _load_json(REWRITE_RESULTS_PATH)

    dataset_by_id = {
        item["id"]: item
        for item in dataset
    }
    rewrite_by_id = {
        item["id"]: item
        for item in rewrite_results["results"]
    }
    failed_ids = _failure_ids(retrieval_results)

    if args.list_failures:
        print("Current baseline Recall@4 failures:")
        for query_id in failed_ids:
            item = dataset_by_id[query_id]
            print(
                f"- {query_id} | "
                f"{item['platform']} / {item['service']} | "
                f"{item.get('query_type')}"
            )
        return

    if args.all_failures:
        selected_ids = failed_ids
    else:
        selected_ids = [
            args.case_id or DEFAULT_CASE_ID
        ]

    missing = [
        query_id
        for query_id in selected_ids
        if query_id not in dataset_by_id
    ]
    if missing:
        raise KeyError(
            "Unknown dataset query id(s): "
            + ", ".join(missing)
        )

    print("Loading real FAISS evaluation index...")
    embeddings = OpenAIEmbeddings(
        model=EMBEDDING_MODEL
    )
    # FAISS native file I/O on Windows can fail on absolute paths that
    # contain non-ASCII characters. The project path may include Arabic
    # folder names, so load through an ASCII relative path from PROJECT_ROOT.
    original_cwd = Path.cwd()
    try:
        os.chdir(PROJECT_ROOT)
        vector_store = FAISS.load_local(
            str(VECTORSTORE_PATH),
            embeddings,
            allow_dangerous_deserialization=True,
        )
    finally:
        os.chdir(original_cwd)

    monitor = MonitoringAgent(vector_store)

    current_item: Dict[str, Any] = {}

    def run_candidate(query: str, top_k: int):
        return build_retrieval_run(
            vector_store,
            query,
            top_k,
            expected_platform=current_item["platform"],
            expected_service=current_item["service"],
        )

    executor = ApprovedActionExecutor(
        run_candidate=run_candidate,
        default_k=BASELINE_K,
    )

    workflow = LangGraphRAGOps(
        monitoring_agent=monitor,
        diagnosis_agent=DiagnosisAgent(),
        optimization_agent=OptimizationAgent(),
        action_executor=executor,
    )

    completed = 0
    improved = 0
    interrupted = 0

    for query_id in selected_ids:
        item = dataset_by_id[query_id]
        current_item.clear()
        current_item.update(item)

        rewrite_probe = rewrite_by_id.get(query_id) or {}
        rewritten_query = str(
            rewrite_probe.get("rewritten_query") or ""
        ).strip()

        before_run = build_retrieval_run(
            vector_store,
            item["query"],
            BASELINE_K,
            expected_platform=item["platform"],
            expected_service=item["service"],
        )

        monitoring_kwargs: Dict[str, Any] = {
            "baseline_k": BASELINE_K,
            "expanded_k": EXPANDED_K,
            "expected_platform": item["platform"],
            "expected_service": item["service"],
        }
        if rewritten_query:
            monitoring_kwargs["rewritten_query"] = (
                rewritten_query
            )

        state = workflow.invoke(
            {
                "query": item["query"],
                "before_run": before_run,
                "expected_platform": item["platform"],
                "expected_service": item["service"],
                "monitoring_kwargs": monitoring_kwargs,
                "trace": [],
            },
            thread_id=f"ragops-demo-{query_id}",
        )

        if state.get("__interrupt__"):
            interrupted += 1
            interrupt_value = (
                state["__interrupt__"][0].value
            )
            print()
            print("=" * 100)
            print(f"CASE       : {query_id}")
            print("FINAL      : HUMAN APPROVAL REQUIRED")
            print(
                "ACTION     : "
                f"{interrupt_value.get('action')}"
            )
            print(
                "REASON     : "
                f"{interrupt_value.get('reason')}"
            )
            print(
                "SAFE STOP  : No structural action was "
                "approved or executed."
            )
            continue

        completed += 1
        if state.get("final_status") == "IMPROVED":
            improved += 1

        _print_case_summary(
            query_id=query_id,
            item=item,
            state=state,
        )

    print()
    print("=" * 100)
    print("UNIFIED RAGOPS DEMO SUMMARY")
    print(f"Selected cases : {len(selected_ids)}")
    print(f"Completed      : {completed}")
    print(f"Improved       : {improved}")
    print(f"HITL stopped   : {interrupted}")
    print("Active index   : unchanged")
    print("=" * 100)


if __name__ == "__main__":
    main()
