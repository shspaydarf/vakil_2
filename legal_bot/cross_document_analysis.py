"""Conservative, source-linked multi-document analysis.

Findings are extraction and comparison candidates, never verified facts or legal
conclusions. The API must supply documents already scoped to one authorized case.
"""
from __future__ import annotations
from collections import defaultdict
from typing import Any

from .document_facts import extract_document_facts

FACT_LABELS = {
    "date": "تاریخ", "amount": "مبلغ", "national_id": "شناسه ملی",
    "phone": "تلفن", "person_or_party": "شخص/طرف",
}


def analyze_case_documents(documents: list[dict[str, Any]], *, max_documents: int = 50,
                           max_facts_per_document: int = 40,
                           max_chars_per_document: int = 500_000,
                           max_total_chars: int = 2_000_000) -> dict[str, Any]:
    """Extract facts per document within explicit work limits.

    Text limits protect synchronous API workers from unexpectedly large case
    corpora. Any truncation/omission is reported so the UI cannot imply full
    coverage. Findings remain candidates for lawyer review.
    """
    source_docs = list(documents or [])
    limit = max(1, min(int(max_documents), 100))
    per_doc_chars = max(1_000, min(int(max_chars_per_document), 1_000_000))
    total_chars = max(per_doc_chars, min(int(max_total_chars), 10_000_000))
    facts_limit = max(1, min(int(max_facts_per_document), 100))
    selected = source_docs[:limit]
    rows: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    document_summaries: list[dict[str, Any]] = []
    chars_processed = 0
    documents_truncated = 0

    for index, doc in enumerate(selected):
        text = str(doc.get("extracted_text") or "")
        doc_id = doc.get("id", doc.get("document_id"))
        name = str(doc.get("file_name") or doc.get("name") or "سند بدون نام")
        if not text.strip():
            skipped.append({"document_id": doc_id, "file_name": name,
                            "reason": "متن استخراج‌شده در دسترس نیست؛ احتمالاً OCR یا استخراج متن لازم است."})
            document_summaries.append({"document_id": doc_id, "file_name": name,
                                       "status": "no_text", "fact_count": 0,
                                       "text_chars": len(text), "analyzed_chars": 0})
            continue

        remaining = total_chars - chars_processed
        if remaining <= 0:
            skipped.append({"document_id": doc_id, "file_name": name,
                            "reason": "سقف حجم پردازش این نوبت تکمیل شده است؛ این سند در این اجرا تحلیل نشد."})
            document_summaries.append({"document_id": doc_id, "file_name": name,
                                       "status": "limit_skipped", "fact_count": 0,
                                       "text_chars": len(text), "analyzed_chars": 0})
            continue

        allowed_chars = min(len(text), per_doc_chars, remaining)
        analyzed_text = text[:allowed_chars]
        truncated = allowed_chars < len(text)
        if truncated:
            documents_truncated += 1
        chars_processed += allowed_chars
        extracted = extract_document_facts(analyzed_text, limit=facts_limit)
        # Missing IDs must not collapse unrelated documents into one source.
        source_key = str(doc_id) if doc_id is not None else f"missing-id-document-{index}"
        for fact in extracted:
            rows.append({**fact, "document_id": doc_id, "file_name": name,
                         "source_verified": False, "_source_key": source_key})
        document_summaries.append({"document_id": doc_id, "file_name": name,
                                   "status": "analyzed_truncated" if truncated else "analyzed",
                                   "fact_count": len(extracted), "text_chars": len(text),
                                   "analyzed_chars": allowed_chars, "truncated": truncated})

    # Compare only high-signal date/amount candidates. A match is not proof that
    # the underlying facts refer to the same event or obligation.
    by_type: dict[str, dict[str, list[dict[str, Any]]]] = defaultdict(lambda: defaultdict(list))
    for fact in rows:
        norm = fact.get("normalized_value")
        if fact.get("type") in {"date", "amount"} and norm:
            by_type[fact["type"]][str(norm)].append(fact)

    def source_ref(f: dict[str, Any]) -> dict[str, Any]:
        return {k: f.get(k) for k in ("document_id", "file_name", "page", "value", "snippet", "confidence")}

    def source_identity(f: dict[str, Any]) -> str:
        return str(f.get("_source_key") or f.get("document_id"))

    comparisons: list[dict[str, Any]] = []
    matched_values: list[dict[str, Any]] = []
    for kind, values in by_type.items():
        cross_doc_values = {
            value: group for value, group in values.items()
            if len({source_identity(f) for f in group}) >= 2
        }
        if cross_doc_values:
            for value, group in cross_doc_values.items():
                matched_values.append({
                    "type": kind, "label": FACT_LABELS.get(kind, kind),
                    "normalized_value": value,
                    "sources": [source_ref(f) for f in group],
                    "source_document_count": len({source_identity(f) for f in group}),
                    "status": "same_value_found", "review_required": True,
                })
        if len(values) >= 2:
            all_sources = [f for group in values.values() for f in group]
            doc_ids = {source_identity(f) for f in all_sources}
            if len(doc_ids) >= 2 and len(values) > 1:
                comparisons.append({
                    "type": kind, "label": FACT_LABELS.get(kind, kind),
                    "status": "comparison_candidate",
                    "values": [{"normalized_value": value,
                                "sources": [source_ref(f) for f in group]}
                               for value, group in values.items()],
                    "source_document_count": len(doc_ids), "review_required": True,
                    "warning": "تفاوت مقادیر به‌تنهایی تناقض را ثابت نمی‌کند؛ ممکن است به رویدادها، اشخاص، تعهدات یا نسخه‌های متفاوت مربوط باشد.",
                })

    counts = {kind: sum(1 for f in rows if f.get("type") == kind) for kind in FACT_LABELS}
    for fact in rows:
        fact.pop("_source_key", None)
    return {
        "documents_received": len(source_docs),
        "documents_considered": len(selected),
        "documents_omitted_by_limit": max(0, len(source_docs) - len(selected)),
        "documents_analyzed": sum(1 for d in document_summaries if d["status"].startswith("analyzed")),
        "documents_truncated": documents_truncated,
        "documents_skipped_by_text_budget": sum(1 for d in document_summaries if d["status"] == "limit_skipped"),
        "documents_without_text": sum(1 for d in document_summaries if d["status"] == "no_text"),
        "documents_skipped": skipped,
        "document_summaries": document_summaries,
        "characters_processed": chars_processed,
        "character_limit": total_chars,
        "facts": rows,
        "fact_count": len(rows),
        "fact_counts": counts,
        "matched_values": matched_values,
        "matched_value_count": len(matched_values),
        "comparison_candidates": comparisons,
        "comparison_candidate_count": len(comparisons),
        "review_required": True,
        "disclaimer": "یافته‌ها صرفاً از متن استخراج‌شده تولید شده‌اند؛ نه اصالت سند، نه صحت واقعیت و نه تناقض حقوقی را اثبات نمی‌کنند. تطبیق با اصل اسناد و زمینه پرونده بر عهده وکیل است.",
    }
