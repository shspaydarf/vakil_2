import pytest
from legal_bot.ingestion.pipeline_contracts import (
    make_envelope, validate_envelope, stable_document_key, version_key,
    can_transition, transition,
)


def envelope(**updates):
    row = make_envelope(source_id="majles", document_kind="law", title="قانون نمونه",
                        document_id="machina_doc_1234567890", source_url="https://rc.majlis.ir/law/1",
                        external_id="93849")
    row.update(updates)
    return row


def test_valid_envelope():
    assert validate_envelope(envelope())["state"] == "discovered"


def test_rejects_http_and_credentials():
    with pytest.raises(ValueError):
        validate_envelope(envelope(source_url="http://example.org/a"))
    with pytest.raises(ValueError):
        validate_envelope(envelope(source_url="https://user:pass@example.org/a"))


def test_rejects_invalid_pages_and_hash():
    with pytest.raises(ValueError):
        validate_envelope(envelope(page_count=0))
    with pytest.raises(ValueError):
        validate_envelope(envelope(content_sha256="bad"))


def test_stable_key_prefers_official_number_across_sources():
    a = {"document_kind":"law", "issuer":"مجلس شورای اسلامی", "official_number":"۱۲۳", "approval_date":"1400-01-01", "source_id":"majles", "external_id":"a"}
    b = dict(a, source_id="gazette", external_id="b")
    assert stable_document_key(a) == stable_document_key(b)


def test_stable_key_requires_identifier_not_title_only():
    with pytest.raises(ValueError):
        stable_document_key({"document_kind":"law", "title":"قانون نمونه"})


def test_version_key_changes_with_content():
    doc = "machina_doc_1234567890"
    a = version_key(doc, "a" * 64)
    b = version_key(doc, "b" * 64)
    assert a != b


def test_lifecycle_transition_rules():
    row = envelope()
    row = transition(row, "identity_checked")
    row = transition(row, "queued")
    assert row["state"] == "queued"
    assert not can_transition("imported", "queued")
    with pytest.raises(ValueError):
        transition(row, "imported")


def test_integration_map_declares_expected_document_scope():
    import json
    from pathlib import Path
    path = Path(__file__).parents[1] / "legal_bot" / "ingestion" / "PHASE10_1_2_DATA_CONTRACTS_AND_INTEGRATION_MAP.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    assert set(data["document_kinds"]) == {
        "law", "regulation", "supreme_court_ruling",
        "administrative_court_ruling", "advisory_opinion",
    }
    assert data["active_bank_write_performed"] is False
