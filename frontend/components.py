"""Escaped, reusable presentation components for the Streamlit frontend."""
from __future__ import annotations

from html import escape
from math import isfinite
from typing import Any, Dict, Iterable, Optional
from .architecture import architecture_html
from .team import team_html
from .config import NAV_ITEMS
from .icons import icon, logo_svg


def nav_html(active: str, mode_label: str = "Saved Evidence Mode", status_note: str = "", status_kind: str = "neutral", *, show_status: bool = True) -> str:
    icons = {"overview": "home", "action": "play", "dashboard": "chart", "architecture": "network", "team": "users"}
    links = []
    for key, label in NAV_ITEMS:
        selected = key == active
        links.append(f'<a class="{"active" if selected else ""}" href="?page={escape(key)}" target="_self" {"aria-current=page" if selected else ""}>{icon(icons[key])}<span>{escape(label)}</span></a>')
    kind = "available" if status_kind == "available" else "neutral"
    status = (f'<div class="nav-status {kind}"><span class="status-dot {kind}"></span><div class="status-copy">{escape(mode_label)}<small class="status-note">{escape(status_note)}</small></div></div>'
              if show_status else "")
    return f'''<header class="ragops-nav-shell"><div class="ragops-nav">
      <a class="brand-wrap" href="?page=overview" target="_self" aria-label="RAGOps Agent overview"><span class="brand-mark">{logo_svg()}</span><span class="brand-name">RAG<span>Ops</span> Agent</span></a>
      <nav class="nav-links" aria-label="Primary navigation">{''.join(links)}</nav>
      {status}
    </div></header>'''


def mode_banner_html(mode: str, note: str, backend_status: str) -> str:
    return f'<div class="mode-banner"><div class="mode-left"><span class="mode-pill">{escape(mode)}</span><span class="mode-note">{escape(note)}</span></div><div class="backend-status">{escape(backend_status)}</div></div>'


def failure_cards_html(case_links: Optional[Dict[str, str]] = None) -> str:
    cards = [
        ("cyan", "chart", "top-k", "Top-K Retrieval", "Relevant evidence falls outside the retrieval window.", "Expand Top-K and re-evaluate retrieval."),
        ("violet", "file", "query-mismatch", "Query Mismatch", "Query wording and source terminology do not align.", "Rewrite the query and validate the results."),
        ("teal", "layers", "structural", "Chunking Quality", "Context boundaries can split important evidence.", "Review a re-chunking candidate before execution."),
    ]
    output = []
    for theme, symbol, kind, title, copy, action in cards:
        href = (case_links or {}).get(title)
        tag = "a" if href else "article"
        interactive = " interactive" if href else ""
        attributes = f' href="{escape(href, quote=True)}" target="_self" aria-label="Inspect verified {escape(title, quote=True)} case"' if href else ""
        arrow = f'<span class="failure-arrow">{icon("arrow")}</span>' if href else ""
        output.append(f'<{tag} class="failure-card theme-{theme}{interactive}" data-failure-kind="{kind}"{attributes}><div class="failure-top"><span class="failure-icon">{icon(symbol,28)}</span><div><h3>{escape(title)}</h3><p>{escape(copy)}</p></div>{arrow}</div><div class="failure-response">{icon("settings")}<div><span>RAGOps response</span><p>{escape(action)}</p></div></div></{tag}>')
    return '<div class="failure-grid">' + ''.join(output) + '</div>'


def trace_html(steps: Iterable[Dict[str, Any]]) -> str:
    stages = list(steps)
    output = []
    symbols = {"baseline": "database", "monitoring": "eye", "diagnosis": "search", "optimization": "settings", "approval": "shield", "execution": "play", "validation": "chart"}
    complete = {"complete", "completed", "auto_approved", "approved", "improved", "same", "worse", "proposal_ready", "applied", "executed"}
    for idx, step in enumerate(stages):
        status = str(step.get("status") or "waiting").lower()
        stage = str(step.get("stage") or "")
        state = "done" if status in complete else "pending" if status in {"pending", "pending_human_approval"} else "active" if status == "running" else "rejected" if status in {"rejected", "failed", "error"} else "waiting"
        symbol = "check" if state == "done" else "user" if state == "pending" and stage == "approval" else "close" if state == "rejected" else symbols.get(stage, "settings")
        output.append(f'<div class="trace-stage {state}" style="--step:{idx}"><div class="trace-dot {state}">{icon(symbol,23)}</div><span class="trace-number">{idx+1:02d}</span><div class="trace-name">{escape(str(step.get("name") or "Stage"))}</div><div class="trace-role">{escape(str(step.get("role") or "System"))}</div><div class="trace-status {state}">{escape(str(step.get("label") or status.replace("_", " ")))}</div><div class="trace-detail" dir="auto">{escape(str(step.get("detail") or ""))}</div></div>')
        if idx < len(stages)-1:
            next_status = str(stages[idx+1].get("status") or "waiting").lower()
            connector = "active" if next_status == "running" else "done" if state == "done" else ""
            output.append(f'<div class="trace-connector {connector}" aria-hidden="true">{icon("arrow",24)}</div>')
    return '<div class="trace-ribbon" aria-label="Workflow execution stages">' + ''.join(output) + '</div>'


def approval_card_html(proposal: Dict[str, Any], structural: bool = True) -> str:
    """Display a proposal without inventing parameter values or expected gains."""
    params = proposal.get("parameters") or {}
    action = str(proposal.get("action") or "Not reported")
    reason = str(proposal.get("reason") or "No reason reported.")
    if action == "rechunk_and_reindex":
        scope = f'Chunk size: {params.get("chunk_size", "—")} · overlap: {params.get("chunk_overlap", "—")}'
    elif action == "change_top_k":
        scope = f'Top-K: {params.get("baseline_k", "—")} → {params.get("new_k", "—")}'
    else:
        scope = "Current query"
    high_impact = structural and action == "rechunk_and_reindex"
    tag = "Human approval required" if high_impact else "Automatic policy"
    title = "Review the structural proposal before continuing." if high_impact else "Low-impact optimization"
    detail = "Approve or reject the proposed change. Validation follows execution." if high_impact else "This action does not require a human decision."
    return f'''<div class="approval-card {"" if high_impact else "policy-success"}">
      <div class="approval-tag">{icon("user" if high_impact else "shield",22)} {tag}</div><div class="approval-title">{title}</div>
      <div class="approval-grid"><div class="approval-field"><span>Proposed action</span><b>{escape(action.replace("_", " "))}</b><small>{escape(scope)}</small></div><div class="approval-field"><span>Reason</span><b dir="auto">{escape(reason)}</b></div><div class="approval-field"><span>Control policy</span><b>{detail}</b></div></div>
    </div>'''


def _numeric(value: Any) -> Optional[float]:
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if isfinite(number) else None


def _fmt_value(name: str, value: Any) -> str:
    number = _numeric(value)
    if number is None:
        return "—"
    if name == "Latency":
        return f"{number:.2f}s"
    if name == "LLM Judge":
        return f"{number:.1f}/5"
    if name == "First Relevant Rank":
        return "—" if number <= 0 else str(int(number))
    return f"{number:.2f}"


def metrics_compare_html(before: Dict[str, Any], after: Dict[str, Any], first_before: Optional[int] = None, first_after: Optional[int] = None, *, ranks_known: bool = False, labels: Optional[Dict[str, str]] = None) -> str:
    items = [
        ("Recall@K", before.get("recall_at_k"), after.get("recall_at_k"), True),
        ("Precision@K", before.get("precision_at_k"), after.get("precision_at_k"), True),
        ("Reciprocal Rank", before.get("reciprocal_rank"), after.get("reciprocal_rank"), True),
        ("LLM Judge", before.get("judge_score"), after.get("judge_score"), True),
        ("Latency", before.get("latency_seconds"), after.get("latency_seconds"), False),
        ("First Relevant Rank", first_before, first_after, False),
    ]
    cards = []
    for name, before_value, after_value, higher_good in items:
        b, a = _numeric(before_value), _numeric(after_value)
        if name == "First Relevant Rank":
            b = b if b is not None and b > 0 else None
            a = a if a is not None and a > 0 else None
        if b is None and a is None:
            continue
        delta_class, delta_text = "neutral", "Not recorded"
        if name == "First Relevant Rank" and ranks_known and b is None and a is not None and a > 0:
            delta_class, delta_text = "good", "Relevant result found"
        elif name == "First Relevant Rank" and ranks_known and a is None and b is not None and b > 0:
            delta_class, delta_text = "bad", "No relevant result"
        elif b is not None and a is not None:
            delta = a-b
            favorable = delta > 0 if higher_good else delta < 0
            delta_class = "good" if favorable else "neutral" if delta == 0 else "bad"
            delta_text = f"{delta:+.2f}" + ("s" if name == "Latency" else "")
            if name == "Latency" and 0 < abs(delta) < 0.01:
                milliseconds = abs(delta) * 1000
                amount = f"{milliseconds:.2f}" if milliseconds >= 0.01 else "<0.01"
                delta_text = ("+" if delta > 0 else "−") + amount + "ms"
            if name == "First Relevant Rank":
                delta_text = f"{int(delta):+d} rank"
        hint = '<small class="metric-direction">Lower is better</small>' if name == "First Relevant Rank" else ""
        label = escape((labels or {}).get(name, name))
        cards.append(f'<div class="metric-card"><div class="metric-name">{label}</div>{hint}<div class="metric-values"><span class="metric-before">{_fmt_value(name,b)}</span><span class="metric-arrow">→</span><span class="metric-after">{_fmt_value(name,a)}</span></div><div class="metric-delta {delta_class}">{escape(delta_text)}</div></div>')
    return '<div class="metric-grid">' + ''.join(cards) + '</div>' if cards else ""


def verdict_html(verdict: str, recommendation: str = "") -> str:
    value = str(verdict or "").upper()
    known = value in {"IMPROVED", "SAME", "WORSE"}
    cls = value.lower() if known else "neutral"
    symbol = "check" if value == "IMPROVED" else "close" if value == "WORSE" else "clock"
    title = ("NO MEANINGFUL CHANGE" if value == "SAME" else value) if known else "Validation not recorded"
    detail = str(recommendation or "").replace("_", " ") if known else ""
    return f'<div class="verdict {cls}"><span class="verdict-icon">{icon(symbol,28)}</span><div><h3>{escape(title)}</h3><p>{escape(detail)}</p></div></div>'


def kpi_grid_html(kpis: Iterable[tuple]) -> str:
    symbols = ["file", "layers", "warning", "play", "chart", "check"]
    cards = []
    for index, (label, value, sub) in enumerate(kpis):
        cards.append(f'<div class="kpi"><span class="kpi-icon">{icon(symbols[index % len(symbols)],27)}</span><div class="kpi-copy"><div class="label">{escape(str(label))}</div><div class="value">{escape(str(value)) if value is not None else "—"}</div><div class="sub">{escape(str(sub))}</div></div></div>')
    return '<div class="kpi-grid">' + ''.join(cards) + '</div>'
