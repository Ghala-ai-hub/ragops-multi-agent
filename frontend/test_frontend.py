"""Read-only UI regression checks. Run: python -B -m unittest frontend.test_frontend.

Real live execution, answer generation, index construction, and runtime
credential mutation are blocked. Explicit mocks test frontend orchestration.
"""
from __future__ import annotations

import ast
from copy import deepcopy
import json
import unittest
from html.parser import HTMLParser
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

from streamlit.testing.v1 import AppTest

from frontend.adapter import FrontendAdapter, RuntimeStatus, STRUCTURAL_CASE_ID
from frontend.presentation import approval_view, normalized_trace, safe_state

ROOT = Path(__file__).resolve().parents[1]


class FailureCardParser(HTMLParser):
    """Inspect actual rendered navigation semantics instead of matching CSS text."""

    def __init__(self):
        super().__init__()
        self.cards = {}
        self.current_kind = None
        self.current_tag = None

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        classes = attributes.get("class", "").split()
        if "failure-card" in classes:
            self.current_kind = attributes["data-failure-kind"]
            self.current_tag = tag
            self.cards[self.current_kind] = {"tag": tag, "attrs": attributes, "arrows": 0}
        elif self.current_kind and "failure-arrow" in classes:
            self.cards[self.current_kind]["arrows"] += 1

    def handle_endtag(self, tag):
        if tag == self.current_tag:
            self.current_kind = None
            self.current_tag = None


class MarkupNode:
    """A small rendered-markup tree for links and diagram semantics."""

    def __init__(self, tag="root", attrs=None):
        self.tag = tag
        self.attrs = attrs or {}
        self.children = []

    @property
    def text(self):
        return " ".join(" ".join(child.text if isinstance(child, MarkupNode) else child for child in self.children).split())

    def find(self, *, tag=None, class_name=None, **attrs):
        result = []
        for child in self.children:
            if not isinstance(child, MarkupNode):
                continue
            if (tag is None or child.tag == tag) and (class_name is None or class_name in child.attrs.get("class", "").split()) and all(child.attrs.get(key) == value for key, value in attrs.items()):
                result.append(child)
            result.extend(child.find(tag=tag, class_name=class_name, **attrs))
        return result


class MarkupParser(HTMLParser):
    VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}

    def __init__(self, markup):
        super().__init__()
        self.root = MarkupNode()
        self.stack = [self.root]
        self.feed(markup)

    def handle_starttag(self, tag, attrs):
        node = MarkupNode(tag, dict(attrs))
        self.stack[-1].children.append(node)
        if tag not in self.VOID:
            self.stack.append(node)

    def handle_endtag(self, tag):
        for index in range(len(self.stack) - 1, 0, -1):
            if self.stack[index].tag == tag:
                del self.stack[index:]
                return

    def handle_data(self, data):
        self.stack[-1].children.append(data)


class FrontendChecks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.adapter = FrontendAdapter()
        cls.blockers = []
        for method in ("run_live", "resume_live", "build_evaluation_index", "set_session_api_key"):
            blocker = patch.object(FrontendAdapter, method, side_effect=AssertionError("Live backend operations are prohibited during verification"))
            cls.blockers.append((blocker, blocker.start()))
        cls.runtime_patch = patch.object(FrontendAdapter, "runtime_status", return_value=RuntimeStatus(False, False, False, False))
        cls.runtime_patch.start()
        cls.answer_patch = patch("frontend.answers.generate_final_answer", return_value=None)
        cls.answer_mock = cls.answer_patch.start()
        cls.context_patch = patch("frontend.conversation.resolve_followup", side_effect=lambda query, messages: {
            "query":query, "clarification":None, "contextualized":False,
        })
        cls.context_patch.start()
        cls.tracing_patch = patch("frontend.observability.tracing_settings", return_value=SimpleNamespace(enabled=False, project="offline-ui-tests"))
        cls.tracing_patch.start()
        cls.dotenv_patch = patch("dotenv.load_dotenv", return_value=False)
        cls.dotenv_patch.start()

    @classmethod
    def tearDownClass(cls):
        try:
            for _, mocked in cls.blockers:
                mocked.assert_not_called()
        finally:
            for blocker, _ in cls.blockers:
                blocker.stop()
            cls.runtime_patch.stop()
            cls.answer_patch.stop()
            cls.context_patch.stop()
            cls.tracing_patch.stop()
            cls.dotenv_patch.stop()

    def app(self, page, **query_params):
        app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=20)
        app.query_params["page"] = page
        for key, value in query_params.items():
            app.query_params[key] = value
        app.run()
        self.assertEqual(len(app.exception), 0, [e.message for e in app.exception])
        return app

    def assert_clean(self, app):
        self.assertEqual(len(app.exception), 0, [e.message for e in app.exception])

    def saved_app(self):
        app = self.app("action")
        app.radio(key="mode_choice").set_value("View Saved Runs").run()
        self.assert_clean(app)
        return app

    def markup(self, app):
        return "\n".join(item.value for item in app.markdown)

    def failure_cards(self, app):
        parser = FailureCardParser()
        parser.feed(self.markup(app))
        self.assertEqual(set(parser.cards), {"top-k", "query-mismatch", "structural"})
        return parser.cards

    def test_python_syntax(self):
        for path in [ROOT / "app.py", *(ROOT / "frontend").glob("*.py")]:
            ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))

    def test_all_five_pages(self):
        for page in ("overview", "action", "dashboard", "architecture", "team"):
            with self.subTest(page=page):
                app = self.app(page)
                markup = self.markup(app)
                statuses = MarkupParser(markup).root.find(class_name="nav-status")
                if page == "architecture":
                    self.assertFalse(statuses, "Architecture has no navbar mode/status")
                else:
                    expected_status = {"action": "Live Runtime Unavailable", "dashboard": "Official Evaluation"}.get(page, "Saved Evidence Mode")
                    self.assertEqual(len(statuses), 1)
                    self.assertIn(expected_status, statuses[0].text)
                self.assertNotIn("All systems online", markup)
                self.assertNotIn("DEMO READY", markup)
                self.assertEqual(markup.count('aria-current=page'), 1)

    def test_empty_action_has_no_human_controls(self):
        app = self.app("action")
        app.button(key="new_chat").click().run()
        self.assertFalse(any("Approve" in b.label or "Reject" in b.label for b in app.button))
        self.assertEqual(len(normalized_trace(None)), 7)
        self.assertTrue(all(s["status"] == "waiting" for s in normalized_trace(None)))

    def test_overview_links_open_the_backed_saved_cases(self):
        cards = self.failure_cards(self.app("overview"))
        expected_actions = {
            "top-k": "change_top_k",
            "query-mismatch": "rewrite_query",
        }
        self.assertEqual(cards["structural"]["tag"], "article")
        self.assertEqual(cards["structural"]["arrows"], 0)
        self.assertNotIn("href", cards["structural"]["attrs"])
        for kind, action in expected_actions.items():
            with self.subTest(kind=kind):
                card = cards[kind]
                self.assertEqual(card["tag"], "a")
                self.assertEqual(card["arrows"], 1)
                self.assertIn("interactive", card["attrs"]["class"].split())
                self.assertEqual(card["attrs"]["target"], "_self")
                self.assertTrue(card["attrs"]["aria-label"].startswith("Inspect verified "))
                route = parse_qs(urlsplit(card["attrs"]["href"]).query)
                self.assertEqual(route["page"], ["action"])
                case_id = route["case"][0]
                from frontend.evidence import recorded_run
                self.assertEqual(recorded_run(self.adapter, case_id)["optimization_proposal"]["action"], action)
                app = self.app("action", case=case_id)
                self.assertEqual(app.session_state.saved_run["case_id"], case_id)
                self.assertEqual(app.session_state.saved_run["optimization_proposal"]["action"], action)
                self.assertEqual(app.session_state.case_picker, case_id)
                self.assertEqual(app.session_state.selected_case_id, case_id)
                self.assertEqual(app.session_state.runtime_mode, "VERIFIED DEMO MODE")
                self.assertIn("Auto-approved by policy", self.markup(app))
                self.assertFalse(any("Approve" in button.label or "Reject" in button.label for button in app.button))

    def test_synthetic_structural_case_is_not_a_saved_run(self):
        from frontend.evidence import recorded_cases, recorded_run
        cases = recorded_cases(self.adapter)
        self.assertEqual(len(cases), 5)
        self.assertEqual({case["id"] for case in cases}, set(self.adapter.workflow_by_id))
        with self.assertRaises(KeyError):
            recorded_run(self.adapter, STRUCTURAL_CASE_ID)
        app = self.app("action", case=STRUCTURAL_CASE_ID)
        self.assertFalse(any(button.key in {"approve_optimization", "reject_optimization"} for button in app.button))
        self.assertEqual(len(app.selectbox(key="case_picker").options), 6)
        self.assertNotIn("Structural · Chunking Quality", app.selectbox(key="case_picker").options)
        with self.assertRaises(KeyError):
            _ = app.session_state["current_run"]

    def test_overview_without_structural_evidence_has_no_structural_link(self):
        dashboard = self.adapter.dashboard()
        for missing in ("chunking_candidates", "chunking_baseline"):
            with self.subTest(missing=missing):
                unavailable = {**dashboard, missing: [] if missing == "chunking_candidates" else {}}
                with patch.object(FrontendAdapter, "dashboard", return_value=unavailable):
                    cards = self.failure_cards(self.app("overview"))
                structural = cards["structural"]
                self.assertEqual(structural["tag"], "article")
                self.assertNotIn("href", structural["attrs"])
                self.assertNotIn("interactive", structural["attrs"]["class"].split())
                self.assertEqual(structural["arrows"], 0)
                self.assertEqual(cards["top-k"]["tag"], "a")
                self.assertEqual(cards["query-mismatch"]["tag"], "a")

    def test_overview_snapshot_and_domain_agnostic_framing(self):
        markup = self.markup(self.app("overview"))
        self.assertIn('aria-label="24 Indexed Services"', markup)
        self.assertIn('aria-label="48 Evaluation Queries"', markup)
        self.assertIn('aria-label="5/5 Failed Cases Improved"', markup)
        self.assertIn('aria-label="89.6% Baseline Recall@4"', markup)
        self.assertIn("EVALUATION SNAPSHOT", markup)
        self.assertIn("domain-agnostic operations layer", markup)
        self.assertIn("across knowledge domains", markup)
        self.assertIn("Demo corpus: Absher · Balady · Najiz · Sakani", markup)
        cue = MarkupParser(markup).root.find(class_name="overview-scroll-cue")
        self.assertEqual(len(cue), 1)
        self.assertEqual(cue[0].text, "Explore more ↓")
        self.assertEqual(cue[0].attrs["href"], "#evaluation-snapshot")

    def test_team_supplied_content_and_safe_profile_links(self):
        from frontend.config import TEAM, TEAM_LINKEDIN

        expected = {
            "Jawaher": ("Data + Monitoring", "Builds the data and monitoring layer that makes retrieval quality observable.", "cyan", "https://www.linkedin.com/in/jawaher-khalifah-4277242a0"),
            "Ghala": ("Evaluation + Diagnosis", "Evaluates retrieval behavior and diagnoses the root cause of failures.", "teal", "https://www.linkedin.com/in/ghala-bander-alsuna-allah"),
            "Hanan": ("Models + Optimization", "Designs targeted model and retrieval optimizations.", "violet", "https://www.linkedin.com/in/hannansulaiman"),
            "Hajer": ("Validation + Integration + Frontend", "Validates impact and connects the workflow into the end-to-end product experience.", "amber", "https://www.linkedin.com/in/hajeralsaleh"),
        }
        self.assertEqual([member["name"] for member in TEAM], list(expected))
        self.assertEqual(TEAM_LINKEDIN, {name: values[3] for name, values in expected.items()})
        markup = self.markup(self.app("team"))
        document = MarkupParser(markup).root
        cards = document.find(class_name="team-card")
        self.assertEqual(len(cards), 4)
        self.assertIn("TEAM · OWNERSHIP · COLLABORATION", document.text)
        self.assertIn("Concept illustrations are symbolic and do not depict actual team members.", document.text)
        self.assertNotIn("LinkedIn not configured", document.text)
        for member, card in zip(TEAM, cards):
            name = member["name"]
            role, description, accent, destination = expected[name]
            with self.subTest(member=name):
                self.assertEqual(member["role"], role)
                self.assertEqual(member["description"], description)
                self.assertEqual(member["accent"], accent)
                self.assertEqual(card.find(class_name="team-name")[0].text, name)
                self.assertEqual(card.find(class_name="team-role")[0].text, role)
                self.assertEqual(card.find(class_name="team-description")[0].text, description)
                self.assertIn("theme-" + accent, card.attrs["class"].split())
                links = card.find(tag="a")
                self.assertTrue(links)
                for link in links:
                    self.assertEqual(link.attrs["href"], destination)
                    self.assertEqual(link.attrs["target"], "_blank")
                    self.assertTrue({"noopener", "noreferrer"}.issubset(link.attrs.get("rel", "").split()))
                self.assertEqual(card.find(class_name="team-link")[0].text, "LinkedIn ↗")
                self.assertEqual(len(card.find(class_name="svg-avatar")), 1)
        stack = document.find(class_name="stack-items")
        self.assertEqual(len(stack), 1)
        self.assertEqual(stack[0].text.split(), ["Python", "Streamlit", "LangGraph", "LangChain", "OpenAI", "FAISS", "Plotly"])

    def test_architecture_routes_match_risk_policy(self):
        document = MarkupParser(self.markup(self.app("architecture"))).root
        diagrams = document.find(class_name="architecture-flow")
        self.assertEqual(len(diagrams), 1)
        diagram = diagrams[0]
        boards = diagram.find(class_name="architecture-layout")
        self.assertEqual(len(boards), 1, "Use a single board for wide and narrow viewports")
        self.assertFalse(diagram.find(class_name="architecture-merge-mobile"))
        self.assertFalse(diagram.find(class_name="architecture-mobile-flow"))
        nodes = [node for node in diagram.find() if "data-node" in node.attrs]
        board_nodes = [node for node in boards[0].find() if "data-node" in node.attrs]
        self.assertEqual(len(nodes), len(board_nodes), "Every workflow node belongs to the same board")
        by_id = {node.attrs["data-node"]: node for node in nodes}
        self.assertEqual(len(nodes), len(by_id), "Diagram nodes must be unique on desktop and mobile")
        expected_roles = {
            "user-query": "INPUT", "baseline-rag": "SYSTEM", "monitoring": "AGENT 01",
            "retrieval-health": "CONTROL", "baseline-accepted": "OUTCOME",
            "diagnosis": "AGENT 02", "optimization": "AGENT 03", "risk-gate": "CONTROL",
            "auto-approved": "CONTROL", "human-approval": "CONTROL", "action-executor": "SYSTEM",
            "validation": "AGENT 04", "validation-decision": "CONTROL",
            "optimized-accepted": "OUTCOME", "baseline-unchanged": "OUTCOME", "baseline-worse": "OUTCOME",
            "baseline-retained": "OUTCOME", "final-answer": "SYSTEM",
        }
        self.assertEqual({name: node.attrs.get("data-role") for name, node in by_id.items()}, expected_roles)
        self.assertEqual(sum(node.attrs["data-role"].startswith("AGENT") for node in nodes), 4)
        paths = diagram.find(class_name="arch-link")
        edges = {
            (path.attrs["data-from"], path.attrs["data-to"], path.attrs["data-route"])
            for path in paths
        }
        self.assertEqual(len(paths), len(edges), "Narrow screens must reuse the same flow connections")
        required = {
            ("user-query", "baseline-rag", "shared"), ("baseline-rag", "monitoring", "shared"),
            ("monitoring", "retrieval-health", "shared"), ("retrieval-health", "diagnosis", "unhealthy"),
            ("retrieval-health", "baseline-accepted", "healthy"), ("baseline-accepted", "final-answer", "healthy"),
            ("diagnosis", "optimization", "shared"),
            ("optimization", "risk-gate", "shared"), ("risk-gate", "auto-approved", "low"),
            ("auto-approved", "action-executor", "low"), ("risk-gate", "human-approval", "high"),
            ("human-approval", "action-executor", "approved"), ("human-approval", "baseline-retained", "rejected"),
            ("baseline-retained", "final-answer", "rejected"),
            ("action-executor", "validation", "shared"), ("validation", "validation-decision", "shared"),
            ("validation-decision", "optimized-accepted", "improved"),
            ("validation-decision", "baseline-unchanged", "same"),
            ("validation-decision", "baseline-worse", "worse"),
            ("optimized-accepted", "final-answer", "shared"),
            ("baseline-unchanged", "final-answer", "shared"),
            ("baseline-worse", "final-answer", "shared"),
        }
        self.assertEqual(edges, required, "The board must show the conditional run, not unconditional optimization or a future-cycle loop")
        self.assertTrue(all(source in by_id and target in by_id for source, target, _ in edges))

        def reached(routes, start="user-query"):
            visited, pending = set(), [start]
            while pending:
                node = pending.pop()
                if node in visited:
                    continue
                visited.add(node)
                pending.extend(target for source, target, route in edges if source == node and route in routes)
            return visited

        healthy = reached({"shared", "healthy"})
        self.assertEqual(healthy, {"user-query", "baseline-rag", "monitoring", "retrieval-health", "baseline-accepted", "final-answer"})
        self.assertTrue({"diagnosis", "optimization", "risk-gate", "action-executor", "validation"}.isdisjoint(healthy))

        low = reached({"shared", "unhealthy", "low", "improved"})
        self.assertTrue({"diagnosis", "optimization", "auto-approved", "action-executor", "validation", "validation-decision", "optimized-accepted", "final-answer"}.issubset(low))
        self.assertNotIn("human-approval", low)
        self.assertTrue({"baseline-accepted", "baseline-retained", "baseline-unchanged", "baseline-worse"}.isdisjoint(low))
        high = reached({"shared", "unhealthy", "high", "approved", "improved"})
        self.assertTrue({"human-approval", "action-executor", "validation", "optimized-accepted", "final-answer"}.issubset(high))
        self.assertTrue({"auto-approved", "baseline-retained"}.isdisjoint(high))
        rejected = reached({"shared", "unhealthy", "high", "rejected"})
        self.assertTrue({"human-approval", "baseline-retained", "final-answer"}.issubset(rejected))
        self.assertTrue({"auto-approved", "action-executor", "validation", "validation-decision", "optimized-accepted"}.isdisjoint(rejected))
        self.assertIn("No execution", by_id["baseline-retained"].text)

        for verdict, outcome in (("improved", "optimized-accepted"), ("same", "baseline-unchanged"), ("worse", "baseline-worse")):
            with self.subTest(verdict=verdict):
                self.assertEqual(reached({"shared", verdict}, "validation-decision"), {"validation-decision", outcome, "final-answer"})
                for approval in ({"low"}, {"high", "approved"}):
                    traversed = reached({"shared", "unhealthy", verdict} | approval)
                    self.assertTrue({"action-executor", "validation", "validation-decision", outcome, "final-answer"}.issubset(traversed))
                self.assertNotIn("No execution", by_id[outcome].text)

        self.assertFalse(any(source == "final-answer" for source, _, _ in edges), "The grounded answer is the output of this run")
        self.assertFalse(any("validation-feedback" in (source, target) for source, target, _ in edges), "Removed feedback annotation must not appear in the workflow")
        self.assertEqual({source for source, target, _ in edges if target == "baseline-rag"}, {"user-query"})
        self.assertEqual({source for source, target, _ in edges if target == "monitoring"}, {"baseline-rag"})
        self.assertIn("Retrieval healthy?", by_id["retrieval-health"].text)
        self.assertIn("Baseline accepted", by_id["baseline-accepted"].text)
        self.assertIn("Final Grounded Answer", by_id["final-answer"].text)
        self.assertNotIn("validation-feedback", by_id)
        self.assertFalse(document.find(class_name="nav-status"))
        self.assertIn("Auto-approved by policy", by_id["auto-approved"].text)
        self.assertIn("rewrite_query", diagram.text)
        self.assertIn("change_top_k", diagram.text)
        self.assertIn("rechunk_and_reindex", diagram.text)
        for removed in ("Validation Feedback", "Feedback Loop", "Next retrieval cycle", "THE TARGETED-OPTIMIZATION PATH", "Conceptual flow", "Optimization proposal", "Continue at Risk Gate below", "Candidate evaluation does not automatically promote the active index."):
            self.assertNotIn(removed, diagram.text)
        controls = diagram.find(class_name="arch-route-control")
        self.assertTrue({"low", "high", "rejected"}.issubset({control.attrs["data-route"] for control in controls}))
        self.assertTrue(all(control.tag == "button" or control.attrs.get("tabindex") == "0" for control in controls))

    def test_architecture_panels_and_optional_observability(self):
        from frontend.adapter import RuntimeStatus

        with patch.object(FrontendAdapter, "runtime_status", return_value=RuntimeStatus(False, False, False, False)):
            app = self.app("architecture")
        document = MarkupParser(self.markup(app)).root
        page_text = document.text + " " + " ".join(caption.value for caption in app.caption)
        for field in ("query", "monitoring_report", "diagnosis_report", "optimization_proposal", "approval_result", "execution_result", "before_run / after_run", "validation_result", "trace"):
            self.assertIn(field, page_text)
        self.assertEqual([expander.label for expander in app.expander], ["View Shared State"])
        self.assertFalse(app.expander[0].proto.expanded)
        self.assertNotIn("Control Policy", page_text)
        self.assertIn("LangGraph", page_text)
        self.assertIn("LangSmith", page_text)
        self.assertIn("Tracing: Off", page_text)
        captions = [caption.value for caption in app.caption]
        self.assertIn("Workflow orchestration · shared state · interrupt/resume", captions)
        self.assertIn("Optional observability", captions)
        self.assertNotIn("All systems online", page_text)
        self.assertNotIn("LangSmith is required", page_text)
        self.assertTrue("interrupt/resume" in page_text or "interrupt / resume" in page_text)

    def test_saved_low_impact_actions_never_pause(self):
        from frontend.evidence import recorded_cases
        names = ["Baseline RAG", "Monitoring", "Diagnosis", "Optimization", "Risk Gate", "Action Executor", "Validation"]
        for case in recorded_cases(self.adapter):
            with self.subTest(case=case["id"]):
                app = self.saved_app()
                app.selectbox(key="case_picker").select(case["id"]).run()
                app.button(key="view_saved_run").click().run()
                self.assert_clean(app)
                self.assertIn("Auto-approved by policy", self.markup(app))
                self.assertFalse(any("Approve" in b.label or "Reject" in b.label for b in app.button))
                self.assertEqual(app.session_state.saved_run["case_id"], case["id"])
                trace_names = [node.text for node in MarkupParser(self.markup(app)).root.find(class_name="trace-name")]
                self.assertEqual(trace_names, names)
                evidence = [expander for expander in app.expander if expander.label == "View Baseline Retrieval"]
                self.assertEqual(len(evidence), 1)
                self.assertFalse(evidence[0].proto.expanded)
                self.assertIn("Saved evaluation record", self.markup(app))
                self.assertFalse(app.chat_message)

    def test_live_is_primary_even_when_runtime_is_unavailable_without_execution(self):
        for ready in (False, True):
            with self.subTest(ready=ready), patch.object(FrontendAdapter, "runtime_status", return_value=RuntimeStatus(ready, ready, ready, False)):
                app = self.app("action")
                self.assertEqual(app.radio(key="mode_choice").options, ["Live Run", "View Saved Runs"])
                self.assertEqual(app.session_state.runtime_mode, "LIVE MODE")
                self.assertEqual(app.radio(key="mode_choice").value, "Live Run")
                self.assertEqual(app.button(key="send_message").disabled, not ready)
                self.assertTrue(all(stage["status"] == "waiting" for stage in normalized_trace(None)))
                self.assertFalse(MarkupParser(self.markup(app)).root.find(class_name="metric-card"))

    def test_live_interrupts_resume_only_through_mocked_adapter(self):
        """Test orchestration with explicit local mocks; real API methods stay blocked."""
        payload = {"type":"human_approval_required", "action":"rechunk_and_reindex", "parameters":{"chunk_size":750,"chunk_overlap":150}}
        for shape, interrupt in (("dict", {"value":payload}), ("object", SimpleNamespace(value=payload))):
            for decision in ("approve", "reject"):
                with self.subTest(shape=shape, decision=decision):
                    workflow = SimpleNamespace(action_executor=SimpleNamespace(rechunk_candidate=lambda _: None))
                    pending = {"query":"Frontend orchestration fixture", "__interrupt__":[interrupt]}
                    resumed = {"query":pending["query"], "optimization_proposal":{"action":"rechunk_and_reindex"},
                               "approval_result":{"approval_status":"approved" if decision == "approve" else "rejected", "human_decision":decision},
                               "final_status":"COMPLETED" if decision == "approve" else "REJECTED"}
                    with patch.object(FrontendAdapter, "runtime_status", return_value=RuntimeStatus(True, True, True, False)), \
                         patch.object(FrontendAdapter, "run_live", return_value={"state":pending,"workflow":workflow,"thread_id":"frontend-test-only"}) as run_mock, \
                         patch.object(FrontendAdapter, "resume_live", return_value=resumed) as resume_mock:
                        app = self.app("action")
                        app.text_area(key="query_text").set_value(pending["query"]).run()
                        app.button(key="send_message").click().run()
                        self.assert_clean(app)
                        run_mock.assert_called_once_with(pending["query"])
                        resume_mock.assert_not_called()
                        self.assertTrue(approval_view(app.session_state.current_run)["requires_decision"])
                        self.assertEqual([stage["name"] for stage in normalized_trace(app.session_state.current_run)], ["Baseline RAG","Monitoring","Diagnosis","Optimization","Risk Gate","Action Executor","Validation"])
                        self.assertFalse(MarkupParser(self.markup(app)).root.find(class_name="metric-card"))
                        self.assertIsNotNone(app.button(key="approve_optimization"))
                        self.assertIsNotNone(app.button(key="reject_optimization"))
                        app.button(key=f"{decision}_optimization").click().run()
                        self.assert_clean(app)
                        resume_mock.assert_called_once_with(workflow, "frontend-test-only", decision)
                        self.assertFalse(approval_view(app.session_state.current_run)["requires_decision"])
                        self.assertFalse(any(button.key in {"approve_optimization","reject_optimization"} for button in app.button))
                        self.assertFalse(MarkupParser(self.markup(app)).root.find(class_name="metric-card"))

    def test_live_no_action_keeps_validation_absent(self):
        for outcome in ("NO_ACTION_REQUIRED", "NEEDS_REVIEW"):
            with self.subTest(outcome=outcome), patch.object(FrontendAdapter, "runtime_status", return_value=RuntimeStatus(True, True, True, False)), \
                 patch.object(FrontendAdapter, "run_live", return_value={"state":{"final_status":outcome},"workflow":object(),"thread_id":"frontend-terminal-fixture"}) as run_mock:
                app = self.app("action")
                app.text_area(key="query_text").set_value("Frontend terminal fixture").run()
                app.button(key="send_message").click().run()
                self.assert_clean(app)
                run_mock.assert_called_once()
                document = MarkupParser(self.markup(app)).root
                self.assertEqual(len(document.find(class_name="trace-name")), 7)
                self.assertFalse(document.find(class_name="metric-grid"))
                self.assertFalse(document.find(class_name="verdict"))
                self.assertIn("Formal Before/After metrics unavailable for this unlabelled query", " ".join(item.value for item in app.caption))
                self.assertFalse(any(button.key in {"approve_optimization","reject_optimization"} for button in app.button))

    def test_live_answer_is_displayed_once_with_real_sources_and_rtl(self):
        query = "كيف أقدم طلب الخدمة؟"
        source = {"rank":3, "source":"دليل الخدمة.pdf", "text":"أرفق النموذج المكتمل. " + "شرح المستند. " * 35 + "RAW_END_MARKER", "chunk_index":12, "relevant":True}
        final_run = {"query":query, "retrieved_results":[source]}
        state = {"query":query, "final_status":"NO_ACTION_REQUIRED", "before_run":deepcopy(final_run), "final_run":deepcopy(final_run)}
        answer = {"text":"أرفق النموذج المكتمل. [1]\n<script>test-only text</script>", "sources":[{"citation":1,"document":deepcopy(source)}], "status":"answered", "evidence":"baseline"}
        with patch.object(FrontendAdapter, "runtime_status", return_value=RuntimeStatus(True, True, True, False)), \
             patch.object(FrontendAdapter, "run_live", return_value={"state":state,"workflow":object(),"thread_id":"answer-test-only"}) as run_mock, \
             patch("frontend.answers.generate_final_answer", return_value=answer) as answer_mock:
            app = self.app("action")
            app.text_area(key="query_text").set_value(query).run()
            answer_mock.assert_not_called()
            app.button(key="send_message").click().run()
            self.assert_clean(app)
            run_mock.assert_called_once_with(query)
            answer_mock.assert_called_once()
            self.assertEqual(answer_mock.call_args.args[0]["final_run"], final_run)
            self.assertEqual(app.session_state.current_run["answer_result"], answer)
            self.assertEqual([message.name for message in app.chat_message], ["user", "assistant"])
            self.assertIn("person", app.chat_message[0].avatar)
            self.assertIn("smart_toy", app.chat_message[1].avatar)
            markup = self.markup(app)
            answer_elements = [item for item in app.chat_message[1].markdown if item.value == answer["text"]]
            self.assertEqual(len(answer_elements), 1)
            self.assertFalse(answer_elements[0].allow_html, "Model text must use Streamlit's safe Markdown renderer")
            self.assertTrue(all("<script>test-only text</script>" not in item.value for item in app.markdown if item.allow_html))
            self.assertIn(f'.st-key-live_answer_text_{app.session_state.current_run["turn_id"]} [data-testid="stMarkdownContainer"] {{direction:rtl;', markup)
            self.assertIn("أرفق النموذج المكتمل. [1]", markup)
            self.assertIn("View full evidence", [expander.label for expander in app.expander])
            assistant_markup = "\n".join(item.value for item in app.chat_message[1].markdown)
            assistant_document = MarkupParser(assistant_markup).root
            self.assertTrue(all(node.attrs.get("dir") == "auto" for node in assistant_document.find(class_name="evidence-content")))
            chips = assistant_document.find(class_name="action-source-chip")
            self.assertEqual(len(chips), 1)
            self.assertIn(source["source"], chips[0].text)
            self.assertEqual(chips[0].attrs.get("dir"), "auto")
            excerpts = assistant_document.find(class_name="action-source-excerpt")
            self.assertTrue(excerpts)
            self.assertTrue(all(len(node.text) < 220 and "RAW_END_MARKER" not in node.text for node in excerpts))
            self.assertTrue(all(not expander.proto.expanded for expander in app.chat_message[1].expander))
            self.assertIn(source, [json.loads(item.value) for item in app.chat_message[1].json])
            self.assertFalse(MarkupParser(markup).root.find(class_name="metric-grid"))
            app.run()
            self.assert_clean(app)
            answer_mock.assert_called_once()
            run_mock.assert_called_once()
            app.text_area(key="query_text").set_value("A different question").run()
            self.assertEqual([message.name for message in app.chat_message], ["user", "assistant"])
            self.assertEqual(app.session_state.current_run["query"], query)
            self.assertEqual(app.session_state.current_run["answer_result"], answer)
            answer_mock.assert_called_once()

    def test_answer_failure_can_retry_without_retrieval_or_leaking_provider_details(self):
        query = "How do I submit the form?"
        final_run = {"retrieved_results":[{"source":"form.txt", "text":"Submit a completed form.", "relevant":True}]}
        state = {"query":query, "final_status":"NEEDS_REVIEW", "before_run":deepcopy(final_run), "final_run":deepcopy(final_run)}
        answer = {"text":"Submit a completed form. [1]", "sources":[{"citation":1,"document":final_run["retrieved_results"][0]}], "status":"answered", "evidence":"baseline"}
        with patch.object(FrontendAdapter, "runtime_status", return_value=RuntimeStatus(True, True, True, False)), \
             patch.object(FrontendAdapter, "run_live", return_value={"state":state,"workflow":object(),"thread_id":"answer-retry-test"}) as run_mock, \
             patch("frontend.answers.generate_final_answer", side_effect=[RuntimeError("test-only provider detail"), answer]) as answer_mock:
            app = self.app("action")
            app.text_area(key="query_text").set_value(query).run()
            app.button(key="send_message").click().run()
            self.assert_clean(app)
            self.assertTrue(app.session_state.current_run["answer_error"])
            self.assertEqual(app.session_state.current_run["final_run"], final_run)
            self.assertEqual([message.name for message in app.chat_message], ["user"])
            visible = self.markup(app) + " ".join(item.value for item in app.warning) + " ".join(item.value for item in app.error)
            self.assertNotIn("test-only provider detail", visible)
            self.assertTrue(any("Retrieval completed" in item.value for item in app.warning))
            self.assertFalse(any("workflow could not complete" in item.value for item in app.error))
            app.run()
            self.assertEqual(answer_mock.call_count, 1, "Rerenders must not automatically retry paid generation")
            app.button(key="retry_answer").click().run()
            self.assert_clean(app)
            self.assertEqual(answer_mock.call_count, 2)
            run_mock.assert_called_once_with(query)
            self.assertFalse(app.session_state.current_run.get("answer_error"))
            self.assertEqual(app.session_state.current_run["answer_result"], answer)
            self.assertEqual([message.name for message in app.chat_message], ["user", "assistant"])
            self.assertIn(f'.st-key-live_answer_text_{app.session_state.current_run["turn_id"]} [data-testid="stMarkdownContainer"] {{direction:ltr;', self.markup(app))
            self.assertFalse(any(button.key == "retry_answer" for button in app.button))
            self.assertTrue(any("not formally validated" in caption.value for caption in app.caption))

    def test_pending_review_has_no_answer_until_mocked_resume_selects_final_evidence(self):
        query = "Answer after structural review"
        source = {"source":"retained.txt", "text":"The retained baseline procedure.", "relevant":True}
        baseline = {"retrieved_results":[source]}
        pending = {"query":query, "before_run":baseline, "__interrupt__":[{"value":{"type":"human_approval_required", "action":"rechunk_and_reindex"}}]}
        resumed = {"query":query, "before_run":deepcopy(baseline), "final_run":deepcopy(baseline), "final_status":"REJECTED",
                   "optimization_proposal":{"action":"rechunk_and_reindex"}, "approval_result":{"approval_status":"rejected", "human_decision":"reject"}}
        answer = {"text":"The baseline procedure is retained. [1]", "sources":[{"citation":1,"document":source}], "status":"answered", "evidence":"baseline"}
        workflow = object()

        def generated(run):
            return deepcopy(answer) if run.get("final_status") == "REJECTED" else None

        with patch.object(FrontendAdapter, "runtime_status", return_value=RuntimeStatus(True, True, True, False)), \
             patch.object(FrontendAdapter, "run_live", return_value={"state":pending,"workflow":workflow,"thread_id":"answer-review-test"}) as run_mock, \
             patch.object(FrontendAdapter, "resume_live", return_value=resumed) as resume_mock, \
             patch("frontend.answers.generate_final_answer", side_effect=generated) as answer_mock:
            app = self.app("action")
            app.text_area(key="query_text").set_value(query).run()
            app.button(key="send_message").click().run()
            self.assert_clean(app)
            self.assertEqual([message.name for message in app.chat_message], ["user"])
            self.assertNotIn("answer_result", app.session_state.current_run)
            resume_mock.assert_not_called()
            app.button(key="reject_optimization").click().run()
            self.assert_clean(app)
            resume_mock.assert_called_once_with(workflow, "answer-review-test", "reject")
            self.assertEqual(answer_mock.call_args.args[0]["final_run"], baseline)
            self.assertEqual(app.session_state.current_run["answer_result"], answer)
            self.assertEqual([message.name for message in app.chat_message], ["user", "assistant"])
            self.assertFalse(any(button.key in {"approve_optimization", "reject_optimization"} for button in app.button))
            run_mock.assert_called_once()

    def test_saved_evidence_never_generates_or_displays_a_new_answer(self):
        from frontend.evidence import recorded_cases
        with patch("frontend.answers.generate_final_answer", side_effect=AssertionError("Saved evidence must not generate answers")) as answer_mock:
            app = self.saved_app()
            self.assertFalse(app.chat_message)
            app.selectbox(key="case_picker").select(recorded_cases(self.adapter)[1]["id"]).run()
            app.button(key="view_saved_run").click().run()
            self.assert_clean(app)
            self.assertFalse(app.chat_message)
            self.assertNotIn("answer_result", app.session_state.saved_run)
            self.assertNotIn("current_run", app.session_state)
            answer_mock.assert_not_called()

    def test_recorded_projection_preserves_values_and_missing_fields(self):
        from frontend.evidence import recorded_cases, recorded_run
        snapshot = deepcopy(self.adapter.workflow)
        for case in recorded_cases(self.adapter):
            run = recorded_run(self.adapter, case["id"])
            source = self.adapter.workflow_by_id[case["id"]]
            self.assertEqual(run["before_run"]["latency_seconds"], source["validation"]["before"]["latency_seconds"])
            self.assertEqual(run["optimization_proposal"], source["proposal"])
            self.assertEqual(run["validation_result"], source["validation"])
            self.assertEqual(run["approval_result"], source["approval"])
            self.assertFalse(run.get("monitoring_report"))
            self.assertFalse(run.get("trace"))
            monitoring = next(stage for stage in normalized_trace(run) if stage["stage"] == "monitoring")
            self.assertEqual(monitoring["status"], "not_recorded")
            self.assertEqual(monitoring["label"], "Not recorded")
            run["optimization_proposal"]["action"] = "local-test-mutation"
        self.assertEqual(self.adapter.workflow, snapshot)

    def test_retrieval_sources_and_missing_fields_remain_truthful(self):
        app = self.saved_app()
        content = "دليل الخدمة <script>test-only-text</script>"
        source = "دليل الخدمة.pdf"
        app.session_state.saved_run = {
            "verified": True, "mode": "VERIFIED DEMO MODE", "query": "سؤال للاختبار",
            "before_run": {"retrieved_results": [{"rank": 1, "source": source, "content": content}]},
        }
        app.run()
        self.assert_clean(app)
        markup = self.markup(app)
        document = MarkupParser(markup).root
        self.assertEqual(document.find(class_name="evidence-title")[0].text, source)
        self.assertIn(source, document.text)
        self.assertIn(content, document.text)
        self.assertIn("&lt;script&gt;test-only-text&lt;/script&gt;", markup)
        self.assertNotIn("Platform not reported", document.text)
        self.assertNotIn("Query type —", document.text)
        self.assertNotIn("Service —", document.text)
        self.assertFalse(document.find(class_name="evidence-relevance"), "Unknown source relevance must not acquire a status label")
        self.assertTrue(all(node.attrs.get("dir") == "auto" for node in document.find(class_name="evidence-title") + document.find(class_name="evidence-content")))
        self.assertFalse(document.find(class_name="metric-grid"))
        self.assertFalse(document.find(class_name="verdict"))

    def test_missing_metric_and_judge_values_are_not_manufactured(self):
        from frontend.components import metrics_compare_html, verdict_html
        before = {"recall_at_k":.25, "latency_seconds":1.25}
        after = {"recall_at_k":.5, "latency_seconds":1.5}
        document = MarkupParser(metrics_compare_html(before, after)).root
        names = [node.text for node in document.find(class_name="metric-name")]
        self.assertEqual(set(names), {"Recall@K", "Latency"})
        self.assertNotIn("LLM Judge", document.text)
        self.assertFalse(MarkupParser(metrics_compare_html({}, {})).root.find(class_name="metric-grid"))
        verdict = MarkupParser(verdict_html("REJECTED")).root.find(class_name="verdict")[0]
        self.assertIn("neutral", verdict.attrs["class"].split())
        self.assertIn("Validation not recorded", verdict.text)

    def test_query_draft_changes_retain_active_results_until_submission(self):
        from frontend.evidence import recorded_cases
        app = self.saved_app()
        case = recorded_cases(self.adapter)[0]
        app.selectbox(key="case_picker").select(case["id"]).run()
        app.button(key="view_saved_run").click().run()
        saved = deepcopy(app.session_state.saved_run)
        app.radio(key="mode_choice").set_value("Live Run").run()
        app.text_area(key="query_text").set_value("A different question").run()
        self.assert_clean(app)
        self.assertEqual(app.session_state.saved_run, saved)
        self.assertNotIn("current_run", app.session_state)
        self.assertFalse(app.chat_message)

    def test_action_case_changes_keep_url_query_and_results_synchronized(self):
        from frontend.evidence import recorded_cases, recorded_run
        cases = recorded_cases(self.adapter)
        chosen = [cases[0], cases[-1]]
        payloads, answers = [], []
        for index, case in enumerate(chosen):
            run = recorded_run(self.adapter, case["id"])
            marker = f"UNIQUE_CASE_{index}_EVIDENCE"
            document = {"rank":1, "source":marker + ".txt", "text":marker,
                        "platform":case["platform"], "service":case["service"], "relevant":True}
            run["after_run"] = {"query":case["query"], "retrieved_results":[document]}
            run["final_run"] = deepcopy(run["after_run"])
            payloads.append({"state":run,"workflow":object(),"thread_id":f"case-sync-{index}",
                             "dataset_item":self.adapter.dataset_by_id[case["id"]]})
            answers.append({"text":f"UNIQUE_CASE_{index}_ANSWER [1]", "sources":[{"citation":1,"document":document}],
                            "status":"answered", "evidence":"optimized"})

        def query_param(app, name):
            value = app.query_params.get(name)
            return value[0] if isinstance(value, list) and value else value

        with patch.object(FrontendAdapter, "runtime_status", return_value=RuntimeStatus(True, True, True, False)), \
             patch.object(FrontendAdapter, "run_live", side_effect=payloads) as run_mock, \
             patch("frontend.answers.generate_final_answer", side_effect=answers) as answer_mock:
            app = self.app("action")
            self.assertFalse(app.selectbox, "The primary chat uses suggestions and the composer")
            for index, case in enumerate(chosen):
                app.text_area(key="query_text").set_value(case["query"]).run()
                self.assert_clean(app)
                self.assertEqual(app.session_state.runtime_mode, "LIVE MODE")
                self.assertEqual(app.session_state.query_text, case["query"])
                self.assertEqual(app.session_state.selected_case_id, case["id"])
                self.assertEqual(query_param(app, "case"), case["id"])
                self.assertEqual(query_param(app, "mode"), "live")
                if index:
                    self.assertIn("UNIQUE_CASE_0_ANSWER", self.markup(app))
                    self.assertIn("UNIQUE_CASE_0_EVIDENCE", self.markup(app))
                    self.assertEqual(app.session_state.current_run["query"], chosen[0]["query"])
                else:
                    with self.assertRaises(KeyError):
                        _ = app.session_state["current_run"]
                app.button(key="send_message").click().run()
                self.assert_clean(app)
                current = app.session_state.current_run
                self.assertEqual(current["query"], case["query"])
                self.assertEqual(current["platform"], case["platform"])
                self.assertEqual(current["diagnosis_report"], payloads[index]["state"]["diagnosis_report"])
                self.assertEqual(current["validation_result"], payloads[index]["state"]["validation_result"])
                self.assertEqual(current["answer_result"], answers[index])
                self.assertIn(answers[index]["text"], self.markup(app))
                self.assertIn(f"UNIQUE_CASE_{index}_EVIDENCE", self.markup(app))
            self.assertEqual([message.name for message in app.chat_message], ["user", "assistant"] * 2)
            self.assertIn("UNIQUE_CASE_0_ANSWER", self.markup(app))
            app.text_area(key="query_text").set_value("A custom draft").run()
            self.assert_clean(app)
            self.assertEqual(app.session_state.query_text, "A custom draft")
            self.assertEqual(app.session_state.case_picker, "")
            self.assertNotIn("case", app.query_params)
            self.assertNotIn("mode", app.query_params)
            self.assertIn("UNIQUE_CASE_1_ANSWER", self.markup(app))
            self.assertEqual(app.session_state.current_run["query"], chosen[1]["query"])
            self.assertEqual(run_mock.call_count, 2)
            self.assertEqual(answer_mock.call_count, 2)

    def test_saved_url_changes_update_saved_run_without_replacing_conversation(self):
        from frontend.evidence import recorded_cases
        first, second = recorded_cases(self.adapter)[0], recorded_cases(self.adapter)[-1]
        app = self.app("action", case=first["id"])
        self.assertEqual(app.session_state.saved_run["case_id"], first["id"])
        app.session_state.current_run = {
            "mode":"LIVE MODE", "query":"Earlier conversation question",
            "answer_result":{"text":"Earlier answer", "sources":[], "evidence":"baseline", "status":"answered"},
        }
        app.run()
        active = deepcopy(app.session_state.current_run)
        history = deepcopy(app.session_state.chat_history)
        app.query_params["case"] = second["id"]
        app.run()
        self.assert_clean(app)
        self.assertEqual(app.session_state.query_text, second["query"])
        self.assertEqual(app.session_state.case_picker, second["id"])
        self.assertEqual(app.session_state.saved_run["case_id"], second["id"])
        self.assertEqual(app.session_state.current_run, active)
        self.assertEqual(app.session_state.chat_history, history)
        app.radio(key="mode_choice").set_value("Live Run").run()
        app.text_area(key="query_text").set_value("An unlabelled custom question").run()
        app.run()
        self.assert_clean(app)
        self.assertEqual(app.session_state.query_text, "An unlabelled custom question")
        self.assertEqual(app.session_state.case_picker, "")
        self.assertNotIn("case", app.query_params)
        self.assertEqual(app.session_state.current_run, active)
        self.assertEqual(app.session_state.chat_history, history)
        self.assertIn("Earlier answer", self.markup(app))

    def test_unlabelled_query_hides_formal_quality_even_with_backend_numbers(self):
        query = "An arbitrary question with no evaluation ground truth"
        quality = {"recall_at_k":1.0, "precision_at_k":0.5, "reciprocal_rank":1.0, "latency_seconds":0.2}
        rows = [{"rank":1,"text":"Unrelated document one", "platform":"balady", "service":"unrelated-one", "relevant":True},
                {"rank":2,"text":"Unrelated document two", "platform":"absher", "service":"unrelated-two", "relevant":True}]
        final_run = {**quality, "retrieved_results":rows}
        state = {"query":query,"final_status":"IMPROVED","before_run":deepcopy(final_run),"after_run":deepcopy(final_run),
                 "final_run":deepcopy(final_run),"validation_result":{"verdict":"IMPROVED","recommendation":"ACCEPT_OPTIMIZED","before":quality,"after":quality},
                 "trace":[{"stage":"validation","status":"improved","detail":"Recall@K improved"}]}
        answer = {"text":"The retrieved evidence does not answer this question.", "sources":[], "status":"insufficient_evidence", "evidence":"baseline"}
        with patch.object(FrontendAdapter, "runtime_status", return_value=RuntimeStatus(True, True, True, False)), \
             patch.object(FrontendAdapter, "run_live", return_value={"state":state,"workflow":object(),"thread_id":"unlabelled-ui-test"}) as run_mock, \
             patch("frontend.answers.generate_final_answer", return_value=answer):
            app = self.app("action")
            app.text_area(key="query_text").set_value(query).run()
            app.button(key="send_message").click().run()
            self.assert_clean(app)
            document = MarkupParser(self.markup(app)).root
            visible = document.text + " ".join(item.value for item in app.info) + " ".join(item.value for item in app.caption) + " ".join(item.value for item in app.warning)
            self.assertIn("Unlabelled query — retrieval quality is not formally validated.", visible)
            self.assertIn("Retrieved evidence does not sufficiently support this query.", visible)
            self.assertFalse(document.find(class_name="verdict"))
            self.assertFalse(document.find(class_name="metric-card"))
            trace_labels = " ".join(node.text for node in document.find(class_name="trace-status") + document.find(class_name="trace-detail"))
            self.assertNotIn("improved", trace_labels.casefold())
            self.assertNotIn("worse", trace_labels.casefold())
            self.assertNotIn("Optimized retrieval accepted", visible)
            self.assertNotIn("case", app.query_params)
            self.assertEqual(app.session_state.current_run["validation_result"], state["validation_result"], "Presentation must not rewrite backend state")
            for item in app.json:
                rendered = json.loads(item.value)
                if isinstance(rendered, dict) and rendered.get("query") == query:
                    self.assertNotIn("validation_result", rendered)
                    self.assertNotIn("recall_at_k", json.dumps(rendered))
                    self.assertNotIn("precision_at_k", json.dumps(rendered))
                    self.assertNotIn("reciprocal_rank", json.dumps(rendered))
            run_mock.assert_called_once_with(query)

    def test_missing_structural_callback_disables_approve_but_reject_works(self):
        workflow = SimpleNamespace(action_executor=SimpleNamespace(rechunk_candidate=None))
        query = "Frontend structural capability fixture"
        baseline = {"retrieved_results":[]}
        pending = {"query":query,"before_run":baseline,"optimization_proposal":{"action":"rechunk_and_reindex"},
                   "approval_result":{"approval_status":"pending_human_approval"},"final_status":"PENDING_HUMAN_APPROVAL"}
        resumed = {"query":query,"before_run":deepcopy(baseline),"final_run":deepcopy(baseline),
                   "optimization_proposal":{"action":"rechunk_and_reindex"},"approval_result":{"approval_status":"rejected"},"final_status":"REJECTED"}
        with patch.object(FrontendAdapter, "runtime_status", return_value=RuntimeStatus(True, True, True, False)), \
             patch.object(FrontendAdapter, "run_live", return_value={"state":pending,"workflow":workflow,"thread_id":"missing-callback-test"}), \
             patch.object(FrontendAdapter, "resume_live", return_value=resumed) as resume_mock:
            app = self.app("action")
            app.text_area(key="query_text").set_value(query).run()
            app.button(key="send_message").click().run()
            self.assert_clean(app)
            self.assertTrue(app.button(key="approve_optimization").disabled)
            self.assertFalse(app.button(key="reject_optimization").disabled)
            self.assertTrue(any("callback" in item.value for item in app.info))
            self.assertFalse(MarkupParser(self.markup(app)).root.find(class_name="verdict"))
            resume_mock.assert_not_called()
            app.button(key="reject_optimization").click().run()
            self.assert_clean(app)
            resume_mock.assert_called_once_with(workflow, "missing-callback-test", "reject")
            self.assertEqual(app.session_state.current_run["final_status"], "REJECTED")
            self.assertIn("Baseline retained", self.markup(app))
            self.assertFalse(MarkupParser(self.markup(app)).root.find(class_name="metric-card"))

    def test_unavailable_runtime_status(self):
        status = RuntimeStatus(False, False, False, False)
        with patch.object(FrontendAdapter, "runtime_status", return_value=status):
            from frontend.evidence import recorded_cases
            app = self.app("action", case=recorded_cases(self.adapter)[0]["id"])
            saved_run = deepcopy(app.session_state.saved_run)
            app.radio(key="mode_choice").set_value("Live Run").run()
            self.assert_clean(app)
            self.assertIn("Live Runtime Unavailable", self.markup(app))
            self.assertTrue(app.button(key="send_message").disabled)
            alerts = " ".join(item.value for item in app.info)
            self.assertIn(status.reason, alerts)
            for filename in ("index.faiss", "index.pkl"):
                if not (ROOT / "vector_store" / "evaluation_index" / filename).is_file():
                    self.assertIn("vector_store/evaluation_index/" + filename, alerts)
            self.assertFalse(app.radio(key="mode_choice").disabled)
            self.assertEqual(app.session_state.saved_run, saved_run)
            self.assertNotIn("current_run", app.session_state)
            self.assertNotIn("Saved evaluation record", self.markup(app))
            app.radio(key="mode_choice").set_value("View Saved Runs").run()
            self.assertIn("Saved evaluation record", self.markup(app))
            self.assertFalse(any("Build" in b.label for b in app.button))

    def test_dashboard_filters_and_inspector(self):
        from frontend.evidence import recorded_cases
        app = self.app("dashboard")
        table = app.dataframe[0].value
        self.assertEqual(set(table["Case"]), set(self.adapter.workflow_by_id))
        self.assertEqual(list(table.columns), ["Case", "Platform", "Issue", "Action", "Decision", "Validation Verdict"])
        self.assertTrue(set(table["Validation Verdict"]).issubset({"Improved", "No Meaningful Change", "Worse", "Not recorded"}))
        self.assertTrue(all(value == "Auto-approved by policy" for value in table["Decision"]))
        specs = [json.loads(chart.proto.spec) for chart in app.get("plotly_chart")]
        outcomes = [trace for spec in specs for trace in spec["data"] if trace.get("labels") == ["Improved", "No Meaningful Change", "Worse"]]
        self.assertEqual(len(outcomes), 1)
        self.assertEqual(sum(outcomes[0]["values"]), len(self.adapter.workflow_by_id))
        next(t for t in app.text_input if t.label == "Search runs").set_value("no matching saved run").run()
        self.assert_clean(app)
        self.assertTrue(any("No stored runs match" in c.value for c in app.caption))
        app.selectbox(key="inspector_id").select(recorded_cases(self.adapter)[1]["id"]).run()
        self.assert_clean(app)

    def test_gate_projection_and_secret_redaction(self):
        for action in ("rewrite_query", "change_top_k"):
            run = {"optimization_proposal":{"action":action}, "approval_result":{"approval_status":"pending_human_approval"}}
            self.assertFalse(approval_view(run)["requires_decision"])
            self.assertNotEqual(approval_view(run)["label"], "Auto-approved by policy")
        for status in ("pending_human_approval", "approved", "rejected"):
            run = {"optimization_proposal":{"action":"rechunk_and_reindex"}, "approval_result":{"approval_status":status}}
            trace = normalized_trace(run)
            self.assertEqual(sum(s["role"].startswith("Agent") for s in trace), 4)
            self.assertEqual(trace[4]["name"], "Risk Gate")
        sample = {"api_key":"test-only-placeholder", "nested":{"Authorization":"test-only-placeholder"}, "workflow":object()}
        clean = safe_state(sample)
        self.assertEqual(clean["api_key"], "[redacted]")
        self.assertNotIn("workflow", clean)


if __name__ == "__main__":
    unittest.main()
