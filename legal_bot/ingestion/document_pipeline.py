# -*- coding: utf-8 -*-
"""Controlled end-to-end PDF staging pipeline (Phase 3.7).

This pipeline creates sidecar artifacts only. It never changes the source PDF,
queue state, or active legal JSON bank.
"""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .pdf_text_extractor import ExtractionPolicy, extract_pdf_text, write_extraction_json
from .persian_pdf_ocr import OCRPolicy, ocr_pdf_pages, write_ocr_json
from .legal_structure_parser import parse_legal_structure, write_legal_structure_json
from .legal_text_normalizer import NormalizationPolicy, normalize_legal_document, write_normalization_json

PIPELINE_VERSION = "3.7.0"


class DocumentPipelineError(ValueError):
    """Raised when a pipeline stage fails or inputs are inconsistent."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(payload, stream, ensure_ascii=False, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp_name, path)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)


@dataclass(frozen=True)
class PipelineResult:
    pipeline_version: str
    source_path: str
    source_sha256: str
    output_dir: str
    page_count: int
    ocr_page_numbers: list[int]
    stage_status: dict[str, str]
    artifacts: dict[str, str]
    review_required: bool
    active_bank_imported: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def process_pdf_document(
    pdf_path: str | Path,
    output_dir: str | Path,
    *,
    document_type: str = "unknown",
    extraction_policy: ExtractionPolicy | None = None,
    ocr_policy: OCRPolicy | None = None,
    normalization_policy: NormalizationPolicy | None = None,
    run_ocr: bool = True,
) -> PipelineResult:
    """Run extraction -> selective OCR -> structure parsing -> normalization.

    OCR is run only for pages flagged as text-sparse by Phase 3.3. A non-empty
    OCR result replaces text for that page; empty OCR never erases existing text.
    Every page retains provenance and original extraction text in sidecar JSON.
    """
    source = Path(pdf_path)
    target = Path(output_dir)
    if not source.is_file():
        raise DocumentPipelineError("فایل PDF ورودی پیدا نشد")
    if source.suffix.lower() != ".pdf":
        raise DocumentPipelineError("پسوند فایل ورودی PDF نیست")
    target.mkdir(parents=True, exist_ok=True)
    source_hash = _sha256(source)
    stage_status: dict[str, str] = {}
    artifacts: dict[str, str] = {}

    try:
        extraction = extract_pdf_text(source, policy=extraction_policy, expected_sha256=source_hash)
        extraction_path = target / "01_extraction.json"
        write_extraction_json(extraction, extraction_path)
        artifacts["extraction"] = extraction_path.name
        stage_status["pdf_text_extraction"] = "completed"

        merged_pages = []
        for page in extraction.pages:
            merged_pages.append({
                "page_number": page["page_number"],
                "text": page.get("text", ""),
                "provenance": "pdf_text_extraction",
                "extraction_text": page.get("text", ""),
            })

        ocr_pages: list[int] = []
        if extraction.scan_or_ocr_page_numbers and run_ocr:
            ocr_result = ocr_pdf_pages(
                source, page_numbers=extraction.scan_or_ocr_page_numbers,
                policy=ocr_policy, expected_sha256=source_hash,
            )
            ocr_path = target / "02_ocr.json"
            write_ocr_json(ocr_result, ocr_path)
            artifacts["ocr"] = ocr_path.name
            ocr_by_page = {int(row["page_number"]): row for row in ocr_result.pages}
            for page in merged_pages:
                row = ocr_by_page.get(page["page_number"])
                if row and str(row.get("text", "")).strip():
                    page["text"] = row["text"]
                    page["provenance"] = "tesseract_ocr_machine_generated"
                    page["ocr_status"] = row.get("status")
                    page["ocr_mean_confidence"] = row.get("mean_confidence")
                    page["ocr_warnings"] = row.get("warnings", [])
                elif row:
                    page["ocr_status"] = row.get("status", "empty_result")
                    page["ocr_warnings"] = row.get("warnings", [])
            ocr_pages = list(ocr_result.ocr_pages)
            stage_status["persian_ocr"] = "completed_with_review" if ocr_result.review_required else "completed"
        elif extraction.scan_or_ocr_page_numbers:
            stage_status["persian_ocr"] = "skipped_by_configuration"
        else:
            stage_status["persian_ocr"] = "not_required"

        # Keep the full page set and ensure stable 1-based sequential numbering.
        if len(merged_pages) != extraction.page_count or [p["page_number"] for p in merged_pages] != list(range(1, extraction.page_count + 1)):
            raise DocumentPipelineError("توالی صفحات پس از ادغام استخراج و OCR ناسازگار است")

        structure = parse_legal_structure(merged_pages, source_sha256=source_hash, document_type=document_type)
        structure_path = target / "03_legal_structure.json"
        write_legal_structure_json(structure, structure_path)
        artifacts["legal_structure"] = structure_path.name
        stage_status["legal_structure_parsing"] = "completed_with_review"

        normalized = normalize_legal_document(
            merged_pages, source_sha256=source_hash,
            policy=normalization_policy, structure=structure.to_dict(),
        )
        normalized_path = target / "04_normalized_text.json"
        write_normalization_json(normalized, normalized_path)
        artifacts["normalized_text"] = normalized_path.name
        stage_status["text_normalization"] = "completed"

        final_payload = {
            "schema_version": "1.0",
            "pipeline_version": PIPELINE_VERSION,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "source": {"path": str(source.resolve()), "sha256": source_hash, "page_count": extraction.page_count},
            "pages": merged_pages,
            "document_text": normalized.document_text,
            "structure": structure.to_dict(),
            "normalized": normalized.to_dict(),
            "ocr_page_numbers": ocr_pages,
            "review_required": True,
            "imported_to_active_legal_bank": False,
            "warnings": [
                "خروجی استخراج و OCR ماشین‌ساخته است و صحت حقوقی یا اعتبار سند را تأیید نمی‌کند.",
                "ورود به بانک فعال قوانین در این مرحله انجام نمی‌شود.",
            ],
        }
        final_path = target / "05_staging_document.json"
        _atomic_json(final_path, final_payload)
        artifacts["staging_document"] = final_path.name
        stage_status["staging_package"] = "completed_review_required"

        # Hash all generated artifacts except the manifest itself.
        artifact_hashes = {key: _sha256(target / name) for key, name in artifacts.items()}
        manifest = PipelineResult(
            pipeline_version=PIPELINE_VERSION, source_path=str(source.resolve()),
            source_sha256=source_hash, output_dir=str(target.resolve()),
            page_count=extraction.page_count, ocr_page_numbers=ocr_pages,
            stage_status=stage_status, artifacts=artifacts, review_required=True,
        )
        manifest_payload = manifest.to_dict()
        manifest_payload["artifact_sha256"] = artifact_hashes
        manifest_path = target / "manifest.json"
        _atomic_json(manifest_path, manifest_payload)
        return manifest
    except DocumentPipelineError:
        raise
    except Exception as exc:
        raise DocumentPipelineError(f"پردازش سند در یکی از مراحل ناموفق بود: {type(exc).__name__}: {exc}") from exc
