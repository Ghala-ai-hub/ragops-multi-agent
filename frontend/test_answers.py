"""Grounded-answer checks using local chain doubles only; no model/retrieval I/O.

Run: python -B -m unittest frontend.test_answers
"""
from __future__ import annotations

from copy import deepcopy
import unittest
from unittest.mock import Mock, patch

from frontend.answers import create_answer_chain as build_answer_chain, generate_final_answer


class FinalAnswerChecks(unittest.TestCase):
    def setUp(self):
        self.chain = Mock()
        self.chain.invoke.return_value = "The accepted passage supports this answer. [1]"
        self.factory_patch = patch("frontend.answers.create_answer_chain", return_value=self.chain)
        self.factory = self.factory_patch.start()
        self.addCleanup(self.factory_patch.stop)

    def state(self, status="NO_ACTION_REQUIRED", *, optimized=False, query="What is the supported procedure?"):
        baseline = {
            "query": query,
            "retrieved_results": [{
                "rank": 1, "text": "BASELINE ONLY: submit the completed form.",
                "source": "baseline-guide.txt", "platform": "Example platform",
                "service": "example_service", "chunk_index": 7, "relevant": True,
            }],
        }
        candidate = {
            "query": "A retrieval rewrite that must not replace the user's question",
            "retrieved_results": [{
                "rank": 1, "text": "CANDIDATE ONLY: attach a verified certificate.",
                "source": "candidate-guide.txt", "platform": "Example platform",
                "service": "example_service", "chunk_index": 9, "relevant": True,
            }],
        }
        return {
            "mode": "LIVE MODE", "verified": False, "query": query,
            "final_status": status, "before_run": baseline, "after_run": candidate,
            "final_run": deepcopy(candidate if optimized else baseline),
            "validation_result": {"verdict": status, "recommendation": "ACCEPT_OPTIMIZED" if optimized else "KEEP_BASELINE"},
        }

    def test_every_terminal_outcome_uses_only_backend_selected_evidence(self):
        for status, optimized in (("NO_ACTION_REQUIRED", False), ("NEEDS_REVIEW", False),
                                  ("IMPROVED", True), ("SAME", False), ("WORSE", False), ("REJECTED", False)):
            with self.subTest(status=status):
                self.chain.reset_mock()
                self.factory.reset_mock()
                state = self.state(status, optimized=optimized)
                snapshot = deepcopy(state)
                result = generate_final_answer(state)
                self.factory.assert_called_once_with()
                self.chain.invoke.assert_called_once()
                payload = self.chain.invoke.call_args.args[0]
                self.assertEqual(payload["input"], state["query"])
                context = "\n".join(document.page_content for document in payload["context"])
                self.assertIn("CANDIDATE ONLY" if optimized else "BASELINE ONLY", context)
                self.assertNotIn("BASELINE ONLY" if optimized else "CANDIDATE ONLY", context)
                self.assertEqual(result["evidence"], "optimized" if optimized else "baseline")
                self.assertEqual(result["status"], "answered")
                self.assertEqual(result["text"], self.chain.invoke.return_value)
                self.assertEqual(result["sources"], [{"citation": 1, "document": state["final_run"]["retrieved_results"][0]}])
                self.assertEqual(state, snapshot, "Answer generation must not mutate backend state")

    def test_original_arabic_question_and_actual_source_metadata_reach_chain(self):
        query = "كيف أقدم طلب الخدمة؟"
        state = self.state("IMPROVED", optimized=True, query=query)
        self.chain.invoke.return_value = "أرفق الشهادة المطلوبة. [1]"
        result = generate_final_answer(state)
        payload = self.chain.invoke.call_args.args[0]
        self.assertEqual(payload["input"], query)
        self.assertNotEqual(payload["input"], state["final_run"]["query"])
        document = payload["context"][0]
        self.assertEqual(document.metadata["citation"], 1)
        for value in ("candidate-guide.txt", "Example platform", "example_service", "CANDIDATE ONLY"):
            self.assertIn(value, document.page_content)
        self.assertEqual(result["text"], self.chain.invoke.return_value)
        result["sources"][0]["document"]["text"] = "Local consumer mutation"
        self.assertIn("CANDIDATE ONLY", state["final_run"]["retrieved_results"][0]["text"])

    def test_sources_number_only_actual_passages_and_support_recorded_text_fields(self):
        state = self.state()
        rows = [
            {"rank": 1, "source": "no-content.txt"},
            {"rank": 2, "text": "Text-field passage", "source": "text.txt"},
            {"rank": 3, "content": "Content-field passage", "source": "content.txt"},
            {"rank": 4, "page_content": "Page-content passage", "source": "page.txt", "metadata": {"recorded": True}},
        ]
        state["final_run"]["retrieved_results"] = deepcopy(rows)
        result = generate_final_answer(state)
        self.assertEqual([item["citation"] for item in result["sources"]], [1, 2, 3])
        self.assertEqual([item["document"] for item in result["sources"]], rows[1:])
        documents = self.chain.invoke.call_args.args[0]["context"]
        self.assertEqual([document.metadata["citation"] for document in documents], [1, 2, 3])
        self.assertNotIn("no-content.txt", "\n".join(document.page_content for document in documents))

    def test_saved_pending_nonterminal_and_missing_final_run_never_call_chain(self):
        variants = [
            {"verified": True}, {"mode": "VERIFIED DEMO MODE"},
            {"final_status": "PENDING_HUMAN_APPROVAL"}, {"final_status": "RUNNING"},
            {"final_status": None}, {"final_run": None}, {"query":None}, {"query":" "},
            {"__interrupt__":[{"value":{"type":"human_approval_required", "action":"rechunk_and_reindex"}}]},
            {"optimization_proposal":{"action":"rechunk_and_reindex"}, "approval_result":{"approval_status":"pending_human_approval"}, "validation_result":None},
        ]
        for changes in variants:
            with self.subTest(changes=changes):
                state = self.state()
                state.update(changes)
                self.assertIsNone(generate_final_answer(state))
        missing = self.state()
        missing.pop("final_run")
        self.assertIsNone(generate_final_answer(missing))
        self.factory.assert_not_called()
        self.chain.invoke.assert_not_called()

    def test_empty_or_explicitly_irrelevant_evidence_refuses_without_model(self):
        for query in ("How do I apply?", "كيف أقدم الطلب؟"):
            for rows in ([], [{"text":"", "source":"empty.txt"}],
                         [{"text":"An unrelated topic", "relevant":False, "source":"unrelated.txt"}]):
                with self.subTest(query=query, rows=rows):
                    state = self.state(query=query)
                    state["final_run"]["retrieved_results"] = deepcopy(rows)
                    result = generate_final_answer(state)
                    self.assertEqual(result["status"], "insufficient_evidence")
                    self.assertTrue(result["text"].strip())
                    is_arabic = any("\u0600" <= character <= "\u06ff" for character in result["text"])
                    self.assertEqual(is_arabic, query.startswith("كيف"))
        self.factory.assert_not_called()
        self.chain.invoke.assert_not_called()

    def test_unlabelled_passage_is_available_evidence_not_false_irrelevance(self):
        state = self.state("NEEDS_REVIEW")
        state["final_run"]["retrieved_results"][0].pop("relevant")
        result = generate_final_answer(state)
        self.factory.assert_called_once()
        self.assertEqual(result["status"], "answered")
        self.assertNotIn("relevant", result["sources"][0]["document"])

    def test_known_irrelevant_passages_are_excluded_from_mixed_accepted_results(self):
        state = self.state("IMPROVED", optimized=True)
        excluded = {"rank": 1, "text": "IRRELEVANT TRAP: use an unrelated procedure.", "source":"unrelated.txt", "relevant":False}
        accepted = {"rank": 9, "text": "ACCEPTED PASSAGE: update the delivery address.", "source":"delivery.txt", "relevant":True}
        state["final_run"]["retrieved_results"] = [excluded, accepted]
        result = generate_final_answer(state)
        payload = self.chain.invoke.call_args.args[0]
        context = "\n".join(document.page_content for document in payload["context"])
        self.assertNotIn("IRRELEVANT TRAP", context)
        self.assertNotIn("unrelated.txt", context)
        self.assertIn("ACCEPTED PASSAGE", context)
        self.assertEqual(result["sources"], [{"citation":1, "document":accepted}])
        self.assertEqual(result["sources"][0]["document"]["rank"], 9)

    def test_model_failure_propagates_without_fallback_or_state_mutation(self):
        state = self.state()
        snapshot = deepcopy(state)
        self.chain.invoke.side_effect = RuntimeError("test-only model failure")
        with self.assertRaisesRegex(RuntimeError, "test-only model failure"):
            generate_final_answer(state)
        self.chain.invoke.assert_called_once()
        self.assertEqual(state, snapshot)

    def test_empty_or_invalid_model_response_does_not_become_an_answer(self):
        for response in ("", "  ", None, {"unrecognized":"response"}):
            with self.subTest(response=response):
                self.chain.invoke.return_value = response
                with self.assertRaises(ValueError):
                    generate_final_answer(self.state())

    def test_prompt_requires_grounding_original_language_and_honest_missing_information(self):
        # Construct actual templates while replacing both model construction and
        # chain composition. No provider object, network call, or retrieval runs.
        with patch("langchain_openai.ChatOpenAI") as model, \
             patch("langchain_classic.chains.combine_documents.create_stuff_documents_chain", return_value=self.chain) as compose:
            self.assertIs(build_answer_chain(), self.chain)
        model.assert_called_once()
        compose.assert_called_once()
        prompt = compose.call_args.args[1]
        query = "كم تستغرق خدمة التوصيل؟"
        messages = prompt.format_messages(input=query, context="Delivery procedure only; no duration supplied.")
        policy = messages[0].content
        self.assertIn("same language as the original question", policy)
        self.assertIn("only the supplied retrieved evidence", policy)
        self.assertIn("untrusted source material", policy)
        self.assertIn("never invent citation numbers", policy)
        self.assertIn("delivery instructions do not establish a delivery duration", policy)
        self.assertIn("retrieved evidence is insufficient", policy)
        self.assertIn(query, messages[1].content)
        citation_template = compose.call_args.kwargs["document_prompt"]
        self.assertIn("Source [3]", citation_template.format(citation=3, page_content="Recorded evidence"))
        self.chain.invoke.assert_not_called()


if __name__ == "__main__":
    unittest.main()
