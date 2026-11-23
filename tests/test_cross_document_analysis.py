from legal_bot.cross_document_analysis import analyze_case_documents


def test_extracts_facts_from_multiple_documents_with_provenance():
    result = analyze_case_documents([
        {'id': 1, 'file_name': 'قرارداد.pdf', 'extracted_text': '[صفحه 2]\nمبلغ قرارداد ۱۰۰۰ ریال است.'},
        {'id': 2, 'file_name': 'الحاقیه.pdf', 'extracted_text': '[صفحه 4]\nمبلغ قرارداد ۲۰۰۰ ریال است.'},
    ])
    assert result['documents_analyzed'] == 2
    assert result['fact_count'] >= 2
    assert {x['document_id'] for x in result['facts']} == {1, 2}
    assert {x['file_name'] for x in result['facts']} == {'قرارداد.pdf', 'الحاقیه.pdf'}
    assert {x['page'] for x in result['facts']} == {2, 4}
    assert all(x['source_verified'] is False for x in result['facts'])


def test_different_amounts_are_review_candidates_not_asserted_contradictions():
    result = analyze_case_documents([
        {'id': 1, 'file_name': 'الف.pdf', 'extracted_text': 'مبلغ قرارداد ۱۰۰۰ ریال است.'},
        {'id': 2, 'file_name': 'ب.pdf', 'extracted_text': 'مبلغ قرارداد ۲۰۰۰ ریال است.'},
    ])
    assert result['comparison_candidate_count'] == 1
    candidate = result['comparison_candidates'][0]
    assert candidate['status'] == 'comparison_candidate'
    assert 'تناقض را ثابت نمی‌کند' in candidate['warning']


def test_same_value_across_documents_is_not_flagged_as_difference():
    result = analyze_case_documents([
        {'id': 1, 'file_name': 'الف.pdf', 'extracted_text': 'مبلغ ۱۰۰۰ ریال'},
        {'id': 2, 'file_name': 'ب.pdf', 'extracted_text': 'مبلغ ۱۰۰۰ ریال'},
    ])
    assert result['comparison_candidate_count'] == 0


def test_documents_without_text_are_reported_as_skipped():
    result = analyze_case_documents([
        {'id': 1, 'file_name': 'اسکن.pdf', 'extracted_text': ''},
        {'id': 2, 'file_name': 'متن.pdf', 'extracted_text': 'مبلغ ۵۰۰ ریال'},
    ])
    assert result['documents_analyzed'] == 1
    assert result['documents_skipped'][0]['document_id'] == 1


def test_differences_within_one_document_are_not_cross_document_candidates():
    result = analyze_case_documents([
        {'id': 1, 'file_name': 'یک.pdf', 'extracted_text': 'مبلغ ۱۰۰ ریال و مبلغ ۲۰۰ ریال'},
    ])
    assert result['comparison_candidate_count'] == 0


def test_same_normalized_amount_is_reported_as_cross_document_match():
    result = analyze_case_documents([
        {'id': 1, 'file_name': 'قرارداد.pdf', 'extracted_text': 'مبلغ قرارداد ۱۰۰۰ ریال است.'},
        {'id': 2, 'file_name': 'رسید.pdf', 'extracted_text': 'مبلغ پرداختی ۱۰۰۰ ریال است.'},
    ])
    assert result['matched_value_count'] == 1
    match = result['matched_values'][0]
    assert match['status'] == 'same_value_found'
    assert match['source_document_count'] == 2
    assert len(match['sources']) == 2


def test_document_limit_is_reported_and_never_exceeds_limit():
    docs = [
        {'id': i, 'file_name': f'{i}.txt', 'extracted_text': f'مبلغ {i + 100} ریال'}
        for i in range(4)
    ]
    result = analyze_case_documents(docs, max_documents=2)
    assert result['documents_received'] == 4
    assert result['documents_considered'] == 2
    assert result['documents_omitted_by_limit'] == 2
    assert result['documents_analyzed'] == 2


def test_fact_counts_are_structured_and_source_verified_is_false():
    result = analyze_case_documents([
        {'id': 1, 'file_name': 'سند.txt', 'extracted_text': 'تاریخ قرارداد ۱۴۰۲/۰۱/۰۵ و مبلغ ۵۰۰ تومان'},
    ])
    assert result['fact_counts']['date'] >= 1
    assert result['fact_counts']['amount'] >= 1
    assert all(f['source_verified'] is False for f in result['facts'])
    assert result['review_required'] is True


def test_text_budget_is_enforced_and_truncation_is_visible():
    result = analyze_case_documents([
        {'id': 1, 'file_name': 'بلند.txt', 'extracted_text': 'مبلغ ۱۰۰ ریال ' + ('الف' * 2000)},
        {'id': 2, 'file_name': 'بعدی.txt', 'extracted_text': 'مبلغ ۲۰۰ ریال'},
    ], max_chars_per_document=1200, max_total_chars=1200)
    assert result['characters_processed'] == 1200
    assert result['documents_truncated'] == 1
    assert result['document_summaries'][0]['status'] == 'analyzed_truncated'
    assert result['document_summaries'][1]['status'] == 'limit_skipped'
    assert result['documents_skipped'][0]['document_id'] == 2
    assert result['documents_skipped_by_text_budget'] == 1


def test_missing_document_ids_do_not_merge_distinct_sources():
    result = analyze_case_documents([
        {'file_name': 'الف.txt', 'extracted_text': 'مبلغ ۱۰۰ ریال'},
        {'file_name': 'ب.txt', 'extracted_text': 'مبلغ ۲۰۰ ریال'},
    ])
    assert result['comparison_candidate_count'] == 1
    assert result['comparison_candidates'][0]['source_document_count'] == 2


def test_analysis_limits_are_clamped_to_safe_ranges():
    result = analyze_case_documents([
        {'id': 1, 'file_name': 'الف.txt', 'extracted_text': 'مبلغ ۱۰۰ ریال'},
    ], max_documents=0, max_facts_per_document=0,
       max_chars_per_document=1, max_total_chars=1)
    assert result['documents_considered'] == 1
    assert result['character_limit'] >= 1000
    assert result['fact_count'] >= 1


def test_ambiguous_punctuated_amounts_are_not_auto_matched():
    result = analyze_case_documents([
        {'id': 1, 'file_name': 'الف.txt', 'extracted_text': 'مبلغ ۱.۰۰۰ ریال'},
        {'id': 2, 'file_name': 'ب.txt', 'extracted_text': 'مبلغ ۱۰۰۰ ریال'},
    ])
    assert result['matched_value_count'] == 0
    assert result['comparison_candidate_count'] == 0
    assert result['fact_count'] >= 2
