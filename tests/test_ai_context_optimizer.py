from legal_bot.ai_context_optimizer import select_records, select_document_pages, query_terms


def test_select_records_prefers_question_relevant_complete_records_and_keeps_order():
    rows = [
        {'text': 'موضوع اجاره و تخلیه', 'source_pages': [1]},
        {'text': 'موضوع چک و مطالبه وجه', 'source_pages': [2]},
        {'text': 'موضوع اجاره و تمدید قرارداد', 'source_pages': [3]},
    ]
    selected, audit = select_records(rows, 'اختلاف درباره اجاره و تخلیه', max_items=2, char_budget=1000)
    assert selected == [rows[0], rows[2]]
    assert audit['strategy'] == 'question_relevance'
    assert audit['matched'] == 2
    assert selected[0]['source_pages'] == [1]


def test_select_records_safe_fallback_when_no_lexical_match():
    rows = [{'text': 'اول'}, {'text': 'دوم'}, {'text': 'سوم'}]
    selected, audit = select_records(rows, 'پرسش نامرتبط', max_items=2, char_budget=1000)
    assert selected == rows[:2]
    assert audit['strategy'] == 'safe_fallback'


def test_document_page_selection_keeps_original_page_markers_and_order():
    text = ('[صفحه ۱]\nمتن درباره اجاره و تخلیه\n' * 1) + ('[صفحه ۲]\nمتن درباره چک و سفته\n') + ('[صفحه ۳]\nمدارک اجاره و تخلیه\n')
    selected, audit = select_document_pages(text, 'اجاره تخلیه', max_pages=2)
    assert '[صفحه ۱]' in selected and '[صفحه ۳]' in selected
    assert '[صفحه ۲]' not in selected
    assert audit['selected_pages'] == [1, 3]
    assert audit['strategy'] == 'question_relevance_pages'


def test_question_terms_normalize_arabic_and_persian_forms():
    assert 'علی' in query_terms('علي درباره قرارداد')
