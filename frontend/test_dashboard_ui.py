"""Dashboard-only UI checks against stored evaluation evidence; never run live.

The optional session fixture is deliberately confined to this test. It verifies
that session results cannot alter official charts or evaluation totals.
"""
from __future__ import annotations

from contextlib import ExitStack
from copy import deepcopy
import json
import math
from pathlib import Path
import unittest
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

from frontend.adapter import FrontendAdapter, RuntimeStatus
from frontend.evidence import recorded_run
from frontend.test_frontend import MarkupParser


ROOT = Path(__file__).resolve().parents[1]
VERDICTS = ["Improved", "No Meaningful Change", "Worse"]
HISTORY_COLUMNS = ["Case", "Platform", "Issue", "Action", "Decision", "Validation Verdict"]


class DashboardUIChecks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.adapter = FrontendAdapter()
        cls.patches = ExitStack()
        cls.blockers = []
        for method in ("run_live", "resume_live", "build_evaluation_index", "set_session_api_key"):
            cls.blockers.append(cls.patches.enter_context(patch.object(
                FrontendAdapter, method,
                side_effect=AssertionError("Dashboard verification cannot execute or write backend state"),
            )))
        cls.patches.enter_context(patch.object(
            FrontendAdapter, "runtime_status", return_value=RuntimeStatus(False, False, False, False),
        ))
        for target in ("frontend.answers.generate_final_answer", "frontend.conversation.resolve_followup"):
            cls.blockers.append(cls.patches.enter_context(patch(
                target, side_effect=AssertionError("Dashboard verification cannot call OpenAI"),
            )))

    @classmethod
    def tearDownClass(cls):
        try:
            for blocker in cls.blockers:
                blocker.assert_not_called()
        finally:
            cls.patches.close()

    def app(self, run=None):
        app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=30)
        app.query_params["page"] = "dashboard"
        if run is not None:
            app.session_state.current_run = deepcopy(run)
        app.run()
        self.assert_clean(app)
        return app

    def assert_clean(self, app):
        self.assertEqual(len(app.exception), 0, [error.message for error in app.exception])

    def markup(self, app):
        return "\n".join(item.value for item in app.markdown)

    def document(self, app):
        return MarkupParser(self.markup(app)).root

    def plots(self, app):
        return [json.loads(chart.proto.spec) for chart in app.get("plotly_chart")]

    def plot(self, app, key):
        charts = [chart for chart in app.get("plotly_chart") if chart.proto.id.endswith("-plot_" + key)]
        self.assertEqual(len(charts), 1, f"Missing or duplicated official chart: {key}")
        return json.loads(charts[0].proto.spec)

    def snapshot(self, app):
        return {
            node.find(class_name="label")[0].text: node.find(class_name="value")[0].text
            for node in self.document(app).find(class_name="kpi")
        }

    def test_official_snapshot_matches_loaded_artifacts(self):
        app = self.app()
        summary = self.adapter.retrieval["summary"]
        failures = self.adapter.workflow["results"]
        expected = {
            "Evaluation Queries": str(summary["total_queries"]),
            "Platforms": str(len(summary["by_platform"])),
            "Baseline Failures": str(sum(row.get("recall_at_k") == 0 for row in self.adapter.retrieval["results"])),
            "Verified Labelled Failures Improved": f'{sum(row["validation"]["verdict"] == "IMPROVED" for row in failures)}/{len(failures)}',
            "Baseline Recall@4": f'{summary["overall"]["recall_at_k"]:.1%}',
        }
        self.assertEqual(self.snapshot(app), expected)
        self.assertEqual(list(expected.values()), ["48", "4", "5", "5/5", "89.6%"])
        text = self.document(app).text
        self.assertIn("Official Evaluation Snapshot", text)
        self.assertIn("Based on the verified evaluation dataset", text)
        self.assertIn(
            f'Before → After covers the {len(failures)} verified failure runs. '
            f'A combined post-optimization result for all {summary["total_queries"]} evaluation queries is not recorded.',
            text,
        )
        self.assertNotIn("Latest Live Run", text)

    def test_dashboard_heading_and_status_are_evaluation_specific(self):
        app = self.app()
        document = self.document(app)
        self.assertEqual(document.find(tag="h1")[0].text.rstrip("."), "Evaluation Evidence at a Glance")
        self.assertEqual(document.find(class_name="nav-status")[0].text,
                         "Official Evaluation Saved evaluation artifacts")
        for page in ("overview", "architecture", "team", "action"):
            with self.subTest(page=page):
                app.query_params["page"] = page
                app.run()
                self.assert_clean(app)
                statuses = self.document(app).find(class_name="nav-status")
                if page == "architecture":
                    self.assertFalse(statuses, "Architecture omits the navbar mode/status")
                    continue
                expected = ("Live Runtime Unavailable Saved evidence is available" if page == "action"
                            else "Saved Evidence Mode Repository evaluation artifacts")
                self.assertEqual(len(statuses), 1)
                self.assertEqual(statuses[0].text, expected)

    def test_unusable_live_states_hide_the_entire_panel(self):
        for run in ({}, {"mode": "LIVE MODE"}, {"mode": "LIVE MODE", "query": "Question only"},
                    {"mode": "LIVE MODE", "query": "Question", "diagnosis_report": {}, "validation_result": {}},
                    {"mode": "LIVE MODE", "verified": True, "query": "Saved evidence", "optimization_proposal": {"action": "rewrite_query"}}):
            with self.subTest(run=run):
                app = self.app(run)
                self.assertNotIn("Latest Live Run", self.document(app).text)
                self.assertEqual(self.document(app).find(class_name="dashboard-live-fields"), [])

    def test_live_panel_uses_health_status_and_omits_unreported_fields(self):
        before = {"query": "Question", "retrieved_results": [{"text": "Relevant evidence", "relevant": True}]}
        healthy = {
            "mode": "LIVE MODE", "query": "Question", "before_run": before,
            "final_run": deepcopy(before), "final_status": "NO_ACTION_REQUIRED",
            "monitoring_report": {"failure_detected": False, "baseline_relevant_found": True},
            "diagnosis_report": {"issue_type": None, "recommended_action": "none"},
        }
        for run, expected in ((healthy, "Healthy baseline · No optimization required"),
                              ({"mode": "LIVE MODE", "query": "Question", "diagnosis_report": {"issue_type": "Query Mismatch"}}, "Query Mismatch")):
            with self.subTest(expected=expected):
                app = self.app(run)
                panel = self.document(app).find(class_name="dashboard-live-fields")
                self.assertEqual(len(panel), 1)
                self.assertIn(expected, panel[0].text)
                for absent in ("Not reported", "Not run", "Not formally validated", "Validation outcome"):
                    self.assertNotIn(absent, panel[0].text)
                self.assertEqual(app.session_state.current_run, run)

    def test_platform_chart_matches_each_stored_platform_metric(self):
        app = self.app()
        spec = self.plot(app, "chart_platform")
        self.assertEqual(len(spec["data"]), 3)
        source = self.adapter.retrieval["summary"]["by_platform"]
        keys = {"Recall@4": "recall_at_k", "Precision@4": "precision_at_k", "MRR": "mrr"}
        for trace in spec["data"]:
            self.assertEqual(set(trace["x"]), {platform.title() for platform in source})
            metric = keys[trace["name"]]
            self.assertEqual(trace["y"], [source[platform.casefold()][metric] for platform in trace["x"]])

    def test_failure_distribution_uses_workflow_diagnoses_only(self):
        app = self.app()
        traces = self.plot(app, "chart_failures")["data"]
        self.assertEqual(len(traces), 1)
        counts = dict(zip(traces[0]["labels"], traces[0]["values"]))
        self.assertEqual(counts, {"Query Mismatch": 4, "Top-K Retrieval": 1, "Chunking Quality": 0})
        self.assertEqual(sum(counts.values()), len(self.adapter.workflow["results"]))
        self.assertEqual({row["platform"] for row in self.adapter.workflow["results"]}, {"absher", "balady"})

    def test_validation_outcomes_exclude_workflow_approval(self):
        app = self.app()
        trace = self.plot(app, "chart_outcomes")["data"][0]
        self.assertEqual(trace["labels"], VERDICTS)
        self.assertEqual(trace["values"], [5, 0, 0])
        for chart in self.plots(app):
            for data in chart["data"]:
                labels = data.get("labels", [])
                self.assertFalse(any("approved" in label.casefold() or "rejected" in label.casefold() for label in labels))

    def test_before_after_charts_use_actual_recorded_validation(self):
        app = self.app()
        metrics = ("recall_at_k", "precision_at_k", "reciprocal_rank")
        records = self.adapter.workflow["results"]
        chart = self.plot(app, "chart_compare")
        self.assertEqual({trace["name"] for trace in chart["data"]}, {"Before", "After"})
        for trace in chart["data"]:
            phase = trace["name"].casefold()
            self.assertEqual(trace["x"], ["Recall@K", "Precision@K", "MRR"])
            expected = [math.fsum(row["validation"][phase][metric] for row in records) / len(records) for metric in metrics]
            for actual, recorded in zip(trace["y"], expected):
                self.assertAlmostEqual(actual, recorded)
        cards = self.document(app).find(class_name="metric-card")[:4]
        self.assertEqual([card.find(class_name="metric-name")[0].text for card in cards],
                         ["Recall@K", "Precision@K", "MRR (Mean Reciprocal Rank)", "Observed Retrieval Latency"])
        self.assertIn(f"Paired averages across {len(records)} verified failure runs only.", self.document(app).text)
        self.assertIn("Metrics use each run's configured K.", self.document(app).text)
        for card, metric in zip(cards, (*metrics, "latency_seconds")):
            before = math.fsum(row["validation"]["before"][metric] for row in records) / len(records)
            after = math.fsum(row["validation"]["after"][metric] for row in records) / len(records)
            improved = after < before if metric == "latency_seconds" else after > before
            direction = "neutral" if after == before else "good" if improved else "bad"
            self.assertIn(direction, card.find(class_name="metric-delta")[0].attrs["class"].split())

    def test_latency_is_measured_and_cases_are_available_in_hover(self):
        app = self.app()
        chart = self.plot(app, "chart_latency")
        records = self.adapter.workflow["results"]
        for trace in chart["data"]:
            phase = trace["name"].casefold()
            self.assertEqual(trace["x"], [f"Run {index}" for index in range(1, len(records) + 1)])
            self.assertEqual(trace["y"], [row["validation"][phase]["latency_seconds"] for row in records])
            self.assertTrue(all(row["id"] in json.dumps(trace.get("customdata", [])) for row in records))
        self.assertIn("Observed Retrieval Latency", self.document(app).text)
        self.assertIn("Recorded timings · hover for the stored case ID", self.document(app).text)
        self.assertIn("Observed timings do not establish a causal speedup from RAGOps.",
                      [caption.value for caption in app.caption])

    def test_chunking_sweep_matches_baseline_and_candidate_artifact(self):
        app = self.app()
        chart = self.plot(app, "chart_chunking")
        rows = sorted([self.adapter.chunk_sweep["baseline"], *self.adapter.chunk_sweep["candidates"]], key=lambda row: row["chunk_size"])
        keys = {"Recall@4": "recall_at_k", "Recall@K": "recall_at_k", "Precision@4": "precision_at_k", "Precision@K": "precision_at_k", "MRR": "mrr"}
        for trace in chart["data"]:
            self.assertEqual(trace["x"], [f'{row["chunk_size"]}/{row["chunk_overlap"]}' for row in rows])
            self.assertEqual(trace["y"], [row[keys[trace["name"]]] for row in rows])
        self.assertIn("Structural Experiment — Chunking Sweep", self.document(app).text)
        self.assertIn(f'Evaluated separately from the {len(self.adapter.workflow["results"])} verified failure cases.',
                      self.document(app).text)
        self.assertIn("Diamond = baseline. " + self.adapter.chunk_sweep["decision_policy"]
                      + " Permanent promotion decision not recorded.", [caption.value for caption in app.caption])

    def test_history_has_six_columns_and_real_ids_without_dates(self):
        app = self.app()
        table = app.dataframe[0].value
        self.assertEqual(list(table.columns), HISTORY_COLUMNS)
        self.assertEqual(set(table["Case"]), set(self.adapter.workflow_by_id))
        self.assertEqual(set(table["Decision"]), {"Auto-approved by policy"})
        self.assertEqual(set(table["Validation Verdict"]), {"Improved"})
        self.assertEqual(set(table["Action"]), {"Rewrite query", "Change Top-K"})
        next(widget for widget in app.text_input if widget.label == "Search runs").set_value("no matching saved run").run()
        self.assert_clean(app)
        self.assertTrue(any("No stored runs match" in caption.value for caption in app.caption))

    def test_inspector_matches_selected_record_with_collapsed_evidence(self):
        app = self.app()
        case_id = next(row["id"] for row in self.adapter.workflow["results"] if row["proposal"]["action"] == "change_top_k")
        app.selectbox(key="inspector_id").select(case_id).run()
        self.assert_clean(app)
        record = self.adapter.workflow_by_id[case_id]
        text = self.document(app).text
        self.assertIn(record["original_query"], text)
        self.assertIn("Auto-approved by policy", text)
        self.assertIn("Optimized retrieval", text)
        self.assertIn("Before", text)
        self.assertIn("After", text)
        cards = self.document(app).find(class_name="metric-card")[4:]
        self.assertEqual([card.find(class_name="metric-name")[0].text for card in cards],
                         ["Recall@K", "Precision@K", "Reciprocal Rank", "Observed Retrieval Latency"])
        self.assertEqual(cards[2].find(class_name="metric-before")[0].text,
                         f'{record["validation"]["before"]["reciprocal_rank"]:.2f}')
        self.assertEqual(cards[2].find(class_name="metric-after")[0].text,
                         f'{record["validation"]["after"]["reciprocal_rank"]:.2f}')
        self.assertFalse(any(widget.label == "Inspector view" for widget in app.radio))
        self.assertTrue(app.expander)
        self.assertTrue(all(not disclosure.proto.expanded for disclosure in app.expander))

    def test_mobile_history_inspection_changes_only_selected_case(self):
        app = self.app()
        official = self.snapshot(app), self.plots(app)
        records = self.adapter.workflow["results"]
        case_ids = {row["id"] for row in records}
        history = [disclosure for disclosure in app.expander if disclosure.label in case_ids]
        self.assertEqual({disclosure.label for disclosure in history}, case_ids)
        self.assertTrue(all(not disclosure.proto.expanded for disclosure in history))
        for row in records:
            button = app.button(key="dashboard_inspect_" + row["id"])
            self.assertEqual(button.label, "Inspect case")
        case = records[1]
        app.button(key="dashboard_inspect_" + case["id"]).click().run()
        self.assert_clean(app)
        self.assertEqual(app.selectbox(key="inspector_id").value, case["id"])
        query = self.document(app).find(class_name="dashboard-inspector-query")
        self.assertEqual(len(query), 1)
        self.assertIn(case["original_query"], query[0].text)
        self.assertEqual(official, (self.snapshot(app), self.plots(app)))

    def test_optional_live_panel_cannot_change_official_results_or_session(self):
        app = self.app()
        official = self.snapshot(app), self.plots(app), app.dataframe[0].value.to_dict("records")
        run = recorded_run(self.adapter, next(iter(self.adapter.workflow_by_id)))
        run["mode"] = "LIVE MODE"
        run["verified"] = False  # Test-only genuine-live shape, not a saved replay.
        run["validation_result"]["verdict"] = "WORSE"  # Test-only session input.
        app.session_state.current_run = deepcopy(run)
        app.run()
        self.assert_clean(app)
        self.assertIn("Latest Live Run", self.document(app).text)
        self.assertIn("Current Session — separate from official evaluation", self.document(app).text)
        self.assertEqual(official, (self.snapshot(app), self.plots(app), app.dataframe[0].value.to_dict("records")))
        self.assertEqual(app.session_state.current_run, run)


if __name__ == "__main__":
    unittest.main()
