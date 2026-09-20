from scripts.optimization_agent import OptimizationAgent


def run_pipeline_test():
    agent = OptimizationAgent()

    query_mismatch = {
        "issue_type": "Query Mismatch",
        "original_query": "وش اسوي لو انتهت رخصتي حق بلدي",
        "recommended_action": "rewrite_query",
        "baseline_k": 4,
    }

    top_k = {
        "issue_type": "Top-K",
        "original_query": "مثال Top-K",
        "recommended_action": "change_top_k",
        "recommended_k": 6,
        "baseline_k": 4,
    }

    chunking = {
        "issue_type": "Chunking Quality",
        "original_query": "مثال جودة التقسيم",
        "recommended_action": "rechunk_and_reindex",
        "baseline_k": 4,
        "new_chunk_size": 500,
        "new_chunk_overlap": 100,
    }

    q = agent.propose(query_mismatch)
    k = agent.propose(top_k)
    c = agent.propose(chunking)

    assert q["action"] == "rewrite_query"
    assert q["parameters"]["original_query"] == query_mismatch["original_query"]
    assert q["parameters"]["baseline_k"] == 4

    assert k["action"] == "change_top_k"
    assert k["parameters"]["new_k"] == 6

    assert c["action"] == "rechunk_and_reindex"
    assert c["parameters"]["chunk_size"] == 500
    assert c["parameters"]["chunk_overlap"] == 100

    print("Optimization proposal tests passed.")


if __name__ == "__main__":
    run_pipeline_test()
