"""Pure frontend projections of reported backend state; no execution or I/O."""
from __future__ import annotations

import re
from typing import Any, Dict, List

LOW_IMPACT = {"rewrite_query", "change_top_k"}


def _state(run: Any = None) -> Dict[str, Any]:
    if not isinstance(run, dict):
        return {}
    state = run.get("state")
    return state if isinstance(state, dict) else run


def _mapping(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def approval_view(run: Any = None) -> Dict[str, Any]:
    """Human controls appear only for an explicit, pending structural gate."""
    state = _state(run)
    proposal = _mapping(state.get("optimization_proposal") or state.get("proposal"))
    approval = _mapping(state.get("approval_result") or state.get("approval"))
    interrupt_payloads = []
    interrupts = state.get("__interrupt__") or []
    if not isinstance(interrupts, (list, tuple)):
        interrupts = [interrupts]
    for entry in interrupts:
        payload = entry.get("value", entry) if isinstance(entry, dict) else getattr(entry, "value", None)
        if isinstance(payload, dict) and payload.get("type") == "human_approval_required":
            interrupt_payloads.append(payload)
    interrupted_action = next((item.get("action") for item in interrupt_payloads if item.get("action")), None)
    action = proposal.get("action") or approval.get("action") or interrupted_action
    status = str(approval.get("approval_status") or "").lower()
    final_status = str(state.get("final_status") or "").upper()
    saved = state.get("verified") is True or state.get("mode") == "VERIFIED DEMO MODE"
    approval_steps = [] if saved else [s for s in (state.get("trace") or []) if isinstance(s, dict) and s.get("stage") == "approval"]
    if not status and approval_steps:
        status = str(approval_steps[-1].get("status") or "").lower()
    decision = str(approval.get("human_decision") or state.get("human_decision") or "").lower()
    if action in LOW_IMPACT:
        auto_reported = status == "auto_approved" or (
            not status
            and str(approval.get("approval_mode") or "").lower() == "auto"
            and approval.get("execution_allowed") is True
        )
        return {"kind": "auto" if auto_reported else "neutral", "label": "Auto-approved by policy" if auto_reported else "Automatic policy · no human review", "requires_decision": False}
    if action != "rechunk_and_reindex":
        return {"kind": "neutral", "label": "No approval decision reported", "requires_decision": False}
    # Terminal decisions take precedence over a stale pending status.
    if status == "rejected" or decision == "reject" or final_status == "REJECTED":
        return {"kind": "rejected", "label": "Rejected · baseline retained", "requires_decision": False}
    if status == "approved" or decision == "approve":
        return {"kind": "approved", "label": "Approved by human", "requires_decision": False}
    execution = _mapping(state.get("execution_result") or state.get("execution"))
    action_result = _mapping(execution.get("action_result"))
    execution_status = str(action_result.get("status") or execution.get("status") or "").lower()
    if execution_status in {"applied", "completed", "executed"} or execution.get("after_run") or state.get("validation_result") or state.get("validation"):
        return {"kind": "neutral", "label": "Execution recorded · approval decision not reported", "requires_decision": False}
    interrupted = any(payload.get("action") == "rechunk_and_reindex" for payload in interrupt_payloads)
    pending = status in {"pending", "pending_human_approval"} or final_status == "PENDING_HUMAN_APPROVAL" or interrupted
    return {"kind": "pending" if pending else "neutral", "label": "Awaiting human approval" if pending else "Structural policy · decision not reported", "requires_decision": pending}


def normalized_trace(run: Any = None) -> List[Dict[str, Any]]:
    """Normalize each stage independently; never infer all stages from a verdict."""
    state = _state(run)
    saved = state.get("verified") is True or state.get("mode") == "VERIFIED DEMO MODE"
    # Saved stage presentation is grounded in the stored record fields, not an
    # adapter-generated event sequence that the artifact does not contain.
    trace = {} if saved else {str(s.get("stage")): s for s in (state.get("trace") or []) if isinstance(s, dict)}
    absent_status = "not_recorded" if saved else "waiting"
    approval = approval_view(state)
    final_status = str(state.get("final_status") or "").upper()
    definitions = [
        ("baseline", "Baseline RAG", "System", "before_run"),
        ("monitoring", "Monitoring", "Agent 01", "monitoring_report"),
        ("diagnosis", "Diagnosis", "Agent 02", "diagnosis_report"),
        ("optimization", "Optimization", "Agent 03", "optimization_proposal"),
        ("approval", "Risk Gate", "Control gate", "approval_result"),
        ("execution", "Action Executor", "System", "execution_result"),
        ("validation", "Validation", "Agent 04", "validation_result"),
    ]
    output = []
    for stage, name, role, field in definitions:
        reported = trace.get(stage, {})
        value = _mapping(state.get(field))
        status = str(reported.get("status") or absent_status).lower()
        detail = str(reported.get("detail") or "")
        if stage in {"baseline", "monitoring", "diagnosis"} and value and not reported:
            status = "completed"
        if stage == "optimization" and value and not reported:
            status = "proposal_ready"
        if stage == "approval":
            status = {"auto": "auto_approved", "pending": "pending_human_approval", "approved": "approved", "rejected": "rejected"}.get(approval["kind"], absent_status)
            detail = approval["label"]
        if stage == "execution":
            result = _mapping(value.get("action_result"))
            action_status = str(result.get("status") or value.get("status") or "").lower()
            if action_status in {"failed", "error", "rejected", "blocked", "skipped"}:
                status = action_status
            elif action_status in {"applied", "executed", "completed"} or value.get("after_run"):
                status = "completed"
        if stage == "validation" and str(value.get("verdict") or "").upper() in {"IMPROVED", "SAME", "WORSE"}:
            status = str(value["verdict"]).lower()
            detail = detail or str(value.get("recommendation") or "").replace("_", " ")
        if approval["kind"] == "rejected" and stage in {"execution", "validation"} and status == "waiting":
            status, detail = "skipped", "Baseline retained after rejection."
        if not detail and stage == "diagnosis" and value:
            detail = str(value.get("issue_type") or "")
        if not detail and stage == "optimization" and value:
            detail = str(value.get("action") or "").replace("_", " ")
        future_stage = stage in {"optimization", "approval", "execution", "validation"}
        execution_evidence = stage == "execution" and bool(state.get("after_run") or state.get("validation_result"))
        if final_status in {"NO_ACTION_REQUIRED", "NEEDS_REVIEW"} and future_stage and status == "waiting" and not reported and not value and not execution_evidence:
            status = "skipped"
            detail = "Backend outcome: " + final_status.replace("_", " ").lower() + "."
        step = {"stage": stage, "name": name, "role": role, "status": status, "detail": detail, "human": role == "Control gate" and approval["kind"] == "pending"}
        if status == "not_recorded":
            step["label"] = "Not recorded"
            if not detail:
                step["detail"] = "This stage is not included in the saved record."
        output.append(step)
    return output


_SECRET_KEYS = re.compile(r"(?:api[_-]?key|secret|password|passwd|credential|authorization|private[_-]?key|access[_-]?token|refresh[_-]?token|bearer|cookie)", re.I)
_SECRET_VALUE = re.compile(r"\bsk-[A-Za-z0-9_-]{12,}|\b(?:lsv2_[A-Za-z0-9_-]{12,})|\bBearer\s+[A-Za-z0-9._~+/-]+=*", re.I)


def safe_state(run: Any) -> Any:
    """Return a JSON-safe inspection projection without runtime handles or secrets."""
    if isinstance(run, dict):
        clean = {}
        for key, value in run.items():
            label = str(key)
            if label in {"workflow", "__interrupt__"}:
                continue
            if _SECRET_KEYS.search(label) or label.lower() in {"token", "env", "environment", "headers"}:
                clean[label] = "[redacted]"
            else:
                clean[label] = safe_state(value)
        return clean
    if isinstance(run, (list, tuple)):
        return [safe_state(item) for item in run]
    if isinstance(run, str):
        return _SECRET_VALUE.sub("[redacted]", run)
    if run is None or isinstance(run, (bool, int, float)):
        return run
    return "[runtime object omitted]"
