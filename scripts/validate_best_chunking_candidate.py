"""Detailed validation for the best chunking candidate (750/150).

Builds a NON-DESTRUCTIVE candidate index, evaluates the same 48 queries at
K=4, and reports exactly which queries improved, stayed the same, or regressed
relative to the saved 1000/200 baseline.

This script does not replace or promote the active baseline index.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from optimization_tools import rechunk_and_reindex


DATASET_PATH = Path("evaluation/dataset_v2.json")
BASELINE_RESULTS_PATH = Path("evaluation/retrieval_results_v2.json")
OUTPUT_PATH = Path("evaluation/rechunk_750_150_detailed.json")

K = 4
CHUNK_SIZE = 750
CHUNK_OVERLAP = 150


def evaluate_query(vector_store, item: Dict[str, Any]) -> Dict[str, Any]:
    docs = vector_store.similarity_search(item["query"], k=K)

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
        "recall_at_k": 1.0 if relevant_count else 0.0,
        "precision_at_k": relevant_count / len(docs) if docs else 0.0,
        "reciprocal_rank": (
            1.0 / first_relevant_rank
            if first_relevant_rank is not None
            else 0.0
        ),
        "first_relevant_rank": first_relevant_rank,
        "retrieved": retrieved,
    }


def verdict(before: Dict[str, Any], after: Dict[str, Any]) -> str:
    before_tuple = (
        before["recall_at_k"],
        before["reciprocal_rank"],
        before["precision_at_k"],
    )
    after_tuple = (
        after["recall_at_k"],
        after["reciprocal_rank"],
        after["precision_at_k"],
    )

    if after_tuple > before_tuple:
        return "IMPROVED"
    if after_tuple < before_tuple:
        return "WORSE"
    return "SAME"


def main() -> None:
    dataset: List[Dict[str, Any]] = json.loads(
        DATASET_PATH.read_text(encoding="utf-8")
    )
    baseline_payload = json.loads(
        BASELINE_RESULTS_PATH.read_text(encoding="utf-8")
    )
    baseline_by_id = {
        item["id"]: item
        for item in baseline_payload["results"]
    }

    print(
        "Building NON-DESTRUCTIVE candidate "
        f"{CHUNK_SIZE}/{CHUNK_OVERLAP}..."
    )
    candidate = rechunk_and_reindex(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
    )
    vector_store = candidate["vector_store"]

    rows = []
    counts = {"IMPROVED": 0, "SAME": 0, "WORSE": 0}

    for item in dataset:
        before = baseline_by_id[item["id"]]
        after = evaluate_query(vector_store, item)
        status = verdict(before, after)
        counts[status] += 1

        rows.append(
            {
                "id": item["id"],
                "platform": item["platform"],
                "service": item["service"],
                "query_type": item["query_type"],
                "query": item["query"],
                "before": {
                    "recall_at_k": before["recall_at_k"],
                    "precision_at_k": before["precision_at_k"],
                    "reciprocal_rank": before["reciprocal_rank"],
                    "first_relevant_rank": before["first_relevant_rank"],
                },
                "after": {
                    "recall_at_k": after["recall_at_k"],
                    "precision_at_k": after["precision_at_k"],
                    "reciprocal_rank": after["reciprocal_rank"],
                    "first_relevant_rank": after["first_relevant_rank"],
                },
                "verdict": status,
            }
        )

    improved = [r for r in rows if r["verdict"] == "IMPROVED"]
    worse = [r for r in rows if r["verdict"] == "WORSE"]

    recovered_failures = [
        r
        for r in rows
        if r["before"]["recall_at_k"] == 0.0
        and r["after"]["recall_at_k"] == 1.0
    ]
    new_failures = [
        r
        for r in rows
        if r["before"]["recall_at_k"] == 1.0
        and r["after"]["recall_at_k"] == 0.0
    ]

    output = {
        "configuration": {
            "baseline_chunk_size": 1000,
            "baseline_chunk_overlap": 200,
            "candidate_chunk_size": CHUNK_SIZE,
            "candidate_chunk_overlap": CHUNK_OVERLAP,
            "k": K,
            "candidate_index_path": candidate["candidate_index_path"],
            "active_index_overwritten": False,
        },
        "counts": counts,
        "recovered_failures": recovered_failures,
        "new_failures": new_failures,
        "improved_queries": improved,
        "worse_queries": worse,
        "results": rows,
    }

    OUTPUT_PATH.write_text(
        json.dumps(output, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print("=" * 100)
    print(
        f"Per-query verdicts: "
        f"{counts['IMPROVED']} improved, "
        f"{counts['SAME']} same, "
        f"{counts['WORSE']} worse"
    )
    print(
        f"Recovered baseline failures: {len(recovered_failures)}"
    )
    for row in recovered_failures:
        print(
            f"  + {row['id']} | "
            f"rank {row['before']['first_relevant_rank']} "
            f"-> {row['after']['first_relevant_rank']}"
        )

    print(f"New Recall@4 failures: {len(new_failures)}")
    for row in new_failures:
        print(
            f"  - {row['id']} | "
            f"rank {row['before']['first_relevant_rank']} "
            f"-> {row['after']['first_relevant_rank']}"
        )

    print("\nWORSE QUERIES")
    if not worse:
        print("  None")
    else:
        for row in worse:
            print(
                f"  {row['id']} | "
                f"Recall {row['before']['recall_at_k']:.0f}"
                f"->{row['after']['recall_at_k']:.0f}, "
                f"RR {row['before']['reciprocal_rank']:.2f}"
                f"->{row['after']['reciprocal_rank']:.2f}, "
                f"P {row['before']['precision_at_k']:.2f}"
                f"->{row['after']['precision_at_k']:.2f}"
            )

    print(f"\nSaved to: {OUTPUT_PATH}")
    print(
        "No promotion was performed. Promotion remains a separate "
        "human-approved structural action."
    )


if __name__ == "__main__":
    main()
