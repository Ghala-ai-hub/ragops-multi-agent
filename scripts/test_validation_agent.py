from validation_agent import ValidationAgent


def test_improved():
    agent = ValidationAgent()
    before = {
        "retrieved_results": [
            {"rank": 1, "relevant": False},
            {"rank": 2, "relevant": False},
            {"rank": 3, "relevant": False},
            {"rank": 4, "relevant": False},
        ],
        "answer": "المعلومات غير كافية.",
        "judge_score": 1.0,
        "latency_seconds": 1.2,
    }
    after = {
        "retrieved_results": [
            {"rank": 1, "relevant": True},
            {"rank": 2, "relevant": True},
            {"rank": 3, "relevant": True},
            {"rank": 4, "relevant": False},
        ],
        "answer": "إجابة محسنة مبنية على السياق المسترجع.",
        "judge_score": 5.0,
        "latency_seconds": 2.0,
    }
    result = agent.validate(before, after)
    assert result["verdict"] == "IMPROVED"
    assert result["recommendation"] == "ACCEPT_OPTIMIZED"
    assert result["after"]["recall_at_k"] == 1.0
    assert result["after"]["precision_at_k"] == 0.75
    assert result["after"]["reciprocal_rank"] == 1.0


def test_worse():
    agent = ValidationAgent()
    before = {
        "retrieved_results": [{"rank": 1, "relevant": True}],
        "judge_score": 5.0,
        "latency_seconds": 1.0,
    }
    after = {
        "retrieved_results": [{"rank": 1, "relevant": False}],
        "judge_score": 3.0,
        "latency_seconds": 1.0,
    }
    result = agent.validate(before, after)
    assert result["verdict"] == "WORSE"
    assert result["recommendation"] == "RETAIN_BASELINE"


if __name__ == "__main__":
    test_improved()
    test_worse()
    print("Validation Agent tests passed: IMPROVED and WORSE scenarios.")
