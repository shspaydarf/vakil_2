"""Phase 5.4: guarded, journaled JSON-bank transactions.

Preparation is the default and never changes active bank files. Commit requires
both explicit human approval metadata and an explicit commit=True argument.
The transaction is restricted to the four existing legal corpus files.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from .bank_architecture import BANK_TARGETS, DATA_DIR

SCHEMA_VERSION = "5.4"
TARGETS = frozenset(BANK_TARGETS)


def _validate_transaction_id(transaction_id: str) -> str:
    if (not isinstance(transaction_id, str) or not transaction_id
            or any(c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_" for c in transaction_id)):
        raise ValueError("invalid transaction_id")
    return transaction_id


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")


def _complete_commit_approval(approval: Mapping[str, Any] | None) -> bool:
    """Require the same explicit review attestations at the final write boundary."""
    if not isinstance(approval, Mapping) or approval.get("approved") is not True:
        return False
    for key in ("reviewer_id", "decided_at"):
        if not isinstance(approval.get(key), str) or not approval[key].strip():
            return False
    try:
        decided = datetime.fromisoformat(approval["decided_at"].replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return False
    if decided.tzinfo is None or decided.utcoffset() is None:
        return False
    return all(approval.get(key) is True for key in (
        "source_review_completed", "legal_review_completed", "mapping_review_completed"
    ))


def _atomic_write(path: Path, raw: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def _load_json(raw: bytes, name: str) -> Any:
    try:
        return json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"replacement for {name} is not valid UTF-8 JSON") from exc


def _journal(root: Path, transaction_id: str, event: Mapping[str, Any]) -> None:
    path = root / "ingestion" / "transactions" / transaction_id / "audit_log.json"
    existing = []
    if path.exists():
        existing = json.loads(path.read_text(encoding="utf-8"))
    existing.append(dict(event))
    _atomic_write(path, _json_bytes(existing))


def prepare_transaction(
    replacements: Mapping[str, Any], *, data_dir: Path | str | None = None,
    transaction_id: str, expected_sha256: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Create a dry-run transaction package and byte-exact backups; no bank writes."""
    _validate_transaction_id(transaction_id)
    if not isinstance(replacements, Mapping) or not replacements:
        raise ValueError("replacements must be a non-empty mapping")
    unknown = set(replacements) - TARGETS
    if unknown:
        raise ValueError(f"non-whitelisted bank targets: {sorted(unknown)}")
    root = Path(data_dir) if data_dir is not None else DATA_DIR
    tx_dir = root / "ingestion" / "transactions" / transaction_id
    if tx_dir.exists():
        raise FileExistsError(f"transaction already exists: {transaction_id}")
    expected_sha256 = expected_sha256 or {}
    plan = []
    for name, replacement in sorted(replacements.items()):
        target = root / name
        if not target.is_file():
            raise FileNotFoundError(f"active bank target missing: {name}")
        original = target.read_bytes()
        _load_json(original, name)
        new_raw = replacement if isinstance(replacement, bytes) else _json_bytes(replacement)
        _load_json(new_raw, name)
        before_hash = _sha(original)
        if name in expected_sha256 and expected_sha256[name] != before_hash:
            raise RuntimeError(f"concurrency_conflict:{name}")
        plan.append({"target": name, "before_sha256": before_hash,
                     "after_sha256": _sha(new_raw), "before_size": len(original),
                     "after_size": len(new_raw), "replacement_bytes": new_raw})
    tx_dir.mkdir(parents=True, exist_ok=False)
    try:
        backups = tx_dir / "backups"
        backups.mkdir()
        public_plan = []
        for item in plan:
            name = item["target"]
            backup_path = backups / name
            backup_path.write_bytes((root / name).read_bytes())
            with backup_path.open("rb") as handle:
                os.fsync(handle.fileno())
            (tx_dir / "replacements").mkdir(exist_ok=True)
            _atomic_write(tx_dir / "replacements" / name, item["replacement_bytes"])
            public_plan.append({k: v for k, v in item.items() if k != "replacement_bytes"} | {"backup_path": f"backups/{name}", "replacement_path": f"replacements/{name}"})
        manifest = {
            "schema_version": SCHEMA_VERSION, "transaction_id": transaction_id,
            "status": "prepared_dry_run", "mode": "dry_run",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "operations": public_plan, "human_approval": None,
            "active_bank_modified": False, "commit_performed": False,
            "rollback_available": True,
        }
        _atomic_write(tx_dir / "transaction_manifest.json", _json_bytes(manifest))
        _journal(root, transaction_id, {"event": "prepared", "at": manifest["created_at"], "active_bank_modified": False})
    except Exception:
        shutil.rmtree(tx_dir, ignore_errors=True)
        raise
    return manifest | {"transaction_path": str(tx_dir)}


def commit_transaction(
    transaction_id: str, *, data_dir: Path | str | None = None,
    human_approval: Mapping[str, Any] | None = None, commit: bool = False,
) -> dict[str, Any]:
    """Commit only with explicit approval + commit flag; otherwise return dry-run."""
    _validate_transaction_id(transaction_id)
    root = Path(data_dir) if data_dir is not None else DATA_DIR
    tx_dir = root / "ingestion" / "transactions" / transaction_id
    manifest_path = tx_dir / "transaction_manifest.json"
    if not manifest_path.is_file():
        raise FileNotFoundError("prepared transaction not found")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("status") != "prepared_dry_run":
        raise RuntimeError("transaction is not in prepared_dry_run state")
    approval_ok = _complete_commit_approval(human_approval)
    if not commit or not approval_ok:
        return manifest | {"status": "prepared_dry_run", "commit_performed": False,
                           "reason": "explicit_commit_and_complete_human_review_approval_required"}
    lock = root / "ingestion" / "transactions" / ".bank-write.lock"
    lock.parent.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError as exc:
        raise RuntimeError("bank_write_locked") from exc
    os.close(fd)
    applied: list[dict[str, Any]] = []
    try:
        for op in manifest["operations"]:
            target = root / op["target"]
            current = target.read_bytes()
            if _sha(current) != op["before_sha256"]:
                raise RuntimeError(f"concurrency_conflict:{op['target']}")
            replacement = (tx_dir / op["replacement_path"]).read_bytes()
            _load_json(replacement, op["target"])
        for op in manifest["operations"]:
            target = root / op["target"]
            replacement = (tx_dir / op["replacement_path"]).read_bytes()
            _atomic_write(target, replacement)
            applied.append(op)
        manifest.update({"status": "committed", "mode": "transactional_commit",
                         "human_approval": dict(human_approval), "committed_at": datetime.now(timezone.utc).isoformat(),
                         "active_bank_modified": True, "commit_performed": True})
        _atomic_write(manifest_path, _json_bytes(manifest))
        _journal(root, transaction_id, {"event": "committed", "at": manifest["committed_at"],
                                        "reviewer_id": human_approval["reviewer_id"],
                                        "targets": [x["target"] for x in applied]})
        return manifest
    except Exception:
        # Best-effort all-or-restore: restore every target already replaced from byte-exact backups.
        restore_errors = []
        for op in reversed(applied):
            try:
                _atomic_write(root / op["target"], (tx_dir / op["backup_path"]).read_bytes())
            except Exception as restore_exc:  # pragma: no cover - exceptional filesystem failure
                restore_errors.append(f"{op['target']}:{restore_exc}")
        _journal(root, transaction_id, {"event": "commit_failed", "at": datetime.now(timezone.utc).isoformat(),
                                        "restored_targets": [x["target"] for x in applied],
                                        "restore_errors": restore_errors})
        raise
    finally:
        try:
            lock.unlink()
        except FileNotFoundError:
            pass


def rollback_transaction(transaction_id: str, *, data_dir: Path | str | None = None,
                         human_approval: Mapping[str, Any] | None = None, rollback: bool = False) -> dict[str, Any]:
    """Restore committed targets only after separate explicit rollback approval."""
    _validate_transaction_id(transaction_id)
    root = Path(data_dir) if data_dir is not None else DATA_DIR
    tx_dir = root / "ingestion" / "transactions" / transaction_id
    manifest_path = tx_dir / "transaction_manifest.json"
    if not manifest_path.is_file():
        raise FileNotFoundError("transaction not found")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("status") != "committed":
        raise RuntimeError("only committed transactions can be rolled back")
    valid = (rollback and isinstance(human_approval, Mapping) and human_approval.get("approved") is True
             and isinstance(human_approval.get("reviewer_id"), str) and bool(human_approval["reviewer_id"].strip())
             and isinstance(human_approval.get("decided_at"), str) and bool(human_approval["decided_at"].strip()))
    if not valid:
        return {"status": "rollback_not_performed", "reason": "explicit_rollback_and_human_approval_required", "active_bank_modified": False}
    for op in manifest["operations"]:
        target = root / op["target"]
        if _sha(target.read_bytes()) != op["after_sha256"]:
            raise RuntimeError(f"rollback_conflict:{op['target']}")
    for op in reversed(manifest["operations"]):
        _atomic_write(root / op["target"], (tx_dir / op["backup_path"]).read_bytes())
    manifest.update({"status": "rolled_back", "rolled_back_at": datetime.now(timezone.utc).isoformat(),
                     "rollback_approval": dict(human_approval), "rollback_performed": True})
    _atomic_write(manifest_path, _json_bytes(manifest))
    _journal(root, transaction_id, {"event": "rolled_back", "at": manifest["rolled_back_at"],
                                    "reviewer_id": human_approval["reviewer_id"]})
    return manifest


def recover_interrupted_transaction(transaction_id: str, *, data_dir: Path | str | None = None) -> dict[str, Any]:
    """Fail-closed recovery for a process crash during a multi-file commit.

    A target at its before-hash is untouched; a target at its after-hash is
    restored from its verified byte-exact backup. Any third hash blocks
    recovery rather than overwriting an unrelated concurrent edit.
    """
    _validate_transaction_id(transaction_id)
    root = Path(data_dir) if data_dir is not None else DATA_DIR
    tx_dir = root / "ingestion" / "transactions" / transaction_id
    manifest_path = tx_dir / "transaction_manifest.json"
    if not manifest_path.is_file():
        raise FileNotFoundError("prepared transaction not found")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("status") != "prepared_dry_run":
        raise RuntimeError("only an unfinalized prepared transaction can be crash-recovered")

    lock = root / "ingestion" / "transactions" / ".bank-write.lock"
    lock.parent.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError as exc:
        raise RuntimeError("bank_write_locked") from exc
    os.close(fd)
    restored: list[str] = []
    try:
        states = []
        for op in manifest.get("operations", []):
            if op.get("target") not in TARGETS:
                raise RuntimeError("recovery_target_not_whitelisted")
            target = root / op["target"]
            backup = tx_dir / op["backup_path"]
            if not target.is_file() or not backup.is_file():
                raise RuntimeError(f"recovery_file_missing:{op['target']}")
            backup_raw = backup.read_bytes()
            if _sha(backup_raw) != op["before_sha256"]:
                raise RuntimeError(f"recovery_backup_hash_mismatch:{op['target']}")
            current_hash = _sha(target.read_bytes())
            if current_hash == op["before_sha256"]:
                states.append((op, "before"))
            elif current_hash == op["after_sha256"]:
                states.append((op, "after"))
            else:
                raise RuntimeError(f"recovery_unknown_target_hash:{op['target']}")

        changed = [op for op, state in states if state == "after"]
        if not changed:
            return {"status": "no_interrupted_write_detected", "restored_targets": [],
                    "active_bank_modified": False}
        for op in reversed(changed):
            _atomic_write(root / op["target"], (tx_dir / op["backup_path"]).read_bytes())
            restored.append(op["target"])
        for op in manifest["operations"]:
            if _sha((root / op["target"]).read_bytes()) != op["before_sha256"]:
                raise RuntimeError(f"recovery_verification_failed:{op['target']}")
        manifest.update({"status": "recovered_after_interruption", "recovered_at": datetime.now(timezone.utc).isoformat(),
                         "recovered_targets": restored, "active_bank_restored": True})
        _atomic_write(manifest_path, _json_bytes(manifest))
        _journal(root, transaction_id, {"event": "crash_recovered", "at": manifest["recovered_at"],
                                        "restored_targets": restored})
        return manifest
    finally:
        try:
            lock.unlink()
        except FileNotFoundError:
            pass
