"""Offline release-readiness checks for the current RAGOps branch.

This script does not call OpenAI or LangSmith and does not modify files.
It verifies corpus/evaluation structure, required project files, local FAISS
availability, git-ignore safety, and scans tracked text files for likely API
keys without printing any secret values.
"""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent

PLATFORMS = {
    "absher": 6,
    "balady": 6,
    "najiz": 6,
    "sakani": 6,
}

REQUIRED_FILES = [
    "requirements.txt",
    ".env.example",
    ".gitignore",
    "scripts/monitoring_agent.py",
    "scripts/diagnosis_agent.py",
    "scripts/optimization_agent.py",
    "scripts/action_executor.py",
    "scripts/validation_agent.py",
    "scripts/langgraph_workflow.py",
    "scripts/run_ragops_demo.py",
    "scripts/run_regression_suite.py",
    "evaluation/dataset_v2.json",
    "evaluation/retrieval_results_v2.json",
    "evaluation/rewrite_probe_results.json",
    "evaluation/real_failure_workflow_results.json",
    "evaluation/chunking_sweep_results.json",
    "evaluation/rechunk_750_150_detailed.json",
]

EVALUATION_INDEX_FILES = [
    "vector_store/evaluation_index/index.faiss",
    "vector_store/evaluation_index/index.pkl",
]

SECRET_PATTERNS = [
    re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"),
    re.compile(r"\blsv2_(?:pt|sk)[A-Za-z0-9_-]{15,}\b"),
]


def _git_tracked_files() -> list[str]:
    result = subprocess.run(
        ["git", "ls-files"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    return [
        line.strip()
        for line in result.stdout.splitlines()
        if line.strip()
    ]


def _check(name: str, condition: bool, detail: str = "") -> bool:
    label = "PASS" if condition else "FAIL"
    suffix = f" | {detail}" if detail else ""
    print(f"{label:<4} {name}{suffix}")
    return condition


def _scan_secrets(tracked: list[str]) -> list[tuple[str, int]]:
    findings: list[tuple[str, int]] = []

    for relative in tracked:
        path = ROOT / relative
        if not path.is_file():
            continue

        try:
            text = path.read_text(
                encoding="utf-8",
                errors="ignore",
            )
        except OSError:
            continue

        for line_number, line in enumerate(
            text.splitlines(),
            start=1,
        ):
            if any(pattern.search(line) for pattern in SECRET_PATTERNS):
                findings.append((relative, line_number))

    return findings


def main() -> None:
    print("RAGOps release-readiness checks")
    print("=" * 88)

    results: list[bool] = []

    for relative in REQUIRED_FILES:
        results.append(
            _check(
                f"required file: {relative}",
                (ROOT / relative).is_file(),
            )
        )

    total_final = 0
    for platform, expected in PLATFORMS.items():
        files = list(
            (ROOT / "knowledge_base" / platform).glob(
                "*/content_final.md"
            )
        )
        total_final += len(files)
        results.append(
            _check(
                f"{platform} final services",
                len(files) == expected,
                f"{len(files)}/{expected}",
            )
        )

    results.append(
        _check(
            "total final corpus",
            total_final == 24,
            f"{total_final}/24",
        )
    )

    dataset_path = ROOT / "evaluation" / "dataset_v2.json"
    dataset_count = -1
    if dataset_path.is_file():
        try:
            dataset = json.loads(
                dataset_path.read_text(encoding="utf-8")
            )
            dataset_count = len(dataset)
        except (OSError, json.JSONDecodeError, TypeError):
            dataset_count = -1

    results.append(
        _check(
            "evaluation dataset queries",
            dataset_count == 48,
            f"{dataset_count}/48",
        )
    )

    requirements = (
        ROOT / "requirements.txt"
    ).read_text(encoding="utf-8-sig")
    results.append(
        _check(
            "LangGraph dependency pinned",
            "langgraph==1.2.11" in requirements,
        )
    )

    gitignore = (
        ROOT / ".gitignore"
    ).read_text(encoding="utf-8-sig")
    for ignored in [
        ".env",
        "vector_store/evaluation_index/",
        "vector_store/candidates/",
        "logs/",
    ]:
        results.append(
            _check(
                f"gitignore protects {ignored}",
                ignored in gitignore,
            )
        )

    for relative in EVALUATION_INDEX_FILES:
        results.append(
            _check(
                f"local FAISS: {relative}",
                (ROOT / relative).is_file(),
            )
        )

    tracked = _git_tracked_files()

    results.append(
        _check(
            ".env is not tracked",
            ".env" not in tracked,
        )
    )
    results.append(
    _check(
        "official frontend is tracked",
        "app.py" in tracked
        and "frontend/adapter.py" in tracked
        and "frontend/observability.py" in tracked,
    )
)
    
    results.append(
        _check(
            "candidate indexes are not tracked",
            not any(
                path.startswith("vector_store/candidates/")
                for path in tracked
            ),
        )
    )

    secret_findings = _scan_secrets(tracked)
    results.append(
        _check(
            "tracked secret scan",
            not secret_findings,
            (
                "no likely API keys found"
                if not secret_findings
                else "possible key pattern found; inspect file/line"
            ),
        )
    )

    if secret_findings:
        for relative, line_number in secret_findings:
            print(
                f"     inspect: {relative}:{line_number}"
            )

    print("-" * 88)
    passed = sum(1 for item in results if item)
    total = len(results)
    print(f"READINESS SUMMARY: {passed}/{total} checks passed")

    if passed != total:
        raise SystemExit(1)

    print("RAGOps branch readiness checks passed.")


if __name__ == "__main__":
    main()
