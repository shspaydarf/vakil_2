from legal_bot.ingestion.bulk_processing_architecture import (
    BatchPolicy, architecture_blueprint, create_batch_plan, write_batch_plan,
)


def item(doc, source="majles", kind="law", **extra):
    return {"document_id": doc, "source_id": source, "document_type": kind,
            "source_class": "official_primary", **extra}


def test_plan_is_deterministic_and_planning_only():
    candidates = [item("b"), item("a", kind="ruling")]
    one = create_batch_plan(candidates)
    two = create_batch_plan(candidates)
    assert one["plan_id"] == two["plan_id"]
    assert one["mode"] == "planning_only_dry_run"
    assert one["execution"]["network_access"] is False
    assert one["execution"]["active_bank_modified"] is False
    assert one["selected"][0]["document_id"] == "b"


def test_untrusted_sources_are_rejected_by_default():
    candidate = item("x") | {"source_class": "secondary"}
    plan = create_batch_plan([candidate])
    assert not plan["selected"]
    assert "source_class_not_permitted" in plan["rejected"][0]["reason"]


def test_batch_and_ocr_budgets_defer_without_dropping():
    policy = BatchPolicy(max_documents=1, max_total_bytes=100, max_ocr_pages=2,
                         max_documents_per_source=5)
    plan = create_batch_plan([
        item("a", estimated_bytes=60, requires_ocr=True, estimated_pages=2),
        item("b", estimated_bytes=60, requires_ocr=True, estimated_pages=1),
    ], policy=policy)
    assert len(plan["selected"]) == 1
    assert len(plan["deferred"]) == 1
    assert plan["resource_estimate"]["estimated_ocr_pages"] == 2


def test_duplicate_identity_and_conflict_are_separated():
    a = item("same")
    identical = item("same")
    conflict = item("same", kind="ruling")
    plan = create_batch_plan([a, identical, conflict])
    assert plan["duplicates_skipped"] == 1
    assert any(x["reason"] == "conflicting_duplicate_document_identity" for x in plan["rejected"])


def test_per_source_limit_is_enforced():
    policy = BatchPolicy(max_documents=10, max_total_bytes=1000, max_ocr_pages=10,
                         max_documents_per_source=1)
    plan = create_batch_plan([item("a"), item("b")], policy=policy)
    assert len(plan["selected"]) == 1
    assert plan["deferred"][0]["reason"] == "per_source_document_limit"


def test_invalid_items_are_rejected_and_policy_validation_is_strict():
    plan = create_batch_plan([{}, item("ok")])
    assert len(plan["rejected"]) == 1
    try:
        create_batch_plan([], policy=BatchPolicy(max_documents=0))
    except ValueError:
        pass
    else:
        raise AssertionError("invalid policy accepted")


def test_plan_artifact_is_written_atomically(tmp_path):
    plan = create_batch_plan([item("a")])
    path = write_batch_plan(plan, tmp_path / "plans" / "batch.json")
    assert path.exists()
    assert 'planning_only_dry_run' in path.read_text(encoding="utf-8")


def test_blueprint_covers_all_later_phases_and_invariants():
    blueprint = architecture_blueprint()
    phases = {component["phase"] for component in blueprint["components"]}
    assert phases == {"7.2", "7.3", "7.4", "7.5", "7.6", "7.7", "7.8", "7.9"}
    assert "active_bank_is_read_only_until_explicit_phase_7_9_approval" in blueprint["global_invariants"]
