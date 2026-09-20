"""Offline contract test for the real re-chunk candidate adapter.

No OpenAI key, embeddings, FAISS build, or network is required.
"""
from __future__ import annotations

from rechunk_candidate_adapter import RechunkCandidateAdapter


class FakeVectorStore:
    pass


def fake_build_candidate(
    *,
    chunk_size: int,
    chunk_overlap: int,
):
    assert chunk_size == 500
    assert chunk_overlap == 100
    return {
        "status": "candidate_built",
        "vector_store": FakeVectorStore(),
        "candidate_index_path": (
            "vector_store/candidates/"
            "rechunk_500_100_test"
        ),
        "platforms": [
            "absher",
            "balady",
            "najiz",
            "sakani",
        ],
        "final_files": 24,
        "chunks": 250,
        "chunk_size": 500,
        "chunk_overlap": 100,
        "embedding_model": "text-embedding-3-small",
    }


def fake_build_run(
    vector_store,
    query: str,
    top_k: int,
    *,
    expected_platform=None,
    expected_service=None,
):
    assert isinstance(vector_store, FakeVectorStore)
    assert query == "chunking test query"
    assert top_k == 4
    assert expected_platform == "balady"
    assert expected_service == "building_permit_issuance"

    return {
        "query": query,
        "top_k": top_k,
        "retrieved_results": [
            {
                "rank": 1,
                "platform": "balady",
                "service": "building_permit_issuance",
                "relevant": True,
            }
        ],
        "answer": "",
        "judge_score": None,
        "latency_seconds": 0.02,
    }


def run_tests() -> None:
    adapter = RechunkCandidateAdapter(
        expected_platform="balady",
        expected_service="building_permit_issuance",
        build_candidate=fake_build_candidate,
        build_run=fake_build_run,
    )

    result = adapter(
        {
            "original_query": "chunking test query",
            "baseline_k": 4,
            "chunk_size": 500,
            "chunk_overlap": 100,
        }
    )

    assert result["after_run"]["top_k"] == 4
    assert (
        result["after_run"]["retrieved_results"][0][
            "relevant"
        ]
        is True
    )

    action = result["action_result"]
    assert action["candidate_status"] == "candidate_built"
    assert action["non_destructive"] is True
    assert action["chunk_size"] == 500
    assert action["chunk_overlap"] == 100
    assert action["final_files"] == 24
    assert action["chunks"] == 250
    assert action["embedding_model"] == "text-embedding-3-small"

    # Ground truth can be switched per offline evaluation case.
    adapter.set_expected(
        platform="sakani",
        service="online_financing",
    )
    assert adapter.expected_platform == "sakani"
    assert adapter.expected_service == "online_financing"

    print("Re-chunk candidate adapter tests passed.")


if __name__ == "__main__":
    run_tests()
