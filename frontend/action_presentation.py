"""Pure projections used only by the RAGOps in Action page."""
from __future__ import annotations

from math import isfinite
from typing import Any

from .presentation import approval_view, normalized_trace, safe_state


_TERMINAL = {"NO_ACTION_REQUIRED", "NEEDS_REVIEW", "IMPROVED", "SAME", "WORSE", "REJECTED"}
_QUALITY_OUTCOMES = {"IMPROVED", "SAME", "WORSE"}
_ACTION_LABELS = {"rewrite_query": "Rewrite query", "change_top_k": "Change Top-K", "rechunk_and_reindex": "Re-chunk & re-index"}


def _state(run: Any) -> dict:
    if not isinstance(run, dict):
        return {}
    return run["state"] if isinstance(run.get("state"), dict) else run


def _mapping(value: Any) -> dict:
    return value if isinstance(value, dict) else {}


def _pending(state: dict) -> bool:
    return bool(state.get("__interrupt__")) or approval_view(state)["requires_decision"]


def healthy_baseline(run: Any) -> bool:
    """Recognize the completed healthy branch from its actual backend signals."""
    state = _state(run)
    monitoring = _mapping(state.get("monitoring_report"))
    diagnosis = _mapping(state.get("diagnosis_report"))
    before = state.get("before_run")
    return (
        state.get("final_status") == "NO_ACTION_REQUIRED"
        and monitoring.get("failure_detected") is False
        and monitoring.get("baseline_relevant_found") is True
        and diagnosis.get("recommended_action") == "none"
        and not diagnosis.get("issue_type")
        and isinstance(before, dict)
        and bool(before)
        and state.get("final_run") == before
        and not _pending(state)
        and not any(state.get(key) for key in (
            "optimization_proposal", "execution_result", "after_run", "validation_result",
        ))
    )


def validation_summary(run: Any, *, labelled: bool) -> dict[str, str]:
    """Describe the latest run without implying an unperformed comparison."""
    state = _state(run)
    if not state:
        return {"kind": "empty", "message": ""}
    if _pending(state):
        return {"kind": "pending", "message": "Validation waits for the structural decision and execution."}
    before = state.get("before_run")
    no_execution = not any(state.get(key) for key in ("execution_result", "after_run", "validation_result"))
    if (state.get("final_status") == "REJECTED"
            and approval_view(state)["kind"] == "rejected"
            and isinstance(before, dict) and bool(before)
            and state.get("final_run") == before and no_execution):
        return {"kind": "rejected", "message": "Baseline retained — no candidate execution was performed"}
    if not labelled:
        return {"kind": "unlabelled", "message": "Formal Before/After metrics unavailable for this unlabelled query"}
    if healthy_baseline(state):
        return {"kind": "healthy", "message": "No optimization required"}
    validation = _mapping(state.get("validation_result"))
    metrics_before, metrics_after = _mapping(validation.get("before")), _mapping(validation.get("after"))
    metric_names = ("recall_at_k", "precision_at_k", "reciprocal_rank", "latency_seconds", "first_relevant_rank")
    comparable = any(
        all(isinstance(value, (int, float)) and not isinstance(value, bool) and isfinite(value)
            for value in (metrics_before.get(key), metrics_after.get(key)))
        for key in metric_names
    )
    if str(validation.get("verdict") or "").upper() in _QUALITY_OUTCOMES and comparable:
        return {"kind": "metrics", "message": ""}
    return {"kind": "empty", "message": "Measured results appear when validation is available."}


def compact_trace(run: Any, *, labelled: bool) -> list[dict]:
    """Keep the seven reported stages, with one short label and no long detail."""
    state = _state(run)
    diagnosis = _mapping(state.get("diagnosis_report"))
    proposal = _mapping(state.get("optimization_proposal"))
    validation = _mapping(state.get("validation_result"))
    gate = approval_view(state)
    healthy = healthy_baseline(state)
    healthy_labels = {
        "baseline": "Complete", "monitoring": "Healthy", "diagnosis": "No retrieval issue detected",
        "optimization": "Not needed", "approval": "Not needed", "execution": "Not needed",
        "validation": "Not required",
    }
    status_labels = {
        "waiting": "Waiting", "not_recorded": "Not recorded", "skipped": "Not run",
        "not_run": "Not run", "completed": "Complete", "complete": "Complete",
        "running": "Running", "proposal_ready": "Proposal ready", "failed": "Failed",
        "error": "Failed", "blocked": "Blocked", "rejected": "Rejected",
        "applied": "Applied", "executed": "Executed",
    }
    steps = []
    for source in normalized_trace(state):
        step = dict(source)
        stage, status = step["stage"], str(step["status"]).lower()
        label = status_labels.get(status, status.replace("_", " ").capitalize())
        if stage == "diagnosis" and diagnosis:
            if diagnosis.get("issue_type"):
                label = str(diagnosis["issue_type"])
            elif diagnosis.get("recommended_action") == "needs_review":
                label = "Needs review"
            elif diagnosis.get("recommended_action") == "none":
                label = "No action required"
        elif stage == "optimization" and proposal.get("action"):
            action = str(proposal["action"])
            label = _ACTION_LABELS.get(action, action.replace("_", " "))
        elif stage == "approval":
            label = {
                "auto": "Auto-approved by policy", "pending": "Human Approval Required",
                "approved": "Human-approved", "rejected": "Rejected",
            }.get(gate["kind"], label)
        elif stage == "validation":
            if not labelled:
                reported = bool(validation) or status in {"completed", "complete", "improved", "same", "worse"}
                if reported:
                    step["status"] = "unvalidated"
                    label = "Not formally validated"
                else:
                    label = "Waiting" if status == "waiting" and not state.get("query") else "Not run"
            else:
                verdict = str(validation.get("verdict") or "").upper()
                label = {"IMPROVED": "Improved", "SAME": "No meaningful change", "WORSE": "Worse"}.get(verdict, label)
        if healthy:
            label = healthy_labels[stage]
            step["status"] = "completed" if stage in {"baseline", "monitoring", "diagnosis"} else "skipped"
        step.update({"label": label, "detail": ""})
        steps.append(step)
    return steps


def feedback_state(run: Any, *, labelled: bool) -> dict[str, str] | None:
    """Summarize a recorded terminal selection without choosing new evidence."""
    state = _state(run)
    final_status = str(state.get("final_status") or "").upper()
    if final_status not in _TERMINAL or _pending(state):
        return None
    validation = _mapping(state.get("validation_result"))
    recommendation = validation.get("recommendation")
    saved = state.get("verified") is True or state.get("mode") == "VERIFIED DEMO MODE"
    final_run = state.get("final_run")
    if saved and not isinstance(final_run, dict):
        if final_status == "IMPROVED" and recommendation == "ACCEPT_OPTIMIZED" and state.get("after_run"):
            return {"text": "Optimized retrieval accepted", "kind": "positive"} if labelled else None
        if final_status in {"SAME", "WORSE"} and recommendation == "RETAIN_BASELINE" and state.get("before_run"):
            return {"text": "Baseline retained", "kind": "neutral"}
        return None
    if not isinstance(final_run, dict):
        return None
    if healthy_baseline(state):
        return {"text": "Baseline retrieval accepted — no optimization required.", "kind": "positive"}
    if final_status == "IMPROVED" and recommendation == "ACCEPT_OPTIMIZED":
        return {"text": "Optimized retrieval accepted", "kind": "positive"} if labelled else None
    before = state.get("before_run")
    if isinstance(before, dict) and final_run != before:
        return None
    retained = final_status in {"NO_ACTION_REQUIRED", "NEEDS_REVIEW", "REJECTED"}
    retained = retained or (final_status in {"SAME", "WORSE"} and (
        recommendation == "RETAIN_BASELINE" or isinstance(before, dict) and final_run == before
    ))
    return {"text": "Baseline retained", "kind": "neutral"} if retained else None


def evidence_warning(run: Any, *, labelled: bool) -> str | None:
    """Use explicit evidence signals; raw distance scores are not thresholds."""
    state = _state(run)
    if labelled or not state:
        return None
    evidence = state.get("before_run") if _pending(state) else state.get("final_run")
    if not isinstance(evidence, dict):
        return None
    retrieved = evidence.get("retrieved_results")
    rows = [row for row in retrieved if isinstance(row, dict)] if isinstance(retrieved, (list, tuple)) else []
    monitoring = _mapping(state.get("monitoring_report"))
    platforms = {str(row["platform"]).strip().casefold() for row in rows if row.get("platform")}
    has_text = any(isinstance(row.get(key), str) and row[key].strip() for row in rows for key in ("text", "content", "page_content"))
    insufficient = not rows or not has_text or all(row.get("relevant") is False for row in rows)
    insufficient = insufficient or monitoring.get("chunking_signal") is True or monitoring.get("failure_detected") is True
    if insufficient or len(platforms) > 1:
        return "Retrieved evidence does not sufficiently support this query."
    return None


def structural_execution_available(workflow: Any) -> bool:
    """Inspect the configured callback without building a runtime or an index."""
    executor = getattr(workflow, "action_executor", None)
    return callable(getattr(executor, "rechunk_candidate", None))


def inspector_state(run: Any, *, labelled: bool) -> Any:
    """Detach and redact the inspector view; omit unsupported formal quality."""
    projection = safe_state(run)
    if labelled:
        return projection

    def strip(value: Any) -> Any:
        if isinstance(value, list):
            return [strip(item) for item in value]
        if not isinstance(value, dict):
            return value
        clean = {}
        for key, item in value.items():
            normalized = str(key).casefold().replace("-", "_")
            quality_key = normalized in {"recall", "precision", "reciprocal_rank", "mrr", "judge_score"}
            quality_key = quality_key or normalized.startswith(("recall_at_", "precision_at_")) or "first_relevant_rank" in normalized
            if quality_key or normalized in {"validation_result", "validation"}:
                continue
            if normalized in {"final_status", "verdict"} and str(item).upper() in _QUALITY_OUTCOMES:
                continue
            if normalized == "trace" and isinstance(item, list):
                clean[key] = [strip(event) for event in item if not isinstance(event, dict) or str(event.get("stage") or "").casefold() != "validation"]
            else:
                clean[key] = strip(item)
        return clean

    return strip(projection)
