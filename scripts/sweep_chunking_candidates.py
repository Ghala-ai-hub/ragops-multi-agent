"""Sweep several non-destructive chunking candidates against the baseline.

The baseline remains fixed at 1000/200 and K=4. Each candidate is built under
vector_store/candidates/, evaluated on the same 48-query dataset, and compared
using the project's retrieval-first priority:

1) Recall@4
2) MRR
3) Precision@4

No candidate is promoted automatically.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Tuple

from optimization_tools import rechunk_and_reindex


DATASET_PATH = Path("evaluation/dataset_v2.json")
BASELINE_RESULTS_PATH = Path(
    "evaluation/retrieval_results_v2.json"
)
OUTPUT_PATH = Path(
    "evaluation/chunking_sweep_results.json"
)

K = 4
CANDIDATES: List[Tuple[int, int]] = [
    (750, 150),
    (1250, 250),
    (1500, 300),
]


def average(values):
    return sum(values) / len(values) if values else 0.0


def evaluate_candidate(
    vector_store,
    dataset: List[Dict[str, Any]],
):
    results = []

    for item in dataset:
        docs = vector_store.similarity_search(
            item["query"],
            k=K,
        )

        relevant_count = 0
        first_relevant_rank = None

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

        results.append(
            {
                "id": item["id"],
                "recall_at_k": (
                    1.0 if relevant_count else 0.0
                ),
                "precision_at_k": (
                    relevant_count / len(docs)
                    if docs else 0.0
                ),
                "reciprocal_rank": (
                    1.0 / first_relevant_rank
                    if first_relevant_rank is not None
                    else 0.0
                ),
            }
        )

    return {
        "recall_at_k": average(
            [r["recall_at_k"] for r in results]
        ),
        "precision_at_k": average(
            [r["precision_at_k"] for r in results]
        ),
        "mrr": average(
            [r["reciprocal_rank"] for r in results]
        ),
    }


def compare_to_baseline(
    baseline: Dict[str, float],
    candidate: Dict[str, float],
) -> str:
    # Match ValidationAgent's retrieval-first decision order.
    if candidate["recall_at_k"] != baseline["recall_at_k"]:
        return (
            "IMPROVED"
            if candidate["recall_at_k"] > baseline["recall_at_k"]
            else "WORSE"
        )

    if candidate["mrr"] != baseline["mrr"]:
        return (
            "IMPROVED"
            if candidate["mrr"] > baseline["mrr"]
            else "WORSE"
        )

    if (
        candidate["precision_at_k"]
        != baseline["precision_at_k"]
    ):
        return (
            "IMPROVED"
            if candidate["precision_at_k"]
            > baseline["precision_at_k"]
            else "WORSE"
        )

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
    baseline = baseline_payload["summary"]["overall"]

    print("BASELINE")
    print(
        f"1000/200 | Recall@4={baseline['recall_at_k']:.4f} | "
        f"Precision@4={baseline['precision_at_k']:.4f} | "
        f"MRR={baseline['mrr']:.4f}"
    )
    print("=" * 95)

    rows = []

    for chunk_size, chunk_overlap in CANDIDATES:
        print(
            f"Building candidate "
            f"{chunk_size}/{chunk_overlap}..."
        )

        candidate = rechunk_and_reindex(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
        )
        metrics = evaluate_candidate(
            candidate["vector_store"],
            dataset,
        )

        verdict = compare_to_baseline(
            baseline,
            metrics,
        )

        row = {
            "chunk_size": chunk_size,
            "chunk_overlap": chunk_overlap,
            "chunks": candidate["chunks"],
            "candidate_index_path": candidate[
                "candidate_index_path"
            ],
            "recall_at_k": metrics["recall_at_k"],
            "precision_at_k": metrics["precision_at_k"],
            "mrr": metrics["mrr"],
            "delta": {
                "recall_at_k": (
                    metrics["recall_at_k"]
                    - baseline["recall_at_k"]
                ),
                "precision_at_k": (
                    metrics["precision_at_k"]
                    - baseline["precision_at_k"]
                ),
                "mrr": (
                    metrics["mrr"]
                    - baseline["mrr"]
                ),
            },
            "verdict": verdict,
        }
        rows.append(row)

        print(
            f"{chunk_size}/{chunk_overlap} | "
            f"chunks={candidate['chunks']} | "
            f"Recall@4={metrics['recall_at_k']:.4f} | "
            f"Precision@4={metrics['precision_at_k']:.4f} | "
            f"MRR={metrics['mrr']:.4f} | "
            f"{verdict}"
        )
        print("-" * 95)

    output = {
        "baseline": {
            "chunk_size": 1000,
            "chunk_overlap": 200,
            **baseline,
        },
        "candidate_count": len(rows),
        "candidates": rows,
        "decision_policy": (
            "Recall@4 first, then MRR, then Precision@4. "
            "No automatic promotion."
        ),
    }

    OUTPUT_PATH.write_text(
        json.dumps(
            output,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print("\nSUMMARY")
    print("=" * 95)
    for row in rows:
        print(
            f"{row['chunk_size']}/{row['chunk_overlap']} -> "
            f"{row['verdict']} | "
            f"R@4={row['recall_at_k']:.4f}, "
            f"P@4={row['precision_at_k']:.4f}, "
            f"MRR={row['mrr']:.4f}"
        )

    print(
        "\nA structural candidate should only be considered for "
        "promotion if Validation says IMPROVED after human approval."
    )
    print(f"Saved to: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
