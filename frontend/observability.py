"""Optional native tracing with asynchronous, confirmed UI references.

This module adds no workflow nodes. Disabled tracing overrides legacy tracing
flags in the current execution context without changing the environment.
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from hashlib import sha256
import logging
import os
import re
import threading
import time
from typing import Any
from urllib.parse import parse_qsl, urlsplit
from uuid import UUID

from langchain_core.tracers.context import collect_runs
from langsmith import Client, tracing_context
from urllib3.util.retry import Retry


_DEFAULT_PROJECT = "ragops-multi-agent"
_DEFAULT_ENDPOINT = "https://api.smith.langchain.com"
_SECRET_KEY = re.compile(r"(?:api[_-]?key|authorization|password|secret|credential|private[_-]?key|access[_-]?token|refresh[_-]?token|(?:^|[_-])token$)", re.I)
_ENV_SECRET_KEY = re.compile(r"(?:api[_-]?key|token|password|secret|credential|private[_-]?key)", re.I)
_SECRET_VALUE = re.compile(r"\b(?:sk-(?:proj-|svcacct-)?[A-Za-z0-9_-]{12,}|lsv2_[A-Za-z0-9_-]{8,})\b")
_CLIENT_LOCK = threading.Lock()
_CLIENT: Any = None
_CLIENT_SIGNATURE = ""


def _secrets() -> tuple[str, ...]:
    return tuple(sorted({value for key, value in os.environ.items()
                         if _ENV_SECRET_KEY.search(key) and value
                         and (len(value) >= 6 or re.search(r"api[_-]?key", key, re.I))},
                        key=len, reverse=True))

def _sanitize(value: Any, *, secrets: tuple[str, ...] | None = None, depth: int = 0) -> Any:
    """Remove credential fields and known credential values from SDK payloads."""
    secrets = _secrets() if secrets is None else secrets
    if depth > 20:
        return "[nested content omitted]"
    if isinstance(value, str):
        for secret in secrets:
            value = value.replace(secret, "[redacted]")
        return _SECRET_VALUE.sub("[redacted]", value)
    if isinstance(value, dict):
        return {str(_sanitize(str(key), secrets=secrets)): (
                    "[redacted]" if _SECRET_KEY.search(str(key)) else
                    _sanitize(item, secrets=secrets, depth=depth + 1)) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_sanitize(item, secrets=secrets, depth=depth + 1) for item in value]
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return _sanitize(str(value), secrets=secrets, depth=depth + 1)


class _TraceLogFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if record.name.startswith(("langsmith", "langchain_core.tracers", "langchain_core.callbacks")):
            try:
                record.msg = _sanitize(record.getMessage())
            except Exception:
                record.msg = "Optional trace operation could not be completed."
            record.args = ()
            # SDK tracebacks can embed request headers or exception arguments.
            record.exc_info = record.exc_text = record.stack_info = None
        return True


_LOG_FILTER = _TraceLogFilter()


def _install_log_filter() -> None:
    names = {"langsmith", "langsmith.client", "langsmith.run_helpers", "langsmith._internal._background_thread",
             "langchain_core.tracers.langchain", "langchain_core.callbacks.manager"}
    names.update(name for name in logging.Logger.manager.loggerDict
                 if name.startswith(("langsmith", "langchain_core.tracers", "langchain_core.callbacks")))
    for name in names:
        logger = logging.getLogger(name)
        if _LOG_FILTER not in logger.filters:
            logger.addFilter(_LOG_FILTER)
    # Handler filters also cover SDK child loggers initialized later.
    for logger in [logging.getLogger(), *(logging.getLogger(name) for name in names)]:
        for handler in logger.handlers:
            if _LOG_FILTER not in handler.filters:
                handler.addFilter(_LOG_FILTER)


def _endpoint() -> str:
    value = os.environ.get("LANGSMITH_ENDPOINT", "").strip() or _DEFAULT_ENDPOINT
    parts = urlsplit(value)
    if (parts.scheme != "https" or not parts.hostname or parts.username or parts.password
            or parts.query or parts.fragment or _sanitize(value) != value):
        raise ValueError("The optional tracing endpoint is not a safe HTTPS address.")
    return value.rstrip("/")


@dataclass(frozen=True)
class TracingSettings:
    enabled: bool
    project: str


def tracing_settings() -> TracingSettings:
    """Return configuration availability, never credentials or connection claims."""
    project = os.environ.get("LANGSMITH_PROJECT", "").strip() or _DEFAULT_PROJECT
    safe_project = _sanitize(project)
    enabled = (os.environ.get("LANGSMITH_TRACING", "").strip().lower() in {"true", "1", "yes", "on"}
               and bool(os.environ.get("LANGSMITH_API_KEY", "").strip()))
    if safe_project != project or len(project) > 200 or any(ord(char) < 32 for char in project):
        return TracingSettings(False, _DEFAULT_PROJECT)
    try:
        _endpoint()
    except Exception:
        enabled = False
    return TracingSettings(enabled, project)


def _create_client() -> Any:
    """Reuse the native batching client; references remain capture/session local."""
    global _CLIENT, _CLIENT_SIGNATURE
    settings = tracing_settings()
    if not settings.enabled:
        return None
    endpoint, key = _endpoint(), os.environ["LANGSMITH_API_KEY"].strip()
    signature = sha256((endpoint + "\0" + key + "\0" + settings.project).encode()).hexdigest()
    with _CLIENT_LOCK:
        if _CLIENT is None or signature != _CLIENT_SIGNATURE:
            _CLIENT = Client(
                api_key=key, api_urls={endpoint: key}, auto_batch_tracing=True,
                timeout_ms=(500, 1500), retry_config=Retry(total=0), tracing_mode="langsmith",
                anonymizer=_sanitize, hide_inputs=_sanitize, hide_outputs=_sanitize, hide_metadata=_sanitize,
                omit_traced_runtime_info=True, tracing_error_callback=lambda _error: None,
            )
            _CLIENT_SIGNATURE = signature
        return _CLIENT


class TraceCapture:
    def __init__(self, settings: TracingSettings | None = None):
        self.settings = settings or tracing_settings()
        self._lock = threading.Lock()
        self._references: list[dict[str, str]] = []
        self._confirmed: dict[str, dict[str, str]] = {}

    @property
    def references(self) -> list[dict[str, str]]:
        """Local native IDs are not proof that a trace reached LangSmith."""
        with self._lock:
            return [dict(reference) for reference in self._references]

    def snapshot(self) -> list[dict[str, str]]:
        """Expose only references successfully read back from the trace service."""
        with self._lock:
            return [dict(self._confirmed[reference["run_id"]]) for reference in self._references
                    if reference["run_id"] in self._confirmed]

    def _record(self, runs: list[Any]) -> list[Any]:
        roots = []
        for run in runs:
            try:
                run_id = str(UUID(str(run.id)))
                if getattr(run, "parent_run_id", None) is not None:
                    continue
                with self._lock:
                    if any(reference["run_id"] == run_id for reference in self._references):
                        continue
                    self._references.append({"run_id": run_id, "project": self.settings.project})
                roots.append(run)
                if len(roots) == 32:
                    break
            except Exception:
                continue
        return roots


def _safe_url(value: Any) -> str | None:
    if not isinstance(value, str) or _sanitize(value) != value:
        return None
    try:
        parts, endpoint = urlsplit(value), urlsplit(_endpoint())
        host, api_host = parts.hostname or "", endpoint.hostname or ""
        trusted = (host == "smith.langchain.com" or host.endswith(".smith.langchain.com")) if (
            api_host == "smith.langchain.com" or api_host.endswith(".smith.langchain.com")) else host == api_host
        if (parts.scheme == "https" and trusted and not parts.username and not parts.password
                and not parts.fragment and all(key == "poll" and item in {"true", "false"}
                                               for key, item in parse_qsl(parts.query, keep_blank_values=True))):
            return value
    except Exception:
        pass
    return None


def _verify_capture(capture: TraceCapture, client: Any, runs: list[Any]) -> None:
    """Bounded remote verification runs only on the daemon worker."""
    deadline = time.monotonic() + 12
    try:
        client.flush(timeout=1)
    except Exception:
        pass
    project = None
    remaining = list(runs)
    for delay in (0, .5, 1.5):
        if not remaining or time.monotonic() >= deadline:
            return
        if delay:
            time.sleep(delay)
        try:
            project = project or client.read_project(project_name=capture.settings.project)
            project_id = str(UUID(str(project.id)))
        except Exception:
            continue
        for local in list(remaining):
            if time.monotonic() >= deadline:
                return
            try:
                run_id = str(UUID(str(local.id)))
                remote = client.read_run(run_id, project_id=project_id, start_time=local.start_time)
                if str(remote.id) != run_id:
                    continue
                remote_project = getattr(remote, "session_id", None)
                if remote_project is not None and str(remote_project) != project_id:
                    continue
                reference = {"run_id": run_id, "project": capture.settings.project}
                url = None
                try:
                    url = _safe_url(getattr(remote, "url", None))
                except Exception:
                    pass
                if not url:
                    try:
                        url = _safe_url(client.get_run_url(run=remote, project_id=project_id))
                    except Exception:
                        pass
                if url:
                    reference["url"] = url
                with capture._lock:
                    capture._confirmed[run_id] = reference
                remaining.remove(local)
            except Exception:
                continue


def _exit_context(context: Any) -> None:
    if context is not None:
        try:
            context.__exit__(None, None, None)
        except Exception:
            pass


@contextmanager
def capture_traces(*, verify: bool = True):
    """Observe native runs once; trace setup/cleanup never retries the operation."""
    capture = TraceCapture(TracingSettings(False, _DEFAULT_PROJECT))
    disabled = active = collector_context = collector = client = None
    fallback_token = None
    try:
        capture.settings = tracing_settings()
        _install_log_filter()
        disabled = tracing_context(enabled=False, parent=False, replicas=[])
        disabled.__enter__()
        if capture.settings.enabled:
            client = _create_client()
            if client is not None:
                active = tracing_context(enabled=True, client=client, project_name=capture.settings.project,
                                         parent=False, replicas=[])
                active.__enter__()
                collector_context = collect_runs()
                collector = collector_context.__enter__()
    except Exception:
        _exit_context(collector_context)
        _exit_context(active)
        active = collector_context = collector = client = None
        # Preserve fail-open application execution even if SDK context setup
        # failed, while preventing fallback to a legacy environment flag.
        try:
            from langsmith._internal._context import _TRACING_ENABLED
            fallback_token = _TRACING_ENABLED.set(False)
        except Exception:
            pass
    try:
        yield capture
    finally:
        _exit_context(collector_context)
        _exit_context(active)
        if fallback_token is not None:
            try:
                from langsmith._internal._context import _TRACING_ENABLED
                _TRACING_ENABLED.reset(fallback_token)
            except Exception:
                pass
        _exit_context(disabled)
        if collector is not None and client is not None:
            try:
                roots = capture._record(collector.traced_runs)
                if roots and verify:
                    threading.Thread(target=_verify_capture, args=(capture, client, roots),
                                     name="ragops-trace-verification", daemon=True).start()
            except Exception:
                pass
