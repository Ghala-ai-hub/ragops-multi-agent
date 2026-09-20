"""Inspect current Recall@4 failures using an expanded Top-10 window.

Purpose:
- Keep the baseline fixed at K=4.
- For queries that fail at K=4, check whether the expected service appears
  between ranks 5-10.
- This provides evidence for a possible Top-K diagnosis without changing the
  baseline evaluation.

Uses the already-built four-platform FAISS evaluation index.
"""
from __future__ import annotations

import json
from pathlib import Path

from dotenv import load_dotenv
from langchain_community.vectorstores import FAISS
from langchain_openai import OpenAIEmbeddings


DATASET_PATH = Path("evaluation/dataset_v2.json")
RESULTS_PATH = Path("evaluation/retrieval_results_v2.json")
VECTORSTORE_PATH = "vector_store/evaluation_index"
EMBEDDING_MODEL = "text-embedding-3-small"
BASELINE_K = 4
EXPANDED_K = 10


def first_relevant_rank(docs, platform: str, service: str):
    for rank, doc in enumerate(docs, start=1):
        metadata = doc.metadata
        if (
            metadata.get("platform") == platform
            and metadata.get("service") == service
        ):
            return rank
    return None


def main() -> None:
    load_dotenv()

    dataset = json.loads(
        DATASET_PATH.read_text(encoding="utf-8")
    )
    stored = json.loads(
        RESULTS_PATH.read_text(encoding="utf-8")
    )

    by_id = {item["id"]: item for item in dataset}
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

    print(f"BASELINE K: {BASELINE_K}")
    print(f"EXPANDED K: {EXPANDED_K}")
    print(f"FAILED BASELINE QUERIES: {len(failures)}")
    print("=" * 80)

    topk_candidates = 0
    unresolved = 0

    for failure in failures:
        item = by_id[failure["id"]]
        docs = vector_store.similarity_search(
            item["query"],
            k=EXPANDED_K,
        )
        rank = first_relevant_rank(
            docs,
            item["platform"],
            item["service"],
        )

        if rank is not None and rank > BASELINE_K:
            classification = "TOP-K CANDIDATE"
            topk_candidates += 1
        elif rank is None:
            classification = "NOT FOUND IN TOP-10"
            unresolved += 1
        else:
            # This should be rare because the stored K=4 result failed.
            classification = "RECHECK BASELINE"

        print(
            f"{item['id']} | {item['query_type']} | "
            f"expanded_rank={rank} | {classification}"
        )
        print(f"Query: {item['query']}")
        print("Top-10 services:")

        for result_rank, doc in enumerate(docs, start=1):
            meta = doc.metadata
            marker = " <-- EXPECTED" if (
                meta.get("platform") == item["platform"]
                and meta.get("service") == item["service"]
            ) else ""
            print(
                f"  {result_rank:02d}. "
                f"{meta.get('platform')}/"
                f"{meta.get('service')}{marker}"
            )

        print("-" * 80)

    print("SUMMARY")
    print("=" * 80)
    print(f"Top-K candidates (rank 5-10): {topk_candidates}")
    print(f"Not found in Top-10: {unresolved}")
    print(
        "Note: 'Not found in Top-10' is not automatically Query Mismatch "
        "or Chunking Quality; it means more diagnostic evidence is needed."
    )


if __name__ == "__main__":
    main()
