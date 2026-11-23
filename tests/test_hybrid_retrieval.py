from legal_bot.hybrid_retrieval import score_text, normalize, terms
from legal_bot.ai_context_optimizer import select_document_pages, select_records


def test_normalization_handles_persian_arabic_letters_and_digits():
    assert normalize("مستأجر ۱۲۳ ك") == "مستاجر 123 ک"


def test_hybrid_retrieval_recovers_small_ocr_or_typing_variation():
    result = score_text("مستاجر", "مستأجر متعهد به پرداخت اجاره است")
    assert result["score"] > 0.5


def test_legal_concepts_that_are_not_synonyms_are_not_collapsed():
    assert terms("فسخ") != terms("انفساخ")
    assert score_text("فسخ قرارداد", "انفساخ قرارداد") ["score"] < 0.8


def test_page_selection_uses_hybrid_matching_and_keeps_source_page_labels():
    text = (
        "[صفحه ۱]\nمستأجر مکلف به پرداخت اجاره‌بها است.\n"
        "[صفحه ۲]\nشرایط فسخ قرارداد در این صفحه آمده است.\n"
        "[صفحه ۳]\nمستاجر باید اجاره را در موعد مقرر بپردازد.\n"
    )
    selected, audit = select_document_pages(text, "تعهد مستاجر در پرداخت اجاره", max_pages=2)
    assert "[صفحه ۱]" in selected
    assert "[صفحه ۳]" in selected
    assert "[صفحه ۲]" not in selected
    assert audit["retrieval"] == "offline_hybrid_lexical_fuzzy"
    assert audit["selected_pages"] == [1, 3]


def test_record_selection_reports_hybrid_and_preserves_complete_records():
    rows = [
        {"text": "تعهد مستأجر به پرداخت اجاره", "source_pages": [4]},
        {"text": "شرایط فسخ قرارداد", "source_pages": [9]},
    ]
    selected, audit = select_records(rows, "پرداخت اجاره مستاجر", max_items=1, char_budget=1000)
    assert selected == [rows[0]]
    assert selected[0]["source_pages"] == [4]
    assert audit["retrieval"] == "offline_hybrid_lexical_fuzzy"


def test_weak_match_keeps_safe_fallback_instead_of_narrowing_context():
    rows = [{"text": "مدرک اول"}, {"text": "مدرک دوم"}]
    selected, audit = select_records(rows, "موضوع کاملاً متفاوت", max_items=1, char_budget=1000)
    assert selected == rows[:1]
    assert audit["strategy"] == "safe_fallback"
