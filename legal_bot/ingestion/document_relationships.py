# -*- coding: utf-8 -*-
"""Phase 7.6: conservative legal-document structure and relationship graph.

All extracted links are candidates with source locations. This module does not
make legal findings about amendment, repeal, validity, precedence, or force.
It consumes caller-supplied catalog/structure data only; no network or bank I/O.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


class RelationshipBuildError(ValueError):
    """Invalid graph input or policy."""


_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
_SPACE = re.compile(r"\s+")
_ARTICLE_REF = re.compile(r"ماده\s*\(?\s*([0-9]{1,4}|[الف-ی])\s*\)?")
_AMEND = ("اصلاح می‌شود", "اصلاح می‌گردد", "اصلاح شد", "اصلاح قانون", "اصلاح می‌نماید")
_REPEAL = ("نسخ می‌شود", "ملغی می‌شود", "لغو می‌شود", "نسخ گردید", "از تاریخ ... لغو")
_ADD = ("الحاق می‌شود", "الحاق می‌گردد", "به قانون اضافه می‌شود", "افزوده می‌شود")
_REPLACE = ("جایگزین می‌شود", "جایگزین می‌گردد", "به شرح زیر جایگزین", "متن زیر جایگزین")
_DELETE = ("حذف می‌شود", "حذف می‌گردد", "عبارت ... حذف", "کلمه ... حذف")
_RENUMBER = ("شماره‌گذاری مجدد", "تغییر شماره ماده", "شماره ماده به", "به شماره جدید تغییر")


def _norm(text: str) -> str:
    value = str(text or "").replace("ي", "ی").replace("ك", "ک").translate(_DIGITS)
    value = value.replace("ۀ", "ه").replace("ة", "ه")
    return _SPACE.sub(" ", value).strip().casefold()


def _sha(payload: Any) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _contains_exact_title(normalized_text: str, normalized_title: str) -> bool:
    """Match a normalized title as a complete phrase, not as a word prefix."""
    if not normalized_title:
        return False
    pattern = r"(?<!\w)" + re.escape(normalized_title) + r"(?!\w)"
    return re.search(pattern, normalized_text, flags=re.UNICODE) is not None


def _iter_lines(structure: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for field in ("preamble", "trailing_text"):
        for row in structure.get(field, []) or []:
            if isinstance(row, dict) and str(row.get("text", "")).strip():
                rows.append({"page_number": row.get("page_number"), "line_number": row.get("line_number"), "text": str(row["text"])})
    for article in structure.get("articles", []) or []:
        for line in article.get("text_lines", []) or []:
            if isinstance(line, dict) and str(line.get("text", "")).strip():
                rows.append({"page_number": line.get("page_number", article.get("start_page")), "line_number": line.get("line_number"), "text": str(line["text"])})
        for note in article.get("notes", []) or []:
            for line in note.get("text_lines", []) or []:
                if isinstance(line, dict) and str(line.get("text", "")).strip():
                    rows.append({"page_number": line.get("page_number", article.get("start_page")), "line_number": line.get("line_number"), "text": str(line["text"])})
    return rows


@dataclass(frozen=True)
class RelationshipPolicy:
    max_documents: int = 5000
    max_edges: int = 50000
    min_title_chars: int = 12
    include_secondary_candidates: bool = True

    def validate(self) -> None:
        if min(self.max_documents, self.max_edges, self.min_title_chars) < 1:
            raise RelationshipBuildError("policy limits must be positive")


def build_document_graph(documents: Iterable[dict[str, Any]], *,
                         policy: RelationshipPolicy | None = None) -> dict[str, Any]:
    """Build a review-only graph from catalog rows enriched with parsed structure.

    Expected row keys: document_id, record{title, document_type, source_id},
    optional source_authority_at_discovery, structure{articles,preamble,...}.
    Catalog metadata relationships are retained only as unverified candidates.
    """
    policy = policy or RelationshipPolicy()
    policy.validate()
    docs = list(documents)
    if len(docs) > policy.max_documents:
        raise RelationshipBuildError("document count exceeds policy limit")
    ids: set[str] = set()
    prepared: list[dict[str, Any]] = []
    for row in docs:
        if not isinstance(row, dict):
            raise RelationshipBuildError("each document must be an object")
        doc_id = str(row.get("document_id", "")).strip()
        record = row.get("record") or {}
        title = str(record.get("title", row.get("title", ""))).strip()
        if not doc_id or not title:
            raise RelationshipBuildError("document_id and title are required")
        if doc_id in ids:
            raise RelationshipBuildError("duplicate document_id")
        ids.add(doc_id)
        authority = str(row.get("source_authority_at_discovery", row.get("source_authority", "unverified")))
        if authority not in {"official_primary", "secondary", "unverified"}:
            authority = "unverified"
        if authority != "official_primary" and not policy.include_secondary_candidates:
            continue
        prepared.append({"id": doc_id, "title": title, "norm_title": _norm(title),
                         "record": record, "authority": authority,
                         "structure": row.get("structure") or {}})

    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []

    def add_edge(edge: dict[str, Any]) -> None:
        edges.append(edge)
        if len(edges) > policy.max_edges:
            raise RelationshipBuildError("edge count exceeds policy limit")

    prepared_ids = {doc["id"] for doc in prepared}
    for doc in prepared:
        articles = doc["structure"].get("articles", []) or []
        nodes.append({"id": doc["id"], "type": "document", "title": doc["title"],
                      "document_type": doc["record"].get("document_type", "other"),
                      "source_id": doc["record"].get("source_id", ""),
                      "source_authority": doc["authority"], "review_required": True})
        for index, article in enumerate(articles):
            number = str(article.get("number", "")).strip()
            if not number:
                continue
            article_id = f"{doc['id']}#article:{number}:{index}"
            nodes.append({"id": article_id, "type": "article", "document_id": doc["id"],
                          "article_number": number, "start_page": article.get("start_page"),
                          "end_page": article.get("end_page"), "review_required": True})
            add_edge({"id": _sha([doc["id"], "contains_article", article_id])[:24],
                          "from": doc["id"], "to": article_id, "type": "contains_article",
                          "confidence": "structural_parser_output", "status": "machine_extracted_candidate",
                          "evidence": {"start_page": article.get("start_page"), "end_page": article.get("end_page")}})
            for note_index, note in enumerate(article.get("notes", []) or []):
                note_id = f"{article_id}#note:{note_index}"
                note_pages = [line.get("page_number") for line in note.get("text_lines", []) if line.get("page_number") is not None]
                nodes.append({"id": note_id, "type": "note", "document_id": doc["id"],
                              "article_id": article_id, "label": note.get("label", "تبصره"),
                              "number": note.get("number"), "page_numbers": sorted(set(note_pages)),
                              "review_required": True})
                add_edge({"id": _sha([article_id, "contains_note", note_id])[:24],
                              "from": article_id, "to": note_id, "type": "contains_note",
                              "confidence": "structural_parser_output", "status": "machine_extracted_candidate",
                              "evidence": {"page_numbers": sorted(set(note_pages))}})
            for band_index, band in enumerate(article.get("bands", []) or []):
                band_id = f"{article_id}#band:{band_index}"
                band_pages = [line.get("page_number") for line in band.get("text_lines", []) if line.get("page_number") is not None]
                nodes.append({"id": band_id, "type": "band", "document_id": doc["id"],
                              "article_id": article_id, "label": band.get("label"),
                              "page_numbers": sorted(set(band_pages)), "review_required": True})
                add_edge({"id": _sha([article_id, "contains_band", band_id])[:24],
                              "from": article_id, "to": band_id, "type": "contains_band",
                              "confidence": "structural_parser_output", "status": "machine_extracted_candidate",
                              "evidence": {"page_numbers": sorted(set(band_pages))}})
                for sub_index, subitem in enumerate(band.get("subitems", []) or []):
                    sub_id = f"{band_id}#subitem:{sub_index}"
                    sub_pages = [line.get("page_number") for line in subitem.get("text_lines", []) if line.get("page_number") is not None]
                    nodes.append({"id": sub_id, "type": "subitem", "document_id": doc["id"],
                                  "band_id": band_id, "label": subitem.get("label"),
                                  "page_numbers": sorted(set(sub_pages)), "review_required": True})
                    add_edge({"id": _sha([band_id, "contains_subitem", sub_id])[:24],
                                  "from": band_id, "to": sub_id, "type": "contains_subitem",
                                  "confidence": "structural_parser_output", "status": "machine_extracted_candidate",
                                  "evidence": {"page_numbers": sorted(set(sub_pages))}})

    # Exact normalized title mentions only. Short titles are skipped to avoid false positives.
    title_targets = [d for d in prepared if len(d["norm_title"]) >= policy.min_title_chars]
    for source in prepared:
        lines = _iter_lines(source["structure"])
        for line in lines:
            normalized = _norm(line["text"])
            for target in title_targets:
                if target["id"] == source["id"] or not _contains_exact_title(normalized, target["norm_title"]):
                    continue
                article_refs = sorted(set(_ARTICLE_REF.findall(normalized)))
                add_edge({"id": _sha([source["id"], target["id"], line, "mentions_document"])[:24],
                              "from": source["id"], "to": target["id"], "type": "mentions_document",
                              "confidence": "exact_title_text_match", "status": "candidate_unverified",
                              "evidence": {"page_number": line.get("page_number"), "line_number": line.get("line_number"),
                                           "excerpt": line["text"][:500], "article_references": article_refs}})
                # Conservative phrase classification. Exact target-title matching is
                # required above; the resulting edge remains a candidate, never a legal finding.
                relation = None
                if any(token in normalized for token in _REPEAL):
                    relation = "possible_repeals"
                elif any(token in normalized for token in _REPLACE):
                    relation = "possible_replaces"
                elif any(token in normalized for token in _ADD):
                    relation = "possible_adds"
                elif any(token in normalized for token in _DELETE):
                    relation = "possible_deletions"
                elif any(token in normalized for token in _RENUMBER):
                    relation = "possible_renumbering"
                elif any(token in normalized for token in _AMEND):
                    relation = "possible_amends"
                if relation:
                    add_edge({"id": _sha([source["id"], target["id"], line, relation])[:24],
                                  "from": source["id"], "to": target["id"], "type": relation,
                                  "confidence": "explicit_phrase_and_exact_title_match",
                                  "status": "human_legal_review_required",
                                  "evidence": {"page_number": line.get("page_number"), "line_number": line.get("line_number"),
                                               "excerpt": line["text"][:500], "article_references": article_refs}})

    # Catalog-supplied related IDs are preserved as hints, never promoted to facts.
    for doc in prepared:
        for target_id in doc["record"].get("related_document_ids", []) or []:
            if target_id in prepared_ids and target_id != doc["id"]:
                add_edge({"id": _sha([doc["id"], target_id, "catalog_hint"])[:24],
                              "from": doc["id"], "to": target_id, "type": "catalog_relationship_hint",
                              "confidence": "catalog_metadata", "status": "candidate_unverified",
                              "evidence": {"metadata_field": "related_document_ids"}})

    # Stable de-duplication by edge id, while preserving distinct evidence locations.
    unique_edges = {edge["id"]: edge for edge in edges}
    edges = sorted(unique_edges.values(), key=lambda x: (x["from"], x["to"], x["type"], x["id"]))
    nodes.sort(key=lambda x: (x["type"], x["id"]))
    graph = {"schema_version": "7.6", "generated_at": datetime.now(timezone.utc).isoformat(),
             "nodes": nodes, "edges": edges,
             "summary": {"document_count": len(prepared), "article_node_count": sum(n["type"] == "article" for n in nodes),
                         "note_node_count": sum(n["type"] == "note" for n in nodes),
                         "band_node_count": sum(n["type"] == "band" for n in nodes),
                         "subitem_node_count": sum(n["type"] == "subitem" for n in nodes),
                         "edge_count": len(edges), "possible_amendment_edges": sum(e["type"] == "possible_amends" for e in edges),
                         "possible_repeal_edges": sum(e["type"] == "possible_repeals" for e in edges),
                         "possible_addition_edges": sum(e["type"] == "possible_adds" for e in edges),
                         "possible_replacement_edges": sum(e["type"] == "possible_replaces" for e in edges),
                         "possible_deletion_edges": sum(e["type"] == "possible_deletions" for e in edges),
                         "possible_renumbering_edges": sum(e["type"] == "possible_renumbering" for e in edges)},
             "safety": {"all_relationships_are_candidates": True, "legal_effect_determined": False,
                        "amendment_or_repeal_not_legally_confirmed": True, "human_review_required": True,
                        "source_authority_not_inferred_from_text": True, "network_access": False,
                        "active_bank_write": False}}
    graph["graph_sha256"] = _sha({"nodes": nodes, "edges": edges})
    return graph


def write_document_graph(graph: dict[str, Any], output_path: str | Path) -> Path:
    """Atomically persist graph as a review-only staging artifact."""
    if graph.get("schema_version") != "7.6" or not graph.get("safety", {}).get("all_relationships_are_candidates"):
        raise RelationshipBuildError("only a valid review-only 7.6 graph may be written")
    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=target.name + ".", suffix=".tmp", dir=str(target.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(graph, stream, ensure_ascii=False, indent=2, sort_keys=True)
            stream.flush(); os.fsync(stream.fileno())
        os.replace(tmp, target)
    finally:
        if os.path.exists(tmp): os.unlink(tmp)
    return target
