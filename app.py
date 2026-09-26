from __future__ import annotations

from copy import deepcopy
from html import escape
from unicodedata import bidirectional
from urllib.parse import urlencode
from uuid import uuid4
import plotly.graph_objects as go
import streamlit as st
from dotenv import load_dotenv

from frontend.adapter import FrontendAdapter, INDEX_DIR
from frontend.answers import generate_final_answer
from frontend.conversation import resolve_followup
from frontend.action_presentation import (
    compact_trace, evidence_warning, feedback_state, inspector_state,
    structural_execution_available, validation_summary,
)
from frontend.action_styles import ACTION_CSS
from frontend.animations import control_loop_html
from frontend.architecture import ARCHITECTURE_CSS
from frontend.components import (
    approval_card_html, architecture_html, failure_cards_html, kpi_grid_html,
    metrics_compare_html, nav_html, team_html, trace_html, verdict_html,
)
from frontend.icons import icon, logo_svg
from frontend.dashboard import (
    accepted_result, action_label, decision_label, evaluation_dashboard, live_run_summary,
)
from frontend.dashboard_styles import DASHBOARD_CSS
from frontend.evidence import recorded_cases, recorded_run
from frontend.overview import OVERVIEW_INTERACTIONS
from frontend.observability import capture_traces, tracing_settings
from frontend.presentation import approval_view, normalized_trace, safe_state
from frontend.session import navigation_bridge
from frontend.styles import CSS
from frontend.team import TEAM_CSS

load_dotenv()
st.set_page_config(page_title="RAGOps Agent", page_icon="◈", layout="wide", initial_sidebar_state="collapsed")
st.html(CSS + ARCHITECTURE_CSS + TEAM_CSS)


@st.cache_resource
def get_adapter() -> FrontendAdapter:
    # The adapter constructor reads JSON. Live backend imports are lazy.
    return FrontendAdapter()


adapter = get_adapter()
SAVED, LIVE = "VERIFIED DEMO MODE", "LIVE MODE"
CYAN, GREEN, PURPLE, AMBER, RED = "#00d8f4", "#25e6ae", "#aa8bfa", "#ffc34a", "#ff6c82"


def html(value: str) -> None:
    # Keep nested SVG/HTML in a single markdown block. Blank lines otherwise
    # terminate Markdown's raw HTML block and can detach SVG nodes from the hero.
    st.markdown(" ".join(line.strip() for line in value.splitlines()), unsafe_allow_html=True)


def text(value) -> str:
    return escape(str(value if value is not None else "—"))


def observed_call(operation, *args, phase: str, turn_id: str | None = None):
    """Use native tracing at the UI boundary without changing backend inputs.

    Capture handles stay separate from the backend state. The background SDK
    worker only updates its own handle; Streamlit reads it on the next render.
    """
    with capture_traces(verify=phase != "conversation") as capture:
        if turn_id and phase != "conversation":
            captures = st.session_state.get("langsmith_trace_captures") or {}
            if captures.get("turn_id") != turn_id:
                captures = {"turn_id": turn_id}
            captures[phase] = capture
            st.session_state.langsmith_trace_captures = captures
        return operation(*args)


def current_langsmith_trace(run: dict | None) -> dict:
    """A local workflow trace or a configured key is not a hosted trace."""
    if not run or run.get("mode") != LIVE or run.get("verified") or not run.get("turn_id"):
        return {}
    captures = st.session_state.get("langsmith_trace_captures") or {}
    if captures.get("turn_id") != run["turn_id"]:
        return {}
    for phase in ("workflow", "answer"):
        capture = captures.get(phase)
        if capture is not None:
            try:
                references = capture.snapshot()
            except Exception:
                # Optional observability must never prevent the UI rendering.
                continue
            if references:
                return references[-1]
    return {}


def page_nav(active: str) -> None:
    if active == "architecture":
        html(nav_html(active, show_status=False))
        return
    status = adapter.runtime_status()
    if active == "dashboard":
        label, note, kind = "Official Evaluation", "Saved evaluation artifacts", "evidence"
    elif active != "action" or st.session_state.get("runtime_mode", SAVED) == SAVED:
        label, note, kind = "Saved Evidence Mode", "Repository evaluation artifacts", "evidence"
    elif status.live_configured:
        answer = (st.session_state.get("current_run") or {}).get("answer_result") or {}
        note = "Answer generated" if answer.get("model") and answer.get("text") else "Index and credentials detected"
        label, kind = "Live Runtime Configured", "neutral"
    else:
        label, note, kind = "Live Runtime Unavailable", "Saved evidence is available", "neutral"
    html(nav_html(active, label, note, kind))


def page_heading(kicker: str, title: str, copy: str) -> None:
    html(f'<div class="page-heading"><div class="section-kicker">{text(kicker)}</div>'
         f'<h1 class="page-title">{title}</h1><p class="page-subtitle">{text(copy)}</p></div>')


def panel_heading(title: str, glyph: str = "file", note: str = "") -> None:
    html(f'<div class="panel-heading">{icon(glyph)}<span>{text(title)}</span><small>{text(note)}</small></div>')


def footer() -> None:
    html(f'<div class="page-footer"><span>{logo_svg(24)} RAGOps Agent</span>'
         '<span>OBSERVE. DIAGNOSE. OPTIMIZE. VALIDATE.</span><span>Four agents. Measured impact.</span></div>')


def dataset_counts() -> tuple[int, int]:
    return (len({(r["platform"], r["service"]) for r in adapter.dataset}),
            len({r["platform"] for r in adapter.dataset}))


def render_overview() -> None:
    page_nav("overview")
    d = evaluation_dashboard(adapter)
    services, _ = dataset_counts()
    overall, count, k = d["summary"]["overall"], len(d["failures"]), d["summary"]["k"]
    stats = [
        ("database", services, 0, "", "Indexed Services"),
        ("file", d["summary"]["total_queries"], 0, "", "Evaluation Queries"),
        ("chart", d["outcomes"].get("IMPROVED", 0), 0, f"/{count}", "Failed Cases Improved"),
        ("check", overall["recall_at_k"] * 100, 1, "%", f"Baseline Recall@{k}"),
    ]
    stat_html = ''
    for symbol, value, decimals, suffix, label in stats:
        final = f"{value:.{decimals}f}{suffix}"
        stat_html += (f'<div class="hero-stat">{icon(symbol,28)}<div><b aria-label="{text(final)} {text(label)}">'
                      f'<span class="kpi-count" aria-hidden="true" data-count-to="{value}" data-count-decimals="{decimals}" '
                      f'data-count-suffix="{text(suffix)}">{text(final)}</span></b><span>{text(label)}</span></div></div>')
    case_links = verified_failure_links(d)
    high_impact = approval_view(st.session_state.get("current_run"))["requires_decision"]
    html(f'''<div class="hero-grid"><div class="hero-left">
      <div class="eyebrow">AGENTIC AI · RETRIEVAL OPERATIONS</div>
      <h1 class="hero-title">RAG<span class="accent">Ops</span> Agent</h1>
      <div class="hero-subtitle">Multi-Agent Retrieval QA Optimizer</div>
      <div class="hero-tagline">Observe. Diagnose. Optimize. Validate.</div>
      <p class="hero-copy">A domain-agnostic operations layer for Retrieval-Augmented Generation systems.
      Diagnose retrieval failures, propose targeted optimizations, control structural changes,
      and validate measurable improvement across knowledge domains.</p>
      <div class="hero-actions"><a class="hero-btn primary" href="?page=action" target="_self">{icon('play')} Run RAGOps {icon('arrow')}</a>
      <a class="hero-btn secondary" href="?page=architecture" target="_self">{icon('network')} Explore Architecture</a></div>
      <div class="hero-evidence-note">{icon('shield',14)} Four functional agents · conceptual workflow illustration</div>
      </div><div class="hero-visual">{control_loop_html(high_impact=high_impact)}</div></div>
      <div id="evaluation-snapshot" class="evaluation-snapshot" tabindex="-1">
      <div class="section-kicker">EVALUATION SNAPSHOT</div><div class="hero-statbar">{stat_html}</div>
      <p class="corpus-note">Demo corpus: Absher · Balady · Najiz · Sakani</p></div>
      <a class="overview-scroll-cue" href="#evaluation-snapshot" target="_self">Explore more <span aria-hidden="true">↓</span></a>''')
    with st.container(border=True, key="overview_failures"):
        html('<div class="section-kicker">COMMON RETRIEVAL FAILURES</div>'
             '<h2 class="section-title">Three retrieval failures. Three targeted optimizations.</h2>')
        html(failure_cards_html(case_links))
    footer()
    # This trusted, local script only enhances presentation; it has no network
    # requests or backend callbacks. Final KPI values are already server-rendered.
    st.html(OVERVIEW_INTERACTIONS, unsafe_allow_javascript=True)


def verified_failure_links(dashboard: dict) -> dict[str, str]:
    links = {}
    for title, issue, action in [
        ("Top-K Retrieval", "Top-K", "change_top_k"),
        ("Query Mismatch", "Query Mismatch", "rewrite_query"),
        ("Chunking Quality", "Chunking Quality", "rechunk_and_reindex"),
    ]:
        for case in recorded_cases(adapter):
            if case["issue"] != issue:
                continue
            try:
                run = recorded_run(adapter, case["id"])
            except (LookupError, StopIteration, ValueError):
                continue
            proposal = run.get("optimization_proposal") or {}
            if not run.get("verified") or proposal.get("action") != action:
                continue
            backed = bool((run.get("before_run") or {}).get("retrieved_results") and run.get("validation_result"))
            if backed:
                links[title] = "?" + urlencode({"page": "action", "case": case["id"]})
                break
    return links


def clear_run() -> None:
    for key in ("current_run", "live_workflow", "live_thread_id", "selected_case_id", "decision_error", "active_turn_id", "turn_error", "latest_turn_status", "langsmith_trace_captures"):
        st.session_state.pop(key, None)


def action_cases(runtime: str | None = None) -> list[dict]:
    recorded = recorded_cases(adapter)
    if (runtime or st.session_state.get("runtime_mode")) != LIVE:
        return recorded
    known = {case["id"]: case for case in recorded}
    return [known.get(item["id"]) or {
        **item, "label": f'{item["platform"].title()} · {item["query_type"].replace("_", " ")}',
        "issue": None,
    } for item in adapter.dataset]


def sync_case_url(case_id: str = "") -> None:
    if case_id:
        mode = "live" if st.session_state.get("runtime_mode") == LIVE else "saved"
        st.query_params["case"], st.query_params["mode"] = case_id, mode
    else:
        st.query_params.pop("case", None)
        st.query_params.pop("mode", None)
        mode = ""
    st.session_state.loaded_link_case = (case_id, mode)


def change_mode() -> None:
    st.session_state.runtime_mode = SAVED if st.session_state.mode_choice == "View Saved Runs" else LIVE
    query_changed()


def choose_case(case_id: str, update_url: bool = True) -> None:
    case = next((c for c in action_cases() if c["id"] == case_id), None)
    st.session_state.query_text = case["query"] if case else ""
    st.session_state.selected_case_id = case_id if case else None
    st.session_state.case_picker = case_id if case else ""
    if update_url:
        sync_case_url(case_id if case else "")


def query_changed() -> None:
    item = adapter.match_dataset_query(st.session_state.get("query_text", ""))
    case_id = item["id"] if item and any(c["id"] == item["id"] for c in action_cases()) else ""
    st.session_state.case_picker = case_id
    st.session_state.selected_case_id = case_id or None
    sync_case_url(case_id)


def reset_query() -> None:
    clear_run()
    st.session_state.chat_history = []
    st.session_state.pop("saved_run", None)
    st.session_state.runtime_mode = LIVE
    st.session_state.mode_choice = "Live Run"
    st.session_state.query_text = ""
    st.session_state.case_picker = ""
    sync_case_url()


def custom_query() -> None:
    # Selecting/editing a draft does not discard the active result or review.
    st.session_state.query_text = ""
    st.session_state.case_picker = ""
    st.session_state.selected_case_id = None
    sync_case_url()


def select_case() -> None:
    choose_case(st.session_state.case_picker)


def render_runtime_controls(status) -> str:
    st.session_state.setdefault("runtime_mode", LIVE)
    expected = "Live Run" if st.session_state.runtime_mode == LIVE else "View Saved Runs"
    if st.session_state.get("mode_choice") not in ("Live Run", "View Saved Runs"):
        st.session_state.mode_choice = expected
    mode_col, clear_col = st.columns([4, 1], gap="medium")
    with mode_col:
        st.radio("Execution source", ["Live Run", "View Saved Runs"], key="mode_choice",
                 horizontal=True, on_change=change_mode, label_visibility="collapsed")
    with clear_col:
        st.button("New Chat", key="new_chat", on_click=reset_query, width="stretch")
    return st.session_state.runtime_mode


def normalize_live_state(state: dict, query: str) -> dict:
    run = {**state, "mode": LIVE, "query": state.get("query", query), "verified": False}
    item = adapter.match_dataset_query(run["query"])
    if item:
        run.update({key: item[key] for key in ("platform", "service", "query_type") if key in item})
        run["case_id"] = item["id"]
    # An interrupt is itself backend evidence of a pending review. Preserve its
    # proposal fields without manufacturing approval results or run outcomes.
    if not run.get("optimization_proposal"):
        interrupts = state.get("__interrupt__") or []
        if not isinstance(interrupts, (list, tuple)):
            interrupts = [interrupts]
        for entry in interrupts:
            value = entry.get("value", entry) if isinstance(entry, dict) else getattr(entry, "value", None)
            if isinstance(value, dict) and value.get("type") == "human_approval_required":
                run["optimization_proposal"] = {k: value[k] for k in ("issue_type", "action", "reason", "parameters") if k in value}
                break
    return run


def labelled_query(run: dict | None, query: str = "") -> bool:
    item = adapter.match_dataset_query((run or {}).get("query") or query)
    return bool(item and item.get("platform") and item.get("service"))


def runtime_unavailable_message(status) -> str:
    message = "Live Runtime Unavailable · " + status.reason
    if not status.index_ready:
        missing = [f"vector_store/evaluation_index/{name}" for name in ("index.faiss", "index.pkl") if not (INDEX_DIR / name).is_file()]
        if missing:
            message += " Missing files: " + ", ".join(missing) + "."
    return message


def complete_live_answer() -> None:
    """Generate once for this completed run; rerenders only display the result."""
    run = st.session_state.get("current_run")
    if not run or run.get("mode") != LIVE or run.get("answer_result"):
        return
    run.pop("answer_error", None)
    try:
        with st.spinner("Preparing an answer from the accepted evidence…"):
            result = observed_call(generate_final_answer, run, phase="answer", turn_id=run.get("turn_id"))
        if result is not None:
            run["answer_result"] = result
            publish_answer(run)
            st.session_state.latest_turn_status = "complete"
    except Exception:
        # Keep the successful retrieval/validation available. Provider exception
        # strings can contain request details and must not reach the UI.
        run["answer_error"] = True


def publish_answer(run: dict) -> None:
    """Keep each turn's accepted answer/sources independently of the latest run."""
    answer = run.get("answer_result")
    turn_id = run.get("turn_id")
    if not answer or not turn_id:
        return
    message = {
        "role": "assistant", "turn_id": turn_id, "content": answer["text"],
        "sources": deepcopy(answer.get("sources") or []), "status": answer.get("status"),
        "evidence": answer.get("evidence"), "labelled": labelled_query(run),
    }
    history = st.session_state.chat_history
    existing = next((i for i, value in enumerate(history) if value.get("turn_id") == turn_id and value["role"] == "assistant"), None)
    if existing is None:
        history.append(message)
    else:
        history[existing] = message


def ensure_conversation() -> None:
    st.session_state.setdefault("chat_history", [])
    run = st.session_state.get("current_run")
    if run and run.get("mode") == SAVED:
        st.session_state.setdefault("saved_run", run)
        st.session_state.pop("current_run", None)
    elif run and run.get("mode") == LIVE and not run.get("turn_id"):
        # Adopt an existing session's run once when upgrading the page.
        run["turn_id"] = uuid4().hex
        run.setdefault("user_query", run.get("query", ""))
        st.session_state.active_turn_id = run["turn_id"]
        st.session_state.chat_history.append({"role": "user", "turn_id": run["turn_id"],
            "content": run["user_query"], "retrieval_query": run.get("query", "")})
        publish_answer(run)


def render_chat_message(message: dict) -> None:
    turn_id = message["turn_id"]
    if message["role"] == "user":
        with st.container(key=f"action_chat_user_{turn_id}"), st.chat_message("user", avatar=":material/person:"):
            html('<div class="action-answer-label">You</div>')
            html(f'<div dir="auto">{text(message["content"])}</div>')
        return
    with st.container(key=f"action_chat_assistant_{turn_id}"), st.chat_message("assistant", avatar=":material/smart_toy:"):
        html('<div class="action-answer-label">RAGOps</div>')
        # Use Streamlit's safe Markdown renderer, with direction determined by
        # the first strong character so Arabic lists and English both read well.
        first_direction = next((bidirectional(c) for c in message["content"] if bidirectional(c) in {"L", "R", "AL"}), "L")
        direction = "rtl" if first_direction in {"R", "AL"} else "ltr"
        with st.container(key=f"live_answer_text_{turn_id}"):
            st.markdown(f'<style>.st-key-live_answer_text_{turn_id} [data-testid="stMarkdownContainer"] {{direction:{direction};text-align:start;overflow-wrap:anywhere}}</style>', unsafe_allow_html=True)
            st.markdown(message["content"], unsafe_allow_html=False)
        if message.get("evidence"):
            st.caption(("Validated optimized evidence" if message.get("labelled") else "Accepted retrieval evidence")
                       if message["evidence"] == "optimized" else "Baseline evidence")
        sources = message.get("sources") or []
        if sources:
            chips = []
            for source in sources:
                row = source["document"]
                label = " · ".join(str(v) for v in (str(row["platform"]).title() if row.get("platform") else None, row.get("service") or row.get("source")) if v)
                chips.append(f'<span class="action-source-chip" dir="auto">[{source["citation"]}] {text(label or "Retrieved passage")}</span>')
            html('<div class="action-source-chips" aria-label="Answer sources">' + ''.join(chips) + '</div>')
            for source in sources:
                excerpt = evidence_excerpt(source["document"])
                if excerpt:
                    html(f'<div class="action-source-summary"><p class="action-source-excerpt" dir="auto">[{source["citation"]}] {text(excerpt)}</p></div>')
            with st.expander("View full evidence", expanded=False):
                render_document_evidence({"retrieved_results": [source["document"] for source in sources]})


def render_live_answer(run: dict | None) -> None:
    for message in st.session_state.chat_history:
        render_chat_message(message)
    if run and run.get("answer_error"):
        st.warning("Retrieval completed, but the answer could not be generated. Retry using the same accepted evidence.")
        if st.button("Retry answer", key="retry_answer"):
            complete_live_answer()
            st.rerun()
    elif run and approval_view(run)["requires_decision"]:
        st.caption("Resolve Human Approval to receive this answer and continue the conversation.")
    if st.session_state.get("turn_error"):
        st.warning("This message could not be processed. The previous conversation is preserved.")
        if st.button("Retry message", key="retry_message"):
            latest = next(m for m in reversed(st.session_state.chat_history) if m["role"] == "user")
            execute_query(latest["content"], LIVE, retry_turn=latest["turn_id"])
            st.rerun()


def evidence_excerpt(row: dict, limit: int = 200) -> str:
    content = row.get("text") or row.get("content") or row.get("page_content") or ""
    compact = " ".join(str(content).split())
    return compact[:limit].rstrip() + "…" if len(compact) > limit else compact


def render_runtime_status(status, run: dict | None) -> None:
    observed = bool(run and run.get("mode") == LIVE and not run.get("verified") and run.get("before_run"))
    labels = [
        ("OpenAI ✓" if observed else "OpenAI · key configured" if status.api_key_present else "OpenAI · unavailable", observed),
        ("FAISS ✓" if observed else "FAISS · files present" if status.index_ready else "FAISS · missing", observed),
        ("Live runtime ✓" if observed else "Live runtime · configured" if status.live_configured else "Live runtime · unavailable", observed),
    ]
    html('<div class="action-runtime" aria-label="Runtime status">' + ''.join(
        f'<span class="action-runtime-badge {"available" if available else "neutral"}">{text(label)}</span>' for label, available in labels
    ) + f'<span class="action-runtime-note">{"Last live retrieval completed" if observed else "Configuration detected; connectivity is checked on submission" if status.live_configured else "See missing requirements below"}</span></div>')


def execute_query(query: str, runtime: str, retry_turn: str | None = None) -> None:
    if not query.strip():
        st.warning("Enter a query or choose a verified case.")
        return
    try:
        if runtime == LIVE:
            status = adapter.runtime_status()
            if not status.live_configured:
                st.info(runtime_unavailable_message(status))
                return
            if approval_view(st.session_state.get("current_run"))["requires_decision"]:
                st.info("Resolve Human Approval before sending another message, or start a New Chat.")
                return
            ensure_conversation()
            turn_id = retry_turn or uuid4().hex
            context = [deepcopy(message) for message in st.session_state.chat_history if message.get("turn_id") != turn_id]
            if not retry_turn:
                st.session_state.chat_history.append({"role":"user", "content":query, "turn_id":turn_id})
            user_message = next(message for message in st.session_state.chat_history if message["role"] == "user" and message["turn_id"] == turn_id)
            for key in ("current_run", "live_workflow", "live_thread_id", "decision_error", "turn_error"):
                st.session_state.pop(key, None)
            st.session_state.active_turn_id = turn_id
            st.session_state.latest_turn_status = "resolving"
            if retry_turn and user_message.get("retrieval_query"):
                # A failed workflow must retry the already resolved intent,
                # especially when the visible user message is only 'yes'.
                resolved = user_message["retrieval_query"]
                resolution = {"query":resolved, "clarification":None, "contextualized":resolved != query}
            elif adapter.match_dataset_query(query):
                resolution = {"query":query, "clarification":None, "contextualized":False}
            else:
                with st.spinner("Understanding your question…"):
                    resolution = observed_call(resolve_followup, query, context, phase="conversation")
            if resolution.get("clarification"):
                message = {"role":"assistant", "turn_id":turn_id,
                    "content":resolution["clarification"], "sources":[], "status":"clarification"}
                if resolution.get("pending_clarification"):
                    message["pending_clarification"] = deepcopy(resolution["pending_clarification"])
                st.session_state.chat_history.append(message)
                st.session_state.latest_turn_status = "clarification"
                return
            resolved_query = resolution["query"]
            user_message["retrieval_query"] = resolved_query
            st.session_state.latest_turn_status = "running"
            with st.spinner("Running the retrieval workflow…"):
                # A new adapter gives each submission an isolated graph and
                # checkpointer. Reusing the cached adapter can retain a prior
                # decision when its deterministic query thread ID is reused.
                payload = observed_call(FrontendAdapter().run_live, resolved_query, phase="workflow", turn_id=turn_id)
            st.session_state.pop("decision_error", None)
            st.session_state.live_workflow = payload["workflow"]
            st.session_state.live_thread_id = payload["thread_id"]
            st.session_state.current_run = normalize_live_state(payload["state"], resolved_query)
            st.session_state.current_run.update({"user_query":query, "turn_id":turn_id,
                                               "contextualized":resolution["contextualized"]})
            item = payload.get("dataset_item") or {}
            for key in ("platform", "service", "query_type"):
                if key in item and key not in st.session_state.current_run:
                    st.session_state.current_run[key] = item[key]
            complete_live_answer()
            if approval_view(st.session_state.current_run)["requires_decision"]:
                st.session_state.latest_turn_status = "pending"
        else:
            selected = st.session_state.get("selected_case_id")
            cases = recorded_cases(adapter)
            selected_case = next((c for c in cases if c["id"] == selected and c["query"] == query), None)
            matched = selected_case or next((c for c in cases if " ".join(c["query"].split()) == " ".join(query.split())), None)
            run = recorded_run(adapter, matched["id"]) if matched else None
            if run is None:
                st.info("No saved run matches this query. Select a verified case to inspect recorded evidence.")
            else:
                st.session_state.saved_run = run
    except Exception:
        # Backend exception strings may contain request details; do not expose them.
        if runtime == LIVE:
            st.session_state.turn_error = True
            st.session_state.latest_turn_status = "error"
        else:
            st.error("The saved run could not be loaded.")


def submit_message() -> None:
    query = st.session_state.get("query_text", "").strip()
    if query:
        execute_query(query, LIVE)
        st.session_state.query_text = ""


def suggested_cases() -> list[dict]:
    """Use original evaluation wording; never manufacture a demonstration case."""
    selected = []
    cases = recorded_cases(adapter)
    for issue in ("Query Mismatch", "Top-K"):
        case = next((case for case in cases if case["issue"] == issue), None)
        if case:
            selected.append(case)
    for service in ("driving_license_renewal", "health_certificate_issuance"):
        case = next((case for case in adapter.dataset if case["service"] == service and
                     case["id"] not in {item["id"] for item in selected}), None)
        if case:
            selected.append(case)
    return selected[:4]


def first_relevant_rank(run: dict | None) -> int | None:
    for item in (run or {}).get("retrieved_results", []) or []:
        if item.get("relevant") is True and item.get("rank"):
            return int(item["rank"])
    return None


def evidence_cards(run: dict | None) -> str:
    results = (run or {}).get("retrieved_results", []) or []
    if not results:
        return '<div class="empty-state">Retrieved evidence will appear here when a run provides document results.</div>'
    cards = []
    for row in results[:4]:
        relevant = row.get("relevant")
        tag = "Relevant" if relevant is True else "Not relevant" if relevant is False else None
        tone = "good" if relevant is True else "bad" if relevant is False else "neutral"
        title = str(row.get("service") or row.get("source") or "Retrieved document").replace("_", " ")
        relevance = f'<span class="evidence-relevance {tone}"><i></i>{tag}</span>' if tag else ""
        excerpt = f'<p class="action-source-excerpt" dir="auto">{text(evidence_excerpt(row))}</p>' if evidence_excerpt(row) else ""
        rank = f'<div class="evidence-rank">#{text(row["rank"])}</div>' if row.get("rank") is not None else ""
        platform = f'<div class="evidence-source" dir="auto">{text(row["platform"])}</div>' if row.get("platform") else ""
        cards.append(f'<div class="evidence-card">{rank}'
                     f'<div class="evidence-title" dir="auto">{text(title)}</div>'
                     f'{platform}'
                     f'{excerpt}{relevance}</div>')
    return '<div class="evidence-grid">' + ''.join(cards) + '</div>'


def render_document_evidence(run: dict | None) -> None:
    rows = (run or {}).get("retrieved_results", []) or []
    if not rows:
        st.caption("No per-document evidence is included in this run.")
        return
    for row in rows:
        title = f"#{row.get('rank', '—')} · {row.get('service') or row.get('source') or 'Document'}"
        with st.expander(title):
            metadata = [text(row[key]) for key in ("platform", "service", "source") if row.get(key)]
            if metadata:
                html('<div class="query-context" dir="auto">' + '<br>'.join(metadata) + '</div>')
            content = row.get("content") or row.get("page_content") or row.get("text")
            if content:
                html(f'<div class="evidence-content" dir="auto">{text(content)}</div>')
            st.json(safe_state(row), expanded=False)


def render_context(run: dict | None, query: str) -> None:
    data = run or adapter.match_dataset_query(query) or {}
    platform = data.get("platform") or data.get("expected_platform")
    results = (data.get("before_run") or {}).get("retrieved_results", []) or []
    html(f'<div class="query-context"><div class="context-platform">{icon("database",28)}<div>'
         f'<small>EVALUATION CORPUS</small><b>{text(str(platform).title() if platform else "Platform not reported")}</b>'
         '</div></div></div>')
    if query:
        html(f'<div class="query-context"><small>QUERY CONTEXT</small><p dir="auto">{text(query)}</p></div>')
    values = [
        ("Retrieved documents", len(results) if run and results else "—"),
        ("Labelled relevant", sum(r.get("relevant") is True for r in results) if results and any(r.get("relevant") is not None for r in results) else "—"),
        ("Query type", data.get("query_type") or "—"), ("Service", data.get("service") or data.get("expected_service") or "—"),
    ]
    html('<div class="context-grid">' + ''.join(f'<div class="context-item"><small>{text(label)}</small><b dir="auto">{text(value)}</b></div>' for label,value in values) + '</div>')


def render_validation(run: dict | None) -> None:
    if not run:
        return
    summary = validation_summary(run, labelled=labelled_query(run))
    with st.container(border=True, key="action_validation"):
        panel_heading("VALIDATION RESULTS — BEFORE → AFTER", "chart", "Latest turn")
        if summary["kind"] == "metrics":
            validation = run["validation_result"]
            html(metrics_compare_html(dict(validation["before"]), dict(validation["after"]),
                 first_relevant_rank(run.get("before_run")), first_relevant_rank(run.get("after_run")), ranks_known=True))
            html(verdict_html(validation["verdict"]))
        else:
            st.caption(summary["message"])
        feedback = feedback_state(run, labelled=labelled_query(run))
        if feedback:
            html(f'<div class="action-feedback {text(feedback["kind"])}">{icon("check" if feedback["kind"] == "positive" else "shield", 18)}<span>{text(feedback["text"])}</span></div>')


def render_decision(run: dict, runtime: str) -> None:
    gate = approval_view(run)
    if gate["requires_decision"]:
        if runtime != LIVE:
            st.caption("This record contains a pending review; it is not an active workflow that can accept a decision.")
            return
        html(approval_card_html(run.get("optimization_proposal") or {}))
        if st.session_state.get("decision_error"):
            st.error("The backend could not complete this decision. Start a new run before retrying. The last reported state is shown below.")
            return
        workflow = st.session_state.get("live_workflow")
        structural_unavailable = not structural_execution_available(workflow)
        if structural_unavailable:
            st.info("Structural execution is unavailable: the current backend executor has no candidate-index callback configured. Rejection can still retain the baseline.")
        reject, approve = st.columns([1, 1.3], gap="small")
        with reject:
            rejected = st.button("Reject / Keep Baseline", key="reject_optimization", width="stretch")
        with approve:
            approved = st.button("Approve Optimization", type="primary", key="approve_optimization", width="stretch", disabled=structural_unavailable)
        decision = "approve" if approved else "reject" if rejected else None
        if decision:
            try:
                workflow, thread = st.session_state.get("live_workflow"), st.session_state.get("live_thread_id")
                if workflow is None or not thread:
                    st.error("The live session is unavailable. Run this query again before making a decision.")
                    return
                state = observed_call(adapter.resume_live, workflow, thread, decision,
                                      phase="workflow", turn_id=run.get("turn_id"))
                st.session_state.current_run = normalize_live_state(state, run.get("query", ""))
                st.session_state.current_run.update({key:run[key] for key in ("user_query", "turn_id", "contextualized") if key in run})
                complete_live_answer()
                st.rerun()
            except Exception:
                st.session_state.decision_error = True
                st.rerun()
    elif gate["kind"] != "neutral":
        html(f'<div class="policy-banner {text(gate["kind"])}">{icon("shield")}<div><b>{text(gate["label"])}</b>'
             f'<span>{text((run.get("optimization_proposal") or {}).get("action"))}</span></div></div>')


def render_action() -> None:
    st.html(ACTION_CSS)
    status = adapter.runtime_status()
    st.session_state.setdefault("runtime_mode", LIVE)
    st.session_state.setdefault("query_text", "")
    ensure_conversation()
    requested_case = str(st.query_params.get("case", ""))
    requested_mode = str(st.query_params.get("mode", ""))
    link_token = (requested_case, requested_mode)
    link_unavailable = False
    if link_token != st.session_state.get("loaded_link_case"):
        st.session_state.loaded_link_case = link_token
        if requested_case:
            target_mode = LIVE if requested_mode == "live" else SAVED
            st.session_state.runtime_mode = target_mode
            st.session_state.mode_choice = "Live Run" if target_mode == LIVE else "View Saved Runs"
            choose_case(requested_case, update_url=False)
            if st.session_state.get("selected_case_id"):
                if target_mode == SAVED:
                    st.session_state.saved_run = recorded_run(adapter, requested_case)
            else:
                link_unavailable = True
            st.session_state.action_initialized = True
    st.session_state.action_initialized = True
    page_nav("action")
    page_heading("AGENTIC AI · RETRIEVAL OPERATIONS", 'RAG<span class="accent">Ops</span> in Action',
                 "Ask a question. Continue the conversation. Inspect the latest retrieval decision.")
    if link_unavailable:
        st.info("That saved example is unavailable. Choose an existing evaluation case below.")
    runtime = render_runtime_controls(status)
    run = st.session_state.get("current_run") if runtime == LIVE else st.session_state.get("saved_run")
    render_runtime_status(status, run)
    if runtime == LIVE and not status.live_configured:
        st.info(runtime_unavailable_message(status))
    if runtime == SAVED:
        html('<div class="source-note">' + icon("shield",14) + ' View Saved Runs · stored evaluation evidence; no workflow or model is rerun.</div>')
    left, right = st.columns(2, gap="medium")
    with left:
        with st.container(border=True, key="action_query"):
            if runtime == LIVE:
                panel_heading("Conversation", "file", "Arabic ↔ English")
                with st.container(height=520, border=False, key="action_conversation", autoscroll=True):
                    if not st.session_state.chat_history:
                        st.caption("Ask a question or choose a suggestion below to start a conversation.")
                    render_live_answer(run)
                with st.container(key="action_suggestions"):
                    html('<div class="quick-label">Suggested questions</div>')
                    suggestions = suggested_cases()
                    for col, case in zip(st.columns(len(suggestions), gap="small"), suggestions):
                        with col:
                            st.button(case["query"], key=f"suggest_{case['id']}", help=case["query"],
                                      on_click=choose_case, args=(case["id"],), width="stretch")
                with st.container(key="action_composer"):
                    pending = approval_view(run)["requires_decision"]
                    st.text_area("Message RAGOps", key="query_text", height=90,
                                 placeholder="اكتب سؤالك أو تابع المحادثة · Ask a question or follow up",
                                 on_change=query_changed, label_visibility="collapsed", disabled=pending)
                    st.button("Send message", key="send_message", type="primary", on_click=submit_message,
                              width="stretch", disabled=not status.live_configured or pending)
            else:
                panel_heading("Saved evaluation run", "file", "Read-only evidence")
                cases = recorded_cases(adapter)
                lookup = {c["id"]: f'{c["label"]} · {c["service"].replace("_", " ")}' for c in cases}
                if st.session_state.get("case_picker") not in ["", *lookup]:
                    st.session_state.case_picker = ""
                st.selectbox("Evaluation cases", ["", *lookup], format_func=lambda x: lookup.get(x, "Choose a saved run…"),
                             key="case_picker", on_change=select_case, label_visibility="collapsed")
                if st.button("View saved run", key="view_saved_run", type="primary", width="stretch"):
                    execute_query(st.session_state.get("query_text", ""), SAVED)
                    st.rerun()
                if run:
                    html(f'<div class="query-context"><p dir="auto">{text(run.get("query"))}</p></div>')
                    metadata = " · ".join(str(run[key]).replace("_", " ") for key in ("platform", "service") if run.get(key))
                    if metadata:
                        st.caption(metadata)
                    accepted_run = run.get("final_run")
                    if not isinstance(accepted_run, dict):
                        accepted = (run.get("validation_result") or {}).get("recommendation") == "ACCEPT_OPTIMIZED"
                        accepted_run = run.get("after_run" if accepted else "before_run") or {}
                    recorded_answer = accepted_run.get("answer")
                    if recorded_answer:
                        st.markdown(recorded_answer, unsafe_allow_html=False)
                    else:
                        st.caption("This record contains retrieval and validation evidence; no conversational answer was stored.")
                else:
                    st.caption("Choose a stored evaluation run to inspect its measured results.")
    with right:
        with st.container(border=True, key="action_results"):
            panel_heading("RAGOps workflow trace", "network", "Latest turn · Four agents")
            if run:
                source = "Saved evaluation record" if run.get("verified") else "Backend execution"
                html(f'<div class="trace-source">{text(source)}</div>')
            elif runtime == LIVE and st.session_state.get("latest_turn_status") == "clarification":
                st.caption("Clarification requested — retrieval has not run for this message.")
            elif runtime == LIVE and st.session_state.get("turn_error"):
                st.caption("This turn did not complete. No earlier run is shown as its result.")
            html(trace_html(compact_trace(run, labelled=labelled_query(run))))
            if run:
                render_decision(run, run.get("mode", runtime))
                if not labelled_query(run):
                    st.caption("Unlabelled query — retrieval quality is not formally validated.")
                warning = evidence_warning(run, labelled=labelled_query(run))
                if warning:
                    st.info(warning)
            else:
                html('<div class="policy-banner neutral">' + icon("shield") + '<div><b>Autonomy is bounded by impact</b>'
                     '<span>Query rewrites and Top-K changes pass automatically. Structural changes require a human decision.</span></div></div>')
            html('<div class="panel-divider"></div>')
            panel_heading("Retrieval evidence", "search")
            if run:
                with st.expander("View Baseline Retrieval", expanded=False):
                    html(evidence_cards(run.get("before_run")))
                    render_document_evidence(run.get("before_run"))
                with st.expander("View Candidate Evidence", expanded=False):
                    html(evidence_cards(run.get("after_run")))
                    render_document_evidence(run.get("after_run"))
                with st.expander("Advanced Technical State", expanded=False):
                    trace_reference = current_langsmith_trace(run)
                    html('<div class="source-note"><b>LangSmith Trace</b> · '
                         + ("✓ Available" if trace_reference else "Off") + '</div>')
                    inspection = inspector_state(run, labelled=labelled_query(run))
                    if trace_reference:
                        inspection["langsmith_trace"] = trace_reference
                    st.json(inspection, expanded=False)
            else:
                st.caption("The latest turn's retrieved evidence will appear here.")
    render_validation(run)
    footer()


def plot_layout(fig: go.Figure, height: int = 220) -> go.Figure:
    fig.update_layout(height=height, margin=dict(l=12,r=12,t=44,b=16),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color="#a8c7d9", family="Segoe UI, Arial, sans-serif", size=12),
        legend=dict(orientation="h", yanchor="bottom", y=1.03, x=0, font=dict(size=11)),
        xaxis=dict(gridcolor="rgba(90,159,190,.1)", zeroline=False, automargin=True, fixedrange=True),
        yaxis=dict(gridcolor="rgba(90,159,190,.1)", zeroline=False, automargin=True, fixedrange=True),
        hoverlabel=dict(bgcolor="#071c2c", font_color="#e7f6ff"), transition_duration=0)
    return fig


def chart_platform(summary: dict) -> go.Figure:
    fig = go.Figure()
    by, k = summary.get("by_platform") or {}, summary.get("k")
    platforms = sorted(by, key=str.casefold)
    for metric,label,color in [("recall_at_k",f"Recall@{k}",CYAN),("precision_at_k",f"Precision@{k}",GREEN),("mrr","MRR",PURPLE)]:
        if any(by[p].get(metric) is not None for p in platforms):
            fig.add_bar(name=label, x=[p.title() for p in platforms], y=[by[p].get(metric) for p in platforms],
                        marker_color=color, hovertemplate="%{x}<br>%{fullData.name}: %{y:.3f}<extra></extra>")
    fig.update_layout(barmode="group", bargap=.30, yaxis_range=[0,1.05])
    return plot_layout(fig, 270)


def donut(labels: list, values: list, colors: list, noun: str) -> go.Figure:
    fig = go.Figure(go.Pie(labels=labels, values=values, hole=.73, marker=dict(colors=colors, line=dict(color="#061521",width=2)),
                          textinfo="none", sort=False, hovertemplate="%{label}: %{value}<extra></extra>"))
    fig.update_layout(annotations=[dict(x=.5,y=.5,text=f'<b>{sum(values)}</b><br>{noun}',showarrow=False,font=dict(size=19,color="#effaff"))])
    plot_layout(fig, 205)
    # A wrapping HTML legend keeps zero-count categories visible on phones.
    fig.update_layout(showlegend=False, margin=dict(l=8,r=8,t=8,b=8))
    return fig


def chart_before_after(d: dict) -> go.Figure:
    fig = go.Figure()
    metrics = [(key,label) for key,label in [("recall_at_k","Recall@K"),("precision_at_k","Precision@K"),("reciprocal_rank","MRR")]
               if d["avg_before"].get(key) is not None and d["avg_after"].get(key) is not None]
    for source,label,color in [("avg_before","Before",CYAN),("avg_after","After",GREEN)]:
        values = [d[source][key] for key,_ in metrics]
        colors = [GREEN if d["avg_after"][key] > d["avg_before"][key] else RED if d["avg_after"][key] < d["avg_before"][key] else "#8caabc" for key,_ in metrics]
        fig.add_bar(name=label,x=[label for _,label in metrics],y=values,marker_color=colors if source == "avg_after" else color,
                    text=[f"{v:.2f}" for v in values],textposition="outside",cliponaxis=False,
                    hovertemplate="%{x}<br>%{fullData.name}: %{y:.3f}<extra></extra>")
    fig.update_layout(barmode="group",yaxis_range=[0,1.14],bargap=.45)
    return plot_layout(fig, 270)


def chart_latency(d: dict) -> go.Figure:
    fig = go.Figure()
    runs = [r for r in d["failures"] if any(isinstance(((r.get("validation") or {}).get(phase) or {}).get("latency_seconds"), (int, float)) for phase in ("before", "after"))]
    run_ids = [r.get("id") for r in runs]
    labels = [f"Run {index+1}" for index in range(len(runs))]
    for phase,label,color in [("before","Before",CYAN),("after","After",GREEN)]:
        fig.add_scatter(name=label,x=labels, customdata=run_ids,
                        y=[((r.get("validation") or {}).get(phase) or {}).get("latency_seconds") for r in runs],
                        mode="lines+markers",line=dict(color=color,width=2),marker_size=6,
                        hovertemplate="%{x} · %{customdata}<br>%{fullData.name}: %{y:.3f}s<extra></extra>")
    plot_layout(fig, 270)
    fig.update_layout(yaxis_title="Seconds", xaxis=dict(tickmode="array",tickvals=labels,ticktext=labels,tickangle=0))
    return fig


def chart_chunking(d: dict) -> go.Figure:
    rows = sorted([r for r in [d["chunking_baseline"], *d["chunking_candidates"]] if r.get("chunk_size") is not None and r.get("chunk_overlap") is not None],key=lambda r:r["chunk_size"])
    fig = go.Figure()
    for metric,label,color in [("recall_at_k","Recall@K",CYAN),("precision_at_k","Precision@K",GREEN),("mrr","MRR",PURPLE)]:
        if any(r.get(metric) is not None for r in rows):
            fig.add_scatter(name=label,x=[f'{r["chunk_size"]}/{r["chunk_overlap"]}' for r in rows], y=[r.get(metric) for r in rows],
                           customdata=["Baseline" if r == d["chunking_baseline"] else "Candidate" for r in rows],
                           mode="lines+markers",line=dict(color=color,width=2),marker_size=7,
                           marker_symbol=["diamond" if r == d["chunking_baseline"] else "circle" for r in rows],
                           hovertemplate="%{customdata} · %{x}<br>%{fullData.name}: %{y:.3f}<extra></extra>")
    fig.update_layout(yaxis_range=[0,1.04],xaxis_title="Chunk size / overlap")
    return plot_layout(fig, 270)


def chart_panel(title: str, subtitle: str, fig: go.Figure, key: str, *, note: str = "") -> None:
    with st.container(border=True, key=key):
        html(f'<div class="chart-title">{text(title)}</div><div class="chart-subtitle">{text(subtitle)}</div>')
        st.plotly_chart(fig, width="stretch", config={"displayModeBar":False}, key=f"plot_{key}")
        if fig.data and fig.data[0].type == "pie":
            pie = fig.data[0]
            html('<div class="dashboard-chart-legend">' + ''.join(
                f'<span><i style="background:{text(color)}"></i>{text(label)}<b>{text(value)}</b></span>'
                for label,value,color in zip(pie.labels, pie.values, pie.marker.colors)) + '</div>')
        if note:
            st.caption(note)


def select_dashboard_run(case_id: str) -> None:
    st.session_state.inspector_id = case_id


def render_dashboard() -> None:
    page_nav("dashboard")
    st.html(DASHBOARD_CSS)
    d = evaluation_dashboard(adapter)
    s, count = d["summary"], len(d["failures"])
    with st.container(key="dashboard_content"):
        page_heading("OFFICIAL EVALUATION RESULTS", 'Evaluation Evidence <span class="accent">at a Glance.</span>',
                     "Did RAGOps improve retrieval quality? Explore the verified baseline and the measured results of targeted optimizations.")
        with st.container(key="dashboard_official"):
            with st.container(key="dashboard_snapshot"):
                html('<div class="dashboard-snapshot-label"><b>Official Evaluation Snapshot</b><span>Based on the verified evaluation dataset</span></div>')
                html(kpi_grid_html([
                    ("Evaluation Queries",s.get("total_queries"),"Labelled evaluation set"),
                    ("Platforms",len(s.get("by_platform") or {}),"Current evaluation corpus"),
                    ("Baseline Failures",d["baseline_failure_count"],f'Zero Recall@{s.get("k")}'),
                    ("Verified Labelled Failures Improved",f'{d["outcomes"].get("IMPROVED",0)}/{count}',"Stored validation results"),
                    (f'Baseline Recall@{s.get("k")}',f'{s["overall"]["recall_at_k"]:.1%}',"Monitoring · baseline retrieval"),
                ]))
                html(f'<p class="dashboard-scope-note">Before → After covers the {count} verified failure runs. A combined post-optimization result for all {text(s.get("total_queries"))} evaluation queries is not recorded.</p>')
            c1,c2,c3 = st.columns([1.6,1,1],gap="small")
            with c1:
                chart_panel("Performance by Platform",f'Monitoring · baseline Recall@{s.get("k")}, Precision@{s.get("k")} and MRR',chart_platform(s),"chart_platform")
            with c2:
                platforms = sorted({r["Platform"] for r in d["history_rows"] if r.get("Platform")})
                chart_panel("Failure Distribution","Diagnosis · recorded causes in the verified failure set",donut(list(d["display_issue_counts"]),list(d["display_issue_counts"].values()),[CYAN,GREEN,PURPLE],"Failures"),"chart_failures",
                            note="Verified failures recorded for " + " and ".join(platforms) + ".")
            with c3:
                chart_panel("Validation Outcomes","Validation · measured retrieval outcomes only",donut(["Improved","No Meaningful Change","Worse"],[d["outcomes"].get(x,0) for x in ["IMPROVED","SAME","WORSE"]],[GREEN,"#8caabc",RED],"Runs"),"chart_outcomes")
            with st.container(key="dashboard_compare_metrics"):
                html(f'<p class="dashboard-scope-note">Paired averages across {count} verified failure runs only.</p>')
                html('<div class="dashboard-section-label"><b>BEFORE → AFTER</b><span>Metrics use each run\'s configured K.</span></div>')
                html(metrics_compare_html(d["avg_before"], d["avg_after"], labels={
                    "Reciprocal Rank":"MRR (Mean Reciprocal Rank)", "Latency":"Observed Retrieval Latency",
                }))
            c4,c5,c6 = st.columns([1.6,1,1],gap="small")
            with c4:
                chart_panel("Retrieval Quality: Before → After","Verified failure runs · higher is better · K follows each recorded run",chart_before_after(d),"chart_compare")
            with c5:
                if d["avg_before"].get("latency_seconds") is not None or d["avg_after"].get("latency_seconds") is not None:
                    chart_panel("Observed Retrieval Latency","Recorded timings · hover for the stored case ID",chart_latency(d),"chart_latency",
                                note="Observed timings do not establish a causal speedup from RAGOps.")
            with c6:
                if d["chunking_candidates"]:
                    chart_panel("Structural Experiment — Chunking Sweep",f"Evaluated separately from the {count} verified failure cases.",chart_chunking(d),"chart_chunking",
                                note="Diamond = baseline. " + str(adapter.chunk_sweep.get("decision_policy") or "")
                                + " Permanent promotion decision not recorded.")
        with st.container(border=True,key="history"):
            panel_heading("Run History", "file", "Saved evaluation runs")
            search_col, platform_col = st.columns([2,1],gap="small")
            with search_col:
                search = st.text_input("Search runs",placeholder="Search query, issue, or run…",label_visibility="collapsed")
            with platform_col:
                platform = st.selectbox("Platform filter",["All platforms", *sorted({r["Platform"] for r in d["history_rows"] if r.get("Platform")})],label_visibility="collapsed")
            rows = []
            for row,raw in zip(d["history_rows"], d["run_rows"]):
                if platform != "All platforms" and row["Platform"] != platform: continue
                if search and search.casefold() not in ' '.join(str(v) for v in [*row.values(), raw.get("Query")]).casefold(): continue
                rows.append(row)
            with st.container(key="dashboard_history_desktop"):
                selection = st.dataframe(rows,hide_index=True,width="stretch",
                    column_order=["Case","Platform","Issue","Action","Decision","Validation Verdict"],
                    column_config={"Case":st.column_config.TextColumn(width="medium"),"Platform":st.column_config.TextColumn(width="small"),
                        "Issue":st.column_config.TextColumn(width="small"),"Action":st.column_config.TextColumn(width="small"),
                        "Decision":st.column_config.TextColumn(width="medium"),"Validation Verdict":st.column_config.TextColumn(width="small")},
                    on_select="rerun",selection_mode="single-row",key=f"history_selection_{hash((search, platform))}")
            with st.container(key="dashboard_history_mobile"):
                for row in rows:
                    with st.expander(str(row.get("Case") or "Case ID not recorded"), expanded=False):
                        html('<div class="dashboard-inspector-fields">' + ''.join(
                            f'<div><small>{text(label)}</small><b>{text(value)}</b></div>'
                            for label,value in row.items() if label != "Case") + '</div>')
                        if row.get("Case"):
                            st.button("Inspect case",key=f'dashboard_inspect_{row["Case"]}',width="stretch",
                                      on_click=select_dashboard_run,args=(row["Case"],))
            selection_fingerprint = (search, platform, tuple(selection.selection.rows))
            if selection.selection.rows and selection_fingerprint != st.session_state.get("last_history_selection"):
                selected_index = selection.selection.rows[0]
                if selected_index < len(rows):
                    st.session_state.inspector_id = rows[selected_index]["Case"]
            st.session_state.last_history_selection = selection_fingerprint
            if not rows: st.caption("No stored runs match these filters.")
        with st.container(border=True,key="inspector"):
            panel_heading("Run Inspector", "search", "Select a history row or choose a stored case")
            ids = [r["Case"] for r in d["history_rows"] if r.get("Case")]
            if st.session_state.get("inspector_id") not in ids:
                st.session_state.pop("inspector_id", None)
            chosen = st.selectbox("Inspect a run",ids,key="inspector_id",label_visibility="collapsed",disabled=not ids)
            if chosen:
                run = recorded_run(adapter, chosen)
                proposal = run.get("optimization_proposal") or {}
                validation = run.get("validation_result") or {}
                summary, measured = st.columns([1,1.35],gap="medium")
                with summary:
                    html(f'<div class="dashboard-inspector-query"><small>Query</small><p dir="auto">{text(run.get("query"))}</p></div>')
                    html('<div class="dashboard-inspector-fields">' + ''.join(
                        f'<div><small>{text(k)}</small><b dir="auto">{text(v)}</b></div>' for k,v in [
                            ("Platform",str(run.get("platform") or "Not recorded").title()),
                            ("Diagnosis",(run.get("diagnosis_report") or {}).get("issue_type") or "Not recorded"),
                            ("Optimization action",action_label(proposal.get("action"))),
                            ("Decision",decision_label(run)),
                        ]) + '</div>')
                    result = accepted_result(run)
                    if result:
                        html(f'<div class="dashboard-accepted"><small>Accepted result</small><b>{text(result)}</b></div>')
                with measured:
                    html('<div class="dashboard-section-label"><b>Before metrics → After metrics</b></div>')
                    html(metrics_compare_html(validation.get("before") or {},validation.get("after") or {},
                                              labels={"Latency":"Observed Retrieval Latency"}))
                    if validation.get("verdict") in {"IMPROVED","SAME","WORSE"}:
                        html(verdict_html(validation["verdict"]))
                with st.expander("Retrieved evidence", expanded=False):
                    before,after = st.tabs(["Baseline","Candidate"])
                    with before: render_document_evidence(run.get("before_run"))
                    with after: render_document_evidence(run.get("after_run"))
                with st.expander("Technical state", expanded=False):
                    st.json(safe_state(run),expanded=False)
        latest = st.session_state.get("current_run")
        labelled = bool(isinstance(latest, dict) and adapter.match_dataset_query(latest.get("query", "")))
        live = live_run_summary(latest, labelled=labelled)
        if live:
            if "Action" in live:
                live["Action"] = action_label(live["Action"])
            with st.container(border=True,key="dashboard_live_run"):
                panel_heading("Latest Live Run", "play", "Current Session — separate from official evaluation")
                html('<div class="dashboard-live-fields">' + ''.join(
                    f'<div><small>{text(label)}</small><span dir="auto">{text(value)}</span></div>'
                    for label,value in live.items()) + '</div>')
    footer()


def render_architecture() -> None:
    page_nav("architecture")
    with st.container(border=False,key="architecture_content"):
        page_heading("SYSTEM ARCHITECTURE", 'Four functional agents. One <span class="accent">controlled</span> optimization loop.',
                     "Retrieval optimization with human review for structural changes.")
        html(architecture_html())
        orchestration,observability = st.columns(2,gap="small")
        with orchestration:
            with st.container(border=True,key="architecture_langgraph"):
                panel_heading("LangGraph","network")
                st.caption("Workflow orchestration · shared state · interrupt/resume")
        with observability:
            with st.container(border=True,key="architecture_langsmith"):
                panel_heading("LangSmith","chart")
                st.caption("Optional observability")
                settings = tracing_settings()
                html(f'<div class="source-note">{"Tracing: On ✓" if settings.enabled else "Tracing: Off"}</div>')
                if settings.enabled:
                    html(f'<div class="source-note">Project: {text(settings.project)}</div>')
                trace_reference = current_langsmith_trace(st.session_state.get("current_run"))
                if trace_reference:
                    html('<div class="source-note">Last run traced ✓</div>')
                    if trace_reference.get("url"):
                        st.link_button("Open Latest Trace ↗", trace_reference["url"])
        with st.container(border=False,key="architecture_state"):
            with st.expander("View Shared State",expanded=False):
                fields = [("query","user request"),("monitoring_report","retrieval signals"),("diagnosis_report","root cause"),
                          ("optimization_proposal","proposed action"),("approval_result","policy / human decision"),
                          ("execution_result","applied action"),("before_run / after_run","retrieval evidence"),
                          ("validation_result","measured impact"),("trace","reported workflow stages")]
                html('<div class="state-code">' + ''.join(f'<div><code>{text(k)}</code><span>{text(v)}</span></div>' for k,v in fields) + '</div>')
        footer()


def render_team() -> None:
    page_nav("team")
    page_heading("TEAM · OWNERSHIP · COLLABORATION", 'Meet the Team Behind RAG<span class="accent">Ops</span>',
                 "Different strengths. A shared mission: turning retrieval evidence into measurable improvement.")
    html(team_html())
    with st.container(border=True,key="team_stack"):
        html('<div class="stack-panel"><div><div class="section-kicker">BUILT TOGETHER</div>'
             '<h2 class="section-title">A shared stack. A shared purpose.</h2><p class="section-copy">The technologies behind this project.</p></div>'
             '<div class="stack-items">' + ''.join(f'<div>{icon(glyph,25)}<span>{label}</span></div>' for label,glyph in [
                 ("Python","code"),("Streamlit","chart"),("LangGraph","network"),("LangChain","link"),("OpenAI","layers"),("FAISS","database"),("Plotly","chart")]) + '</div></div>')
    footer()


PAGES = {"overview":render_overview,"action":render_action,"dashboard":render_dashboard,"architecture":render_architecture,"team":render_team}
navigation_bridge(recorded_cases(adapter))
page = str(st.query_params.get("page","overview")).lower()
PAGES.get(page,render_overview)()
