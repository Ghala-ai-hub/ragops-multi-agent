"""Evaluate a non-destructive re-chunk candidate against the baseline.

Builds a candidate FAISS index with the proposed chunking configuration
(default 500/100), evaluates the same 48-query dataset at K=4, and compares it
with the saved baseline retrieval results.

Important:
- The active baseline index is NOT overwritten.
- Candidate index is written under vector_store/candidates/.
- This is evidence for Validation/HITL, not an automatic promotion.
"""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List

from optimization_tools import rechunk_and_reindex


DATASET_PATH = Path("evaluation/dataset_v2.json")
BASELINE_RESULTS_PATH = Path(
    "evaluation/retrieval_results_v2.json"
)
OUTPUT_PATH = Path(
    "evaluation/rechunk_candidate_results.json"
)

K = 4
CHUNK_SIZE = 500
CHUNK_OVERLAP = 100


def average(values):
    return sum(values) / len(values) if values else 0.0


def evaluate_query(
    vector_store,
    item: Dict[str, Any],
) -> Dict[str, Any]:
    docs = vector_store.similarity_search(
        item["query"],
        k=K,
    )

    relevant_count = 0
    first_relevant_rank = None
    retrieved = []

    for rank, doc in enumerate(docs, start=1):
        metadata = dict(doc.metadata or {})
        relevant = (
            metadata.get("platform") == item["platform"]
            and metadata.get("service") == item["service"]
        )

        if relevant:
            relevant_count += 1
            if first_relevant_rank is None:
                first_relevant_rank = rank

        retrieved.append(
            {
                "rank": rank,
                "platform": metadata.get("platform"),
                "service": metadata.get("service"),
                "source": metadata.get("source"),
                "chunk_index": metadata.get("chunk_index"),
                "relevant": relevant,
            }
        )

    return {
        "id": item["id"],
        "platform": item["platform"],
        "service": item["service"],
        "query": item["query"],
        "query_type": item["query_type"],
        "k": K,
        "recall_at_k": 1.0 if relevant_count else 0.0,
        "precision_at_k": (
            relevant_count / len(docs) if docs else 0.0
        ),
        "reciprocal_rank": (
            1.0 / first_relevant_rank
            if first_relevant_rank is not None
            else 0.0
        ),
        "first_relevant_rank": first_relevant_rank,
        "retrieved": retrieved,
    }


def summarize(results: List[Dict[str, Any]]):
    summary = {
        "total_queries": len(results),
        "k": K,
        "overall": {
            "recall_at_k": average(
                [r["recall_at_k"] for r in results]
            ),
            "precision_at_k": average(
                [r["precision_at_k"] for r in results]
            ),
            "mrr": average(
                [r["reciprocal_rank"] for r in results]
            ),
        },
        "by_query_type": {},
        "by_platform": {},
    }

    by_type = defaultdict(list)
    by_platform = defaultdict(list)

    for result in results:
        by_type[result["query_type"]].append(result)
        by_platform[result["platform"]].append(result)

    for name, group in by_type.items():
        summary["by_query_type"][name] = {
            "count": len(group),
            "recall_at_k": average(
                [r["recall_at_k"] for r in group]
            ),
            "precision_at_k": average(
                [r["precision_at_k"] for r in group]
            ),
            "mrr": average(
                [r["reciprocal_rank"] for r in group]
            ),
        }

    for name, group in by_platform.items():
        summary["by_platform"][name] = {
            "count": len(group),
            "recall_at_k": average(
                [r["recall_at_k"] for r in group]
            ),
            "precision_at_k": average(
                [r["precision_at_k"] for r in group]
            ),
            "mrr": average(
                [r["reciprocal_rank"] for r in group]
            ),
        }

    return summary


def compare_query(
    baseline: Dict[str, Any],
    candidate: Dict[str, Any],
) -> str:
    before = (
        baseline["recall_at_k"],
        baseline["reciprocal_rank"],
        baseline["precision_at_k"],
    )
    after = (
        candidate["recall_at_k"],
        candidate["reciprocal_rank"],
        candidate["precision_at_k"],
    )

    if after > before:
        return "IMPROVED"
    if after < before:
        return "WORSE"
    return "SAME"


def main() -> None:
    dataset = json.loads(
        DATASET_PATH.read_text(encoding="utf-8")
    )
    baseline_payload = json.loads(
        BASELINE_RESULTS_PATH.read_text(
            encoding="utf-8"
        )
    )
    baseline_by_id = {
        item["id"]: item
        for item in baseline_payload["results"]
    }

    print(
        "Building NON-DESTRUCTIVE rechunk candidate "
        f"({CHUNK_SIZE}/{CHUNK_OVERLAP})..."
    )
    candidate = rechunk_and_reindex(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
    )

    vector_store = candidate["vector_store"]

    print(
        f"Candidate built: {candidate['chunks']} chunks "
        f"from {candidate['final_files']} files"
    )
    print(
        f"Candidate path: "
        f"{candidate['candidate_index_path']}"
    )
    print("=" * 90)

    results = []
    counts = {
        "IMPROVED": 0,
        "SAME": 0,
        "WORSE": 0,
    }

    for index, item in enumerate(dataset, start=1):
        result = evaluate_query(
            vector_store,
            item,
        )
        verdict = compare_query(
            baseline_by_id[item["id"]],
            result,
        )
        result["vs_baseline"] = verdict
        results.append(result)
        counts[verdict] += 1

        print(
            f"[{index:02d}/{len(dataset)}] "
            f"{item['id']} | "
            f"R@4={result['recall_at_k']:.2f} | "
            f"P@4={result['precision_at_k']:.2f} | "
            f"RR={result['reciprocal_rank']:.2f} | "
            f"{verdict}"
        )

    candidate_summary = summarize(results)
    baseline_summary = baseline_payload["summary"]

    delta = {
        "recall_at_k": (
            candidate_summary["overall"]["recall_at_k"]
            - baseline_summary["overall"]["recall_at_k"]
        ),
        "precision_at_k": (
            candidate_summary["overall"]["precision_at_k"]
            - baseline_summary["overall"]["precision_at_k"]
        ),
        "mrr": (
            candidate_summary["overall"]["mrr"]
            - baseline_summary["overall"]["mrr"]
        ),
    }

    output = {
        "configuration": {
            "k": K,
            "chunk_size": CHUNK_SIZE,
            "chunk_overlap": CHUNK_OVERLAP,
            "candidate_index_path": candidate[
                "candidate_index_path"
            ],
            "embedding_model": candidate[
                "embedding_model"
            ],
            "active_index_overwritten": False,
        },
        "baseline_summary": baseline_summary,
        "candidate_summary": candidate_summary,
        "overall_delta": delta,
        "per_query_verdict_counts": counts,
        "results": results,
    }

    OUTPUT_PATH.write_text(
        json.dumps(
            output,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print("\n" + "=" * 90)
    print("BASELINE VS RECHUNK CANDIDATE")
    print("=" * 90)
    print(
        "Baseline : "
        f"Recall@4={baseline_summary['overall']['recall_at_k']:.4f}, "
        f"Precision@4={baseline_summary['overall']['precision_at_k']:.4f}, "
        f"MRR={baseline_summary['overall']['mrr']:.4f}"
    )
    print(
        "Candidate: "
        f"Recall@4={candidate_summary['overall']['recall_at_k']:.4f}, "
        f"Precision@4={candidate_summary['overall']['precision_at_k']:.4f}, "
        f"MRR={candidate_summary['overall']['mrr']:.4f}"
    )
    print(
        "Delta    : "
        f"Recall@4={delta['recall_at_k']:+.4f}, "
        f"Precision@4={delta['precision_at_k']:+.4f}, "
        f"MRR={delta['mrr']:+.4f}"
    )
    print(
        "Per-query: "
        f"{counts['IMPROVED']} improved, "
        f"{counts['SAME']} same, "
        f"{counts['WORSE']} worse"
    )
    print(
        "Decision note: this candidate is NOT promoted automatically. "
        "Use these results as Validation/HITL evidence."
    )
    print(f"Saved to: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
