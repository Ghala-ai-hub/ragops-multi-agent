"""Run a Query-Rewrite diagnostic probe on current Recall@4 failures.

This script does NOT change the baseline index or dataset. For each failed
baseline query it:
1) rewrites the query using the Optimization tool,
2) retrieves Top-10 for the rewritten query,
3) compares the expected service rank before vs after,
4) saves the evidence to evaluation/rewrite_probe_results.json.

The result is diagnostic evidence only. Diagnosis decides whether the failure
is Query Mismatch, Top-K, Chunking Quality, or still needs review.
"""
from __future__ import annotations

import json
from pathlib import Path

from dotenv import load_dotenv
from langchain_community.vectorstores import FAISS
from langchain_openai import OpenAIEmbeddings

from optimization_tools import rewrite_query


DATASET_PATH = Path("evaluation/dataset_v2.json")
RESULTS_PATH = Path("evaluation/retrieval_results_v2.json")
OUTPUT_PATH = Path("evaluation/rewrite_probe_results.json")
VECTORSTORE_PATH = "vector_store/evaluation_index"

EMBEDDING_MODEL = "text-embedding-3-small"
BASELINE_K = 4
PROBE_K = 10


def first_relevant_rank(docs, platform: str, service: str):
    for rank, doc in enumerate(docs, start=1):
        metadata = doc.metadata
        if (
            metadata.get("platform") == platform
            and metadata.get("service") == service
        ):
            return rank
    return None


def baseline_rank_from_stored(result):
    rank = result.get("first_relevant_rank")
    return int(rank) if rank is not None else None


def main() -> None:
    load_dotenv()

    dataset = json.loads(
        DATASET_PATH.read_text(encoding="utf-8")
    )
    stored = json.loads(
        RESULTS_PATH.read_text(encoding="utf-8")
    )

    dataset_by_id = {item["id"]: item for item in dataset}
    failures = [
        item
        for item in stored["results"]
        if float(item.get("recall_at_k", 0.0)) == 0.0
    ]

    embeddings = OpenAIEmbeddings(model=EMBEDDING_MODEL)
    vector_store = FAISS.load_local(
        VECTORSTORE_PATH,
        embeddings,
        allow_dangerous_deserialization=True,
    )

    output = {
        "configuration": {
            "baseline_k": BASELINE_K,
            "probe_k": PROBE_K,
            "embedding_model": EMBEDDING_MODEL,
            "rewrite_model": "gpt-4o-mini",
        },
        "results": [],
    }

    print(f"FAILED BASELINE QUERIES: {len(failures)}")
    print("=" * 90)

    for index, failure in enumerate(failures, start=1):
        item = dataset_by_id[failure["id"]]

        original_docs = vector_store.similarity_search(
            item["query"],
            k=PROBE_K,
        )
        original_expanded_rank = first_relevant_rank(
            original_docs,
            item["platform"],
            item["service"],
        )

        rewritten = rewrite_query(item["query"])

        rewritten_docs = vector_store.similarity_search(
            rewritten,
            k=PROBE_K,
        )
        rewritten_rank = first_relevant_rank(
            rewritten_docs,
            item["platform"],
            item["service"],
        )

        baseline_rank = baseline_rank_from_stored(failure)

        if rewritten_rank is None:
            improved = False
        elif baseline_rank is None:
            # Baseline Recall@4 failed. Any rewritten hit inside Top-4 is a
            # direct retrieval improvement; a hit only at 5-10 is useful
            # evidence but does not repair the baseline cutoff.
            improved = rewritten_rank <= BASELINE_K
        else:
            improved = rewritten_rank < baseline_rank

        if improved:
            interpretation = "QUERY-REWRITE IMPROVED TOP-4"
        elif (
            original_expanded_rank is not None
            and original_expanded_rank > BASELINE_K
        ):
            interpretation = "TOP-K EVIDENCE REMAINS"
        else:
            interpretation = "STILL NEEDS DIAGNOSIS"

        record = {
            "id": item["id"],
            "platform": item["platform"],
            "service": item["service"],
            "query_type": item["query_type"],
            "original_query": item["query"],
            "rewritten_query": rewritten,
            "baseline_first_relevant_rank": baseline_rank,
            "original_expanded_rank": original_expanded_rank,
            "rewritten_first_relevant_rank": rewritten_rank,
            "rewrite_probe_improved": improved,
            "interpretation": interpretation,
        }
        output["results"].append(record)

        print(f"[{index}/{len(failures)}] {item['id']}")
        print(f"Original : {item['query']}")
        print(f"Rewrite  : {rewritten}")
        print(
            "Ranks    : "
            f"baseline_top4={baseline_rank}, "
            f"original_top10={original_expanded_rank}, "
            f"rewritten_top10={rewritten_rank}"
        )
        print(f"Probe    : {improved}")
        print(f"Result   : {interpretation}")
        print("-" * 90)

    OUTPUT_PATH.write_text(
        json.dumps(output, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    improved_count = sum(
        1
        for item in output["results"]
        if item["rewrite_probe_improved"]
    )

    print("SUMMARY")
    print("=" * 90)
    print(
        f"Rewrite improved Top-4: "
        f"{improved_count}/{len(output['results'])}"
    )
    print(f"Saved to: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
