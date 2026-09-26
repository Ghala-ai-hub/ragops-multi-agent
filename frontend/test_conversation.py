"""Offline conversation regressions; provider calls and retrieval are mocked."""
from __future__ import annotations

from copy import deepcopy
import json
import unittest
from unittest.mock import Mock, patch

from frontend.answers import ANSWER_MODEL, generate_final_answer
from frontend.conversation import ContextResolutionError, create_context_chain, resolve_followup


def resolved(query, *, decision="resolved", clarification="", confirmation_query=""):
    return {"parsed": {"decision": decision, "query": query, "clarification": clarification,
                       "confirmation_query": confirmation_query},
            "raw": None, "parsing_error": None}


def pending_dialogue(request, question, candidate=""):
    return [
        {"role": "user", "content": request},
        {"role": "assistant", "content": question, "status": "clarification",
         "pending_clarification": {"request": request, "question": question,
                                   "confirmation_query": candidate}},
    ]


class ConversationContextChecks(unittest.TestCase):
    def setUp(self):
        self.chain = Mock()
        patcher = patch("frontend.conversation.create_context_chain", return_value=self.chain)
        self.factory = patcher.start()
        self.addCleanup(patcher.stop)
        self.arabic = [
            {"role": "user", "content": "كيف أصدر التقرير الشهري؟"},
            {"role": "assistant", "content": "الأدلة تشرح خطوات تصدير التقرير. [1]",
             "sources": [{"secret": "must not enter resolver"}]},
        ]

    def test_standalone_first_question_preserves_original_after_context_check(self):
        query = "كيف أصدر التقرير الشهري؟"
        self.chain.invoke.return_value = resolved(query, decision="unchanged")
        self.assertEqual(resolve_followup(query, []), {
            "query": query, "clarification": None, "contextualized": False,
        })
        self.factory.assert_called_once()
        self.assertEqual(self.chain.invoke.call_args.args[0]["history"], "[]")

    def test_ambiguous_first_question_retains_known_request_without_invented_topic(self):
        query, question = "طيب وش الشروط؟", "شروط ماذا تقصد؟"
        self.chain.invoke.return_value = resolved(query, decision="clarify", clarification=question)
        result = resolve_followup(query, [])
        self.assertEqual(result["query"], query)
        self.assertEqual(result["clarification"], question)
        self.assertFalse(result["contextualized"])
        self.assertEqual(result["pending_clarification"], {
            "request": query, "question": question, "confirmation_query": "",
        })
        self.chain.invoke.return_value = resolved("ما شروط تصدير التقرير الشهري؟")
        with self.assertRaises(ContextResolutionError):
            resolve_followup(query, [])

    def test_identical_first_question_is_safe_when_model_labels_it_resolved(self):
        query = "How do I export a report?"
        self.chain.invoke.return_value = resolved("  " + query + "  ")
        self.assertEqual(resolve_followup(query, []), {
            "query": query, "clarification": None, "contextualized": False,
        })

    def test_arabic_followup_resolves_only_topic_and_keeps_inputs_unchanged(self):
        snapshot = deepcopy(self.arabic)
        self.chain.invoke.return_value = resolved("ما شروط تصدير التقرير الشهري؟")
        result = resolve_followup("طيب وش الشروط؟", self.arabic)
        self.assertEqual(result, {
            "query": "ما شروط تصدير التقرير الشهري؟", "clarification": None, "contextualized": True,
        })
        payload = self.chain.invoke.call_args.args[0]
        self.assertEqual(payload["question"], "طيب وش الشروط؟")
        self.assertEqual(payload["question_language"], "Arabic")
        self.assertIn("كيف أصدر التقرير الشهري؟", payload["history"])
        self.assertNotIn("sources", payload["history"])
        self.assertNotIn("secret", payload["history"])
        self.assertEqual(self.arabic, snapshot)

    def test_english_third_turn_uses_prior_resolved_topic(self):
        messages = [
            {"role": "user", "content": "How do I export the monthly report?"},
            {"role": "assistant", "content": "The supported steps are listed. [1]"},
            {"role": "user", "content": "And the formats?",
             "retrieval_query": "Which formats can I use to export the monthly report?"},
            {"role": "assistant", "content": "The evidence lists these formats. [1]"},
        ]
        query = "How do I export the monthly report in PDF format?"
        self.chain.invoke.return_value = resolved(query)
        result = resolve_followup("And how do I use PDF?", messages)
        self.assertTrue(result["contextualized"])
        self.assertEqual(result["query"], query)
        history = json.loads(self.chain.invoke.call_args.args[0]["history"])
        self.assertEqual(history[2]["retrieval_query"], messages[2]["retrieval_query"])
        self.assertEqual(self.chain.invoke.call_args.args[0]["question_language"], "English")

    def test_english_followup_can_keep_an_arabic_subject_name(self):
        standalone = "What are the requirements for exporting التقرير الشهري?"
        self.chain.invoke.return_value = resolved(standalone)
        result = resolve_followup("What are its requirements?", self.arabic)
        self.assertEqual(result["query"], standalone)
        self.assertIsNone(result["clarification"])
        self.assertEqual(self.chain.invoke.call_args.args[0]["question_language"], "English")

    def test_wrong_language_rewrite_is_retryable_error_not_generic_clarification(self):
        self.chain.invoke.return_value = resolved("ما متطلبات تصدير التقرير الشهري؟")
        with self.assertRaises(ContextResolutionError):
            resolve_followup("What are its requirements?", self.arabic)

    def test_numbers_and_punctuation_do_not_determine_question_language(self):
        query, question = "٢١ — What are its requirements?", "Which report do you mean?"
        self.chain.invoke.return_value = resolved(query, decision="clarify", clarification=question)
        result = resolve_followup(query, self.arabic)
        self.assertEqual(result["clarification"], question)
        self.assertEqual(self.chain.invoke.call_args.args[0]["question_language"], "English")

    def test_new_topic_preserves_original_and_supersedes_pending_request(self):
        messages = pending_dialogue("How do I export a report?", "Which format do you want?")
        query = "How do I configure the notification settings?"
        self.chain.invoke.return_value = resolved(query, decision="unchanged")
        self.assertEqual(resolve_followup(query, messages), {
            "query": query, "clarification": None, "contextualized": False,
        })

    def test_confirmation_displays_exact_candidate_and_retains_pending_request(self):
        for request, candidate, prefix, history in [
            ("كيف أصدره؟", "كيف أصدر التقرير الشهري؟", "هل تقصد: ", self.arabic),
            ("How do I export it?", "How do I export the monthly report?", "Do you mean: ",
             [{"role": "user", "content": "I need the monthly report."}]),
        ]:
            with self.subTest(request=request):
                self.chain.invoke.return_value = resolved(request, decision="clarify", confirmation_query=candidate)
                result = resolve_followup(request, history)
                self.assertEqual(result["query"], request)
                self.assertEqual(result["clarification"], prefix + candidate)
                self.assertEqual(result["pending_clarification"], {
                    "request": request, "question": prefix + candidate, "confirmation_query": candidate,
                })
                self.assertFalse(result["contextualized"])

    def test_exact_arabic_or_english_confirmation_uses_only_visible_candidate(self):
        for candidate, request, question, replies in [
            ("كيف أصدر التقرير الشهري؟", "كيف أصدر التقرير؟", "هل تقصد: كيف أصدر التقرير الشهري؟",
             ["نعم", "نَعَمْ!", " صحيح. ", "صَحِيحٌ"]),
            ("How do I export the monthly report?", "How do I export the report?",
             "Do you mean: How do I export the monthly report?", ["yes", " YES! ", "Correct."]),
        ]:
            messages = pending_dialogue(request, question, candidate)
            snapshot = deepcopy(messages)
            for reply in replies:
                with self.subTest(reply=reply):
                    self.assertEqual(resolve_followup(reply, messages), {
                        "query": candidate, "clarification": None, "contextualized": True,
                    })
            self.assertEqual(messages, snapshot)
        self.factory.assert_not_called()

    def test_yes_with_a_correction_must_not_take_confirmation_shortcut(self):
        candidate = "How do I export the monthly report?"
        messages = pending_dialogue("How do I export the report?", "Do you mean: " + candidate, candidate)
        replacement = "How do I export the weekly report?"
        self.chain.invoke.return_value = resolved(replacement)
        result = resolve_followup("Yes, but I mean the weekly report.", messages)
        self.factory.assert_called_once()
        self.assertEqual(result["query"], replacement)
        self.assertNotEqual(result["query"], candidate)

    def test_arabic_confirmation_with_correction_uses_the_new_explicit_topic(self):
        candidate = "كيف أصدر التقرير الشهري؟"
        messages = pending_dialogue("كيف أصدر التقرير؟", "هل تقصد: " + candidate, candidate)
        replacement = "كيف أصدر التقرير الأسبوعي؟"
        self.chain.invoke.return_value = resolved(replacement)
        result = resolve_followup("نعم لكن أقصد التقرير الأسبوعي", messages)
        self.factory.assert_called_once()
        self.assertEqual(result["query"], replacement)

    def test_negative_reply_clears_candidate_and_retains_request_without_retrieval(self):
        for request, candidate, prefix, reply in [
            ("How do I export the report?", "How do I export the monthly report?", "Do you mean: ", "No."),
            ("كيف أصدر التقرير؟", "كيف أصدر التقرير الشهري؟", "هل تقصد: ", "لا"),
        ]:
            with self.subTest(reply=reply):
                messages = pending_dialogue(request, prefix + candidate, candidate)
                result = resolve_followup(reply, messages)
                self.assertTrue(result["clarification"])
                self.assertFalse(result["contextualized"])
                self.assertEqual(result["pending_clarification"]["request"], request)
                self.assertEqual(result["pending_clarification"]["confirmation_query"], "")
        self.factory.assert_not_called()

    def test_short_reply_completes_pending_slot_without_losing_request(self):
        messages = pending_dialogue("How do I export the report?", "Which export format do you want?")
        complete = "How do I export the report in PDF format?"
        self.chain.invoke.return_value = resolved(complete)
        result = resolve_followup("PDF", messages)
        self.assertEqual(result, {"query": complete, "clarification": None, "contextualized": True})
        payload = self.chain.invoke.call_args.args[0]
        pending = json.loads(payload["pending_clarification"])
        self.assertEqual(pending, messages[-1]["pending_clarification"])
        self.assertEqual(json.loads(payload["history"])[-1]["status"], "clarification")

    def test_resolver_cannot_repeat_an_answered_clarification(self):
        messages = pending_dialogue("How do I export the report?", "Which export format do you want?")
        self.chain.invoke.return_value = resolved("How do I export the report as PDF?", decision="clarify",
                                                clarification="Which export format do you want?")
        with self.assertRaises(ContextResolutionError):
            resolve_followup("PDF", messages)

    def test_bare_yes_or_no_without_clarification_context_never_becomes_retrieval(self):
        for messages in [[], [{"role": "assistant", "content": "Do you mean the monthly report?"}]]:
            for reply in ("yes", "no"):
                with self.subTest(messages=messages, reply=reply):
                    result = resolve_followup(reply, messages)
                    self.assertIsNotNone(result["clarification"])
                    self.assertFalse(result["contextualized"])
        self.factory.assert_not_called()

    def test_open_choice_yes_retains_pending_request_and_asks_for_missing_detail(self):
        messages = pending_dialogue("How do I export the report?", "PDF or CSV?")
        self.chain.invoke.return_value = resolved("How do I export the report?", decision="clarify",
                                                clarification="Please choose the export format: PDF or CSV?")
        result = resolve_followup("yes", messages)
        self.assertTrue(result["clarification"])
        self.assertEqual(result["pending_clarification"]["request"], "How do I export the report?")
        self.assertEqual(result["pending_clarification"]["confirmation_query"], "")
        self.assertNotEqual(result["clarification"], "PDF or CSV?")
        self.factory.assert_called_once()
        payload = self.chain.invoke.call_args.args[0]
        self.assertEqual(json.loads(payload["pending_clarification"]), messages[-1]["pending_clarification"])
        self.assertEqual(json.loads(payload["history"])[-1]["content"], "PDF or CSV?")

    def test_yes_and_no_complete_a_boolean_slot_through_context_resolution(self):
        messages = pending_dialogue("How do I export the report?", "Should archived records be included?")
        for reply, qualifier in [("yes", "including"), ("no", "excluding")]:
            with self.subTest(reply=reply):
                complete = f"How do I export the report {qualifier} archived records?"
                self.chain.invoke.return_value = resolved(complete)
                result = resolve_followup(reply, messages)
                self.assertEqual(result, {"query": complete, "clarification": None, "contextualized": True})
                payload = self.chain.invoke.call_args.args[0]
                self.assertEqual(payload["question"], reply)
                self.assertEqual(json.loads(payload["pending_clarification"]), messages[-1]["pending_clarification"])
        self.assertEqual(self.factory.call_count, 2)

    def test_model_cannot_leave_a_pending_acknowledgement_unresolved(self):
        messages = pending_dialogue("How do I export the report?", "Should archived records be included?")
        for reply in ("yes", "no"):
            for decision in ("unchanged", "resolved"):
                with self.subTest(reply=reply, decision=decision):
                    self.chain.invoke.return_value = resolved(reply, decision=decision)
                    with self.assertRaises(ContextResolutionError):
                        resolve_followup(reply, messages)

    def test_model_confirmation_candidate_cannot_be_only_an_acknowledgement(self):
        request = "How do I export the report?"
        for candidate in ("yes", "no"):
            with self.subTest(candidate=candidate):
                self.chain.invoke.return_value = resolved(request, decision="clarify", confirmation_query=candidate)
                with self.assertRaises(ContextResolutionError):
                    resolve_followup(request, [])

    def test_stored_acknowledgement_candidate_cannot_take_a_local_shortcut(self):
        request = "How do I export the report?"
        for candidate in ("yes", "no"):
            with self.subTest(candidate=candidate):
                messages = pending_dialogue(request, "Do you mean: " + candidate, candidate)
                self.chain.invoke.return_value = resolved(request, decision="clarify",
                                                        clarification="Which export format do you want?")
                result = resolve_followup("yes", messages)
                self.assertTrue(result["clarification"])
                self.assertFalse(result["contextualized"])
                self.assertIsNone(json.loads(self.chain.invoke.call_args.args[0]["pending_clarification"]))
        self.assertEqual(self.factory.call_count, 2)

    def test_legacy_clarification_without_pending_metadata_uses_recorded_dialogue(self):
        for question, reply, complete in [
            ("Which format do you want?", "PDF", "How do I export the report as PDF?"),
            ("Should archived records be included?", "yes", "How do I export the report including archived records?"),
            ("Do you mean: How do I export the monthly report?", "yes", "How do I export the monthly report?"),
        ]:
            with self.subTest(question=question, reply=reply):
                messages = [{"role": "user", "content": "How do I export the report?"},
                            {"role": "assistant", "content": question, "status": "clarification"}]
                self.chain.invoke.return_value = resolved(complete)
                result = resolve_followup(reply, messages)
                self.assertEqual(result, {"query": complete, "clarification": None, "contextualized": True})
                payload = self.chain.invoke.call_args.args[0]
                self.assertIsNone(json.loads(payload["pending_clarification"]))
                self.assertEqual(json.loads(payload["history"])[-1], messages[-1])
        self.assertEqual(self.factory.call_count, 3)

    def test_prior_confirmation_cannot_leak_past_later_assistant_message(self):
        candidate = "How do I export the monthly report?"
        messages = pending_dialogue("How do I export the report?", "Do you mean: " + candidate, candidate)
        messages.extend(pending_dialogue("I have a different question.", "What would you like to ask?"))
        self.chain.invoke.return_value = resolved("I have a different question.", decision="clarify",
                                                clarification="Please name the topic of your new question.")
        result = resolve_followup("yes", messages)
        self.assertIsNotNone(result["clarification"])
        self.assertNotEqual(result["query"], candidate)
        self.assertEqual(result["pending_clarification"]["request"], "I have a different question.")
        self.factory.assert_called_once()
        self.assertEqual(json.loads(self.chain.invoke.call_args.args[0]["pending_clarification"]),
                         messages[-1]["pending_clarification"])

    def test_completed_answer_expires_a_previous_confirmation(self):
        candidate = "How do I export the monthly report?"
        messages = pending_dialogue("How do I export the report?", "Do you mean: " + candidate, candidate)
        messages.extend([
            {"role": "user", "content": "How do I print a chart instead?"},
            {"role": "assistant", "content": "The evidence lists the print steps. [1]", "status": "answer"},
        ])
        result = resolve_followup("yes", messages)
        self.assertTrue(result["clarification"])
        self.assertEqual(result["pending_clarification"]["confirmation_query"], "")
        self.assertNotEqual(result["query"], candidate)
        self.factory.assert_not_called()

    def test_hidden_candidate_cannot_be_auto_selected(self):
        messages = pending_dialogue("How do I export the report?", "Which report do you mean?",
                                    "How do I export the monthly report?")
        self.chain.invoke.return_value = resolved("How do I export the report?", decision="clarify",
                                                clarification="Please name the report you want to export.")
        result = resolve_followup("yes", messages)
        self.assertIsNotNone(result["clarification"])
        self.assertNotEqual(result["query"], messages[-1]["pending_clarification"]["confirmation_query"])
        self.factory.assert_called_once()
        self.assertIsNone(json.loads(self.chain.invoke.call_args.args[0]["pending_clarification"]))

    def test_broad_and_other_domain_questions_are_not_forced_into_service_subtypes(self):
        for query in ["How do I back up my database?", "How does photosynthesis work?",
                      "كيف أتعلم البرمجة؟", "What are the reporting options?"]:
            with self.subTest(query=query):
                self.chain.invoke.return_value = resolved(query, decision="unchanged")
                self.assertEqual(resolve_followup(query, []), {
                    "query": query, "clarification": None, "contextualized": False,
                })

    def test_refusal_malformed_or_incomplete_responses_are_retryable_errors(self):
        responses = [
            None, "invalid", {"parsed": None}, {"parsed": {}},
            {"parsed": {"decision": "resolved", "query": "a topic", "clarification": ""}},
            resolved("", decision="resolved"), resolved("a topic", decision="unknown"),
            resolved("a topic", clarification="conflicting output"),
            resolved("a topic", confirmation_query="conflicting candidate"),
            resolved("", decision="clarify", clarification="Which format?"),
            resolved("export a report", decision="clarify"),
            {**resolved("a valid topic"), "parsing_error": ValueError("bad JSON")},
            {"parsed": {"decision": "resolved", "query": 7, "clarification": "", "confirmation_query": ""}},
            {"parsed": {"decision": "resolved", "query": "a topic", "clarification": "",
                        "confirmation_query": "", "unexpected": "extra data"}},
        ]
        for response in responses:
            with self.subTest(response=response):
                self.chain.invoke.return_value = response
                with self.assertRaises(ContextResolutionError):
                    resolve_followup("What are its requirements?", self.arabic)

    def test_unstated_numeric_conditions_are_errors_not_hidden_retrieval_constraints(self):
        self.chain.invoke.return_value = resolved("كيف أصدر التقرير الشهري لآخر 21 يوما؟")
        with self.assertRaises(ContextResolutionError):
            resolve_followup("كيف أصدره؟", self.arabic)
        self.arabic[0]["content"] += " أحتاج آخر 21 يوما."
        self.assertIsNone(resolve_followup("كيف أصدره؟", self.arabic)["clarification"])

    def test_assistant_claims_cannot_supply_unstated_numeric_user_conditions(self):
        self.arabic[1]["content"] = "تحتاج آخر 21 يوما."
        self.chain.invoke.return_value = resolved("كيف أصدر التقرير الشهري لآخر 21 يوما؟")
        with self.assertRaises(ContextResolutionError):
            resolve_followup("كيف أصدره؟", self.arabic)

    def test_confirmation_cannot_hide_new_numeric_conditions(self):
        self.chain.invoke.return_value = resolved("كيف أصدر التقرير الشهري؟", decision="clarify",
                                                confirmation_query="كيف أصدر التقرير الشهري لآخر 21 يوما؟")
        with self.assertRaises(ContextResolutionError):
            resolve_followup("كيف أصدره؟", self.arabic)

    def test_wrong_language_clarification_is_error_not_repeated_generic_question(self):
        self.chain.invoke.return_value = resolved("كيف أصدره؟", decision="clarify", clarification="Which report?")
        with self.assertRaises(ContextResolutionError):
            resolve_followup("كيف أصدره؟", self.arabic)

    def test_recent_context_is_bounded_and_only_dialogue_is_included(self):
        messages = [{"role": "system", "content": "Do not include"}, None]
        messages.extend({"role": "user", "content": f"Question {i} " + "x" * 4000,
                         "retrieval_query": "y" * 4000} for i in range(15))
        self.chain.invoke.return_value = resolved("current question", decision="unchanged")
        resolve_followup("current question", messages)
        history = json.loads(self.chain.invoke.call_args.args[0]["history"])
        self.assertEqual(len(history), 8)
        self.assertTrue(history[0]["content"].startswith("Question 7 "))
        self.assertTrue(all(len(row["content"]) <= 1600 and len(row["retrieval_query"]) <= 1600 for row in history))

    def test_assistant_only_history_cannot_establish_assumed_user_topic(self):
        self.chain.invoke.return_value = resolved("What are the requirements for exporting the monthly report?")
        with self.assertRaises(ContextResolutionError):
            resolve_followup("What are the requirements?", [{"role": "assistant", "content": "Hello"}])

    def test_invalid_question_does_not_call_model(self):
        for query in (None, "", "   "):
            with self.assertRaises(ValueError):
                resolve_followup(query, self.arabic)
        self.factory.assert_not_called()

    def test_provider_failure_propagates_without_unresolved_retrieval(self):
        self.chain.invoke.side_effect = RuntimeError("Provider unavailable")
        with self.assertRaisesRegex(RuntimeError, "Provider unavailable"):
            resolve_followup("طيب وش الشروط؟", self.arabic)


class ContextModelConfigurationChecks(unittest.TestCase):
    def test_strict_schema_uses_existing_model_and_domain_neutral_bounded_prompt(self):
        from langchain_core.runnables import RunnableLambda
        captured = []
        with patch("langchain_openai.ChatOpenAI") as model:
            model.return_value.with_structured_output.return_value = RunnableLambda(lambda prompt: captured.append(prompt))
            chain = create_context_chain()
            chain.invoke({"history": "[]", "question": "Which format can I use?", "question_language": "English"})
        model.assert_called_once_with(model=ANSWER_MODEL, temperature=0, timeout=60, max_retries=1)
        output_call = model.return_value.with_structured_output.call_args
        self.assertEqual(output_call.kwargs, {"method": "json_schema", "strict": True, "include_raw": True})
        schema = output_call.args[0]
        self.assertFalse(schema["additionalProperties"])
        self.assertEqual(set(schema["required"]), {"decision", "query", "clarification", "confirmation_query"})
        self.assertEqual(set(schema["properties"]), set(schema["required"]))
        self.assertTrue(all(value["type"] == "string" for value in schema["properties"].values()))
        policy = captured[0].to_messages()[0].content
        self.assertIn("not factual evidence", policy)
        self.assertIn("English", policy)
        self.assertIn("confirmation_query", policy)
        self.assertIn("clarification", policy.lower())
        self.assertIn("new topic", policy.lower())
        self.assertIn("broad", policy.lower())
        for corpus_example in ("Absher", "Balady", "Najiz", "Sakani", "driving licence"):
            self.assertNotIn(corpus_example, policy)


class ContextualAnswerChecks(unittest.TestCase):
    def test_original_question_controls_language_resolved_query_controls_reference_only(self):
        state = {
            "mode": "LIVE MODE", "query": "ما شروط تصدير التقرير الشهري؟", "user_query": "طيب وش الشروط؟",
            "final_status": "NO_ACTION_REQUIRED", "final_run": {
                "retrieved_results": [{"text": "ACCEPTED EVIDENCE", "source": "guide.txt", "relevant": True}],
            },
            "before_run": {"retrieved_results": [{"text": "NOT ACCEPTED"}]},
        }
        snapshot = deepcopy(state)
        chain = Mock()
        chain.invoke.return_value = "الشروط المدعومة فقط. [1]"
        with patch("frontend.answers.create_answer_chain", return_value=chain):
            answer = generate_final_answer(state)
        payload = chain.invoke.call_args.args[0]
        self.assertEqual(payload["input"], state["user_query"])
        self.assertIn(state["query"], payload["resolved_context"])
        evidence = "\n".join(doc.page_content for doc in payload["context"])
        self.assertIn("ACCEPTED EVIDENCE", evidence)
        self.assertNotIn("NOT ACCEPTED", evidence)
        self.assertNotIn(state["query"], evidence)
        self.assertEqual(answer["sources"][0]["document"]["source"], "guide.txt")
        self.assertEqual(state, snapshot)


if __name__ == "__main__":
    unittest.main()
