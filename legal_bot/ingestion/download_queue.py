# -*- coding: utf-8 -*-
"""Persistent, bounded staging queue for discovered legal-document assets.

This module only plans work. It does not fetch URLs, parse PDFs, or write to the
active legal JSON bank; those responsibilities belong to later phases.
"""
from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable

from .models import CandidateDocument
from .policy import ConnectorPolicy, host_allowed

QUEUE_SCHEMA_VERSION = "1.0"
_ALLOWED_STATES = {"queued", "retry_wait", "downloading", "downloaded", "failed", "cancelled"}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


class DownloadQueue:
    """Atomic JSON queue with URL allowlisting, deduplication and retry metadata."""

    def __init__(self, path: str | Path, *, policy: ConnectorPolicy | None = None,
                 allowed_hosts: Iterable[str] = (), max_queue_items: int = 500):
        self.path = Path(path)
        self.policy = policy or ConnectorPolicy()
        self.allowed_hosts = {h.lower() for h in allowed_hosts}
        self.max_queue_items = max(1, int(max_queue_items))

    def _read(self) -> dict:
        if not self.path.exists():
            return {"schema_version": QUEUE_SCHEMA_VERSION, "items": []}
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict) or not isinstance(payload.get("items"), list):
            raise ValueError("ساختار صف دریافت نامعتبر است")
        return payload

    def _write(self, payload: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, temp_name = tempfile.mkstemp(prefix=self.path.name + ".", suffix=".tmp", dir=str(self.path.parent))
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                json.dump(payload, stream, ensure_ascii=False, indent=2)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temp_name, self.path)
        finally:
            if os.path.exists(temp_name):
                os.unlink(temp_name)

    def enqueue(self, candidates: Iterable[CandidateDocument]) -> dict[str, int]:
        payload = self._read()
        items = payload["items"]
        known = {row.get("candidate_key") for row in items}
        added = duplicates = rejected = 0
        for candidate in candidates:
            # A candidate without a PDF asset is not download work.
            if not candidate.asset_url or not host_allowed(candidate.asset_url, self.allowed_hosts):
                rejected += 1
                continue
            key = candidate.stable_key
            if key in known:
                duplicates += 1
                continue
            if len(items) >= self.max_queue_items:
                rejected += 1
                continue
            now = _now()
            items.append({
                "candidate_key": key,
                "candidate": candidate.to_dict(),
                "state": "queued",
                "attempt_count": 0,
                "max_attempts": 3,
                "created_at": _iso(now),
                "updated_at": _iso(now),
                "next_attempt_at": _iso(now),
                "last_error": None,
            })
            known.add(key)
            added += 1
        payload["schema_version"] = QUEUE_SCHEMA_VERSION
        payload["updated_at"] = _iso(_now())
        self._write(payload)
        return {"added": added, "duplicates_skipped": duplicates, "rejected": rejected}

    def list_items(self, *, state: str | None = None) -> list[dict]:
        if state is not None and state not in _ALLOWED_STATES:
            raise ValueError("وضعیت صف نامعتبر است")
        items = self._read()["items"]
        return [row for row in items if state is None or row.get("state") == state]

    def mark_result(self, candidate_key: str, *, success: bool, error: str | None = None,
                    retry_delay_seconds: int = 300) -> bool:
        """Record a worker result; retries are bounded and never run automatically."""
        payload = self._read()
        for row in payload["items"]:
            if row.get("candidate_key") != candidate_key:
                continue
            if row.get("state") in {"downloaded", "cancelled"}:
                return False
            now = _now()
            if success:
                row["state"] = "downloaded"
                row["last_error"] = None
                row["next_attempt_at"] = None
            else:
                row["attempt_count"] = int(row.get("attempt_count", 0)) + 1
                row["last_error"] = (error or "خطای نامشخص")[:500]
                if row["attempt_count"] < int(row.get("max_attempts", 3)):
                    row["state"] = "retry_wait"
                    delay = max(30, min(int(retry_delay_seconds), 86400))
                    row["next_attempt_at"] = _iso(now + timedelta(seconds=delay))
                else:
                    row["state"] = "failed"
                    row["next_attempt_at"] = None
            row["updated_at"] = _iso(now)
            payload["updated_at"] = _iso(now)
            self._write(payload)
            return True
        return False

    def due_retries(self, *, now: datetime | None = None) -> list[dict]:
        current = now or _now()
        result = []
        for row in self.list_items(state="retry_wait"):
            value = row.get("next_attempt_at")
            try:
                due = datetime.fromisoformat(value) if value else None
            except (TypeError, ValueError):
                due = None
            if due and due <= current:
                result.append(row)
        return result
