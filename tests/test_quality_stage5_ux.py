from legal_bot.output_engine import render_output_overview


def test_output_overview_gives_plain_language_next_steps_for_blocked_draft():
    text = render_output_overview({
        "status": "BLOCKED",
        "findings": [{"severity": "high", "problem": "ادعای نیازمند بررسی"}],
        "changes": [{"change_id": "chg-1"}],
        "gate": {"counts": {"high": 1, "medium": 2, "low": 0}},
    })
    assert "هنوز به بررسی بیشتر نیاز دارد" in text
    assert "ابتدا موارد جدی" in text
    assert "گزارش تغییرات" in text
    assert "نسخه نهایی" in text
    assert "API" in text


def test_output_overview_pass_never_claims_legal_approval():
    text = render_output_overview({
        "status": "PASS", "findings": [], "changes": [],
        "gate": {"counts": {"high": 0, "medium": 0, "low": 0}},
    })
    assert "مانع جدی ثبت نکرده" in text
    assert "صحت حقوقی" in text
    assert "تأیید وکیل" in text


def test_output_overview_handles_missing_artifact_error_with_recovery_hint():
    text = render_output_overview({"error": "خروجی موجود نیست"})
    assert "آماده‌سازی خروجی انجام نشد" in text
    assert "دوباره تلاش کنید" in text
