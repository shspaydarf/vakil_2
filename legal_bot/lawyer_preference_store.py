"""Durable owner-scoped storage for lawyer work preferences.

Stage 3.2: repository/engine only. API wiring and lifecycle controls are added
in later sub-stages. This module stores general professional preferences only;
case/client material is outside its schema and must never be passed here.
"""
from __future__ import annotations

import json
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import config
from .lawyer_preferences import normalize_preferences

SCHEMA_VERSION = "1.0"
_ALLOWED_ORIGINS = {"lawyer_entered", "lawyer_confirmed_suggestion"}


class ProfileVersionConflict(RuntimeError):
    """The caller's expected profile version is stale."""


class ProfileNotFound(LookupError):
    """No persisted profile exists for this owner."""


class ProfileVersionNotFound(LookupError):
    """The requested historical snapshot does not exist for this owner."""


class ConfirmationRequired(PermissionError):
    """A profile save must be explicitly confirmed by the lawyer."""


class PreferencePrivacyError(ValueError):
    """A preference field appears to contain identifying case/client data."""


class ProfileIntegrityError(RuntimeError):
    """The current profile and immutable version history are inconsistent."""


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _owner_id(value: Any) -> int:
    # This is a repository invariant, not authentication. API callers must pass
    # the UID extracted from the authenticated Telegram init data/session.
    if isinstance(value, bool):
        raise ValueError("شناسه مالک معتبر نیست.")
    try:
        owner = int(value)
    except (TypeError, ValueError):
        raise ValueError("شناسه مالک معتبر نیست.") from None
    if owner <= 0:
        raise ValueError("شناسه مالک معتبر نیست.")
    return owner


def _connect() -> sqlite3.Connection:
    db_path = Path(config.DB_PATH)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(str(db_path), timeout=20, isolation_level="DEFERRED")
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys=ON")
    connection.execute("PRAGMA busy_timeout=20000")
    return connection


def init_lawyer_preference_tables() -> None:
    """Create the two additive tables; never alters existing application tables."""
    with _connect() as conn:
        conn.execute("""CREATE TABLE IF NOT EXISTS lawyer_preference_profiles (
            user_id INTEGER PRIMARY KEY,
            preferences_json TEXT NOT NULL CHECK(json_valid(preferences_json)),
            field_metadata_json TEXT NOT NULL CHECK(json_valid(field_metadata_json)),
            schema_version TEXT NOT NULL DEFAULT '1.0',
            profile_version INTEGER NOT NULL CHECK(profile_version >= 1),
            status TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active','inactive')),
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            confirmed_at TEXT NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(user_id) ON DELETE CASCADE
        )""")
        conn.execute("""CREATE TABLE IF NOT EXISTS lawyer_preference_versions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            profile_version INTEGER NOT NULL CHECK(profile_version >= 1),
            schema_version TEXT NOT NULL,
            preferences_json TEXT NOT NULL CHECK(json_valid(preferences_json)),
            field_metadata_json TEXT NOT NULL CHECK(json_valid(field_metadata_json)),
            change_type TEXT NOT NULL CHECK(change_type IN ('created','updated','activated','deactivated','restored')),
            created_at TEXT NOT NULL,
            UNIQUE(user_id, profile_version),
            FOREIGN KEY(user_id) REFERENCES users(user_id) ON DELETE CASCADE
        )""")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_lawyer_pref_versions_owner_version ON lawyer_preference_versions(user_id, profile_version DESC)")
        # Historical snapshots are append-only. DELETE remains available for the
        # explicit hard-delete lifecycle in a later sub-stage (including CASCADE).
        conn.execute("""CREATE TRIGGER IF NOT EXISTS trg_lawyer_pref_versions_no_update
            BEFORE UPDATE ON lawyer_preference_versions
            BEGIN SELECT RAISE(ABORT, 'lawyer preference history is immutable'); END""")
        # A profile must never be reassigned to another owner by an UPDATE.
        conn.execute("""CREATE TRIGGER IF NOT EXISTS trg_lawyer_pref_profiles_no_owner_change
            BEFORE UPDATE OF user_id ON lawyer_preference_profiles
            WHEN OLD.user_id != NEW.user_id
            BEGIN SELECT RAISE(ABORT, 'lawyer preference owner is immutable'); END""")



def _ascii_digits(value: str) -> str:
    table = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
    return value.translate(table)


# Only free-text preference fields are screened. This is a guard against common
# accidental disclosures, not semantic DLP and not a guarantee that all secrets
# or identifying information can be detected.
_PRIVACY_TEXT_FIELDS = {
    "professional_context.jurisdiction",
    "professional_context.practice_context_note",
    "writing_style.style_note",
    "output_formats.format_note",
}
_PHONE_RE = re.compile(r"(?<!\d)(?:(?:\+|00)?98|0)?9\d{9}(?!\d)")
_NATIONAL_ID_RE = re.compile(r"(?<!\d)\d{10}(?!\d)")
_EMAIL_RE = re.compile(r"(?i)(?<![\w.+-])[\w.+-]+@[\w.-]+\.[a-z]{2,}(?![\w.-])")
_CASE_REF_RE = re.compile(
    r"(?i)(?:شماره\s*(?:پرونده|بایگانی|دادنامه|ملی|تماس)|"
    r"case\s*(?:no\.?|number|id)|national\s*id|phone)\s*[:：#-]?\s*[\w\d-]{4,}"
)


def validate_preference_privacy(preferences: dict) -> None:
    """Reject common direct identifiers in general preference free-text fields."""
    for category, fields in preferences.items():
        for field, value in fields.items():
            key = f"{category}.{field}"
            if key not in _PRIVACY_TEXT_FIELDS or not isinstance(value, str):
                continue
            text = _ascii_digits(value)
            if (_PHONE_RE.search(text) or _NATIONAL_ID_RE.search(text)
                    or _EMAIL_RE.search(text) or _CASE_REF_RE.search(text)):
                raise PreferencePrivacyError(
                    "اطلاعات حافظه فقط برای ترجیحات عمومی است؛ شماره تماس، کد ملی، ایمیل یا شناسه پرونده را حذف کنید."
                )


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _make_field_metadata(preferences: dict, supplied: dict | None, previous: dict | None, now: str) -> dict:
    supplied = supplied if isinstance(supplied, dict) else {}
    flat_keys = {f"{category}.{field}" for category, fields in preferences.items() for field in fields}
    if set(supplied) - flat_keys:
        raise ValueError("فراداده ترجیح نامعتبر است.")
    result = {}
    previous = previous if isinstance(previous, dict) else {}
    for key in sorted(flat_keys):
        item = supplied.get(key, {})
        if item is None:
            item = {}
        if not isinstance(item, dict):
            raise ValueError("ساختار منشأ ترجیح نامعتبر است.")
        origin = item.get("origin", "lawyer_entered")
        if origin not in _ALLOWED_ORIGINS:
            raise ValueError("منشأ ترجیح معتبر نیست یا هنوز تأیید نشده است.")
        old = previous.get(key, {})
        if not isinstance(old, dict):
            old = {}
        result[key] = {
            "origin": origin,
            "created_at": old.get("created_at") or now,
            "updated_at": now,
            "confirmed_at": now,
        }
    return result


def save_profile(
    user_id: int,
    preferences: dict,
    *,
    expected_profile_version: int,
    confirm_save: bool,
    field_metadata: dict | None = None,
) -> dict:
    """Create or fully replace a confirmed profile and append an immutable snapshot.

    expected_profile_version=0 means first save. Any stale version raises
    ProfileVersionConflict. Both writes are committed atomically.
    """
    owner = _owner_id(user_id)
    if confirm_save is not True:
        raise ConfirmationRequired("برای ذخیره دائمی، تأیید صریح وکیل لازم است.")
    if isinstance(expected_profile_version, bool):
        raise ValueError("نسخه مورد انتظار معتبر نیست.")
    try:
        expected = int(expected_profile_version)
    except (TypeError, ValueError):
        raise ValueError("نسخه مورد انتظار معتبر نیست.") from None
    if expected < 0:
        raise ValueError("نسخه مورد انتظار معتبر نیست.")

    normalized, selected_count = normalize_preferences(preferences)
    validate_preference_privacy(normalized)
    now = _utc_now()
    init_lawyer_preference_tables()
    conn = _connect()
    try:
        conn.execute("BEGIN IMMEDIATE")
        current = conn.execute(
            "SELECT * FROM lawyer_preference_profiles WHERE user_id=?", (owner,)
        ).fetchone()
        actual = int(current["profile_version"]) if current else 0
        if actual != expected:
            raise ProfileVersionConflict(
                f"نسخه پروفایل تغییر کرده است؛ نسخه فعلی {actual} است."
            )
        if current is not None:
            latest = conn.execute(
                "SELECT MAX(profile_version) AS version FROM lawyer_preference_versions WHERE user_id=?",
                (owner,),
            ).fetchone()
            latest_version = int(latest["version"] or 0)
            if latest_version != actual:
                raise ProfileIntegrityError("تاریخچه پروفایل با نسخه فعلی هماهنگ نیست؛ ذخیره متوقف شد.")
        previous_meta = json.loads(current["field_metadata_json"]) if current else {}
        metadata = _make_field_metadata(normalized, field_metadata, previous_meta, now)
        new_version = actual + 1
        created_at = current["created_at"] if current else now
        status = current["status"] if current else "active"
        change_type = "created" if current is None else "updated"
        values = (_json(normalized), _json(metadata), SCHEMA_VERSION, new_version,
                  status, created_at, now, now, owner)
        conn.execute("""INSERT INTO lawyer_preference_profiles
            (preferences_json,field_metadata_json,schema_version,profile_version,status,
             created_at,updated_at,confirmed_at,user_id)
            VALUES(?,?,?,?,?,?,?,?,?)
            ON CONFLICT(user_id) DO UPDATE SET
             preferences_json=excluded.preferences_json,
             field_metadata_json=excluded.field_metadata_json,
             schema_version=excluded.schema_version,
             profile_version=excluded.profile_version,
             status=excluded.status,
             updated_at=excluded.updated_at,
             confirmed_at=excluded.confirmed_at""", values)
        conn.execute("""INSERT INTO lawyer_preference_versions
            (user_id,profile_version,schema_version,preferences_json,field_metadata_json,change_type,created_at)
            VALUES(?,?,?,?,?,?,?)""",
            (owner, new_version, SCHEMA_VERSION, _json(normalized), _json(metadata), change_type, now))
        conn.commit()
        return {
            "user_id": owner,
            "preferences": normalized,
            "field_metadata": metadata,
            "schema_version": SCHEMA_VERSION,
            "profile_version": new_version,
            "status": status,
            "created_at": created_at,
            "updated_at": now,
            "confirmed_at": now,
            "selected_count": selected_count,
        }
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def set_profile_status(
    user_id: int,
    *,
    target_status: str,
    expected_profile_version: int,
    confirm_action: bool,
) -> dict:
    """Activate or deactivate an existing profile with an immutable snapshot.

    Repeating the current status is idempotent: it returns unchanged and does
    not create a meaningless new version.
    """
    owner = _owner_id(user_id)
    if target_status not in {"active", "inactive"}:
        raise ValueError("وضعیت حافظه معتبر نیست.")
    if confirm_action is not True:
        raise ConfirmationRequired("برای تغییر وضعیت حافظه، تأیید صریح وکیل لازم است.")
    if isinstance(expected_profile_version, bool):
        raise ValueError("نسخه مورد انتظار معتبر نیست.")
    try:
        expected = int(expected_profile_version)
    except (TypeError, ValueError):
        raise ValueError("نسخه مورد انتظار معتبر نیست.") from None
    if expected < 0:
        raise ValueError("نسخه مورد انتظار معتبر نیست.")

    now = _utc_now()
    init_lawyer_preference_tables()
    conn = _connect()
    try:
        conn.execute("BEGIN IMMEDIATE")
        current = conn.execute(
            "SELECT * FROM lawyer_preference_profiles WHERE user_id=?", (owner,)
        ).fetchone()
        if current is None:
            raise ProfileNotFound("حافظه ترجیحات هنوز ایجاد نشده است.")
        actual = int(current["profile_version"])
        if actual != expected:
            raise ProfileVersionConflict(
                f"نسخه پروفایل تغییر کرده است؛ نسخه فعلی {actual} است."
            )
        latest = conn.execute(
            "SELECT MAX(profile_version) AS version FROM lawyer_preference_versions WHERE user_id=?",
            (owner,),
        ).fetchone()
        if int(latest["version"] or 0) != actual:
            raise ProfileIntegrityError("تاریخچه پروفایل با نسخه فعلی هماهنگ نیست؛ تغییر وضعیت متوقف شد.")

        if current["status"] == target_status:
            result = {
                "profile_version": actual, "status": target_status, "changed": False,
                "updated_at": current["updated_at"],
            }
            conn.commit()
            return result

        new_version = actual + 1
        preferences_json = current["preferences_json"]
        metadata_json = current["field_metadata_json"]
        change_type = "activated" if target_status == "active" else "deactivated"
        conn.execute(
            "UPDATE lawyer_preference_profiles SET status=?, profile_version=?, updated_at=?, confirmed_at=? WHERE user_id=?",
            (target_status, new_version, now, now, owner),
        )
        conn.execute("""INSERT INTO lawyer_preference_versions
            (user_id,profile_version,schema_version,preferences_json,field_metadata_json,change_type,created_at)
            VALUES(?,?,?,?,?,?,?)""",
            (owner, new_version, current["schema_version"], preferences_json, metadata_json, change_type, now),
        )
        conn.commit()
        return {"profile_version": new_version, "status": target_status, "changed": True, "updated_at": now}
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def restore_profile_version(
    user_id: int,
    *,
    source_profile_version: int,
    expected_profile_version: int,
    confirm_action: bool,
) -> dict:
    """Restore a historical snapshot as a NEW current version.

    The source snapshot is never edited or deleted. The current active/inactive
    status is retained; only preferences, field metadata and schema version are
    restored from the selected snapshot.
    """
    owner = _owner_id(user_id)
    if confirm_action is not True:
        raise ConfirmationRequired("برای بازیابی نسخه قبلی، تأیید صریح وکیل لازم است.")

    def _positive_version(value: Any, label: str) -> int:
        if isinstance(value, bool):
            raise ValueError(f"{label} معتبر نیست.")
        try:
            number = int(value)
        except (TypeError, ValueError):
            raise ValueError(f"{label} معتبر نیست.") from None
        if number < 1:
            raise ValueError(f"{label} معتبر نیست.")
        return number

    source_version = _positive_version(source_profile_version, "نسخه مبدأ")
    if isinstance(expected_profile_version, bool):
        raise ValueError("نسخه فعلی مورد انتظار معتبر نیست.")
    try:
        expected = int(expected_profile_version)
    except (TypeError, ValueError):
        raise ValueError("نسخه فعلی مورد انتظار معتبر نیست.") from None
    if expected < 0:
        raise ValueError("نسخه فعلی مورد انتظار معتبر نیست.")
    now = _utc_now()
    init_lawyer_preference_tables()
    conn = _connect()
    try:
        conn.execute("BEGIN IMMEDIATE")
        current = conn.execute(
            "SELECT * FROM lawyer_preference_profiles WHERE user_id=?", (owner,)
        ).fetchone()
        if current is None:
            raise ProfileNotFound("حافظه ترجیحات هنوز ایجاد نشده است.")
        actual = int(current["profile_version"])
        if actual != expected:
            raise ProfileVersionConflict(
                f"نسخه پروفایل تغییر کرده است؛ نسخه فعلی {actual} است."
            )
        latest = conn.execute(
            "SELECT MAX(profile_version) AS version FROM lawyer_preference_versions WHERE user_id=?",
            (owner,),
        ).fetchone()
        if int(latest["version"] or 0) != actual:
            raise ProfileIntegrityError("تاریخچه پروفایل با نسخه فعلی هماهنگ نیست؛ بازیابی متوقف شد.")
        source = conn.execute(
            "SELECT schema_version,preferences_json,field_metadata_json FROM lawyer_preference_versions WHERE user_id=? AND profile_version=?",
            (owner, source_version),
        ).fetchone()
        if source is None:
            raise ProfileVersionNotFound("نسخه انتخاب‌شده در تاریخچه این وکیل پیدا نشد.")

        new_version = actual + 1
        conn.execute("""UPDATE lawyer_preference_profiles
            SET preferences_json=?, field_metadata_json=?, schema_version=?,
                profile_version=?, updated_at=?, confirmed_at=?
            WHERE user_id=?""",
            (source["preferences_json"], source["field_metadata_json"],
             source["schema_version"], new_version, now, now, owner))
        conn.execute("""INSERT INTO lawyer_preference_versions
            (user_id,profile_version,schema_version,preferences_json,field_metadata_json,change_type,created_at)
            VALUES(?,?,?,?,?,?,?)""",
            (owner, new_version, source["schema_version"], source["preferences_json"],
             source["field_metadata_json"], "restored", now))
        conn.commit()
        return {
            "profile_version": new_version,
            "source_profile_version": source_version,
            "status": current["status"],
            "changed": True,
            "updated_at": now,
        }
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()



def hard_delete_profile(
    user_id: int,
    *,
    expected_profile_version: int,
    confirm_action: bool,
) -> dict:
    """Permanently delete the owner's profile and every history snapshot atomically.

    No tombstone is retained. A later first save starts again at version 1.
    The explicit history DELETE is required because snapshots reference users,
    not the profile row, so deleting the profile alone would leave history.
    """
    owner = _owner_id(user_id)
    if confirm_action is not True:
        raise ConfirmationRequired("برای حذف دائمی حافظه، تأیید صریح وکیل لازم است.")
    if isinstance(expected_profile_version, bool):
        raise ValueError("نسخه فعلی مورد انتظار معتبر نیست.")
    try:
        expected = int(expected_profile_version)
    except (TypeError, ValueError):
        raise ValueError("نسخه فعلی مورد انتظار معتبر نیست.") from None
    if expected < 1:
        raise ValueError("نسخه فعلی مورد انتظار معتبر نیست.")

    init_lawyer_preference_tables()
    conn = _connect()
    try:
        conn.execute("BEGIN IMMEDIATE")
        current = conn.execute(
            "SELECT profile_version FROM lawyer_preference_profiles WHERE user_id=?", (owner,)
        ).fetchone()
        if current is None:
            raise ProfileNotFound("حافظه ترجیحات برای حذف پیدا نشد.")
        actual = int(current["profile_version"])
        if actual != expected:
            raise ProfileVersionConflict(
                f"نسخه پروفایل تغییر کرده است؛ نسخه فعلی {actual} است."
            )
        latest = conn.execute(
            "SELECT MAX(profile_version) AS version, COUNT(*) AS total FROM lawyer_preference_versions WHERE user_id=?",
            (owner,),
        ).fetchone()
        if int(latest["version"] or 0) != actual or int(latest["total"] or 0) != actual:
            raise ProfileIntegrityError("تاریخچه پروفایل با نسخه فعلی سازگار نیست؛ حذف متوقف شد.")

        deleted_versions = conn.execute(
            "DELETE FROM lawyer_preference_versions WHERE user_id=?", (owner,)
        ).rowcount
        deleted_profiles = conn.execute(
            "DELETE FROM lawyer_preference_profiles WHERE user_id=?", (owner,)
        ).rowcount
        if deleted_profiles != 1 or deleted_versions != actual:
            raise ProfileIntegrityError("حذف کامل حافظه تأیید نشد؛ تراکنش بازگردانده شد.")
        conn.commit()
        return {"deleted": True, "deleted_versions": deleted_versions}
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

def get_profile(user_id: int) -> dict | None:
    """Read the owner's current profile; does not create an empty row."""
    owner = _owner_id(user_id)
    init_lawyer_preference_tables()
    with _connect() as conn:
        row = conn.execute("SELECT * FROM lawyer_preference_profiles WHERE user_id=?", (owner,)).fetchone()
    if not row:
        return None
    return {
        "user_id": owner,
        "preferences": json.loads(row["preferences_json"]),
        "field_metadata": json.loads(row["field_metadata_json"]),
        "schema_version": row["schema_version"],
        "profile_version": int(row["profile_version"]),
        "status": row["status"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "confirmed_at": row["confirmed_at"],
    }


def list_profile_versions(user_id: int, *, limit: int = 20) -> list[dict]:
    """Return bounded, owner-only immutable snapshots (newest first)."""
    owner = _owner_id(user_id)
    try:
        bounded = max(1, min(50, int(limit)))
    except (TypeError, ValueError):
        bounded = 20
    init_lawyer_preference_tables()
    with _connect() as conn:
        rows = conn.execute("""SELECT profile_version,schema_version,preferences_json,
            field_metadata_json,change_type,created_at FROM lawyer_preference_versions
            WHERE user_id=? ORDER BY profile_version DESC LIMIT ?""", (owner, bounded)).fetchall()
    return [{
        "profile_version": int(row["profile_version"]),
        "schema_version": row["schema_version"],
        "preferences": json.loads(row["preferences_json"]),
        "field_metadata": json.loads(row["field_metadata_json"]),
        "change_type": row["change_type"],
        "created_at": row["created_at"],
    } for row in rows]

def compare_profile_versions(
    user_id: int, *, from_profile_version: int, to_profile_version: int
) -> dict:
    """Compare two immutable snapshots belonging to the authenticated owner.

    Returns a deterministic field-level diff. Neither snapshot is modified.
    The comparison is read-only and does not expose database row IDs or owner IDs.
    """
    owner = _owner_id(user_id)
    def _version(value: Any, label: str) -> int:
        if isinstance(value, bool):
            raise ValueError(f"{label} معتبر نیست.")
        try:
            number = int(value)
        except (TypeError, ValueError):
            raise ValueError(f"{label} معتبر نیست.") from None
        if number < 1:
            raise ValueError(f"{label} معتبر نیست.")
        return number

    from_version = _version(from_profile_version, "نسخه مبدأ")
    to_version = _version(to_profile_version, "نسخه مقصد")
    if from_version == to_version:
        raise ValueError("برای مقایسه باید دو نسخه متفاوت انتخاب شوند.")

    init_lawyer_preference_tables()
    with _connect() as conn:
        rows = conn.execute("""SELECT profile_version,schema_version,preferences_json,
            field_metadata_json,change_type,created_at FROM lawyer_preference_versions
            WHERE user_id=? AND profile_version IN (?,?)""",
            (owner, from_version, to_version)).fetchall()
    snapshots = {int(row["profile_version"]): row for row in rows}
    if from_version not in snapshots or to_version not in snapshots:
        raise ProfileVersionNotFound("یکی از نسخه‌های انتخاب‌شده در تاریخچه این وکیل پیدا نشد.")

    def _flatten(value: Any, prefix: str = "") -> dict[str, Any]:
        result: dict[str, Any] = {}
        if isinstance(value, dict) and value:
            for key in sorted(value):
                path = f"{prefix}.{key}" if prefix else str(key)
                result.update(_flatten(value[key], path))
        elif prefix:
            result[prefix] = value
        return result

    before = json.loads(snapshots[from_version]["preferences_json"])
    after = json.loads(snapshots[to_version]["preferences_json"])
    before_flat, after_flat = _flatten(before), _flatten(after)
    changes = []
    for key in sorted(set(before_flat) | set(after_flat)):
        old_present, new_present = key in before_flat, key in after_flat
        old_value, new_value = before_flat.get(key), after_flat.get(key)
        if old_present and new_present and old_value == new_value:
            continue
        change_type = "added" if not old_present else "removed" if not new_present else "changed"
        changes.append({
            "field": key, "change_type": change_type,
            "before": old_value if old_present else None,
            "after": new_value if new_present else None,
        })

    from_row, to_row = snapshots[from_version], snapshots[to_version]
    return {
        "from_profile_version": from_version,
        "to_profile_version": to_version,
        "from_created_at": from_row["created_at"],
        "to_created_at": to_row["created_at"],
        "from_change_type": from_row["change_type"],
        "to_change_type": to_row["change_type"],
        "schema_changed": from_row["schema_version"] != to_row["schema_version"],
        "change_count": len(changes),
        "changes": changes,
    }

