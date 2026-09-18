"""
evaluation.py
-------------
Person 1 — Steps B (Query Mismatch) and C (Top-K Retrieval) + testing.

Everything here runs against the REAL 6-service corpus built from the
Absher source material (see data/raw/SOURCES_MANIFEST.md — updated
2026-09-16, all 6 originally-scoped services now have accessible official
sources). Every test query below was written by hand to reflect realistic
Absher user phrasing based on what is actually in that corpus — nothing
about Absher itself is invented, only the *phrasing* of hypothetical user
questions, which is exactly what the assignment asks for ("create realistic
Absher user queries"). The 8 queries for the 2 newly-added services (lost/
stolen plate report, firearm transport permit) follow the same style mix
and were added when those services' data became available; the original 16
queries for the other 4 services are unchanged.

Query styles covered (per query): direct, short/keyword, natural Saudi
colloquial, paraphrase of another query's intent, and deliberately ambiguous
(no single correct service).

What "expected" means here
===========================
For each non-ambiguous query we record `expected_service_id`: which Absher
service the query is actually about. This is a SERVICE-level ground truth
(coarse but objective and cheap to check by hand), not a chunk-level
ground truth — grading "is this the exact right chunk" would need either a
human-labeled rubric per chunk or an LLM-as-judge, neither of which this MVP
implements (noted as a follow-up for the Diagnosis Agent's richer eval).
Recall@K / Precision@K below are therefore computed at the service level.

Two backends, honestly labeled
================================
`run_full_evaluation()` always runs an explicit TF-IDF pass — labeled
`baseline_tfidf` — and separately attempts a `primary` pass through
`get_embedder()`'s default resolution (sentence-transformers as of this
revision). If sentence-transformers actually loads, `primary` gets its own
full Top-K sweep and its own log files. If it can't load in this
environment, `primary` is NOT silently filled in with the baseline numbers
under a new label — the JSON/console output says plainly
`"status": "not_run_fallback_to_tfidf"` with the real reason, and points
back at `baseline_tfidf` as the only numbers that actually exist. Threshold
constants in monitoring_agent.py were calibrated against TF-IDF's cosine
score distribution; if/when a real sentence-transformers pass runs, those
thresholds should be re-checked against its (typically higher) similarity
scores rather than assumed to transfer — that recalibration is intentionally
NOT guessed at here.
"""

from __future__ import annotations

import json
import statistics
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional

from embeddings import TfidfEmbedder, get_embedder
from monitoring_agent import MonitoringAgent
from retrieval import VectorStore

BASE_DIR = Path(__file__).resolve().parent.parent
PROCESSED_DIR = BASE_DIR / "data" / "processed"
LOGS_DIR = BASE_DIR / "logs"


@dataclass
class EvalQuery:
    query: str
    expected_service_id: Optional[str]  # None => deliberately ambiguous
    style: str
    note: str


EVAL_QUERIES: List[EvalQuery] = [
    # ---- Driving license renewal ----------------------------------------
    EvalQuery("ما هي شروط تجديد رخصة القيادة؟", "driving_license_renewal",
              "direct", "eligibility conditions"),
    EvalQuery("فحص طبي رخصة قيادة", "driving_license_renewal",
              "short_keyword", "medical exam requirement"),
    EvalQuery("ابغى اجدد رخصتي كم تاخذ توصل لي", "driving_license_renewal",
              "saudi_colloquial", "delivery time"),
    EvalQuery("عدد السنوات المسموح بها لتجديد رخصة القيادة",
              "driving_license_renewal", "paraphrase", "renewal duration options"),

    # ---- Vehicle registration renewal ------------------------------------
    EvalQuery("كيف احسب تاريخ انتهاء الاستمارة بعد التجديد؟",
              "vehicle_registration_renewal", "direct", "expiry date calc"),
    EvalQuery("شروط تجديد استمارة السيارة", "vehicle_registration_renewal",
              "short_keyword", "eligibility conditions"),
    EvalQuery("استمارة سيارتي خلصت ابي اجددها", "vehicle_registration_renewal",
              "saudi_colloquial", "expired registration renewal"),
    EvalQuery("متطلبات تجديد رخصة السير", "vehicle_registration_renewal",
              "paraphrase", "eligibility conditions (paraphrase of query #6)"),

    # ---- Exit/Reentry or Final Exit visa (FAQ-only service) --------------
    EvalQuery("هل لازم بصمة عشان اطلع تأشيرة خروج وعودة؟",
              "exit_reentry_final_exit_visa", "saudi_colloquial",
              "fingerprint requirement"),
    EvalQuery("تأشيرة خروج نهائي للتابعين", "exit_reentry_final_exit_visa",
              "short_keyword", "how to request for dependents"),
    EvalQuery("اقامتي منتهية اقدر اطلع تأشيرة خروج وعودة؟",
              "exit_reentry_final_exit_visa", "direct_colloquial",
              "expired residency permit"),

    # ---- Lost passport replacement ---------------------------------------
    EvalQuery("ضاع جوازي كيف أطلع بدل فاقد؟", "lost_passport_replacement",
              "saudi_colloquial", "how to request a replacement"),
    EvalQuery("هل يشترط الإبلاغ عن فقدان الجواز؟", "lost_passport_replacement",
              "direct", "loss report requirement"),
    EvalQuery("اصدار جواز لفرد من العائلة بدل الجواز المفقود",
              "lost_passport_replacement", "paraphrase",
              "issuing for a family member"),
    EvalQuery("هويتي منتهية ابي اصدر جواز بدل فاقد",
              "lost_passport_replacement", "direct_colloquial",
              "expired national ID blocker"),
    EvalQuery("كم تكلفة توصيل الجواز البديل", "lost_passport_replacement",
              "short_keyword", "delivery fee"),

    # ---- Report Stolen/Lost Vehicle Plate (new service, previously excluded) --
    EvalQuery("كيف أبلغ عن فقدان لوحة السيارة؟", "lost_stolen_plate_report",
              "direct", "how to report a lost/stolen plate"),
    EvalQuery("سرقة لوحة السيارة", "lost_stolen_plate_report",
              "short_keyword", "plate theft"),
    EvalQuery("ضاعت لوحة سيارتي كيف ابلغ عنها", "lost_stolen_plate_report",
              "saudi_colloquial", "lost plate, how to report"),
    EvalQuery("هل يمكن تقديم أكثر من بلاغ عن نفس المركبة؟",
              "lost_stolen_plate_report", "paraphrase",
              "duplicate-report rule (real FAQ in the new source)"),

    # ---- Firearm Transport Permit (new service, previously excluded) --------
    EvalQuery("ما هي رسوم إذن التنقل بالسلاح؟", "firearm_transport_permit",
              "direct", "transport permit fee"),
    EvalQuery("تصريح نقل سلاح", "firearm_transport_permit",
              "short_keyword", "weapon transport permit"),
    EvalQuery("ابي انقل سلاحي من مدينة لمدينة وش اسوي",
              "firearm_transport_permit", "saudi_colloquial",
              "moving a weapon between cities"),
    EvalQuery("هل يمكن حمل أكثر من سلاح بإذن واحد؟", "firearm_transport_permit",
              "paraphrase", "one-weapon-per-permit rule (real FAQ in the new source)"),

    # ---- Deliberately ambiguous queries (no single correct service) -----
    EvalQuery("رخصة", None, "ambiguous",
              "single word 'license' — matches driving license AND vehicle "
              "registration equally; there is no single correct answer"),
    EvalQuery("تجديد", None, "ambiguous",
              "single word 'renewal' — matches all 3 renewal-type services"),
]


def save_eval_queries(out_path: Path = PROCESSED_DIR / "eval_queries.jsonl") -> Path:
    with out_path.open("w", encoding="utf-8") as f:
        for q in EVAL_QUERIES:
            f.write(json.dumps(asdict(q), ensure_ascii=False) + "\n")
    return out_path


# --------------------------------------------------------------------------
# Top-K experiment
# --------------------------------------------------------------------------

def run_topk_experiment(store: VectorStore, log_prefix: str,
                         k_values: List[int] = (3, 5, 7)) -> Dict[str, dict]:
    """Run the Top-K sweep against an already-built `store` (so the caller
    controls exactly which embedding backend is in play — see
    `run_full_evaluation()` below, which calls this once for the explicit
    TF-IDF baseline and once for the "primary"/default-resolved backend)."""
    scored_queries = [q for q in EVAL_QUERIES if q.expected_service_id is not None]
    results: Dict[str, dict] = {}

    for k in k_values:
        recall_hits = 0
        precision_scores = []
        mismatch_flags = 0
        retrieval_issue_flags = 0
        per_query_rows = []

        # Fresh agent/log file per (backend, K) so each run is independently
        # inspectable and never overwrites or mixes with another backend's.
        agent = MonitoringAgent(store, log_path=LOGS_DIR / f"topk_experiment_{log_prefix}_k{k}.jsonl")

        for q in scored_queries:
            entry = agent.monitor_query(q.query, top_k=k, expected_service_id=q.expected_service_id)
            hit = entry.eval["expected_in_topk"] if entry.eval else False
            recall_hits += int(hit)
            match_count = sum(1 for sid in entry.retrieved_service_ids if sid == q.expected_service_id)
            precision = match_count / len(entry.retrieved_service_ids) if entry.retrieved_service_ids else 0.0
            precision_scores.append(precision)
            mismatch_flags += int(entry.signals["query_mismatch"])
            retrieval_issue_flags += int(entry.signals["retrieval_issue"])
            per_query_rows.append({
                "query": q.query, "style": q.style,
                "expected_service_id": q.expected_service_id,
                "top1_service_id": entry.eval["top1_service_id"] if entry.eval else None,
                "correct_top1": entry.eval["correct_top1"] if entry.eval else None,
                "expected_in_topk": hit,
                "precision_at_k": round(precision, 3),
                "top1_score": entry.retrieval_scores[0] if entry.retrieval_scores else None,
            })

        n = len(scored_queries)
        results[str(k)] = {
            "k": k,
            "n_queries": n,
            "recall_at_k": round(recall_hits / n, 3),
            "mean_precision_at_k": round(statistics.mean(precision_scores), 3),
            "query_mismatch_rate": round(mismatch_flags / n, 3),
            "retrieval_issue_rate": round(retrieval_issue_flags / n, 3),
            "per_query": per_query_rows,
        }
    return results


def recommend_k(results: Dict[str, dict]) -> str:
    """Pick the K with the best recall; break ties by higher mean precision
    (i.e. fewer wasted/irrelevant slots), then by the smaller K (cheaper /
    less noisy context for a downstream LLM). This mirrors the assignment's
    instruction: "not simply the largest K"."""
    ranked = sorted(
        results.values(),
        key=lambda r: (-r["recall_at_k"], -r["mean_precision_at_k"], r["k"]),
    )
    return str(ranked[0]["k"])


def print_topk_report(results: Dict[str, dict]) -> None:
    print(f"{'K':<4}{'Recall@K':<12}{'MeanPrecision@K':<18}{'QueryMismatch%':<16}{'Top-K issue %':<15}")
    for k, r in results.items():
        print(f"{k:<4}{r['recall_at_k']:<12}{r['mean_precision_at_k']:<18}"
              f"{r['query_mismatch_rate']:<16}{r['retrieval_issue_rate']:<15}")
    best = recommend_k(results)
    print(f"\nRecommended K: {best}")


def run_full_evaluation() -> Dict[str, dict]:
    save_eval_queries()

    # 1) Baseline: explicit TF-IDF. Always runs — fully offline, deterministic.
    baseline_store = VectorStore.from_jsonl(embedder=TfidfEmbedder())
    baseline_backend = baseline_store.backend_info()
    baseline_results = run_topk_experiment(baseline_store, log_prefix="baseline_tfidf")

    # 2) Primary: whatever get_embedder() resolves to by default (openai as
    #    of this revision, matching the project proposal's stated stack,
    #    unless it can't load — in which case get_embedder() itself already
    #    fell back one or two tiers, down to sentence-transformers or
    #    tfidf).
    primary_store = VectorStore.from_jsonl(embedder=get_embedder())
    primary_backend = primary_store.backend_info()

    output: Dict[str, Any] = {
        "baseline_tfidf": {
            "label": "TF-IDF baseline",
            "backend_info": baseline_backend,
            "results": baseline_results,
            "recommended_k": recommend_k(baseline_results),
        },
    }

    actual = primary_backend["actual_backend"]
    if actual == "openai":
        primary_results = run_topk_experiment(primary_store, log_prefix="primary_openai")
        output["primary"] = {
            "label": "OpenAI + FAISS (primary/default)",
            "status": "ran",
            "backend_info": primary_backend,
            "results": primary_results,
            "recommended_k": recommend_k(primary_results),
        }
    elif actual == "sentence-transformers":
        # openai unavailable, fell back one tier to a still-real semantic
        # backend — worth running and reporting, just not the FAISS path.
        primary_results = run_topk_experiment(primary_store, log_prefix="primary_sentence-transformers")
        output["primary"] = {
            "label": "Sentence Transformers (fallback from openai)",
            "status": "ran_as_fallback",
            "backend_info": primary_backend,
            "note": (
                f"openai was requested (default) but could not be loaded: "
                f"{primary_backend['fallback_reason']!r}. Fell back one tier "
                "to sentence-transformers, which DID load, so these are real "
                "semantic-retrieval results — just not FAISS-backed."
            ),
            "results": primary_results,
            "recommended_k": recommend_k(primary_results),
        }
    else:
        output["primary"] = {
            "label": "OpenAI + FAISS (primary/default) — NOT RUN",
            "status": "not_run_fallback_to_tfidf",
            "backend_info": primary_backend,
            "note": (
                "openai is the configured default (ABSHER_EMBEDDER=openai) "
                "but could not be loaded in this environment: "
                f"{primary_backend['fallback_reason']!r}. "
                "retrieval.get_embedder() already cascaded all the way down "
                "to TF-IDF automatically, so a 'primary' run here would be "
                "numerically identical to baseline_tfidf above under a "
                "misleading label -- it is deliberately NOT duplicated/"
                "relabeled as semantic-retrieval or FAISS results. Re-run "
                "`python src/evaluation.py` on a machine with "
                "OPENAI_API_KEY set, `pip install langchain-openai "
                "langchain-community faiss-cpu`, and network access to "
                "populate this section with real numbers."
            ),
            "results": None,
            "recommended_k": None,
        }

    out_path = PROCESSED_DIR / "topk_comparison.json"
    out_path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")

    print("=== BASELINE: TF-IDF ===")
    print_topk_report(baseline_results)

    print(f"\n=== PRIMARY: requested={primary_backend['requested_backend']!r} "
          f"actual={primary_backend['actual_backend']!r} ===")
    if output["primary"]["results"] is not None:
        print_topk_report(primary_results)
    else:
        print(output["primary"]["note"])

    print(f"\nFull comparison written to {out_path}")
    return output


# --------------------------------------------------------------------------
# Monitoring -> Diagnosis Agent contract: real-data demonstration
# --------------------------------------------------------------------------

# A hand-authored example rewrite for the diagnostic_probe demo below.
# IMPORTANT: this is a MANUALLY WRITTEN alternate phrasing, not something
# Monitoring Agent (or anything in this repo) generates automatically —
# automatic query rewriting is Optimization Agent's "Query Rewriting" tool,
# out of scope here. This only demonstrates that build_monitoring_report()
# can honestly MEASURE the effect of a rewrite it's handed.
_DIAGNOSTIC_PROBE_DEMO_QUERY = "ابغى اجدد رخصتي كم تاخذ توصل لي"
_DIAGNOSTIC_PROBE_DEMO_REWRITE = "ما هي المدة المتوقعة لتسليم رخصة القيادة الجديدة بعد التجديد؟"
_DIAGNOSTIC_PROBE_DEMO_SERVICE = "driving_license_renewal"


def generate_diagnosis_reports_sample(
    out_path: Path = PROCESSED_DIR / "diagnosis_reports_sample.json",
) -> Dict[str, Any]:
    """Run `MonitoringAgent.build_monitoring_report()` over the real
    EVAL_QUERIES (using their existing expected_service_id as ground truth —
    the same ground truth evaluation.py already uses elsewhere, nothing new
    invented) so the Monitoring -> Diagnosis contract is demonstrated
    against real retrieval evidence, not synthetic examples. Also runs the
    optional diagnostic_probe once, using the hand-authored rewrite above.
    """
    store = VectorStore.from_jsonl(embedder=TfidfEmbedder())
    agent = MonitoringAgent(store, diagnosis_report_log_path=LOGS_DIR / "diagnosis_reports.jsonl")

    scored_queries = [q for q in EVAL_QUERIES if q.expected_service_id is not None]
    reports = []
    for q in scored_queries:
        report = agent.build_monitoring_report(q.query, expected_service_id=q.expected_service_id)
        reports.append({"style": q.style, "note": q.note, "monitoring_report": report})

    # One demonstration of the optional diagnostic_probe, using a query that
    # actually failed baseline retrieval, paired with a manually authored
    # alternate phrasing (see constants above).
    probe_report = agent.build_monitoring_report(
        _DIAGNOSTIC_PROBE_DEMO_QUERY,
        expected_service_id=_DIAGNOSTIC_PROBE_DEMO_SERVICE,
        rewritten_query=_DIAGNOSTIC_PROBE_DEMO_REWRITE,
    )
    reports.append({
        "style": "diagnostic_probe_demo",
        "note": "manually authored rewrite, see _DIAGNOSTIC_PROBE_DEMO_REWRITE",
        "monitoring_report": probe_report,
    })

    n_failures = sum(1 for r in reports if r["monitoring_report"]["failure_detected"])
    summary = {
        "n_reports": len(reports),
        "n_failure_detected": n_failures,
        "reports": reports,
    }
    out_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\n=== Monitoring -> Diagnosis contract: {len(reports)} real reports "
          f"({n_failures} with failure_detected=true) ===")
    print(f"Written to {out_path} and appended to {agent.diagnosis_report_log_path}")
    print("\nDiagnostic probe demo:")
    print(json.dumps(probe_report, ensure_ascii=False, indent=2))
    return summary


if __name__ == "__main__":
    run_full_evaluation()
    generate_diagnosis_reports_sample()
