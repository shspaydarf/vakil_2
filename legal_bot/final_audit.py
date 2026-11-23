"""V136 lightweight final audit checks; no secrets or client data are printed."""
from pathlib import Path
from .production import health_snapshot
from .config import LAW_FILE


def run_audit():
    snap = health_snapshot()
    return {
        "health": snap,
        "law_corpus_present": Path(LAW_FILE).is_file(),
        "law_corpus_size_bytes": Path(LAW_FILE).stat().st_size if Path(LAW_FILE).is_file() else 0,
        "status": "PASS" if snap.get("bot_token_configured") and snap.get("phone_hash_secret_configured") and snap.get("storage_writable") and snap.get("backup_dir_writable") else "CONFIG_REVIEW",
    }
