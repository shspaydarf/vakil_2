import json
from pathlib import Path
import pytest
from legal_bot.ingestion import dotic_pipeline as pipeline


def _manifest(path: Path):
    value = {'phase': '10.4.6', 'active_bank_write': False,
             'legal_authenticity_verified': False, 'sha256': 'a' * 64}
    path.write_text(json.dumps(value), encoding='utf-8')
    return path


def test_pipeline_rejects_non_quarantine_manifest(tmp_path):
    p = tmp_path / 'bad.json'
    p.write_text(json.dumps({'phase': '10.4.6', 'active_bank_write': True}), encoding='utf-8')
    with pytest.raises(pipeline.DoticPipelineError):
        pipeline.run_quarantined_pipeline(p)


def test_pipeline_rejects_wrong_phase(tmp_path):
    p = tmp_path / 'bad.json'
    p.write_text(json.dumps({'phase': '10.4.5', 'active_bank_write': False,
                             'legal_authenticity_verified': False}), encoding='utf-8')
    with pytest.raises(pipeline.DoticPipelineError):
        pipeline.run_quarantined_pipeline(p)


def test_pipeline_orchestrates_outputs_and_never_approves(tmp_path, monkeypatch):
    manifest = _manifest(tmp_path / 'manifest.json')
    digest = 'a' * 64
    extraction = {'phase': '10.4.7', 'source_pdf_sha256': digest,
                  'source_url': 'https://dotic.ir/example.pdf', 'complete': True,
                  'page_count': 1, 'pages_extracted_so_far': 1, 'next_page': None,
                  'pages': [{'page_number': 1, 'selected_text': 'ماده ۱\nمتن ماده',
                             'native_text': 'ماده ۱\nمتن ماده', 'ocr_text': '',
                             'likely_scanned_or_text_sparse': False}],
                  'active_bank_write': False, 'legal_authenticity_verified': False}
    quality = {'phase': '10.4.8', 'source_pdf_sha256': digest,
               'average_page_quality_score': 98, 'flagged_pages': [], 'review_required': False}
    identity = {'phase': '10.4.9', 'source_pdf_sha256': digest,
                'identity_status': 'identity_incomplete_or_ambiguous',
                'stable_document_id_proposal': None, 'human_review_required': True}
    structure = {'phase': '10.4.10', 'source_pdf_sha256': digest,
                 'pages': [{'segment_count': 1}], 'active_bank_write': False}
    monkeypatch.setattr(pipeline, 'run_extraction', lambda *a, **k: extraction)
    monkeypatch.setattr(pipeline, 'analyze_extraction', lambda x: quality)
    monkeypatch.setattr(pipeline, 'classify_extraction', lambda x, q: identity)
    monkeypatch.setattr(pipeline, 'structure_extraction', lambda x, i: structure)
    result = pipeline.run_quarantined_pipeline(manifest, output_dir=tmp_path / 'out')
    assert result['decision'] == 'quarantine_review_required'
    assert result['active_bank_write'] is False
    assert result['legal_authenticity_verified'] is False
    assert result['network_access_performed'] is False
    assert Path(result['report_path']).is_file()
    for key in ('extraction', 'quality', 'identity', 'structure'):
        assert Path(result['artifacts'][key]).is_file()


def test_pipeline_marks_partial_extraction_resumable(tmp_path, monkeypatch):
    manifest = _manifest(tmp_path / 'manifest.json')
    digest = 'b' * 64
    extraction = {'phase': '10.4.7', 'source_pdf_sha256': digest,
                  'source_url': 'https://dotic.ir/example.pdf', 'complete': False,
                  'page_count': 25, 'pages_extracted_so_far': 20, 'next_page': 21,
                  'pages': [{'page_number': 1, 'selected_text': 'متن', 'native_text': 'متن',
                             'ocr_text': '', 'likely_scanned_or_text_sparse': False}],
                  'active_bank_write': False, 'legal_authenticity_verified': False}
    quality = {'phase': '10.4.8', 'source_pdf_sha256': digest,
               'average_page_quality_score': 90, 'flagged_pages': [], 'review_required': False}
    identity = {'phase': '10.4.9', 'source_pdf_sha256': digest,
                'identity_status': 'identity_incomplete_or_ambiguous',
                'stable_document_id_proposal': None, 'human_review_required': True}
    structure = {'phase': '10.4.10', 'source_pdf_sha256': digest, 'pages': []}
    monkeypatch.setattr(pipeline, 'run_extraction', lambda *a, **k: extraction)
    monkeypatch.setattr(pipeline, 'analyze_extraction', lambda x: quality)
    monkeypatch.setattr(pipeline, 'classify_extraction', lambda x, q: identity)
    monkeypatch.setattr(pipeline, 'structure_extraction', lambda x, i: structure)
    result = pipeline.run_quarantined_pipeline(manifest, output_dir=tmp_path / 'out')
    assert result['decision'] == 'quarantine_partial_resumable'
    assert result['next_page'] == 21
    assert result['human_review_required'] is True
