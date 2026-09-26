"""Read-only projections of loaded evaluation records for frontend display.

These helpers do not run the backend, load files, or manufacture saved cases.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any


def _records(adapter: Any, attribute: str) -> list[dict[str, Any]]:
    artifact = getattr(adapter, attribute, None)
    rows = artifact.get("results", []) if isinstance(artifact, dict) else []
    return [row for row in rows if isinstance(row, dict)] if isinstance(rows, list) else []


def recorded_cases(adapter: Any) -> list[dict[str, Any]]:
    """List only cases that exist in the loaded workflow artifact."""
    cases = []
    for row in _records(adapter, "workflow"):
        if not row.get("id"):
            continue
        diagnosis = row.get("diagnosis") if isinstance(row.get("diagnosis"), dict) else {}
        platform, issue = row.get("platform"), diagnosis.get("issue_type")
        label = " · ".join(str(value) for value in (str(platform).title() if platform else None, issue) if value)
        cases.append({
            "id": row["id"], "label": label or str(row["id"]),
            "query": row.get("original_query"), "platform": platform,
            "service": row.get("service"), "query_type": row.get("query_type"),
            "issue": issue,
        })
    return deepcopy(cases)


def recorded_run(adapter: Any, case_id: str) -> dict[str, Any]:
    """Project one stored workflow record; unknown IDs raise ``KeyError``.

    The retrieval artifact supplies baseline documents. The workflow validation
    supplies recorded baseline measurements, including its actual latency.
    Missing fields stay absent; there is no synthetic structural workflow.
    """
    record = next((row for row in _records(adapter, "workflow") if row.get("id") == case_id), None)
    if record is None:
        raise KeyError(case_id)
    aliases = {
        "diagnosis": "diagnosis_report", "proposal": "optimization_proposal",
        "approval": "approval_result", "execution": "execution_result",
        "validation": "validation_result",
    }
    run = {aliases.get(key, key): deepcopy(value) for key, value in record.items()}
    run["case_id"] = record["id"]
    if "original_query" in record:
        run["query"] = deepcopy(record["original_query"])
    before = deepcopy(record.get("before_run")) if isinstance(record.get("before_run"), dict) else {}
    retrieval = next((row for row in _records(adapter, "retrieval") if row.get("id") == case_id), None)
    if retrieval is not None:
        for source, target in (("query", "query"), ("k", "top_k"), ("retrieved", "retrieved_results")):
            if source in retrieval:
                before.setdefault(target, deepcopy(retrieval[source]))
    validation = record.get("validation") if isinstance(record.get("validation"), dict) else {}
    if isinstance(validation.get("before"), dict):
        before.update(deepcopy(validation["before"]))
    if before:
        run["before_run"] = before
    execution = record.get("execution") if isinstance(record.get("execution"), dict) else {}
    if isinstance(execution.get("after_run"), dict):
        run["after_run"] = deepcopy(execution["after_run"])
    run.update({"verified": True, "mode": "VERIFIED DEMO MODE", "source_artifact": "real_failure_workflow_results.json"})
    return run
