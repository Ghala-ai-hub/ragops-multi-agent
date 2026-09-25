"""Human-in-the-Loop routing for RAGOps.

Project policy:
- Low-impact: rewrite_query, safe change_top_k -> auto-apply + logging.
- High-impact: rechunk_and_reindex -> explicit human approval.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any, Dict, Optional


LOW_IMPACT_ACTIONS = {"rewrite_query", "change_top_k"}
HIGH_IMPACT_ACTIONS = {"rechunk_and_reindex"}
VALID_DECISIONS = {"approve", "reject"}


def route_approval(
    proposal: Dict[str, Any],
    human_decision: Optional[str] = None,
) -> Dict[str, Any]:
    if not isinstance(proposal, dict) or not proposal:
        raise ValueError("proposal must be a non-empty dictionary")

    result = deepcopy(proposal)
    action = result.get("action")
    result["reviewed_at"] = datetime.now(timezone.utc).isoformat()

    if action in LOW_IMPACT_ACTIONS:
        result["approval_mode"] = "auto"
        result["approval_status"] = "auto_approved"
        result["execution_allowed"] = True
        result["next_step"] = "execute_approved_action"
        return result

    if action not in HIGH_IMPACT_ACTIONS:
        raise ValueError(f"unsupported optimization action: {action!r}")

    result["approval_mode"] = "human"

    if human_decision is None:
        result["approval_status"] = "pending_human_approval"
        result["execution_allowed"] = False
        result["next_step"] = "await_human_decision"
        return result

    decision = str(human_decision).strip().lower()
    if decision not in VALID_DECISIONS:
        raise ValueError("human_decision must be 'approve' or 'reject'")

    result["human_decision"] = decision

    if decision == "approve":
        result["approval_status"] = "approved"
        result["execution_allowed"] = True
        result["next_step"] = "execute_approved_action"
    else:
        result["approval_status"] = "rejected"
        result["execution_allowed"] = False
        result["next_step"] = "retain_baseline"

    return result
