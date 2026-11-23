"""V67 durable file storage helpers.

Telegram uploads are treated as transport/temporary input. Files explicitly
attached to a case are copied into the durable case storage tree. Temporary
OCR/AI files are deleted after processing and cleaned again by the retention job.
"""
from pathlib import Path
import hashlib, mimetypes, shutil, uuid
from .config import CASE_STORAGE_DIR, TEMP_STORAGE_DIR


def _safe_name(name: str) -> str:
    name = Path(name or 'document').name
    # Keep unicode filenames, but strip path/control characters.
    return ''.join(ch for ch in name if ch.isalnum() or ch in ' ._-()[]')[:180] or 'document'



def validate_supported_file(path, suffix):
    """Validate file content against the upload suffix before parsing/storing it.

    Extensions are user-controlled metadata. PDF/DOCX/image uploads get a
    lightweight magic/content check; plain text is intentionally permissive.
    """
    p = Path(path)
    if not p.is_file() or p.stat().st_size == 0:
        return False
    suffix = (suffix or p.suffix).lower()
    with p.open('rb') as f:
        head = f.read(8)
    if suffix == '.pdf':
        return head.startswith(b'%PDF-')
    if suffix == '.docx':
        if not head.startswith(b'PK'):
            return False
        try:
            import zipfile
            with zipfile.ZipFile(p) as z:
                names = set(z.namelist())
                return '[Content_Types].xml' in names and 'word/document.xml' in names
        except (OSError, zipfile.BadZipFile):
            return False
    if suffix in {'.jpg', '.jpeg'}:
        return head.startswith(b'\xff\xd8\xff')
    if suffix == '.png':
        return head.startswith(b'\x89PNG\r\n\x1a\n')
    if suffix == '.webp':
        # WebP files use a RIFF container with WEBP as the form type.
        with p.open('rb') as f:
            signature = f.read(12)
        return len(signature) == 12 and signature[:4] == b'RIFF' and signature[8:12] == b'WEBP'
    if suffix == '.txt':
        return True
    return False

def store_case_file(case_id: int, source_path, original_name: str, category='documents'):
    # Category is internal, but keep a strict allow-list so a future caller
    # cannot turn this helper into a path traversal primitive.
    if category not in {'documents', 'versions'}:
        raise ValueError('invalid storage category')
    src = Path(source_path).resolve()
    if not src.is_file():
        raise FileNotFoundError(str(src))
    dest_dir = CASE_STORAGE_DIR / str(int(case_id)) / category
    dest_dir.mkdir(parents=True, exist_ok=True)
    safe = _safe_name(original_name)
    stem, suffix = Path(safe).stem, Path(safe).suffix
    dest = dest_dir / f"{uuid.uuid4().hex[:12]}_{stem}{suffix}"
    shutil.copy2(src, dest)
    digest = hashlib.sha256(dest.read_bytes()).hexdigest()
    return {
        'storage_path': str(dest.relative_to(CASE_STORAGE_DIR.parent)),
        'file_size': dest.stat().st_size,
        'sha256': digest,
        'mime_type': mimetypes.guess_type(dest.name)[0] or 'application/octet-stream',
        'absolute_path': str(dest),
    }


def cleanup_temp_files(max_age_hours=24):
    import time
    cutoff = time.time() - max(1, int(max_age_hours)) * 3600
    removed = 0
    for root in (TEMP_STORAGE_DIR,):
        root.mkdir(parents=True, exist_ok=True)
        for p in root.rglob('*'):
            if p.is_file() and p.stat().st_mtime < cutoff:
                try:
                    p.unlink(); removed += 1
                except OSError:
                    pass
    return removed
