"""Human-in-the-Loop approval gate for RAGOps optimization proposals."""

from copy import deepcopy
from datetime import datetime, timezone

VALID_DECISIONS = {"approve", "reject"}

class HumanApprovalGate:
    @staticmethod
    def review(proposal: dict, decision: str) -> dict:
        if not isinstance(proposal, dict) or not proposal:
            raise ValueError("proposal must be a non-empty dictionary")

        decision = str(decision).strip().lower()
        if decision not in VALID_DECISIONS:
            raise ValueError("decision must be either 'approve' or 'reject'")

        result = deepcopy(proposal)
        result["human_decision"] = decision
        result["reviewed_at"] = datetime.now(timezone.utc).isoformat()

        if decision == "approve":
            result["approval_status"] = "approved"
            result["execution_allowed"] = True
            result["next_step"] = "execute_approved_action"
        else:
            result["approval_status"] = "rejected"
            result["execution_allowed"] = False
            result["next_step"] = "retain_baseline"

        return result

def request_human_approval(proposal: dict, decision: str) -> dict:
    return HumanApprovalGate.review(proposal, decision)
