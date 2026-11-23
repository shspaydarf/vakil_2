import hashlib
import json
from pathlib import Path

from legal_bot.ingestion.bank_architecture import BANK_TARGETS, inspect_bank


def _write(path: Path, value):
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")


def test_inspect_bank_reports_shapes_and_hashes_without_writing(tmp_path):
    _write(tmp_path / "laws.json", {"قانون نمونه": [{"ماده": "1", "متن": "متن ماده"}]})
    _write(tmp_path / "rulings.json", {"rulings": [{"شماره": "1"}], "diwan_adalat_rulings": []})
    _write(tmp_path / "consultations.json", {"consultations": []})
    _write(tmp_path / "samples_and_circulars.json", {"samples": [], "circulars": []})
    before = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in tmp_path.iterdir()}

    result = inspect_bank(tmp_path)

    assert result["mode"] == "read_only_inventory"
    assert result["active_bank_modified"] is False
    assert set(result["files"]) == set(BANK_TARGETS)
    assert result["files"]["laws.json"]["record_count"] == 1
    assert result["files"]["rulings.json"]["record_count"] == 1
    after = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in tmp_path.iterdir()}
    assert before == after
    assert set(before) == set(after)


def test_inspect_bank_fails_closed_on_invalid_or_missing_file(tmp_path):
    (tmp_path / "laws.json").write_text("{bad", encoding="utf-8")
    result = inspect_bank(tmp_path)
    assert result["files"]["laws.json"]["status"] == "invalid_json"
    assert result["files"]["rulings.json"]["status"] == "missing"


def test_real_bank_inventory_is_read_only_and_all_target_files_parse():
    result = inspect_bank()
    assert result["active_bank_modified"] is False
    assert all(item["status"] == "valid_json" for item in result["files"].values())
    assert result["files"]["laws.json"]["record_count"] > 0
