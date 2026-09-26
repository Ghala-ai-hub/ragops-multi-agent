"""Offline presentation checks for RAGOps in Action; no backend/API execution."""
from __future__ import annotations

import unittest
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import Mock

from frontend.action_presentation import (
    compact_trace, evidence_warning, feedback_state, healthy_baseline,
    inspector_state, structural_execution_available, validation_summary,
)
from frontend.components import metrics_compare_html
from frontend.test_frontend import MarkupParser


class ActionMetricChecks(unittest.TestCase):
    def test_metric_color_tracks_quality_instead_of_numeric_sign(self):
        slow_low = {"recall_at_k":0.2, "precision_at_k":0.1, "reciprocal_rank":0.12, "latency_seconds":1.4}
        fast_high = {"recall_at_k":1.0, "precision_at_k":0.5, "reciprocal_rank":0.5, "latency_seconds":1.02}
        for before, after, first_before, first_after, expected in (
            (slow_low, fast_high, 9, 2, "good"),
            (fast_high, slow_low, 2, 9, "bad"),
        ):
            with self.subTest(direction=expected):
                document = MarkupParser(metrics_compare_html(before, after, first_before, first_after)).root
                cards = document.find(class_name="metric-card")
                self.assertEqual(len(cards), 5)
                for card in cards:
                    name = card.find(class_name="metric-name")[0].text
                    delta = card.find(class_name="metric-delta")[0]
                    self.assertIn(expected, delta.attrs["class"].split(), name)
                    if name == "Latency":
                        self.assertEqual(delta.text, "-0.38s" if expected == "good" else "+0.38s")
                    if name.startswith("First Relevant Rank"):
                        self.assertIn("-7" if expected == "good" else "+7", delta.text)
                        self.assertEqual(card.find(class_name="metric-direction")[0].text, "Lower is better")

    def test_unchanged_or_partial_metrics_have_no_improvement_color(self):
        document = MarkupParser(metrics_compare_html({"recall_at_k":0.5, "latency_seconds":1.0}, {"recall_at_k":0.5})).root
        deltas = document.find(class_name="metric-delta")
        self.assertEqual(len(deltas), 2)
        self.assertTrue(all("neutral" in node.attrs["class"].split() for node in deltas))

    def test_small_latency_changes_show_nonzero_milliseconds_with_correct_direction(self):
        for before, after, expected, color in (
            (0.30151269998168573, 0.30403089997707866, "+2.52ms", "bad"),
            (0.30403089997707866, 0.30151269998168573, "−2.52ms", "good"),
            (1.0, 1.0000001, "+<0.01ms", "bad"),
            (1.0000001, 1.0, "−<0.01ms", "good"),
            (1.0, 1.0, "+0.00s", "neutral"),
        ):
            with self.subTest(before=before, after=after):
                document = MarkupParser(metrics_compare_html({"latency_seconds":before}, {"latency_seconds":after})).root
                delta = document.find(class_name="metric-delta")[0]
                self.assertEqual(delta.text, expected)
                self.assertIn(color, delta.attrs["class"].split())

    def test_rank_found_or_lost_requires_known_relevance(self):
        for first_before, first_after, known, expected in ((None,2,True,"good"), (2,None,True,"bad"), (None,2,False,"neutral")):
            with self.subTest(before=first_before, after=first_after, known=known):
                document = MarkupParser(metrics_compare_html({}, {}, first_before, first_after, ranks_known=known)).root
                self.assertIn(expected, document.find(class_name="metric-delta")[0].attrs["class"].split())


class ActionProjectionChecks(unittest.TestCase):
    def fixture(self, status="IMPROVED"):
        before = {"query":"Test question", "retrieved_results":[{"rank":1,"source":"baseline.txt","text":"Baseline evidence","platform":"balady"}], "recall_at_k":0.0, "latency_seconds":1.2}
        after = {"query":"Rewritten question", "retrieved_results":[{"rank":2,"source":"candidate.txt","text":"Optimized evidence","platform":"balady","relevant":True}], "recall_at_k":1.0, "latency_seconds":0.8}
        return {"mode":"LIVE MODE", "query":"Test question", "before_run":before, "after_run":after,
                "final_run":deepcopy(after if status == "IMPROVED" else before), "final_status":status,
                "diagnosis_report":{"issue_type":"Query Mismatch","reason":"Long diagnostic explanation. " * 30},
                "optimization_proposal":{"action":"rewrite_query","reason":"Long proposal explanation. " * 30},
                "approval_result":{"approval_status":"auto_approved"},
                "validation_result":{"verdict":status,"recommendation":"ACCEPT_OPTIMIZED" if status == "IMPROVED" else "RETAIN_BASELINE","before":before,"after":after},
                "trace":[{"stage":"diagnosis","status":"completed","detail":"Long technical trace. " * 30}, {"stage":"validation","status":"improved","detail":"Recall@K improved"}]}

    def healthy_fixture(self):
        before = {"query":"A labelled question", "retrieved_results":[{"text":"Relevant evidence", "relevant":True}]}
        return {
            "query":"A labelled question", "mode":"LIVE MODE", "before_run":before,
            "final_run":deepcopy(before), "final_status":"NO_ACTION_REQUIRED",
            "monitoring_report":{"failure_detected":False, "baseline_relevant_found":True},
            "diagnosis_report":{"issue_type":None, "recommended_action":"none"},
        }

    def test_healthy_run_reports_skipped_work_without_claiming_validation(self):
        state = self.healthy_fixture()
        snapshot = deepcopy(state)
        self.assertTrue(healthy_baseline(state))
        steps = compact_trace(state, labelled=True)
        self.assertEqual([step["label"] for step in steps], [
            "Complete", "Healthy", "No retrieval issue detected", "Not needed",
            "Not needed", "Not needed", "Not required",
        ])
        self.assertEqual([step["status"] for step in steps], ["completed"] * 3 + ["skipped"] * 4)
        self.assertEqual(feedback_state(state, labelled=True), {
            "text":"Baseline retrieval accepted — no optimization required.", "kind":"positive",
        })
        self.assertEqual(validation_summary(state, labelled=True), {"kind":"healthy", "message":"No optimization required"})
        self.assertEqual(state, snapshot)

    def test_healthy_label_requires_monitoring_diagnosis_and_retained_baseline(self):
        for mutation in (
            {"final_status":"NEEDS_REVIEW"},
            {"monitoring_report":{"baseline_relevant_found":True}},
            {"monitoring_report":{"failure_detected":False, "baseline_relevant_found":None}},
            {"diagnosis_report":{"recommended_action":"needs_review"}},
            {"diagnosis_report":{"recommended_action":"none", "issue_type":"Chunking Quality"}},
            {"final_run":{"query":"A different run"}},
            {"execution_result":{"status":"completed"}},
        ):
            with self.subTest(mutation=mutation):
                state = self.healthy_fixture()
                state.update(mutation)
                self.assertFalse(healthy_baseline(state))
                self.assertNotIn("Healthy", [step["label"] for step in compact_trace(state, labelled=True)])
                self.assertNotEqual(validation_summary(state, labelled=True)["kind"], "healthy")

    def test_validation_summary_distinguishes_real_comparison_rejection_and_unlabelled(self):
        state = self.fixture()
        self.assertEqual(validation_summary(state, labelled=True)["kind"], "metrics")
        self.assertEqual(validation_summary(state, labelled=False), {
            "kind":"unlabelled", "message":"Formal Before/After metrics unavailable for this unlabelled query",
        })
        for before, after in (({}, {}), ({"recall_at_k":None}, {"recall_at_k":1}), ({"recall_at_k":True}, {"recall_at_k":False}), ({"latency_seconds":float("nan")}, {"latency_seconds":1.0})):
            with self.subTest(before=before, after=after):
                state["validation_result"].update(before=before, after=after)
                self.assertNotEqual(validation_summary(state, labelled=True)["kind"], "metrics")
        rejected = self.healthy_fixture()
        rejected.update(final_status="REJECTED", optimization_proposal={"action":"rechunk_and_reindex"}, approval_result={"approval_status":"rejected"})
        expected = {"kind":"rejected", "message":"Baseline retained — no candidate execution was performed"}
        self.assertEqual(validation_summary(rejected, labelled=True), expected)
        self.assertEqual(validation_summary(rejected, labelled=False), expected)
        rejected["execution_result"] = {"status":"completed"}
        self.assertNotEqual(validation_summary(rejected, labelled=True)["kind"], "rejected")

    def test_pending_review_never_reports_before_after(self):
        pending = self.fixture()
        for key in ("validation_result", "after_run", "final_run"):
            pending.pop(key, None)
        pending["final_status"] = "PENDING_HUMAN_APPROVAL"
        pending["optimization_proposal"] = {"action":"rechunk_and_reindex"}
        pending["approval_result"] = {"approval_status":"pending_human_approval"}
        pending["__interrupt__"] = [{"value":{"type":"human_approval_required", "action":"rechunk_and_reindex"}}]
        for labelled in (True, False):
            self.assertEqual(validation_summary(pending, labelled=labelled)["kind"], "pending")
        self.assertEqual(compact_trace(pending, labelled=True)[4]["label"], "Human Approval Required")
        self.assertEqual(validation_summary(None, labelled=False), {"kind":"empty", "message":""})

    def test_trace_is_compact_and_unlabelled_view_has_no_quality_verdict(self):
        state = self.fixture()
        snapshot = deepcopy(state)
        steps = compact_trace(state, labelled=True)
        self.assertEqual([step["name"] for step in steps], ["Baseline RAG","Monitoring","Diagnosis","Optimization","Risk Gate","Action Executor","Validation"])
        self.assertEqual(sum(step["role"].startswith("Agent") for step in steps), 4)
        self.assertTrue(all(step["detail"] == "" for step in steps))
        self.assertEqual(steps[2]["label"], "Query Mismatch")
        self.assertEqual(steps[3]["label"].casefold(), "rewrite query")
        self.assertEqual(steps[4]["label"], "Auto-approved by policy")
        self.assertEqual(steps[6]["label"], "Improved")
        unlabelled = compact_trace(state, labelled=False)
        self.assertEqual(unlabelled[6]["label"], "Not formally validated")
        self.assertEqual(unlabelled[6]["status"], "unvalidated")
        self.assertFalse(any("improved" in (step["label"] + step["detail"]).casefold() for step in unlabelled))
        self.assertEqual(state, snapshot)

    def test_feedback_reflects_only_recorded_evidence_selection(self):
        for status in ("IMPROVED", "SAME", "WORSE", "REJECTED", "NO_ACTION_REQUIRED", "NEEDS_REVIEW"):
            with self.subTest(status=status):
                state = self.fixture(status)
                expected = {"text":"Optimized retrieval accepted","kind":"positive"} if status == "IMPROVED" else {"text":"Baseline retained","kind":"neutral"}
                self.assertEqual(feedback_state(state, labelled=True), expected)
                self.assertEqual(feedback_state(state, labelled=False), None if status == "IMPROVED" else expected)
                state.pop("final_run")
                self.assertIsNone(feedback_state(state, labelled=True))
        pending = self.fixture()
        pending["__interrupt__"] = [{"value":{"type":"human_approval_required","action":"rechunk_and_reindex"}}]
        self.assertIsNone(feedback_state(pending, labelled=True))
        saved = self.fixture()
        saved.pop("final_run")
        saved["verified"] = True
        self.assertEqual(feedback_state(saved, labelled=True)["text"], "Optimized retrieval accepted")

    def test_evidence_warning_uses_explicit_signals_not_distance_thresholds(self):
        state = self.fixture("NEEDS_REVIEW")
        state["final_run"]["retrieved_results"] = [{"platform":"balady","text":"Available context","score":9000}]
        self.assertIsNone(evidence_warning(state, labelled=False))
        for rows in ([], [{"text":"Unrelated","relevant":False}], [{"platform":"balady"},{"platform":"absher"}]):
            with self.subTest(rows=rows):
                state["final_run"]["retrieved_results"] = rows
                self.assertEqual(evidence_warning(state, labelled=False), "Retrieved evidence does not sufficiently support this query.")
                self.assertIsNone(evidence_warning(state, labelled=True))

    def test_structural_capability_requires_explicit_callable_and_never_executes_it(self):
        callback = Mock()
        for workflow in (None, object(), SimpleNamespace(action_executor=None), SimpleNamespace(action_executor=SimpleNamespace(rechunk_candidate=None)), SimpleNamespace(action_executor=SimpleNamespace(rechunk_candidate=True))):
            self.assertFalse(structural_execution_available(workflow))
        self.assertTrue(structural_execution_available(SimpleNamespace(action_executor=SimpleNamespace(rechunk_candidate=callback))))
        callback.assert_not_called()

    def test_unlabelled_inspection_removes_formal_quality_without_changing_state(self):
        state = self.fixture()
        state["nested"] = {"precision_at_k":0.5,"mrr":1.0,"first_relevant_rank":2,"judge_score":5,"latency_seconds":1.2}
        snapshot = deepcopy(state)
        projected = inspector_state(state, labelled=False)
        self.assertNotIn("validation_result", projected)
        self.assertNotIn("final_status", projected)
        self.assertFalse(any(event["stage"] == "validation" for event in projected["trace"]))
        self.assertNotIn("recall_at_k", projected["before_run"])
        self.assertEqual(projected["nested"], {"latency_seconds":1.2})
        self.assertEqual(state, snapshot)
        projected["before_run"]["retrieved_results"][0]["source"] = "Local view mutation"
        self.assertEqual(state, snapshot)
        labelled = inspector_state(state, labelled=True)
        self.assertEqual(labelled["validation_result"], state["validation_result"])


if __name__ == "__main__":
    unittest.main()
