"""Run the current offline RAGOps regression suite.

This suite validates the integration contracts without calling OpenAI,
LangSmith, or rebuilding FAISS. It intentionally excludes the legacy
test_baseline_rag.py script because that script targets the older two-platform
Balady/Najiz baseline index rather than the current four-platform evaluation
pipeline.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent

TESTS = [
    "test_monitoring_diagnosis_contract.py",
    "test_optimization_pipeline.py",
    "test_hitl_executor.py",
    "test_integration_workflow.py",
    "test_rechunk_candidate_adapter.py",
    "test_langgraph_workflow.py",
    "test_langgraph_hitl.py",
    "test_langsmith_observability.py",
]


def main() -> None:
    passed = []
    failed = []

    print("RAGOps offline regression suite")
    print("=" * 88)

    for name in TESTS:
        path = SCRIPT_DIR / name
        print(f"RUN  {name}")

        result = subprocess.run(
            [sys.executable, str(path)],
            cwd=SCRIPT_DIR.parent,
            text=True,
        )

        if result.returncode == 0:
            passed.append(name)
            print(f"PASS {name}")
        else:
            failed.append(name)
            print(f"FAIL {name}")

        print("-" * 88)

    print("REGRESSION SUMMARY")
    print(f"Passed: {len(passed)}/{len(TESTS)}")
    print(f"Failed: {len(failed)}/{len(TESTS)}")

    if failed:
        print("Failed tests:")
        for name in failed:
            print(f"- {name}")
        raise SystemExit(1)

    print("All current offline RAGOps regression tests passed.")


if __name__ == "__main__":
    main()
