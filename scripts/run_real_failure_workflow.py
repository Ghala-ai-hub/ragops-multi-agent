"""Run the real RAGOps workflow on the current baseline failures.

This is the first real-data integration check over the already-built FAISS
index. It reuses the saved Query-Rewrite diagnostic probes and runs:

Monitoring -> Diagnosis -> Optimization proposal -> Auto-approval ->
Execution -> Validation

Only low-impact actions are expected for the current five failures:
- rewrite_query
- change_top_k

The active FAISS index is never overwritten.
"""
from __future__ import annotations

import json
from pathlib import Path

from dotenv import load_dotenv
from langchain_community.vectorstores import FAISS
from langchain_openai import OpenAIEmbeddings

from action_executor import ApprovedActionExecutor
from diagnosis_agent import DiagnosisAgent
from integration_workflow import RAGOpsWorkflow
from monitoring_agent import MonitoringAgent
from optimization_agent import OptimizationAgent
from retrieval_run import build_retrieval_run


DATASET_PATH = Path("evaluation/dataset_v2.json")
RETRIEVAL_RESULTS_PATH = Path(
    "evaluation/retrieval_results_v2.json"
)
REWRITE_RESULTS_PATH = Path(
    "evaluation/rewrite_probe_results.json"
)
OUTPUT_PATH = Path(
    "evaluation/real_failure_workflow_results.json"
)
VECTORSTORE_PATH = "vector_store/evaluation_index"

EMBEDDING_MODEL = "text-embedding-3-small"
BASELINE_K = 4
EXPANDED_K = 10


def main() -> None:
    load_dotenv()

    dataset = json.loads(
        DATASET_PATH.read_text(encoding="utf-8")
    )
    retrieval_results = json.loads(
        RETRIEVAL_RESULTS_PATH.read_text(
            encoding="utf-8"
        )
    )
    rewrite_results = json.loads(
        REWRITE_RESULTS_PATH.read_text(
            encoding="utf-8"
        )
    )

    dataset_by_id = {item["id"]: item for item in dataset}
    rewrite_by_id = {
        item["id"]: item
        for item in rewrite_results["results"]
    }

    failed_ids = [
        item["id"]
        for item in retrieval_results["results"]
        if float(item.get("recall_at_k", 0.0)) == 0.0
    ]

    embeddings = OpenAIEmbeddings(
        model=EMBEDDING_MODEL
    )
    vector_store = FAISS.load_local(
        VECTORSTORE_PATH,
        embeddings,
        allow_dangerous_deserialization=True,
    )

    monitor = MonitoringAgent(vector_store)

    def run_candidate(query: str, top_k: int):
        # Ground-truth fields are injected per case by the wrapper below.
        # The workflow uses this callback only after diagnosis.
        current = run_candidate.current_item
        return build_retrieval_run(
            vector_store,
            query,
            top_k,
            expected_platform=current["platform"],
            expected_service=current["service"],
        )

    run_candidate.current_item = {}

    executor = ApprovedActionExecutor(
        run_candidate=run_candidate,
        default_k=BASELINE_K,
    )

    workflow = RAGOpsWorkflow(
        monitoring_agent=monitor,
        diagnosis_agent=DiagnosisAgent(),
        optimization_agent=OptimizationAgent(),
        action_executor=executor,
    )

    output = {
        "configuration": {
            "embedding_model": EMBEDDING_MODEL,
            "baseline_k": BASELINE_K,
            "expanded_k": EXPANDED_K,
            "failed_queries": len(failed_ids),
        },
        "results": [],
    }

    print(
        f"REAL FAILED-QUERY WORKFLOW: {len(failed_ids)} cases"
    )
    print("=" * 100)

    for index, query_id in enumerate(
        failed_ids,
        start=1,
    ):
        item = dataset_by_id[query_id]
        rewrite_probe = rewrite_by_id.get(query_id)

        if rewrite_probe is None:
            raise KeyError(
                f"Missing rewrite probe for {query_id}"
            )

        rewritten_query = rewrite_probe.get(
            "rewritten_query"
        )

        before_run = build_retrieval_run(
            vector_store,
            item["query"],
            BASELINE_K,
            expected_platform=item["platform"],
            expected_service=item["service"],
        )

        run_candidate.current_item = item

        state = workflow.run(
            query=item["query"],
            before_run=before_run,
            expected_platform=item["platform"],
            expected_service=item["service"],
            monitoring_kwargs={
                "baseline_k": BASELINE_K,
                "expanded_k": EXPANDED_K,
                "expected_platform": item["platform"],
                "expected_service": item["service"],
                "rewritten_query": rewritten_query,
            },
        )

        diagnosis = state["diagnosis_report"]
        proposal = state.get(
            "optimization_proposal",
            {}
        )
        validation = state.get(
            "validation_result",
            {}
        )

        record = {
            "id": query_id,
            "platform": item["platform"],
            "service": item["service"],
            "query_type": item["query_type"],
            "original_query": item["query"],
            "rewritten_query": rewritten_query,
            "diagnosis": diagnosis,
            "proposal": proposal,
            "approval": state.get(
                "approval_result"
            ),
            "execution": state.get(
                "execution_result"
            ),
            "validation": validation,
            "final_status": state["final_status"],
        }
        output["results"].append(record)

        print(f"[{index}/{len(failed_ids)}] {query_id}")
        print(
            f"Diagnosis : {diagnosis.get('issue_type')}"
        )
        print(
            f"Action    : {diagnosis.get('recommended_action')}"
        )
        print(
            f"Approval  : "
            f"{state.get('approval_result', {}).get('approval_status')}"
        )

        if validation:
            before = validation["before"]
            after = validation["after"]
            print(
                "Before    : "
                f"Recall={before['recall_at_k']:.2f}, "
                f"Precision={before['precision_at_k']:.2f}, "
                f"RR={before['reciprocal_rank']:.2f}"
            )
            print(
                "After     : "
                f"Recall={after['recall_at_k']:.2f}, "
                f"Precision={after['precision_at_k']:.2f}, "
                f"RR={after['reciprocal_rank']:.2f}"
            )
            print(
                f"Validation: {validation['verdict']} | "
                f"{validation['recommendation']}"
            )

        print(f"Final     : {state['final_status']}")
        print("-" * 100)

    OUTPUT_PATH.write_text(
        json.dumps(
            output,
            ensure_ascii=False,
            indent=2,
            default=str,
        ),
        encoding="utf-8",
    )

    counts = {}
    for item in output["results"]:
        issue = (
            item["diagnosis"].get("issue_type")
            or "None"
        )
        counts[issue] = counts.get(issue, 0) + 1

    improved = sum(
        1
        for item in output["results"]
        if item["final_status"] == "IMPROVED"
    )

    print("SUMMARY")
    print("=" * 100)
    print(f"Diagnosis counts: {counts}")
    print(
        f"Validated IMPROVED: "
        f"{improved}/{len(output['results'])}"
    )
    print(f"Saved to: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
