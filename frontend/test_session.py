"""Offline session/navigation regressions; real APIs and index writes blocked."""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from streamlit.testing.v1 import AppTest

from frontend.adapter import FrontendAdapter, RuntimeStatus
from frontend.evidence import recorded_cases


ROOT = Path(__file__).resolve().parents[1]


class SessionChecks(unittest.TestCase):
    def setUp(self):
        for method in ("run_live", "resume_live", "build_evaluation_index", "set_session_api_key"):
            patcher = patch.object(FrontendAdapter, method, side_effect=AssertionError("Real backend disabled"))
            patcher.start()
            self.addCleanup(patcher.stop)
        patcher = patch.object(FrontendAdapter, "runtime_status", return_value=RuntimeStatus(True, True, True, False))
        patcher.start()
        self.addCleanup(patcher.stop)
        patcher = patch("frontend.answers.generate_final_answer", side_effect=AssertionError("No regeneration allowed"))
        self.answer = patcher.start()
        self.addCleanup(patcher.stop)
        patcher = patch("frontend.conversation.resolve_followup", side_effect=lambda query, messages: {
            "query":query, "clarification":None, "contextualized":False,
        })
        patcher.start()
        self.addCleanup(patcher.stop)

    def app(self):
        app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=20)
        app.query_params["page"] = "action"
        app.run()
        self.assertFalse(app.exception)
        return app

    def seed_run(self, app, pending=False):
        case = recorded_cases(FrontendAdapter())[0]
        rows = [{"rank":1, "text":"Document evidence", "source":"actual-source.txt", "platform":case["platform"], "service":case["service"]}]
        retrieval = {"query":case["query"], "retrieved_results":rows, "top_k":4}
        run = {"mode":"LIVE MODE", "query":case["query"], "case_id":case["id"], "before_run":deepcopy(retrieval),
               "trace":[{"stage":"monitoring", "status":"completed"}]}
        if pending:
            run.update({"optimization_proposal":{"action":"rechunk_and_reindex", "parameters":{"chunk_size":400,"chunk_overlap":50}},
                        "approval_result":{"approval_status":"pending_human_approval"},
                        "__interrupt__":[{"value":{"type":"human_approval_required", "action":"rechunk_and_reindex"}}]})
        else:
            run.update({"final_status":"NO_ACTION_REQUIRED", "final_run":deepcopy(retrieval),
                        "answer_result":{"text":"Evidence-backed answer [1]", "evidence":"baseline", "sources":[{"citation":1,"document":rows[0]}], "status":"answered"}})
        workflow = SimpleNamespace(action_executor=SimpleNamespace(rechunk_candidate=Mock()))
        app.session_state.current_run = deepcopy(run)
        app.session_state.live_workflow = workflow
        app.session_state.live_thread_id = "session-checkpoint-test"
        app.session_state.query_text = case["query"]
        app.session_state.case_picker = case["id"]
        app.session_state.selected_case_id = case["id"]
        app.session_state.runtime_mode = "LIVE MODE"
        app.session_state.mode_choice = "Live Run"
        app.run()
        self.assertFalse(app.exception)
        migrated = deepcopy(app.session_state.current_run)
        self.assertEqual(migrated["user_query"], case["query"])
        self.assertTrue(migrated["turn_id"])
        return case, migrated, workflow

    def test_navigation_keeps_entire_run_and_never_regenerates_answer(self):
        app = self.app()
        case, run, workflow = self.seed_run(app)
        history = deepcopy(app.session_state.chat_history)
        for page in ("dashboard", "architecture", "team", "overview"):
            with self.subTest(page=page):
                app.button(key=f"session_nav_{page}").click().run()
                self.assertFalse(app.exception)
                self.assertEqual(app.session_state.current_run, run)
                self.assertEqual(app.session_state.chat_history, history)
                self.assertIs(app.session_state.live_workflow, workflow)
                self.assertEqual(app.session_state.live_thread_id, "session-checkpoint-test")
                app.button(key="session_nav_action").click().run()
                self.assertFalse(app.exception)
                self.assertEqual(app.session_state.current_run, run)
                self.assertEqual(app.text_area(key="query_text").value, case["query"])
                self.assertEqual(app.session_state.selected_case_id, case["id"])
                self.assertEqual(app.radio(key="mode_choice").value, "Live Run")
                self.assertEqual([message.name for message in app.chat_message], ["user", "assistant"])
        self.answer.assert_not_called()

    def test_pending_review_survives_navigation_and_resume_uses_original_query(self):
        app = self.app()
        case, run, workflow = self.seed_run(app, pending=True)
        self.assertTrue(app.text_area(key="query_text").disabled)
        self.assertTrue(app.button(key="send_message").disabled)
        app.button(key="session_nav_team").click().run()
        app.button(key="session_nav_action").click().run()
        self.assertFalse(app.exception)
        self.assertEqual(app.session_state.current_run, run)
        self.assertIs(app.session_state.live_workflow, workflow)
        self.assertFalse(app.button(key="approve_optimization").disabled)
        self.assertEqual(app.text_area(key="query_text").value, case["query"])
        terminal = {"final_status":"REJECTED", "before_run":run["before_run"], "final_run":run["before_run"],
                    "optimization_proposal":run["optimization_proposal"], "approval_result":{"approval_status":"rejected"}}
        with patch.object(FrontendAdapter, "resume_live", return_value=terminal) as resume, \
             patch("frontend.answers.generate_final_answer", return_value=None):
            app.button(key="reject_optimization").click().run()
            self.assertFalse(app.exception)
            resume.assert_called_once_with(workflow, "session-checkpoint-test", "reject")
            self.assertEqual(app.session_state.current_run["query"], case["query"])

    def test_draft_preserves_active_run_failed_turn_preserves_chat_and_new_chat_clears_it(self):
        app = self.app()
        _, run, workflow = self.seed_run(app)
        history = deepcopy(app.session_state.chat_history)
        app.text_area(key="query_text").set_value("A new draft question").run()
        self.assertEqual(app.session_state.current_run, run)
        self.assertIs(app.session_state.live_workflow, workflow)
        self.assertEqual(app.session_state.chat_history, history)
        app.button(key="send_message").click().run()
        self.assertFalse(app.exception)
        self.assertEqual(app.session_state.chat_history[:len(history)], history)
        self.assertEqual(app.session_state.chat_history[-1]["content"], "A new draft question")
        self.assertTrue(app.session_state.turn_error)
        self.assertNotIn("current_run", app.session_state, "A failed latest turn must not display earlier workflow results")
        self.assertEqual([message.name for message in app.chat_message], ["user", "assistant", "user"])
        app.button(key="new_chat").click().run()
        for key in ("current_run", "live_workflow", "live_thread_id"):
            self.assertNotIn(key, app.session_state)
        self.assertEqual(app.session_state.chat_history, [])
        self.assertFalse(app.chat_message)
        self.answer.assert_not_called()


if __name__ == "__main__":
    unittest.main()
