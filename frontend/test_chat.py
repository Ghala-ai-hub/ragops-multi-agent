"""Offline conversational UI regressions; all live operations are replaced."""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from streamlit.testing.v1 import AppTest
from streamlit.testing.v1.errors import AppTestError

from frontend.adapter import FrontendAdapter, RuntimeStatus
from frontend.conversation import resolve_followup as resolve_with_context
from frontend.evidence import recorded_cases, recorded_run


ROOT = Path(__file__).resolve().parents[1]


class ChatChecks(unittest.TestCase):
    def setUp(self):
        self.adapter = FrontendAdapter()
        self.states = {}
        self.resolutions = {}
        self.workflow = SimpleNamespace(action_executor=SimpleNamespace(rechunk_candidate=Mock()))
        self.live = self.mock_method("run_live", side_effect=self.run_live)
        self.resume = self.mock_method("resume_live", side_effect=AssertionError("Resume requires explicit test result"))
        self.forbidden = [self.mock_method(name, side_effect=AssertionError("Backend writes forbidden"))
                          for name in ("build_evaluation_index", "set_session_api_key")]
        self.mock_method("runtime_status", return_value=RuntimeStatus(True, True, True, False))
        self.context = self.mock("frontend.conversation.resolve_followup", side_effect=self.resolve)
        self.answer = self.mock("frontend.answers.generate_final_answer", side_effect=self.answer_from_state)

    def tearDown(self):
        for operation in self.forbidden:
            operation.assert_not_called()

    def mock(self, target, **kwargs):
        patcher = patch(target, **kwargs)
        self.addCleanup(patcher.stop)
        return patcher.start()

    def mock_method(self, name, **kwargs):
        patcher = patch.object(FrontendAdapter, name, **kwargs)
        self.addCleanup(patcher.stop)
        return patcher.start()

    def resolve(self, query, messages):
        return self.resolutions.get(query, {"query": query, "clarification": None, "contextualized": False})

    def baseline(self, query):
        retrieval = {"query": query, "top_k": 4, "retrieved_results": [{
            "rank": 1, "text": "OFFLINE TEST evidence for " + query,
            "source": "test-source.txt", "platform": "test_platform", "service": "test_service", "relevant": True,
        }]}
        return {"query": query, "before_run": retrieval, "final_run": deepcopy(retrieval),
                "monitoring_report": {"failure_detected": False, "baseline_relevant_found": True},
                "diagnosis_report": {"recommended_action": "none", "issue_type": None},
                "final_status": "NO_ACTION_REQUIRED"}

    def run_live(self, query):
        state = deepcopy(self.states.get(query) or self.baseline(query))
        item = self.adapter.match_dataset_query(query)
        return {"state": state, "workflow": self.workflow,
                "thread_id": "offline-thread-" + str(self.live.call_count), "dataset_item": item}

    def answer_from_state(self, state):
        if state.get("__interrupt__") or not state.get("final_run"):
            return None
        query = state.get("user_query") or state["query"]
        prefix = "إجابة مدعومة للسؤال: " if any("\u0600" <= c <= "\u06ff" for c in query) else "Grounded answer for: "
        return {"text": prefix + query + " [1]", "sources": [{"citation": 1,
                    "document": deepcopy(state["final_run"]["retrieved_results"][0])}],
                "status": "answered", "evidence": "optimized" if state.get("final_status") == "IMPROVED" else "baseline"}

    def app(self):
        app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=30)
        app.query_params["page"] = "action"
        app.run()
        self.clean(app)
        self.assertEqual(app.radio(key="mode_choice").value, "Live Run")
        return app

    def clean(self, app):
        self.assertFalse(app.exception, [e.message for e in app.exception])

    def send(self, app, query):
        app.text_area(key="query_text").set_value(query).run()
        app.button(key="send_message").click().run()
        self.clean(app)
        self.assertEqual(app.text_area(key="query_text").value, "")

    def markup(self, app):
        return "\n".join(item.value for item in app.markdown)

    def trace(self, app):
        traces = [item.value for item in app.markdown if item.value.startswith('<div class="trace-ribbon"')]
        self.assertEqual(len(traces), 1)
        self.assertEqual(traces[0].count('class="trace-stage '), 7)
        return traces[0]

    def pending_state(self, query):
        state = self.baseline(query)
        state.pop("final_run")
        state.pop("final_status")
        state.update({"optimization_proposal": {"action": "rechunk_and_reindex", "issue_type": "Chunking Quality", "parameters": {}},
                      "diagnosis_report": {"issue_type": "Chunking Quality"},
                      "approval_result": {"approval_status": "pending_human_approval"},
                      "__interrupt__": [{"value": {"type": "human_approval_required", "action": "rechunk_and_reindex"}}]})
        return state

    def clarification(self, request, question, confirmation_query=""):
        return {"query": request, "clarification": question, "contextualized": False,
                "pending_clarification": {"request": request, "question": question,
                                          "confirmation_query": confirmation_query}}

    def test_three_arabic_turns_keep_original_messages_and_per_answer_sources(self):
        app = self.app()
        queries = ["كيف أجدد رخصة القيادة؟", "طيب وش الشروط؟", "وكم رسومها؟"]
        resolved = [queries[0], "ما شروط تجديد رخصة القيادة؟", "ما رسوم تجديد رخصة القيادة؟"]
        for original, retrieval in zip(queries, resolved):
            self.resolutions[original] = {"query": retrieval, "clarification": None, "contextualized": original != retrieval}
            self.send(app, original)
        history = app.session_state.chat_history
        self.assertEqual([message["role"] for message in history], ["user", "assistant"] * 3)
        self.assertEqual([m["content"] for m in history if m["role"] == "user"], queries)
        self.assertEqual([m["retrieval_query"] for m in history if m["role"] == "user"], resolved)
        self.assertEqual([call.args[0] for call in self.live.call_args_list], resolved)
        self.assertEqual(len(app.chat_message), 6)
        self.assertEqual(app.session_state.current_run["user_query"], queries[-1])
        self.assertEqual(app.session_state.current_run["query"], resolved[-1])
        for index in range(3):
            self.assertIn(queries[index], history[index * 2 + 1]["content"])
            self.assertIn(resolved[index], history[index * 2 + 1]["sources"][0]["document"]["text"])
        self.assertEqual(len(self.context.call_args_list[-1].args[1]), 4)
        self.trace(app)

    def test_english_followup_preserves_grounded_reply_and_resolved_reference(self):
        app = self.app()
        self.send(app, "How can I renew my driving licence?")
        self.resolutions["And its conditions?"] = {"query": "What are driving licence renewal conditions?", "clarification": None, "contextualized": True}
        self.send(app, "And its conditions?")
        self.live.assert_called_with("What are driving licence renewal conditions?")
        self.assertEqual([m.name for m in app.chat_message], ["user", "assistant", "user", "assistant"])
        self.assertIn("And its conditions?", app.session_state.chat_history[-1]["content"])

    def test_navigation_all_pages_and_rerenders_do_not_regenerate_conversation(self):
        app = self.app()
        self.send(app, "Tell me about the recorded service requirements")
        self.send(app, "Which documents are needed for that service?")
        history, run = deepcopy(app.session_state.chat_history), deepcopy(app.session_state.current_run)
        counts = (self.live.call_count, self.context.call_count, self.answer.call_count)
        workflow, thread = app.session_state.live_workflow, app.session_state.live_thread_id
        for page in ("dashboard", "architecture", "team", "overview"):
            app.button(key=f"session_nav_{page}").click().run()
            self.clean(app)
            app.button(key="session_nav_action").click().run()
            self.clean(app)
            self.assertEqual(app.session_state.chat_history, history)
            self.assertEqual(app.session_state.current_run, run)
            self.assertIs(app.session_state.live_workflow, workflow)
            self.assertEqual(app.session_state.live_thread_id, thread)
            self.assertEqual(len(app.chat_message), 4)
        app.run()
        self.assertEqual(counts, (self.live.call_count, self.context.call_count, self.answer.call_count))

    def test_suggestions_populate_composer_without_resetting_or_running(self):
        app = self.app()
        self.send(app, "A custom opening question")
        history = deepcopy(app.session_state.chat_history)
        buttons = [button for button in app.button if str(button.key).startswith("suggest_")]
        self.assertGreaterEqual(len(buttons), 3)
        self.assertLessEqual(len(buttons), 4)
        case = self.adapter.match_dataset_query(buttons[0].label)
        self.assertIsNotNone(case)
        buttons[0].click().run()
        self.clean(app)
        self.assertEqual(app.text_area(key="query_text").value, case["query"])
        self.assertEqual(app.session_state.chat_history, history)
        self.assertEqual(self.live.call_count, 1)

    def test_saved_mode_never_calls_live_or_model_and_retains_live_conversation(self):
        app = self.app()
        self.send(app, "First live conversation question")
        history, run = deepcopy(app.session_state.chat_history), deepcopy(app.session_state.current_run)
        counts = (self.live.call_count, self.context.call_count, self.answer.call_count)
        app.radio(key="mode_choice").set_value("View Saved Runs").run()
        case = recorded_cases(self.adapter)[0]
        app.selectbox(key="case_picker").select(case["id"]).run()
        app.button(key="view_saved_run").click().run()
        self.clean(app)
        self.assertEqual(app.session_state.saved_run["case_id"], case["id"])
        self.assertEqual(app.session_state.current_run, run)
        self.assertFalse(app.chat_message)
        app.radio(key="mode_choice").set_value("Live Run").run()
        self.clean(app)
        self.assertEqual(app.session_state.chat_history, history)
        self.assertEqual(app.session_state.current_run, run)
        self.assertEqual(len(app.chat_message), 2)
        self.assertEqual(counts, (self.live.call_count, self.context.call_count, self.answer.call_count))

    def test_new_chat_clears_messages_latest_result_thread_and_trace(self):
        app = self.app()
        self.send(app, "One completed message")
        app.button(key="new_chat").click().run()
        self.clean(app)
        self.assertEqual(app.session_state.chat_history, [])
        for key in ("current_run", "saved_run", "live_workflow", "live_thread_id", "active_turn_id", "turn_error"):
            self.assertNotIn(key, app.session_state)
        self.assertEqual(app.text_area(key="query_text").value, "")
        self.assertFalse(app.chat_message)
        self.assertEqual(self.trace(app).count('class="trace-stage waiting"'), 7)

    def test_ambiguous_first_and_followup_clarify_without_retrieval_or_stale_trace(self):
        for with_history in (False, True):
            with self.subTest(with_history=with_history):
                app = self.app()
                if with_history:
                    self.send(app, "Describe service A and service B")
                before = deepcopy(app.session_state.chat_history)
                count = self.live.call_count
                self.resolutions["طيب وش الشروط؟"] = {"query": "طيب وش الشروط؟", "clarification": "أي خدمة تقصد؟", "contextualized": False}
                self.send(app, "طيب وش الشروط؟")
                self.assertEqual(self.live.call_count, count)
                self.assertEqual(app.session_state.chat_history[:-2], before)
                self.assertEqual(app.session_state.chat_history[-1]["status"], "clarification")
                self.assertNotIn("current_run", app.session_state)
                self.assertEqual(self.trace(app).count('class="trace-stage waiting"'), 7)
                self.assertNotIn('class="metric-card"', self.markup(app))

    def test_latest_unlabelled_turn_replaces_prior_metric_trace_but_keeps_chat(self):
        app = self.app()
        case = next(case for case in recorded_cases(self.adapter) if case["issue"] == "Top-K")
        state = recorded_run(self.adapter, case["id"])
        state.update({"mode": "LIVE MODE", "verified": False, "final_run": deepcopy(state["after_run"])})
        self.states[case["query"]] = state
        self.send(app, case["query"])
        self.assertIn("Change Top-K", self.trace(app))
        self.assertIn('class="metric-card"', self.markup(app))
        first_pair = deepcopy(app.session_state.chat_history)
        self.send(app, "A completely different custom question without labels")
        self.assertEqual(app.session_state.chat_history[:2], first_pair)
        self.assertNotIn("Change Top-K", self.trace(app))
        self.assertNotIn('class="metric-card"', self.markup(app))
        self.assertIn("Formal Before/After metrics unavailable for this unlabelled query", [item.value for item in app.caption])

    def test_pending_blocks_new_turn_and_approve_or_reject_updates_only_pending_turn(self):
        for decision in ("approve", "reject"):
            with self.subTest(decision=decision):
                app = self.app()
                self.send(app, "An earlier completed question")
                prior = deepcopy(app.session_state.chat_history)
                original, resolved_query = "What about restructuring it?", "Review the earlier service's structural retrieval"
                self.resolutions[original] = {"query": resolved_query, "clarification": None, "contextualized": True}
                pending = self.pending_state(resolved_query)
                self.states[resolved_query] = pending
                self.send(app, original)
                turn = app.session_state.active_turn_id
                thread = app.session_state.live_thread_id
                self.assertTrue(app.button(key="send_message").disabled)
                self.assertTrue(app.text_area(key="query_text").disabled)
                self.assertEqual(len(app.session_state.chat_history), 3)
                app.button(key="session_nav_team").click().run()
                app.button(key="session_nav_action").click().run()
                self.assertEqual(app.session_state.active_turn_id, turn)
                terminal = deepcopy(pending)
                terminal.pop("__interrupt__")
                terminal.pop("query")  # Resume may omit it; preserve original and resolved questions.
                terminal.update({"final_status": "SAME" if decision == "approve" else "REJECTED",
                                 "approval_result": {"approval_status": "approved" if decision == "approve" else "rejected"},
                                 "final_run": deepcopy(pending["before_run"])})
                if decision == "approve":
                    terminal.update({"execution_result": {"status": "executed"}, "after_run": deepcopy(pending["before_run"]),
                                     "validation_result": {"verdict": "SAME", "recommendation": "RETAIN_BASELINE"}})
                self.resume.side_effect = None
                self.resume.return_value = terminal
                app.button(key=f"{decision}_optimization").click().run()
                self.clean(app)
                self.resume.assert_called_with(self.workflow, thread, decision)
                self.assertEqual(app.session_state.chat_history[:2], prior)
                self.assertEqual(app.session_state.chat_history[-1]["turn_id"], turn)
                self.assertIn(original, app.session_state.chat_history[-1]["content"])
                self.assertEqual(app.session_state.current_run["user_query"], original)
                self.assertEqual(app.session_state.current_run["query"], resolved_query)
                self.assertEqual(len(app.chat_message), 4)
                self.assertFalse(app.button(key="send_message").disabled)

    def test_context_error_retry_reuses_latest_turn_without_duplicate_messages(self):
        app = self.app()
        self.send(app, "A successful earlier question")
        prior = deepcopy(app.session_state.chat_history)
        self.context.side_effect = RuntimeError("private provider detail")
        self.send(app, "And what next?")
        self.assertEqual(self.live.call_count, 1)
        self.assertEqual(len(app.session_state.chat_history), 3)
        turn = app.session_state.active_turn_id
        self.assertNotIn("private provider detail", self.markup(app))
        self.context.side_effect = self.resolve
        app.button(key="retry_message").click().run()
        self.clean(app)
        self.assertEqual(len(app.session_state.chat_history), 4)
        self.assertEqual(app.session_state.chat_history[:2], prior)
        self.assertEqual(app.session_state.chat_history[-1]["turn_id"], turn)
        self.assertEqual(self.live.call_count, 2)

    def test_answer_retry_uses_existing_evidence_and_adds_one_assistant_message(self):
        app = self.app()
        self.send(app, "A successful earlier question")
        prior = deepcopy(app.session_state.chat_history)
        self.answer.side_effect = RuntimeError("private answer provider detail")
        self.send(app, "A new question with retrieved evidence")
        self.assertEqual(len(app.session_state.chat_history), 3)
        counts = (self.live.call_count, self.context.call_count)
        self.answer.side_effect = self.answer_from_state
        app.button(key="retry_answer").click().run()
        self.clean(app)
        self.assertEqual(app.session_state.chat_history[:2], prior)
        self.assertEqual(len(app.session_state.chat_history), 4)
        self.assertEqual(counts, (self.live.call_count, self.context.call_count))
        calls = self.answer.call_count
        app.run()
        self.assertEqual(self.answer.call_count, calls)

    def test_pending_clarification_persists_across_navigation_saved_mode_and_new_chat(self):
        request = "How do I renew the licence I mentioned?"
        question = "Do you mean renewing a driving licence through Absher?"
        candidate = "How do I renew a driving licence through Absher?"
        self.resolutions[request] = self.clarification(request, question, candidate)
        app = self.app()
        self.send(app, request)
        history = deepcopy(app.session_state.chat_history)
        self.assertEqual(history[-1]["pending_clarification"], self.resolutions[request]["pending_clarification"])
        counts = (self.context.call_count, self.live.call_count, self.answer.call_count)
        for page in ("dashboard", "architecture", "team", "overview"):
            app.button(key=f"session_nav_{page}").click().run()
            app.button(key="session_nav_action").click().run()
            self.clean(app)
            self.assertEqual(app.session_state.chat_history, history)
        app.radio(key="mode_choice").set_value("View Saved Runs").run()
        case = recorded_cases(self.adapter)[0]
        app.selectbox(key="case_picker").select(case["id"]).run()
        app.button(key="view_saved_run").click().run()
        app.radio(key="mode_choice").set_value("Live Run").run()
        self.clean(app)
        self.assertEqual(app.session_state.chat_history, history)
        self.assertEqual(counts, (self.context.call_count, self.live.call_count, self.answer.call_count))
        self.assertNotIn("current_run", app.session_state)
        app.button(key="new_chat").click().run()
        self.clean(app)
        self.assertEqual(app.session_state.chat_history, [])
        self.assertNotIn("saved_run", app.session_state)
        self.assertNotIn("current_run", app.session_state)
        self.assertEqual(app.session_state.runtime_mode, "LIVE MODE")

    def test_real_resolver_confirmation_reaches_workflow_answer_and_sources_once(self):
        cases = [
            ("How do I renew my licence on Absher?", "Do you mean renewing a driving licence on Absher?",
             "How do I renew a driving licence on Absher?", "yes"),
            ("How do I renew my licence on Absher?", "Do you mean renewing a driving licence on Absher?",
             "How do I renew a driving licence on Absher?", "correct"),
            ("أبغى أجدد الرخصة من أبشر", "هل تقصد تجديد رخصة القيادة عبر أبشر؟",
             "كيف أجدد رخصة القيادة عبر أبشر؟", "نعم"),
        ]
        self.context.side_effect = resolve_with_context
        for request, question, candidate, confirmation in cases:
            with self.subTest(confirmation=confirmation):
                self.live.reset_mock()
                self.answer.reset_mock()
                chain = Mock()
                chain.invoke.return_value = {"parsed": {
                    "decision": "clarify", "query": request, "clarification": question,
                    "confirmation_query": candidate,
                }, "parsing_error": None}
                with patch("frontend.conversation.create_context_chain", return_value=chain):
                    app = self.app()
                    self.send(app, request)
                    self.assertEqual(self.live.call_count, 0)
                    self.assertEqual(app.session_state.chat_history[-1]["pending_clarification"]["confirmation_query"], candidate)
                    self.send(app, confirmation)
                    self.live.assert_called_once_with(candidate)
                    self.assertEqual(chain.invoke.call_count, 1, "A direct confirmation must not ask the model to resolve again")
                    self.assertEqual(app.session_state.current_run["query"], candidate)
                    self.assertEqual(app.session_state.current_run["user_query"], confirmation)
                    self.assertEqual([m["role"] for m in app.session_state.chat_history], ["user", "assistant", "user", "assistant"])
                    answer = app.session_state.chat_history[-1]
                    self.assertEqual(answer["status"], "answered")
                    self.assertEqual(len(answer["sources"]), 1)
                    self.assertIn(candidate, answer["sources"][0]["document"]["text"])
                    self.assertNotIn("pending_clarification", answer)
                    app.run()
                    self.answer.assert_called_once()
                    self.live.assert_called_once_with(candidate)

    def test_slot_completion_resolves_original_request_and_runs_existing_workflow(self):
        request = "How do I renew it?"
        question = "Which licence are you renewing?"
        completion = "My driving licence through Absher"
        resolved = "How do I renew my driving licence through Absher?"
        self.resolutions[request] = self.clarification(request, question)
        self.resolutions[completion] = {"query": resolved, "clarification": None, "contextualized": True}
        app = self.app()
        self.send(app, request)
        self.assertEqual(app.session_state.chat_history[-1]["pending_clarification"]["confirmation_query"], "")
        self.send(app, completion)
        self.live.assert_called_once_with(resolved)
        self.assertEqual(self.context.call_args.args[1][-1]["pending_clarification"], self.resolutions[request]["pending_clarification"])
        self.assertEqual(app.session_state.current_run["query"], resolved)
        self.assertEqual(app.session_state.current_run["user_query"], completion)
        self.assertEqual(app.session_state.chat_history[-1]["status"], "answered")
        self.answer.assert_called_once()

    def test_resolved_confirmation_retry_reuses_query_and_does_not_repeat_clarification(self):
        request = "How do I renew the licence?"
        candidate = "How do I renew a driving licence through Absher?"
        self.resolutions[request] = self.clarification(request, "Do you mean a driving licence through Absher?", candidate)
        self.resolutions["yes"] = {"query": candidate, "clarification": None, "contextualized": True}
        app = self.app()
        self.send(app, request)
        self.live.side_effect = RuntimeError("private retrieval provider detail")
        self.send(app, "yes")
        self.assertEqual(len(app.session_state.chat_history), 3)
        confirmation = deepcopy(app.session_state.chat_history[-1])
        self.assertEqual(confirmation["retrieval_query"], candidate)
        self.assertNotIn("private retrieval provider detail", self.markup(app))
        self.assertTrue(app.session_state.turn_error)
        context_calls = self.context.call_count
        self.context.side_effect = AssertionError("Already resolved query must bypass contextual resolution on retry")
        self.live.side_effect = self.run_live
        app.button(key="retry_message").click().run()
        self.clean(app)
        self.assertEqual(self.context.call_count, context_calls)
        self.assertEqual([call.args[0] for call in self.live.call_args_list], [candidate, candidate])
        self.assertEqual(len(app.session_state.chat_history), 4)
        self.assertEqual(app.session_state.chat_history[-2], confirmation)
        self.assertEqual(app.session_state.chat_history[-1]["turn_id"], confirmation["turn_id"])
        self.assertEqual(app.session_state.current_run["query"], candidate)
        self.assertTrue(app.session_state.current_run["contextualized"])
        self.answer.assert_called_once()
        self.assertNotIn("turn_error", app.session_state)

    def test_new_topic_clears_active_clarification_and_later_yes_cannot_reuse_it(self):
        self.context.side_effect = resolve_with_context
        request = "How do I renew my licence?"
        candidate = "How do I renew my driving licence through Absher?"
        new_topic = "How can I request a building permit through Balady?"
        chain = Mock()
        chain.invoke.side_effect = [
            {"parsed": {"decision": "clarify", "query": request, "clarification": "Do you mean renewing a driving licence through Absher?", "confirmation_query": candidate}},
            {"parsed": {"decision": "unchanged", "query": new_topic, "clarification": "", "confirmation_query": ""}},
        ]
        with patch("frontend.conversation.create_context_chain", return_value=chain):
            app = self.app()
            self.send(app, request)
            self.send(app, new_topic)
            self.live.assert_called_once_with(new_topic)
            self.assertNotIn("pending_clarification", app.session_state.chat_history[-1])
            self.send(app, "yes")
            self.live.assert_called_once_with(new_topic)
            self.assertEqual(chain.invoke.call_count, 2)
            self.assertEqual(app.session_state.chat_history[-1]["status"], "clarification")
            self.assertEqual(app.session_state.chat_history[-1]["pending_clarification"]["confirmation_query"], "")
            self.assertEqual(app.session_state.chat_history[-1]["pending_clarification"]["request"], "yes")
            self.assertNotIn("current_run", app.session_state)

    def test_yes_message_cannot_resolve_pending_human_approval(self):
        request = "Review the structural quality of this service's retrieved evidence"
        self.states[request] = self.pending_state(request)
        app = self.app()
        self.send(app, request)
        pending = deepcopy(app.session_state.current_run)
        history = deepcopy(app.session_state.chat_history)
        counts = (self.live.call_count, self.context.call_count, self.answer.call_count)
        self.assertTrue(app.button(key="send_message").disabled)
        self.assertTrue(app.text_area(key="query_text").disabled)
        # Even a confirmation text in the draft cannot submit the disabled chat.
        app.session_state.query_text = "yes"
        with self.assertRaises(AppTestError):
            app.button(key="send_message").click()
        app.run()
        self.clean(app)
        self.assertEqual(app.session_state.current_run, pending)
        self.assertEqual(app.session_state.chat_history, history)
        self.assertEqual(counts, (self.live.call_count, self.context.call_count, self.answer.call_count))
        self.resume.assert_not_called()
        self.assertTrue(app.button(key="send_message").disabled)
        self.assertFalse(app.button(key="approve_optimization").disabled)


if __name__ == "__main__":
    unittest.main()
