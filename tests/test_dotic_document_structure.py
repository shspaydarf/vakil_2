import pytest
from legal_bot.ingestion.dotic_document_structure import segment_text, structure_extraction, DocumentStructureError

def test_segments_articles_notes_and_clauses_with_parent():
    result = segment_text('ماده ۱۲ ـ متن ماده\nتبصره ۱ ـ متن تبصره\nبند الف ـ متن بند')
    assert [x['type'] for x in result['segments']] == ['article', 'note', 'clause']
    assert result['segments'][1]['parent_article'] == '12'
    assert result['segments'][2]['parent_article'] == '12'

def test_preserves_exact_text_and_offsets():
    text = 'ماده ۱ ـ متن\n  ادامه متن  '
    result = segment_text(text)
    for item in result['segments']:
        assert text[item['start']:item['end']] == item['text']

def test_detects_appendix_chapter_and_signature():
    result = segment_text('فصل اول\nپیوست ۲ ـ جدول\nامضا: وزیر')
    assert [x['type'] for x in result['segments']] == ['chapter', 'appendix', 'signature']

def test_rejects_wrong_phase_and_active_bank_flags():
    with pytest.raises(DocumentStructureError):
        structure_extraction({'phase':'10.4.8'})
    bad = {'phase':'10.4.7','active_bank_write':True,'legal_authenticity_verified':False,
           'source_pdf_sha256':'a'*64,'pages':[{'selected_text':'ماده ۱'}]}
    with pytest.raises(DocumentStructureError): structure_extraction(bad)

def test_output_stays_quarantined_and_requires_review():
    data = {'phase':'10.4.7','active_bank_write':False,'legal_authenticity_verified':False,
            'source_pdf_sha256':'a'*64,'pages':[{'page_number':1,'selected_text':'ماده ۱ ـ متن'}]}
    result = structure_extraction(data)
    assert result['phase'] == '10.4.10'
    assert result['active_bank_write'] is False
    assert result['human_review_required'] is True
