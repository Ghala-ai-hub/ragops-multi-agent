"""End-to-end integration tests using the team's real components and data.

Runs fully offline with Jawaher's real Absher chunks + TF-IDF backend, Ghala's
DiagnosisAgent, Hajer's HITL/Validation/Workflow, and the approved-action
executor contract that can call Hanan's rewrite tool in live API mode.
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

# Team-owned modules currently use top-level imports. Add scripts/ to sys.path
# without changing their internal logic.
SCRIPTS_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPTS_DIR.parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from diagnosis_agent import DiagnosisAgent
from embeddings import get_embedder
from monitoring_agent import MonitoringAgent
from retrieval import VectorStore

from scripts.action_executor import ApprovedActionExecutor
from scripts.integration_workflow import RAGOpsWorkflow
from scripts.retrieval_run import build_retrieval_run
from scripts.validation_agent import ValidationAgent


ABSHEER_CHUNKS = PROJECT_ROOT / "knowledge_base" / "absher" / "chunks.jsonl"


def build_real_stack(expected_service: str):
    store = VectorStore.from_jsonl(
        ABSHEER_CHUNKS,
        embedder=get_embedder("tfidf"),
    )
    temp_dir = Path(tempfile.mkdtemp(prefix="ragops_real_integration_"))
    monitoring = MonitoringAgent(
        store,
        log_path=temp_dir / "monitoring.jsonl",
        diagnosis_report_log_path=temp_dir / "diagnosis.jsonl",
    )

    def run_candidate(query: str, top_k: int):
        return build_retrieval_run(
            store,
            query,
            top_k,
            expected_platform="Absher",
            expected_service=expected_service,
        )

    executor = ApprovedActionExecutor(
        run_candidate=run_candidate,
        default_k=3,
    )
    workflow = RAGOpsWorkflow(
        monitoring_agent=monitoring,
        diagnosis_agent=DiagnosisAgent(),
        action_executor=executor,
        validation_agent=ValidationAgent(),
    )
    return store, workflow


def test_real_query_mismatch_approved():
    original_query = "ابغى اجدد رخصتي كم تاخذ توصل لي"
    rewritten_query = "ما مدة توصيل رخصة القيادة بعد التجديد؟"
    expected_service = "driving_license_renewal"
    store, workflow = build_real_stack(expected_service)
    before_run = build_retrieval_run(
        store,
        original_query,
        3,
        expected_platform="Absher",
        expected_service=expected_service,
    )

    state = workflow.run(
        query=original_query,
        human_decision="approve",
        before_run=before_run,
        expected_platform="Absher",
        expected_service=expected_service,
        monitoring_kwargs={
            "baseline_k": 3,
            "expanded_k": 10,
            "expected_service_id": expected_service,
            "rewritten_query": rewritten_query,
        },
    )

    assert state["diagnosis_report"]["issue_type"] == "Query Mismatch"
    assert state["optimization_proposal"]["parameters"]["rewritten_query"] == rewritten_query
    assert state["approval_result"]["approval_status"] == "approved"
    assert state["execution_result"]["action_result"]["action"] == "rewrite_query"
    assert state["final_status"] == "IMPROVED"
    assert state["validation_result"]["recommendation"] == "ACCEPT_OPTIMIZED"


def test_real_top_k_approved():
    query = "ضاعت لوحة سيارتي كيف ابلغ عنها"
    expected_service = "lost_stolen_plate_report"
    store, workflow = build_real_stack(expected_service)
    before_run = build_retrieval_run(
        store,
        query,
        2,
        expected_platform="Absher",
        expected_service=expected_service,
    )

    state = workflow.run(
        query=query,
        human_decision="approve",
        before_run=before_run,
        expected_platform="Absher",
        expected_service=expected_service,
        monitoring_kwargs={
            "baseline_k": 2,
            "expanded_k": 10,
            "expected_service_id": expected_service,
        },
    )

    assert state["diagnosis_report"]["issue_type"] == "Top-K"
    assert state["optimization_proposal"]["parameters"]["new_k"] == 3
    assert state["execution_result"]["action_result"]["applied_k"] == 3
    assert state["final_status"] == "IMPROVED"


def test_real_query_mismatch_rejected():
    original_query = "استمارة سيارتي خلصت ابي اجددها"
    rewritten_query = "ما هي شروط وخطوات تجديد رخصة سير المركبة المنتهية؟"
    expected_service = "vehicle_registration_renewal"
    store, workflow = build_real_stack(expected_service)
    before_run = build_retrieval_run(
        store,
        original_query,
        3,
        expected_platform="Absher",
        expected_service=expected_service,
    )

    state = workflow.run(
        query=original_query,
        human_decision="reject",
        before_run=before_run,
        expected_platform="Absher",
        expected_service=expected_service,
        monitoring_kwargs={
            "baseline_k": 3,
            "expanded_k": 10,
            "expected_service_id": expected_service,
            "rewritten_query": rewritten_query,
        },
    )

    assert state["approval_result"]["approval_status"] == "rejected"
    assert state["final_status"] == "REJECTED"
    assert "execution_result" not in state
    assert "validation_result" not in state


def test_real_healthy_baseline():
    query = "ما هي شروط تجديد رخصة القيادة؟"
    expected_service = "driving_license_renewal"
    store, workflow = build_real_stack(expected_service)
    before_run = build_retrieval_run(
        store,
        query,
        3,
        expected_platform="Absher",
        expected_service=expected_service,
    )

    state = workflow.run(
        query=query,
        human_decision="approve",
        before_run=before_run,
        expected_platform="Absher",
        expected_service=expected_service,
        monitoring_kwargs={
            "baseline_k": 3,
            "expanded_k": 10,
            "expected_service_id": expected_service,
        },
    )

    assert state["final_status"] == "NO_ACTION_REQUIRED"
    assert "optimization_proposal" not in state


if __name__ == "__main__":
    test_real_query_mismatch_approved()
    test_real_top_k_approved()
    test_real_query_mismatch_rejected()
    test_real_healthy_baseline()
    print(
        "Real component integration tests passed: Query Mismatch, Top-K, "
        "REJECT, and healthy-baseline paths."
    )
