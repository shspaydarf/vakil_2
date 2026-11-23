# -*- coding: utf-8 -*-
"""Phase 7.2: versioned, fail-closed registry of trusted-source policies.

This module records source authority and access policy. It does not probe networks,
fetch pages, infer legal validity, or change the active legal bank.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlparse

SCHEMA_VERSION = "7.2"
AUTHORITY_LEVELS = {"official_primary", "secondary", "unverified"}
SOURCE_STATUSES = {"unverified", "verified", "temporarily_unavailable", "blocked", "retired"}
ACCESS_MODES = {"manual_only", "polite_public_read", "disabled"}
_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_.-]{1,79}$")


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _clean_hosts(values: Iterable[str]) -> tuple[str, ...]:
    hosts = []
    for value in values:
        host = str(value).strip().lower().rstrip(".")
        if not host or "/" in host or ":" in host or "@" in host or "*" in host:
            raise ValueError("allowed_hosts must contain exact DNS hostnames only")
        if host not in hosts:
            hosts.append(host)
    return tuple(sorted(hosts))


@dataclass(frozen=True)
class SourceRecord:
    source_id: str
    display_name: str
    publisher: str
    jurisdiction: str
    authority_level: str = "unverified"
    document_types: tuple[str, ...] = ()
    allowed_hosts: tuple[str, ...] = ()
    canonical_roots: tuple[str, ...] = ()
    access_mode: str = "disabled"
    respect_robots_txt: bool = True
    min_request_interval_seconds: int = 5
    max_pages_per_run: int = 2
    status: str = "unverified"
    last_checked_at: str | None = None
    last_access_observation: str | None = None
    verification: dict[str, str] = field(default_factory=dict)
    notes: str = ""

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "SourceRecord":
        if not isinstance(raw, dict):
            raise ValueError("source record must be an object")
        hosts = _clean_hosts(raw.get("allowed_hosts", ()))
        roots = tuple(sorted(set(str(x).strip() for x in raw.get("canonical_roots", ()) if str(x).strip())))
        record = cls(
            source_id=str(raw.get("source_id", "")).strip().lower(),
            display_name=str(raw.get("display_name", "")).strip(),
            publisher=str(raw.get("publisher", "")).strip(),
            jurisdiction=str(raw.get("jurisdiction", "")).strip(),
            authority_level=str(raw.get("authority_level", "unverified")).strip().lower(),
            document_types=tuple(sorted(set(str(x).strip() for x in raw.get("document_types", ()) if str(x).strip()))),
            allowed_hosts=hosts,
            canonical_roots=roots,
            access_mode=str(raw.get("access_mode", "disabled")).strip().lower(),
            respect_robots_txt=raw.get("respect_robots_txt", True),
            min_request_interval_seconds=raw.get("min_request_interval_seconds", 5),
            max_pages_per_run=raw.get("max_pages_per_run", 2),
            status=str(raw.get("status", "unverified")).strip().lower(),
            last_checked_at=raw.get("last_checked_at"),
            last_access_observation=raw.get("last_access_observation"),
            verification=dict(raw.get("verification") or {}),
            notes=str(raw.get("notes", "")),
        )
        record.validate()
        return record

    def validate(self) -> None:
        if not _ID_RE.fullmatch(self.source_id):
            raise ValueError("source_id must be a stable lowercase identifier")
        if not self.display_name or not self.publisher or not self.jurisdiction:
            raise ValueError("display_name, publisher and jurisdiction are required")
        if self.authority_level not in AUTHORITY_LEVELS:
            raise ValueError("invalid authority_level")
        if self.status not in SOURCE_STATUSES:
            raise ValueError("invalid source status")
        if self.access_mode not in ACCESS_MODES:
            raise ValueError("invalid access_mode")
        if not isinstance(self.respect_robots_txt, bool):
            raise ValueError("respect_robots_txt must be boolean")
        for key in ("min_request_interval_seconds", "max_pages_per_run"):
            value = getattr(self, key)
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise ValueError(f"{key} must be a positive integer")
        if self.status == "verified":
            required = {"reviewer_id", "reviewed_at", "evidence_ref", "evidence_sha256"}
            if not required.issubset(self.verification) or not all(self.verification.get(k) for k in required):
                raise ValueError("verified source requires reviewer, timestamp, evidence reference and evidence SHA-256")
            digest = self.verification["evidence_sha256"].lower()
            if not re.fullmatch(r"[a-f0-9]{64}", digest):
                raise ValueError("evidence_sha256 must be a 64-character SHA-256 hex digest")
        if self.authority_level == "official_primary" and self.status != "verified":
            raise ValueError("official_primary authority requires verified status and evidence")
        if self.access_mode == "polite_public_read" and (not self.allowed_hosts or self.status != "verified"):
            raise ValueError("public read requires a verified source and exact host allowlist")
        for root in self.canonical_roots:
            parsed = urlparse(root)
            if parsed.scheme != "https" or not parsed.hostname or parsed.hostname.lower() not in self.allowed_hosts:
                raise ValueError("canonical_roots must be HTTPS URLs on an exact allowed host")
            if parsed.username or parsed.password or parsed.query or parsed.fragment:
                raise ValueError("canonical_roots cannot contain credentials, query or fragment")

    def recognizes_url(self, url: str) -> bool:
        """Validate URL provenance against exact registered host/root, without granting network access.

        This is deliberately separate from ``permits_url``: unverified sources may be
        inventoried from supplied/saved HTML and quarantined, but must not be fetched.
        """
        try:
            parsed = urlparse(url)
            host = (parsed.hostname or "").lower().rstrip(".")
            if parsed.scheme != "https" or host not in self.allowed_hosts or parsed.username or parsed.password:
                return False
            if parsed.port not in (None, 443) or not self.canonical_roots:
                return False
            for root in self.canonical_roots:
                base = urlparse(root)
                base_path = base.path.rstrip("/")
                if host == (base.hostname or "").lower().rstrip(".") and (parsed.path == base_path or parsed.path.startswith(base_path + "/")):
                    return True
            return False
        except (TypeError, ValueError):
            return False

    def permits_url(self, url: str) -> bool:
        """Return true only when the source is verified and explicitly permits public reads."""
        return self.status == "verified" and self.access_mode == "polite_public_read" and self.recognizes_url(url)


class SourceRegistry:
    """Append-audited JSON registry with atomic writes and optimistic versioning."""
    def __init__(self, path: str | Path):
        self.path = Path(path)

    def _empty(self) -> dict[str, Any]:
        return {"schema_version": SCHEMA_VERSION, "registry_version": 0, "sources": {}, "audit": []}

    def load(self) -> dict[str, Any]:
        if not self.path.exists():
            return self._empty()
        data = json.loads(self.path.read_text(encoding="utf-8"))
        if data.get("schema_version") != SCHEMA_VERSION or not isinstance(data.get("sources"), dict) or not isinstance(data.get("audit"), list):
            raise ValueError("invalid source registry document")
        for key, raw in data["sources"].items():
            record = SourceRecord.from_dict(raw)
            if key != record.source_id:
                raise ValueError("source registry key mismatch")
        return data

    def upsert(self, record: SourceRecord | dict[str, Any], *, actor_id: str, reason: str,
               expected_version: int | None = None) -> dict[str, Any]:
        if not actor_id.strip() or not reason.strip():
            raise ValueError("actor_id and reason are required for audited changes")
        item = record if isinstance(record, SourceRecord) else SourceRecord.from_dict(record)
        item.validate()
        data = self.load()
        if expected_version is not None and expected_version != data["registry_version"]:
            raise RuntimeError("registry_version_conflict")
        previous = data["sources"].get(item.source_id)
        data["sources"][item.source_id] = asdict(item)
        data["registry_version"] += 1
        event = {
            "version": data["registry_version"], "at": _utc_now(), "actor_id": actor_id,
            "action": "create" if previous is None else "update", "source_id": item.source_id,
            "reason": reason, "previous_sha256": _json_hash(previous) if previous is not None else None,
            "current_sha256": _json_hash(asdict(item)),
        }
        data["audit"].append(event)
        self._atomic_write(data)
        return data

    def get(self, source_id: str) -> SourceRecord | None:
        raw = self.load()["sources"].get(source_id)
        return SourceRecord.from_dict(raw) if raw else None

    def _atomic_write(self, data: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, temp_name = tempfile.mkstemp(prefix=self.path.name + ".", suffix=".tmp", dir=str(self.path.parent))
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                json.dump(data, stream, ensure_ascii=False, indent=2, sort_keys=True)
                stream.flush(); os.fsync(stream.fileno())
            os.replace(temp_name, self.path)
        finally:
            if os.path.exists(temp_name):
                os.unlink(temp_name)


def _json_hash(value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def registry_policy_summary() -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "default_network_access": False,
        "default_authority_level": "unverified",
        "default_source_status": "unverified",
        "secondary_sources_may_substitute_for_official": False,
        "access_challenge_policy": {"403": "stop_and_mark_blocked_or_review", "429": "stop_and_defer", "captcha": "stop_no_bypass"},
        "authority_requires_human_evidence": True,
        "access_observation_is_not_legal_validity": True,
        "active_bank_write": False,
    }
