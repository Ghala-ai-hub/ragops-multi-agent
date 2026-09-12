import json
from collections import defaultdict

from dotenv import load_dotenv
from langchain_community.vectorstores import FAISS
from langchain_openai import OpenAIEmbeddings

load_dotenv()

DATASET_PATH = "evaluation/dataset_v2.json"
VECTORSTORE_PATH = "vector_store/evaluation_index"
OUTPUT_PATH = "evaluation/retrieval_results_v2.json"

K = 4
EMBEDDING_MODEL = "text-embedding-3-small"


def evaluate_query(vector_store, item):
    query = item["query"]
    expected_service = item["service"]
    expected_platform = item["platform"]

    retrieved_docs = vector_store.similarity_search(query, k=K)

    retrieved_results = []
    relevant_count = 0
    first_relevant_rank = None

    for rank, doc in enumerate(retrieved_docs, start=1):
        metadata = doc.metadata

        is_relevant = (
            metadata.get("platform") == expected_platform
            and metadata.get("service") == expected_service
        )

        if is_relevant:
            relevant_count += 1

            if first_relevant_rank is None:
                first_relevant_rank = rank

        retrieved_results.append(
            {
                "rank": rank,
                "platform": metadata.get("platform"),
                "service": metadata.get("service"),
                "source": metadata.get("source"),
                "chunk_index": metadata.get("chunk_index"),
                "relevant": is_relevant,
            }
        )

    recall_at_k = 1.0 if relevant_count > 0 else 0.0
    precision_at_k = relevant_count / len(retrieved_docs) if retrieved_docs else 0.0
    reciprocal_rank = (
        1.0 / first_relevant_rank
        if first_relevant_rank is not None
        else 0.0
    )

    return {
        "id": item["id"],
        "platform": expected_platform,
        "service": expected_service,
        "query": query,
        "query_type": item["query_type"],
        "k": K,
        "recall_at_k": recall_at_k,
        "precision_at_k": precision_at_k,
        "reciprocal_rank": reciprocal_rank,
        "first_relevant_rank": first_relevant_rank,
        "retrieved": retrieved_results,
    }


def average(values):
    return sum(values) / len(values) if values else 0.0


def build_summary(results):
    summary = {
        "total_queries": len(results),
        "k": K,
        "overall": {
            "recall_at_k": average([r["recall_at_k"] for r in results]),
            "precision_at_k": average([r["precision_at_k"] for r in results]),
            "mrr": average([r["reciprocal_rank"] for r in results]),
        },
        "by_query_type": {},
        "by_platform": {},
    }

    query_type_groups = defaultdict(list)
    platform_groups = defaultdict(list)

    for result in results:
        query_type_groups[result["query_type"]].append(result)
        platform_groups[result["platform"]].append(result)

    for query_type, group in query_type_groups.items():
        summary["by_query_type"][query_type] = {
            "count": len(group),
            "recall_at_k": average([r["recall_at_k"] for r in group]),
            "precision_at_k": average([r["precision_at_k"] for r in group]),
            "mrr": average([r["reciprocal_rank"] for r in group]),
        }

    for platform, group in platform_groups.items():
        summary["by_platform"][platform] = {
            "count": len(group),
            "recall_at_k": average([r["recall_at_k"] for r in group]),
            "precision_at_k": average([r["precision_at_k"] for r in group]),
            "mrr": average([r["reciprocal_rank"] for r in group]),
        }

    return summary


def main():
    with open(DATASET_PATH, "r", encoding="utf-8") as f:
        dataset = json.load(f)

    embeddings = OpenAIEmbeddings(model=EMBEDDING_MODEL)

    vector_store = FAISS.load_local(
        VECTORSTORE_PATH,
        embeddings,
        allow_dangerous_deserialization=True,
    )

    print(f"DATASET QUERIES: {len(dataset)}")
    print(f"TOP-K: {K}")
    print("=" * 70)

    results = []

    for index, item in enumerate(dataset, start=1):
        result = evaluate_query(vector_store, item)
        results.append(result)

        print(
            f"[{index:02d}/{len(dataset)}] "
            f"{item['id']} | "
            f"Recall@{K}={result['recall_at_k']:.2f} | "
            f"Precision@{K}={result['precision_at_k']:.2f} | "
            f"RR={result['reciprocal_rank']:.2f}"
        )

    summary = build_summary(results)

    output = {
        "configuration": {
            "dataset": DATASET_PATH,
            "vector_store": VECTORSTORE_PATH,
            "embedding_model": EMBEDDING_MODEL,
            "k": K,
            "relevance_level": "platform_and_service",
        },
        "summary": summary,
        "results": results,
    }

    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print("\n" + "=" * 70)
    print("OVERALL RESULTS")
    print("=" * 70)
    print(f"Recall@{K}:    {summary['overall']['recall_at_k']:.4f}")
    print(f"Precision@{K}: {summary['overall']['precision_at_k']:.4f}")
    print(f"MRR:           {summary['overall']['mrr']:.4f}")

    print("\nBY QUERY TYPE")
    for query_type, metrics in summary["by_query_type"].items():
        print(
            f"{query_type}: "
            f"Recall@{K}={metrics['recall_at_k']:.4f}, "
            f"Precision@{K}={metrics['precision_at_k']:.4f}, "
            f"MRR={metrics['mrr']:.4f}"
        )

    print("\nBY PLATFORM")
    for platform, metrics in summary["by_platform"].items():
        print(
            f"{platform}: "
            f"Recall@{K}={metrics['recall_at_k']:.4f}, "
            f"Precision@{K}={metrics['precision_at_k']:.4f}, "
            f"MRR={metrics['mrr']:.4f}"
        )

    print(f"\nResults saved to: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()