import hashlib
import json
import pytest

fitz = pytest.importorskip('fitz')
from legal_bot.ingestion.staged_pdf_processor import process_pdf_batch


def make_pdf(path, count=25):
    doc=fitz.open()
    for i in range(count):
        page=doc.new_page()
        page.insert_text((72,72), f'صفحه آزمایشی شماره {i+1} متن کافی برای آزمون استخراج و ادامه پردازش سند حقوقی.')
    doc.save(path); doc.close()


def test_pdf_is_processed_in_resumable_twenty_page_batches(tmp_path):
    pdf=tmp_path/'sample.pdf'; sidecar=tmp_path/'progress.json'; make_pdf(pdf,25)
    digest=hashlib.sha256(pdf.read_bytes()).hexdigest()
    first=process_pdf_batch(pdf,sidecar,max_pages=20,expected_sha256=digest,run_ocr=False)
    assert first['status']=='deferred' and first['pages_processed']==20
    state=json.loads(sidecar.read_text())
    assert state['next_page']==21 and len(state['pages'])==20
    second=process_pdf_batch(pdf,sidecar,max_pages=20,expected_sha256=digest,run_ocr=False)
    assert second['status']=='complete' and second['pages_processed']==5
    state=json.loads(sidecar.read_text())
    assert state['next_page']==26 and len(state['pages'])==25 and state['complete'] is True


def test_pdf_hash_mismatch_rejects_resume(tmp_path):
    pdf=tmp_path/'sample.pdf'; sidecar=tmp_path/'progress.json'; make_pdf(pdf,2)
    process_pdf_batch(pdf,sidecar,max_pages=1,run_ocr=False)
    with pdf.open('ab') as f: f.write(b'changed')
    with pytest.raises(ValueError, match='progress_sidecar_source_mismatch'):
        process_pdf_batch(pdf,sidecar,max_pages=1,run_ocr=False)


def test_page_budget_cannot_exceed_twenty(tmp_path):
    pdf=tmp_path/'sample.pdf'; make_pdf(pdf,1)
    with pytest.raises(ValueError, match='page_budget'):
        process_pdf_batch(pdf,tmp_path/'p.json',max_pages=21,run_ocr=False)
