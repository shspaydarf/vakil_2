"""Phase 5.5: isolated compatibility preview against the production legal retriever.

Staged records are scored with the same deterministic retrieval functions as the
active corpus, but are never inserted into laws.LEGAL_CORPUS or the live index.
This is a test/preview surface only; it does not establish legal authority.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from .. import laws


def _candidate_records(candidate: Mapping[str, Any]) -> list[dict[str, Any]]:
    kind_map = {
        "statute": "law", "law": "law", "ruling": "ruling",
        "consultation": "consultation", "sample": "sample", "circular": "circular",
    }
    kind = kind_map.get(str(candidate.get("document_kind") or ""))
    if not kind:
        raise ValueError("unsupported_document_kind_for_search_preview")
    title = str(candidate.get("title") or "").strip()
    if not title:
        raise ValueError("candidate_title_required")
    source_sha = str(candidate.get("source_document_sha256") or "")
    out = []
    for row in candidate.get("records", []):
        if not isinstance(row, Mapping):
            continue
        locator = row.get("locator")
        if isinstance(locator, Mapping):
            locator_text = str(locator.get("article") or locator.get("number") or locator.get("label") or "")
        else:
            locator_text = str(locator or "")
        text = str(row.get("text_original") or "")
        if not text.strip():
            continue
        record = {
            "kind": kind, "law": title, "title": title,
            "article": locator_text, "ruling_number": locator_text if kind == "ruling" else "",
            "consultation_number": locator_text if kind == "consultation" else "",
            "text": text, "clean_text": laws.clean_legal_text(text),
            "ntext": laws.norm(laws.clean_legal_text(f"{title} {locator_text} {text}")),
            "source_status": "staging_pending_human_review",
            "verification_label": "آزمایشی؛ در بانک فعال نیست و اعتبار حقوقی آن تأیید نشده است",
            "source_file": candidate.get("original_pdf_path"),
            "source_document_sha256": source_sha,
            "candidate_id": candidate.get("candidate_id"),
            "record_id": row.get("record_id"),
            "source_page_refs": list(row.get("source_page_refs") or []),
        }
        record["citation"] = laws.citation_for_record(record)
        out.append(record)
    return out


def preview_staged_package(package_dir: str | Path, queries: Sequence[str], *, limit: int = 10) -> dict[str, Any]:
    """Score staged records using production retrieval logic without activating them."""
    package = Path(package_dir)
    manifest_path = package / "package_manifest.json"
    candidate_path = package / "candidate.json"
    if not manifest_path.is_file() or not candidate_path.is_file():
        raise FileNotFoundError("staging_package_files_missing")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    candidate = json.loads(candidate_path.read_text(encoding="utf-8"))
    if manifest.get("destination") != "staging" or manifest.get("package_status") != "staged_pending_human_review":
        raise ValueError("preview_requires_valid_staging_package")
    if manifest.get("active_bank_modified") is not False or manifest.get("import_performed") is not False:
        raise ValueError("staging_package_activation_flags_invalid")
    staged = _candidate_records(candidate)
    if not staged:
        raise ValueError("no_searchable_records_in_staging_package")

    # Rebuild corpus statistics for this isolated preview so document-frequency
    # scores are comparable to a corpus containing these records. No global state
    # in the production law module is mutated.
    active_corpus, *_ = laws._research_stats()
    preview_corpus = list(active_corpus) + staged
    freqs, df, total = laws._build_research_stats(preview_corpus)
    results = []
    for query in queries:
        q = str(query or "").strip()
        if len(q) < 2 or len(q) > 200:
            raise ValueError("preview_queries_must_be_between_2_and_200_characters")
        phrases, base_terms = laws._terms(q)
        expanded_terms = []
        try:
            for expanded in laws.expand_query(q):
                expanded_terms.extend(laws._terms(expanded)[1])
        except Exception:
            expanded_terms = []
        base_terms = list(dict.fromkeys(laws._research_tokens(" ".join(base_terms))))
        expanded_terms = list(dict.fromkeys(laws._research_tokens(" ".join(expanded_terms))))
        query_norm = laws.norm(laws.clean_legal_text(q))
        query_number = laws._research_number(q)
        query_intent = laws._source_intent(q)
        hits = []
        for index, record in enumerate(preview_corpus):
            if record.get("candidate_id") != candidate.get("candidate_id"):
                continue
            score, matched = laws._research_score(
                q, record, df, total, base_terms, phrases, expanded_terms, freqs[index],
                query_norm=query_norm, query_number=query_number, query_intent=query_intent,
            )
            if score < 3:
                continue
            hits.append({
                "kind": record["kind"], "title": record["title"],
                "locator": record.get("article"), "snippet": record["clean_text"][:420],
                "retrieval_score": round(score, 3), "matched_terms": matched,
                "citation": record["citation"], "source_page_refs": record["source_page_refs"],
                "candidate_id": record["candidate_id"], "record_id": record["record_id"],
                "activation_status": "staging_only_not_active",
                "verification_label": record["verification_label"],
            })
        hits.sort(key=lambda item: (-item["retrieval_score"], str(item.get("locator") or "")))
        results.append({"query": q, "hits": hits[:max(1, min(int(limit), 20))], "hit_count": len(hits)})
    return {
        "schema_version": "5.5", "candidate_id": candidate.get("candidate_id"),
        "queries": results, "retrieval_engine": "legal_bot.laws.search_legal_research scoring primitives",
        "active_bank_modified": False, "active_search_index_modified": False,
        "production_search_behavior_changed": False, "import_performed": False,
        "legal_authority_confirmed": False,
    }
