# -*- coding: utf-8 -*-
"""Append-only staging registry; deliberately disconnected from active JSON bank."""
from __future__ import annotations
import json, os, tempfile
from pathlib import Path
from typing import Iterable
from .models import CandidateDocument

class StagingRegistry:
    def __init__(self, path: str | Path):
        self.path = Path(path)

    def add_candidates(self, candidates: Iterable[CandidateDocument]) -> dict[str, int]:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self.path.exists():
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        else:
            payload = {"schema_version": "1.0", "records": []}
        records = payload.setdefault("records", [])
        candidate_list = list(candidates)
        known = {r.get("candidate_key") for r in records}
        added = 0
        for candidate in candidate_list:
            key = candidate.stable_key
            if key in known:
                continue
            row = candidate.to_dict()
            row["candidate_key"] = key
            row["workflow_status"] = "discovered"
            records.append(row)
            known.add(key)
            added += 1
        payload["updated_at"] = __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat()
        fd, temp_name = tempfile.mkstemp(prefix=self.path.name + ".", suffix=".tmp", dir=str(self.path.parent))
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                json.dump(payload, stream, ensure_ascii=False, indent=2)
                stream.flush(); os.fsync(stream.fileno())
            os.replace(temp_name, self.path)
        finally:
            if os.path.exists(temp_name):
                os.unlink(temp_name)
        return {"added": added, "duplicates_skipped": len(candidate_list) - added}
