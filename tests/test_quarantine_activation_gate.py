import json
from pathlib import Path

from legal_bot import laws


def test_quarantined_law_groups_are_not_in_active_index():
    blocked = set(laws.QUARANTINED_LAWS)
    assert blocked
    assert not any(record.get("law") in blocked for record in laws.INDEX)


def test_quarantined_records_are_preserved_outside_active_laws_json():
    data_dir = Path(__file__).resolve().parents[1] / "legal_bot" / "data" / "iran"
    active = json.loads((data_dir / "laws.json").read_text(encoding="utf-8"))
    quarantine = json.loads((data_dir / "quarantine" / "inactive_laws.json").read_text(encoding="utf-8"))
    assert quarantine["entries"]
    for title, entry in quarantine["entries"].items():
        assert title not in active
        assert entry["status"] == "quarantined"
        assert entry["records"]


def test_quarantine_audit_counts_match_preserved_records():
    data_dir = Path(__file__).resolve().parents[1] / "legal_bot" / "data" / "iran"
    quarantine = json.loads((data_dir / "quarantine" / "inactive_laws.json").read_text(encoding="utf-8"))
    audit = json.loads((data_dir / "quarantine" / "inactive_laws_audit_2026-10-31.json").read_text(encoding="utf-8"))
    assert audit["moved_groups"] == len(quarantine["entries"])
    assert audit["moved_records"] == sum(len(x["records"]) for x in quarantine["entries"].values())
