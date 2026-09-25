"""Approved optimization action executor.

Execution is separate from diagnosis/proposal generation so that structural
changes cannot happen before approval. Re-chunking is intentionally callback-
based so integration can build a candidate index without overwriting the
active index.
"""
from __future__ import annotations

from typing import Any, Callable, Dict, Optional


RunCandidate = Callable[[str, int], Dict[str, Any]]
RewriteFunction = Callable[[str], str]
RechunkCandidate = Callable[[Dict[str, Any]], Dict[str, Any]]


class ApprovedActionExecutor:
    def __init__(
        self,
        *,
        run_candidate: RunCandidate,
        default_k: int = 4,
        rewrite_function: Optional[RewriteFunction] = None,
        rechunk_candidate: Optional[RechunkCandidate] = None,
    ) -> None:
        self.run_candidate = run_candidate
        self.default_k = default_k
        self.rewrite_function = rewrite_function
        self.rechunk_candidate = rechunk_candidate

    @staticmethod
    def _default_rewrite_function(original_query: str) -> str:
        try:
            from scripts.optimization_tools import rewrite_query
        except ModuleNotFoundError:
            from optimization_tools import rewrite_query
        return rewrite_query(original_query)

    def __call__(
        self,
        approved_proposal: Dict[str, Any],
    ) -> Dict[str, Any]:
        if approved_proposal.get("execution_allowed") is not True:
            raise PermissionError(
                "optimization execution is not approved"
            )

        action = approved_proposal.get("action")
        parameters = dict(
            approved_proposal.get("parameters") or {}
        )
        original_query = str(
            parameters.get("original_query", "")
        ).strip()
        baseline_k = int(
            parameters.get("baseline_k", self.default_k)
        )

        if not original_query:
            raise ValueError(
                "proposal is missing parameters.original_query"
            )

        if action == "change_top_k":
            new_k = int(parameters.get("new_k", baseline_k))
            after_run = self.run_candidate(original_query, new_k)
            action_result = {
                "status": "applied",
                "action": action,
                "applied_k": new_k,
            }

        elif action == "rewrite_query":
            rewritten_query = str(
                parameters.get("rewritten_query", "")
            ).strip()

            if not rewritten_query:
                rewrite_fn = (
                    self.rewrite_function
                    or self._default_rewrite_function
                )
                rewritten_query = rewrite_fn(original_query).strip()

            if not rewritten_query:
                raise ValueError(
                    "query rewrite produced an empty query"
                )

            after_run = self.run_candidate(
                rewritten_query, baseline_k
            )
            action_result = {
                "status": "applied",
                "action": action,
                "rewritten_query": rewritten_query,
                "applied_k": baseline_k,
            }

        elif action == "rechunk_and_reindex":
            if self.rechunk_candidate is None:
                raise RuntimeError(
                    "rechunk_and_reindex requires a "
                    "non-destructive candidate-index callback"
                )

            candidate_result = self.rechunk_candidate(parameters)

            if (
                not isinstance(candidate_result, dict)
                or not isinstance(
                    candidate_result.get("after_run"), dict
                )
            ):
                raise ValueError(
                    "rechunk_candidate must return "
                    "{'after_run': {...}}"
                )

            after_run = candidate_result["after_run"]
            action_result = {
                "status": "applied",
                "action": action,
                **dict(
                    candidate_result.get("action_result") or {}
                ),
            }

        else:
            raise ValueError(
                f"unsupported approved action: {action!r}"
            )

        return {
            "action_result": action_result,
            "after_run": after_run,
        }
