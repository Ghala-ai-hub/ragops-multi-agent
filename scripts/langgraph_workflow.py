"""LangGraph orchestration for the RAGOps multi-agent workflow.

This graph wraps the already-tested project components without replacing their
logic:

Monitoring -> Diagnosis -> Optimization -> Approval/HITL -> Execution ->
Validation

Low-impact actions continue automatically. High-impact structural actions
(rechunk_and_reindex) can pause with LangGraph interrupt() and resume after a
human decision.

The graph uses an in-memory checkpointer by default so native interrupts can be
resumed during local/demo runs.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, List, Optional, Protocol, TypedDict
from uuid import uuid4

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt

try:
    from scripts.hitl import (
        HIGH_IMPACT_ACTIONS,
        route_approval,
    )
    from scripts.validation_agent import ValidationAgent
except ModuleNotFoundError:
    from hitl import HIGH_IMPACT_ACTIONS, route_approval
    from validation_agent import ValidationAgent


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


class LangGraphRAGOpsState(TypedDict, total=False):
    query: str
    before_run: Dict[str, Any]
    expected_platform: Optional[str]
    expected_service: Optional[str]
    monitoring_kwargs: Dict[str, Any]
    monitoring_report: Dict[str, Any]
    diagnostic_probe: Dict[str, Any]
    diagnosis_report: Dict[str, Any]
    optimization_proposal: Dict[str, Any]
    human_decision: Optional[str]
    approval_result: Dict[str, Any]
    execution_result: Dict[str, Any]
    after_run: Dict[str, Any]
    validation_result: Dict[str, Any]
    final_run: Dict[str, Any]
    final_status: str
    trace: List[Dict[str, Any]]


class LangGraphRAGOps:
    def __init__(
        self,
        *,
        monitoring_agent: MonitoringComponent,
        diagnosis_agent: DiagnosisComponent,
        optimization_agent: OptimizationComponent,
        action_executor,
        validation_agent: Optional[ValidationAgent] = None,
        checkpointer=None,
    ) -> None:
        self.monitoring_agent = monitoring_agent
        self.diagnosis_agent = diagnosis_agent
        self.optimization_agent = optimization_agent
        self.action_executor = action_executor
        self.validation_agent = (
            validation_agent or ValidationAgent()
        )
        self.checkpointer = checkpointer or InMemorySaver()
        self.graph = self._build_graph()

    @staticmethod
    def _append_trace(
        state: LangGraphRAGOpsState,
        stage: str,
        status: str,
        details: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        trace = list(state.get("trace", []))
        trace.append(
            {
                "stage": stage,
                "status": status,
                "details": details or {},
            }
        )
        return trace

    def _monitoring_node(
        self,
        state: LangGraphRAGOpsState,
    ) -> Dict[str, Any]:
        report = state.get("monitoring_report")

        if report is None:
            kwargs = dict(
                state.get("monitoring_kwargs") or {}
            )
            report = (
                self.monitoring_agent
                .build_monitoring_report(
                    state["query"],
                    **kwargs,
                )
            )
        else:
            report = deepcopy(report)

        return {
            "monitoring_report": report,
            "trace": self._append_trace(
                state,
                "monitoring",
                "completed",
                {
                    "failure_detected": report.get(
                        "failure_detected"
                    )
                },
            ),
        }

    def _diagnosis_node(
        self,
        state: LangGraphRAGOpsState,
    ) -> Dict[str, Any]:
        report = state["monitoring_report"]
        probe = deepcopy(
            report.get("diagnostic_probe") or {}
        )

        supplied_rewrite = (
            state.get("monitoring_kwargs") or {}
        ).get("rewritten_query")
        if supplied_rewrite:
            probe.setdefault(
                "rewritten_query",
                supplied_rewrite,
            )

        diagnosis = self.diagnosis_agent.diagnose(
            report,
            probe,
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

        action = diagnosis.get("recommended_action")
        updates: Dict[str, Any] = {
            "diagnostic_probe": probe,
            "diagnosis_report": diagnosis,
            "trace": self._append_trace(
                state,
                "diagnosis",
                "completed",
                {
                    "issue_type": diagnosis.get(
                        "issue_type"
                    ),
                    "recommended_action": action,
                },
            ),
        }

        if action in (None, "none"):
            updates["final_status"] = (
                "NO_ACTION_REQUIRED"
            )
            updates["final_run"] = deepcopy(
                state["before_run"]
            )
        elif action == "needs_review":
            updates["final_status"] = "NEEDS_REVIEW"
            updates["final_run"] = deepcopy(
                state["before_run"]
            )

        return updates

    @staticmethod
    def _route_after_diagnosis(
        state: LangGraphRAGOpsState,
    ) -> str:
        action = state["diagnosis_report"].get(
            "recommended_action"
        )
        if action in (None, "none", "needs_review"):
            return "end"
        return "optimization"

    def _optimization_node(
        self,
        state: LangGraphRAGOpsState,
    ) -> Dict[str, Any]:
        proposal = self.optimization_agent.propose(
            state["diagnosis_report"]
        )
        return {
            "optimization_proposal": proposal,
            "trace": self._append_trace(
                state,
                "optimization",
                "proposal_ready",
                {"action": proposal.get("action")},
            ),
        }

    def _approval_node(
        self,
        state: LangGraphRAGOpsState,
    ) -> Dict[str, Any]:
        proposal = state["optimization_proposal"]
        action = proposal.get("action")
        decision = state.get("human_decision")

        if (
            action in HIGH_IMPACT_ACTIONS
            and decision is None
        ):
            human_response = interrupt(
                {
                    "type": "human_approval_required",
                    "action": action,
                    "issue_type": proposal.get(
                        "issue_type"
                    ),
                    "reason": proposal.get("reason"),
                    "parameters": proposal.get(
                        "parameters"
                    ),
                    "allowed_decisions": [
                        "approve",
                        "reject",
                    ],
                }
            )

            if isinstance(human_response, dict):
                decision = human_response.get(
                    "decision"
                )
            else:
                decision = human_response

        approval = route_approval(
            proposal,
            human_decision=decision,
        )

        return {
            "human_decision": decision,
            "approval_result": approval,
            "trace": self._append_trace(
                state,
                "approval",
                approval["approval_status"],
                {
                    "approval_mode": approval.get(
                        "approval_mode"
                    ),
                    "execution_allowed": approval.get(
                        "execution_allowed"
                    ),
                },
            ),
        }

    @staticmethod
    def _route_after_approval(
        state: LangGraphRAGOpsState,
    ) -> str:
        approval = state["approval_result"]

        if approval.get("execution_allowed") is True:
            return "execution"
        return "end"

    def _execution_node(
        self,
        state: LangGraphRAGOpsState,
    ) -> Dict[str, Any]:
        execution = self.action_executor(
            state["approval_result"]
        )

        if (
            not isinstance(execution, dict)
            or not isinstance(
                execution.get("after_run"),
                dict,
            )
        ):
            raise ValueError(
                "action_executor must return "
                "{'after_run': {...}}"
            )

        return {
            "execution_result": execution,
            "after_run": execution["after_run"],
            "trace": self._append_trace(
                state,
                "execution",
                "completed",
                {
                    "action": state[
                        "optimization_proposal"
                    ].get("action")
                },
            ),
        }

    def _validation_node(
        self,
        state: LangGraphRAGOpsState,
    ) -> Dict[str, Any]:
        validation = self.validation_agent.validate(
            state["before_run"],
            state["after_run"],
            expected_platform=state.get(
                "expected_platform"
            ),
            expected_service=state.get(
                "expected_service"
            ),
        )

        final_run = (
            deepcopy(state["after_run"])
            if validation["recommendation"]
            == "ACCEPT_OPTIMIZED"
            else deepcopy(state["before_run"])
        )

        return {
            "validation_result": validation,
            "final_status": validation["verdict"],
            "final_run": final_run,
            "trace": self._append_trace(
                state,
                "validation",
                "completed",
                {
                    "verdict": validation[
                        "verdict"
                    ],
                    "recommendation": validation[
                        "recommendation"
                    ],
                },
            ),
        }

    def _finalize_node(
        self,
        state: LangGraphRAGOpsState,
    ) -> Dict[str, Any]:
        if state.get("final_status"):
            return {}

        approval = state.get("approval_result") or {}
        status = approval.get("approval_status")

        if status == "rejected":
            final_status = "REJECTED"
        elif status == "pending_human_approval":
            final_status = "PENDING_HUMAN_APPROVAL"
        else:
            final_status = "NO_ACTION_REQUIRED"

        return {
            "final_status": final_status,
            "final_run": deepcopy(
                state["before_run"]
            ),
        }

    def _build_graph(self):
        builder = StateGraph(LangGraphRAGOpsState)

        builder.add_node(
            "monitoring",
            self._monitoring_node,
        )
        builder.add_node(
            "diagnosis",
            self._diagnosis_node,
        )
        builder.add_node(
            "optimization",
            self._optimization_node,
        )
        builder.add_node(
            "approval",
            self._approval_node,
        )
        builder.add_node(
            "execution",
            self._execution_node,
        )
        builder.add_node(
            "validation",
            self._validation_node,
        )
        builder.add_node(
            "finalize",
            self._finalize_node,
        )

        builder.add_edge(START, "monitoring")
        builder.add_edge("monitoring", "diagnosis")

        builder.add_conditional_edges(
            "diagnosis",
            self._route_after_diagnosis,
            {
                "optimization": "optimization",
                "end": "finalize",
            },
        )

        builder.add_edge(
            "optimization",
            "approval",
        )

        builder.add_conditional_edges(
            "approval",
            self._route_after_approval,
            {
                "execution": "execution",
                "end": "finalize",
            },
        )

        builder.add_edge(
            "execution",
            "validation",
        )
        builder.add_edge(
            "validation",
            END,
        )
        builder.add_edge(
            "finalize",
            END,
        )

        return builder.compile(
            checkpointer=self.checkpointer,
            name="ragops_multi_agent",
        )

    @staticmethod
    def config(
        thread_id: Optional[str] = None,
        *,
        tags: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        return {
            "configurable": {
                "thread_id": (
                    thread_id or str(uuid4())
                )
            },
            "tags": list(
                tags or ["ragops", "multi-agent"]
            ),
            "metadata": {
                "workflow": "ragops_multi_agent",
                "baseline_k": 4,
                **dict(metadata or {}),
            },
        }

    def invoke(
        self,
        state: LangGraphRAGOpsState,
        *,
        thread_id: Optional[str] = None,
    ):
        config = self.config(
            thread_id,
            metadata={
                "expected_platform": state.get(
                    "expected_platform"
                ),
                "expected_service": state.get(
                    "expected_service"
                ),
            },
        )
        return self.graph.invoke(state, config)

    def resume(
        self,
        decision: str,
        *,
        thread_id: str,
    ):
        config = self.config(thread_id)
        return self.graph.invoke(
            Command(resume=decision),
            config,
        )
