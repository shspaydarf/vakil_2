from dataclasses import asdict

import pytest

from legal_bot.ingestion.candidate_adapter import (
    batch_to_catalog_records, candidate_to_catalog_record, mapping_summary,
)
from legal_bot.ingestion.document_catalog import DocumentCatalog, DocumentRecord
from legal_bot.ingestion.models import CandidateDocument, DiscoveryBatch


def candidate(**overrides):
    values = dict(
        source_id="qavanin_national", source_name="Qavanin", source_role="official_registry_candidate_unverified",
        document_type="supreme_court_ruling_candidate", title="رأی وحدت رویه نمونه",
        page_url="https://qavanin.ir/Law/TreeText/?IDS=123", asset_url=None,
        source_record_id="123", issuer="دیوان عالی کشور", document_date="۱۴۰۲-۰۵-۰۱",
        notes="fixture candidate",
    )
    values.update(overrides)
    return CandidateDocument(**values)


def test_candidate_maps_catalog_type_and_preserves_family_and_provenance():
    record = candidate_to_catalog_record(candidate())
    assert record.document_type == "ruling"
    assert record.document_family == "supreme_court_unity_rulings"
    assert record.external_id == "123"
    assert record.source_record_id == "123"
    assert record.discovery_page_url == "https://qavanin.ir/Law/TreeText/?IDS=123"
    assert record.approval_date is None  # source date is not assumed to be approval date
    assert record.source_document_date == "1402-05-01"
    assert record.discovery_method == "connector_fixture_or_saved_html"


def test_catalog_record_round_trip_keeps_optional_connector_fields():
    original = candidate_to_catalog_record(candidate())
    restored = DocumentRecord.from_dict(asdict(original))
    assert restored.document_family == original.document_family
    assert restored.connector_document_type == original.connector_document_type
    assert restored.discovery_page_url == original.discovery_page_url


def test_batch_conversion_rejects_mixed_source_atomically():
    batch = DiscoveryBatch(source_id="qavanin_national", category="laws", candidates=[
        candidate(), candidate(source_id="other_source")
    ])
    with pytest.raises(ValueError, match="discovery_batch_source_mismatch"):
        batch_to_catalog_records(batch)


def test_unknown_connector_type_fails_closed():
    with pytest.raises(ValueError, match="unsupported_connector_document_type"):
        candidate_to_catalog_record(candidate(document_type="mystery_document"))


def test_non_https_candidate_url_is_rejected():
    with pytest.raises(ValueError, match="candidate_url_must_be_https"):
        candidate_to_catalog_record(candidate(page_url="http://qavanin.ir/Law/1"))


def test_asset_url_is_kept_separate_from_discovery_page():
    record = candidate_to_catalog_record(candidate(
        document_type="parliamentary_law_pdf", source_id="majles_rc",
        page_url="https://rc.majlis.ir/fa/law/show/12", asset_url="https://rc.majlis.ir/files/law.pdf",
        source_record_id="12",
    ))
    assert record.document_url == "https://rc.majlis.ir/files/law.pdf"
    assert record.discovery_page_url == "https://rc.majlis.ir/fa/law/show/12"
    assert record.asset_url == "https://rc.majlis.ir/files/law.pdf"
    assert record.document_family == "laws"


def test_mapping_summary_is_fail_closed_and_offline():
    summary = mapping_summary()
    assert summary["unknown_types_fail_closed"] is True
    assert summary["network_access"] is False
    assert summary["active_bank_write"] is False
