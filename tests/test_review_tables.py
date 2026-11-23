from legal_bot.review_tables import build_review_table


def test_review_table_collects_contract_clauses_with_document_and_page_sources():
    result = build_review_table([
        {'id': 12, 'file_name': 'قرارداد.pdf', 'extracted_text': '[صفحه ۳]\nمبلغ قرارداد ۵۰۰ میلیون ریال است. نحوه پرداخت طی سه قسط انجام می‌شود. در صورت تخلف حق فسخ وجود دارد. اختلاف از طریق داوری حل می‌شود.'}
    ])
    assert result['row_count'] == 1
    row = result['rows'][0]
    assert row['cells']['amount']['status'] == 'found'
    assert row['cells']['payment']['status'] == 'found'
    assert row['cells']['termination']['status'] == 'found'
    assert row['cells']['disputes']['sources'][0]['document_id'] == 12
    assert row['cells']['disputes']['sources'][0]['page'] == 3
    assert row['cells']['disputes']['sources'][0]['source_verified'] is False


def test_review_table_keeps_unknown_fields_unknown_and_reports_truncation():
    result = build_review_table([
        {'id': 1, 'file_name': 'سند.txt', 'extracted_text': 'صرفاً یک متن عمومی بدون شرط مشخص' + ('الف' * 1500)}
    ], max_chars_per_document=1000)
    row = result['rows'][0]
    assert row['cells']['guarantees']['status'] == 'not_found'
    assert row['cells']['guarantees']['value'] == ''
    assert row['truncated'] is True
    assert result['review_required'] is True


def test_review_table_does_not_include_documents_without_extracted_text():
    result = build_review_table([{'id': 1, 'file_name': 'scan.pdf', 'extracted_text': ''}])
    assert result['row_count'] == 0
