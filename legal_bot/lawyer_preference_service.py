"""Application service bridging the existing lawyer preference form to storage.

Stage 3.4: this module is deliberately transport-agnostic. HTTP routes and
Mini App network calls are wired in Stage 3.5. It does not accept an owner ID
from form data; callers must pass the authenticated Telegram UID separately.
"""
from __future__ import annotations

from typing import Any

from .lawyer_preferences import get_schema, normalize_preferences
from . import lawyer_preference_store as store


def _owner(uid: Any) -> int:
    # Reuse the repository's strict owner validation without exposing internals.
    if isinstance(uid, bool):
        raise ValueError("شناسه وکیل معتبر نیست.")
    try:
        value = int(uid)
    except (TypeError, ValueError):
        raise ValueError("شناسه وکیل معتبر نیست.") from None
    if value <= 0:
        raise ValueError("شناسه وکیل معتبر نیست.")
    return value


def _editor_profile(profile: dict | None) -> dict:
    """Return only the form's editable state and concurrency metadata."""
    if profile is None:
        return {
            "exists": False,
            "preferences": {},
            "profile_version": 0,
            "status": "not_created",
            "updated_at": None,
            "confirmed_at": None,
        }
    return {
        "exists": True,
        "preferences": profile["preferences"],
        "profile_version": profile["profile_version"],
        "status": profile["status"],
        "updated_at": profile["updated_at"],
        "confirmed_at": profile["confirmed_at"],
    }


def load_editor(uid: Any) -> dict:
    """Load schema plus this authenticated lawyer's current form values."""
    owner = _owner(uid)
    profile = store.get_profile(owner)
    return {"schema": get_schema(), "profile": _editor_profile(profile)}


def preview_editor(preferences: Any) -> dict:
    """Validate the same draft collected by the existing Mini App form."""
    normalized, selected_count = normalize_preferences(preferences or {})
    store.validate_preference_privacy(normalized)
    return {
        "preferences": normalized,
        "selected_count": selected_count,
        "persisted": False,
    }


def save_editor(uid: Any, payload: Any) -> dict:
    """Persist the form only after explicit confirmation and version matching.

    ``confirmed_suggestion_fields`` is an optional list of exact dotted field
    keys which the lawyer explicitly accepted in the form. Suggestions are
    never persisted merely because the suggestion engine produced them.
    """
    owner = _owner(uid)
    if not isinstance(payload, dict):
        raise ValueError("اطلاعات فرم ترجیحات معتبر نیست.")
    confirmed = payload.get("confirm_save") is True
    if not confirmed:
        raise store.ConfirmationRequired("برای ذخیره دائمی، تأیید صریح وکیل لازم است.")
    if "expected_profile_version" not in payload:
        raise ValueError("نسخه پروفایل برای ذخیره مشخص نشده است.")

    normalized, _ = normalize_preferences(payload.get("preferences") or {})
    store.validate_preference_privacy(normalized)
    confirmed_suggestions = payload.get("confirmed_suggestion_fields", [])
    if not isinstance(confirmed_suggestions, list) or any(not isinstance(x, str) for x in confirmed_suggestions):
        raise ValueError("فهرست پیشنهادهای تأییدشده معتبر نیست.")
    selected_keys = {
        f"{category}.{field}"
        for category, fields in normalized.items()
        for field in fields
    }
    if len(set(confirmed_suggestions)) != len(confirmed_suggestions) or set(confirmed_suggestions) - selected_keys:
        raise ValueError("پیشنهاد تأییدشده با ترجیحات فرم تطبیق ندارد.")

    metadata = {
        key: {"origin": "lawyer_confirmed_suggestion" if key in set(confirmed_suggestions) else "lawyer_entered"}
        for key in sorted(selected_keys)
    }
    saved = store.save_profile(
        owner,
        normalized,
        expected_profile_version=payload["expected_profile_version"],
        confirm_save=True,
        field_metadata=metadata,
    )
    # Do not return user_id or raw storage metadata to the browser.
    return {"profile": _editor_profile(saved), "selected_count": saved["selected_count"], "persisted": True}


def list_history(uid: Any, limit: int = 20) -> list[dict]:
    """Bounded history DTO for the same owner; management UI is a later stage."""
    owner = _owner(uid)
    return store.list_profile_versions(owner, limit=limit)


def change_editor_status(uid: Any, payload: Any, target_status: str) -> dict:
    """Change active/inactive state using the authenticated owner and CAS version."""
    owner = _owner(uid)
    if not isinstance(payload, dict):
        raise ValueError("اطلاعات تغییر وضعیت معتبر نیست.")
    if "expected_profile_version" not in payload:
        raise ValueError("نسخه پروفایل برای تغییر وضعیت مشخص نشده است.")
    result = store.set_profile_status(
        owner,
        target_status=target_status,
        expected_profile_version=payload["expected_profile_version"],
        confirm_action=payload.get("confirm_action") is True,
    )
    return {"profile": _editor_profile(store.get_profile(owner)), **result}


def restore_editor_version(uid: Any, payload: Any) -> dict:
    """Restore one owner-scoped historical snapshot after explicit confirmation."""
    owner = _owner(uid)
    if not isinstance(payload, dict):
        raise ValueError("اطلاعات بازیابی نسخه معتبر نیست.")
    for key in ("source_profile_version", "expected_profile_version"):
        if key not in payload:
            raise ValueError("نسخه مبدأ و نسخه فعلی برای بازیابی الزامی هستند.")
    result = store.restore_profile_version(
        owner,
        source_profile_version=payload["source_profile_version"],
        expected_profile_version=payload["expected_profile_version"],
        confirm_action=payload.get("confirm_action") is True,
    )
    return {"profile": _editor_profile(store.get_profile(owner)), **result}


def delete_editor_profile(uid: Any, payload: Any) -> dict:
    """Permanently remove the authenticated lawyer's profile and history."""
    owner = _owner(uid)
    if not isinstance(payload, dict):
        raise ValueError("اطلاعات حذف حافظه معتبر نیست.")
    if "expected_profile_version" not in payload:
        raise ValueError("نسخه فعلی برای حذف مشخص نشده است.")
    result = store.hard_delete_profile(
        owner,
        expected_profile_version=payload["expected_profile_version"],
        confirm_action=payload.get("confirm_action") is True,
    )
    return result


def compare_history(uid: Any, payload: Any) -> dict:
    """Compare two versions without accepting an owner ID from the client."""
    owner = _owner(uid)
    if not isinstance(payload, dict):
        raise ValueError("اطلاعات مقایسه نسخه‌ها معتبر نیست.")
    for key in ("from_profile_version", "to_profile_version"):
        if key not in payload:
            raise ValueError("انتخاب هر دو نسخه برای مقایسه الزامی است.")
    return store.compare_profile_versions(
        owner,
        from_profile_version=payload["from_profile_version"],
        to_profile_version=payload["to_profile_version"],
    )
