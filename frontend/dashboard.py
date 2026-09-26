"""Read-only dashboard projections from the adapter's loaded evaluation artifacts."""
from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from copy import deepcopy
import math
from numbers import Real
from typing import Any

from .action_presentation import feedback_state, healthy_baseline


_METRICS = ("recall_at_k", "precision_at_k", "reciprocal_rank", "latency_seconds")
_VERDICTS = ("IMPROVED", "SAME", "WORSE")
_PLATFORMS = ("absher", "balady", "najiz", "sakani")
_ISSUE_LABELS = {
    "Query Mismatch": "Query Mismatch",
    "Top-K": "Top-K Retrieval",
    "Chunking Quality": "Chunking Quality",
}
_VALIDATION_LABELS = {
    "IMPROVED": "Improved", "SAME": "No Meaningful Change", "WORSE": "Worse",
}


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _records(value: Any) -> list[Mapping[str, Any]]:
    if not isinstance(value, (list, tuple)):
        return []
    return [row for row in value if isinstance(row, Mapping)]


def _finite_number(value: Any) -> float | None:
    # JSON booleans compare equal to 0/1 but are not measured metric values.
    if isinstance(value, bool) or not isinstance(value, Real):
        return None
    try:
        number = float(value)
    except (OverflowError, TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _reported_text(value: Any) -> str | None:
    return value if isinstance(value, str) and value.strip() else None


def _paired_metrics(rows: list[Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    """Compare the same measured runs on both sides of each metric.

    A run with only one measured side cannot support a Before/After delta.
    Missing values are never treated as zero, and latencies are seconds.
    """
    result: dict[str, dict[str, Any]] = {}
    for metric in _METRICS:
        pairs = []
        for row in rows:
            validation = _mapping(row.get("validation"))
            before = _finite_number(_mapping(validation.get("before")).get(metric))
            after = _finite_number(_mapping(validation.get("after")).get(metric))
            if before is not None and after is not None:
                pairs.append((before, after))
        count = len(pairs)
        before = math.fsum(pair[0] / count for pair in pairs) if count else None
        after = math.fsum(pair[1] / count for pair in pairs) if count else None
        delta = after - before if count else None
        lower_is_better = metric == "latency_seconds"
        direction = None
        if delta is not None:
            direction = "neutral" if delta == 0 else (
                "improved" if (delta < 0 if lower_is_better else delta > 0) else "worse"
            )
        result[metric] = {
            "before": before, "after": after, "delta": delta, "count": count,
            "direction": direction, "lower_is_better": lower_is_better,
        }
    return result


def validation_label(verdict: Any) -> str | None:
    """Only a validation verdict can become a validation outcome."""
    return _VALIDATION_LABELS.get(verdict) if isinstance(verdict, str) else None


def action_label(action: Any) -> str | None:
    """Readable action names; preserve unknown reported actions as reported."""
    value = _reported_text(action)
    return {
        "rewrite_query": "Rewrite query",
        "change_top_k": "Change Top-K",
        "rechunk_and_reindex": "Re-chunk & re-index",
    }.get(value, value)


def decision_label(run: Any) -> str:
    """Name recorded workflow-control decisions without inferring approval."""
    state = _mapping(run)
    approval = _mapping(state.get("approval_result") or state.get("approval"))
    status = approval.get("approval_status")
    human = approval.get("human_decision") or state.get("human_decision")
    if status == "rejected" or human == "reject":
        return "Human rejected"
    if status == "approved" or human == "approve":
        return "Human approved"
    if status == "auto_approved":
        return "Auto-approved by policy"
    if state.get("final_status") == "NO_ACTION_REQUIRED":
        return "Not required"
    # Pending or absent decisions remain absent; a low-impact action alone
    # does not prove that the policy gate actually ran.
    return "Not recorded"


def accepted_result(run: Any) -> str | None:
    """Describe acceptance from the saved recommendation, not from approval."""
    state = _mapping(run)
    validation = _mapping(state.get("validation_result") or state.get("validation"))
    recommendation = validation.get("recommendation")
    if recommendation == "ACCEPT_OPTIMIZED":
        return "Optimized retrieval"
    if recommendation == "RETAIN_BASELINE":
        return "Baseline retained"
    approval = _mapping(state.get("approval_result") or state.get("approval"))
    if approval.get("next_step") == "retain_baseline" or state.get("final_status") == "NO_ACTION_REQUIRED":
        return "Baseline retained"
    return None


def live_run_summary(run: Any, *, labelled: bool = False) -> dict[str, Any] | None:
    """Small session-only projection, deliberately independent of evaluations.

    Unlabelled live retrieval cannot support a formal quality verdict even if
    the backend's heuristic validation state contains a verdict string.
    """
    state = _mapping(run)
    if state.get("mode") != "LIVE MODE" or state.get("verified") is True:
        return None
    query = _reported_text(state.get("user_query")) or _reported_text(state.get("query"))
    if query is None:
        return None
    if healthy_baseline(state):
        return {"Query": query, "Status": "Healthy baseline · No optimization required"}
    diagnosis = _mapping(state.get("diagnosis_report"))
    proposal = _mapping(state.get("optimization_proposal"))
    validation = _mapping(state.get("validation_result"))
    fields = {
        "Diagnosis": _reported_text(diagnosis.get("issue_type")),
        "Action": _reported_text(proposal.get("action")),
        "Validation outcome": validation_label(validation.get("verdict")) if labelled else None,
    }
    if fields["Action"] == "none":
        fields["Action"] = None
    details = {key: value for key, value in fields.items() if value is not None}
    if not details and _records(_mapping(state.get("final_run")).get("retrieved_results")):
        feedback = feedback_state(state, labelled=labelled)
        if feedback:
            details["Result"] = feedback["text"]
    return {"Query": query, **details} if details else None


def evaluation_dashboard(adapter: Any) -> dict[str, Any]:
    """Project stored evaluations without invoking runtime or adapter replay methods.

    ``failures`` and history contain only workflow artifact rows. In particular,
    the adapter's synthetic structural review case is never added. Latencies
    come from recorded validation metrics, not reconstructed run placeholders.
    Returned structures are detached copies, so UI formatting cannot mutate the
    adapter's cached evidence.
    """
    retrieval = _mapping(getattr(adapter, "retrieval", None))
    workflow = _mapping(getattr(adapter, "workflow", None))
    sweep = _mapping(getattr(adapter, "chunk_sweep", None))
    retrieval_rows = _records(retrieval.get("results"))
    failures = _records(workflow.get("results"))
    summary = _mapping(retrieval.get("summary"))
    platform_metrics = _mapping(summary.get("by_platform"))
    platform_rows = [
        {"Platform": platform.title(), **dict(_mapping(platform_metrics[platform]))}
        for platform in _PLATFORMS if platform in platform_metrics
    ]
    pairs = _paired_metrics(failures)

    issue_counts: Counter[str] = Counter()
    outcomes = dict.fromkeys(_VERDICTS, 0)
    run_rows = []
    history_rows = []
    for row in failures:
        diagnosis = _mapping(row.get("diagnosis"))
        proposal = _mapping(row.get("proposal"))
        approval = _mapping(row.get("approval"))
        validation = _mapping(row.get("validation"))
        issue = _reported_text(diagnosis.get("issue_type"))
        verdict = _reported_text(validation.get("verdict"))
        if issue is not None:
            issue_counts[issue] += 1
        if verdict in outcomes:
            outcomes[verdict] += 1

        platform = _reported_text(row.get("platform"))
        run_rows.append({
            "Run": row.get("id"),
            "Query": row.get("original_query"),
            "Platform": platform.title() if platform is not None else None,
            "Issue": issue,
            "Proposed Action": proposal.get("action"),
            "Human Decision": (
                _reported_text(approval.get("human_decision"))
                or _reported_text(approval.get("approval_status"))
            ),
            "Verdict": validation.get("verdict"),
            "Policy Reviewed": approval.get("reviewed_at"),
        })
        history_rows.append({
            "Case": row.get("id"),
            "Platform": platform.title() if platform is not None else None,
            "Issue": _ISSUE_LABELS.get(issue, issue),
            "Action": action_label(proposal.get("action")),
            "Decision": decision_label(row),
            "Validation Verdict": validation_label(verdict),
        })

    baseline_failure_count = sum(
        _finite_number(row.get("recall_at_k")) == 0.0 for row in retrieval_rows
    )
    failure_platforms = Counter(
        row["platform"] for row in retrieval_rows
        if _finite_number(row.get("recall_at_k")) == 0.0 and _reported_text(row.get("platform"))
    )

    return deepcopy({
        "summary": dict(summary),
        "snapshot": {
            "evaluation_queries": summary.get("total_queries"),
            "platforms": len(platform_metrics),
            "baseline_failures": baseline_failure_count,
            "verified_failures_improved": outcomes["IMPROVED"],
            "verified_failure_runs": len(failures),
            "baseline_recall_at_k": _mapping(summary.get("overall")).get("recall_at_k"),
            "k": summary.get("k"),
        },
        "platform_rows": platform_rows,
        "failures": [dict(row) for row in failures],
        "baseline_failure_count": baseline_failure_count,
        "baseline_failure_platforms": {
            platform.title(): failure_platforms[platform]
            for platform in _PLATFORMS if failure_platforms[platform]
        },
        "avg_before": {metric: pair["before"] for metric, pair in pairs.items()},
        "avg_after": {metric: pair["after"] for metric, pair in pairs.items()},
        "paired_metrics": pairs,
        "issue_counts": dict(issue_counts),
        "display_issue_counts": {label: issue_counts[issue] for issue, label in _ISSUE_LABELS.items()},
        "outcomes": outcomes,
        "chunking_candidates": [dict(row) for row in _records(sweep.get("candidates"))],
        "chunking_baseline": dict(_mapping(sweep.get("baseline"))),
        "run_rows": run_rows,
        "history_rows": history_rows,
    })
