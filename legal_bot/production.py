"""V135 production readiness helpers.

Small, dependency-free checks used by deployment tooling and operators.  They
avoid exposing secrets or client/case data in health output.
"""
from pathlib import Path
from .config import BOT_TOKEN, PHONE_HASH_SECRET, PHONE_HASH_SECRET_MIN_LEN, DB_PATH, STORAGE_DIR, BACKUP_DIR


def health_snapshot() -> dict:
    """Return a privacy-safe deployment health snapshot."""
    return {
        "bot_token_configured": bool(BOT_TOKEN),
        "phone_hash_secret_configured": len(PHONE_HASH_SECRET) >= PHONE_HASH_SECRET_MIN_LEN,
        "database_present": Path(DB_PATH).is_file(),
        "storage_writable": _writable(STORAGE_DIR),
        "backup_dir_writable": _writable(BACKUP_DIR),
    }


def _writable(path) -> bool:
    p = Path(path)
    try:
        p.mkdir(parents=True, exist_ok=True)
        probe = p / ".healthcheck"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink(missing_ok=True)
        return True
    except OSError:
        return False


def validate_production_config() -> list[str]:
    """Return actionable configuration errors without revealing secret values."""
    errors = []
    if not BOT_TOKEN:
        errors.append("BOT_TOKEN تنظیم نشده است")
    if len(PHONE_HASH_SECRET) < PHONE_HASH_SECRET_MIN_LEN:
        errors.append(f"PHONE_HASH_SECRET باید حداقل {PHONE_HASH_SECRET_MIN_LEN} نویسه باشد")
    snap = health_snapshot()
    if not snap["storage_writable"]:
        errors.append("مسیر storage قابل نوشتن نیست")
    if not snap["backup_dir_writable"]:
        errors.append("مسیر backup قابل نوشتن نیست")
    return errors
