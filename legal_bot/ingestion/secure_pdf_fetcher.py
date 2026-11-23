# -*- coding: utf-8 -*-
"""Bounded, allowlisted PDF acquisition for the legal-ingestion staging area.

Downloads are opt-in, never execute embedded content, and never touch the active
legal JSON bank. Original bytes are retained under a SHA-256-derived filename.
"""
from __future__ import annotations

import hashlib
import ipaddress
import json
import os
import socket
import tempfile
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

import requests

from .policy import ConnectorPolicy, host_allowed


class PDFDownloadError(ValueError):
    """A candidate could not be safely acquired or validated."""


@dataclass(frozen=True)
class DownloadedPDF:
    path: str
    sha256: str
    size_bytes: int
    page_count: int
    source_url: str
    downloaded_at: str
    content_type: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _public_host(host: str) -> bool:
    """Reject DNS results that could route a source URL into a local network."""
    try:
        addresses = {item[4][0] for item in socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)}
    except OSError as exc:
        raise PDFDownloadError("امکان بررسی DNS منبع وجود ندارد") from exc
    if not addresses:
        raise PDFDownloadError("دامنه منبع IP معتبری ندارد")
    for value in addresses:
        ip = ipaddress.ip_address(value)
        if not ip.is_global:
            raise PDFDownloadError("نشانی مقصد عمومی نیست؛ درخواست برای امنیت متوقف شد")
    return True


def _validate_url(url: str, allowed_hosts: set[str], *, check_dns: bool = True) -> str:
    if not host_allowed(url, allowed_hosts):
        raise PDFDownloadError("دامنه یا طرح نشانی در فهرست مجاز نیست")
    parsed = urlparse(url)
    if parsed.port not in (None, 80, 443):
        raise PDFDownloadError("درگاه غیرمجاز در نشانی منبع")
    host = (parsed.hostname or "").lower()
    if check_dns:
        _public_host(host)
    return host


def _atomic_write(directory: Path, filename: str, data: bytes) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / filename
    if target.exists():
        return target
    fd, temp_name = tempfile.mkstemp(prefix=".machina-", suffix=".part", dir=str(directory))
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp_name, target)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)
    return target


class SecurePDFDownloader:
    def __init__(self, storage_dir: str | Path, *, allowed_hosts: set[str],
                 policy: ConnectorPolicy | None = None, session: requests.Session | None = None,
                 max_pages: int = 2000, max_redirects: int = 3):
        self.storage_dir = Path(storage_dir)
        self.allowed_hosts = {h.lower() for h in allowed_hosts}
        self.policy = policy or ConnectorPolicy()
        self.session = session or requests.Session()
        self.max_pages = max(1, int(max_pages))
        self.max_redirects = max(0, min(int(max_redirects), 5))

    def download(self, url: str) -> DownloadedPDF:
        if not self.policy.allow_downloads:
            raise PDFDownloadError("دریافت فایل در تنظیمات فعلی غیرفعال است")
        current = url
        response = None
        for redirect_count in range(self.max_redirects + 1):
            _validate_url(current, self.allowed_hosts)
            try:
                response = self.session.get(
                    current, stream=True, allow_redirects=False, timeout=(5, self.policy.request_timeout_seconds),
                    headers={"User-Agent": self.policy.user_agent, "Accept": "application/pdf"},
                    verify=True,
                )
            except requests.RequestException as exc:
                raise PDFDownloadError("خطا در ارتباط امن با منبع") from exc
            if response.status_code in (301, 302, 303, 307, 308):
                location = response.headers.get("Location")
                response.close()
                if not location or redirect_count >= self.max_redirects:
                    raise PDFDownloadError("تغییر مسیر نامعتبر یا بیش از حد مجاز")
                current = urljoin(current, location)
                continue
            break
        if response is None:
            raise PDFDownloadError("پاسخی از منبع دریافت نشد")
        try:
            if response.status_code in (403, 429):
                raise PDFDownloadError(f"منبع دسترسی را محدود کرد: HTTP {response.status_code}")
            if response.status_code != 200:
                raise PDFDownloadError(f"پاسخ نامعتبر منبع: HTTP {response.status_code}")
            content_type = response.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
            if content_type not in {"application/pdf", "application/x-pdf", "application/octet-stream"}:
                raise PDFDownloadError("نوع محتوای پاسخ PDF نیست")
            declared = response.headers.get("Content-Length")
            if declared:
                try:
                    if int(declared) > self.policy.max_asset_bytes:
                        raise PDFDownloadError("حجم اعلام‌شده فایل از سقف مجاز بیشتر است")
                except ValueError as exc:
                    raise PDFDownloadError("طول محتوای اعلام‌شده نامعتبر است") from exc
            chunks: list[bytes] = []
            total = 0
            for chunk in response.iter_content(chunk_size=64 * 1024):
                if not chunk:
                    continue
                total += len(chunk)
                if total > self.policy.max_asset_bytes:
                    raise PDFDownloadError("حجم واقعی فایل از سقف مجاز بیشتر است")
                chunks.append(chunk)
            data = b"".join(chunks)
        finally:
            response.close()
        if len(data) < 8 or not data.startswith(b"%PDF-"):
            raise PDFDownloadError("امضای فایل PDF معتبر نیست")
        if b"%%EOF" not in data[-2048:]:
            raise PDFDownloadError("پایان‌بندی PDF ناقص یا نامعتبر است")
        # PyMuPDF is already a project dependency; fail closed if unavailable or malformed.
        try:
            import fitz
            document = fitz.open(stream=data, filetype="pdf")
            try:
                if document.is_encrypted:
                    raise PDFDownloadError("PDF رمزگذاری‌شده پذیرفته نمی‌شود")
                page_count = document.page_count
                if page_count < 1 or page_count > self.max_pages:
                    raise PDFDownloadError("تعداد صفحات PDF خارج از محدوده مجاز است")
            finally:
                document.close()
        except PDFDownloadError:
            raise
        except Exception as exc:
            raise PDFDownloadError("ساختار داخلی PDF قابل تأیید نیست") from exc
        digest = hashlib.sha256(data).hexdigest()
        path = _atomic_write(self.storage_dir, f"{digest}.pdf", data)
        return DownloadedPDF(
            path=str(path), sha256=digest, size_bytes=len(data), page_count=page_count,
            source_url=current, downloaded_at=datetime.now(timezone.utc).isoformat(),
            content_type=content_type,
        )


def write_download_manifest(result: DownloadedPDF, manifest_path: str | Path) -> Path:
    """Write provenance metadata separately from the immutable original PDF."""
    target = Path(manifest_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = result.to_dict()
    fd, temp_name = tempfile.mkstemp(prefix=target.name + ".", suffix=".tmp", dir=str(target.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(payload, stream, ensure_ascii=False, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp_name, target)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)
    return target
