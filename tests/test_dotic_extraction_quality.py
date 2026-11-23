import pytest
from legal_bot.ingestion.dotic_extraction_quality import analyze_extraction, ExtractionQualityError

def sample(pages=None, complete=True):
    return {"phase":"10.4.7", "active_bank_write":False, "complete":complete,
            "source_pdf_sha256":"a"*64, "pages": pages if pages is not None else [
             {"page_number":1,"selected_text":"ماده ۱ ـ متن قانون\nتبصره ۲", "native_text":"ماده ۱ ـ متن قانون", "ocr_text":"", "likely_scanned_or_text_sparse":False},
             {"page_number":2,"selected_text":"فصل دوم\nماده ۲", "native_text":"فصل دوم\nماده ۲", "ocr_text":"", "likely_scanned_or_text_sparse":False}]}

def test_detects_article_and_section_markers_without_changing_text():
    r=analyze_extraction(sample()); assert len(r["article_and_paragraph_markers"]) == 3
    assert r["section_markers"][0]["label"] == "فصل"
    assert r["text_modified"] is False and r["active_bank_write"] is False

def test_flags_mixed_digits_and_unicode_replacement():
    d=sample([{"page_number":1,"selected_text":"ماده ۱۲3 \ufffd", "native_text":"", "ocr_text":"ماده ۱۲3 \ufffd"}])
    r=analyze_extraction(d); assert "unicode_replacement_characters" in r["page_quality"][0]["flags"]
    assert "mixed_digit_scripts_in_token" in r["page_quality"][0]["flags"]

def test_detects_missing_and_duplicate_pages():
    rows=[{"page_number":1,"selected_text":"متن یک"},{"page_number":3,"selected_text":"متن یک"}]
    r=analyze_extraction(sample(rows)); assert r["missing_page_numbers_within_extracted_range"] == [2]
    assert r["duplicate_text_pages"][0]["page_number"] == 3

def test_marks_ocr_and_sparse_pages_for_human_review():
    row={"page_number":1,"selected_text":"متن","native_text":"متن","ocr_text":"متن OCR","likely_scanned_or_text_sparse":True}
    r=analyze_extraction(sample([row])); assert r["page_quality"][0]["ocr_review_required"]
    assert r["page_quality"][0]["native_ocr_disagreement"]

def test_rejects_wrong_phase_and_unsafe_bank_flag():
    d=sample(); d["phase"]="10.4.6"
    with pytest.raises(ExtractionQualityError): analyze_extraction(d)
    d=sample(); d["active_bank_write"]=True
    with pytest.raises(ExtractionQualityError): analyze_extraction(d)
