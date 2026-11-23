# -*- coding: utf-8 -*-
"""Phase 10.2.3: resumable, page-budgeted PDF extraction/OCR staging.

The original PDF is immutable. Progress and page text live in a separate atomic
sidecar. This module never imports or modifies active legal JSON banks.
"""
from __future__ import annotations
import hashlib, json, os, tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .pdf_text_extractor import ExtractionPolicy


def _hash(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def _atomic_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=path.name + '.', suffix='.tmp', dir=str(path.parent))
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            json.dump(value, f, ensure_ascii=False, indent=2)
            f.flush(); os.fsync(f.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp): os.unlink(tmp)


def process_pdf_batch(pdf_path: str | Path, progress_path: str | Path, *,
                      max_pages: int = 20, expected_sha256: str | None = None,
                      min_chars_per_page: int = 40, run_ocr: bool = True) -> dict[str, Any]:
    """Process at most max_pages not-yet-processed pages; resume on next call.

    OCR is invoked only for sparse pages in the current batch. If OCR tooling or
    language data is unavailable, the batch remains pending and its cursor is
    not advanced, so pages cannot be silently marked complete.
    """
    if not 1 <= max_pages <= 20:
        raise ValueError('page_budget_must_be_between_1_and_20')
    source, sidecar = Path(pdf_path), Path(progress_path)
    if not source.is_file(): raise ValueError('pdf_not_found')
    digest = _hash(source)
    if expected_sha256 and digest != expected_sha256.lower(): raise ValueError('pdf_hash_mismatch')
    try:
        import fitz
    except ImportError as exc: raise ValueError('pymupdf_unavailable') from exc
    state = {'schema_version':'10.2.3','source_sha256':digest,'page_count':None,
             'next_page':1,'pages':{},'complete':False}
    if sidecar.exists():
        state = json.loads(sidecar.read_text(encoding='utf-8'))
        if state.get('schema_version') != '10.2.3' or state.get('source_sha256') != digest:
            raise ValueError('progress_sidecar_source_mismatch')
    doc = fitz.open(str(source))
    try:
        if doc.is_encrypted or doc.page_count < 1: raise ValueError('invalid_or_encrypted_pdf')
        if state['page_count'] is None: state['page_count'] = doc.page_count
        if state['page_count'] != doc.page_count: raise ValueError('pdf_page_count_changed')
        page_count = doc.page_count
        start = int(state['next_page'])
        if start > page_count:
            state['complete'] = True; _atomic_json(sidecar, state)
            return {'status':'complete','pages_processed':0,'next_page':start,'page_count':page_count,'source_sha256':digest}
        end = min(page_count, start + max_pages - 1)
        batch: list[dict[str, Any]] = []
        sparse: list[int] = []
        for page_no in range(start, end + 1):
            page = doc.load_page(page_no - 1)
            raw = page.get_text('dict', sort=True)
            blocks=[]
            for block in raw.get('blocks', []):
                if block.get('type') != 0: continue
                lines=[]
                for line in block.get('lines', []):
                    value=''.join(span.get('text','') for span in line.get('spans',[])).strip()
                    if value: lines.append(value)
                text='\n'.join(lines).strip()
                if text: blocks.append({'bbox':[round(float(v),2) for v in block.get('bbox',(0,0,0,0))],'text':text})
            page_text='\n'.join(b['text'] for b in blocks).strip()
            is_sparse=len(page_text) < min_chars_per_page
            if is_sparse: sparse.append(page_no)
            batch.append({'page_number':page_no,'text':page_text,'blocks':blocks,
                          'character_count':len(page_text),'likely_scanned_or_text_sparse':is_sparse,
                          'ocr_status':'not_required' if not is_sparse else 'pending'})
    finally: doc.close()
    # OCR selected pages only; do not advance the checkpoint on OCR failure.
    if sparse and run_ocr:
        from .persian_pdf_ocr import ocr_pdf_pages
        ocr_result = ocr_pdf_pages(source, page_numbers=sparse, expected_sha256=digest)
        ocr_by_page = {int(p['page_number']):p for p in ocr_result.pages}
        for row in batch:
            if row['page_number'] in ocr_by_page:
                ocr = ocr_by_page[row['page_number']]
                row.update({'ocr_text':ocr.get('text',''),'ocr_status':ocr.get('status'),
                            'ocr_confidence':ocr.get('mean_confidence'),
                            'ocr_provenance':ocr_result.provenance,
                            'ocr_warnings':ocr.get('warnings',[])})
    elif sparse:
        for row in batch:
            if row['page_number'] in sparse: row['ocr_status']='deferred_ocr'
    for row in batch: state['pages'][str(row['page_number'])] = row
    state['next_page'] = end + 1
    state['complete'] = end == page_count
    state['updated_at'] = datetime.now(timezone.utc).isoformat()
    _atomic_json(sidecar, state)
    return {'status':'complete' if state['complete'] else 'deferred',
            'pages_processed':len(batch),'pages_remaining':page_count-end,
            'next_page':state['next_page'],'page_count':page_count,
            'ocr_pages':[r['page_number'] for r in batch if r['ocr_status'] not in ('not_required','deferred_ocr')],
            'ocr_pending_pages':[r['page_number'] for r in batch if r['ocr_status']=='deferred_ocr'],
            'source_sha256':digest,'progress_path':str(sidecar)}


def acquire_pdf(url: str, *, storage_dir: str | Path, manifest_path: str | Path,
                allowed_hosts: set[str], policy: Any = None) -> dict[str, Any]:
    """Use the existing fail-closed downloader and persist a separate manifest."""
    from .secure_pdf_fetcher import SecurePDFDownloader, write_download_manifest
    downloader = SecurePDFDownloader(storage_dir, allowed_hosts=allowed_hosts, policy=policy)
    result = downloader.download(url)
    write_download_manifest(result, manifest_path)
    return result.to_dict()
