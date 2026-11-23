"""Phase 5.7: explicit human-gated activation of staged legal records.

This module deliberately does not guess how extracted records map into the
legacy production JSON schemas. A reviewed, schema-compatible full replacement
must be supplied by an authorized adapter/caller. The gate enforces append-only
preservation, provenance, human review, and the existing transaction protocol.
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from .bank_architecture import BANK_TARGETS, DATA_DIR
from .bank_transactions import prepare_transaction, commit_transaction
from .staging_packages import validate_candidate

KIND_TARGET = {
    "statute": "laws.json", "law": "laws.json",
    "regulation": "samples_and_circulars.json",
    "supreme_court_ruling": "rulings.json",
    "administrative_court_ruling": "rulings.json",
    "advisory_opinion": "consultations.json",
    "ruling": "rulings.json", "consultation": "consultations.json",
    "sample": "samples_and_circulars.json", "circular": "samples_and_circulars.json",
}


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _approval_complete(approval: Mapping[str, Any] | None) -> bool:
    if not isinstance(approval, Mapping) or approval.get("approved") is not True:
        return False
    required = ("reviewer_id", "decided_at")
    if any(not isinstance(approval.get(key), str) or not approval[key].strip() for key in required):
        return False
    try:
        decided = datetime.fromisoformat(str(approval["decided_at"]).replace("Z", "+00:00"))
    except ValueError:
        return False
    if decided.tzinfo is None or decided.utcoffset() is None:
        return False
    return all(approval.get(key) is True for key in
               ("source_review_completed", "legal_review_completed", "mapping_review_completed"))


def _validate_target_shape(target: str, value: Any) -> None:
    if target == "laws.json":
        if not isinstance(value, dict) or any(not isinstance(k, str) or not isinstance(v, list) for k, v in value.items()):
            raise ValueError("laws.json must remain an object of law-title to record-list")
        for title, rows in value.items():
            for row in rows:
                if not isinstance(row, dict) or "ماده" not in row or "متن" not in row:
                    raise ValueError(f"laws.json invalid law record under {title}")
    elif target == "rulings.json":
        if not isinstance(value, dict) or not isinstance(value.get("rulings"), list) or not isinstance(value.get("diwan_adalat_rulings"), list):
            raise ValueError("rulings.json must preserve rulings and diwan_adalat_rulings lists")
    elif target == "consultations.json":
        if not isinstance(value, dict) or not isinstance(value.get("consultations"), list):
            raise ValueError("consultations.json must preserve consultations list")
    elif target == "samples_and_circulars.json":
        if not isinstance(value, dict) or not isinstance(value.get("samples"), list) or not isinstance(value.get("circulars"), list):
            raise ValueError("samples_and_circulars.json must preserve samples and circulars lists")
    else:
        raise ValueError("target_not_whitelisted")


def _append_only_check(target: str, before: Any, after: Any) -> dict[str, int]:
    """Require all existing rows/keys/metadata to remain byte-semantically present."""
    _validate_target_shape(target, before)
    _validate_target_shape(target, after)
    if target == "laws.json":
        for title, rows in before.items():
            if title not in after:
                raise ValueError(f"append_only_violation:law_title_removed:{title}")
            new_rows = [_canonical(row) for row in after[title]]
            for row in rows:
                if _canonical(row) not in new_rows:
                    raise ValueError(f"append_only_violation:existing_law_record_removed_or_changed:{title}")
        return {"existing_records": sum(map(len, before.values())),
                "new_records": sum(map(len, after.values())) - sum(map(len, before.values()))}

    list_keys = {
        "rulings.json": ("rulings", "diwan_adalat_rulings"),
        "consultations.json": ("consultations",),
        "samples_and_circulars.json": ("samples", "circulars"),
    }[target]
    for key, old_value in before.items():
        if key == "metadata":
            if _canonical(after.get(key)) != _canonical(old_value):
                raise ValueError(f"append_only_violation:metadata_changed:{target}")
        elif key in list_keys:
            new_rows = [_canonical(row) for row in after[key]]
            for row in old_value:
                if _canonical(row) not in new_rows:
                    raise ValueError(f"append_only_violation:existing_record_removed_or_changed:{target}:{key}")
        elif key not in after or _canonical(after[key]) != _canonical(old_value):
            raise ValueError(f"append_only_violation:existing_field_changed:{target}:{key}")
    old_count = sum(len(before[k]) for k in list_keys)
    new_count = sum(len(after[k]) for k in list_keys)
    return {"existing_records": old_count, "new_records": new_count - old_count}


def prepare_staged_import(
    package_dir: str | Path, target_replacements: Mapping[str, Any], *,
    transaction_id: str, human_approval: Mapping[str, Any] | None,
    data_dir: Path | str | None = None,
) -> dict[str, Any]:
    """Prepare (never commit) an append-only bank import from a staged package."""
    if not _approval_complete(human_approval):
        raise PermissionError("complete_human_review_approval_required")
    root = Path(data_dir) if data_dir is not None else DATA_DIR
    package = Path(package_dir).resolve()
    staging_root = (root / "ingestion" / "staging").resolve()
    if staging_root not in package.parents:
        raise ValueError("package_must_be_inside_staging_directory")
    manifest_path, candidate_path, gate_path = (package / "package_manifest.json", package / "candidate.json", package / "final_validation_report.json")
    if not all(p.is_file() for p in (manifest_path, candidate_path, gate_path)):
        raise FileNotFoundError("staging_package_or_final_validation_report_missing")
    package_manifest = _read_json(manifest_path)
    candidate = _read_json(candidate_path)
    gate = _read_json(gate_path)
    candidate_validation = validate_candidate(candidate)
    if not candidate_validation.get("valid"):
        raise ValueError("staged_candidate_schema_invalid:" + ",".join(candidate_validation.get("errors", [])))
    if package_manifest.get("candidate_id") != candidate.get("candidate_id") or package.name != candidate.get("candidate_id"):
        raise ValueError("staging_candidate_identity_mismatch")
    if package_manifest.get("destination") != "staging" or package_manifest.get("package_status") != "staged_pending_human_review":
        raise ValueError("candidate_not_in_pending_staging_state")
    if package_manifest.get("active_bank_modified") is not False or package_manifest.get("import_performed") is not False:
        raise ValueError("staging_package_activation_flags_invalid")
    if gate.get("phase5_eligible") is not True or gate.get("active_bank_changed") is not False or gate.get("import_performed") is not False:
        raise PermissionError("phase4_6_final_validation_gate_not_passed")
    if candidate.get("review_decision", {}).get("approved") is not False:
        raise ValueError("candidate_review_state_must_be_pending_before_activation")
    expected_target = KIND_TARGET.get(candidate.get("document_kind"))
    if not expected_target or set(target_replacements) != {expected_target}:
        raise ValueError("exactly_one_document_kind_compatible_bank_target_required")

    before = _read_json(root / expected_target)
    after = target_replacements[expected_target]
    counts = _append_only_check(expected_target, before, after)
    # Require every extracted record's text to be represented in the proposed
    # target payload. This is a basic mapping guard, not legal equivalence proof.
    payload_text = _canonical(after)
    for row in candidate.get("records", []):
        text = row.get("text_original") if isinstance(row, Mapping) else None
        if not isinstance(text, str) or text not in payload_text:
            raise ValueError("candidate_record_text_missing_from_proposed_bank_payload")
    if counts["new_records"] < len(candidate.get("records", [])):
        raise ValueError("proposed_bank_does_not_contain_all_candidate_records_as_new_rows")

    active_hash = _sha((root / expected_target).read_bytes())
    tx = prepare_transaction({expected_target: after}, data_dir=root,
                             transaction_id=transaction_id,
                             expected_sha256={expected_target: active_hash})
    gate_manifest = {
        "schema_version": "5.7", "candidate_id": candidate["candidate_id"],
        "document_kind": candidate["document_kind"], "target": expected_target,
        "transaction_id": transaction_id, "prepared_at": datetime.now(timezone.utc).isoformat(),
        "human_review": dict(human_approval), "append_only_counts": counts,
        "source_document_sha256": candidate["source_document_sha256"],
        "active_bank_modified": False, "import_performed": False,
        "commit_requires_separate_explicit_confirmation": True,
        "legal_force_or_authenticity_established_by_software": False,
    }
    tx_dir = root / "ingestion" / "transactions" / transaction_id
    (tx_dir / "phase5_7_import_gate.json").write_text(json.dumps(gate_manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {**gate_manifest, "transaction": tx}


def commit_staged_import(
    transaction_id: str, *, human_approval: Mapping[str, Any] | None,
    explicit_commit: bool = False, data_dir: Path | str | None = None,
) -> dict[str, Any]:
    """Commit a prepared 5.7 import only with a second explicit confirmation."""
    if not explicit_commit or not _approval_complete(human_approval):
        return {"status": "prepared_dry_run", "commit_performed": False,
                "reason": "second_explicit_commit_and_complete_human_approval_required"}
    if not isinstance(transaction_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]+", transaction_id):
        raise ValueError("invalid transaction_id")
    root = Path(data_dir) if data_dir is not None else DATA_DIR
    tx_dir = root / "ingestion" / "transactions" / transaction_id
    gate_path = tx_dir / "phase5_7_import_gate.json"
    if not gate_path.is_file():
        raise PermissionError("phase5_7_import_gate_missing")
    gate = _read_json(gate_path)
    if gate.get("schema_version") != "5.7" or gate.get("transaction_id") != transaction_id:
        raise PermissionError("phase5_7_import_gate_invalid")
    if gate.get("human_review") != dict(human_approval):
        raise PermissionError("commit_approval_must_match_prepared_review")
    # Preserve the complete review attestation through the final write boundary;
    # the transaction layer independently enforces all three review flags.
    result = commit_transaction(transaction_id, data_dir=root,
                                human_approval=dict(human_approval), commit=True)
    if result.get("status") == "committed":
        result["phase5_7_candidate_id"] = gate["candidate_id"]
        result["phase5_7_import_gate"] = str(gate_path)
    return result
