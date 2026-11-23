import json
import pytest
from legal_bot.ingestion.document_relationships import (
    RelationshipBuildError, RelationshipPolicy, build_document_graph, write_document_graph,
)


def _doc(doc_id, title, text="", authority="official_primary", related=None):
    return {"document_id": doc_id, "source_authority_at_discovery": authority,
            "record": {"title": title, "document_type": "law", "source_id": "majlis",
                       "related_document_ids": related or []},
            "structure": {"articles": [{"number": "1", "start_page": 1, "end_page": 1,
                                            "text_lines": ([{"page_number": 1, "line_number": 3, "text": text}] if text else [])}],
                          "preamble": [], "trailing_text": []}}


def test_builds_document_and_article_nodes_and_containment_edges():
    graph = build_document_graph([_doc("a", "قانون نمونه بسیار مهم")])
    assert graph["summary"]["document_count"] == 1
    assert graph["summary"]["article_node_count"] == 1
    assert graph["edges"][0]["type"] == "contains_article"


def test_exact_title_mention_creates_candidate_edge_with_provenance():
    target = _doc("target", "قانون نمونه بسیار مهم")
    source = _doc("source", "قانون دیگر و مستقل", "مطابق قانون نمونه بسیار مهم ماده ۵ اجرا می‌شود")
    graph = build_document_graph([target, source])
    edge = next(e for e in graph["edges"] if e["type"] == "mentions_document")
    assert edge["from"] == "source" and edge["to"] == "target"
    assert edge["evidence"]["page_number"] == 1
    assert edge["status"] == "candidate_unverified"


def test_amendment_phrase_is_only_possible_amendment():
    target = _doc("target", "قانون نمونه بسیار مهم")
    source = _doc("source", "قانون اصلاحی مستقل", "ماده واحده قانون نمونه بسیار مهم اصلاح می‌شود")
    graph = build_document_graph([target, source])
    edge = next(e for e in graph["edges"] if e["type"] == "possible_amends")
    assert edge["status"] == "human_legal_review_required"
    assert graph["safety"]["legal_effect_determined"] is False


def test_secondary_source_keeps_secondary_class_and_candidate_status():
    graph = build_document_graph([_doc("s", "قانون نمونه بسیار مهم", authority="secondary")])
    node = next(n for n in graph["nodes"] if n["type"] == "document")
    assert node["source_authority"] == "secondary"


def test_can_exclude_secondary_documents_by_policy():
    graph = build_document_graph([_doc("s", "قانون نمونه بسیار مهم", authority="secondary")],
                                 policy=RelationshipPolicy(include_secondary_candidates=False))
    assert graph["summary"]["document_count"] == 0


def test_catalog_relationship_hints_are_not_confirmed_facts():
    graph = build_document_graph([_doc("a", "قانون اول بسیار مهم", related=["b"]),
                                  _doc("b", "قانون دوم بسیار مهم")])
    edge = next(e for e in graph["edges"] if e["type"] == "catalog_relationship_hint")
    assert edge["status"] == "candidate_unverified"


def test_rejects_duplicate_document_ids_and_missing_identity():
    with pytest.raises(RelationshipBuildError):
        build_document_graph([_doc("a", "قانون نمونه بسیار مهم"), _doc("a", "قانون دیگر بسیار مهم")])
    with pytest.raises(RelationshipBuildError):
        build_document_graph([{"document_id": "", "record": {"title": "x"}}])


def test_enforces_document_and_edge_budgets():
    with pytest.raises(RelationshipBuildError):
        build_document_graph([_doc("a", "قانون نمونه بسیار مهم")], policy=RelationshipPolicy(max_documents=0))
    with pytest.raises(RelationshipBuildError):
        build_document_graph([_doc("a", "قانون نمونه بسیار مهم")], policy=RelationshipPolicy(max_edges=0))


def test_atomic_graph_write_and_safety_flags(tmp_path):
    graph = build_document_graph([_doc("a", "قانون نمونه بسیار مهم")])
    path = write_document_graph(graph, tmp_path / "graph.json")
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved["graph_sha256"] == graph["graph_sha256"]
    assert saved["safety"]["active_bank_write"] is False


def test_graph_hash_is_stable_for_same_content_except_timestamp():
    docs = [_doc("a", "قانون نمونه بسیار مهم")]
    first = build_document_graph(docs)
    second = build_document_graph(docs)
    assert first["graph_sha256"] == second["graph_sha256"]


def test_builds_note_band_and_subitem_hierarchy():
    doc = _doc("hier", "قانون ساختارمند بسیار مهم")
    doc["structure"]["articles"][0]["notes"] = [
        {"label": "تبصره", "number": "1", "text_lines": [{"page_number": 2, "text": "متن تبصره"}]}
    ]
    doc["structure"]["articles"][0]["bands"] = [
        {"label": "الف", "text_lines": [{"page_number": 3, "text": "متن بند"}],
         "subitems": [{"label": "1", "text_lines": [{"page_number": 3, "text": "متن جزء"}]}]}
    ]
    graph = build_document_graph([doc])
    assert graph["summary"]["note_node_count"] == 1
    assert graph["summary"]["band_node_count"] == 1
    assert graph["summary"]["subitem_node_count"] == 1
    assert {e["type"] for e in graph["edges"]} >= {"contains_note", "contains_band", "contains_subitem"}


@pytest.mark.parametrize("phrase,expected", [
    ("به قانون نمونه بسیار مهم الحاق می‌شود", "possible_adds"),
    ("متن قانون نمونه بسیار مهم جایگزین می‌شود", "possible_replaces"),
    ("عبارت قانون نمونه بسیار مهم حذف می‌شود", "possible_deletions"),
    ("شماره ماده قانون نمونه بسیار مهم به شماره جدید تغییر می‌کند", "possible_renumbering"),
])
def test_classifies_addition_replacement_deletion_and_renumbering_as_candidates(phrase, expected):
    target = _doc("target", "قانون نمونه بسیار مهم")
    source = _doc("source", "سند تغییرات مستقل", phrase)
    graph = build_document_graph([target, source])
    edge = next(e for e in graph["edges"] if e["type"] == expected)
    assert edge["status"] == "human_legal_review_required"
    assert edge["evidence"]["page_number"] == 1
    assert graph["safety"]["legal_effect_determined"] is False


def test_change_classification_requires_exact_target_title_and_never_confirms_effect():
    target = _doc("target", "قانون نمونه بسیار مهم")
    source = _doc("source", "سند تغییرات مستقل", "قانونی دیگر الحاق می‌شود")
    graph = build_document_graph([target, source])
    assert not any(e["type"].startswith("possible_") for e in graph["edges"])
    assert graph["safety"]["amendment_or_repeal_not_legally_confirmed"] is True


def test_edge_budget_applies_to_structural_edges_too():
    doc = _doc("budget", "قانون ساختارمند بسیار مهم")
    doc["structure"]["articles"][0]["notes"] = [
        {"label": "تبصره", "number": "1", "text_lines": []}
    ]
    with pytest.raises(RelationshipBuildError, match="edge count exceeds"):
        build_document_graph([doc], policy=RelationshipPolicy(max_edges=1))


def test_excluded_secondary_documents_do_not_create_dangling_catalog_edges():
    primary = _doc("primary", "قانون اصلی بسیار مهم", related=["secondary"])
    secondary = _doc("secondary", "قانون فرعی بسیار مهم", authority="secondary")
    graph = build_document_graph(
        [primary, secondary],
        policy=RelationshipPolicy(include_secondary_candidates=False),
    )
    assert {node["id"] for node in graph["nodes"] if node["type"] == "document"} == {"primary"}
    assert not any(edge["type"] == "catalog_relationship_hint" for edge in graph["edges"])


def test_title_prefix_inside_a_longer_word_does_not_create_relationship():
    target = _doc("target", "قانون نمونه بسیار مهم")
    source = _doc("source", "سند مستقل دیگر", "قانون نمونه بسیار مهمتر اصلاح می‌شود")
    graph = build_document_graph([target, source])
    assert not any(edge["to"] == "target" for edge in graph["edges"])
