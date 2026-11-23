from legal_bot.ai_preference_context import build_ai_preference_context


def _prefs():
    return {
        "writing_style": {"tone": "formal", "detail_level": "concise"},
        "legal_analysis": {"analysis_structure": "irac", "counterargument_review": True},
        "citations_and_sources": {"citation_density": "relevant_only", "citation_verification": True},
        "output_formats": {"heading_style": "numbered", "include_executive_summary": True},
        "document_review": {"review_focus": ["payment", "termination"], "comparison_mode": "clause_by_clause"},
        "assistant_interaction": {"clarification_behavior": "balanced"},
        "professional_context": {"practice_context_note": "DO NOT LEAK"},
    }


def test_contract_review_receives_contract_specific_preferences_only():
    block = build_ai_preference_context(_prefs(), task="contract_review")
    assert "بررسی قرارداد" in block
    assert "پرداخت" in block
    assert "فسخ و خاتمه" in block
    assert "IRAC" not in block
    assert "DO NOT LEAK" not in block


def test_legal_drafting_receives_drafting_preferences_not_contract_checklist():
    block = build_ai_preference_context(_prefs(), task="legal_drafting")
    assert "تنظیم لایحه" in block
    assert "رسمی" in block
    assert "مسئله، قاعده، تطبیق و نتیجه" in block
    assert "پرداخت" not in block
    assert "بندبه‌بند" not in block


def test_case_summary_is_compact_and_omits_citation_controls():
    block = build_ai_preference_context(_prefs(), task="case_summary")
    assert "خلاصه‌سازی پرونده" in block
    assert "مختصر" in block
    assert "- citation_density:" not in block and "- citation_verification:" not in block
    assert "پرداخت" not in block


def test_unknown_task_uses_safe_general_profile():
    block = build_ai_preference_context(_prefs(), task="untrusted-or-unknown")
    assert "کار عمومی حقوقی" in block
    assert "DO NOT LEAK" not in block
    assert "پرداخت" not in block


def test_ai_feature_routes_task_specific_profile(monkeypatch):
    from legal_bot import ai
    captured = {}

    def fake_loader(uid, *, task="general", **kwargs):
        captured["uid"] = uid
        captured["task"] = task
        return f"PROFILE:{task}"

    monkeypatch.setattr("legal_bot.ai_preference_context.load_ai_preference_context", fake_loader)
    monkeypatch.setattr(ai, "_call", lambda messages, temperature=0.05: messages)
    result = ai._call_feature(
        [{"role": "system", "content": "SYSTEM"}, {"role": "user", "content": "REQUEST"}],
        feature="contract_review", preference_uid=912,
    )
    assert captured == {"uid": 912, "task": "contract_review"}
    assert result[1]["content"] == "PROFILE:contract_review"
