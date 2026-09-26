"""Offline optional-tracing checks: local native runs, fake SDK transport only."""
from __future__ import annotations

from contextlib import ExitStack
from copy import deepcopy
from datetime import datetime, timezone
import io
import json
import logging
import os
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
from uuid import UUID, uuid4

from langchain_core.runnables import RunnableLambda
from streamlit.testing.v1 import AppTest

from frontend import observability
from frontend.adapter import FrontendAdapter, RuntimeStatus


ROOT = Path(__file__).resolve().parents[1]
PRIVATE_MARKER = "FAKE_PRIVATE_CREDENTIAL_MUST_STAY_PRIVATE"
PROJECT = "offline-observability-tests"
CREATE_NATIVE_CLIENT = observability._create_client


class DeferredThread:
    """Run only the RAGOps verification task when explicitly requested."""

    pending = []

    def __init__(self, target=None, args=(), kwargs=None, name=None, **unused):
        self.target = target
        self.args = args
        self.kwargs = kwargs or {}
        self.name = name

    def start(self):
        if self.name == "ragops-trace-verification":
            self.pending.append(self)

    def run(self):
        self.target(*self.args, **self.kwargs)

class FakeSDKClient:
    """SDK transport protocol, with no sockets, credentials, or remote writes."""

    def __init__(self):
        self.project_id = uuid4()
        self.created = []
        self.updated = []
        self.reads = []
        self.closed = []
        self.failure = None
        self.confirmed_url = None
        self.remote_id = None
        self.remote_project_id = None

    def create_run(self, **kwargs):
        self.created.append(deepcopy(kwargs))

    def update_run(self, **kwargs):
        self.updated.append(deepcopy(kwargs))

    def read_project(self, *args, **kwargs):
        self.reads.append(("project", args, kwargs))
        if self.failure:
            raise self.failure
        return SimpleNamespace(id=self.project_id, name=PROJECT)

    def read_run(self, run_id, **kwargs):
        self.reads.append(("run", (run_id,), kwargs))
        if self.failure:
            raise self.failure
        run_id = self.remote_id or run_id
        url = self.confirmed_url or f"https://smith.langchain.com/o/offline/projects/p/{self.project_id}/r/{run_id}"
        return SimpleNamespace(id=UUID(str(run_id)), session_id=self.remote_project_id or self.project_id,
                               url=url, start_time=datetime.now(timezone.utc), end_time=datetime.now(timezone.utc))

    def get_run_url(self, *args, **kwargs):
        if self.failure:
            raise self.failure
        return self.confirmed_url

    def close(self, **kwargs):
        self.closed.append(kwargs)


class OfflineTracingBase(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.dict(os.environ, {
            "LANGSMITH_TRACING": "false", "LANGSMITH_API_KEY": "",
            "LANGSMITH_PROJECT": PROJECT, "LANGCHAIN_CALLBACKS_BACKGROUND": "false",
            "USERPROFILE": str(Path.home()), "STREAMLIT_BROWSER_GATHER_USAGE_STATS": "false",
        }, clear=True))
        self.stack.enter_context(patch("dotenv.load_dotenv", return_value=False))
        self.network = [self.stack.enter_context(patch(target, side_effect=AssertionError("Network forbidden during offline tracing checks")))
                        for target in ("requests.sessions.Session.request", "requests.sessions.Session.send",
                                       "httpx.Client.send", "httpx.AsyncClient.send", "socket.create_connection")]
        self.log = io.StringIO()
        handler = logging.StreamHandler(self.log)
        logger = logging.getLogger()
        logger.addHandler(handler)
        self.addCleanup(logger.removeHandler, handler)

    def tearDown(self):
      self.assertNotIn(PRIVATE_MARKER, self.log.getvalue())

class ObservabilityChecks(OfflineTracingBase):
    def setUp(self):
        super().setUp()
        DeferredThread.pending = []
        self.client = FakeSDKClient()
        self.factory = self.stack.enter_context(patch("frontend.observability._create_client", return_value=self.client))
        self.stack.enter_context(patch("frontend.observability.threading.Thread", DeferredThread))

    def enable(self):
        os.environ["LANGSMITH_TRACING"] = "true"
        os.environ["LANGSMITH_API_KEY"] = PRIVATE_MARKER

    def native_run(self, value="local input"):
        with observability.capture_traces() as capture:
            result = RunnableLambda(lambda item: item.upper(), name="offline-native-chain").invoke(value)
        self.assertEqual(result, value.upper())
        return capture

    def verify(self):
        workers, DeferredThread.pending = DeferredThread.pending, []
        for worker in workers:
            worker.run()

    def test_tracing_requires_explicit_flag_and_key(self):
        for flag, key, enabled in (("false", PRIVATE_MARKER, False), ("true", "", False), ("", PRIVATE_MARKER, False), ("true", PRIVATE_MARKER, True)):
            with self.subTest(flag=flag, key_present=bool(key)):
                os.environ["LANGSMITH_TRACING"], os.environ["LANGSMITH_API_KEY"] = flag, key
                settings = observability.tracing_settings()
                self.assertEqual(settings.enabled, enabled)
                self.assertEqual(settings.project, PROJECT)
                self.assertNotIn(PRIVATE_MARKER, repr(settings))
        self.factory.assert_not_called()

    def test_project_never_exposes_a_misconfigured_credential(self):
        self.enable()
        os.environ["LANGSMITH_PROJECT"] = PRIVATE_MARKER
        settings = observability.tracing_settings()
        self.assertFalse(settings.enabled)
        self.assertNotIn(PRIVATE_MARKER, repr(settings))

    def test_native_client_batches_and_redacts_sensitive_payload_fields(self):
        self.enable()
        with patch.object(observability, "_CLIENT", None), patch.object(observability, "_CLIENT_SIGNATURE", ""), \
             patch.object(observability, "Client", return_value=self.client) as sdk:
            self.assertIs(CREATE_NATIVE_CLIENT(), self.client)
            self.assertIs(CREATE_NATIVE_CLIENT(), self.client)
            sdk.assert_called_once()
            arguments = sdk.call_args.kwargs
            self.assertTrue(arguments["auto_batch_tracing"])
            self.assertEqual(list(arguments["api_urls"]), ["https://api.smith.langchain.com"])
            payload = {"query": "Public text " + PRIVATE_MARKER,
                       "nested": {"authorization": "Bearer fake", "service": "Public service"}}
            for hook in ("anonymizer", "hide_inputs", "hide_outputs", "hide_metadata"):
                sanitized = arguments[hook](payload)
                self.assertNotIn(PRIVATE_MARKER, json.dumps(sanitized))
                self.assertEqual(sanitized["nested"]["authorization"], "[redacted]")
                self.assertEqual(sanitized["nested"]["service"], "Public service")
            self.assertNotIn(PRIVATE_MARKER, observability._CLIENT_SIGNATURE)

    def test_disabled_tracing_overrides_legacy_flag_and_does_not_create_client(self):
        os.environ["LANGSMITH_API_KEY"] = PRIVATE_MARKER
        os.environ["LANGCHAIN_TRACING_V2"] = "true"
        capture = self.native_run()
        self.factory.assert_not_called()
        self.assertEqual(capture.references, [])
        self.assertEqual(capture.snapshot(), [])
        self.assertEqual(DeferredThread.pending, [])

    def test_enabled_flag_without_key_does_not_trace_native_chain(self):
        os.environ["LANGSMITH_TRACING"] = "true"
        capture = self.native_run()
        self.factory.assert_not_called()
        self.assertEqual(capture.references, [])
        self.assertEqual(capture.snapshot(), [])
        self.assertEqual(DeferredThread.pending, [])

    def test_capture_without_verification_never_schedules_remote_readback(self):
        self.enable()
        with observability.capture_traces(verify=False) as capture:
            self.assertEqual(RunnableLambda(lambda value: value + 1).invoke(3), 4)
        self.assertEqual(len(capture.references), 1)
        self.assertEqual(capture.snapshot(), [])
        self.assertEqual(DeferredThread.pending, [])
        self.assertEqual(self.client.reads, [])

    def test_broken_sdk_context_still_disables_legacy_tracing_without_replaying_body(self):
        from langsmith.run_helpers import get_tracing_context

        class BrokenContext:
            def __enter__(self):
                raise RuntimeError(PRIVATE_MARKER)

            def __exit__(self, *args):
                return False

        self.enable()
        os.environ["LANGCHAIN_TRACING_V2"] = "true"
        before = get_tracing_context()["enabled"]
        operation = Mock(return_value="one application result")
        with patch.object(observability, "tracing_context", return_value=BrokenContext()):
            with observability.capture_traces() as capture:
                self.assertIs(get_tracing_context()["enabled"], False)
                result = RunnableLambda(lambda item: operation()).invoke("local")
        self.assertEqual(result, "one application result")
        operation.assert_called_once()
        self.factory.assert_not_called()
        self.assertEqual(capture.references, [])
        self.assertEqual(get_tracing_context()["enabled"], before)

    def test_configuration_alone_never_becomes_an_available_trace(self):
        self.enable()
        with observability.capture_traces() as capture:
            self.assertEqual(capture.snapshot(), [])
        self.verify()
        self.assertEqual(capture.references, [])
        self.assertEqual(capture.snapshot(), [])
        self.assertEqual(self.client.created, [])
        self.assertFalse(any(read[0] == "run" for read in self.client.reads))

    def test_real_native_runnable_is_available_only_after_remote_confirmation(self):
        self.enable()
        capture = self.native_run()
        self.assertEqual(capture.snapshot(), [])
        references = capture.references
        self.assertEqual(len(references), 1)
        self.assertEqual(references[0]["project"], PROJECT)
        identifier = references[0]["run_id"]
        UUID(identifier)
        self.assertTrue(self.client.created, "A native LangChain callback must reach the fake SDK transport")
        self.assertIn(identifier, {str(run["id"]) for run in self.client.created})
        self.assertEqual(self.client.reads, [], "Remote verification must not block the workflow thread")
        self.verify()
        confirmed = capture.snapshot()
        self.assertEqual(len(confirmed), 1)
        self.assertEqual(confirmed[0]["run_id"], identifier)
        self.assertEqual(confirmed[0]["project"], PROJECT)
        self.assertIn(identifier, confirmed[0]["url"])
        self.assertTrue(confirmed[0]["url"].startswith("https://smith.langchain.com/"))
        self.assertLessEqual(set(confirmed[0]), {"run_id", "project", "url"})
        self.assertNotIn(PRIVATE_MARKER, json.dumps(confirmed))
        references[0]["project"] = "mutated-only-in-test"
        confirmed[0]["run_id"] = "mutated-only-in-test"
        self.assertEqual(capture.references[0]["project"], PROJECT)
        self.assertEqual(capture.snapshot()[0]["run_id"], identifier)

    def test_unavailable_sdk_does_not_repeat_or_prevent_the_workflow(self):
        self.enable()
        self.factory.side_effect = ImportError(PRIVATE_MARKER)
        operation = Mock(return_value="application result")
        with observability.capture_traces() as capture:
            result = operation()
        self.assertEqual(result, "application result")
        operation.assert_called_once()
        self.assertEqual(capture.snapshot(), [])

    def test_authentication_and_network_failures_remain_unconfirmed(self):
        self.enable()
        for failure in (PermissionError(PRIVATE_MARKER), ConnectionError(PRIVATE_MARKER)):
            with self.subTest(error_type=type(failure).__name__):
                capture = self.native_run()
                self.client.failure = failure
                self.verify()
                self.assertEqual(capture.snapshot(), [])
                self.assertNotIn(PRIVATE_MARKER, json.dumps(capture.references))
                self.client.failure = None

    def test_sdk_upload_failure_does_not_leak_credential_through_logs(self):
        self.enable()
        self.client.create_run = Mock(side_effect=PermissionError(PRIVATE_MARKER))
        capture = self.native_run()
        self.client.failure = PermissionError(PRIVATE_MARKER)
        self.verify()
        self.assertEqual(capture.snapshot(), [])
        self.assertNotIn(PRIVATE_MARKER, self.log.getvalue())

    def test_application_exception_is_not_retried_or_suppressed(self):
        self.enable()
        failure = ValueError("application failure fixture")
        operation = Mock(side_effect=failure)
        with self.assertRaises(ValueError) as caught:
            with observability.capture_traces() as capture:
                operation()
        self.assertIs(caught.exception, failure)
        operation.assert_called_once()
        self.verify()
        self.assertEqual(capture.snapshot(), [])

    def test_remote_identity_must_match_actual_local_run(self):
        self.enable()
        capture = self.native_run()
        self.client.remote_id = uuid4()
        self.verify()
        self.assertEqual(capture.snapshot(), [])

    def test_untrusted_remote_urls_cannot_become_ui_links(self):
        self.enable()
        for url in ("javascript:alert(1)", "http://smith.langchain.com/r/fixture", "https://outside.invalid/r/fixture",
                    "https://user:password@smith.langchain.com/r/fixture", "https://smith.langchain.com/r/fixture?api_key=" + PRIVATE_MARKER):
            with self.subTest(url_kind=url.split(":", 1)[0]):
                capture = self.native_run()
                self.client.confirmed_url = url
                self.verify()
                for reference in capture.snapshot():
                    self.assertNotIn("url", reference)
                    self.assertNotIn(PRIVATE_MARKER, json.dumps(reference))


class ObservabilityUIChecks(OfflineTracingBase):
    def setUp(self):
        super().setUp()
        self.operations = [self.stack.enter_context(patch.object(FrontendAdapter, method,
                           side_effect=AssertionError("Live operations forbidden in read-only UI checks")))
                           for method in ("run_live", "resume_live", "build_evaluation_index", "set_session_api_key")]
        self.stack.enter_context(patch.object(FrontendAdapter, "runtime_status", return_value=RuntimeStatus(False, False, False, False)))
        self.operations.append(self.stack.enter_context(patch("frontend.answers.generate_final_answer", side_effect=AssertionError("No answer generation"))))
        self.operations.append(self.stack.enter_context(patch("frontend.conversation.resolve_followup", side_effect=AssertionError("No context model"))))
        self.operations.append(self.stack.enter_context(patch("frontend.observability._create_client", side_effect=AssertionError("No SDK client on read-only navigation"))))
        self.run_id = str(uuid4())
        self.reference = {"run_id": self.run_id, "project": PROJECT,
                          "url": f"https://smith.langchain.com/o/offline/projects/p/{uuid4()}/r/{self.run_id}"}

    def tearDown(self):
        for operation in self.operations:
            operation.assert_not_called()
        super().tearDown()

    def app(self, page="architecture"):
        app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=30)
        app.query_params["page"] = page
        app.run()
        self.clean(app)
        return app

    def clean(self, app):
        self.assertFalse(app.exception, [error.message for error in app.exception])
        self.assertNotIn(PRIVATE_MARKER, self.markup(app))
        for state in app.json:
            self.assertNotIn(PRIVATE_MARKER, state.value)

    def markup(self, app):
        return " ".join(item.value for item in app.markdown) + " " + " ".join(item.value for item in app.caption)

    def seed(self, app, *, confirmed=True, turn_id="offline-current-turn", capture_turn=None):
        app.session_state.current_run = {
            "mode": "LIVE MODE", "turn_id": turn_id, "query": "Public offline question",
            "before_run": {"retrieved_results": []},
        }
        app.session_state.langsmith_trace_captures = {
            "turn_id": capture_turn or turn_id,
            "workflow": SimpleNamespace(snapshot=lambda: deepcopy([self.reference] if confirmed else [])),
        }
        app.run()
        self.clean(app)

    def test_architecture_configuration_is_truthful_without_a_recorded_trace(self):
        os.environ["LANGSMITH_API_KEY"] = PRIVATE_MARKER
        app = self.app()
        self.assertIn("Tracing: Off", self.markup(app))
        self.assertIn("Optional observability", self.markup(app))
        self.assertNotIn("Last run traced", self.markup(app))
        os.environ["LANGSMITH_TRACING"] = "true"
        app.run()
        self.clean(app)
        self.assertIn("Tracing: On", self.markup(app))
        self.assertIn("Project: " + PROJECT, self.markup(app))
        self.assertNotIn("Last run traced", self.markup(app))
        self.assertFalse(app.get("link_button"))

    def test_local_capture_only_is_off_in_advanced_state(self):
        os.environ["LANGSMITH_TRACING"], os.environ["LANGSMITH_API_KEY"] = "true", PRIVATE_MARKER
        app = self.app("action")
        self.seed(app, confirmed=False)
        self.assertIn("LangSmith Trace", self.markup(app))
        self.assertNotIn("✓ Available", self.markup(app))
        advanced = next(expander for expander in app.expander if expander.label == "Advanced Technical State")
        self.assertFalse(advanced.proto.expanded)
        self.assertFalse(any("langsmith_trace" in item.value for item in app.json))

    def test_confirmed_trace_persists_on_navigation_but_not_new_chat(self):
        os.environ["LANGSMITH_TRACING"], os.environ["LANGSMITH_API_KEY"] = "true", PRIVATE_MARKER
        app = self.app("action")
        self.seed(app)
        self.assertIn("✓ Available", self.markup(app))
        self.assertTrue(any(self.run_id in item.value for item in app.json))
        self.assertNotIn("langsmith_trace", app.session_state.current_run)
        self.assertNotIn(PRIVATE_MARKER, repr(app.session_state.current_run))
        app.button(key="session_nav_architecture").click().run()
        self.clean(app)
        self.assertIn("Last run traced", self.markup(app))
        self.assertEqual([element.proto.url for element in app.get("link_button")], [self.reference["url"]])
        app.button(key="session_nav_action").click().run()
        self.clean(app)
        self.assertIn("✓ Available", self.markup(app))
        app.button(key="new_chat").click().run()
        self.assertNotIn("langsmith_trace_captures", app.session_state)
        app.button(key="session_nav_architecture").click().run()
        self.clean(app)
        self.assertNotIn("Last run traced", self.markup(app))
        self.assertFalse(app.get("link_button"))

    def test_old_turn_and_saved_runs_never_claim_the_current_trace(self):
        app = self.app("action")
        self.seed(app, capture_turn="earlier-turn")
        self.assertNotIn("✓ Available", self.markup(app))
        self.assertFalse(any(self.run_id in item.value for item in app.json))
        app.button(key="session_nav_architecture").click().run()
        self.assertNotIn("Last run traced", self.markup(app))
        self.seed(app)
        app.session_state.current_run["mode"] = "VERIFIED DEMO MODE"
        app.session_state.current_run["verified"] = True
        app.run()
        self.clean(app)
        self.assertNotIn("Last run traced", self.markup(app))

    def test_capture_read_failure_is_private_and_does_not_break_ui(self):
        app = self.app("action")
        self.seed(app, confirmed=False)
        app.session_state.langsmith_trace_captures["workflow"] = SimpleNamespace(snapshot=Mock(side_effect=RuntimeError(PRIVATE_MARKER)))
        app.run()
        self.clean(app)
        self.assertNotIn("✓ Available", self.markup(app))
        app.button(key="session_nav_architecture").click().run()
        self.clean(app)
        self.assertNotIn("Last run traced", self.markup(app))


if __name__ == "__main__":
    unittest.main()
