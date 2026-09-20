"""RAGOps integration workflow.

Shared flow:
Monitoring -> Diagnosis -> Optimization Proposal -> Risk Gate ->
Execution -> Validation.

Low-impact actions auto-apply. Structural corpus/index changes require HITL.
LangGraph can later wrap these same contracts as graph nodes without changing
the agent interfaces.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any, Callable, Dict, List, Optional, Protocol, TypedDict

from scripts.hitl import route_approval
from scripts.validation_agent import ValidationAgent


class MonitoringComponent(Protocol):
    def build_monitoring_report(
        self,
        query: str,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        ...


class DiagnosisComponent(Protocol):
    def diagnose(
        self,
        monitoring_report: Dict[str, Any],
        diagnostic_probe: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        ...


class OptimizationComponent(Protocol):
    def propose(
        self,
        diagnosis_report: Dict[str, Any],
    ) -> Dict[str, Any]:
        ...


class RAGOpsState(TypedDict, total=False):
    query: str
    expected_platform: Optional[str]
    expected_service: Optional[str]
    monitoring_report: Dict[str, Any]
    diagnostic_probe: Dict[str, Any]
    diagnosis_report: Dict[str, Any]
    optimization_proposal: Dict[str, Any]
    approval_result: Dict[str, Any]
    execution_result: Dict[str, Any]
    before_run: Dict[str, Any]
    after_run: Dict[str, Any]
    validation_result: Dict[str, Any]
    final_run: Dict[str, Any]
    final_status: str
    trace: List[Dict[str, Any]]


ProposalBuilder = Callable[[Dict[str, Any]], Dict[str, Any]]
ActionExecutor = Callable[[Dict[str, Any]], Dict[str, Any]]


_EXPECTED_IMPACT = {
    "change_top_k": (
        "Retrieve relevant evidence that currently falls "
        "outside the baseline cutoff."
    ),
    "rewrite_query": (
        "Improve alignment between natural user wording "
        "and official knowledge-base terminology."
    ),
    "rechunk_and_reindex": (
        "Improve context completeness and chunk boundaries."
    ),
}


def build_optimization_proposal(
    diagnosis_report: Dict[str, Any],
) -> Dict[str, Any]:
    """Temporary adapter until Person 3's OptimizationAgent is refactored
    to expose the same proposal contract."""
    action = diagnosis_report.get("recommended_action")

    if action in (None, "none", "needs_review"):
        raise ValueError(
            "diagnosis has no executable recommendation"
        )

    parameters: Dict[str, Any] = {
        "original_query": diagnosis_report.get(
            "original_query", ""
        ),
        "baseline_k": int(
            diagnosis_report.get("baseline_k", 4)
        ),
    }

    if (
        action == "rewrite_query"
        and diagnosis_report.get("rewritten_query")
    ):
        parameters["rewritten_query"] = (
            diagnosis_report["rewritten_query"]
        )

    if action == "change_top_k":
        parameters["new_k"] = int(
            diagnosis_report.get("recommended_k", 6)
        )

    elif action == "rechunk_and_reindex":
        parameters["chunk_size"] = int(
            diagnosis_report.get("new_chunk_size", 500)
        )
        parameters["chunk_overlap"] = int(
            diagnosis_report.get("new_chunk_overlap", 100)
        )

    return {
        "issue_type": diagnosis_report.get("issue_type"),
        "action": action,
        "parameters": parameters,
        "reason": diagnosis_report.get("reason", ""),
        "confidence": diagnosis_report.get("confidence"),
        "expected_impact": _EXPECTED_IMPACT.get(
            action,
            "Measure impact before accepting the change.",
        ),
        "status": "proposed",
    }


class RAGOpsWorkflow:
    def __init__(
        self,
        *,
        diagnosis_agent: DiagnosisComponent,
        monitoring_agent: Optional[MonitoringComponent] = None,
        optimization_agent: Optional[OptimizationComponent] = None,
        action_executor: Optional[ActionExecutor] = None,
        validation_agent: Optional[ValidationAgent] = None,
        proposal_builder: ProposalBuilder = build_optimization_proposal,
    ) -> None:
        self.monitoring_agent = monitoring_agent
        self.diagnosis_agent = diagnosis_agent
        self.optimization_agent = optimization_agent
        self.action_executor = action_executor
        self.validation_agent = (
            validation_agent or ValidationAgent()
        )
        self.proposal_builder = proposal_builder

    @staticmethod
    def _record(
        state: RAGOpsState,
        stage: str,
        status: str,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        state.setdefault("trace", []).append(
            {
                "stage": stage,
                "status": status,
                "details": details or {},
            }
        )

    def run(
        self,
        *,
        query: str,
        before_run: Dict[str, Any],
        human_decision: Optional[str] = None,
        expected_platform: Optional[str] = None,
        expected_service: Optional[str] = None,
        monitoring_report: Optional[Dict[str, Any]] = None,
        diagnostic_probe: Optional[Dict[str, Any]] = None,
        monitoring_kwargs: Optional[Dict[str, Any]] = None,
    ) -> RAGOpsState:
        if not query.strip():
            raise ValueError("query must not be empty")

        if not isinstance(before_run, dict):
            raise ValueError(
                "before_run must be a dictionary"
            )

        state: RAGOpsState = {
            "query": query,
            "before_run": deepcopy(before_run),
            "expected_platform": expected_platform,
            "expected_service": expected_service,
            "trace": [],
        }

        # 1) Monitoring
        if monitoring_report is None:
            if self.monitoring_agent is None:
                raise ValueError(
                    "monitoring_agent is required when no "
                    "monitoring_report is supplied"
                )
            kwargs = dict(monitoring_kwargs or {})
            report = self.monitoring_agent.build_monitoring_report(
                query, **kwargs
            )
        else:
            report = deepcopy(monitoring_report)

        state["monitoring_report"] = report
        self._record(
            state,
            "monitoring",
            "completed",
            {
                "failure_detected": report.get(
                    "failure_detected"
                )
            },
        )

        # 2) Diagnosis
        probe = deepcopy(
            diagnostic_probe
            or report.get("diagnostic_probe")
            or {}
        )
        supplied_rewrite = (
            monitoring_kwargs or {}
        ).get("rewritten_query")

        if supplied_rewrite:
            probe.setdefault(
                "rewritten_query", supplied_rewrite
            )

        state["diagnostic_probe"] = probe

        diagnosis = self.diagnosis_agent.diagnose(
            report, probe
        )
        diagnosis.setdefault(
            "baseline_k",
            int(report.get("baseline_k", 4)),
        )

        if (
            diagnosis.get("recommended_action")
            == "rewrite_query"
            and probe.get("rewritten_query")
        ):
            diagnosis.setdefault(
                "rewritten_query",
                probe["rewritten_query"],
            )

        state["diagnosis_report"] = diagnosis
        self._record(
            state,
            "diagnosis",
            "completed",
            {
                "issue_type": diagnosis.get("issue_type"),
                "recommended_action": diagnosis.get(
                    "recommended_action"
                ),
            },
        )

        recommended_action = diagnosis.get(
            "recommended_action"
        )

        if recommended_action in (None, "none"):
            state["final_status"] = "NO_ACTION_REQUIRED"
            state["final_run"] = deepcopy(before_run)
            return state

        if recommended_action == "needs_review":
            state["final_status"] = "NEEDS_REVIEW"
            state["final_run"] = deepcopy(before_run)
            return state

        # 3) Optimization proposal
        if self.optimization_agent is not None:
            proposal = self.optimization_agent.propose(
                diagnosis
            )
        else:
            proposal = self.proposal_builder(diagnosis)

        state["optimization_proposal"] = proposal
        self._record(
            state,
            "optimization",
            "proposal_ready",
            {"action": proposal.get("action")},
        )

        # 4) Risk-based approval routing
        approval = route_approval(
            proposal,
            human_decision=human_decision,
        )
        state["approval_result"] = approval
        self._record(
            state,
            "approval",
            approval["approval_status"],
            {
                "approval_mode": approval.get(
                    "approval_mode"
                ),
                "execution_allowed": approval[
                    "execution_allowed"
                ],
            },
        )

        if (
            approval["approval_status"]
            == "pending_human_approval"
        ):
            state["final_status"] = (
                "PENDING_HUMAN_APPROVAL"
            )
            state["final_run"] = deepcopy(before_run)
            return state

        if not approval["execution_allowed"]:
            state["final_status"] = "REJECTED"
            state["final_run"] = deepcopy(before_run)
            return state

        # 5) Execute approved/auto-approved action
        if self.action_executor is None:
            raise ValueError(
                "action_executor is required to execute "
                "an optimization"
            )

        execution_result = self.action_executor(approval)

        if (
            not isinstance(execution_result, dict)
            or not isinstance(
                execution_result.get("after_run"), dict
            )
        ):
            raise ValueError(
                "action_executor must return "
                "{'after_run': {...}}"
            )

        state["execution_result"] = execution_result
        state["after_run"] = execution_result["after_run"]

        self._record(
            state,
            "execution",
            "completed",
            {"action": proposal.get("action")},
        )

        # 6) Validate BEFORE vs AFTER
        validation = self.validation_agent.validate(
            before_run,
            state["after_run"],
            expected_platform=expected_platform,
            expected_service=expected_service,
        )

        state["validation_result"] = validation
        state["final_status"] = validation["verdict"]

        state["final_run"] = (
            deepcopy(state["after_run"])
            if validation["recommendation"]
            == "ACCEPT_OPTIMIZED"
            else deepcopy(before_run)
        )

        self._record(
            state,
            "validation",
            "completed",
            {
                "verdict": validation["verdict"],
                "recommendation": validation[
                    "recommendation"
                ],
            },
        )

        return state
