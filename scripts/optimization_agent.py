"""Optimization Agent for RAGOps.

This agent converts Diagnosis output into a structured optimization proposal.
It does not execute structural changes itself. Execution is handled by the
integration workflow after risk-based approval routing.
"""
from __future__ import annotations

from typing import Any, Dict


class OptimizationAgent:
    SUPPORTED_ACTIONS = {
        "Top-K": "change_top_k",
        "Query Mismatch": "rewrite_query",
        "Chunking Quality": "rechunk_and_reindex",
    }

    def propose(self, diagnosis_report: Dict[str, Any]) -> Dict[str, Any]:
        issue_type = diagnosis_report.get("issue_type")
        recommended_action = diagnosis_report.get("recommended_action")
        original_query = str(
            diagnosis_report.get("original_query", "")
        ).strip()

        if recommended_action in (None, "none", "needs_review"):
            return {
                "issue_type": issue_type,
                "action": recommended_action or "none",
                "status": "no_executable_action",
                "reason": diagnosis_report.get("reason", ""),
                "confidence": diagnosis_report.get("confidence"),
                "parameters": {
                    "original_query": original_query,
                    "baseline_k": int(
                        diagnosis_report.get("baseline_k", 4)
                    ),
                },
            }

        expected_action = self.SUPPORTED_ACTIONS.get(issue_type)
        if expected_action is None:
            raise ValueError(
                f"Unsupported diagnosis issue_type: {issue_type!r}"
            )

        if recommended_action != expected_action:
            raise ValueError(
                "Diagnosis action does not match issue type: "
                f"{issue_type!r} -> expected {expected_action!r}, "
                f"got {recommended_action!r}"
            )

        parameters: Dict[str, Any] = {
            "original_query": original_query,
            "baseline_k": int(
                diagnosis_report.get("baseline_k", 4)
            ),
        }

        if recommended_action == "change_top_k":
            parameters["new_k"] = int(
                diagnosis_report.get("recommended_k", 6)
            )

        elif recommended_action == "rewrite_query":
            if diagnosis_report.get("rewritten_query"):
                parameters["rewritten_query"] = str(
                    diagnosis_report["rewritten_query"]
                ).strip()

        elif recommended_action == "rechunk_and_reindex":
            parameters["chunk_size"] = int(
                diagnosis_report.get("new_chunk_size", 500)
            )
            parameters["chunk_overlap"] = int(
                diagnosis_report.get("new_chunk_overlap", 100)
            )

        return {
            "issue_type": issue_type,
            "action": recommended_action,
            "parameters": parameters,
            "reason": diagnosis_report.get("reason", ""),
            "confidence": diagnosis_report.get("confidence"),
            "status": "proposed",
        }

    def process_optimization(
        self,
        diagnosis_report: Dict[str, Any],
        user_approval: Any = None,
    ) -> Dict[str, Any]:
        """Backward-compatible adapter for older callers.

        The old implementation executed actions directly. The integration
        review intentionally changes this behavior: the Optimization Agent now
        proposes; HITL/auto-apply routing and execution happen downstream.
        """
        proposal = self.propose(diagnosis_report)
        proposal["legacy_user_approval_argument_ignored"] = (
            user_approval is not None
        )
        return proposal


if __name__ == "__main__":
    agent = OptimizationAgent()

    examples = [
        {
            "issue_type": "Top-K",
            "original_query": "مثال Top-K",
            "recommended_action": "change_top_k",
            "recommended_k": 6,
            "baseline_k": 4,
        },
        {
            "issue_type": "Query Mismatch",
            "original_query": "وش اسوي لو انتهت رخصتي حق بلدي",
            "recommended_action": "rewrite_query",
            "baseline_k": 4,
        },
        {
            "issue_type": "Chunking Quality",
            "original_query": "مثال جودة التقسيم",
            "recommended_action": "rechunk_and_reindex",
            "baseline_k": 4,
        },
    ]

    for report in examples:
        print(agent.propose(report))
