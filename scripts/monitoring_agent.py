"""
monitoring_agent.py
--------------------
Person 1, Part 2 deliverable: Monitoring Agent.

Scope (per the project architecture — Monitor -> Diagnose -> Optimize ->
Approve -> Validate): this module only OBSERVES and LOGS. It does not
diagnose root causes or propose fixes — that is the Diagnosis Agent's and
Optimization Agent's job, owned by other team members.

Two outputs, deliberately kept separate (per Person 2's confirmed interface)
====================================================================
1. `monitor_query()` -> `MonitoringLogEntry` (unchanged from before): the
   rich INTERNAL log, including the heuristic `signals` block
   (query_mismatch / retrieval_issue / chunking_issue). This is Person 1's
   own debugging/Top-K-experiment tool (still used by evaluation.py) and is
   NOT what Diagnosis Agent consumes.

2. `build_monitoring_report()` -> the `monitoring_report` dict Person 2
   confirmed as the Monitoring -> Diagnosis Agent CONTRACT (see
   `logs/diagnosis_reports.jsonl` and README "Monitoring -> Diagnosis
   Interface Contract"). It reports RAW RETRIEVAL EVIDENCE — ranks, whether
   a relevant result was found at baseline vs. expanded K, a chunking
   signal, the retrieved results themselves — and a plain `failure_detected`
   boolean. It deliberately does NOT include `query_mismatch` /
   `retrieval_issue` / `chunking_issue` as named fields, and it never sets
   an `issue_type`: classifying WHY something failed (Query Mismatch vs.
   Top-K vs. Chunking) is Diagnosis Agent's job, using this evidence as
   input. Internally it still computes the same heuristic signals (reused
   for `chunking_signal` and, only when no ground truth exists, for
   `failure_detected`) — but it hands over evidence, not a verdict.

What is actually measurable right now
======================================
This system has NO human-labeled relevance judgments in production and NO
click-through data. So the heuristic `signals` block is an explicitly
documented HEURISTIC, never a claim of "this answer is wrong" — see each
field's docstring below. The `monitoring_report`'s ground-truth-dependent
fields (`baseline_relevant_found`, `baseline_first_relevant_rank`,
`expanded_first_relevant_rank`) are computed ONLY when an
`expected_service_id` is supplied (currently only by evaluation.py's
offline test set, using the SAME service-level ground truth already
documented/scoped in evaluation.py) — in production, with no ground truth,
they are honestly `None`, never invented. See `build_monitoring_report()`'s
docstring for exactly how `failure_detected` differs between the two modes.

Signals implemented (internal, Section 1 above)
====================
1. query_mismatch   — top-1 retrieval similarity score falls below
                       QUERY_MISMATCH_THRESHOLD. Proxy for "nothing we
                       retrieved looks confidently related to the query".
2. retrieval_issue  — the top-K results span more than
                       MAX_EXPECTED_DISTINCT_SERVICES distinct Absher
                       services. Proxy for "Top-K is pulling in unrelated
                       services", i.e. a Top-K tuning problem.
3. chunking_issue   — any retrieved chunk is shorter than
                       MIN_HEALTHY_CHUNK_CHARS (looks fragmented) or the
                       same chunk_id appears twice in one result set
                       (indicates a store/index problem).

Log formats: JSON Lines.
  logs/monitoring_log.jsonl    <- MonitoringLogEntry (internal)
  logs/diagnosis_reports.jsonl <- monitoring_report (the contract)
"""

from __future__ import annotations

import json
import time
import traceback
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from retrieval import RetrievedChunk, VectorStore

BASE_DIR = Path(__file__).resolve().parent.parent
LOGS_DIR = BASE_DIR / "logs"

# --- tunable thresholds (documented assumptions, not learned) -------------
QUERY_MISMATCH_THRESHOLD = 0.12       # TF-IDF cosine score scale, see README
MAX_EXPECTED_DISTINCT_SERVICES = 2    # more than this among top-k => suspicious
MIN_HEALTHY_CHUNK_CHARS = 60          # below this, a chunk is likely a fragment

# --- Monitoring -> Diagnosis contract defaults -----------------------------
# baseline_k=3 ties directly to evaluation.py's own Top-K=3/5/7 experiment,
# which recommended K=3 (best precision, same recall as 5/7 — see README
# section 4). expanded_k=10 is the "look deeper" probe depth used only when
# baseline_k misses; the whole corpus is 38 chunks, so 10 is a meaningful
# deeper look without retrieving everything.
DEFAULT_BASELINE_K = 3
DEFAULT_EXPANDED_K = 10


@dataclass
class Signals:
    query_mismatch: bool
    query_mismatch_reason: Optional[str]
    retrieval_issue: bool
    retrieval_issue_reason: Optional[str]
    chunking_issue: bool
    chunking_issue_reason: Optional[str]


@dataclass
class MonitoringLogEntry:
    timestamp: str
    query: str
    top_k: int
    retrieved_chunks: List[str]
    retrieval_scores: List[float]
    source_documents: List[str]
    retrieved_service_ids: List[str]
    num_results: int
    latency_ms: float
    embedder_backend: str
    signals: Dict[str, Any]
    eval: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


def _compute_signals(query: str, results: List[RetrievedChunk]) -> Signals:
    if not results:
        return Signals(
            True, "no results returned by the retriever at all",
            True, "zero results for a non-empty query",
            False, None,
        )

    top_score = results[0].score
    query_mismatch = top_score < QUERY_MISMATCH_THRESHOLD
    mismatch_reason = (
        f"top-1 similarity {top_score:.3f} < threshold "
        f"{QUERY_MISMATCH_THRESHOLD}" if query_mismatch else None
    )

    distinct_services = {r.service_id for r in results}
    retrieval_issue = len(distinct_services) > MAX_EXPECTED_DISTINCT_SERVICES
    retrieval_reason = (
        f"top-{len(results)} results span {len(distinct_services)} distinct "
        f"services ({sorted(distinct_services)}), expected at most "
        f"{MAX_EXPECTED_DISTINCT_SERVICES}" if retrieval_issue else None
    )

    short_chunks = [r.chunk_id for r in results if len(r.text) < MIN_HEALTHY_CHUNK_CHARS]
    seen_ids = [r.chunk_id for r in results]
    dup_ids = {cid for cid in seen_ids if seen_ids.count(cid) > 1}
    chunking_issue = bool(short_chunks) or bool(dup_ids)
    reasons = []
    if short_chunks:
        reasons.append(f"fragment-length chunks retrieved: {short_chunks}")
    if dup_ids:
        reasons.append(f"duplicate chunk_id(s) in one result set: {sorted(dup_ids)}")
    chunking_reason = "; ".join(reasons) if reasons else None

    return Signals(
        query_mismatch, mismatch_reason,
        retrieval_issue, retrieval_reason,
        chunking_issue, chunking_reason,
    )


def _first_relevant_rank(results: List[RetrievedChunk], expected_service_id: str) -> Optional[int]:
    """Rank (1-indexed) of the first result whose service matches ground
    truth, or None if none of the given results match. "Relevant" here
    means SERVICE-level ground truth (the same coarse-but-objective ground
    truth evaluation.py already uses and documents) — not a verified
    chunk-level/passage-level judgment. This function invents nothing: it
    only runs when a caller supplies `expected_service_id` explicitly."""
    for r in results:
        if r.service_id == expected_service_id:
            return r.rank
    return None


class MonitoringAgent:
    def __init__(
        self,
        store: VectorStore,
        log_path: Path = LOGS_DIR / "monitoring_log.jsonl",
        diagnosis_report_log_path: Path = LOGS_DIR / "diagnosis_reports.jsonl",
    ):
        self.store = store
        self.log_path = log_path
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self.diagnosis_report_log_path = diagnosis_report_log_path
        self.diagnosis_report_log_path.parent.mkdir(parents=True, exist_ok=True)

    def monitor_query(
        self,
        query: str,
        top_k: int = 5,
        expected_service_id: Optional[str] = None,
    ) -> MonitoringLogEntry:
        """Run one query through the retriever, compute signals, append a
        log line, and return the structured entry. `expected_service_id` is
        ONLY supplied by evaluation.py's offline test set; production calls
        never pass it, so the `eval` block is None in real usage."""
        start = time.perf_counter()
        error_str: Optional[str] = None
        results: List[RetrievedChunk] = []
        try:
            results = self.store.search(query, top_k=top_k)
        except Exception:  # noqa: BLE001 - we want to log & continue, not crash
            error_str = traceback.format_exc(limit=3)
        latency_ms = (time.perf_counter() - start) * 1000

        if error_str is not None:
            signals = Signals(False, None, False, None, False, None)
        else:
            signals = _compute_signals(query, results)

        eval_block = None
        if expected_service_id is not None and error_str is None:
            top1_service = results[0].service_id if results else None
            expected_in_topk = expected_service_id in {r.service_id for r in results}
            eval_block = {
                "expected_service_id": expected_service_id,
                "top1_service_id": top1_service,
                "correct_top1": top1_service == expected_service_id,
                "expected_in_topk": expected_in_topk,
            }

        entry = MonitoringLogEntry(
            timestamp=datetime.now(timezone.utc).isoformat(),
            query=query,
            top_k=top_k,
            retrieved_chunks=[r.chunk_id for r in results],
            retrieval_scores=[round(r.score, 4) for r in results],
            source_documents=sorted({d for r in results for d in r.source_documents}),
            retrieved_service_ids=[r.service_id for r in results],
            num_results=len(results),
            latency_ms=round(latency_ms, 3),
            embedder_backend=self.store.embedder.name,
            signals=asdict(signals),
            eval=eval_block,
            error=error_str,
        )
        self._append_log(entry)
        return entry

    def _append_log(self, entry: MonitoringLogEntry) -> None:
        with self.log_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(asdict(entry), ensure_ascii=False) + "\n")

    def build_monitoring_report(
        self,
        query: str,
        baseline_k: int = DEFAULT_BASELINE_K,
        expanded_k: int = DEFAULT_EXPANDED_K,
        expected_service_id: Optional[str] = None,
        rewritten_query: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Produce the `monitoring_report` dict Person 2 confirmed as the
        Monitoring -> Diagnosis Agent contract, and append it to
        `logs/diagnosis_reports.jsonl`. This is EVIDENCE for Diagnosis
        Agent, not a diagnosis: it never sets an `issue_type` and never
        exposes the internal `query_mismatch`/`retrieval_issue`/
        `chunking_issue` signal names directly — Diagnosis Agent is meant to
        derive its own classification from the ranks/flags below.

        Ground-truth gating (per task instruction: "do not invent relevance
        in production"):
          - `expected_service_id=None` (the default; every production call)
            -> `baseline_relevant_found`, `baseline_first_relevant_rank`,
            `expanded_first_relevant_rank` are all `None`. There is no way
            to know what's "relevant" without ground truth, so none is
            invented. `failure_detected` instead falls back to the internal
            heuristic signals (query_mismatch OR retrieval_issue OR
            chunking_issue) — a "this looks worth investigating" flag, NOT
            a confirmed failure.
          - `expected_service_id=<service_id>` (only ever passed by
            evaluation.py, using the same service-level ground truth it
            already documents) -> those three fields are computed for real,
            and `failure_detected = not baseline_relevant_found` (a verified
            failure, not a heuristic guess).
          Callers can tell which mode produced a given report by checking
          whether `baseline_relevant_found is None`.

        `expanded_first_relevant_rank` is only probed for (an extra
        `expanded_k` retrieval call) when the baseline actually missed —
        running it after a baseline hit would be redundant and could
        misleadingly imply extra significance.

        `diagnostic_probe` (optional): only included if the CALLER supplies
        `rewritten_query` — an already-authored alternate phrasing.
        Monitoring Agent does not generate query rewrites itself (that is
        Optimization Agent's "Query Rewriting" tool, out of scope here); it
        only MEASURES the effect of a rewrite it's handed, by re-running the
        exact same retrieval mechanism with the alternate text. If no
        `rewritten_query` is given, `diagnostic_probe` is omitted from the
        report entirely rather than filled with an invented value.
        """
        start = time.perf_counter()
        baseline_results = self.store.search(query, top_k=baseline_k)
        latency_ms = (time.perf_counter() - start) * 1000

        internal_signals = _compute_signals(query, baseline_results)

        ground_truth_available = expected_service_id is not None
        baseline_relevant_found: Optional[bool] = None
        baseline_first_relevant_rank: Optional[int] = None
        expanded_first_relevant_rank: Optional[int] = None

        if ground_truth_available:
            baseline_first_relevant_rank = _first_relevant_rank(baseline_results, expected_service_id)
            baseline_relevant_found = baseline_first_relevant_rank is not None
            if not baseline_relevant_found:
                expanded_results = self.store.search(query, top_k=expanded_k)
                expanded_first_relevant_rank = _first_relevant_rank(expanded_results, expected_service_id)
            failure_detected = not baseline_relevant_found
        else:
            failure_detected = (
                internal_signals.query_mismatch
                or internal_signals.retrieval_issue
                or internal_signals.chunking_issue
            )

        diagnostic_probe: Optional[Dict[str, Any]] = None
        if rewritten_query:
            rewritten_results = self.store.search(rewritten_query, top_k=baseline_k)
            if ground_truth_available:
                rewritten_rank = _first_relevant_rank(rewritten_results, expected_service_id)
                if baseline_first_relevant_rank is None and rewritten_rank is not None:
                    improved = True
                elif rewritten_rank is None:
                    improved = False
                else:
                    improved = rewritten_rank < baseline_first_relevant_rank
                diagnostic_probe = {
                    "rewrite_probe_improved": improved,
                    "rewritten_first_relevant_rank": rewritten_rank,
                }
            else:
                # Executed honestly (real retrieval call with the given
                # rewrite), but without ground truth there is no way to
                # judge "improved" — say so rather than guessing.
                diagnostic_probe = {
                    "rewrite_probe_improved": None,
                    "rewritten_first_relevant_rank": None,
                    "note": "rewritten query was retrieved, but no ground "
                            "truth was supplied so improvement cannot be judged",
                }

        report: Dict[str, Any] = {
            "original_query": query,
            "baseline_k": baseline_k,
            "failure_detected": failure_detected,
            "baseline_relevant_found": baseline_relevant_found,
            "baseline_first_relevant_rank": baseline_first_relevant_rank,
            "expanded_first_relevant_rank": expanded_first_relevant_rank,
            "chunking_signal": internal_signals.chunking_issue,
            "retrieval_latency_ms": round(latency_ms, 3),
            "retrieved_results": [
                {
                    "rank": r.rank,
                    "platform": r.platform,
                    "service": r.service_id,
                    "source": r.source_file,
                    "chunk_index": r.chunk_index,
                }
                for r in baseline_results
            ],
        }
        if diagnostic_probe is not None:
            report["diagnostic_probe"] = diagnostic_probe

        self._append_diagnosis_report(report, internal_signals)
        return report

    def _append_diagnosis_report(self, report: Dict[str, Any], internal_signals: Signals) -> None:
        """Persist the contract report, envelope-wrapped with a timestamp
        and (clearly separated, per task instruction 7) the internal
        signals — NOT merged into the report body Diagnosis Agent reads."""
        envelope = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "monitoring_report": report,
            "internal_signals_not_part_of_contract": asdict(internal_signals),
        }
        with self.diagnosis_report_log_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(envelope, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    store = VectorStore.from_jsonl()
    agent = MonitoringAgent(store)

    print("=== monitor_query() — internal log (unchanged) ===")
    demo_queries = [
        "شروط تجديد رخصة القيادة",
        "كم سنة تجديد الاستمارة",
        "ما هو الطقس اليوم في الرياض",  # deliberately off-topic -> mismatch demo
    ]
    for q in demo_queries:
        entry = agent.monitor_query(q, top_k=5)
        print(f"Q: {q}")
        print(f"   top1_score={entry.retrieval_scores[0] if entry.retrieval_scores else None} "
              f"signals={entry.signals}")
    print(f"Logged {len(demo_queries)} entries to {agent.log_path}\n")

    print("=== build_monitoring_report() — the Diagnosis Agent contract ===")
    print("-- production mode (no ground truth; note the null fields) --")
    prod_report = agent.build_monitoring_report("شروط تجديد رخصة القيادة")
    print(json.dumps(prod_report, ensure_ascii=False, indent=2))

    print("\n-- evaluation mode (ground truth supplied; a real failing query) --")
    eval_report = agent.build_monitoring_report(
        "ابغى اجدد رخصتي كم تاخذ توصل لي",
        expected_service_id="driving_license_renewal",
    )
    print(json.dumps(eval_report, ensure_ascii=False, indent=2))
    print(f"\nLogged reports to {agent.diagnosis_report_log_path}")
