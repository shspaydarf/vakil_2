import hashlib
import pytest
from legal_bot.ingestion.dotic_legal_identity import classify_extraction, LegalIdentityError

HASH = hashlib.sha256(b'pdf').hexdigest()
def sample(text, complete=True):
    return {'phase':'10.4.7','source_pdf_sha256':HASH,'source_url':'https://dotic.ir/sample',
            'complete':complete,'pages':[{'page_number':1,'selected_text':text}],
            'legal_authenticity_verified':False,'active_bank_write':False}

def test_classifies_and_creates_identity_only_with_complete_unambiguous_metadata():
    data = sample('قانون مصوب مجلس شورای اسلامی شماره ۱۲۳۴ تاریخ ۱۴۰۴/۰۲/۰۳')
    result = classify_extraction(data)
    assert result['proposed_document_kind'] == 'parliamentary_law'
    assert result['proposed_issuer'] == 'parliament'
    assert result['stable_document_id_proposal'].startswith('IR-')
    assert result['active_bank_write'] is False
    assert result['legal_authenticity_verified'] is False

def test_missing_number_withholds_stable_id():
    result = classify_extraction(sample('قانون مصوب مجلس شورای اسلامی تاریخ ۱۴۰۴/۰۲/۰۳'))
    assert result['stable_document_id_proposal'] is None
    assert 'official_number' in result['identity_fields_missing']

def test_multiple_dates_are_ambiguous():
    result = classify_extraction(sample('قانون مصوب مجلس شورای اسلامی شماره ۱۲۳ تاریخ ۱۴۰۴/۰۲/۰۳ و ۱۴۰۳/۰۱/۰۱'))
    assert result['stable_document_id_proposal'] is None
    assert 'multiple_date_candidates' in result['ambiguity_flags']

def test_incomplete_extraction_withholds_identity():
    result = classify_extraction(sample('قانون مصوب مجلس شورای اسلامی شماره ۱۲۳ تاریخ ۱۴۰۴/۰۲/۰۳', False))
    assert result['stable_document_id_proposal'] is None
    assert 'extraction_incomplete' in result['ambiguity_flags']

def test_rejects_active_bank_or_authenticity_claim():
    data = sample('قانون مصوب مجلس شورای اسلامی شماره ۱۲۳ تاریخ ۱۴۰۴/۰۲/۰۳')
    data['active_bank_write'] = True
    with pytest.raises(LegalIdentityError): classify_extraction(data)

def test_quality_report_must_match_pdf_hash():
    data = sample('قانون مصوب مجلس شورای اسلامی شماره ۱۲۳ تاریخ ۱۴۰۴/۰۲/۰۳')
    with pytest.raises(LegalIdentityError): classify_extraction(data, {'phase':'10.4.8','source_pdf_sha256':'0'*64})
