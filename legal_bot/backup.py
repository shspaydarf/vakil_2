"""V67 backup/rotation helpers. Backups are written outside the live app tree by default."""
from pathlib import Path
from datetime import datetime, timezone
import sqlite3, tarfile, tempfile, os
from .config import DB_PATH, BACKUP_DIR, STORAGE_DIR, DAILY_BACKUPS, WEEKLY_BACKUPS, MONTHLY_BACKUPS


def create_backup():
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    with tempfile.TemporaryDirectory(prefix='legalbot-backup-') as td:
        td=Path(td)
        db_copy=td/'legal_bot.db'
        src=sqlite3.connect(str(DB_PATH))
        dst=sqlite3.connect(str(db_copy))
        try:
            src.backup(dst)
        finally:
            dst.close(); src.close()
        archive=BACKUP_DIR/f'legalbot-{stamp}.tar.gz'
        with tarfile.open(archive,'w:gz') as tar:
            tar.add(db_copy, arcname='legal_bot.db')
            if STORAGE_DIR.exists():
                tar.add(STORAGE_DIR, arcname='storage')
        # Backups contain legal documents and personal data. Do not leave them
        # world-readable when the bot runs on a shared host.
        try:
            os.chmod(archive, 0o600)
        except OSError:
            pass
        return archive


def _keep(paths, n):
    paths=sorted(paths, key=lambda p:p.stat().st_mtime, reverse=True)
    for p in paths[n:]:
        try: p.unlink()
        except OSError: pass


def rotate_backups():
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    files=list(BACKUP_DIR.glob('legalbot-*.tar.gz'))
    # Keep the newest daily set. Weekly/monthly retention is represented by
    # retaining additional snapshots; the rotation never deletes the newest
    # DAILY_BACKUPS + WEEKLY_BACKUPS + MONTHLY_BACKUPS files.
    keep=max(DAILY_BACKUPS, DAILY_BACKUPS + WEEKLY_BACKUPS, DAILY_BACKUPS + WEEKLY_BACKUPS + MONTHLY_BACKUPS)
    _keep(files, keep)
