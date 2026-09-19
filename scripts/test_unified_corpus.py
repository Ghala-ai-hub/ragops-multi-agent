"""Offline tests for the unified four-platform corpus and retriever."""
from scripts.unified_corpus import build_unified_store, load_unified_chunks, corpus_summary


def test_corpus_structure():
    chunks = load_unified_chunks(chunk_size=800, chunk_overlap=120)
    summary = corpus_summary(chunks)
    assert summary["total_services"] == 24, summary
    assert set(summary["platforms"]) == {"Absher", "balady", "najiz", "sakani"}
    assert all(info["service_count"] == 6 for info in summary["platforms"].values())
    required = {
        "chunk_id", "text", "service_id", "service_name_ar", "chunk_type",
        "section_title_ar", "source_documents", "data_completeness", "platform",
        "source_file", "chunk_index",
    }
    assert all(required.issubset(chunk) for chunk in chunks)


def test_unified_retrieval_offline():
    store, summary = build_unified_store("tfidf", chunk_size=800, chunk_overlap=120)
    assert summary["total_services"] == 24
    cases = [
        ("ما هي شروط تجديد رخصة القيادة؟", "driving_license_renewal"),
        ("ما خطوات تجديد رخصة تجارية؟", "commercial_license_renewal"),
        ("ما خطوات تقديم صحيفة دعوى عبر ناجز؟", "statement_of_claim"),
        ("كيف أعرف إذا أنا مستحق للدعم السكني؟", "housing_support_eligibility"),
    ]
    for query, expected_service in cases:
        results = store.search(query, top_k=5)
        assert expected_service in {item.service_id for item in results}, (
            query,
            expected_service,
            [(item.rank, item.service_id, round(item.score, 3)) for item in results],
        )


if __name__ == "__main__":
    test_corpus_structure()
    test_unified_retrieval_offline()
    print("Unified corpus tests passed: 24 services across Absher, Balady, Najiz, and Sakani.")
