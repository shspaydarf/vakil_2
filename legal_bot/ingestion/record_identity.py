"""Phase 5.3: deterministic legal-document/record identity and cautious lineage.

Identifiers are technical keys, not claims of legal equivalence or authority.
No records are merged and no amendment/repeal relationship is inferred.
"""
from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from pathlib import Path
from typing import Any, Mapping

SCHEMA_VERSION = "5.4"
RELATION_TYPES = {"amends", "repeals", "replaces", "interprets", "implements", "related_to", "same_document_version"}
_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")


def normalize_identity_text(value: Any) -> str:
    text = unicodedata.normalize("NFKC", str(value or ""))
    text = text.translate(str.maketrans({"ي": "ی", "ك": "ک", "ۀ": "ه", "ة": "ه"})).translate(_DIGITS)
    text = re.sub(r"[\u064B-\u065F\u0670\u0640]", "", text)
    return re.sub(r"\s+", " ", text).strip().casefold()


def _digest(*parts: str) -> str:
    payload = "\x1f".join(parts).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _short(prefix: str, *parts: str) -> str:
    return f"{prefix}_{_digest(*parts)[:32]}"


DOCUMENT_FAMILY_ALIASES = {
    "statute": "laws", "law": "laws", "laws": "laws",
    "regulation": "regulations_and_bylaws", "bylaw": "regulations_and_bylaws",
    "regulations_and_bylaws": "regulations_and_bylaws",
    "supreme_court_unity_ruling": "supreme_court_unity_rulings",
    "supreme_court_unity_rulings": "supreme_court_unity_rulings",
    "administrative_justice_general_assembly_ruling": "administrative_justice_general_assembly_rulings",
    "administrative_justice_general_assembly_rulings": "administrative_justice_general_assembly_rulings",
    "advisory_opinion": "judiciary_advisory_opinions",
    "judiciary_advisory_opinion": "judiciary_advisory_opinions",
    "judiciary_advisory_opinions": "judiciary_advisory_opinions",
}


def canonical_document_family(value: Any) -> str | None:
    """Map explicit legacy kinds to one of five families; never guess generic kinds."""
    key = normalize_identity_text(value).replace(" ", "_")
    return DOCUMENT_FAMILY_ALIASES.get(key)


def _valid_sha(value: Any) -> str | None:
    value = str(value or "").lower()
    return value if re.fullmatch(r"[0-9a-f]{64}", value) else None


def build_identity_manifest(candidate: Mapping[str, Any]) -> dict[str, Any]:
    """Build cautious technical identity/version keys without legal equivalence claims.

    A family key requires jurisdiction, issuing authority, a recognized family, and
    either an official document number or a title. Record keys require a non-empty
    record kind and locator. Missing anchors yield null IDs instead of guessed IDs.
    """
    family_source = candidate.get("document_family") if "document_family" in candidate else candidate.get("document_kind")
    family = canonical_document_family(family_source)
    authority = normalize_identity_text(candidate.get("source_authority_id"))
    jurisdiction = normalize_identity_text(candidate.get("jurisdiction"))
    title = normalize_identity_text(candidate.get("title"))
    official_number = normalize_identity_text(candidate.get("document_number") or candidate.get("official_document_number"))
    anchor_kind = "official_document_number" if official_number else "normalized_title"
    anchor = official_number or title
    identity_complete = bool(family and authority and jurisdiction and anchor)
    family_id = _short("docfam", jurisdiction, authority, family, anchor_kind, anchor) if identity_complete else None

    source_sha = _valid_sha(candidate.get("source_document_sha256"))
    version_id = _short("docver", family_id, source_sha) if family_id and source_sha else None
    extracted_sha = _valid_sha(candidate.get("extracted_text_sha256"))
    raw_text = candidate.get("extracted_text")
    raw_text_sha = hashlib.sha256(str(raw_text).encode("utf-8")).hexdigest() if isinstance(raw_text, str) else None
    normalized_text_sha = hashlib.sha256(normalize_identity_text(raw_text).encode("utf-8")).hexdigest() if isinstance(raw_text, str) else None

    records = []
    for row in candidate.get("records", []) if isinstance(candidate.get("records"), list) else []:
        if not isinstance(row, Mapping):
            continue
        record_kind = normalize_identity_text(row.get("record_kind"))
        raw_locator = row.get("locator")
        locator = normalize_identity_text(json.dumps(raw_locator, ensure_ascii=False, sort_keys=True) if isinstance(raw_locator, Mapping) else raw_locator)
        text = normalize_identity_text(row.get("text_original"))
        content_hash = hashlib.sha256(text.encode("utf-8")).hexdigest() if text else None
        record_complete = bool(family_id and record_kind and locator)
        logical_id = _short("reclog", family_id, record_kind, locator) if record_complete else None
        version_record_id = _short("recver", version_id or family_id, record_kind, locator, content_hash or "") if record_complete and content_hash else None
        records.append({
            "input_record_id": row.get("record_id"),
            "logical_record_id": logical_id,
            "version_record_id": version_record_id,
            "identity_status": "complete" if record_complete else "incomplete",
            "record_kind": record_kind or None,
            "locator_normalized": locator or None,
            "normalized_content_sha256": content_hash,
            "source_page_refs": list(row.get("source_page_refs", [])) if isinstance(row.get("source_page_refs"), list) else [],
        })

    date_fields = ("adoption_date", "publication_date", "promulgation_date", "effective_date", "acquired_at")
    dates = {key: candidate.get(key) for key in date_fields if candidate.get(key) is not None}
    return {
        "identity_schema_version": SCHEMA_VERSION,
        "document_family": family,
        "identity_status": "complete" if identity_complete else "incomplete",
        "document_family_id": family_id,
        "document_version_id": version_id,
        "official_document_number": candidate.get("document_number") or candidate.get("official_document_number"),
        "identity_basis": ["jurisdiction", "source_authority_id", "canonical_document_family", anchor_kind] if identity_complete else [],
        "version_basis": ["document_family_id", "source_document_sha256"],
        "source_document_sha256": source_sha,
        "extracted_text_sha256": extracted_sha,
        "raw_extracted_text_sha256": raw_text_sha,
        "normalized_text_sha256": normalized_text_sha,
        "legal_dates": dates,
        "record_identity_basis": ["document_family_id", "record_kind", "normalized_locator"],
        "records": records,
        "legal_equivalence_asserted": False,
        "automatic_merge_performed": False,
    }


def validate_lineage(candidate: Mapping[str, Any]) -> dict[str, Any]:
    """Validate explicit human-supplied lineage without trusting malformed input."""
    relations = candidate.get("lineage_relations", [])
    errors: list[str] = []
    if not isinstance(relations, list):
        return {"valid": False, "errors": ["lineage_relations_must_be_list"], "relations": []}
    clean = []
    seen = set()
    for i, relation in enumerate(relations):
        if not isinstance(relation, Mapping):
            errors.append(f"lineage[{i}]:must_be_object")
            continue
        source = relation.get("source_document_id")
        target = relation.get("target_document_id")
        rel_type = relation.get("relation_type")
        reviewer = relation.get("reviewer_id")
        source_ok = isinstance(source, str) and bool(source.strip())
        target_ok = isinstance(target, str) and bool(target.strip())
        type_ok = isinstance(rel_type, str) and rel_type in RELATION_TYPES
        reviewer_ok = isinstance(reviewer, str) and bool(reviewer.strip())
        if not source_ok: errors.append(f"lineage[{i}]:invalid_source_document_id")
        if not target_ok: errors.append(f"lineage[{i}]:invalid_target_document_id")
        if not type_ok: errors.append(f"lineage[{i}]:invalid_relation_type")
        if not reviewer_ok: errors.append(f"lineage[{i}]:reviewer_required")
        if source_ok and target_ok and source.strip() == target.strip():
            errors.append(f"lineage[{i}]:self_relation_forbidden")
        if source_ok and target_ok and type_ok:
            key = (source.strip(), target.strip(), rel_type)
            if key in seen:
                errors.append(f"lineage[{i}]:duplicate_relation")
            seen.add(key)
        if source_ok and target_ok and type_ok and reviewer_ok and source.strip() != target.strip():
            clean.append({"source_document_id": source.strip(), "target_document_id": target.strip(),
                          "relation_type": rel_type, "reviewer_id": reviewer.strip(),
                          "asserted_by_human": True, "legal_effect_confirmed": False})
    return {"valid": not errors, "errors": errors, "relations": clean,
            "automatic_lineage_inference": False}


def scan_existing_identities(candidate: Mapping[str, Any], data_dir: Path | str) -> dict[str, Any]:
    """Compare against prior staging/quarantine packages; report, never merge/block."""
    current = build_identity_manifest(candidate)
    root = Path(data_dir) / "ingestion"
    matches = []
    current_records = current["records"]
    for bucket in ("staging", "quarantine"):
        base = root / bucket
        if not base.is_dir():
            continue
        for path in sorted(base.glob("*/candidate.json")):
            try:
                other = json.loads(path.read_text(encoding="utf-8"))
                other_id = build_identity_manifest(other)
            except (OSError, ValueError, TypeError):
                continue
            if other.get("candidate_id") == candidate.get("candidate_id"):
                continue
            if current.get("document_version_id") and current["document_version_id"] == other_id.get("document_version_id"):
                matches.append({"candidate_id": other.get("candidate_id"), "match_type": "same_source_document_version"})
            old_by_logical = {r["logical_record_id"]: r for r in other_id["records"]
                              if r.get("logical_record_id")}
            for row in current_records:
                logical_id = row.get("logical_record_id")
                old = old_by_logical.get(logical_id) if logical_id else None
                if old:
                    match_type = "exact_normalized_content" if old["normalized_content_sha256"] == row["normalized_content_sha256"] else "same_logical_locator_different_content"
                    matches.append({"candidate_id": other.get("candidate_id"), "match_type": match_type,
                                    "logical_record_id": row["logical_record_id"]})
    unique = {(m["candidate_id"], m["match_type"], m.get("logical_record_id")): m for m in matches}
    return {"matches": list(unique.values()), "duplicate_policy": "report_only_no_merge_no_overwrite",
            "automatic_duplicate_decision": False}
