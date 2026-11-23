# -*- coding: utf-8 -*-
"""Phase 10.4.11: offline orchestration of the quarantined Dotic PDF pipeline.

Consumes an operator-supplied quarantine manifest/PDF. No network access,
no automatic legal approval, and no active-bank or staging-registry writes.
"""
from __future__ import annotations
import argparse, json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from legal_bot.ingestion.dotic_pdf_extraction import run_extraction
from legal_bot.ingestion.dotic_extraction_quality import analyze_extraction
from legal_bot.ingestion.dotic_legal_identity import classify_extraction
from legal_bot.ingestion.dotic_document_structure import structure_extraction

class DoticPipelineError(ValueError):
    pass

def run_quarantined_pipeline(manifest_path: str | Path, *, pdf_path: str | Path | None = None,
                             output_dir: str | Path | None = None, max_pages: int = 20,
                             run_ocr: bool = False) -> dict[str, Any]:
    manifest_file = Path(manifest_path)
    if not manifest_file.is_file():
        raise DoticPipelineError('مانیفست قرنطینه پیدا نشد')
    try:
        manifest = json.loads(manifest_file.read_text(encoding='utf-8'))
    except Exception as exc:
        raise DoticPipelineError('مانیفست JSON معتبر نیست') from exc
    if manifest.get('phase') != '10.4.6' or manifest.get('active_bank_write') is not False:
        raise DoticPipelineError('فقط مانیفست قرنطینه فاز ۱۰.۴.۶ پذیرفته می‌شود')
    if manifest.get('legal_authenticity_verified') is not False:
        raise DoticPipelineError('مانیفست نباید اصالت حقوقی را تأییدشده اعلام کند')
    root = Path(output_dir) if output_dir else manifest_file.parent / 'pipeline'
    root.mkdir(parents=True, exist_ok=True)
    extraction_path = root / 'extraction.json'
    quality_path = root / 'quality.json'
    identity_path = root / 'identity.json'
    structure_path = root / 'structure.json'
    try:
        extraction = run_extraction(manifest_file, pdf_path=pdf_path,
                                    progress_path=root / 'progress.json',
                                    output_path=extraction_path, max_pages=max_pages,
                                    run_ocr=run_ocr)
        extraction_path.write_text(json.dumps(extraction, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        quality = analyze_extraction(extraction)
        quality_path.write_text(json.dumps(quality, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        identity = classify_extraction(extraction, quality)
        identity_path.write_text(json.dumps(identity, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        structure = structure_extraction(extraction, identity)
        structure_path.write_text(json.dumps(structure, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    except Exception as exc:
        raise DoticPipelineError(f'زنجیره در این نقطه متوقف شد: {type(exc).__name__}: {exc}') from exc
    complete = bool(extraction.get('complete'))
    review_flags = list(quality.get('flagged_pages', []))
    review_required = bool(identity.get('human_review_required', True) or review_flags or not complete)
    report = {
        'phase': '10.4.11', 'source_pdf_sha256': extraction['source_pdf_sha256'],
        'source_url': extraction.get('source_url'), 'pages_extracted': extraction.get('pages_extracted_so_far'),
        'pdf_page_count': extraction.get('page_count'), 'extraction_complete': complete,
        'next_page': extraction.get('next_page'), 'ocr_requested': bool(run_ocr),
        'quality_score': quality.get('average_page_quality_score'),
        'quality_flagged_pages': review_flags,
        'identity_status': identity.get('identity_status'),
        'stable_document_id_proposal': identity.get('stable_document_id_proposal'),
        'structure_segment_count': sum(p.get('segment_count', 0) for p in structure.get('pages', [])),
        'human_review_required': review_required,
        'legal_authenticity_verified': False, 'legal_status_verified': False,
        'active_bank_write': False, 'staging_registry_write': False,
        'network_access_performed': False,
        'decision': 'quarantine_review_required' if complete else 'quarantine_partial_resumable',
        'artifacts': {'extraction': str(extraction_path), 'quality': str(quality_path),
                      'identity': str(identity_path), 'structure': str(structure_path),
                      'progress': str(root / 'progress.json')},
        'generated_at': datetime.now(timezone.utc).isoformat(),
    }
    report_path = root / 'pipeline-report.json'
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    report['report_path'] = str(report_path)
    return report

def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', required=True)
    parser.add_argument('--pdf-file')
    parser.add_argument('--output-dir')
    parser.add_argument('--max-pages', type=int, default=20)
    parser.add_argument('--ocr', action='store_true')
    args = parser.parse_args(argv)
    result = run_quarantined_pipeline(args.manifest, pdf_path=args.pdf_file,
                                      output_dir=args.output_dir, max_pages=args.max_pages,
                                      run_ocr=args.ocr)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
