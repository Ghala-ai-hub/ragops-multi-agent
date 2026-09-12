from typing import Dict, Any, Optional


class DiagnosisAgent:
    """
    Diagnosis Agent for retrieval failures.

    Input 1: monitoring_report
    Comes from the Monitoring Agent.

    Input 2: diagnostic_probe
    Optional evidence generated during diagnosis,
    such as the result of a Query Rewriting probe.
    """

    def diagnose(
        self,
        monitoring_report: Dict[str, Any],
        diagnostic_probe: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:

        original_query = monitoring_report.get("original_query", "")
        baseline_k = monitoring_report.get("baseline_k", 4)

        failure_detected = monitoring_report.get(
            "failure_detected",
            False,
        )

        baseline_relevant_found = monitoring_report.get(
            "baseline_relevant_found"
        )

        baseline_first_rank = monitoring_report.get(
            "baseline_first_relevant_rank"
        )

        expanded_first_rank = monitoring_report.get(
            "expanded_first_relevant_rank"
        )

        chunking_signal = monitoring_report.get(
            "chunking_signal",
            False,
        )

        diagnostic_probe = diagnostic_probe or {}

        rewrite_probe_improved = diagnostic_probe.get(
            "rewrite_probe_improved",
            False,
        )

        rewritten_first_rank = diagnostic_probe.get(
            "rewritten_first_relevant_rank"
        )

        # 1. No detected failure
        if not failure_detected and baseline_relevant_found is True:
            return {
                "issue_type": None,
                "original_query": original_query,
                "recommended_action": "none",
                "confidence": 0.90,
                "reason": (
                    f"Relevant content was found within Top-{baseline_k} "
                    "and no retrieval failure was detected."
                ),
            }

        # 2. Chunking Quality
        if chunking_signal:
            return {
                "issue_type": "Chunking Quality",
                "original_query": original_query,
                "recommended_action": "rechunk_and_reindex",
                "confidence": 0.90,
                "reason": (
                    "Retrieval evidence indicates that relevant content "
                    "may be fragmented or poorly represented by the "
                    "current chunking strategy."
                ),
            }

        # 3. Query Mismatch
        if rewrite_probe_improved:
            return {
                "issue_type": "Query Mismatch",
                "original_query": original_query,
                "recommended_action": "rewrite_query",
                "confidence": 0.95,
                "reason": (
                    "A rewritten version of the query improved retrieval "
                    "ranking compared with the original query."
                ),
                "baseline_first_relevant_rank": baseline_first_rank,
                "rewritten_first_relevant_rank": rewritten_first_rank,
            }

        # 4. Top-K
        if (
            baseline_relevant_found is False
            and expanded_first_rank is not None
            and expanded_first_rank > baseline_k
        ):
            return {
                "issue_type": "Top-K",
                "original_query": original_query,
                "recommended_action": "change_top_k",
                "recommended_k": expanded_first_rank,
                "confidence": 0.85,
                "reason": (
                    f"Relevant content was not found within Top-{baseline_k} "
                    f"but appeared at rank {expanded_first_rank} "
                    "when the retrieval window was expanded."
                ),
            }

        # 5. Insufficient evidence
        return {
            "issue_type": None,
            "original_query": original_query,
            "recommended_action": "needs_review",
            "confidence": 0.40,
            "reason": (
                "There is not enough evidence to distinguish between "
                "Top-K, Query Mismatch, and Chunking Quality."
            ),
        }


if __name__ == "__main__":
    agent = DiagnosisAgent()

    tests = [
        {
            "name": "Query Mismatch",
            "monitoring_report": {
                "original_query": "رخصة المحل انتهت وأبي أجددها من بلدي، وش الخطوات؟",
                "baseline_k": 4,
                "failure_detected": True,
                "baseline_relevant_found": False,
                "baseline_first_relevant_rank": None,
                "expanded_first_relevant_rank": 6,
                "chunking_signal": False,
            },
            "diagnostic_probe": {
                "rewrite_probe_improved": True,
                "rewritten_first_relevant_rank": 1,
            },
        },
        {
            "name": "Top-K",
            "monitoring_report": {
                "original_query": "مثال لاختبار مشكلة Top-K",
                "baseline_k": 4,
                "failure_detected": True,
                "baseline_relevant_found": False,
                "baseline_first_relevant_rank": None,
                "expanded_first_relevant_rank": 6,
                "chunking_signal": False,
            },
            "diagnostic_probe": {
                "rewrite_probe_improved": False,
            },
        },
        {
            "name": "Chunking Quality",
            "monitoring_report": {
                "original_query": "مثال لاختبار مشكلة جودة التقسيم",
                "baseline_k": 4,
                "failure_detected": True,
                "baseline_relevant_found": False,
                "baseline_first_relevant_rank": None,
                "expanded_first_relevant_rank": None,
                "chunking_signal": True,
            },
            "diagnostic_probe": {},
        },
    ]

    for test in tests:
        result = agent.diagnose(
            test["monitoring_report"],
            test["diagnostic_probe"],
        )

        print("\n" + "=" * 60)
        print(f"TEST: {test['name']}")
        print("=" * 60)

        for key, value in result.items():
            print(f"{key}: {value}")