"""Read-only checks for evaluation-only Dashboard projections.

Synthetic records below exercise absent/invalid artifact fields only; they are
never written to artifacts or included in the application Dashboard.
"""
from __future__ import annotations

from copy import deepcopy
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

from frontend.adapter import FrontendAdapter
from frontend.dashboard import (
    accepted_result, action_label, decision_label, evaluation_dashboard, live_run_summary, validation_label,
)
from frontend.evidence import recorded_run
from frontend.presentation import approval_view


class DashboardAuditChecks(unittest.TestCase):
    def setUp(self):
        self.adapter = FrontendAdapter()

    def test_actual_artifact_totals_and_decisions_are_separate(self):
        dashboard = evaluation_dashboard(self.adapter)
        self.assertEqual(dashboard["summary"]["total_queries"], 48)
        self.assertEqual(dashboard["summary"]["k"], 4)
        self.assertAlmostEqual(dashboard["summary"]["overall"]["recall_at_k"], 43 / 48)
        self.assertEqual(dashboard["baseline_failure_count"], 5)
        self.assertEqual(dashboard["outcomes"], {"IMPROVED": 5, "SAME": 0, "WORSE": 0})
        self.assertEqual(dashboard["issue_counts"], {"Query Mismatch": 4, "Top-K": 1})
        self.assertEqual(len(dashboard["run_rows"]), 5)
        for row in dashboard["run_rows"]:
            self.assertIn(row["Run"], self.adapter.workflow_by_id)
            stored = self.adapter.workflow_by_id[row["Run"]]
            self.assertEqual(row["Policy Reviewed"], stored["approval"]["reviewed_at"])
            self.assertEqual(row["Human Decision"], "auto_approved")
            self.assertEqual(row["Verdict"], "IMPROVED")
            self.assertEqual(approval_view(recorded_run(self.adapter, row["Run"]))["label"], "Auto-approved by policy")

    def test_policy_outcomes_cannot_be_counted_as_validation(self):
        rows = [
            {"approval": {"approval_status": "approved"}, "validation": {"verdict": "WORSE"}},
            {"approval": {"approval_status": "auto_approved"}, "validation": {"verdict": "SAME"}},
            {"approval": {"approval_status": "rejected"}},
            {"validation": {"verdict": "REJECTED"}},
            {"validation": {"verdict": "AUTO_APPROVED"}},
            {"validation": {"verdict": "HUMAN_APPROVED"}},
        ]
        dashboard = evaluation_dashboard(SimpleNamespace(workflow={"results": rows}))
        self.assertEqual(dashboard["outcomes"], {"IMPROVED": 0, "SAME": 1, "WORSE": 1})
        self.assertEqual([row["Human Decision"] for row in dashboard["run_rows"][:3]], ["approved", "auto_approved", "rejected"])

    def test_absent_ids_dates_metrics_and_outcomes_stay_absent(self):
        dashboard = evaluation_dashboard(SimpleNamespace(workflow={"results": [{}]}))
        self.assertEqual(dashboard["outcomes"], {"IMPROVED": 0, "SAME": 0, "WORSE": 0})
        self.assertTrue(all(value is None for value in dashboard["run_rows"][0].values()))
        self.assertTrue(all(value is None for value in dashboard["avg_before"].values()))
        self.assertTrue(all(value is None for value in dashboard["avg_after"].values()))

    def test_missing_measurements_are_not_zero_or_false_failures(self):
        adapter = SimpleNamespace(
            workflow={"results": [
                {"validation": {"before": {"latency_seconds": 2.0}, "after": {"latency_seconds": 1.0}}},
                {"validation": {"before": {"latency_seconds": None}, "after": {"latency_seconds": False}}},
                {"validation": {"before": {"latency_seconds": float("nan")}, "after": {"latency_seconds": float("inf")}}},
            ]},
            retrieval={"results": [{}, {"recall_at_k": False}, {"recall_at_k": 0.0}]},
        )
        dashboard = evaluation_dashboard(adapter)
        self.assertEqual(dashboard["baseline_failure_count"], 1)
        self.assertEqual(dashboard["avg_before"]["latency_seconds"], 2.0)
        self.assertEqual(dashboard["avg_after"]["latency_seconds"], 1.0)

    def test_projection_never_invokes_live_or_synthetic_replay(self):
        forbidden = Mock(side_effect=AssertionError("Dashboard must use stored evidence only"))
        for method in ("dashboard", "run_live", "resume_live", "demo_run", "build_evaluation_index"):
            setattr(self.adapter, method, forbidden)
        dashboard = evaluation_dashboard(self.adapter)
        self.assertEqual(set(row["Run"] for row in dashboard["run_rows"]), set(self.adapter.workflow_by_id))
        forbidden.assert_not_called()

    def test_frontend_formatting_cannot_mutate_stored_artifacts(self):
        snapshot = deepcopy((self.adapter.retrieval, self.adapter.workflow, self.adapter.chunk_sweep))
        dashboard = evaluation_dashboard(self.adapter)
        dashboard["summary"]["overall"]["recall_at_k"] = -1
        dashboard["failures"][0]["approval"]["approval_status"] = "rejected"
        dashboard["run_rows"][0]["Run"] = "view-only"
        self.assertEqual((self.adapter.retrieval, self.adapter.workflow, self.adapter.chunk_sweep), snapshot)

    def test_official_snapshot_and_platform_order_match_artifacts(self):
        dashboard = evaluation_dashboard(self.adapter)
        self.assertEqual(dashboard["snapshot"], {
            "evaluation_queries": 48, "platforms": 4, "baseline_failures": 5,
            "verified_failures_improved": 5, "verified_failure_runs": 5,
            "baseline_recall_at_k": 43 / 48, "k": 4,
        })
        self.assertEqual([row["Platform"] for row in dashboard["platform_rows"]], ["Absher", "Balady", "Najiz", "Sakani"])
        for row in dashboard["platform_rows"]:
            stored = self.adapter.retrieval["summary"]["by_platform"][row["Platform"].lower()]
            self.assertEqual({key: value for key, value in row.items() if key != "Platform"}, stored)

    def test_three_failure_types_include_real_zero_without_extra_platform_failures(self):
        dashboard = evaluation_dashboard(self.adapter)
        self.assertEqual(dashboard["display_issue_counts"], {
            "Query Mismatch": 4, "Top-K Retrieval": 1, "Chunking Quality": 0,
        })
        self.assertEqual({row["Platform"] for row in dashboard["history_rows"]}, {"Balady", "Absher"})
        self.assertEqual(sum(dashboard["display_issue_counts"].values()), 5)
        self.assertEqual(dashboard["baseline_failure_platforms"], {"Absher": 1, "Balady": 4})

    def test_before_after_only_averages_paired_finite_measurements(self):
        adapter = SimpleNamespace(workflow={"results": [
            {"validation": {"before": {"recall_at_k": 0, "latency_seconds": 2}, "after": {"recall_at_k": 1, "latency_seconds": 1}}},
            {"validation": {"before": {"recall_at_k": 1, "latency_seconds": 100}, "after": {}}},
            {"validation": {"before": {}, "after": {"recall_at_k": 0, "latency_seconds": 100}}},
        ]})
        dashboard = evaluation_dashboard(adapter)
        self.assertEqual(dashboard["avg_before"]["recall_at_k"], 0)
        self.assertEqual(dashboard["avg_after"]["recall_at_k"], 1)
        self.assertEqual(dashboard["paired_metrics"]["recall_at_k"]["count"], 1)
        self.assertEqual(dashboard["paired_metrics"]["latency_seconds"], {
            "before": 2, "after": 1, "delta": -1, "count": 1,
            "direction": "improved", "lower_is_better": True,
        })
        self.assertEqual(dashboard["paired_metrics"]["precision_at_k"]["count"], 0)
        self.assertIsNone(dashboard["paired_metrics"]["precision_at_k"]["direction"])

    def test_actual_aggregate_and_candidate_metrics_are_from_recorded_runs(self):
        dashboard = evaluation_dashboard(self.adapter)
        for metric, pair in dashboard["paired_metrics"].items():
            self.assertEqual(pair["count"], 5)
            before = sum(row["validation"]["before"][metric] for row in self.adapter.workflow["results"]) / 5
            after = sum(row["validation"]["after"][metric] for row in self.adapter.workflow["results"]) / 5
            self.assertAlmostEqual(pair["before"], before)
            self.assertAlmostEqual(pair["after"], after)
            self.assertAlmostEqual(pair["delta"], after - before)
            self.assertEqual(pair["direction"], "improved")
        self.assertEqual(dashboard["chunking_candidates"], self.adapter.chunk_sweep["candidates"])
        self.assertEqual(dashboard["chunking_baseline"], self.adapter.chunk_sweep["baseline"])
        self.assertNotIn("judge_score", dashboard["paired_metrics"])

    def test_compact_history_has_only_requested_columns_and_real_ids(self):
        dashboard = evaluation_dashboard(self.adapter)
        for row in dashboard["history_rows"]:
            self.assertEqual(list(row), ["Case", "Platform", "Issue", "Action", "Decision", "Validation Verdict"])
            stored = self.adapter.workflow_by_id[row["Case"]]
            self.assertEqual(row["Action"], action_label(stored["proposal"]["action"]))
            self.assertEqual(row["Decision"], "Auto-approved by policy")
            self.assertEqual(row["Validation Verdict"], "Improved")
        absent = evaluation_dashboard(SimpleNamespace(workflow={"results": [{}]}))
        self.assertEqual(absent["history_rows"][0]["Decision"], "Not recorded")
        self.assertTrue(all(value is None for key, value in absent["history_rows"][0].items() if key != "Decision"))

    def test_decisions_never_imply_a_quality_outcome_or_acceptance(self):
        for verdict in ("auto_approved", "approved", "REJECTED", "HUMAN_APPROVED", "", None, {}):
            self.assertIsNone(validation_label(verdict))
        self.assertEqual(validation_label("SAME"), "No Meaningful Change")
        self.assertEqual(decision_label({"approval": {"approval_status": "approved"}}), "Human approved")
        self.assertEqual(decision_label({"approval_result": {"human_decision": "reject"}}), "Human rejected")
        self.assertEqual(decision_label({"final_status": "NO_ACTION_REQUIRED"}), "Not required")
        self.assertEqual(decision_label({"proposal": {"action": "rewrite_query"}}), "Not recorded")
        self.assertEqual(decision_label({"approval": {"approval_status": "pending_human_approval"}}), "Not recorded")
        self.assertIsNone(accepted_result({"approval": {"approval_status": "approved"}}))
        self.assertIsNone(accepted_result({"validation": {"verdict": "IMPROVED"}}))
        self.assertEqual(accepted_result({"validation": {"recommendation": "ACCEPT_OPTIMIZED"}}), "Optimized retrieval")
        self.assertEqual(accepted_result({"validation_result": {"recommendation": "RETAIN_BASELINE"}}), "Baseline retained")
        self.assertEqual(accepted_result({"approval": {"next_step": "retain_baseline"}}), "Baseline retained")

    def test_live_session_is_secondary_and_cannot_change_official_evaluation(self):
        before = evaluation_dashboard(self.adapter)
        live = {
            "mode": "LIVE MODE", "user_query": "Original question", "query": "Resolved question",
            "diagnosis_report": {"issue_type": "Top-K"},
            "optimization_proposal": {"action": "change_top_k"},
            "validation_result": {"verdict": "WORSE"},
        }
        summary = live_run_summary(live)
        self.assertEqual(summary, {
            "Query": "Original question", "Diagnosis": "Top-K", "Action": "change_top_k",
        })
        self.assertEqual(live_run_summary(live, labelled=True)["Validation outcome"], "Worse")
        self.assertIsNone(live_run_summary({**live, "mode": "VERIFIED DEMO MODE"}))
        self.assertIsNone(live_run_summary(None))
        live["validation_result"]["verdict"] = "IMPROVED"
        self.assertEqual(evaluation_dashboard(self.adapter), before)

    def test_unusable_live_sessions_do_not_produce_a_panel(self):
        for run in (None, {}, [], "invalid", {"mode": "LIVE MODE"},
                    {"mode": "LIVE MODE", "query": "Question only"},
                    {"mode": "LIVE MODE", "query": "   ", "optimization_proposal": {"action": "rewrite_query"}},
                    {"mode": "LIVE MODE", "query": "Question", "diagnosis_report": {"issue_type": None},
                     "optimization_proposal": {}, "validation_result": {}},
                    {"mode": "LIVE MODE", "query": "Question", "final_status": "NO_ACTION_REQUIRED"},
                    {"mode": "LIVE MODE", "query": "Question", "final_status": "REJECTED", "final_run": {}}):
            with self.subTest(run=run):
                self.assertIsNone(live_run_summary(run))

    def test_real_retained_evidence_is_usable_without_formal_metrics(self):
        before = {"retrieved_results": [{"text": "Recorded evidence"}]}
        run = {"mode": "LIVE MODE", "query": "Question", "final_status": "REJECTED",
               "before_run": before, "final_run": deepcopy(before)}
        self.assertEqual(live_run_summary(run), {"Query": "Question", "Result": "Baseline retained"})

    def test_healthy_baseline_summary_requires_real_completed_branch(self):
        before = {"query": "Question", "retrieved_results": [{"text": "Relevant evidence", "relevant": True}]}
        healthy = {
            "mode": "LIVE MODE", "query": "Question", "before_run": before,
            "final_run": deepcopy(before), "final_status": "NO_ACTION_REQUIRED",
            "monitoring_report": {"failure_detected": False, "baseline_relevant_found": True},
            "diagnosis_report": {"issue_type": None, "recommended_action": "none"},
        }
        snapshot = deepcopy(healthy)
        summary = live_run_summary(healthy)
        self.assertIn("Healthy baseline · No optimization required", summary.values())
        self.assertEqual(summary["Query"], "Question")
        self.assertEqual(healthy, snapshot)
        for patch in ({"final_status": "NEEDS_REVIEW"}, {"monitoring_report": {}},
                      {"final_run": {}}, {"execution_result": {"status": "completed"}}):
            with self.subTest(patch=patch):
                summary = live_run_summary({**healthy, **patch})
                self.assertNotIn("Healthy baseline · No optimization required", (summary or {}).values())


if __name__ == "__main__":
    unittest.main()
