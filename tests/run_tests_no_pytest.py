"""
run_tests_no_pytest.py
-----------------------
This sandbox has no outbound network access, so `pip install pytest` is not
possible here (confirmed: PyPI is unreachable). `tests/test_pipeline.py` is
still written in standard pytest style because that is what the team should
use once they run this on a normal internet-connected machine
(`pip install -r requirements.txt && python -m pytest tests/ -v`).

This script is a minimal, dependency-free runner that executes the exact
same test functions from test_pipeline.py (handling the one `tmp_path`
fixture manually) so the suite can be proven to actually pass in THIS
environment, right now, instead of just being trusted on faith.
"""

from __future__ import annotations

import sys
import tempfile
import traceback
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parent.parent / "src"
TESTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SRC_DIR))

try:
    import pytest  # noqa: F401
except ImportError:
    import _pytest_shim
    sys.modules["pytest"] = _pytest_shim

import test_pipeline as tp  # noqa: E402


def main() -> int:
    store = tp.store.__wrapped__() if hasattr(tp.store, "__wrapped__") else None
    # pytest fixtures aren't callable directly; just rebuild what they'd give us.
    from retrieval import VectorStore
    real_store = VectorStore.from_jsonl()

    no_arg_tests = [
        tp.test_six_services_present,
        tp.test_no_services_are_excluded_anymore,
        tp.test_all_services_are_data_completeness_full,
        tp.test_chunk_ids_are_unique,
        tp.test_every_chunk_has_required_metadata,
        tp.test_no_chunk_is_a_tiny_fragment,
        tp.test_exit_visa_service_has_real_steps_for_both_procedures,
        tp.test_min_healthy_chunk_threshold_is_below_every_real_chunk_length,
        tp.test_default_backend_is_openai,
        tp.test_unavailable_sentence_transformers_falls_back_to_tfidf_not_a_crash,
        tp.test_unavailable_openai_falls_back_correctly_not_a_crash,
        tp.test_explicit_tfidf_request_never_reports_a_fallback,
        tp.test_vector_store_backend_info_is_consistent_with_its_embedder,
        tp.test_chunk_service_is_platform_agnostic,
    ]
    store_only_tests = [
        tp.test_store_returns_top_k_results,
        tp.test_top1_result_is_the_correct_service_for_a_clean_direct_query,
        tp.test_lost_passport_faq_is_retrievable,
        tp.test_new_services_are_chunked_and_retrievable,
    ]
    store_and_tmp_tests = [
        tp.test_monitoring_agent_flags_offtopic_query,
        tp.test_monitoring_agent_does_not_flag_a_clean_matching_query,
        tp.test_monitoring_log_is_valid_jsonl,
        tp.test_monitoring_report_schema_matches_contract_exactly,
        tp.test_monitoring_report_never_exposes_internal_signal_or_issue_type_names,
        tp.test_monitoring_report_production_mode_has_null_ground_truth_fields,
        tp.test_monitoring_report_evaluation_mode_finds_relevant_at_baseline,
        tp.test_monitoring_report_evaluation_mode_on_a_known_real_failure,
        tp.test_monitoring_report_default_baseline_k,
        tp.test_monitoring_report_chunking_signal_mirrors_internal_heuristic,
        tp.test_retrieved_results_items_match_contract_fields,
        tp.test_diagnostic_probe_absent_when_no_rewrite_supplied,
        tp.test_diagnostic_probe_present_and_honest_when_rewrite_supplied,
        tp.test_diagnosis_reports_log_keeps_internal_signals_separate,
    ]
    tmp_only_tests = [
        tp.test_monitoring_agent_survives_a_broken_store,
    ]

    passed, failed = 0, 0

    def run(name, fn, *args):
        nonlocal passed, failed
        try:
            fn(*args)
            print(f"PASS  {name}")
            passed += 1
        except Exception:  # noqa: BLE001
            print(f"FAIL  {name}")
            traceback.print_exc()
            failed += 1

    for fn in no_arg_tests:
        run(fn.__name__, fn)
    for fn in store_only_tests:
        run(fn.__name__, fn, real_store)
    with tempfile.TemporaryDirectory() as td:
        base = Path(td)
        # Real pytest gives every test its own fresh tmp_path; replicate
        # that here with a per-test subdirectory so log files from one test
        # don't bleed into the next.
        for fn in store_and_tmp_tests:
            tmp = base / fn.__name__
            tmp.mkdir()
            run(fn.__name__, fn, real_store, tmp)
        for fn in tmp_only_tests:
            tmp = base / fn.__name__
            tmp.mkdir()
            run(fn.__name__, fn, tmp)

    print(f"\n{passed} passed, {failed} failed out of {passed + failed}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
