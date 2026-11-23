"""Read-only architecture and inventory for the existing legal JSON bank.

Phase 5.1 deliberately does not import, rewrite, normalize, or activate data.
It fingerprints current files and describes their consumer-facing shapes.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

DATA_DIR = Path(__file__).resolve().parents[1] / "data" / "iran"
STAGING_DIR_NAME = "staging"
QUARANTINE_DIR_NAME = "quarantine"
ARCHIVE_DIR_NAME = "archive"

# These are the only current production corpus files identified as searchable
# legal content. Metadata/catalog files are intentionally not import targets.
BANK_TARGETS = {
    "laws.json": {"kind": "law_collection", "container": "object_by_law_title", "record_list": "<root>[law_title]", "consumer": "legal_bot.laws.RAW"},
    "rulings.json": {"kind": "ruling_collection", "container": "object_with_lists", "record_list": "rulings + diwan_adalat_rulings", "consumer": "legal_bot.laws.RULING_INDEX"},
    "consultations.json": {"kind": "consultation_collection", "container": "object_with_list", "record_list": "consultations", "consumer": "legal_bot.laws.CONSULTATION_INDEX"},
    "samples_and_circulars.json": {"kind": "template_and_circular_collection", "container": "object_with_lists", "record_list": "samples + circulars", "consumer": "application_features"},
}
REFERENCE_FILES = {
    "official_sources.json": "source_policy_and_authority_registry",
    "secondary_academic_sources.json": "secondary_reference_catalog",
    "law_catalog.json": "coverage_and_planning_catalog",
    "quarantine_manifest.json": "quarantine_control_metadata",
    "quarantine/inactive_laws.json": "inactive_law_records_not_searchable",
}


def _load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _shape(value: Any, depth: int = 0) -> Any:
    if depth >= 3:
        return type(value).__name__
    if isinstance(value, dict):
        return {str(k): _shape(v, depth + 1) for k, v in list(value.items())[:8]}
    if isinstance(value, list):
        return {"type": "list", "length": len(value), "item_shape": _shape(value[0], depth + 1) if value else None}
    return type(value).__name__


def _record_count(filename: str, data: Any) -> int:
    if filename == "laws.json" and isinstance(data, dict):
        return sum(len(v) for v in data.values() if isinstance(v, list))
    if isinstance(data, dict):
        keys = {"rulings.json": ("rulings", "diwan_adalat_rulings"),
                "consultations.json": ("consultations",),
                "samples_and_circulars.json": ("samples", "circulars")}.get(filename, ())
        return sum(len(data.get(k, [])) for k in keys if isinstance(data.get(k), list))
    return len(data) if isinstance(data, list) else 1


def inspect_bank(data_dir: Path | str | None = None) -> dict[str, Any]:
    """Return a read-only inventory; missing/invalid files are reported, not repaired."""
    root = Path(data_dir) if data_dir is not None else DATA_DIR
    files: dict[str, Any] = {}
    for name, descriptor in BANK_TARGETS.items():
        path = root / name
        if not path.is_file():
            files[name] = {"status": "missing", **descriptor}
            continue
        raw = path.read_bytes()
        try:
            parsed = json.loads(raw.decode("utf-8"))
            files[name] = {
                "status": "valid_json", **descriptor,
                "size_bytes": len(raw),
                "sha256": hashlib.sha256(raw).hexdigest(),
                "top_level_type": type(parsed).__name__,
                "top_level_count": len(parsed) if hasattr(parsed, "__len__") else None,
                "record_count": _record_count(name, parsed),
                "shape": _shape(parsed),
            }
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            files[name] = {"status": "invalid_json", **descriptor, "error": str(exc),
                           "size_bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}

    references = {}
    for name, role in REFERENCE_FILES.items():
        path = root / name
        references[name] = {"role": role, "status": "present" if path.is_file() else "missing"}
        if path.is_file():
            raw = path.read_bytes()
            references[name].update(size_bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())
    return {
        "schema_version": "5.1",
        "mode": "read_only_inventory",
        "active_bank_modified": False,
        "files": files,
        "reference_files": references,
        "storage_policy": {
            "staging": STAGING_DIR_NAME,
            "quarantine": QUARANTINE_DIR_NAME,
            "archive": ARCHIVE_DIR_NAME,
            "default_import_mode": "dry_run",
            "active_bank_write_in_phase_5_1": False,
        },
        "safety_notes": [
            "A valid JSON file or passing schema check does not establish legal authenticity or current force of law.",
            "No source text is automatically imported from staging or quarantine.",
            "Existing consumer schemas must remain compatible unless a separately reviewed migration is approved.",
        ],
    }
