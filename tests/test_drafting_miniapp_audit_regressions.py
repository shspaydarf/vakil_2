from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = (ROOT / "miniapp" / "app.js").read_text(encoding="utf-8")


def test_drafting_ui_does_not_claim_success_when_no_artifact_was_created():
    assert "if(!r.artifact?.id)" in APP
    assert "فرآیند اجرا شد اما نسخه قابل‌نمایش/ذخیره‌ای تولید نشد" in APP


def test_drafting_ui_handles_archived_and_missing_cases_explicitly():
    assert "r.status==='CASE_ARCHIVED'" in APP
    assert "r.status==='CASE_NOT_FOUND'" in APP
    assert "const archived=String(currentCase?.status||'').toLowerCase()==='archived'" in APP
    assert 'id="generateDraft" ${archived?' in APP


def test_drafting_ui_exposes_missing_information_without_faking_a_draft():
    assert "r.status==='NEEDS_INFORMATION'" in APP
    assert "برای ساخت پیش‌نویس، اطلاعات تکمیلی لازم است" in APP
    assert "renderDraftIntakeForm" in APP
    assert "ثبت پاسخ‌ها و ادامه لایحه‌نویسی" in APP


def test_review_request_is_explicitly_non_mutating_and_versioned():
    assert "درخواست اصلاح» فقط در تاریخچه ثبت می‌شود و متن را خودکار تغییر نمی‌دهد" in APP
    assert "برای دریافت نسخه تازه باید پیش‌نویس جدید تولید شود" in APP
