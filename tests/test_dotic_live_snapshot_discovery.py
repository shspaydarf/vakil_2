"""Regression tests based on a small, manually captured public Dotic HTML excerpt.
No network access is performed by these tests.
"""
from legal_bot.ingestion.connectors import DoticRegulationsConnector

SNAPSHOT = '''<html><body>
<a href="/news/21843">رای شماره 1709520 هیات عمومی دیوان عدالت اداری درخصوص ابطال مواد 7 و 8 آیین نامه</a>
<a href="/news/21824">مجموعه نظریات مشورتی اداره کل حقوقی قوه قضائیه در مهرماه 1405 منتشر شد</a>
<a href="/news/21840">رأی وحدت رویه شماره 881 هیأت عمومی دیوان عالی کشور</a>
<a href="https://evil.example/news/999">نظریه مشورتی جعلی</a>
</body></html>'''
BASE = "https://dotic.ir/"


def test_dotic_snapshot_discovers_administrative_court_general_assembly_record():
    found = list(DoticRegulationsConnector().discover_from_html(
        SNAPSHOT, BASE, category="administrative_justice_general_assembly_rulings"))
    assert len(found) == 1
    assert found[0].source_record_id == "21843"
    assert found[0].page_url == "https://dotic.ir/news/21843"
    assert found[0].asset_url is None
    assert "ورود به بانک فعال مجاز نیست" in found[0].notes


def test_dotic_snapshot_discovers_advisory_opinion_collection_without_claiming_pdf():
    found = list(DoticRegulationsConnector().discover_from_html(
        SNAPSHOT, BASE, category="judiciary_advisory_opinions"))
    assert len(found) == 1
    assert found[0].source_record_id == "21824"
    assert found[0].document_type == "advisory_opinion_collection_record"
    assert found[0].asset_url is None


def test_dotic_snapshot_separates_supreme_court_unity_ruling():
    found = list(DoticRegulationsConnector().discover_from_html(
        SNAPSHOT, BASE, category="supreme_court_unity_rulings"))
    assert len(found) == 1
    assert found[0].source_record_id == "21840"
