"""Offline checks of the existing live structural integration.

The real policy, LangGraph checkpoints, agents, executor, candidate adapter,
retrieval normalizer, and validator run here. Only embedding/vector I/O is
replaced. Candidate files and monitoring logs stay in temporary directories.
"""
from __future__ import annotations

import os
import tempfile
import unittest
from contextlib import ExitStack
from datetime import datetime, timezone
from functools import partial
from pathlib import Path
from unittest.mock import Mock, patch

from langchain_core.documents import Document

from frontend.adapter import FrontendAdapter, RuntimeStatus
from scripts.action_executor import ApprovedActionExecutor
from scripts.diagnosis_agent import DiagnosisAgent
from scripts.langgraph_workflow import LangGraphRAGOps
from scripts.monitoring_agent import MonitoringAgent
from scripts.optimization_agent import OptimizationAgent
from scripts.rechunk_candidate_adapter import RechunkCandidateAdapter
from scripts.retrieval_run import build_retrieval_run
from scripts.validation_agent import ValidationAgent


def document(platform: str, service: str, *, tiny: bool = False) -> Document:
    return Document(
        page_content="Short fragment" if tiny else "Complete retrieval evidence. " * 12,
        metadata={
            "platform": platform,
            "service": service,
            "source": f"test/{platform}/{service}.md",
            "chunk_index": 0,
        },
    )


class MemoryVectorStore:
    """Substitute for network/vector I/O, with real document metadata."""

    def __init__(self, documents):
        self.documents = documents
        self.calls = []

    def similarity_search_with_score(self, query, *, k):
        self.calls.append((query, k))
        return [(row, float(rank)) for rank, row in enumerate(self.documents[:k])]


class OfflineIntegrationCase(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.directory = Path(self.stack.enter_context(tempfile.TemporaryDirectory(prefix="ragops-integration-")))
        self.stack.enter_context(patch.dict(os.environ, {
            "LANGSMITH_TRACING": "false", "LANGCHAIN_TRACING_V2": "false",
        }))
        self.stack.enter_context(patch("socket.socket.connect", side_effect=AssertionError("Network is disabled in offline tests")))

    def monitoring(self, vector_store):
        return MonitoringAgent(vector_store, log_path=self.directory / "monitoring.jsonl")


class StructuralWorkflowChecks(OfflineIntegrationCase):
    def workflow(self, *, baseline_relevant, candidate_relevant):
        expected = {"expected_platform": "balady", "expected_service": "building_permit"}
        baseline = MemoryVectorStore([document(
            "balady" if baseline_relevant else "absher",
            "building_permit" if baseline_relevant else "passport",
            tiny=True,
        )])
        candidate = MemoryVectorStore([document(
            "balady" if candidate_relevant else "absher",
            "building_permit" if candidate_relevant else "passport",
        )])
        builder = Mock(return_value={
            "vector_store": candidate,
            "status": "candidate_built",
            "candidate_index_path": "vector_store/candidates/offline-test",
        })
        build_run = Mock(wraps=build_retrieval_run)
        callback = RechunkCandidateAdapter(build_candidate=builder, build_run=build_run, **expected)
        ordinary_retrieval = Mock(side_effect=AssertionError("Structural execution must retrieve from the candidate"))
        validator = ValidationAgent()
        validate = Mock(wraps=validator.validate)
        validator.validate = validate
        workflow = LangGraphRAGOps(
            monitoring_agent=self.monitoring(baseline),
            diagnosis_agent=DiagnosisAgent(),
            optimization_agent=OptimizationAgent(),
            action_executor=ApprovedActionExecutor(run_candidate=ordinary_retrieval, rechunk_candidate=callback),
            validation_agent=validator,
        )
        before = build_retrieval_run(baseline, "Structural test question", 4, **expected)
        state = {
            "query": before["query"], "before_run": before, **expected,
            "monitoring_kwargs": {"baseline_k": 4, "expanded_k": 10, **expected},
            "trace": [],
        }
        return workflow, state, builder, build_run, validate, ordinary_retrieval, candidate

    def test_native_interrupt_builds_nothing_and_reject_retains_baseline(self):
        workflow, state, builder, build_run, validate, ordinary, _ = self.workflow(
            baseline_relevant=False, candidate_relevant=True,
        )
        pending = workflow.invoke(state, thread_id="reject-structural")
        self.assertTrue(pending.get("__interrupt__"))
        self.assertEqual(pending["optimization_proposal"]["action"], "rechunk_and_reindex")
        self.assertNotIn("execution_result", pending)
        self.assertNotIn("validation_result", pending)
        builder.assert_not_called()
        build_run.assert_not_called()
        validate.assert_not_called()

        rejected = workflow.resume("reject", thread_id="reject-structural")
        self.assertEqual(rejected["final_status"], "REJECTED")
        self.assertEqual(rejected["approval_result"]["approval_status"], "rejected")
        self.assertFalse(rejected["approval_result"]["execution_allowed"])
        self.assertEqual(rejected["final_run"], state["before_run"])
        self.assertNotIn("execution_result", rejected)
        self.assertNotIn("validation_result", rejected)
        builder.assert_not_called()
        build_run.assert_not_called()
        validate.assert_not_called()
        ordinary.assert_not_called()

    def test_approve_validates_candidate_and_selects_evidence_by_actual_verdict(self):
        for baseline_relevant, candidate_relevant, verdict in (
            (False, True, "IMPROVED"), (True, True, "SAME"), (True, False, "WORSE"),
        ):
            with self.subTest(verdict=verdict):
                workflow, state, builder, build_run, validate, ordinary, candidate = self.workflow(
                    baseline_relevant=baseline_relevant, candidate_relevant=candidate_relevant,
                )
                thread = f"approve-{verdict}"
                pending = workflow.invoke(state, thread_id=thread)
                self.assertTrue(pending.get("__interrupt__"))
                builder.assert_not_called()
                validate.assert_not_called()

                result = workflow.resume("approve", thread_id=thread)
                self.assertEqual(result["approval_result"]["approval_status"], "approved")
                self.assertTrue(result["approval_result"]["execution_allowed"])
                builder.assert_called_once_with(chunk_size=500, chunk_overlap=100)
                build_run.assert_called_once_with(
                    candidate, state["query"], 4,
                    expected_platform="balady", expected_service="building_permit",
                )
                validate.assert_called_once_with(
                    result["before_run"], result["after_run"],
                    expected_platform="balady", expected_service="building_permit",
                )
                self.assertEqual(result["validation_result"]["verdict"], verdict)
                self.assertEqual(result["final_status"], verdict)
                self.assertEqual(result["final_run"], result["after_run"] if verdict == "IMPROVED" else state["before_run"])
                self.assertEqual(result["after_run"]["retrieved_results"][0]["relevant"], candidate_relevant)
                self.assertTrue(result["execution_result"]["action_result"]["non_destructive"])
                self.assertEqual([event["stage"] for event in result["trace"]], [
                    "monitoring", "diagnosis", "optimization", "approval", "execution", "validation",
                ])
                ordinary.assert_not_called()


class AdapterWiringChecks(OfflineIntegrationCase):
    def test_real_adapter_callback_uses_current_run_ground_truth(self):
        adapter = FrontendAdapter()
        baseline = MemoryVectorStore([document("test-other", "test-other", tiny=True)])
        candidate = MemoryVectorStore([document("balady", "building_permit")])
        builder = Mock(return_value={"vector_store": candidate, "status": "candidate_built"})
        build_run = Mock(wraps=build_retrieval_run)
        candidate_factory = Mock(wraps=partial(RechunkCandidateAdapter, build_candidate=builder, build_run=build_run))
        log_path = self.directory / "adapter-monitoring.jsonl"

        class TemporaryLogMonitoring(MonitoringAgent):
            def __init__(self, vector_store):
                super().__init__(vector_store, log_path=log_path)

        self.stack.enter_context(patch("dotenv.load_dotenv", return_value=False))
        self.stack.enter_context(patch("langchain_openai.OpenAIEmbeddings", return_value=object()))
        self.stack.enter_context(patch("langchain_community.vectorstores.FAISS.load_local", return_value=baseline))
        self.stack.enter_context(patch("scripts.monitoring_agent.MonitoringAgent", TemporaryLogMonitoring))
        self.stack.enter_context(patch("scripts.rechunk_candidate_adapter.RechunkCandidateAdapter", candidate_factory))
        self.stack.enter_context(patch.object(adapter, "runtime_status", return_value=RuntimeStatus(True, True, True, False)))

        cases = [adapter.dataset_by_id[case] for case in ("balady_building_permit_001", "absher_driving_license_renewal_002")]
        for item in cases:
            with self.subTest(case=item["id"]):
                candidate.documents = [document(item["platform"], item["service"])]
                builder.reset_mock()
                candidate_factory.reset_mock()
                build_run.reset_mock()
                live = adapter.run_live(item["query"])
                self.assertTrue(callable(live["workflow"].action_executor.rechunk_candidate))
                self.assertTrue(live["state"].get("__interrupt__"))
                builder.assert_not_called()
                candidate_factory.assert_not_called()
                approved = adapter.resume_live(live["workflow"], live["thread_id"], "approve")
                candidate_factory.assert_called_once_with(expected_platform=item["platform"], expected_service=item["service"])
                build_run.assert_called_once_with(candidate, item["query"], 4, expected_platform=item["platform"], expected_service=item["service"])
                self.assertEqual(approved["validation_result"]["verdict"], "IMPROVED")
                self.assertTrue(approved["final_run"]["retrieved_results"][0]["relevant"])
                self.assertEqual(approved["final_run"]["retrieved_results"][0]["service"], item["service"])


class CandidateIsolationChecks(OfflineIntegrationCase):
    def test_same_timestamp_builds_are_isolated_and_baseline_is_untouched(self):
        from scripts import optimization_tools

        baseline = self.directory / "vector_store" / "evaluation_index"
        baseline.mkdir(parents=True)
        sentinels = {"index.faiss": b"baseline-vector-sentinel", "index.pkl": b"baseline-metadata-sentinel"}
        for name, content in sentinels.items():
            (baseline / name).write_bytes(content)
        corpus = self.directory / "knowledge_base"
        service = corpus / "balady" / "building_permit"
        service.mkdir(parents=True)
        (service / "content_final.md").write_text("# Test service\n\n" + "Document content for chunking. " * 45, encoding="utf-8")
        saved_paths = []

        def save_local(path):
            output = Path(path).resolve()
            self.assertTrue(output.is_relative_to(self.directory / "vector_store" / "candidates"))
            self.assertTrue(output.is_dir())
            saved_paths.append(output)
            (output / "index.faiss").write_bytes(b"candidate-vectors")
            (output / "index.pkl").write_bytes(b"candidate-metadata")

        fake_store = Mock()
        fake_store.save_local.side_effect = save_local
        frozen = Mock()
        frozen.now.return_value = datetime(2026, 1, 1, tzinfo=timezone.utc)
        with patch.object(optimization_tools, "PROJECT_ROOT", self.directory), \
             patch.object(optimization_tools, "KNOWLEDGE_BASE_DIR", corpus), \
             patch.object(optimization_tools, "datetime", frozen), \
             patch.object(optimization_tools, "OpenAIEmbeddings", return_value=object()), \
             patch.object(optimization_tools.FAISS, "from_documents", return_value=fake_store) as from_documents:
            cwd = Path.cwd()
            first = optimization_tools.rechunk_and_reindex(500, 100)
            second = optimization_tools.rechunk_and_reindex(500, 100)
            self.assertEqual(Path.cwd(), cwd)
        self.assertNotEqual(first["candidate_index_path"], second["candidate_index_path"])
        self.assertEqual(len(set(saved_paths)), 2)
        self.assertEqual(from_documents.call_count, 2)
        for outcome in (first, second):
            self.assertEqual(outcome["status"], "candidate_built")
            self.assertIn("rechunk_500_100_20260101T000000Z_", outcome["candidate_index_path"])
            self.assertTrue((self.directory / outcome["candidate_index_path"] / "index.faiss").is_file())
        for name, content in sentinels.items():
            self.assertEqual((baseline / name).read_bytes(), content)
        chunks = from_documents.call_args.args[0]
        self.assertTrue(chunks)
        self.assertTrue(all(chunk.metadata["platform"] == "balady" and chunk.metadata["service"] == "building_permit" for chunk in chunks))


if __name__ == "__main__":
    unittest.main()
