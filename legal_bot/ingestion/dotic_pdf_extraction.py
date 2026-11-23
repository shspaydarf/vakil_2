# -*- coding: utf-8 -*-
"""Phase 10.4.7: bounded, page-preserving extraction for quarantined Dotic PDFs.

No network access, no legal-status inference, and no active-bank/staging import.
Each invocation processes at most 20 pages and can be resumed using its sidecar.
OCR is opt-in; sparse pages remain explicitly pending when it is not requested.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .staged_pdf_processor import process_pdf_batch


class DoticExtractionError(ValueError):
    pass


def _load_manifest(path: str | Path) -> dict[str, Any]:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception as exc:
        raise DoticExtractionError("مانیفست قرنطینه قابل خواندن نیست") from exc
    if not isinstance(value, dict) or value.get("phase") != "10.4.6":
        raise DoticExtractionError("مانیفست معتبر فاز ۱۰.۴.۶ لازم است")
    if value.get("technical_validation") != "passed":
        raise DoticExtractionError("اعتبارسنجی فنی PDF در مانیفست تأیید نشده است")
    if value.get("legal_authenticity_verified") is not False or value.get("active_bank_write") is not False:
        raise DoticExtractionError("وضعیت ایمنی مانیفست قابل قبول نیست")
    return value


def _atomic_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(tmp_name, path)
    finally:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)


def run_extraction(manifest_path: str | Path, *, pdf_path: str | Path | None = None,
                   progress_path: str | Path | None = None, output_path: str | Path | None = None,
                   max_pages: int = 20, run_ocr: bool = False) -> dict[str, Any]:
    if not 1 <= int(max_pages) <= 20:
        raise DoticExtractionError("بودجه هر اجرا باید بین ۱ تا ۲۰ صفحه باشد")
    manifest_file = Path(manifest_path)
    manifest = _load_manifest(manifest_file)
    source = Path(pdf_path or manifest.get("stored_original", ""))
    if not source.is_file():
        raise DoticExtractionError("فایل اصلی PDF قرنطینه پیدا نشد")
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    expected = str(manifest.get("sha256", "")).lower()
    if not expected or digest != expected:
        raise DoticExtractionError("هش PDF با مانیفست قرنطینه مطابقت ندارد")

    base_dir = manifest_file.parent
    progress = Path(progress_path) if progress_path else base_dir / f"{digest}.extraction-progress.json"
    output = Path(output_path) if output_path else base_dir / f"{digest}.extracted.json"
    try:
        batch_result = process_pdf_batch(
            source, progress, max_pages=max_pages, expected_sha256=expected,
            run_ocr=run_ocr,
        )
    except Exception as exc:
        # In particular, OCR dependency/language failures are surfaced and the
        # staged processor keeps its cursor unchanged on OCR failure.
        raise DoticExtractionError(f"پردازش PDF متوقف شد: {type(exc).__name__}: {exc}") from exc

    state = json.loads(progress.read_text(encoding="utf-8"))
    ordered_pages = [state["pages"][str(i)] for i in sorted(map(int, state.get("pages", {}).keys()))]
    page_records = []
    combined_parts = []
    for row in ordered_pages:
        native_text = str(row.get("text", ""))
        ocr_text = str(row.get("ocr_text", ""))
        # Prefer OCR only when it returned text; retain native text separately.
        selected_text = ocr_text if ocr_text.strip() else native_text
        if selected_text:
            combined_parts.append(selected_text)
        page_records.append({
            "page_number": int(row["page_number"]),
            "native_text": native_text,
            "ocr_text": ocr_text,
            "selected_text": selected_text,
            "character_count_native": len(native_text),
            "character_count_ocr": len(ocr_text),
            "ocr_status": row.get("ocr_status", "unknown"),
            "ocr_confidence": row.get("ocr_confidence"),
            "ocr_provenance": row.get("ocr_provenance"),
            "ocr_warnings": row.get("ocr_warnings", []),
            "likely_scanned_or_text_sparse": bool(row.get("likely_scanned_or_text_sparse")),
        })
    combined_text = "\n\n".join(combined_parts)
    result = {
        "phase": "10.4.7",
        "source_manifest": str(manifest_file),
        "source_url": manifest.get("source_url"),
        "source_pdf_sha256": digest,
        "page_count": state.get("page_count"),
        "pages_extracted_so_far": len(page_records),
        "next_page": state.get("next_page"),
        "complete": bool(state.get("complete")),
        "batch": batch_result,
        "ocr_requested": bool(run_ocr),
        "ocr_pages_pending": [p["page_number"] for p in page_records
                               if p["likely_scanned_or_text_sparse"] and not p["ocr_text"].strip()],
        "pages": page_records,
        "combined_text": combined_text,
        "combined_text_sha256": hashlib.sha256(combined_text.encode("utf-8")).hexdigest(),
        "extracted_at": datetime.now(timezone.utc).isoformat(),
        "text_extraction_status": "complete" if state.get("complete") else "partial_resumable",
        "ocr_review_required": any(p["ocr_text"] for p in page_records),
        "legal_authenticity_verified": False,
        "legal_status_verified": False,
        "active_bank_write": False,
        "staging_registry_write": False,
        "decision": "quarantined_extraction_only_human_legal_and_text_review_required",
    }
    _atomic_json(output, result)
    result["output_path"] = str(output)
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Bounded offline extraction of a quarantined Dotic PDF")
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--pdf-file")
    parser.add_argument("--progress-file")
    parser.add_argument("--output")
    parser.add_argument("--max-pages", type=int, default=20)
    parser.add_argument("--run-ocr", action="store_true", help="Opt in to Persian+English OCR for sparse pages")
    args = parser.parse_args(argv)
    result = run_extraction(args.manifest, pdf_path=args.pdf_file,
                            progress_path=args.progress_file, output_path=args.output,
                            max_pages=args.max_pages, run_ocr=args.run_ocr)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
