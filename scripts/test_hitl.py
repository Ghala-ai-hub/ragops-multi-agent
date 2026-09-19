"""Tests for the RAGOps HITL approval gate."""

from scripts.hitl import request_human_approval

def sample_proposal():
    return {
        "issue_type": "Query Mismatch",
        "action": "rewrite_query",
        "parameters": {
            "original_query": "وش اسوي لو انتهت رخصتي حق بلدي",
            "new_query": "ما هي إجراءات تجديد رخصة بلدي المنتهية؟",
        },
        "reason": "Query wording does not align well with the knowledge base.",
        "expected_impact": "Improve relevant-document ranking.",
        "status": "pending_approval",
    }

def test_approve():
    result = request_human_approval(sample_proposal(), "approve")
    assert result["approval_status"] == "approved"
    assert result["execution_allowed"] is True
    assert result["next_step"] == "execute_approved_action"

def test_reject():
    result = request_human_approval(sample_proposal(), "reject")
    assert result["approval_status"] == "rejected"
    assert result["execution_allowed"] is False
    assert result["next_step"] == "retain_baseline"

def test_invalid_decision():
    try:
        request_human_approval(sample_proposal(), "maybe")
    except ValueError:
        return
    raise AssertionError("Invalid decision should raise ValueError")

if __name__ == "__main__":
    test_approve()
    test_reject()
    test_invalid_decision()
    print("HITL tests passed: APPROVE, REJECT, and invalid-decision scenarios.")
