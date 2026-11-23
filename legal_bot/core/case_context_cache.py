"""Short-lived, process-local cache for deterministic case intelligence.

Only derived intelligence objects are cached; raw document text, prompts,
provider responses, and AI outputs are never written to disk by this module.
Entries are scoped by (user_id, case_id), fingerprinted against current case
metadata/documents/events, expire quickly, and are bounded in memory.
"""
from __future__ import annotations

import copy
import hashlib
import json
import threading
import time
from collections import OrderedDict
from typing import Any, Callable

_TTL_SECONDS = 120
_MAX_ENTRIES = 128
_LOCK = threading.RLock()
_CACHE: "OrderedDict[tuple[int, int], tuple[str, float, dict[str, Any]]]" = OrderedDict()
_STATS = {"hits": 0, "misses": 0, "invalidations": 0, "evictions": 0}


def case_fingerprint(*, case: dict, documents: list[dict], events: list[dict]) -> str:
    """Hash only the inputs that can change the deterministic case snapshot."""
    doc_parts = []
    for doc in documents or []:
        raw = str(doc.get("extracted_text") or "").encode("utf-8", "replace")
        doc_parts.append({
            "id": doc.get("id"),
            "created_at": doc.get("created_at"),
            "page_count": doc.get("page_count"),
            "sha256": hashlib.sha256(raw).hexdigest(),
        })
    event_parts = [
        {"id": e.get("id"), "created_at": e.get("created_at"),
         "event_type": e.get("event_type"), "title": e.get("title"),
         "details": e.get("details")}
        for e in (events or [])
    ]
    payload = {
        "case_updated_at": case.get("updated_at"),
        "case_name": case.get("file_name") or case.get("name"),
        "documents": doc_parts,
        "events": event_parts,
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def get_or_build(user_id: int, case_id: int, fingerprint: str,
                 builder: Callable[[], dict[str, Any]]) -> tuple[dict[str, Any], bool]:
    """Return a defensive copy and whether it came from a valid cache entry."""
    key = (int(user_id), int(case_id))
    now = time.monotonic()
    with _LOCK:
        entry = _CACHE.get(key)
        if entry:
            old_fingerprint, expires_at, value = entry
            if expires_at > now and old_fingerprint == fingerprint:
                _CACHE.move_to_end(key)
                _STATS["hits"] += 1
                return copy.deepcopy(value), True
            _CACHE.pop(key, None)
            _STATS["invalidations"] += 1
        _STATS["misses"] += 1

    # Do expensive work outside the lock. Failed builders are never cached.
    value = builder()
    if not isinstance(value, dict):
        raise TypeError("case context cache builder must return a dict")
    with _LOCK:
        _CACHE[key] = (fingerprint, now + _TTL_SECONDS, copy.deepcopy(value))
        _CACHE.move_to_end(key)
        while len(_CACHE) > _MAX_ENTRIES:
            _CACHE.popitem(last=False)
            _STATS["evictions"] += 1
    return copy.deepcopy(value), False


def cache_stats() -> dict[str, int]:
    with _LOCK:
        return {**_STATS, "entries": len(_CACHE), "ttl_seconds": _TTL_SECONDS,
                "max_entries": _MAX_ENTRIES}


def clear_cache() -> None:
    """Test/process-maintenance hook; does not touch persistent case data."""
    with _LOCK:
        _CACHE.clear()
        for key in _STATS:
            _STATS[key] = 0
