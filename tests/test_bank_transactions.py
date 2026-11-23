import hashlib
import json
from pathlib import Path

import pytest

from legal_bot.ingestion.bank_transactions import (
    prepare_transaction, commit_transaction, rollback_transaction,
)


def _bank(tmp_path):
    root = tmp_path
    originals = {
        "laws.json": {"قانون الف": [{"ماده": "۱"}]},
        "rulings.json": {"rulings": [], "diwan_adalat_rulings": []},
        "consultations.json": {"consultations": []},
        "samples_and_circulars.json": {"samples": [], "circulars": []},
    }
    for name, data in originals.items():
        (root / name).write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return originals


def _approval():
    return {"approved": True, "reviewer_id": "reviewer-test",
            "decided_at": "2026-11-01T12:00:00+00:00",
            "source_review_completed": True, "legal_review_completed": True,
            "mapping_review_completed": True}


def test_prepare_is_dry_run_with_byte_exact_backup_and_no_bank_write(tmp_path):
    _bank(tmp_path)
    target = tmp_path / "laws.json"
    before = target.read_bytes()
    result = prepare_transaction({"laws.json": {"قانون ب": []}}, data_dir=tmp_path, transaction_id="tx-001")
    assert result["status"] == "prepared_dry_run"
    assert result["active_bank_modified"] is False
    assert target.read_bytes() == before
    backup = Path(result["transaction_path"]) / "backups" / "laws.json"
    assert backup.read_bytes() == before


def test_commit_requires_both_explicit_flag_and_human_approval(tmp_path):
    _bank(tmp_path)
    prepare_transaction({"laws.json": {"قانون ب": []}}, data_dir=tmp_path, transaction_id="tx-002")
    result = commit_transaction("tx-002", data_dir=tmp_path, human_approval=_approval(), commit=False)
    assert result["commit_performed"] is False
    assert "قانون الف" in (tmp_path / "laws.json").read_text(encoding="utf-8")



def test_commit_rejects_incomplete_review_attestation_at_central_write_boundary(tmp_path):
    _bank(tmp_path)
    target = tmp_path / "laws.json"
    before = target.read_bytes()
    prepare_transaction({"laws.json": {"قانون ب": []}}, data_dir=tmp_path, transaction_id="tx-approval-01")
    incomplete = {"approved": True, "reviewer_id": "reviewer-test",
                  "decided_at": "2026-11-01T12:00:00+00:00",
                  "source_review_completed": True, "legal_review_completed": True}
    result = commit_transaction("tx-approval-01", data_dir=tmp_path,
                                human_approval=incomplete, commit=True)
    assert result["status"] == "prepared_dry_run"
    assert result["commit_performed"] is False
    assert "complete_human_review" in result["reason"]
    assert target.read_bytes() == before


def test_commit_rejects_naive_timestamp_even_with_review_flags(tmp_path):
    _bank(tmp_path)
    target = tmp_path / "laws.json"
    before = target.read_bytes()
    prepare_transaction({"laws.json": {"قانون ب": []}}, data_dir=tmp_path, transaction_id="tx-approval-02")
    invalid = _approval() | {"decided_at": "2026-11-01T12:00:00"}
    result = commit_transaction("tx-approval-02", data_dir=tmp_path,
                                human_approval=invalid, commit=True)
    assert result["status"] == "prepared_dry_run"
    assert result["commit_performed"] is False
    assert target.read_bytes() == before

def test_commit_and_rollback_restore_exact_bytes(tmp_path):
    _bank(tmp_path)
    target = tmp_path / "laws.json"
    before = target.read_bytes()
    prepare_transaction({"laws.json": {"قانون ب": []}}, data_dir=tmp_path, transaction_id="tx-003")
    committed = commit_transaction("tx-003", data_dir=tmp_path, human_approval=_approval(), commit=True)
    assert committed["status"] == "committed"
    assert target.read_bytes() != before
    rolled = rollback_transaction("tx-003", data_dir=tmp_path, human_approval=_approval(), rollback=True)
    assert rolled["status"] == "rolled_back"
    assert target.read_bytes() == before


def test_concurrency_conflict_prevents_commit_without_partial_write(tmp_path):
    _bank(tmp_path)
    prepare_transaction({"laws.json": {"قانون ب": []}, "consultations.json": {"consultations": [1]}},
                        data_dir=tmp_path, transaction_id="tx-004")
    (tmp_path / "consultations.json").write_text('{"consultations":["external"]}', encoding="utf-8")
    laws_before = (tmp_path / "laws.json").read_bytes()
    with pytest.raises(RuntimeError, match="concurrency_conflict"):
        commit_transaction("tx-004", data_dir=tmp_path, human_approval=_approval(), commit=True)
    assert (tmp_path / "laws.json").read_bytes() == laws_before


def test_non_whitelisted_target_and_invalid_json_are_rejected(tmp_path):
    _bank(tmp_path)
    with pytest.raises(ValueError, match="non-whitelisted"):
        prepare_transaction({"official_sources.json": {}}, data_dir=tmp_path, transaction_id="tx-005")
    with pytest.raises(ValueError, match="valid UTF-8 JSON"):
        prepare_transaction({"laws.json": b"not-json"}, data_dir=tmp_path, transaction_id="tx-006")


def test_expected_hash_guards_prepare_against_stale_inventory(tmp_path):
    _bank(tmp_path)
    with pytest.raises(RuntimeError, match="concurrency_conflict"):
        prepare_transaction({"laws.json": {}}, data_dir=tmp_path, transaction_id="tx-007",
                            expected_sha256={"laws.json": "0" * 64})


def test_crash_recovery_restores_partially_replaced_multi_file_transaction(tmp_path):
    from legal_bot.ingestion.bank_transactions import recover_interrupted_transaction
    _bank(tmp_path)
    names = ["laws.json", "consultations.json"]
    before = {name: (tmp_path / name).read_bytes() for name in names}
    prepared = prepare_transaction(
        {"laws.json": {"قانون ب": []}, "consultations.json": {"consultations": ["new"]}},
        data_dir=tmp_path, transaction_id="tx-crash-01")
    tx_dir = Path(prepared["transaction_path"])
    # Simulate abrupt process death after the first atomic replacement, before
    # the transaction manifest can be finalized or the exception handler runs.
    (tmp_path / "laws.json").write_bytes((tx_dir / "replacements" / "laws.json").read_bytes())
    recovered = recover_interrupted_transaction("tx-crash-01", data_dir=tmp_path)
    assert recovered["status"] == "recovered_after_interruption"
    assert set(recovered["recovered_targets"]) == {"laws.json"}
    assert {name: (tmp_path / name).read_bytes() for name in names} == before
    assert not (tmp_path / "ingestion/transactions/.bank-write.lock").exists()


def test_crash_recovery_is_idempotent_when_no_target_was_replaced(tmp_path):
    from legal_bot.ingestion.bank_transactions import recover_interrupted_transaction
    _bank(tmp_path)
    prepare_transaction({"laws.json": {"قانون ب": []}}, data_dir=tmp_path, transaction_id="tx-crash-02")
    result = recover_interrupted_transaction("tx-crash-02", data_dir=tmp_path)
    assert result["status"] == "no_interrupted_write_detected"


def test_crash_recovery_fails_closed_on_unknown_target_hash(tmp_path):
    from legal_bot.ingestion.bank_transactions import recover_interrupted_transaction
    _bank(tmp_path)
    prepare_transaction({"laws.json": {"قانون ب": []}}, data_dir=tmp_path, transaction_id="tx-crash-03")
    (tmp_path / "laws.json").write_text('{"external":"edit"}', encoding="utf-8")
    with pytest.raises(RuntimeError, match="recovery_unknown_target_hash"):
        recover_interrupted_transaction("tx-crash-03", data_dir=tmp_path)
    assert json.loads((tmp_path / "laws.json").read_text(encoding="utf-8")) == {"external": "edit"}


def test_crash_recovery_rejects_corrupt_backup_and_respects_writer_lock(tmp_path):
    from legal_bot.ingestion.bank_transactions import recover_interrupted_transaction
    _bank(tmp_path)
    prepared = prepare_transaction({"laws.json": {"قانون ب": []}}, data_dir=tmp_path, transaction_id="tx-crash-04")
    tx_dir = Path(prepared["transaction_path"])
    (tx_dir / "backups/laws.json").write_text('{"tampered":true}', encoding="utf-8")
    (tmp_path / "ingestion/transactions/.bank-write.lock").parent.mkdir(parents=True, exist_ok=True)
    (tmp_path / "ingestion/transactions/.bank-write.lock").write_text("busy", encoding="utf-8")
    with pytest.raises(RuntimeError, match="bank_write_locked"):
        recover_interrupted_transaction("tx-crash-04", data_dir=tmp_path)
    (tmp_path / "ingestion/transactions/.bank-write.lock").unlink()
    (tmp_path / "laws.json").write_bytes((tx_dir / "replacements/laws.json").read_bytes())
    with pytest.raises(RuntimeError, match="recovery_backup_hash_mismatch"):
        recover_interrupted_transaction("tx-crash-04", data_dir=tmp_path)


def test_transaction_entry_points_reject_path_traversal_ids(tmp_path):
    from legal_bot.ingestion.bank_transactions import recover_interrupted_transaction
    _bank(tmp_path)
    for operation in (commit_transaction, rollback_transaction, recover_interrupted_transaction):
        with pytest.raises(ValueError, match="invalid transaction_id"):
            operation("../escape", data_dir=tmp_path)
