"""RAGOps integration workflow.

This module connects the functional stages through one shared state:
Monitoring -> Diagnosis -> Optimization Proposal -> HITL -> Execution -> Validation.

The workflow is dependency-injected on purpose. Each team-owned component can be
plugged in without rewriting its internal implementation, while this module owns
the handoffs, approval routing, execution contract, trace, and final verdict.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any, Callable, Dict, List, Optional, Protocol, TypedDict

from scripts.hitl import request_human_approval
from scripts.validation_agent import ValidationAgent


class MonitoringComponent(Protocol):
    def build_monitoring_report(self, query: str, **kwargs: Any) -> Dict[str, Any]: ...


class DiagnosisComponent(Protocol):
    def diagnose(
        self,
        monitoring_report: Dict[str, Any],
        diagnostic_probe: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]: ...


class RAGOpsState(TypedDict, total=False):
    query: str
    expected_platform: Optional[str]
    expected_service: Optional[str]
    monitoring_report: Dict[str, Any]
    diagnostic_probe: Dict[str, Any]
    diagnosis_report: Dict[str, Any]
    optimization_proposal: Dict[str, Any]
    human_decision: str
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
    "change_top_k": "Retrieve relevant evidence that currently falls outside the cutoff.",
    "rewrite_query": "Improve alignment between user wording and knowledge-base terminology.",
    "rechunk_and_reindex": "Improve context completeness and chunk boundaries.",
}


def build_optimization_proposal(diagnosis_report: Dict[str, Any]) -> Dict[str, Any]:
    """Convert Diagnosis output into a structured, non-executing proposal."""
    action = diagnosis_report.get("recommended_action")
    if action in (None, "none", "needs_review"):
        raise ValueError("Diagnosis report does not contain an executable recommendation")

    parameters: Dict[str, Any] = {
        "original_query": diagnosis_report.get("original_query", ""),
        "baseline_k": int(diagnosis_report.get("baseline_k", 3)),
    }
    if action == "rewrite_query" and diagnosis_report.get("rewritten_query"):
        parameters["rewritten_query"] = diagnosis_report["rewritten_query"]
    if action == "change_top_k":
        parameters["new_k"] = int(diagnosis_report.get("recommended_k", 6))
    elif action == "rechunk_and_reindex":
        parameters["chunk_size"] = int(diagnosis_report.get("new_chunk_size", 500))
        parameters["chunk_overlap"] = int(diagnosis_report.get("new_chunk_overlap", 100))

    return {
        "issue_type": diagnosis_report.get("issue_type"),
        "action": action,
        "parameters": parameters,
        "reason": diagnosis_report.get("reason", ""),
        "confidence": diagnosis_report.get("confidence"),
        "expected_impact": _EXPECTED_IMPACT.get(action, "Measure the impact before accepting the change."),
        "status": "pending_approval",
    }


class RAGOpsWorkflow:
    """Framework-neutral orchestrator for the project's shared workflow.

    `action_executor` must execute an approved proposal, rerun the candidate RAG,
    and return `{"after_run": {...}}`. Keeping this contract explicit prevents
    the Optimization Agent from executing before human approval.
    """

    def __init__(
        self,
        *,
        diagnosis_agent: DiagnosisComponent,
        monitoring_agent: Optional[MonitoringComponent] = None,
        action_executor: Optional[ActionExecutor] = None,
        validation_agent: Optional[ValidationAgent] = None,
        proposal_builder: ProposalBuilder = build_optimization_proposal,
    ) -> None:
        self.monitoring_agent = monitoring_agent
        self.diagnosis_agent = diagnosis_agent
        self.action_executor = action_executor
        self.validation_agent = validation_agent or ValidationAgent()
        self.proposal_builder = proposal_builder

    @staticmethod
    def _record(
        state: RAGOpsState,
        stage: str,
        status: str,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        state.setdefault("trace", []).append(
            {"stage": stage, "status": status, "details": details or {}}
        )

    def run(
        self,
        *,
        query: str,
        human_decision: str,
        before_run: Dict[str, Any],
        expected_platform: Optional[str] = None,
        expected_service: Optional[str] = None,
        monitoring_report: Optional[Dict[str, Any]] = None,
        diagnostic_probe: Optional[Dict[str, Any]] = None,
        monitoring_kwargs: Optional[Dict[str, Any]] = None,
    ) -> RAGOpsState:
        if not query.strip():
            raise ValueError("query must not be empty")
        if not isinstance(before_run, dict):
            raise ValueError("before_run must be a dictionary")

        state: RAGOpsState = {
            "query": query,
            "human_decision": human_decision,
            "before_run": deepcopy(before_run),
            "expected_platform": expected_platform,
            "expected_service": expected_service,
            "trace": [],
        }

        # 1) Monitoring
        if monitoring_report is None:
            if self.monitoring_agent is None:
                raise ValueError(
                    "monitoring_agent is required when monitoring_report is not supplied"
                )
            kwargs = dict(monitoring_kwargs or {})
            report = self.monitoring_agent.build_monitoring_report(query, **kwargs)
        else:
            report = deepcopy(monitoring_report)
        state["monitoring_report"] = report
        self._record(state, "monitoring", "completed", {"failure_detected": report.get("failure_detected")})

        # 2) Diagnosis
        probe = deepcopy(diagnostic_probe or report.get("diagnostic_probe") or {})
        supplied_rewrite = (monitoring_kwargs or {}).get("rewritten_query")
        if supplied_rewrite:
            probe.setdefault("rewritten_query", supplied_rewrite)
        state["diagnostic_probe"] = probe
        diagnosis = self.diagnosis_agent.diagnose(report, probe)
        diagnosis.setdefault("baseline_k", int(report.get("baseline_k", 3)))
        if diagnosis.get("recommended_action") == "rewrite_query" and probe.get("rewritten_query"):
            diagnosis.setdefault("rewritten_query", probe["rewritten_query"])
        state["diagnosis_report"] = diagnosis
        self._record(
            state,
            "diagnosis",
            "completed",
            {"issue_type": diagnosis.get("issue_type"), "recommended_action": diagnosis.get("recommended_action")},
        )

        recommended_action = diagnosis.get("recommended_action")
        if recommended_action in (None, "none"):
            state["final_status"] = "NO_ACTION_REQUIRED"
            state["final_run"] = deepcopy(before_run)
            self._record(state, "workflow", "completed", {"reason": "healthy baseline"})
            return state
        if recommended_action == "needs_review":
            state["final_status"] = "NEEDS_REVIEW"
            state["final_run"] = deepcopy(before_run)
            self._record(state, "workflow", "paused", {"reason": diagnosis.get("reason", "")})
            return state

        # 3) Optimization proposal (proposal only; no execution here)
        proposal = self.proposal_builder(diagnosis)
        state["optimization_proposal"] = proposal
        self._record(state, "optimization", "proposal_ready", {"action": proposal.get("action")})

        # 4) Human approval gate
        approval = request_human_approval(proposal, human_decision)
        state["approval_result"] = approval
        self._record(
            state,
            "human_approval",
            approval["approval_status"],
            {"execution_allowed": approval["execution_allowed"]},
        )

        if not approval["execution_allowed"]:
            state["final_status"] = "REJECTED"
            state["final_run"] = deepcopy(before_run)
            self._record(state, "workflow", "completed", {"result": "baseline retained"})
            return state

        # 5) Approved action executor + candidate rerun
        if self.action_executor is None:
            raise ValueError("action_executor is required for an approved proposal")
        execution_result = self.action_executor(approval)
        if not isinstance(execution_result, dict) or not isinstance(
            execution_result.get("after_run"), dict
        ):
            raise ValueError("action_executor must return a dictionary containing 'after_run'")

        state["execution_result"] = execution_result
        state["after_run"] = execution_result["after_run"]
        self._record(state, "execution", "completed", {"action": proposal.get("action")})

        # 6) Validation before accepting the candidate configuration
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
            if validation["recommendation"] == "ACCEPT_OPTIMIZED"
            else deepcopy(before_run)
        )
        self._record(
            state,
            "validation",
            "completed",
            {
                "verdict": validation["verdict"],
                "recommendation": validation["recommendation"],
            },
        )
        return state
